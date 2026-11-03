import json
import logging
import time
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from .models import ReportCard, SubjectMark

logger = logging.getLogger(__name__)

FEEDBACK_CACHE_KEY = "report-card-groq-feedback-templates"
FEEDBACK_CACHE_SECONDS = 60 * 60 * 24
FEEDBACK_CATEGORIES = ("needs_support", "developing", "strong")
GROQ_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class AIServiceUnavailable(APIException):
    status_code = 503
    default_detail = "AI feedback is currently unavailable. Please try again later."
    default_code = "ai_service_unavailable"


def _feedback_templates():
    templates = cache.get(FEEDBACK_CACHE_KEY)
    if templates is not None:
        return templates

    api_key = settings.GROQ_API_KEY
    if not api_key:
        raise AIServiceUnavailable("GROQ_API_KEY is not configured on the server.")

    request_data = json.dumps(
        {
            "model": settings.GROQ_MODEL,
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Write brief, constructive, teacher-facing feedback templates. "
                        "Return only a JSON object with exactly these string keys: "
                        "needs_support, developing, strong. Each value should be one "
                        "or two neutral, actionable sentences. These are reusable "
                        "templates, not assessments of real students. Do not include "
                        "names, marks, percentages, rankings, subjects, or invented facts."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Create one reusable feedback template for each general "
                        "performance band: needs_support, developing, and strong. "
                        "Give supportive teaching suggestions only. No student "
                        "records or identifying details are provided."
                    ),
                },
            ],
        }
    ).encode("utf-8")
    request = Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=request_data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": GROQ_USER_AGENT,
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as provider_response:
            provider_payload = json.loads(provider_response.read())
    except HTTPError as exc:
        logger.warning("Groq returned HTTP status %s.", exc.code)
        raise AIServiceUnavailable() from exc
    except (TimeoutError, URLError) as exc:
        logger.warning("Could not reach Groq: %s", exc)
        raise AIServiceUnavailable() from exc
    except OSError as exc:
        logger.warning("Could not read the Groq response: %s", exc)
        raise AIServiceUnavailable() from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("Groq returned an invalid response.")
        raise AIServiceUnavailable() from exc

    try:
        message = provider_payload["choices"][0]["message"]["content"]
        templates = json.loads(message)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        logger.warning("Groq response did not contain valid feedback templates.")
        raise AIServiceUnavailable() from exc

    if not isinstance(templates, dict) or set(templates) != set(
        FEEDBACK_CATEGORIES
    ) or any(
        not isinstance(templates.get(category), str)
        or not templates[category].strip()
        or len(templates[category]) > 1200
        for category in FEEDBACK_CATEGORIES
    ):
        logger.warning("Groq feedback templates did not match the required format.")
        raise AIServiceUnavailable()

    templates = {
        category: templates[category].strip()
        for category in FEEDBACK_CATEGORIES
    }
    cache.set(FEEDBACK_CACHE_KEY, templates, FEEDBACK_CACHE_SECONDS)
    return templates


def generate_teacher_summary(report_card):
    marks = SubjectMark.objects.filter(
        student_id=report_card.student_id,
        examination_id=report_card.examination_id,
    ).aggregate(
        earned=Coalesce(
            Sum("marks"),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        ),
        possible=Coalesce(
            Sum("subject__maximum_marks"),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        ),
        subject_count=Count("pk"),
    )
    possible = marks["possible"]
    if not marks["subject_count"] or possible <= 0:
        raise ValidationError(
            "Add subject marks with a non-zero maximum before generating feedback."
        )

    percentage = marks["earned"] * Decimal("100") / possible
    if percentage < 50:
        category = "needs_support"
    elif percentage < 80:
        category = "developing"
    else:
        category = "strong"

    feedback = _feedback_templates()[category]
    return (
        f"{feedback} Current average: {percentage:.1f}% across "
        f"{marks['subject_count']} subjects."
    )


def save_teacher_summary(report_card):
    report_card.teacher_summary = generate_teacher_summary(report_card)
    report_card.summary_generated_at = timezone.now()
    report_card.save(update_fields=["teacher_summary", "summary_generated_at"])
    return report_card


def _request_groq_json(messages):
    if not settings.GROQ_API_KEY:
        raise AIServiceUnavailable("GROQ_API_KEY is not configured on the server.")

    models_to_try = [
        getattr(settings, "GROQ_MODEL", "qwen/qwen3.8-27b"),
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
    ]
    seen = set()
    models_to_try = [m for m in models_to_try if m and not (m in seen or seen.add(m))]

    # Ensure 'json' is in messages for json_object mode
    safe_messages = list(messages)
    if not any("json" in str(m.get("content", "")).lower() for m in safe_messages):
        if safe_messages:
            safe_messages[0] = dict(safe_messages[0])
            safe_messages[0]["content"] = f"{safe_messages[0].get('content', '')}\nRespond in valid JSON format."

    last_error = None
    for model in models_to_try:
        try:
            request = Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=json.dumps(
                    {
                        "model": model,
                        "temperature": 0.2,
                        "response_format": {"type": "json_object"},
                        "messages": safe_messages,
                    }
                ).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                    "User-Agent": GROQ_USER_AGENT,
                },
                method="POST",
            )
            with urlopen(request, timeout=30) as provider_response:
                response_data = json.loads(provider_response.read())
            content = response_data["choices"][0]["message"]["content"]
            result = json.loads(content)
            if not isinstance(result, dict):
                raise AIServiceUnavailable("Groq returned an unexpected response.")
            return result
        except HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
            logger.warning("Groq returned HTTP status %s for model %s: %s", exc.code, model, err_body)
            last_error = exc
            if exc.code in (400, 404, 429, 500, 502, 503, 504):
                time.sleep(0.5)
                continue
            raise AIServiceUnavailable() from exc
        except (TimeoutError, URLError, OSError) as exc:
            logger.warning("Could not reach Groq (%s): %s", model, exc)
            last_error = exc
            continue
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            logger.warning("Groq returned an invalid structured response.")
            raise AIServiceUnavailable() from exc

    raise AIServiceUnavailable() from last_error


def stream_groq_chat(messages, temperature=0.6):
    api_key = settings.GROQ_API_KEY
    if not api_key:
        raise AIServiceUnavailable("GROQ_API_KEY is not configured on the server.")

    models_to_try = [
        getattr(settings, "GROQ_MODEL", "qwen/qwen3.8-27b"),
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
    ]
    seen = set()
    models_to_try = [m for m in models_to_try if m and not (m in seen or seen.add(m))]

    last_error = None
    for model in models_to_try:
        try:
            req_payload = json.dumps(
                {
                    "model": model,
                    "temperature": temperature,
                    "messages": messages,
                    "stream": True,
                }
            ).encode("utf-8")
            request = Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=req_payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": GROQ_USER_AGENT,
                },
                method="POST",
            )
            with urlopen(request, timeout=45) as provider_response:
                for line in provider_response:
                    line_str = line.decode("utf-8", errors="replace").strip()
                    if not line_str or not line_str.startswith("data:"):
                        continue
                    data_str = line_str[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = (
                            chunk.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content", "")
                        )
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
            return
        except HTTPError as exc:
            logger.warning("Groq model %s failed with %s: %s", model, exc.code, exc)
            last_error = exc
            if exc.code in (404, 429, 500, 502, 503, 504):
                time.sleep(0.5)
                continue
            raise AIServiceUnavailable() from exc
        except (TimeoutError, URLError, OSError) as exc:
            logger.warning("Groq connection failed for %s: %s", model, exc)
            last_error = exc
            continue

    if last_error:
        raise AIServiceUnavailable() from last_error


def propose_grading_policy(requirements):
    result = _request_groq_json(
        [
            {
                "role": "system",
                "content": (
                    "Propose a grading policy based only on the institution's stated "
                    "requirements. Return JSON with keys name, grade_boundaries, "
                    "minimum_passing_percentage, require_subject_pass, "
                    "subject_passing_percentage, weighted_subjects. grade_boundaries "
                    "must cover 0 to 100 continuously in 0.01 increments and each "
                    "entry has grade, min_percentage, max_percentage. Never claim "
                    "the policy is official or approved. If requirements do not "
                    "specify a policy, return a conventional proposal with grades "
                    "A (90-100), B (80-89.99), C (70-79.99), D (60-69.99), "
                    "E (50-59.99), F (0-49.99), passing threshold 40, and no "
                    "subject-wise pass requirement."
                ),
            },
            {
                "role": "user",
                "content": requirements,
            },
        ]
    )
    expected_keys = {
        "name",
        "grade_boundaries",
        "minimum_passing_percentage",
        "require_subject_pass",
        "subject_passing_percentage",
        "weighted_subjects",
    }
    if set(result) != expected_keys:
        raise AIServiceUnavailable("Groq returned an incomplete grading proposal.")
    return result


def clarify_grading_requirements(requirements):
    result = _request_groq_json(
        [
            {
                "role": "system",
                "content": (
                    "You are a school grading-policy clarification assistant. "
                    "Return JSON with one string field named clarification, no more "
                    "than 800 characters. Ask at most three concise questions only "
                    "about grade boundaries, minimum passing percentages, "
                    "subject-wise pass requirements, and subject weights. If the "
                    "requirements are clear, say they are clear and invite the "
                    "teacher to request a proposal. Do not invent policy details, "
                    "approve policies, or calculate student results."
                ),
            },
            {"role": "user", "content": requirements},
        ]
    )
    clarification = result.get("clarification")
    if (
        not isinstance(clarification, str)
        or not clarification.strip()
        or len(clarification) > 800
    ):
        raise AIServiceUnavailable("Groq returned invalid grading clarification.")
    return clarification.strip()


def answer_workflow_question(question, step, context=None):
    allowed_steps = {
        "marks": "enter student details and subject marks",
        "confirm_marks": "review and confirm the entered student details and marks",
        "policy_choice": "choose an existing, proposed, or custom grading policy",
        "existing_policy": "select an approved grading policy",
        "requirements": "describe or clarify institutional grading requirements",
        "custom_policy": "customize grade boundaries, passing rules, and subject weights",
        "approve_policy": "review and approve a grading policy",
        "comparison": "provide complete class comparison marks or continue without ranking",
        "preview": "review the calculated report card before issuing it",
    }
    current_step = allowed_steps.get(step)
    if current_step is None:
        raise ValidationError("Questions are not available after the report is issued.")
    question = question.strip()
    if not question or len(question) > 1000:
        raise ValidationError(
            {"question": "Enter a question of 1,000 characters or fewer."}
        )
    result = _request_groq_json(
        [
            {
                "role": "system",
                "content": (
                    "You are a concise guide for a teacher using a report-card "
                    "assistant. Answer only workflow and policy-process questions, "
                    "using the supplied current workflow step. Return JSON with a "
                    "single string field named answer, no more than 1200 characters. "
                    "Use the supplied conversation and saved report details as context "
                    "when relevant, but do not expose personal details unnecessarily. "
                    "Never invent or calculate official marks, grades, pass/fail, rank, "
                    "or percentile. "
                    "Do not approve grading policies or claim an AI proposal is official."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "current_step": current_step,
                        "question": question,
                        "saved_context": context or {},
                    }
                ),
            },
        ]
    )
    answer = result.get("answer")
    if not isinstance(answer, str) or not answer.strip() or len(answer) > 1200:
        raise AIServiceUnavailable("Groq returned invalid workflow guidance.")
    return answer.strip()


def generate_academic_feedback(subject_results):
    feedback_data = [
        {
            "subject": item["subject"],
            "percentage": item["percentage"],
        }
        for item in subject_results
    ]
    try:
        result = _request_groq_json(
            [
                {
                    "role": "system",
                    "content": (
                        "Write supportive, concise academic feedback for a teacher to "
                        "review. Use only subject-level percentages provided. Do not "
                        "calculate or state official marks, grades, rank, percentile, "
                        "or pass/fail results. Do not invent student traits or claim "
                        "the output is an official assessment. Return JSON with one "
                        "string field named feedback, up to 1000 characters."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({"subject_results": feedback_data}),
                },
            ]
        )
        feedback = result.get("feedback")
        if isinstance(feedback, str) and feedback.strip() and len(feedback) <= 1000:
            return feedback.strip()
    except Exception as exc:
        logger.warning("Could not generate AI feedback with Groq: %s", exc)

    # Fallback feedback when AI provider is rate-limited or unavailable
    strong = [item["subject"] for item in subject_results if Decimal(item.get("percentage", "0")) >= 75]
    needs_support = [item["subject"] for item in subject_results if Decimal(item.get("percentage", "0")) < 50]
    parts = []
    if strong:
        parts.append(f"Demonstrates consistent dedication and solid academic proficiency in {', '.join(strong)}.")
    if needs_support:
        parts.append(f"Recommended for guided review and additional practice in {', '.join(needs_support)}.")
    if not parts:
        parts.append("Maintains balanced academic effort and steady participation across coursework.")
    return " ".join(parts)
