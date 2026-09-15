from rest_framework.permissions import BasePermission


class IsTeacher(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.account_type == "teacher"


class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.account_type == "student"


class IsReadyUser(BasePermission):
    message = "請先完成首次密碼修改。"

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.account_type == "teacher":
            return True
        return not request.user.student.must_change_password
