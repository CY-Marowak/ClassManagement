from core import views
from core.announcements import AnnouncementChangeView, AnnouncementsView, StudentAnnouncementsView
from core.awards import PointAwardsView
from core.batch_scores import PendingReasonsView, ScoreBatchesView
from core.cohorts import ClassDetailView, ClassesView
from core.comments import CommentChangeView, CommentsView, StudentCommentsView
from core.dashboard import DashboardView
from core.import_issues import ImportIssuesView, ResolveImportIssueView
from core.mascots import ClassMascotView, StudentMascotView
from core.memberships import (
    TeacherApplicationsView,
    TeacherCodeView,
    TeacherDecisionView,
    TeacherEventsView,
    TeachersView,
)
from core.score_changes import ScoreChangesView, ScoreEditPreviewView
from core.scores import ScoreEventsView, ScoreRosterView, ScoresView, StudentScoresView
from core.student_management import ResetStudentPasswordView, StudentDetailView, StudentEventsView
from core.students import StudentLoginView, StudentMeView, StudentPasswordView, StudentsView
from django.urls import path

urlpatterns = [
    path("api/classes/<int:pk>/import-issues/", ImportIssuesView.as_view()),
    path("api/classes/<int:pk>/import-issues/<int:issue_id>/", ResolveImportIssueView.as_view()),
    path("api/classes/<int:pk>/dashboard/", DashboardView.as_view()),
    path(
        "api/classes/<int:pk>/announcements/<int:announcement_id>/comments/<int:comment_id>/",
        CommentChangeView.as_view(),
    ),
    path(
        "api/classes/<int:pk>/announcements/<int:announcement_id>/comments/", CommentsView.as_view()
    ),
    path(
        "api/student/announcements/<int:announcement_id>/comments/", StudentCommentsView.as_view()
    ),
    path("api/classes/<int:pk>/announcements/", AnnouncementsView.as_view()),
    path(
        "api/classes/<int:pk>/announcements/<int:announcement_id>/",
        AnnouncementChangeView.as_view(),
    ),
    path("api/student/announcements/", StudentAnnouncementsView.as_view()),
    path("api/student/mascot/", StudentMascotView.as_view()),
    path("api/classes/<int:pk>/mascot/", ClassMascotView.as_view()),
    path("api/classes/<int:pk>/point-awards/", PointAwardsView.as_view()),
    path(
        "api/classes/<int:pk>/scores/<int:record_id>/edit-preview/", ScoreEditPreviewView.as_view()
    ),
    path("api/classes/<int:pk>/score-changes/", ScoreChangesView.as_view()),
    path("api/classes/<int:pk>/pending-reasons/", PendingReasonsView.as_view()),
    path("api/classes/<int:pk>/score-batches/", ScoreBatchesView.as_view()),
    path("api/classes/<int:pk>/score-roster/", ScoreRosterView.as_view()),
    path("api/classes/<int:pk>/scores/", ScoresView.as_view()),
    path("api/classes/<int:pk>/score-events/", ScoreEventsView.as_view()),
    path("api/student/scores/", StudentScoresView.as_view()),
    path("api/teacher-applications/", TeacherApplicationsView.as_view()),
    path("api/classes/<int:pk>/teachers/", TeachersView.as_view()),
    path("api/classes/<int:pk>/teachers/<int:member_id>/", TeacherDecisionView.as_view()),
    path("api/classes/<int:pk>/teacher-events/", TeacherEventsView.as_view()),
    path("api/classes/<int:pk>/teacher-code/", TeacherCodeView.as_view()),
    path("api/classes/", ClassesView.as_view()),
    path("api/classes/<int:pk>/", ClassDetailView.as_view()),
    path("api/classes/<int:pk>/students/", StudentsView.as_view()),
    path("api/classes/<int:pk>/students/<int:student_id>/", StudentDetailView.as_view()),
    path(
        "api/classes/<int:pk>/students/<int:student_id>/reset-password/",
        ResetStudentPasswordView.as_view(),
    ),
    path("api/classes/<int:pk>/student-events/", StudentEventsView.as_view()),
    path("api/student/login/", StudentLoginView.as_view()),
    path("api/student/change-password/", StudentPasswordView.as_view()),
    path("api/student/me/", StudentMeView.as_view()),
    path("api/csrf/", views.csrf),
    path("api/auth/register/", views.RegisterView.as_view()),
    path("api/auth/verify/", views.VerifyView.as_view()),
    path("api/auth/login/", views.LoginView.as_view()),
    path("api/auth/me/", views.MeView.as_view()),
    path("api/auth/logout/", views.LogoutView.as_view()),
    path("api/auth/forgot-password/", views.RequestEmailView.as_view()),
    path("api/auth/resend-verification/", views.ResendVerificationView.as_view()),
    path("api/auth/reset-password/", views.ResetView.as_view()),
]
