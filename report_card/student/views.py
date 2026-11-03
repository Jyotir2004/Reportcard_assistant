from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from .models import ReportCard, SubjectMark


@login_required(login_url="/login/")
def student_report_card(request, student_id):
    report_card = get_object_or_404(
        ReportCard.objects.select_related(
            "student", "student__department", "examination"
        ).order_by("-generated_at"),
        student_id=student_id,
    )
    marks = SubjectMark.objects.filter(
        student=report_card.student, examination=report_card.examination
    ).select_related("subject")
    return render(
        request,
        "student/report_card.html",
        {"report_card": report_card, "subject_marks": marks},
    )
