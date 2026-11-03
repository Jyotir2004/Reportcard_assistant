import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Student(models.Model):
    roll_number = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    class_name = models.CharField(max_length=50, blank=True)
    section = models.CharField(max_length=30, blank=True)
    academic_year = models.CharField(max_length=20, blank=True)
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
    )

    class Meta:
        ordering = ["roll_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["roll_number", "class_name", "section", "academic_year"],
                name="unique_student_roll_class_year",
            )
        ]

    def __str__(self):
        return f"{self.roll_number} - {self.name}"


class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True)
    maximum_marks = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=100,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SubjectMark(models.Model):
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="subject_marks"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="student_marks"
    )
    examination = models.ForeignKey(
        "Examination",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subject_marks",
    )
    maximum_marks = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    marks = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        ordering = ["subject__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "examination", "subject"],
                name="unique_student_exam_subject_mark",
            ),
            models.UniqueConstraint(
                fields=["student", "subject"],
                condition=Q(examination__isnull=True),
                name="unique_legacy_student_subject_mark",
            ),
            models.CheckConstraint(condition=Q(marks__gte=0), name="marks_nonnegative"),
        ]

    def clean(self):
        super().clean()
        if self.maximum_marks is not None and self.maximum_marks <= 0:
            raise ValidationError(
                {"maximum_marks": "Maximum marks must be greater than zero."}
            )
        if self.subject_id and self.marks is not None:
            maximum_marks = self.maximum_marks
            if maximum_marks is None:
                maximum_marks = Subject.objects.values_list(
                    "maximum_marks", flat=True
                ).filter(pk=self.subject_id).first()
            if maximum_marks is None:
                return
            if self.marks > maximum_marks:
                raise ValidationError(
                    {"marks": f"Marks cannot exceed the subject maximum of {maximum_marks}."}
                )

    def __str__(self):
        return f"{self.student} - {self.subject}: {self.marks}"


class Examination(models.Model):
    name = models.CharField(max_length=120)
    class_name = models.CharField(max_length=50)
    section = models.CharField(max_length=30, blank=True)
    academic_year = models.CharField(max_length=20)
    comparison_data = models.JSONField(default=list, blank=True)
    comparison_complete = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-academic_year", "class_name", "section", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "class_name", "section", "academic_year"],
                name="unique_exam_class_year",
            )
        ]

    def __str__(self):
        return f"{self.name} - Class {self.class_name} ({self.academic_year})"


class GradingPolicy(models.Model):
    name = models.CharField(max_length=120)
    class_name = models.CharField(max_length=50, blank=True)
    academic_year = models.CharField(max_length=20, blank=True)
    grade_boundaries = models.JSONField(default=list)
    minimum_passing_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=40,
        validators=[MinValueValidator(0)],
    )
    require_subject_pass = models.BooleanField(default=False)
    subject_passing_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=33,
        validators=[MinValueValidator(0)],
    )
    weighted_subjects = models.JSONField(default=dict, blank=True)
    ai_generated_proposal = models.BooleanField(default=False)
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return f"{self.name}{' (approved)' if self.approved else ' (pending approval)'}"


class AssistantSession(models.Model):
    class Step(models.TextChoices):
        MARKS = "marks", "Collect student details and marks"
        CONFIRM_MARKS = "confirm_marks", "Confirm student details and marks"
        POLICY_CHOICE = "policy_choice", "Choose grading policy"
        EXISTING_POLICY = "existing_policy", "Select existing grading policy"
        REQUIREMENTS = "requirements", "Enter institution requirements"
        CUSTOM_POLICY = "custom_policy", "Customize grading policy"
        APPROVE_POLICY = "approve_policy", "Approve grading policy"
        COMPARISON = "comparison", "Add class comparison marks"
        PREVIEW = "preview", "Review report card"
        ISSUED = "issued", "Report card issued"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_assistant_sessions",
    )
    step = models.CharField(max_length=30, choices=Step.choices, default=Step.MARKS)
    state = models.JSONField(default=dict, blank=True)
    messages = models.JSONField(default=list, blank=True)
    report_card = models.ForeignKey(
        "ReportCard",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assistant_sessions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]


class ReportCard(models.Model):
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="report_cards"
    )
    examination = models.ForeignKey(
        Examination,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="report_cards",
    )
    grading_policy = models.ForeignKey(
        GradingPolicy,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="report_cards",
    )
    total_marks = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    rank = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)]
    )
    generated_at = models.DateTimeField()
    teacher_summary = models.TextField(blank=True)
    summary_generated_at = models.DateTimeField(null=True, blank=True)
    total_maximum_marks = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    percentage = models.DecimalField(
        max_digits=6, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    overall_grade = models.CharField(max_length=10, blank=True)
    passed = models.BooleanField(default=False)
    percentile = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    rank_unavailable_reason = models.CharField(max_length=300, blank=True)
    subject_results = models.JSONField(default=list, blank=True)
    teacher_remarks = models.TextField(blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["rank", "student__roll_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "examination"],
                condition=Q(examination__isnull=False),
                name="unique_student_exam_report_card",
            ),
            models.UniqueConstraint(
                fields=["student"],
                condition=Q(examination__isnull=True),
                name="unique_legacy_student_report_card",
            ),
        ]

    def __str__(self):
        return f"Report card for {self.student} (rank {self.rank})"
