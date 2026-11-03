from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView


def _user_payload(user):
    return {"authenticated": True, "username": user.get_username()}


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfTokenView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class TeacherRegistrationView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        User = get_user_model()
        username = str(request.data.get(User.USERNAME_FIELD, "")).strip()
        password = request.data.get("password")
        if not username:
            return Response(
                {User.USERNAME_FIELD: ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(password, str) or not password:
            return Response(
                {"password": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User()
        username_field = User._meta.get_field(User.USERNAME_FIELD)
        try:
            setattr(user, User.USERNAME_FIELD, username_field.clean(username, user))
            validate_password(password, user=user)
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_staff = True
        user.set_password(password)
        try:
            with transaction.atomic():
                user.save()
        except IntegrityError:
            return Response(
                {User.USERNAME_FIELD: ["An account with this username already exists."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response(_user_payload(user), status=status.HTTP_201_CREATED)


@method_decorator(csrf_protect, name="dispatch")
class TeacherLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        User = get_user_model()
        username = str(request.data.get(User.USERNAME_FIELD, "")).strip()
        password = request.data.get("password")
        user = authenticate(
            request,
            **{User.USERNAME_FIELD: username, "password": password},
        )
        if user is None or not user.is_staff:
            return Response(
                {"detail": "Username or password is incorrect."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        login(request, user)
        return Response(_user_payload(user))


@method_decorator(csrf_protect, name="dispatch")
class TeacherLogoutView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        logout(request)
        return Response({"authenticated": False})


class CurrentTeacherView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return Response({"authenticated": False})
        return Response(_user_payload(request.user))
