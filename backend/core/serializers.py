from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Cohort, User


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    display_name = serializers.CharField(max_length=80)
    password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)

    def validate(self, attrs):
        attrs["email"] = attrs["email"].lower()
        try:
            validate_password(
                attrs["password"], User(email=attrs["email"], display_name=attrs["display_name"])
            )
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": error.messages}) from error
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class TokenSerializer(serializers.Serializer):
    token = serializers.RegexField(r"^[A-Za-z0-9_-]{43}$")


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class ResetSerializer(TokenSerializer):
    password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)


class CohortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cohort
        fields = ["id", "name", "entry_year", "current_grade"]
        read_only_fields = ["id"]
