import json
from io import BytesIO
from unittest.mock import patch

from django.test import TestCase
from django.test import override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient
from django.utils import timezone

from .ai_insights import (
    AIServiceUnavailable,
    FEEDBACK_CACHE_KEY,
    generate_teacher_summary,
    save_teacher_summary,
)
from .assistant_workflow import (
    POLICY_QUESTION,
    WELCOME_MESSAGE,
    advance_assistant,
    calculate_report,
    create_assistant_session,
    ensure_assistant_intake,
)
from .models import (
    Department,
    Examination,
    GradingPolicy,
    ReportCard,
    Student,
    Subject,
    SubjectMark,
)
from .report_pdf import build_report_card_pdf
from .services import generate_report_cards


FEEDBACK_TEMPLATES = {
    "needs_support": "Use short, guided practice and check understanding regularly.",
    "developing": "Reinforce progress with targeted practice and clear next steps.",
    "strong": "Extend learning with more challenging tasks and independent projects.",
}


class ReportCardGenerationTests(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Mathematics")
        self.first_student = Student.objects.create(
            roll_number="S001", name="Asha"
        )
        self.second_student = Student.objects.create(
            roll_number="S002", name="Ben"
        )
        self.third_student = Student.objects.create(
            roll_number="S003", name="Chris"
        )

    def test_generates_totals_and_competition_ranks(self):
        SubjectMark.objects.create(
            student=self.first_student, subject=self.subject, marks=90
        )
        SubjectMark.objects.create(
            student=self.second_student, subject=self.subject, marks=90
        )
        SubjectMark.objects.create(
            student=self.third_student, subject=self.subject, marks=70
        )

        self.assertEqual(generate_report_cards(), 3)

        self.assertEqual(
            list(
                ReportCard.objects.order_by("student__roll_number").values_list(
                    "total_marks", "rank"
                )
            ),
            [(90, 1), (90, 1), (70, 3)],
        )

    def test_students_without_marks_receive_zero_and_rank_after_scored_students(self):
        SubjectMark.objects.create(
            student=self.first_student, subject=self.subject, marks=80
        )

        generate_report_cards()

        unscored_card = ReportCard.objects.get(student=self.second_student)
        self.assertEqual(unscored_card.total_marks, 0)
        self.assertEqual(unscored_card.rank, 2)

    def test_legacy_generation_does_not_mix_examination_specific_marks(self):
        examination = Examination.objects.create(
            name="Final",
            class_name="10",
            academic_year="2026-2027",
        )
        SubjectMark.objects.create(
            student=self.first_student,
            subject=self.subject,
            examination=examination,
            marks=100,
            maximum_marks=100,
        )
        SubjectMark.objects.create(
            student=self.second_student,
            subject=self.subject,
            marks=60,
        )

        generate_report_cards()

        self.assertFalse(
            ReportCard.objects.filter(
                student=self.first_student, examination__isnull=True
            ).exists()
        )
        self.assertEqual(
            ReportCard.objects.get(
                student=self.second_student, examination__isnull=True
            ).total_marks,
            60,
        )

    def test_regeneration_updates_changed_marks_and_is_idempotent(self):
        mark = SubjectMark.objects.create(
            student=self.first_student, subject=self.subject, marks=80
        )
        generate_report_cards()
        original_generated_at = ReportCard.objects.get(
            student=self.first_student, examination__isnull=True
        ).generated_at
        mark.marks = 95
        mark.save()

        self.assertEqual(generate_report_cards(), 3)
        report_card = ReportCard.objects.get(student=self.first_student)
        self.assertEqual(report_card.total_marks, 95)
        self.assertEqual(report_card.rank, 1)
        self.assertGreaterEqual(report_card.generated_at, original_generated_at)

        self.assertEqual(generate_report_cards(), 3)
        self.assertEqual(ReportCard.objects.count(), 3)

    def test_report_card_page_shows_stored_data_and_marks(self):
        department = Department.objects.create(name="Science")
        self.first_student.department = department
        self.first_student.save()
        SubjectMark.objects.create(
            student=self.first_student, subject=self.subject, marks=88
        )
        generate_report_cards()
        user = get_user_model().objects.create_user(
            username="report-viewer",
            password="report-viewer-password",
            is_staff=True,
        )
        self.client.force_login(user)

        response = self.client.get(
            f"/students/{self.first_student.pk}/report-card/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Asha")
        self.assertContains(response, "88.00")
        self.assertContains(response, "Mathematics")
        self.assertContains(response, "Science")

    def test_report_card_page_returns_404_before_generation(self):
        user = get_user_model().objects.create_user(
            username="report-viewer",
            password="report-viewer-password",
            is_staff=True,
        )
        self.client.force_login(user)
        response = self.client.get(
            f"/students/{self.first_student.pk}/report-card/"
        )
        self.assertEqual(response.status_code, 404)

    def test_report_card_page_redirects_anonymous_users_to_teacher_login(self):
        response = self.client.get(
            f"/students/{self.first_student.pk}/report-card/"
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])


class ReportCardApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = Student.objects.create(roll_number="A100", name="Ari")
        self.subject = Subject.objects.create(name="Science", maximum_marks=100)
        SubjectMark.objects.create(
            student=self.student,
            subject=self.subject,
            marks=84,
        )

    def test_api_exposes_paginated_report_cards_and_summary(self):
        generate_report_cards()
        user = get_user_model().objects.create_user(
            username="report-api-viewer",
            password="report-api-viewer-password",
            is_staff=True,
        )
        self.client.force_authenticate(user=user)

        response = self.client.get("/api/report-cards/?page_size=1")
        summary = self.client.get("/api/report-cards/summary/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["student"]["name"], "Ari")
        self.assertEqual(response.data["results"][0]["subject_marks"][0]["subject_name"], "Science")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.data["total_reports"], 1)
        self.assertEqual(summary.data["top_student"]["roll_number"], "A100")

    def test_api_pagination_honors_requested_page_size(self):
        for index in range(2, 5):
            student = Student.objects.create(
                roll_number=f"A10{index}",
                name=f"Student {index}",
            )
            SubjectMark.objects.create(
                student=student,
                subject=self.subject,
                marks=50 + index,
            )
        generate_report_cards()
        user = get_user_model().objects.create_user(
            username="report-page-viewer",
            password="report-page-viewer-password",
            is_staff=True,
        )
        self.client.force_authenticate(user=user)

        response = self.client.get("/api/report-cards/?page_size=2")

        self.assertEqual(response.data["count"], 4)
        self.assertEqual(len(response.data["results"]), 2)

    def test_report_data_requires_teacher_authentication(self):
        self.assertEqual(self.client.get("/api/students/").status_code, 403)
        self.assertEqual(self.client.get("/api/report-cards/").status_code, 403)
        self.assertEqual(
            self.client.get("/api/report-cards/summary/").status_code,
            403,
        )

    def test_data_writes_require_authentication_and_generation_requires_staff(self):
        student_payload = {"roll_number": "A101", "name": "Bea"}
        self.assertEqual(
            self.client.post("/api/students/", student_payload).status_code,
            403,
        )

        user = get_user_model().objects.create_user(
            username="student-user",
            password="test-password",
        )
        self.client.force_authenticate(user=user)
        self.assertEqual(
            self.client.post("/api/students/", student_payload).status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/api/report-cards/generate/").status_code,
            403,
        )

        staff_user = get_user_model().objects.create_user(
            username="staff-user",
            password="test-password",
            is_staff=True,
        )
        self.client.force_authenticate(user=staff_user)
        generated = self.client.post("/api/report-cards/generate/")
        self.assertEqual(generated.status_code, 200)
        self.assertEqual(generated.data, {"updated": 1})

    @patch("student.api.save_teacher_summary")
    def test_teacher_summary_generation_is_staff_only(self, generate_summary):
        generate_summary.side_effect = lambda card: self._add_summary(card)
        generate_report_cards()
        card = ReportCard.objects.get(student=self.student)

        self.assertEqual(
            self.client.post(
                f"/api/report-cards/{card.pk}/teacher-summary/"
            ).status_code,
            403,
        )

        staff_user = get_user_model().objects.create_user(
            username="feedback-staff",
            password="test-password",
            is_staff=True,
        )
        self.client.force_authenticate(user=staff_user)
        response = self.client.post(
            f"/api/report-cards/{card.pk}/teacher-summary/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"], "Teacher note.")
        generate_summary.assert_called_once()

    @staticmethod
    def _add_summary(card):
        card.teacher_summary = "Teacher note."
        return card


class AIInsightTests(TestCase):
    def setUp(self):
        cache.delete(FEEDBACK_CACHE_KEY)
        self.student = Student.objects.create(roll_number="P001", name="Private Name")
        self.subject = Subject.objects.create(name="Private Subject", maximum_marks=100)
        SubjectMark.objects.create(
            student=self.student,
            subject=self.subject,
            marks=84,
        )
        self.report_card = ReportCard.objects.create(
            student=self.student,
            total_marks=84,
            rank=1,
            generated_at=timezone.now(),
        )

    @override_settings(
        GROQ_API_KEY="test-api-key",
        GROQ_MODEL="llama-3.3-70b-versatile",
    )
    @patch("student.ai_insights.urlopen")
    def test_sends_only_generic_feedback_prompt_and_uses_configured_model(
        self, mock_urlopen
    ):
        provider_result = {
            "choices": [
                {"message": {"content": json.dumps(FEEDBACK_TEMPLATES)}}
            ]
        }
        mock_urlopen.return_value = BytesIO(json.dumps(provider_result).encode())

        summary = generate_teacher_summary(self.report_card)

        request = mock_urlopen.call_args.args[0]
        request_body = json.loads(request.data)
        sent_prompt = json.dumps(request_body["messages"])
        self.assertEqual(request_body["model"], "llama-3.3-70b-versatile")
        self.assertNotIn("Private Name", sent_prompt)
        self.assertNotIn("Private Subject", sent_prompt)
        self.assertNotIn("84", sent_prompt)
        self.assertIn("84.0%", summary)
        self.assertIn(FEEDBACK_TEMPLATES["strong"], summary)

    @override_settings(GROQ_API_KEY="")
    def test_missing_api_key_returns_clear_service_error(self):
        with self.assertRaisesMessage(
            AIServiceUnavailable, "GROQ_API_KEY is not configured on the server."
        ):
            generate_teacher_summary(self.report_card)

    def test_summary_requires_at_least_one_scored_subject(self):
        SubjectMark.objects.filter(student=self.student).delete()

        with self.assertRaisesMessage(
            ValidationError,
            "Add subject marks with a non-zero maximum before generating feedback.",
        ):
            generate_teacher_summary(self.report_card)

    @patch(
        "student.ai_insights.generate_teacher_summary",
        return_value="Generated teacher note.",
    )
    def test_persists_teacher_summary(self, generate_summary):
        card = save_teacher_summary(self.report_card)

        self.assertEqual(card.teacher_summary, "Generated teacher note.")
        self.assertIsNotNone(card.summary_generated_at)
        generate_summary.assert_called_once_with(self.report_card)


class AssistantWorkflowTests(TestCase):
    def setUp(self):
        self.details = {
            "name": "Rahul Sharma",
            "roll_number": "12",
            "class_name": "10",
            "section": "A",
            "academic_year": "2026-2027",
            "examination_name": "Final Examination",
        }
        self.marks = [
            {"subject": "Mathematics", "marks": "85", "maximum_marks": "100"},
            {"subject": "Science", "marks": "92", "maximum_marks": "100"},
            {"subject": "English", "marks": "78", "maximum_marks": "100"},
            {"subject": "Computer Science", "marks": "95", "maximum_marks": "100"},
            {"subject": "Social Science", "marks": "80", "maximum_marks": "100"},
        ]
        self.policy = {
            "name": "School policy",
            "grade_boundaries": [
                {"grade": "A", "min_percentage": "90", "max_percentage": "100"},
                {"grade": "B", "min_percentage": "80", "max_percentage": "89.99"},
                {"grade": "C", "min_percentage": "70", "max_percentage": "79.99"},
                {"grade": "D", "min_percentage": "60", "max_percentage": "69.99"},
                {"grade": "E", "min_percentage": "50", "max_percentage": "59.99"},
                {"grade": "F", "min_percentage": "0", "max_percentage": "49.99"},
            ],
            "minimum_passing_percentage": "40",
            "require_subject_pass": True,
            "subject_passing_percentage": "33",
            "weighted_subjects": {},
        }

    def test_new_assistant_starts_with_exact_marks_first_welcome(self):
        session = create_assistant_session()

        self.assertEqual(session.step, "marks")
        self.assertEqual(
            session.messages,
            [
                {"role": "assistant", "content": WELCOME_MESSAGE},
                {
                    "role": "assistant",
                    "content": "What is the student's full name?",
                },
            ],
        )
        self.assertEqual(session.state["intake"]["input"]["label"], "Student name")

    def test_chat_answers_are_saved_as_context_after_each_turn(self):
        session = create_assistant_session()
        answers = [
            "Rahul Sharma",
            "12",
            "10",
            "A",
            "2026-2027",
            "Final Examination",
            "Mathematics",
            "85",
            "100",
            "no",
            "yes",
        ]

        for answer in answers:
            advance_assistant(session, "intake_answer", {"answer": answer})
            session.refresh_from_db()

        self.assertEqual(session.step, "confirm_marks")
        self.assertEqual(session.state["details"], self.details)
        self.assertEqual(
            session.state["marks"],
            [{"subject": "Mathematics", "marks": "85", "maximum_marks": "100"}],
        )
        self.assertTrue(session.state["rank_requested"])
        self.assertEqual(session.messages[-2]["role"], "user")
        self.assertEqual(session.messages[-2]["content"], "yes")
        self.assertIn("Rahul Sharma", session.messages[-1]["content"])
        self.assertEqual(
            [message["content"] for message in session.messages if message["role"] == "user"],
            answers,
        )

    def test_invalid_chat_answer_is_not_added_to_saved_history(self):
        session = create_assistant_session()
        with self.assertRaises(ValidationError):
            advance_assistant(session, "intake_answer", {"answer": ""})

        session.refresh_from_db()
        self.assertEqual(session.state["intake"]["detail_index"], 0)
        self.assertEqual(len(session.messages), 2)

    def test_legacy_marks_session_gets_a_persisted_first_question(self):
        session = create_assistant_session()
        session.state.pop("intake")
        session.save(update_fields=["state"])

        ensure_assistant_intake(session)
        session.refresh_from_db()

        self.assertEqual(session.state["intake"]["detail_index"], 0)
        self.assertEqual(session.messages[-1]["content"], "What is the student's full name?")

    def test_assistant_api_persists_staff_session_and_exact_first_message(self):
        client = APIClient()
        self.assertEqual(client.post("/api/assistant/sessions/").status_code, 403)
        staff_user = get_user_model().objects.create_user(
            username="assistant-staff",
            password="test-password",
            is_staff=True,
        )
        client.force_authenticate(user=staff_user)

        created = client.post("/api/assistant/sessions/")

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["messages"][0]["content"], WELCOME_MESSAGE)
        self.assertEqual(created.data["step"], "marks")
        restored = client.get(f"/api/assistant/sessions/{created.data['id']}/")
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.data["messages"], created.data["messages"])

    def test_assistant_page_sets_csrf_cookie_for_staff_workflow(self):
        response = self.client.get("/assistant/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)

    def test_marks_are_validated_before_policy_question(self):
        session = create_assistant_session()
        with self.assertRaises(ValidationError):
            advance_assistant(
                session,
                "submit_marks",
                {
                    "details": self.details,
                    "marks": [
                        {
                            "subject": "Mathematics",
                            "marks": "101",
                            "maximum_marks": "100",
                        }
                    ],
                },
            )
        session.refresh_from_db()
        self.assertEqual(session.step, "marks")

        advance_assistant(
            session,
            "submit_marks",
            {"details": self.details, "marks": self.marks},
        )
        session.refresh_from_db()
        self.assertEqual(session.step, "confirm_marks")
        self.assertIn("five subjects", session.messages[-1]["content"])
        self.assertNotIn(POLICY_QUESTION, session.messages[-1]["content"])

        advance_assistant(session, "confirm_marks")
        session.refresh_from_db()
        self.assertEqual(session.step, "policy_choice")
        self.assertEqual(session.messages[-1]["content"], POLICY_QUESTION)

    def test_calculates_grades_weights_pass_status_and_class_comparisons(self):
        policy = {
            **self.policy,
            "weighted_subjects": {"mathematics": "2"},
        }
        result = calculate_report(
            self.details,
            self.marks,
            policy,
            comparisons=[
                {
                    "roll_number": "13",
                    "marks": [
                        {**mark, "marks": "70"}
                        for mark in self.marks
                    ],
                }
            ],
        )

        self.assertEqual(result["total_marks"], "430.00")
        self.assertEqual(result["total_maximum_marks"], "500.00")
        self.assertEqual(result["percentage"], "85.83")
        self.assertEqual(result["overall_grade"], "B")
        self.assertTrue(result["passed"])
        self.assertEqual(result["rank"], 1)
        self.assertIsNotNone(result["percentile"])
        self.assertEqual(result["subject_results"][0]["grade"], "B")

    def test_custom_grade_boundaries_must_cover_all_percentages(self):
        invalid_policy = {
            **self.policy,
            "grade_boundaries": self.policy["grade_boundaries"][:-1],
        }
        with self.assertRaisesMessage(ValidationError, "must cover the full 0-100 range"):
            calculate_report(self.details, self.marks, invalid_policy)

    @patch(
        "student.ai_insights.clarify_grading_requirements",
        return_value="What minimum percentage is required to pass each subject?",
    )
    def test_llama_clarification_keeps_the_session_on_policy_requirements(
        self, clarify
    ):
        session = create_assistant_session()
        advance_assistant(
            session,
            "submit_marks",
            {"details": self.details, "marks": self.marks},
        )
        advance_assistant(session, "confirm_marks")
        advance_assistant(session, "choose_policy", {"mode": "proposal"})

        advance_assistant(
            session,
            "clarify_requirements",
            {"requirements": "Use letter grades and weighted mathematics."},
        )

        session.refresh_from_db()
        self.assertEqual(session.step, "requirements")
        self.assertEqual(
            session.state["policy_requirements"],
            "Use letter grades and weighted mathematics.",
        )
        self.assertIn("minimum percentage", session.messages[-1]["content"])
        clarify.assert_called_once()

    @patch(
        "student.ai_insights.answer_workflow_question",
        return_value="Enter one row per subject with its maximum marks.",
    )
    def test_workflow_question_uses_only_question_and_step(
        self, answer_question
    ):
        session = create_assistant_session()
        advance_assistant(
            session,
            "submit_marks",
            {"details": self.details, "marks": self.marks},
        )

        advance_assistant(
            session,
            "ask_question",
            {"question": "How do I enter marks?"},
        )

        session.refresh_from_db()
        self.assertEqual(session.step, "confirm_marks")
        self.assertEqual(session.messages[-2]["content"], "How do I enter marks?")
        self.assertEqual(
            session.messages[-1]["content"],
            "Enter one row per subject with its maximum marks.",
        )
        answer_question.assert_called_once()
        self.assertEqual(
            answer_question.call_args.args[:2],
            ("How do I enter marks?", "confirm_marks"),
        )
        self.assertEqual(
            answer_question.call_args.args[2]["conversation"][-1]["content"],
            "How do I enter marks?",
        )

    @patch(
        "student.ai_insights.generate_academic_feedback",
        return_value="Build on this strong foundation.",
    )
    def test_class_rank_requires_teacher_confirmation_of_complete_comparison_data(
        self, generate_feedback
    ):
        session = create_assistant_session()
        advance_assistant(
            session,
            "submit_marks",
            {"details": self.details, "marks": self.marks},
        )
        advance_assistant(session, "confirm_marks")
        advance_assistant(session, "choose_policy", {"mode": "custom"})
        advance_assistant(session, "submit_custom_policy", self.policy)
        advance_assistant(session, "approve_policy")
        peer = {
            "roll_number": "13",
            "marks": [
                {**mark, "marks": "70"}
                for mark in self.marks
            ],
        }

        with self.assertRaisesMessage(
            ValidationError, "includes all students in the same class and examination"
        ):
            advance_assistant(session, "add_comparisons", {"comparisons": [peer]})
        session.refresh_from_db()
        self.assertEqual(session.step, "comparison")

        advance_assistant(
            session,
            "add_comparisons",
            {"comparisons": [peer], "comparison_complete": True},
        )
        session.refresh_from_db()
        self.assertEqual(session.state["calculation"]["rank"], 1)
        self.assertEqual(session.state["calculation"]["percentile"], "75.00")
        generate_feedback.assert_called_once()

        advance_assistant(session, "issue_report")
        examination = Examination.objects.get(
            name=self.details["examination_name"],
            class_name=self.details["class_name"],
            academic_year=self.details["academic_year"],
        )
        self.assertTrue(examination.comparison_complete)
        self.assertEqual(len(examination.comparison_data), 2)
        peer = Student.objects.get(
            roll_number="13",
            class_name=self.details["class_name"],
            academic_year=self.details["academic_year"],
        )
        self.assertEqual(peer.subject_marks.filter(examination=examination).count(), 5)

    @patch(
        "student.ai_insights.propose_grading_policy",
        return_value={
            **{
                "name": "Proposed school policy",
                "grade_boundaries": [
                    {"grade": "A", "min_percentage": "90", "max_percentage": "100"},
                    {"grade": "B", "min_percentage": "80", "max_percentage": "89.99"},
                    {"grade": "C", "min_percentage": "70", "max_percentage": "79.99"},
                    {"grade": "D", "min_percentage": "60", "max_percentage": "69.99"},
                    {"grade": "E", "min_percentage": "50", "max_percentage": "59.99"},
                    {"grade": "F", "min_percentage": "0", "max_percentage": "49.99"},
                ],
                "minimum_passing_percentage": "40",
                "require_subject_pass": False,
                "subject_passing_percentage": "33",
                "weighted_subjects": {},
            }
        },
    )
    def test_ai_grading_proposal_is_stored_unapproved_until_teacher_approval(
        self, propose_policy
    ):
        session = create_assistant_session()
        advance_assistant(
            session,
            "submit_marks",
            {"details": self.details, "marks": self.marks},
        )
        advance_assistant(session, "confirm_marks")
        advance_assistant(session, "choose_policy", {"mode": "proposal"})
        advance_assistant(
            session,
            "propose_policy",
            {"requirements": "Use letter grades and require 40 percent to pass."},
        )

        policy = GradingPolicy.objects.get(pk=session.state["policy_id"])
        self.assertTrue(policy.ai_generated_proposal)
        self.assertFalse(policy.approved)
        self.assertEqual(session.step, "approve_policy")
        self.assertIn("requires teacher approval", session.messages[-1]["content"])

        advance_assistant(session, "approve_policy")
        policy.refresh_from_db()
        self.assertTrue(policy.approved)
        propose_policy.assert_called_once()

    @patch(
        "student.ai_insights.generate_academic_feedback",
        return_value="Practice consistently and extend problem-solving tasks.",
    )
    def test_report_is_not_issued_until_preview_confirmation_and_pdf_downloads(
        self, generate_feedback
    ):
        session = create_assistant_session()
        advance_assistant(
            session,
            "submit_marks",
            {"details": self.details, "marks": self.marks},
        )
        advance_assistant(session, "confirm_marks")
        advance_assistant(session, "choose_policy", {"mode": "custom"})
        advance_assistant(session, "submit_custom_policy", self.policy)
        advance_assistant(session, "approve_policy")
        advance_assistant(session, "skip_comparisons")

        session.refresh_from_db()
        self.assertEqual(session.step, "preview")
        self.assertEqual(ReportCard.objects.count(), 0)
        generate_feedback.assert_called_once()

        advance_assistant(session, "issue_report", {"teacher_remarks": "Well done."})
        session.refresh_from_db()
        self.assertEqual(session.step, "issued")
        report_card = ReportCard.objects.get(pk=session.report_card_id)
        self.assertTrue(report_card.passed)
        self.assertEqual(report_card.teacher_remarks, "Well done.")
        self.assertIsNone(report_card.rank)
        self.assertIn("unavailable", report_card.rank_unavailable_reason)
        report_viewer = get_user_model().objects.create_user(
            username="assistant-report-viewer",
            password="assistant-report-viewer-password",
            is_staff=True,
        )
        self.client.force_login(report_viewer)
        html_report = self.client.get(
            f"/students/{report_card.student_id}/report-card/"
        )
        self.assertEqual(html_report.status_code, 200)
        self.assertContains(html_report, "Overall Percentage")
        self.assertContains(html_report, "Academic Feedback")
        self.assertContains(html_report, "Teacher Remarks")
        pdf = build_report_card_pdf(report_card)
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        user = get_user_model().objects.create_user(
            username="pdf-staff",
            password="test-password",
            is_staff=True,
        )
        self.client.force_login(user)
        pdf_response = self.client.get(
            f"/api/assistant/sessions/{session.pk}/pdf/"
        )
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")


class ManualReportCardApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff_user = get_user_model().objects.create_user(
            username="manual-report-staff",
            password="manual-test-password",
            is_staff=True,
        )
        self.client.force_authenticate(user=self.staff_user)
        self.payload = {
            "details": {
                "name": "Mina Patel",
                "roll_number": "M-12",
                "class_name": "10",
                "section": "A",
                "academic_year": "2026-2027",
                "examination_name": "Final Examination",
            },
            "marks": [
                {"subject": "Mathematics", "marks": "85", "maximum_marks": "100"},
                {"subject": "Science", "marks": "92", "maximum_marks": "100"},
            ],
            "rank_requested": True,
            "teacher_remarks": "Consistent effort.",
            "policy": {
                "name": "Manual school policy",
                "grade_boundaries": [
                    {"grade": "A", "min_percentage": "90", "max_percentage": "100"},
                    {"grade": "B", "min_percentage": "80", "max_percentage": "89.99"},
                    {"grade": "C", "min_percentage": "70", "max_percentage": "79.99"},
                    {"grade": "D", "min_percentage": "60", "max_percentage": "69.99"},
                    {"grade": "E", "min_percentage": "50", "max_percentage": "59.99"},
                    {"grade": "F", "min_percentage": "0", "max_percentage": "49.99"},
                ],
                "minimum_passing_percentage": "40",
                "require_subject_pass": True,
                "subject_passing_percentage": "33",
                "weighted_subjects": {},
            },
        }

    @override_settings(
        CSRF_TRUSTED_ORIGINS=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )
    def test_staff_can_sign_in_through_vite_proxy(self):
        client = APIClient(enforce_csrf_checks=True)
        login_page = client.get("/admin/login/")
        csrf_token = client.cookies["csrftoken"].value

        response = client.post(
            "/admin/login/",
            {
                "username": self.staff_user.username,
                "password": "manual-test-password",
                "csrfmiddlewaretoken": csrf_token,
                "next": "/admin/",
            },
            HTTP_ORIGIN="http://127.0.0.1:5173",
        )

        self.assertEqual(login_page.status_code, 200)
        self.assertEqual(response.status_code, 302)

    def test_manual_preview_does_not_issue_report_until_teacher_confirms(self):
        preview = self.client.post(
            "/api/manual/report-cards/preview/",
            self.payload,
            format="json",
        )

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["total_marks"], "177.00")
        self.assertEqual(preview.data["total_maximum_marks"], "200.00")
        self.assertEqual(preview.data["percentage"], "88.50")
        self.assertEqual(preview.data["overall_grade"], "B")
        self.assertTrue(preview.data["passed"])
        self.assertEqual(ReportCard.objects.count(), 0)

        issued = self.client.post(
            "/api/manual/report-cards/issue/",
            self.payload,
            format="json",
        )

        self.assertEqual(issued.status_code, 201)
        report_card = ReportCard.objects.get(pk=issued.data["report_card_id"])
        self.assertEqual(report_card.teacher_remarks, "Consistent effort.")
        self.assertEqual(report_card.teacher_summary, "")
        self.assertTrue(report_card.grading_policy.approved)
        self.assertEqual(report_card.student.subject_marks.count(), 2)

        pdf = self.client.get(f"/api{issued.data['pdf_url']}")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_manual_report_generation_requires_staff_and_valid_marks(self):
        self.client.force_authenticate(user=None)
        denied = self.client.post(
            "/api/manual/report-cards/preview/",
            self.payload,
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(user=self.staff_user)
        invalid_payload = {
            **self.payload,
            "marks": [
                {"subject": "Mathematics", "marks": "101", "maximum_marks": "100"}
            ],
        }
        invalid = self.client.post(
            "/api/manual/report-cards/preview/",
            invalid_payload,
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(ReportCard.objects.count(), 0)


class TeacherAuthenticationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @override_settings(
        CSRF_TRUSTED_ORIGINS=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )
    def test_registration_and_login_accept_csrf_protected_vite_requests(self):
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get("/api/auth/csrf/")
        self.assertEqual(csrf.status_code, 200)
        csrf_token = csrf.data["csrfToken"]
        credentials = {
            "username": "vite-teacher",
            "password": "vite-teacher-account-password",
        }

        registered = client.post(
            "/api/auth/register/",
            credentials,
            format="json",
            HTTP_ORIGIN="http://127.0.0.1:5173",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(registered.status_code, 201)

        logout_token = client.cookies["csrftoken"].value
        client.post(
            "/api/auth/logout/",
            {},
            format="json",
            HTTP_ORIGIN="http://127.0.0.1:5173",
            HTTP_X_CSRFTOKEN=logout_token,
        )
        login_token = client.cookies["csrftoken"].value
        logged_in = client.post(
            "/api/auth/login/",
            credentials,
            format="json",
            HTTP_ORIGIN="http://127.0.0.1:5173",
            HTTP_X_CSRFTOKEN=login_token,
        )
        self.assertEqual(logged_in.status_code, 200)

    def test_teacher_can_register_then_sign_in_with_chosen_credentials(self):
        payload = {
            "username": "new-teacher",
            "password": "teacher-account-password-2026",
        }

        registered = self.client.post(
            "/api/auth/register/",
            payload,
            format="json",
        )

        self.assertEqual(registered.status_code, 201)
        self.assertEqual(registered.data, {
            "authenticated": True,
            "username": "new-teacher",
        })
        user = get_user_model().objects.get(username="new-teacher")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.check_password(payload["password"]))
        self.assertTrue(self.client.get("/api/auth/me/").data["authenticated"])

        logged_out = self.client.post("/api/auth/logout/")
        self.assertEqual(logged_out.status_code, 200)
        self.assertFalse(self.client.get("/api/auth/me/").data["authenticated"])

        logged_in = self.client.post(
            "/api/auth/login/",
            payload,
            format="json",
        )
        self.assertEqual(logged_in.status_code, 200)
        self.assertTrue(self.client.get("/api/auth/me/").data["authenticated"])

        rejected = self.client.post(
            "/api/auth/login/",
            {"username": "new-teacher", "password": "incorrect-password"},
            format="json",
        )
        self.assertEqual(rejected.status_code, 401)

    def test_registration_rejects_duplicate_usernames_and_weak_passwords(self):
        payload = {
            "username": "registered-teacher",
            "password": "strong-teacher-password-2026",
        }
        self.assertEqual(
            self.client.post("/api/auth/register/", payload, format="json").status_code,
            201,
        )
        duplicate = self.client.post(
            "/api/auth/register/",
            payload,
            format="json",
        )
        weak_password = self.client.post(
            "/api/auth/register/",
            {"username": "another-teacher", "password": "password"},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(weak_password.status_code, 400)
