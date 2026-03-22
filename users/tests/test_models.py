from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.signals import user_logged_in
from django.test import TestCase
from django.test.client import RequestFactory
from django.utils import timezone

from ..legal import set_pending_legal_acceptance
from ..models import AdminProfile, Role, StudentProfile
from .helpers import User, add_middleware


class CustomUserModelTests(TestCase):
    def test_default_role_is_student(self):
        user = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")

        self.assertEqual(user.role, Role.STUDENT)

    def test_external_email_defaults_to_realtor(self):
        user = User.objects.create_user(username="agent", email="agent@gmail.com", password="test")

        self.assertEqual(user.role, Role.REALTOR)

    def test_email_field_is_unique(self):
        self.assertTrue(User._meta.get_field("email").unique)

    def test_email_is_required_on_save(self):
        user = User(username="noemail")

        with self.assertRaisesMessage(ValueError, "Users must have an email address."):
            user.save()

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

    def test_realtor_cannot_start_listing_conversations(self):
        user = User.objects.create_user(username="agent", email="agent@gmail.com", password="test")

        self.assertFalse(user.can_start_listing_conversations)
        self.assertTrue(user.has_listing_only_access)

    def test_student_can_browse_and_message(self):
        user = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")

        self.assertTrue(user.can_browse_marketplace)
        self.assertTrue(user.can_start_listing_conversations)

    def test_set_admin_access_false_restores_email_based_role(self):
        user = User.objects.create_user(username="agent", email="agent@gmail.com", password="test", role=Role.ADMIN)

        user.set_admin_access(False)
        user.save(update_fields=["role"])
        user.refresh_from_db()

        self.assertEqual(user.role, Role.REALTOR)

    def test_promoting_user_to_admin_creates_admin_profile(self):
        user = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")

        user.set_admin_access(True)
        user.save(update_fields=["role"])
        user.refresh_from_db()

        self.assertEqual(user.role, Role.ADMIN)
        self.assertTrue(hasattr(user, "admin_profile"))

    def test_partial_email_save_updates_role_policy(self):
        user = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")

        user.email = "stu@gmail.com"
        user.save(update_fields=["email"])
        user.refresh_from_db()

        self.assertEqual(user.email, "stu@gmail.com")
        self.assertEqual(user.role, Role.REALTOR)

    def test_partial_role_save_preserves_admin_role(self):
        user = User.objects.create_user(username="agent", email="agent@gmail.com", password="test")

        user.set_admin_access(True)
        user.save(update_fields=["role"])
        user.refresh_from_db()

        self.assertEqual(user.role, Role.ADMIN)

    def test_student_and_admin_profiles_are_created_for_matching_roles(self):
        student = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")
        admin = User.objects.create_user(username="adm", email="adm@bc.edu", password="test", role=Role.ADMIN)

        self.assertTrue(StudentProfile.objects.filter(user=student).exists())
        self.assertTrue(AdminProfile.objects.filter(user=admin).exists())

    def test_realtor_role_transition_removes_role_specific_profiles(self):
        user = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")

        self.assertTrue(StudentProfile.objects.filter(user=user).exists())

        user.email = "stu@gmail.com"
        user.save(update_fields=["email"])

        self.assertFalse(StudentProfile.objects.filter(user=user).exists())
        self.assertFalse(AdminProfile.objects.filter(user=user).exists())

    def test_str_representation(self):
        user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")

        self.assertEqual(str(user), "eagle (Student)")

    def test_legal_acceptance_is_persisted_on_login(self):
        user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")
        request = add_middleware(RequestFactory().get("/accounts/google/login/"))
        set_pending_legal_acceptance(request, accepted_at=timezone.now())

        user_logged_in.send(sender=user.__class__, request=request, user=user)
        user.refresh_from_db()

        self.assertIsNotNone(user.terms_accepted_at)
        self.assertIsNotNone(user.privacy_accepted_at)
        self.assertTrue(user.has_current_legal_acceptance)

    def test_google_profile_image_is_synced_on_login(self):
        user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")
        SocialAccount.objects.create(
            user=user,
            provider="google",
            uid="google-user-2",
            extra_data={
                "email": "eagle@bc.edu",
                "email_verified": True,
                "picture": "https://example.com/google-avatar.jpg",
            },
        )

        request = add_middleware(RequestFactory().get("/accounts/google/login/"))
        user_logged_in.send(sender=user.__class__, request=request, user=user)
        user.refresh_from_db()

        self.assertEqual(user.profile_image_url, "https://example.com/google-avatar.jpg")
