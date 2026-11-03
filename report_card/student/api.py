from django.db.models import Avg, Count, Prefetch
from rest_framework import decorators, permissions, response, status, viewsets

from .models import Department, Examination, GradingPolicy, ReportCard, Student, Subject, SubjectMark
from .ai_insights import save_teacher_summary
from .serializers import (
    DepartmentSerializer,
    ExaminationSerializer,
    GradingPolicySerializer,
    ReportCardSerializer,
    StudentSerializer,
    SubjectMarkSerializer,
    SubjectSerializer,
)
from .services import generate_report_cards


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all().order_by("name")
    serializer_class = DepartmentSerializer


class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.select_related("department").all()
    serializer_class = StudentSerializer
    search_fields = ["roll_number", "name", "department__name"]
    ordering_fields = ["roll_number", "name"]
    ordering = ["roll_number"]


class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    search_fields = ["name"]
    ordering_fields = ["name", "maximum_marks"]
    ordering = ["name"]


class SubjectMarkViewSet(viewsets.ModelViewSet):
    queryset = SubjectMark.objects.select_related("student", "subject").all()
    serializer_class = SubjectMarkSerializer
    filterset_fields = ["student", "subject"]
    search_fields = ["student__roll_number", "student__name", "subject__name"]


class ExaminationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Examination.objects.all()
    serializer_class = ExaminationSerializer


class GradingPolicyViewSet(viewsets.ModelViewSet):
    serializer_class = GradingPolicySerializer
    queryset = GradingPolicy.objects.filter(approved=True)
    filterset_fields = ["class_name", "academic_year"]
    search_fields = ["name", "class_name", "academic_year"]

    def get_queryset(self):
        if self.request.user.is_staff:
            return GradingPolicy.objects.all()
        return GradingPolicy.objects.filter(approved=True)

    def perform_create(self, serializer):
        serializer.save(approved=False, ai_generated_proposal=False)

    def perform_update(self, serializer):
        serializer.save(approved=False)

    @decorators.action(
        detail=True,
        methods=["post"],
        permission_classes=[permissions.IsAdminUser],
        url_path="approve",
    )
    def approve(self, request, pk=None):
        policy = self.get_object()
        policy.approved = True
        policy.save(update_fields=["approved"])
        return response.Response(self.get_serializer(policy).data)


class ReportCardViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ReportCard.objects.select_related(
        "student", "student__department", "examination"
    ).prefetch_related(
        Prefetch(
            "examination__subject_marks",
            queryset=SubjectMark.objects.select_related("subject").order_by("subject__name"),
            to_attr="prefetched_subject_marks",
        )
    )
    serializer_class = ReportCardSerializer
    search_fields = ["student__roll_number", "student__name"]
    ordering_fields = ["total_marks", "rank", "generated_at"]
    ordering = ["rank", "student__roll_number"]

    @decorators.action(
        detail=False,
        methods=["post"],
        permission_classes=[permissions.IsAdminUser],
        url_path="generate",
    )
    def generate(self, request):
        count = generate_report_cards()
        return response.Response(
            {"updated": count},
            status=status.HTTP_200_OK,
        )

    @decorators.action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        summary = ReportCard.objects.aggregate(
            total_reports=Count("id"),
            average_total_marks=Avg("total_marks"),
        )
        top_card = self.get_queryset().first()
        return response.Response(
            {
                **summary,
                "top_student": (
                    StudentSerializer(top_card.student).data if top_card else None
                ),
            }
        )

    @decorators.action(
        detail=True,
        methods=["get", "post"],
        permission_classes=[permissions.IsAdminUser],
        url_path="teacher-summary",
    )
    def teacher_summary(self, request, pk=None):
        report_card = self.get_object()
        if request.method == "POST":
            report_card = save_teacher_summary(report_card)

        return response.Response(
            {
                "summary": report_card.teacher_summary,
                "generated_at": report_card.summary_generated_at,
            }
        )
