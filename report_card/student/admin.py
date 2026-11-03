from django.contrib import admin

from django.contrib import messages

from .models import (
    AssistantSession,
    Department,
    Examination,
    GradingPolicy,
    ReportCard,
    Student,
    Subject,
    SubjectMark,
)
from .services import generate_report_cards


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ["roll_number", "name", "class_name", "section", "academic_year", "department"]
    list_filter = ["department"]
    search_fields = ["roll_number", "name"]


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ["name", "maximum_marks"]
    search_fields = ["name"]


@admin.register(SubjectMark)
class SubjectMarkAdmin(admin.ModelAdmin):
    list_display = ["student", "examination", "subject", "marks", "maximum_marks"]
    list_filter = ["subject", "examination"]
    search_fields = ["student__roll_number", "student__name", "subject__name"]


@admin.action(description="Generate or refresh all report cards")
def refresh_report_cards(modeladmin, request, queryset):
    count = generate_report_cards()
    modeladmin.message_user(
        request,
        f"Generated or refreshed {count} report card(s).",
        messages.SUCCESS,
    )


@admin.register(ReportCard)
class ReportCardAdmin(admin.ModelAdmin):
    list_display = [
        "student", "examination", "total_marks_display", "rank_display",
        "overall_grade", "passed", "generated_at",
    ]
    list_select_related = ["student", "examination"]
    search_fields = ["student__roll_number", "student__name"]
    ordering = ["rank", "student__roll_number"]
    actions = [refresh_report_cards]

    @admin.display(description="Total Marks", ordering="total_marks")
    def total_marks_display(self, obj):
        return obj.total_marks

    @admin.display(description="Rank", ordering="rank")
    def rank_display(self, obj):
        return obj.rank


@admin.register(Examination)
class ExaminationAdmin(admin.ModelAdmin):
    list_display = ["name", "class_name", "section", "academic_year", "created_at"]
    list_filter = ["academic_year", "class_name"]
    search_fields = ["name", "class_name", "section"]


@admin.register(GradingPolicy)
class GradingPolicyAdmin(admin.ModelAdmin):
    list_display = [
        "name", "class_name", "academic_year", "approved",
        "ai_generated_proposal", "created_at",
    ]
    list_filter = ["approved", "ai_generated_proposal", "academic_year"]
    search_fields = ["name", "class_name", "academic_year"]


@admin.register(AssistantSession)
class AssistantSessionAdmin(admin.ModelAdmin):
    list_display = ["id", "step", "user", "report_card", "updated_at"]
    list_filter = ["step"]
    readonly_fields = ["id", "state", "messages", "created_at", "updated_at"]
