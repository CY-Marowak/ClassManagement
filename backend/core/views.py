from django.contrib.auth import login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .accounts import send_action_email, use_action_token
from .models import EmailToken, User
from .serializers import (
    EmailSerializer,
    LoginSerializer,
    RegisterSerializer,
    ResetSerializer,
    TokenSerializer,
)
from .throttling import throttle_auth


def csrf(request):
    return JsonResponse({"csrfToken": get_token(request)})


def user_data(user):
    return {
        "id": user.pk,
        "display_name": user.display_name,
        "email": user.email,
        "email_verified": user.email_verified,
    }


@method_decorator(csrf_protect, name="dispatch")
class PublicAuthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "auth"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        throttle_auth(request, self.throttle_scope)


class RegisterView(PublicAuthView):
    throttle_scope = "register"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        with transaction.atomic():
            user, created = User.objects.get_or_create(
                email=values["email"], defaults={"display_name": values["display_name"]}
            )
            if created:
                user.set_password(values["password"])
                user.save()
                send_action_email(user, "verify")
        return Response({"detail": "若此 Email 可註冊，驗證信已寄出。請查看信箱。"}, status=202)


class VerifyView(PublicAuthView):
    throttle_scope = "verify"

    def post(self, request):
        serializer = TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with use_action_token(serializer.validated_data["token"], "verify") as user:
            user.email_verified = True
            user.save(update_fields=["email_verified"])
        return Response({"detail": "Email 驗證完成，現在可以登入。"})


class LoginView(PublicAuthView):
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(
            email=serializer.validated_data["email"].lower(), is_active=True
        ).first()
        valid = user.check_password(serializer.validated_data["password"]) if user else False
        if not user:
            User().set_password(serializer.validated_data["password"])
        if not valid:
            return Response({"detail": "Email 或密碼不正確。"}, status=400)
        login(request, user)
        return Response(user_data(user))


class MeView(APIView):
    def get(self, request):
        return Response(user_data(request.user))


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        logout(request)
        return Response({"detail": "已登出。"})


class RequestEmailView(PublicAuthView):
    throttle_scope = "recovery"
    purpose = "reset"

    def post(self, request):
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(
            email=serializer.validated_data["email"].lower(), is_active=True
        ).first()
        if user and (self.purpose == "reset" or not user.email_verified):
            send_action_email(user, self.purpose)
        return Response({"detail": "若此帳號符合條件，信件已寄出。請查看信箱。"}, status=202)


class ResendVerificationView(RequestEmailView):
    throttle_scope = "resend"
    purpose = "verify"


class ResetView(PublicAuthView):
    throttle_scope = "reset"

    def post(self, request):
        serializer = ResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with use_action_token(serializer.validated_data["token"], "reset") as user:
            try:
                validate_password(serializer.validated_data["password"], user)
            except DjangoValidationError as error:
                raise ValidationError({"password": error.messages}) from error
            user.set_password(serializer.validated_data["password"])
            user.save(update_fields=["password"])
            EmailToken.objects.filter(user=user, purpose="reset", used=False).update(used=True)
        return Response({"detail": "密碼已更新，請重新登入。"})
