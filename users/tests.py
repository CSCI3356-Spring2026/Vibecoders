from io import StringIO
from unittest.mock import MagicMock

from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from users.adapters import BCEmailAdapter, NoSignupAccountAdapter
from users.decorators import admin_required
from users.models import Role

User = get_user_model()


def _add_middleware(request):
    """Attach session + messages middleware so messages.error() works."""
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    MessageMiddleware(lambda r: None).process_request(request)
    return request


# ---------------------------------------------------------------------------
# Adapter tests
# ---------------------------------------------------------------------------
class NoSignupAccountAdapterTests(TestCase):
    """Verify that regular (non-social) signup is fully disabled."""

    def test_regular_signup_disabled(self):
        adapter = NoSignupAccountAdapter()
        request = RequestFactory().get("/accounts/signup/")
        self.assertFalse(adapter.is_open_for_signup(request))


class BCEmailAdapterTests(TestCase):
    """Verify that only @bc.edu Google accounts are accepted."""

    def _make_sociallogin(self, email):
        sociallogin = MagicMock()
        sociallogin.account.extra_data = {"email": email}
        return sociallogin

    def test_bc_email_signup_allowed(self):
        adapter = BCEmailAdapter()
        request = RequestFactory().get("/")
        sociallogin = self._make_sociallogin("eagle@bc.edu")
        self.assertTrue(adapter.is_open_for_signup(request, sociallogin))

    def test_non_bc_email_signup_rejected(self):
        adapter = BCEmailAdapter()
        request = RequestFactory().get("/")
        sociallogin = self._make_sociallogin("user@gmail.com")
        self.assertFalse(adapter.is_open_for_signup(request, sociallogin))

    def test_empty_email_signup_rejected(self):
        adapter = BCEmailAdapter()
        request = RequestFactory().get("/")
        sociallogin = self._make_sociallogin("")
        self.assertFalse(adapter.is_open_for_signup(request, sociallogin))

    def test_bc_email_login_allowed(self):
        adapter = BCEmailAdapter()
        request = RequestFactory().get("/")
        sociallogin = self._make_sociallogin("eagle@bc.edu")
        adapter.pre_social_login(request, sociallogin)

    def test_non_bc_email_login_raises(self):
        adapter = BCEmailAdapter()
        request = _add_middleware(RequestFactory().get("/"))
        sociallogin = self._make_sociallogin("user@gmail.com")
        with self.assertRaises(ImmediateHttpResponse):
            adapter.pre_social_login(request, sociallogin)

    def test_spoofed_bc_subdomain_rejected(self):
        """Ensure subdomains like @fake.bc.edu are also rejected."""
        adapter = BCEmailAdapter()
        request = _add_middleware(RequestFactory().get("/"))
        sociallogin = self._make_sociallogin("user@fake.bc.edu")
        self.assertFalse(adapter.is_open_for_signup(request, sociallogin))
        with self.assertRaises(ImmediateHttpResponse):
            adapter.pre_social_login(request, sociallogin)


# ---------------------------------------------------------------------------
# CustomUser model tests
# ---------------------------------------------------------------------------
class CustomUserModelTests(TestCase):
    """Verify CustomUser role field and helper properties."""

    def test_default_role_is_student(self):
        user = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")
        self.assertEqual(user.role, Role.STUDENT)

    def test_is_bc_admin_false_for_student(self):
        user = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")
        self.assertFalse(user.is_bc_admin)

    def test_is_bc_admin_true_for_admin(self):
        user = User.objects.create_user(username="adm", email="adm@bc.edu", password="test", role=Role.ADMIN)
        self.assertTrue(user.is_bc_admin)

    def test_display_role_student(self):
        user = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")
        self.assertEqual(user.display_role, "Student")

    def test_display_role_admin(self):
        user = User.objects.create_user(username="adm", email="adm@bc.edu", password="test", role=Role.ADMIN)
        self.assertEqual(user.display_role, "Admin")

    def test_str_representation(self):
        user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")
        self.assertEqual(str(user), "eagle (Student)")


# ---------------------------------------------------------------------------
# Decorator / mixin tests
# ---------------------------------------------------------------------------
class AdminRequiredDecoratorTests(TestCase):
    """Verify admin_required decorator gates access correctly."""

    def setUp(self):
        self.factory = RequestFactory()
        self.student = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")
        self.admin = User.objects.create_user(username="adm", email="adm@bc.edu", password="test", role=Role.ADMIN)

        @admin_required
        def protected_view(request):
            return HttpResponse("OK")

        self.protected_view = protected_view

    def test_admin_can_access(self):
        request = self.factory.get("/admin-view/")
        request.user = self.admin
        response = self.protected_view(request)
        self.assertEqual(response.status_code, 200)

    def test_student_gets_403(self):
        request = self.factory.get("/admin-view/")
        request.user = self.student
        with self.assertRaises(PermissionDenied):
            self.protected_view(request)


# ---------------------------------------------------------------------------
# Management command tests
# ---------------------------------------------------------------------------
class SetUserRoleCommandTests(TestCase):
    """Verify the set_user_role management command."""

    def setUp(self):
        self.user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")

    def test_promote_to_admin(self):
        call_command("set_user_role", "eagle@bc.edu", "admin", stdout=StringIO())
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, Role.ADMIN)

    def test_demote_to_student(self):
        self.user.role = Role.ADMIN
        self.user.save()
        call_command("set_user_role", "eagle@bc.edu", "student", stdout=StringIO())
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, Role.STUDENT)

    def test_nonexistent_user_raises(self):
        with self.assertRaises(CommandError):
            call_command("set_user_role", "nobody@bc.edu", "admin", stderr=StringIO())
