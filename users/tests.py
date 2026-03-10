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


# Error handling middleware
def _add_middleware(request):
    """Attach session + messages middleware so messages.error() works."""
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    MessageMiddleware(lambda r: None).process_request(request)
    return request


# ---------------------------------------------------------------------------
# Adapter tests
# ---------------------------------------------------------------------------


# Do not allow any signup form besides Google OAuth
class NoSignupAccountAdapterTests(TestCase):
    """Verify that regular (non-social) signup is fully disabled."""

    def test_regular_signup_disabled(self):
        adapter = NoSignupAccountAdapter()
        request = RequestFactory().get("/accounts/signup/")
        self.assertFalse(adapter.is_open_for_signup(request))


# Only allow @bc.edu Google accounts to sign up or log in
class BCEmailAdapterTests(TestCase):
    """Verify that only @bc.edu Google accounts are accepted."""

    # Helper to create a mock sociallogin with specified email
    def _make_sociallogin(self, email):
        sociallogin = MagicMock()
        sociallogin.account.extra_data = {"email": email}
        return sociallogin

    # Allow a BC email to sign up
    def test_bc_email_signup_allowed(self):
        adapter = BCEmailAdapter()
        request = RequestFactory().get("/")
        sociallogin = self._make_sociallogin("eagle@bc.edu")
        self.assertTrue(adapter.is_open_for_signup(request, sociallogin))

    # Reject non-BC emails at signup
    def test_non_bc_email_signup_rejected(self):
        adapter = BCEmailAdapter()
        request = RequestFactory().get("/")
        sociallogin = self._make_sociallogin("user@gmail.com")
        self.assertFalse(adapter.is_open_for_signup(request, sociallogin))

    # Reject empty email at signup
    def test_empty_email_signup_rejected(self):
        adapter = BCEmailAdapter()
        request = RequestFactory().get("/")
        sociallogin = self._make_sociallogin("")
        self.assertFalse(adapter.is_open_for_signup(request, sociallogin))

    # Allow a BC email to log in
    def test_bc_email_login_allowed(self):
        adapter = BCEmailAdapter()
        request = RequestFactory().get("/")
        sociallogin = self._make_sociallogin("eagle@bc.edu")
        adapter.pre_social_login(request, sociallogin)

    # Reject non-BC emails at login
    def test_non_bc_email_login_raises(self):
        adapter = BCEmailAdapter()
        request = _add_middleware(RequestFactory().get("/"))
        sociallogin = self._make_sociallogin("user@gmail.com")
        with self.assertRaises(ImmediateHttpResponse):
            adapter.pre_social_login(request, sociallogin)


# ---------------------------------------------------------------------------
# CustomUser model tests
# ---------------------------------------------------------------------------


# Tests for the initial user model
class CustomUserModelTests(TestCase):
    """Verify CustomUser role field and helper properties."""

    # Test that new users default to Student role
    def test_default_role_is_student(self):
        user = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")
        self.assertEqual(user.role, Role.STUDENT)

    # Test that we can create an Admin user by specifying the role
    def test_is_bc_admin_false_for_student(self):
        user = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")
        self.assertFalse(user.is_bc_admin)

    # Test that is_bc_admin returns True for Admin users
    def test_is_bc_admin_true_for_admin(self):
        user = User.objects.create_user(username="adm", email="adm@bc.edu", password="test", role=Role.ADMIN)
        self.assertTrue(user.is_bc_admin)

    # Test that display_role returns "Student" for Student users
    def test_display_role_student(self):
        user = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")
        self.assertEqual(user.display_role, "Student")

    # Test that display_role returns "Admin" for Admin users
    def test_display_role_admin(self):
        user = User.objects.create_user(username="adm", email="adm@bc.edu", password="test", role=Role.ADMIN)
        self.assertEqual(user.display_role, "Admin")

    # Test the string representation of the user includes username and role
    def test_str_representation(self):
        user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")
        self.assertEqual(str(user), "eagle (Student)")


# ---------------------------------------------------------------------------
# Decorator / mixin tests
# ---------------------------------------------------------------------------


# Tests for the admin_required decorator
class AdminRequiredDecoratorTests(TestCase):
    """Verify admin_required decorator gates access correctly."""

    # Set up a protected view and test users
    def setUp(self):
        self.factory = RequestFactory()
        self.student = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")
        self.admin = User.objects.create_user(username="adm", email="adm@bc.edu", password="test", role=Role.ADMIN)

        @admin_required
        def protected_view(request):
            return HttpResponse("OK")

        self.protected_view = protected_view

    # Test that an admin user can access the protected view
    def test_admin_can_access(self):
        request = self.factory.get("/admin-view/")
        request.user = self.admin
        response = self.protected_view(request)
        self.assertEqual(response.status_code, 200)

    # Test that an unauthenticated user is redirected to login
    def test_student_gets_403(self):
        request = self.factory.get("/admin-view/")
        request.user = self.student
        with self.assertRaises(PermissionDenied):
            self.protected_view(request)


# ---------------------------------------------------------------------------
# Management command tests
# ---------------------------------------------------------------------------


# Tests for the set_user_role management command
class SetUserRoleCommandTests(TestCase):
    """Verify the set_user_role management command."""

    def setUp(self):
        self.user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")

    # Test promoting a user to admin
    def test_promote_to_admin(self):
        call_command("set_user_role", "eagle@bc.edu", "admin", stdout=StringIO())
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, Role.ADMIN)

    # Test demoting a user back to student
    def test_demote_to_student(self):
        self.user.role = Role.ADMIN
        self.user.save()
        call_command("set_user_role", "eagle@bc.edu", "student", stdout=StringIO())
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, Role.STUDENT)

    # Test that providing an invalid role raises an error
    def test_nonexistent_user_raises(self):
        with self.assertRaises(CommandError):
            call_command("set_user_role", "nobody@bc.edu", "admin", stderr=StringIO())


# ----------------------------------------------------------------------------
# View tests
# ----------------------------------------------------------------------------


# Basic smoke tests to ensure user-related pages render without error
class UserPageTests(TestCase):
    def test_user_pages_render(self):
        for path in ("/users/login/", "/users/profile/", "/users/dashboard/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
