from core import views
from core.cohorts import ClassDetailView, ClassesView
from core.memberships import (
    TeacherApplicationsView,
    TeacherCodeView,
    TeacherDecisionView,
    TeacherEventsView,
    TeachersView,
)
from core.student_management import ResetStudentPasswordView, StudentDetailView, StudentEventsView
from core.students import StudentLoginView, StudentMeView, StudentPasswordView, StudentsView
from django.urls import path

urlpatterns = [
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
