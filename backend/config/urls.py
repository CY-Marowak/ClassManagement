from core import views
from core.cohorts import ClassDetailView, ClassesView
from django.urls import path

urlpatterns = [
    path("api/classes/", ClassesView.as_view()),
    path("api/classes/<int:pk>/", ClassDetailView.as_view()),
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
