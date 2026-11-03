from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import (
    AssistantSession,
    Examination,
    GradingPolicy,
    ReportCard,
    Student,
    Subject,
    SubjectMark,
)


WELCOME_MESSAGE = (
    "Welcome to the AI Report Card Assistant! I'll ask for the report details one "
    "question at a time. Your answers are saved in this conversation as we go."
)
DETAIL_INTAKE_FIELDS = (
    ("name", "Student name", "What is the student's full name?", 150, False),
    ("roll_number", "Roll number", "What is the student's roll number?", 30, False),
    ("class_name", "Class", "Which class is the student in?", 50, False),
    ("section", "Section", "Which section is the student in?", 30, True),
    ("academic_year", "Academic year", "Which academic year is this report card for?", 20, False),
    ("examination_name", "Examination name", "What is the name of this examination?", 120, False),
)
MARK_INTAKE_FIELDS = (
    ("subject", "Subject", "text"),
    ("marks", "Marks obtained", "number"),
    ("maximum_marks", "Maximum marks", "number"),
)
POLICY_QUESTION = "Do you already have a grading system that your school follows?"
SUBJECT_COUNT_WORDS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
}


def _append_message(session, role, content):
    session.messages = [*session.messages, {"role": role, "content": content}]


def _new_intake_state():
    return {
        "phase": "details",
        "detail_index": 0,
        "subject_index": 0,
        "mark_field_index": 0,
        "current_mark": {},
        "input": {
            "type": "text",
            "label": DETAIL_INTAKE_FIELDS[0][1],
            "placeholder": "Enter the student's full name",
            "required": True,
            "max_length": DETAIL_INTAKE_FIELDS[0][3],
        },
    }


def _first_intake_question():
    return DETAIL_INTAKE_FIELDS[0][2]


def create_assistant_session():
    session = AssistantSession.objects.create(
        step=AssistantSession.Step.MARKS,
        messages=[
            {"role": "assistant", "content": WELCOME_MESSAGE},
            {"role": "assistant", "content": _first_intake_question()},
        ],
        state={
            "details": {},
            "marks": [],
            "rank_requested": True,
            "intake": _new_intake_state(),
        },
    )
    return session


def ensure_assistant_intake(session):
    if (
        session.step == AssistantSession.Step.MARKS
        and not isinstance(session.state.get("intake"), dict)
    ):
        state = dict(session.state)
        state.setdefault("details", {})
        state.setdefault("marks", [])
        state.setdefault("rank_requested", True)
        state["intake"] = _new_intake_state()
        session.state = state
        _append_message(session, "assistant", _first_intake_question())
        session.save(update_fields=["state", "messages", "updated_at"])
    return session


def _decimal(value, label):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({label: "Enter a valid number."}) from None
    if not result.is_finite():
        raise ValidationError({label: "Enter a finite number."})
    return result


def validate_student_marks(data):
    details = data.get("details", {})
    marks = data.get("marks", [])
    if not isinstance(details, dict):
        raise ValidationError({"details": "Provide student details as an object."})
    required_fields = {
        "name": "Student name",
        "roll_number": "Roll number",
        "class_name": "Class",
        "academic_year": "Academic year",
        "examination_name": "Examination name",
    }
    errors = {
        field: f"{label} is required."
        for field, label in required_fields.items()
        if not str(details.get(field, "")).strip()
    }
    if errors:
        raise ValidationError({"details": errors})
    if not isinstance(marks, list) or not marks:
        raise ValidationError({"marks": "Enter marks for at least one subject."})

    clean_marks = []
    seen_subjects = set()
    for index, mark in enumerate(marks):
        if not isinstance(mark, dict):
            raise ValidationError({"marks": f"Subject entry {index + 1} is invalid."})
        subject_name = str(mark.get("subject", "")).strip()
        if not subject_name:
            raise ValidationError({"marks": f"Subject {index + 1} needs a name."})
        if len(subject_name) > 100:
            raise ValidationError(
                {"marks": f"Subject {index + 1} must be 100 characters or fewer."}
            )
        subject_key = subject_name.casefold()
        if subject_key in seen_subjects:
            raise ValidationError(
                {"marks": f"Subject {subject_name} appears more than once."}
            )
        seen_subjects.add(subject_key)
        obtained = _decimal(mark.get("marks"), f"marks.{index}.marks")
        maximum = _decimal(
            mark.get("maximum_marks"), f"marks.{index}.maximum_marks"
        )
        if obtained.as_tuple().exponent < -2 or maximum.as_tuple().exponent < -2:
            raise ValidationError(
                {"marks": f"{subject_name}: marks can have at most two decimal places."}
            )
        if maximum <= 0:
            raise ValidationError(
                {"marks": f"{subject_name}: maximum marks must be greater than zero."}
            )
        if obtained < 0 or obtained > maximum:
            raise ValidationError(
                {
                    "marks": (
                        f"{subject_name}: marks must be between 0 and "
                        f"{maximum}."
                    )
                }
            )
        if maximum > Decimal("99999.99"):
            raise ValidationError(
                {"marks": f"{subject_name}: maximum marks cannot exceed 99,999.99."}
            )
        clean_marks.append(
            {
                "subject": subject_name,
                "marks": str(obtained),
                "maximum_marks": str(maximum),
            }
        )
        if len(clean_marks) > 100:
            raise ValidationError({"marks": "A report card can include at most 100 subjects."})

    clean_details = {
        field: str(value).strip()
        for field, value in details.items()
        if field in {
            "name", "roll_number", "class_name", "section", "academic_year",
            "examination_name",
        }
    }
    length_limits = {
        "name": 150,
        "roll_number": 30,
        "class_name": 50,
        "section": 30,
        "academic_year": 20,
        "examination_name": 120,
    }
    too_long = {
        field: f"{field.replace('_', ' ').title()} must be {limit} characters or fewer."
        for field, limit in length_limits.items()
        if len(clean_details.get(field, "")) > limit
    }
    if too_long:
        raise ValidationError({"details": too_long})
    return clean_details, clean_marks


def _intake_question(state, intake):
    details = state.get("details", {})
    if intake["phase"] == "details":
        field, label, prompt, limit, optional = DETAIL_INTAKE_FIELDS[
            intake["detail_index"]
        ]
        return prompt, {
            "type": "text",
            "label": label,
            "placeholder": (
                "Enter a section, or use Skip"
                if optional
                else f"Enter {label.lower()}"
            ),
            "required": not optional,
            "max_length": limit,
        }
    if intake["phase"] == "subject":
        field_index = intake["mark_field_index"]
        field, label, input_type = MARK_INTAKE_FIELDS[field_index]
        subject_number = intake["subject_index"] + 1
        subject = intake["current_mark"].get("subject", "")
        prompts = (
            f"What is the name of subject {subject_number}?",
            f"How many marks did {details.get('name', 'the student')} get in {subject}?",
            f"What is the maximum possible mark for {subject}?",
        )
        input_data = {
            "type": input_type,
            "label": label,
            "placeholder": f"Enter {label.lower()}",
            "required": True,
            "max_length": 100 if field == "subject" else None,
        }
        if input_type == "number":
            input_data.update({"min": "0" if field == "marks" else "0.01", "step": "0.01"})
        return prompts[field_index], input_data
    if intake["phase"] == "more_subjects":
        return (
            "Would you like to add another subject? Reply yes or no.",
            {
                "type": "text",
                "label": "Add another subject?",
                "placeholder": "Type yes or no",
                "required": True,
                "max_length": 20,
            },
        )
    return (
        "Would you like to include class rank and percentile? Reply yes or no.",
        {
            "type": "text",
            "label": "Include class rank?",
            "placeholder": "Type yes or no",
            "required": True,
            "max_length": 20,
        },
    )


def _yes_or_no(answer, label):
    normalized = answer.casefold()
    if normalized in {"yes", "y", "yeah", "yep", "true"}:
        return True
    if normalized in {"no", "n", "nope", "false"}:
        return False
    raise ValidationError({label: "Please reply yes or no."})


def _advance_intake_answer(session, state, data):
    intake = dict(state.get("intake", {}))
    if not intake:
        raise ValidationError("Start a new assistant conversation before answering.")
    answer = data.get("answer")
    if not isinstance(answer, str):
        raise ValidationError({"answer": "Enter your answer as text."})
    answer = answer.strip()
    if len(answer) > 1000:
        raise ValidationError({"answer": "Answers must be 1,000 characters or fewer."})

    details = dict(state.get("details", {}))
    marks = list(state.get("marks", []))
    assistant_reply = ""
    if intake["phase"] == "details":
        field, label, _, limit, optional = DETAIL_INTAKE_FIELDS[intake["detail_index"]]
        value = "" if optional and answer.casefold() in {"skip", "none", "n/a", "na"} else answer
        if not value and not optional:
            raise ValidationError({"answer": f"{label} is required."})
        if len(value) > limit:
            raise ValidationError(
                {"answer": f"{label} must be {limit} characters or fewer."}
            )
        details[field] = value
        intake["detail_index"] += 1
        if intake["detail_index"] == len(DETAIL_INTAKE_FIELDS):
            marks = []
            intake.update(
                {
                    "phase": "subject",
                    "subject_index": 0,
                    "mark_field_index": 0,
                    "current_mark": {},
                }
            )
        assistant_reply, intake["input"] = _intake_question(state | {"details": details}, intake)
        if field == "name":
            assistant_reply = f"Nice to meet you, {value}. {assistant_reply}"
        if optional and not value:
            answer = "Skip section (optional)."
    elif intake["phase"] == "subject":
        field, label, _ = MARK_INTAKE_FIELDS[intake["mark_field_index"]]
        current_mark = dict(intake.get("current_mark", {}))
        if not answer:
            raise ValidationError({"answer": f"{label} is required."})
        if field == "subject":
            if len(answer) > 100:
                raise ValidationError({"answer": "Subject names must be 100 characters or fewer."})
            if any(mark["subject"].casefold() == answer.casefold() for mark in marks):
                raise ValidationError({"answer": f"{answer} has already been entered."})
            current_mark[field] = answer
        else:
            value = _decimal(answer, label)
            if value.as_tuple().exponent < -2:
                raise ValidationError({"answer": "Marks can have at most two decimal places."})
            if field == "marks" and value < 0:
                raise ValidationError({"answer": "Marks obtained cannot be negative."})
            if field == "maximum_marks":
                if value <= 0:
                    raise ValidationError({"answer": "Maximum marks must be greater than zero."})
                if value > Decimal("99999.99"):
                    raise ValidationError({"answer": "Maximum marks cannot exceed 99,999.99."})
                if Decimal(current_mark["marks"]) > value:
                    raise ValidationError(
                        {"answer": f"Marks obtained cannot exceed {value} for {current_mark['subject']}."}
                    )
            current_mark[field] = str(value)
        intake["current_mark"] = current_mark
        intake["mark_field_index"] += 1
        if intake["mark_field_index"] == len(MARK_INTAKE_FIELDS):
            marks.append(current_mark)
            intake.update(
                {
                    "phase": "more_subjects",
                    "subject_index": len(marks) - 1,
                    "mark_field_index": 0,
                    "current_mark": {},
                }
            )
        assistant_reply, intake["input"] = _intake_question(
            state | {"details": details, "marks": marks}, intake
        )
        if field == "maximum_marks":
            assistant_reply = (
                f"Saved {current_mark['subject']}: {current_mark['marks']} / "
                f"{current_mark['maximum_marks']}. {assistant_reply}"
            )
    elif intake["phase"] == "more_subjects":
        add_subject = _yes_or_no(answer, "answer")
        if add_subject:
            intake.update(
                {
                    "phase": "subject",
                    "subject_index": len(marks),
                    "mark_field_index": 0,
                    "current_mark": {},
                }
            )
            assistant_reply, intake["input"] = _intake_question(
                state | {"details": details, "marks": marks}, intake
            )
        else:
            intake["phase"] = "rank"
            assistant_reply, intake["input"] = _intake_question(
                state | {"details": details, "marks": marks}, intake
            )
    else:
        rank_requested = _yes_or_no(answer, "answer")
        clean_details, clean_marks = validate_student_marks(
            {"details": details, "marks": marks}
        )
        state.update(
            {
                "details": clean_details,
                "marks": clean_marks,
                "rank_requested": rank_requested,
                "intake": intake,
            }
        )
        _append_message(session, "user", answer)
        session.state = state
        return _assistant_reply(
            session,
            AssistantSession.Step.CONFIRM_MARKS,
            (
                f"Thanks, {clean_details['name']}. I saved the details and marks for "
                f"{len(clean_marks)} subject(s). Please review them below before we "
                "continue."
            ),
        )

    state.update({"details": details, "marks": marks, "intake": intake})
    _append_message(session, "user", answer)
    session.state = state
    return _assistant_reply(session, AssistantSession.Step.MARKS, assistant_reply)


def validate_grade_boundaries(boundaries):
    if not isinstance(boundaries, list) or not boundaries:
        raise ValidationError({"grade_boundaries": "Provide grade boundaries."})

    normalized = []
    for index, boundary in enumerate(boundaries):
        if not isinstance(boundary, dict) or not str(boundary.get("grade", "")).strip():
            raise ValidationError(
                {"grade_boundaries": f"Boundary {index + 1} needs a grade label."}
            )
        minimum = _decimal(
            boundary.get("min_percentage"), f"grade_boundaries.{index}.min_percentage"
        )
        maximum = _decimal(
            boundary.get("max_percentage"), f"grade_boundaries.{index}.max_percentage"
        )
        if minimum.as_tuple().exponent < -2 or maximum.as_tuple().exponent < -2:
            raise ValidationError(
                {"grade_boundaries": "Grade boundaries can have at most two decimal places."}
            )
        if minimum < 0 or maximum > 100 or minimum > maximum:
            raise ValidationError(
                {
                    "grade_boundaries": (
                        f"Boundary {index + 1} must be within 0-100 and "
                        "its minimum cannot exceed its maximum."
                    )
                }
            )
        grade = str(boundary["grade"]).strip()
        if len(grade) > 10:
            raise ValidationError(
                {"grade_boundaries": f"Grade {index + 1} must be 10 characters or fewer."}
            )
        normalized.append(
            {
                "grade": grade,
                "min_percentage": str(minimum),
                "max_percentage": str(maximum),
            }
        )

    ordered = sorted(normalized, key=lambda item: Decimal(item["min_percentage"]))
    if Decimal(ordered[0]["min_percentage"]) != 0 or Decimal(
        ordered[-1]["max_percentage"]
    ) != 100:
        raise ValidationError(
            {"grade_boundaries": "Grade boundaries must cover the full 0-100 range."}
        )
    for previous, current in zip(ordered, ordered[1:]):
        if Decimal(current["min_percentage"]) != Decimal(
            previous["max_percentage"]
        ) + Decimal("0.01"):
            raise ValidationError(
                {
                    "grade_boundaries": (
                        "Grade boundaries must be continuous and must not overlap."
                    )
                }
            )
    return sorted(
        normalized,
        key=lambda item: Decimal(item["min_percentage"]),
        reverse=True,
    )


def validate_policy_data(data):
    boundaries = validate_grade_boundaries(data.get("grade_boundaries"))
    minimum_pass = _decimal(
        data.get("minimum_passing_percentage", 40), "minimum_passing_percentage"
    )
    subject_pass = _decimal(
        data.get("subject_passing_percentage", 33), "subject_passing_percentage"
    )
    if minimum_pass.as_tuple().exponent < -2 or subject_pass.as_tuple().exponent < -2:
        raise ValidationError(
            "Passing percentages can have at most two decimal places."
        )
    if not 0 <= minimum_pass <= 100 or not 0 <= subject_pass <= 100:
        raise ValidationError(
            "Passing percentages must be between 0 and 100."
        )
    weights = data.get("weighted_subjects", {})
    if not isinstance(weights, dict):
        raise ValidationError({"weighted_subjects": "Provide subject weights as an object."})
    normalized_weights = {}
    for subject, weight in weights.items():
        value = _decimal(weight, f"weighted_subjects.{subject}")
        if value <= 0:
            raise ValidationError(
                {"weighted_subjects": "Subject weights must be greater than zero."}
            )
        normalized_weights[str(subject).strip().casefold()] = str(value)
    name = str(data.get("name", "School grading policy")).strip()
    if not name or len(name) > 120:
        raise ValidationError(
            {"name": "Policy name is required and must be 120 characters or fewer."}
        )
    require_subject_pass = data.get("require_subject_pass", False)
    if not isinstance(require_subject_pass, bool):
        raise ValidationError(
            {"require_subject_pass": "Specify whether every subject must be passed."}
        )
    return {
        "name": name,
        "grade_boundaries": boundaries,
        "minimum_passing_percentage": str(minimum_pass),
        "require_subject_pass": require_subject_pass,
        "subject_passing_percentage": str(subject_pass),
        "weighted_subjects": normalized_weights,
    }


def _grade_for_percentage(percentage, boundaries):
    for boundary in boundaries:
        if Decimal(boundary["min_percentage"]) <= percentage <= Decimal(
            boundary["max_percentage"]
        ):
            return boundary["grade"]
    raise ValidationError("The approved grading policy does not cover this percentage.")


def _validate_comparisons(comparisons, target_marks, policy):
    normalized = []
    target_subjects = {
        mark["subject"].casefold(): Decimal(mark["maximum_marks"])
        for mark in target_marks
    }
    seen_rolls = set()
    for index, comparison in enumerate(comparisons or []):
        if index >= 500:
            raise ValidationError({"comparisons": "Add no more than 500 comparison records."})
        if not isinstance(comparison, dict):
            raise ValidationError(
                {"comparisons": f"Comparison record {index + 1} is invalid."}
            )
        roll = str(comparison.get("roll_number", "")).strip()
        if not roll or roll.casefold() in seen_rolls:
            raise ValidationError(
                {"comparisons": f"Comparison record {index + 1} needs a unique roll number."}
            )
        seen_rolls.add(roll.casefold())
        peer_marks = comparison.get("marks")
        if not isinstance(peer_marks, list):
            raise ValidationError(
                {"comparisons": f"Comparison record {index + 1} needs subject marks."}
            )
        peer_by_subject = {}
        for peer_mark in peer_marks:
            if not isinstance(peer_mark, dict):
                raise ValidationError({"comparisons": "Comparison subject entry is invalid."})
            subject = str(peer_mark.get("subject", "")).strip()
            key = subject.casefold()
            if not key or key in peer_by_subject:
                raise ValidationError(
                    {"comparisons": f"Comparison record {index + 1} has duplicate subjects."}
                )
            obtained = _decimal(peer_mark.get("marks"), "comparisons.marks")
            maximum = _decimal(
                peer_mark.get("maximum_marks"), "comparisons.maximum_marks"
            )
            if (
                obtained.as_tuple().exponent < -2
                or maximum.as_tuple().exponent < -2
            ):
                raise ValidationError(
                    {"comparisons": f"{subject}: marks can have at most two decimal places."}
                )
            if maximum <= 0 or obtained < 0 or obtained > maximum:
                raise ValidationError(
                    {"comparisons": f"{subject}: comparison marks are outside valid limits."}
                )
            if key not in target_subjects or target_subjects[key] != maximum:
                raise ValidationError(
                    {
                        "comparisons": (
                            "Comparison marks must use the same subjects and maximum "
                            "marks as the student being evaluated."
                        )
                    }
                )
            peer_by_subject[key] = (subject, obtained, maximum)
        if set(peer_by_subject) != set(target_subjects):
            raise ValidationError(
                {
                    "comparisons": (
                        f"Comparison record {index + 1} must include every report-card subject."
                    )
                }
            )
        weighted_sum = Decimal("0")
        total_weight = Decimal("0")
        total_obtained = Decimal("0")
        total_maximum = Decimal("0")
        for subject_key, (_, obtained, maximum) in peer_by_subject.items():
            weight = Decimal(policy["weighted_subjects"].get(subject_key, "1"))
            weighted_sum += obtained * Decimal("100") / maximum * weight
            total_weight += weight
            total_obtained += obtained
            total_maximum += maximum
        normalized.append(
            {
                "roll_number": roll,
                "marks": [
                    {
                        "subject": subject,
                        "marks": str(obtained),
                        "maximum_marks": str(maximum),
                    }
                    for subject, obtained, maximum in peer_by_subject.values()
                ],
                "total_marks": str(total_obtained.quantize(Decimal("0.01"))),
                "total_maximum_marks": str(total_maximum.quantize(Decimal("0.01"))),
                "percentage": str((weighted_sum / total_weight).quantize(Decimal("0.01"))),
            }
        )
    return normalized


def calculate_report(details, marks, policy, comparisons=None, rank_requested=True):
    clean_details, clean_marks = validate_student_marks(
        {"details": details, "marks": marks}
    )
    clean_policy = validate_policy_data(policy)
    comparisons = _validate_comparisons(comparisons, clean_marks, clean_policy)
    unknown_weights = set(clean_policy["weighted_subjects"]) - {
        mark["subject"].casefold() for mark in clean_marks
    }
    if unknown_weights:
        raise ValidationError(
            {
                "weighted_subjects": (
                    "Weights refer to subjects not present in this report: "
                    + ", ".join(sorted(unknown_weights))
                )
            }
        )
    results = []
    total_obtained = Decimal("0")
    total_maximum = Decimal("0")
    weighted_sum = Decimal("0")
    total_weight = Decimal("0")

    for mark in clean_marks:
        obtained = Decimal(mark["marks"])
        maximum = Decimal(mark["maximum_marks"])
        percentage = obtained * Decimal("100") / maximum
        grade = _grade_for_percentage(percentage, clean_policy["grade_boundaries"])
        weight = Decimal(
            clean_policy["weighted_subjects"].get(mark["subject"].casefold(), "1")
        )
        total_obtained += obtained
        total_maximum += maximum
        weighted_sum += percentage * weight
        total_weight += weight
        results.append(
            {
                **mark,
                "percentage": str(percentage.quantize(Decimal("0.01"))),
                "grade": grade,
                "passed": percentage
                >= Decimal(clean_policy["subject_passing_percentage"]),
            }
        )

    percentage = (weighted_sum / total_weight).quantize(Decimal("0.01"))
    overall_grade = _grade_for_percentage(percentage, clean_policy["grade_boundaries"])
    passed = percentage >= Decimal(clean_policy["minimum_passing_percentage"])
    if clean_policy["require_subject_pass"]:
        passed = passed and all(subject["passed"] for subject in results)

    rank = None
    percentile = None
    valid_comparisons = []
    for item in comparisons:
        valid_comparisons.append(Decimal(item["percentage"]))
    if rank_requested and valid_comparisons:
        rank = 1 + sum(score > percentage for score in valid_comparisons)
        population = len(valid_comparisons) + 1
        below = sum(score < percentage for score in valid_comparisons)
        tied = sum(score == percentage for score in valid_comparisons) + 1
        percentile = (
            (Decimal(below) + Decimal(tied) / 2)
            * Decimal("100")
            / Decimal(population)
        )

    return {
        "details": clean_details,
        "subject_results": results,
        "total_marks": str(total_obtained.quantize(Decimal("0.01"))),
        "total_maximum_marks": str(total_maximum.quantize(Decimal("0.01"))),
        "percentage": str(percentage.quantize(Decimal("0.01"))),
        "overall_grade": overall_grade,
        "passed": passed,
        "rank": rank,
        "percentile": (
            str(percentile.quantize(Decimal("0.01"))) if percentile is not None else None
        ),
        "rank_unavailable_reason": (
            "Rank and percentile are unavailable until marks for other students "
            "in this class, examination, and academic year are provided."
            if rank_requested and not valid_comparisons
            else ""
        ),
        "policy": clean_policy,
    }


def _assistant_reply(session, step, content):
    session.step = step
    _append_message(session, "assistant", content)
    session.save(
        update_fields=["step", "messages", "state", "report_card", "updated_at"]
    )
    return session


def _record_teacher_message(session, action, data):
    if action == "ask_question":
        content = str(data.get("question", "")).strip()
        if content:
            _append_message(session, "user", content[:1000])
        return
    if action == "submit_marks":
        details = data.get("details", {})
        marks = data.get("marks", [])
        content = (
            f"Student: {details.get('name', '')}; class: {details.get('class_name', '')}"
            f"{('-' + details.get('section', '')) if details.get('section') else ''}; "
            f"roll number: {details.get('roll_number', '')}; academic year: "
            f"{details.get('academic_year', '')}; examination: "
            f"{details.get('examination_name', '')}. Marks: "
            + "; ".join(
                f"{item.get('subject', '')} "
                f"{item.get('marks', '')}/{item.get('maximum_marks', '')}"
                for item in marks
                if isinstance(item, dict)
            )
        )
    elif action == "propose_policy":
        content = str(data.get("requirements", "")).strip()
    elif action == "clarify_requirements":
        content = str(data.get("requirements", "")).strip()
    elif action == "submit_custom_policy":
        content = "I entered a custom grading policy for review."
    else:
        content = {
            "edit_marks": "I want to edit the student details or marks.",
            "confirm_marks": "The student details and marks are correct.",
            "choose_policy": (
                "I chose the "
                f"{data.get('mode', 'unknown')} grading policy option."
            ),
            "select_policy": f"I selected approved grading policy {data.get('policy_id', '')}.",
            "edit_policy": "I updated the grading policy.",
            "approve_policy": "I approve this grading policy.",
            "add_comparisons": "I submitted complete class comparison marks.",
            "use_saved_comparisons": "Use saved class comparison marks.",
            "skip_comparisons": "Continue without class comparison marks.",
            "back_to_marks": "Return to edit student details and marks.",
            "issue_report": "Confirm and issue the report card.",
        }.get(action, "")
    if content:
        _append_message(session, "user", content[:5000])


def _make_policy(data, details, ai_generated=False):
    clean = validate_policy_data(data)
    return GradingPolicy.objects.create(
        name=clean["name"],
        class_name=details.get("class_name", ""),
        academic_year=details.get("academic_year", ""),
        grade_boundaries=clean["grade_boundaries"],
        minimum_passing_percentage=clean["minimum_passing_percentage"],
        require_subject_pass=clean["require_subject_pass"],
        subject_passing_percentage=clean["subject_passing_percentage"],
        weighted_subjects=clean["weighted_subjects"],
        ai_generated_proposal=ai_generated,
        approved=False,
    )


def _policy_data(policy):
    return {
        "name": policy.name,
        "grade_boundaries": policy.grade_boundaries,
        "minimum_passing_percentage": str(policy.minimum_passing_percentage),
        "require_subject_pass": policy.require_subject_pass,
        "subject_passing_percentage": str(policy.subject_passing_percentage),
        "weighted_subjects": policy.weighted_subjects,
        "ai_generated_proposal": policy.ai_generated_proposal,
    }


def _saved_class_comparisons(details):
    examination = Examination.objects.filter(
        name=details["examination_name"],
        class_name=details["class_name"],
        section=details.get("section", ""),
        academic_year=details["academic_year"],
    ).first()
    if examination is None or not examination.comparison_complete:
        return []
    own_roll = details["roll_number"].casefold()
    return [
        item
        for item in examination.comparison_data
        if isinstance(item, dict)
        and item.get("roll_number", "").casefold() != own_roll
    ]


def _propose_policy(requirements):
    from .ai_insights import propose_grading_policy

    return propose_grading_policy(requirements)


def advance_assistant(session, action, data=None):
    data = data or {}
    if not isinstance(data, dict):
        raise ValidationError({"data": "Provide assistant step data as an object."})
    ensure_assistant_intake(session)
    state = dict(session.state)
    step = session.step
    if action == "intake_answer":
        if step != AssistantSession.Step.MARKS:
            raise ValidationError("Student details have already been collected.")
        return _advance_intake_answer(session, state, data)
    _record_teacher_message(session, action, data)

    if action == "ask_question":
        if step == AssistantSession.Step.ISSUED:
            raise ValidationError("Questions are not available after the report is issued.")
        from .ai_insights import answer_workflow_question

        question = str(data.get("question", "")).strip()
        answer = answer_workflow_question(
            question,
            step,
            {
                "conversation": session.messages[-12:],
                "details": state.get("details", {}),
                "marks": state.get("marks", []),
            },
        )
        session.state = state
        return _assistant_reply(session, step, answer)

    if action == "back_to_marks" and step not in {
        AssistantSession.Step.MARKS,
        AssistantSession.Step.ISSUED,
    }:
        if step == AssistantSession.Step.PREVIEW and "teacher_remarks" in data:
            state["teacher_remarks"] = str(data["teacher_remarks"]).strip()[:4000]
        state["intake"] = _new_intake_state()
        state["marks"] = []
        session.state = state
        return _assistant_reply(
            session,
            AssistantSession.Step.MARKS,
            _first_intake_question(),
        )

    if step == AssistantSession.Step.MARKS:
        if action != "submit_marks":
            raise ValidationError("Submit student details and marks to continue.")
        details, marks = validate_student_marks(data)
        rank_requested = data.get("rank_requested", True)
        if not isinstance(rank_requested, bool):
            raise ValidationError(
                {"rank_requested": "Choose whether class rank should be included."}
            )
        state.update(
            {
                "details": details,
                "marks": marks,
                "rank_requested": rank_requested,
            }
        )
        session.state = state
        _append_message(
            session,
            "assistant",
            (
                f"I have collected marks for "
                f"{SUBJECT_COUNT_WORDS.get(len(marks), len(marks))} subjects. Would you like "
                "to add or edit any marks before proceeding?"
            ),
        )
        return _assistant_reply(session, AssistantSession.Step.CONFIRM_MARKS, session.messages[-1]["content"])

    if step == AssistantSession.Step.CONFIRM_MARKS:
        if action == "edit_marks":
            state["intake"] = _new_intake_state()
            state["marks"] = []
            session.state = state
            return _assistant_reply(
                session, AssistantSession.Step.MARKS, _first_intake_question()
            )
        if action != "confirm_marks":
            raise ValidationError("Confirm the marks or edit them before proceeding.")
        session.state = state
        return _assistant_reply(
            session,
            AssistantSession.Step.POLICY_CHOICE,
            POLICY_QUESTION,
        )

    if step == AssistantSession.Step.POLICY_CHOICE:
        if action == "back_to_marks":
            state["intake"] = _new_intake_state()
            state["marks"] = []
            session.state = state
            return _assistant_reply(
                session,
                AssistantSession.Step.MARKS,
                _first_intake_question(),
            )
        mode = data.get("mode")
        if action != "choose_policy" or mode not in {"existing", "proposal", "custom"}:
            raise ValidationError("Choose an existing, proposed, or custom grading policy.")
        if mode == "existing":
            session.state = state
            return _assistant_reply(
                session,
                AssistantSession.Step.EXISTING_POLICY,
                "Select an approved grading policy for this class and academic year.",
            )
        if mode == "proposal":
            session.state = state
            return _assistant_reply(
                session,
                AssistantSession.Step.REQUIREMENTS,
                "Describe the institution's requirements for a proposed grading policy.",
            )
        session.state = state
        return _assistant_reply(
            session,
            AssistantSession.Step.CUSTOM_POLICY,
            "Enter grade boundaries, passing requirements, and optional subject weights.",
        )

    if step == AssistantSession.Step.EXISTING_POLICY:
        if action != "select_policy":
            raise ValidationError("Select an approved grading policy.")
        try:
            policy = GradingPolicy.objects.get(pk=data.get("policy_id"), approved=True)
        except (GradingPolicy.DoesNotExist, TypeError, ValueError):
            raise ValidationError({"policy_id": "Select an approved grading policy."}) from None
        details = state["details"]
        if policy.class_name and policy.class_name != details["class_name"]:
            raise ValidationError({"policy_id": "This policy is for a different class."})
        if policy.academic_year and policy.academic_year != details["academic_year"]:
            raise ValidationError({"policy_id": "This policy is for a different academic year."})
        state.update({"policy_id": policy.pk, "policy": _policy_data(policy)})
        if not state.get("comparison_complete"):
            state["comparisons"] = _saved_class_comparisons(details)
            state["comparison_complete"] = bool(state["comparisons"])
        session.state = state
        return _assistant_reply(
            session,
            AssistantSession.Step.COMPARISON,
            (
                f"Grading policy selected. Found {len(state['comparisons'])} saved "
                "class comparison record(s). Add or review comparison marks, or "
                "continue without class ranking."
            ),
        )

    if step == AssistantSession.Step.REQUIREMENTS:
        requirements = str(data.get("requirements", "")).strip()
        if action == "clarify_requirements":
            if not requirements:
                raise ValidationError(
                    {"requirements": "Describe the school's grading requirements first."}
                )
            if len(requirements) > 4000:
                raise ValidationError(
                    {"requirements": "Requirements must be 4,000 characters or fewer."}
                )
            from .ai_insights import clarify_grading_requirements

            clarification = clarify_grading_requirements(requirements)
            state["policy_requirements"] = requirements
            session.state = state
            return _assistant_reply(
                session,
                AssistantSession.Step.REQUIREMENTS,
                clarification,
            )
        if action != "propose_policy" or not requirements:
            raise ValidationError({"requirements": "Describe the school's grading requirements."})
        if len(requirements) > 4000:
            raise ValidationError({"requirements": "Requirements must be 4,000 characters or fewer."})
        proposal = _propose_policy(requirements)
        clean_proposal = validate_policy_data(proposal)
        policy = _make_policy(clean_proposal, state["details"], ai_generated=True)
        state.update(
            {
                "policy_id": policy.pk,
                "policy": _policy_data(policy),
                "policy_requirements": requirements,
            }
        )
        session.state = state
        return _assistant_reply(
            session,
            AssistantSession.Step.APPROVE_POLICY,
            (
                "AI-generated proposal — requires teacher approval. Review the grade "
                "boundaries and passing rules before approving or editing this policy."
            ),
        )

    if step == AssistantSession.Step.CUSTOM_POLICY:
        if action != "submit_custom_policy":
            raise ValidationError("Submit a valid custom grading policy.")
        policy = _make_policy(data, state["details"])
        state.update({"policy_id": policy.pk, "policy": _policy_data(policy)})
        session.state = state
        return _assistant_reply(
            session,
            AssistantSession.Step.APPROVE_POLICY,
            "Review your custom grading policy and approve it to continue.",
        )

    if step == AssistantSession.Step.APPROVE_POLICY:
        if action == "edit_policy":
            if not state.get("policy_id"):
                raise ValidationError("There is no policy to edit.")
            policy = GradingPolicy.objects.get(pk=state["policy_id"], approved=False)
            clean = validate_policy_data(data)
            for field, value in clean.items():
                setattr(policy, field, value)
            policy.save()
            state["policy"] = _policy_data(policy)
            session.state = state
            return _assistant_reply(
                session,
                AssistantSession.Step.APPROVE_POLICY,
                "Policy updated. Review it and approve it to continue.",
            )
        if action != "approve_policy":
            raise ValidationError("Approve or edit the grading policy before continuing.")
        policy = GradingPolicy.objects.get(pk=state["policy_id"])
        if not policy.approved:
            policy.approved = True
            policy.save(update_fields=["approved"])
        state["policy"] = _policy_data(policy)
        if not state.get("comparison_complete"):
            saved_comparisons = _saved_class_comparisons(state["details"])
            state["comparisons"] = saved_comparisons
            state["comparison_complete"] = bool(saved_comparisons)
        else:
            saved_comparisons = state["comparisons"]
        session.state = state
        return _assistant_reply(
            session,
            AssistantSession.Step.COMPARISON,
            (
                f"Grading policy approved. Found {len(saved_comparisons)} saved "
                "class comparison record(s). Add or review comparison marks, or "
                "continue without class ranking."
            ),
        )

    if step == AssistantSession.Step.COMPARISON:
        if action == "add_comparisons":
            comparisons = data.get("comparisons", [])
            if not isinstance(comparisons, list):
                raise ValidationError({"comparisons": "Provide comparison marks as a list."})
            if len(comparisons) > 500:
                raise ValidationError({"comparisons": "Add no more than 500 comparison records at once."})
            if not comparisons:
                raise ValidationError(
                    {"comparisons": "Enter comparison marks or continue without a class rank."}
                )
            if data.get("comparison_complete") is not True:
                raise ValidationError(
                    {
                        "comparison_complete": (
                            "Confirm that comparison data includes all students in "
                            "the same class and examination before calculating rank."
                        )
                    }
                )
            normalized = []
            seen_rolls = {state["details"]["roll_number"].casefold()}
            for index, comparison in enumerate(comparisons):
                if not isinstance(comparison, dict):
                    raise ValidationError(
                        {"comparisons": f"Comparison record {index + 1} is invalid."}
                    )
                roll = str(comparison.get("roll_number", "")).strip()
                if not roll or len(roll) > 30 or roll.casefold() in seen_rolls:
                    raise ValidationError(
                        {"comparisons": f"Comparison record {index + 1} needs a unique roll number."}
                    )
                seen_rolls.add(roll.casefold())
                normalized.append(
                    {
                        "roll_number": roll,
                        "marks": comparison.get("marks", []),
                    }
                )
            state["comparisons"] = normalized
            state["comparison_complete"] = True
        elif action == "use_saved_comparisons":
            state["comparisons"] = state.get("comparisons", [])
            state["comparison_complete"] = bool(state["comparisons"])
        elif action == "skip_comparisons":
            state["comparisons"] = []
            state["comparison_complete"] = False
        else:
            raise ValidationError("Add comparison marks or continue without a class rank.")
        from .ai_insights import generate_academic_feedback

        calculation = calculate_report(
            state["details"],
            state["marks"],
            state["policy"],
            state.get("comparisons", [])
            if state.get("comparison_complete", False)
            else [],
            state.get("rank_requested", True),
        )
        state["teacher_feedback"] = generate_academic_feedback(
            calculation["subject_results"]
        )
        state["calculation"] = calculation
        session.state = state
        return _assistant_reply(
            session,
            AssistantSession.Step.PREVIEW,
            "Review the calculated report card. Confirm it to issue the final report card, or go back to edit marks.",
        )

    if step == AssistantSession.Step.PREVIEW:
        if action == "back_to_marks":
            state["teacher_remarks"] = str(
                data.get("teacher_remarks", state.get("teacher_remarks", ""))
            ).strip()[:4000]
            state["teacher_remarks"] = str(
                data.get("teacher_remarks", state.get("teacher_remarks", ""))
            ).strip()[:4000]
            session.state = state
            return _assistant_reply(
                session,
                AssistantSession.Step.MARKS,
                "Edit the student details or marks below. Your grading policy is saved.",
            )
        if action == "issue_report":
            return _issue_report(session, state, data)
        raise ValidationError("Confirm the preview or go back to edit the marks.")

    if step == AssistantSession.Step.ISSUED:
        raise ValidationError("This report card has already been issued.")
    raise ValidationError("This assistant session is in an unknown state.")


@transaction.atomic
def _issue_report(session, state, data):
    calculation = calculate_report(
        state["details"],
        state["marks"],
        state["policy"],
        state.get("comparisons", [])
        if state.get("comparison_complete", False)
        else [],
        state.get("rank_requested", True),
    )
    feedback = state.get("teacher_feedback")
    if not feedback:
        raise ValidationError("Generate and review academic feedback before issuing.")
    teacher_remarks = str(data.get("teacher_remarks", "")).strip()
    if len(teacher_remarks) > 4000:
        raise ValidationError(
            {"teacher_remarks": "Teacher remarks must be 4,000 characters or fewer."}
        )
    policy = GradingPolicy.objects.get(pk=state["policy_id"], approved=True)
    report_card = _save_report_card(
        calculation,
        policy,
        state.get("comparisons", []),
        state.get("comparison_complete", False),
        teacher_remarks,
        feedback,
    )
    state["calculation"] = calculation
    state["report_card_id"] = report_card.pk
    session.report_card = report_card
    session.state = state
    return _assistant_reply(
        session,
        AssistantSession.Step.ISSUED,
        "The report card has been issued. Download the PDF using the report link.",
    )


def calculate_manual_report(data):
    if not isinstance(data, dict):
        raise ValidationError({"data": "Provide report details as an object."})
    policy = data.get("policy")
    if not isinstance(policy, dict):
        raise ValidationError({"policy": "Provide the grading policy as an object."})
    details, marks = validate_student_marks(
        {"details": data.get("details"), "marks": data.get("marks")}
    )
    rank_requested = data.get("rank_requested", True)
    if not isinstance(rank_requested, bool):
        raise ValidationError(
            {"rank_requested": "Choose whether class rank should be included."}
        )
    comparisons = data.get("comparisons")
    if comparisons is None:
        comparisons = _saved_class_comparisons(details) if rank_requested else []
    elif comparisons and data.get("comparison_complete") is not True:
        raise ValidationError(
            {"comparison_complete": "Confirm the comparison data is complete."}
        )
    if not isinstance(comparisons, list):
        raise ValidationError({"comparisons": "Provide comparison records as a list."})

    calculation = calculate_report(
        details,
        marks,
        policy,
        comparisons,
        rank_requested,
    )
    teacher_remarks = str(data.get("teacher_remarks", "")).strip()
    if len(teacher_remarks) > 4000:
        raise ValidationError(
            {"teacher_remarks": "Teacher remarks must be 4,000 characters or fewer."}
        )
    return calculation, comparisons, teacher_remarks


@transaction.atomic
def issue_manual_report_card(data):
    calculation, comparisons, teacher_remarks = calculate_manual_report(data)
    details = calculation["details"]
    policy_data = calculation["policy"]
    policy, _ = GradingPolicy.objects.get_or_create(
        name=policy_data["name"],
        class_name=details["class_name"],
        academic_year=details["academic_year"],
        grade_boundaries=policy_data["grade_boundaries"],
        minimum_passing_percentage=policy_data["minimum_passing_percentage"],
        require_subject_pass=policy_data["require_subject_pass"],
        subject_passing_percentage=policy_data["subject_passing_percentage"],
        weighted_subjects=policy_data["weighted_subjects"],
        approved=True,
        ai_generated_proposal=False,
    )
    report_card = _save_report_card(
        calculation,
        policy,
        comparisons,
        bool(comparisons),
        teacher_remarks,
        "",
    )
    return report_card


@transaction.atomic
def _save_report_card(
    calculation,
    policy,
    comparisons,
    comparison_complete,
    teacher_remarks,
    feedback,
):
    details = calculation["details"]
    examination, _ = Examination.objects.get_or_create(
        name=details["examination_name"],
        class_name=details["class_name"],
        section=details.get("section", ""),
        academic_year=details["academic_year"],
    )
    if comparison_complete and comparisons:
        examination.comparison_data = [
            *comparisons,
            {
                "roll_number": details["roll_number"],
                "marks": calculation["subject_results"],
            },
        ]
        examination.comparison_complete = True
        examination.save(update_fields=["comparison_data", "comparison_complete"])

    student, _ = Student.objects.get_or_create(
        roll_number=details["roll_number"],
        class_name=details["class_name"],
        section=details.get("section", ""),
        academic_year=details["academic_year"],
        defaults={
            "name": details["name"],
        },
    )
    student.name = details["name"]
    student.class_name = details["class_name"]
    student.section = details.get("section", "")
    student.academic_year = details["academic_year"]
    student.save(
        update_fields=["name", "class_name", "section", "academic_year"]
    )

    for subject_result in calculation["subject_results"]:
        subject, _ = Subject.objects.get_or_create(
            name=subject_result["subject"],
            defaults={"maximum_marks": subject_result["maximum_marks"]},
        )
        mark = SubjectMark.objects.filter(
            student=student, examination=examination, subject=subject
        ).first()
        if mark:
            mark.marks = subject_result["marks"]
            mark.maximum_marks = subject_result["maximum_marks"]
            try:
                mark.full_clean()
            except DjangoValidationError as exc:
                raise ValidationError(exc.message_dict) from exc
            mark.save(update_fields=["marks", "maximum_marks"])
        else:
            mark = SubjectMark(
                student=student,
                examination=examination,
                subject=subject,
                marks=subject_result["marks"],
                maximum_marks=subject_result["maximum_marks"],
            )
            try:
                mark.full_clean()
            except DjangoValidationError as exc:
                raise ValidationError(exc.message_dict) from exc
            mark.save()

    if comparison_complete:
        for comparison in comparisons:
            peer, _ = Student.objects.get_or_create(
                roll_number=comparison["roll_number"],
                class_name=details["class_name"],
                section=details.get("section", ""),
                academic_year=details["academic_year"],
                defaults={
                    "name": comparison.get(
                        "name", f"Student {comparison['roll_number']}"
                    ),
                },
            )
            for peer_result in comparison["marks"]:
                subject, _ = Subject.objects.get_or_create(
                    name=peer_result["subject"],
                    defaults={"maximum_marks": peer_result["maximum_marks"]},
                )
                SubjectMark.objects.update_or_create(
                    student=peer,
                    examination=examination,
                    subject=subject,
                    defaults={
                        "marks": peer_result["marks"],
                        "maximum_marks": peer_result["maximum_marks"],
                    },
                )

    generated_at = timezone.now()
    report_card, _ = ReportCard.objects.update_or_create(
        student=student,
        examination=examination,
        defaults={
            "grading_policy": policy,
            "total_marks": calculation["total_marks"],
            "total_maximum_marks": calculation["total_maximum_marks"],
            "percentage": calculation["percentage"],
            "overall_grade": calculation["overall_grade"],
            "passed": calculation["passed"],
            "rank": calculation["rank"],
            "percentile": calculation["percentile"],
            "rank_unavailable_reason": calculation["rank_unavailable_reason"],
            "subject_results": calculation["subject_results"],
            "teacher_summary": feedback,
            "teacher_remarks": teacher_remarks,
            "summary_generated_at": generated_at if feedback else None,
            "generated_at": generated_at,
            "issued_at": generated_at,
        },
    )
    return report_card
