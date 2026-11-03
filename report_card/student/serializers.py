from rest_framework import serializers

from .models import (
    Department,
    Examination,
    GradingPolicy,
    ReportCard,
    Student,
    Subject,
    SubjectMark,
)


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name"]


class StudentSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)

    class Meta:
        model = Student
        fields = [
            "id", "roll_number", "name", "class_name", "section",
            "academic_year", "department", "department_name",
        ]


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ["id", "name", "maximum_marks"]


class SubjectMarkSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    maximum_marks = serializers.DecimalField(
        max_digits=7,
        decimal_places=2,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = SubjectMark
        fields = [
            "id", "student", "subject", "subject_name", "examination",
            "marks", "maximum_marks",
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        subject = attrs.get("subject", getattr(self.instance, "subject", None))
        marks = attrs.get("marks", getattr(self.instance, "marks", None))
        maximum_marks = attrs.get(
            "maximum_marks",
            getattr(self.instance, "maximum_marks", None),
        )
        if maximum_marks is None and subject is not None:
            maximum_marks = subject.maximum_marks
        if maximum_marks is not None and (
            maximum_marks <= 0 or (marks is not None and marks > maximum_marks)
        ):
            raise serializers.ValidationError(
                {"marks": f"Marks must not exceed the maximum of {maximum_marks}."}
            )
        return attrs

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if instance.maximum_marks is None:
            representation["maximum_marks"] = str(instance.subject.maximum_marks)
        return representation


class ReportCardSerializer(serializers.ModelSerializer):
    student = StudentSerializer(read_only=True)
    subject_marks = serializers.SerializerMethodField()
    examination_name = serializers.CharField(
        source="examination.name", read_only=True, allow_null=True
    )
    subject_results = serializers.JSONField(read_only=True)

    class Meta:
        model = ReportCard
        fields = [
            "id", "student", "examination", "examination_name", "subject_marks",
            "subject_results", "total_marks", "total_maximum_marks", "percentage",
            "overall_grade", "passed", "rank", "percentile",
            "rank_unavailable_reason", "teacher_remarks",
            "issued_at", "generated_at",
        ]

    def get_subject_marks(self, instance):
        if instance.examination_id:
            marks = getattr(
                instance.examination,
                "prefetched_subject_marks",
                instance.examination.subject_marks.select_related("subject").all(),
            )
        else:
            marks = instance.student.subject_marks.filter(
                examination__isnull=True
            ).select_related("subject")
        return SubjectMarkSerializer(marks, many=True).data

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get("request")
        if request and request.user.is_staff:
            representation["teacher_summary"] = instance.teacher_summary
            representation["summary_generated_at"] = instance.summary_generated_at
        return representation


class GradingPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = GradingPolicy
        fields = [
            "id", "name", "class_name", "academic_year", "grade_boundaries",
            "minimum_passing_percentage", "require_subject_pass",
            "subject_passing_percentage", "weighted_subjects",
            "ai_generated_proposal", "approved",
        ]
        read_only_fields = ["approved", "ai_generated_proposal"]

    def validate(self, attrs):
        from .assistant_workflow import validate_policy_data

        values = {
            "name": attrs.get("name", getattr(self.instance, "name", "")),
            "grade_boundaries": attrs.get(
                "grade_boundaries",
                getattr(self.instance, "grade_boundaries", []),
            ),
            "minimum_passing_percentage": attrs.get(
                "minimum_passing_percentage",
                getattr(self.instance, "minimum_passing_percentage", 40),
            ),
            "require_subject_pass": attrs.get(
                "require_subject_pass",
                getattr(self.instance, "require_subject_pass", False),
            ),
            "subject_passing_percentage": attrs.get(
                "subject_passing_percentage",
                getattr(self.instance, "subject_passing_percentage", 33),
            ),
            "weighted_subjects": attrs.get(
                "weighted_subjects",
                getattr(self.instance, "weighted_subjects", {}),
            ),
        }
        return {**attrs, **validate_policy_data(values)}


class ExaminationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Examination
        fields = ["id", "name", "class_name", "section", "academic_year", "created_at"]
        read_only_fields = ["created_at"]
