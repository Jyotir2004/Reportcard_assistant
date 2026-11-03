from django.urls import path
from rest_framework.routers import DefaultRouter

from .assistant_api import (
    ApprovedGradingPoliciesView,
    AssistantAutoFillView,
    AssistantChatStreamView,
    AssistantQuickReportCardView,
    AssistantReportPdfView,
    AssistantSessionListCreateView,
    AssistantSessionView,
    ManualReportIssueView,
    ManualReportPreviewView,
    ReportCardPdfView,
)
from .auth_api import (
    CsrfTokenView,
    CurrentTeacherView,
    TeacherLoginView,
    TeacherLogoutView,
    TeacherRegistrationView,
)
from .api import (
    DepartmentViewSet,
    ExaminationViewSet,
    GradingPolicyViewSet,
    ReportCardViewSet,
    StudentViewSet,
    SubjectMarkViewSet,
    SubjectViewSet,
)

router = DefaultRouter()
router.register("departments", DepartmentViewSet)
router.register("examinations", ExaminationViewSet)
router.register("grading-policies", GradingPolicyViewSet)
router.register("students", StudentViewSet)
router.register("subjects", SubjectViewSet)
router.register("marks", SubjectMarkViewSet)
router.register("report-cards", ReportCardViewSet)

urlpatterns = router.urls
urlpatterns += [
    path("auth/csrf/", CsrfTokenView.as_view(), name="auth-csrf"),
    path("auth/me/", CurrentTeacherView.as_view(), name="auth-current-teacher"),
    path("auth/register/", TeacherRegistrationView.as_view(), name="auth-register"),
    path("auth/login/", TeacherLoginView.as_view(), name="auth-login"),
    path("auth/logout/", TeacherLogoutView.as_view(), name="auth-logout"),
    path(
        "manual/report-cards/preview/",
        ManualReportPreviewView.as_view(),
        name="manual-report-card-preview",
    ),
    path(
        "manual/report-cards/issue/",
        ManualReportIssueView.as_view(),
        name="manual-report-card-issue",
    ),
    path(
        "report-cards/<int:report_id>/pdf/",
        ReportCardPdfView.as_view(),
        name="report-card-pdf",
    ),
    path(
        "api/report-cards/<int:report_id>/pdf/",
        ReportCardPdfView.as_view(),
        name="double-api-report-card-pdf",
    ),
    path(
        "assistant/grading-policies/",
        ApprovedGradingPoliciesView.as_view(),
        name="assistant-grading-policies",
    ),
    path("assistant/sessions/", AssistantSessionListCreateView.as_view(), name="assistant-session-create"),
    path("assistant/sessions/<uuid:session_id>/", AssistantSessionView.as_view(), name="assistant-session"),
    path(
        "assistant/sessions/<uuid:session_id>/pdf/",
        AssistantReportPdfView.as_view(),
        name="assistant-report-pdf",
    ),
    path(
        "assistant/chat/stream/",
        AssistantChatStreamView.as_view(),
        name="assistant-chat-stream",
    ),
    path(
        "assistant/quick-report-card/",
        AssistantQuickReportCardView.as_view(),
        name="assistant-quick-report-card",
    ),
    path(
        "assistant/autofill/",
        AssistantAutoFillView.as_view(),
        name="assistant-autofill",
    ),
]
