
from django.contrib import admin
from django.urls import include, path
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import TemplateView

from student import views
from student.assistant_api import ReportCardPdfView

urlpatterns = [
    path("", TemplateView.as_view(template_name="index.html"), name="home"),
    path(
        "login/",
        ensure_csrf_cookie(TemplateView.as_view(template_name="index.html")),
        name="teacher-login",
    ),
    path(
        
        "register/",
        ensure_csrf_cookie(TemplateView.as_view(template_name="index.html")),
        name="teacher-register",
    ),
    path(
        "assistant/",
        ensure_csrf_cookie(TemplateView.as_view(template_name="index.html")),
        name="assistant",
    ),
    path(
        "manual/",
        ensure_csrf_cookie(TemplateView.as_view(template_name="index.html")),
        name="manual-report",
    ),
    path("admin/", admin.site.urls),
    path("api/", include("student.api_urls")),
    path(
        "report-cards/<int:report_id>/pdf/",
        ReportCardPdfView.as_view(),
        name="direct-report-card-pdf",
    ),
    path(
        "api/api/report-cards/<int:report_id>/pdf/",
        ReportCardPdfView.as_view(),
        name="root-double-api-report-card-pdf",
    ),
    path(
        "students/<int:student_id>/report-card/",
        views.student_report_card,
        name="student-report-card",
    ),
]

