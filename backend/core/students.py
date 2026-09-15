import secrets

from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ClassMember, Cohort, Student, StudentCreatedEvent, User
from .permissions import IsReadyUser, IsStudent, IsTeacher
from .throttling import consume
from .views import PublicAuthView, user_data


def student_data(student):
    return {
        "id": student.pk,
        "name": student.user.display_name,
        "seat_number": student.seat_number,
        "student_number": student.student_number,
        "avatar": student.avatar,
    }


class ImportSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=100000, trim_whitespace=False)


class StudentRowSerializer(serializers.Serializer):
    seat_number = serializers.IntegerField(min_value=1, max_value=9999)
    name = serializers.CharField(max_length=80)
    student_number = serializers.RegexField(r"^\S{1,64}$", max_length=64)


class StudentsView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request, pk):
        get_object_or_404(
            ClassMember, cohort_id=pk, user=request.user, role="homeroom", approved=True
        )
        return Response(
            [student_data(s) for s in Student.objects.filter(cohort_id=pk).select_related("user")]
        )

    def post(self, request, pk):
        payload = ImportSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        lines = [
            (i, line)
            for i, line in enumerate(payload.validated_data["text"].splitlines(), 1)
            if line.strip()
        ]
        if lines and [c.strip() for c in lines[0][1].split("\t")] == ["座號", "姓名", "學號"]:
            lines = lines[1:]
        if not lines or len(lines) > 200:
            raise serializers.ValidationError({"text": "請貼上 1–200 筆學生資料。"})
        results = []
        with transaction.atomic():
            get_object_or_404(
                ClassMember.objects.select_for_update(),
                cohort_id=pk,
                user=request.user,
                role="homeroom",
                approved=True,
            )
            cohort = get_object_or_404(Cohort.objects.select_for_update(), pk=pk)
            for number, line in lines:
                result = {"line": number, "status": "error", "message": ""}
                cells = [c.strip() for c in line.split("\t")]
                if len(cells) != 3:
                    result["message"] = "需要座號、姓名、學號三欄，請從表格複製，以 Tab 分隔。"
                else:
                    row = StudentRowSerializer(
                        data=dict(zip(["seat_number", "name", "student_number"], cells))
                    )
                    if not row.is_valid():
                        labels = {"seat_number": "座號", "name": "姓名", "student_number": "學號"}
                        result["message"] = "；".join(
                            f"{labels[k]}：{' '.join(v)}" for k, v in row.errors.items()
                        )
                    else:
                        values = row.validated_data
                        existing = (
                            Student.objects.filter(
                                cohort=cohort, student_number=values["student_number"]
                            )
                            .select_related("user")
                            .first()
                        )
                        if existing:
                            if (
                                existing.seat_number == values["seat_number"]
                                and existing.user.display_name == values["name"]
                            ):
                                result.update(status="skipped", message="已存在，略過。")
                            else:
                                result["message"] = "學號已存在，但姓名或座號不同；請確認資料。"
                        elif Student.objects.filter(
                            cohort=cohort, seat_number=values["seat_number"]
                        ).exists():
                            result["message"] = "座號已被其他學生使用。"
                        else:
                            user = User(
                                account_type="student", email=None, display_name=values["name"]
                            )
                            user.set_password(values["student_number"])
                            user.save()
                            student = Student.objects.create(
                                cohort=cohort,
                                user=user,
                                seat_number=values["seat_number"],
                                student_number=values["student_number"],
                                avatar=secrets.choice(["cat", "dog", "rabbit"]),
                            )
                            StudentCreatedEvent.objects.create(
                                student=student,
                                actor=request.user,
                                actor_name=request.user.display_name,
                            )
                            result.update(status="created", message="已建立。")
                results.append(result)
        return Response(
            {
                "results": results,
                "summary": {
                    status: sum(r["status"] == status for r in results)
                    for status in ["created", "skipped", "error"]
                },
            }
        )


class StudentLoginSerializer(serializers.Serializer):
    class_code = serializers.RegexField(r"^[0-9a-fA-F]{10}$")
    student_number = serializers.RegexField(r"^\S{1,64}$", max_length=64)
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class StudentLoginView(PublicAuthView):
    throttle_scope = "student-login"

    def post(self, request):
        form = StudentLoginSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        values = form.validated_data
        code = values["class_code"].upper()
        consume("student-login:account", f"{code}:{values['student_number']}", 5)
        with transaction.atomic():
            cohort = Cohort.objects.select_for_update().filter(student_login_code=code).first()
            student = (
                Student.objects.select_related("user")
                .filter(
                    cohort=cohort,
                    student_number=values["student_number"],
                    user__is_active=True,
                    user__account_type="student",
                )
                .first()
                if cohort
                else None
            )
            if student is None:
                User().set_password(values["password"])
            if student is None or not student.user.check_password(values["password"]):
                return Response({"detail": "班級登入碼、學號或密碼不正確。"}, status=400)
            login(request, student.user)
            # Persist before releasing the cohort lock so deletion can revoke this session.
            request.session.save()
            return Response(user_data(student.user))


class ChangeStudentPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class StudentPasswordView(APIView):
    permission_classes = [IsStudent]

    def post(self, request):
        form = ChangeStudentPasswordSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        password = form.validated_data["password"]
        candidate = get_object_or_404(Student, user=request.user)
        with transaction.atomic():
            get_object_or_404(Cohort.objects.select_for_update(), pk=candidate.cohort_id)
            student = get_object_or_404(Student.objects.select_for_update(), pk=candidate.pk)
            user = get_object_or_404(User.objects.select_for_update(), pk=request.user.pk)
            if request.session.get("_auth_user_hash") != user.get_session_auth_hash():
                raise PermissionDenied("登入已失效，請重新登入。")
            if not student.must_change_password:
                raise serializers.ValidationError({"detail": "已完成首次密碼修改。"})
            if password == student.student_number:
                raise serializers.ValidationError({"password": "不可沿用初始學號密碼。"})
            try:
                validate_password(
                    password, User(username=student.student_number, first_name=user.display_name)
                )
            except DjangoValidationError as error:
                raise serializers.ValidationError({"password": error.messages}) from error
            user.set_password(password)
            user.save(update_fields=["password"])
            student.must_change_password = False
            student.save(update_fields=["must_change_password"])
            update_session_auth_hash(request, user)
            request.session.save()
        return Response({"account_type": "student", "must_change_password": False})


class StudentMeView(APIView):
    permission_classes = [IsStudent, IsReadyUser]

    def get(self, request):
        student = get_object_or_404(
            Student.objects.select_related("user", "cohort"), user=request.user
        )
        return Response(
            {
                **student_data(student),
                "cohort": {"id": student.cohort_id, "name": student.cohort.name},
            }
        )
