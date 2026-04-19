from importlib import import_module

from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.signals import user_logged_in
from django.db import IntegrityError, migrations
from django.test import SimpleTestCase, TestCase
from django.test.client import RequestFactory
from django.utils import timezone

from ..legal import LEGAL_ACCEPTANCE_SESSION_KEY, set_pending_legal_acceptance
from ..models import AdminProfile, Role, StudentProfile
from ..session_security import RECENT_AUTH_SESSION_KEY, get_recent_auth_at
from .helpers import User, add_middleware


class CustomUserModelTests(TestCase):
    def _complete_student_profile(self, user, **overrides):
        profile = user.student_profile
        defaults = {
            "preferred_name": user.first_name or user.username,
            "age": 20,
            "gender": "male",
            "major": "Computer Science",
            "bio": "Easygoing roommate.",
            "messy_level": 3,
            "guest_level": 3,
            "bedtime": 22,
            "noise_level": 3,
            "drink": 2,
            "party": 2,
        }
        defaults.update(overrides)
        for field_name, value in defaults.items():
            setattr(profile, field_name, value)
        profile.save()
        user.profile_completed_at = timezone.now()
        user.save(update_fields=["profile_completed_at"])
        return profile

    def _complete_admin_profile(self, user, **overrides):
        profile = user.admin_profile
        defaults = {
            "preferred_name": user.first_name or user.username,
            "bio": "Manages housing listings.",
        }
        defaults.update(overrides)
        for field_name, value in defaults.items():
            setattr(profile, field_name, value)
        profile.save()
        user.profile_completed_at = timezone.now()
        user.save(update_fields=["profile_completed_at"])
        return profile

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

    def test_student_profile_survives_admin_promotion(self):
        user = User.objects.create_user(username="stu-profile", email="stu-profile@bc.edu", password="test")
        student_profile = self._complete_student_profile(user, preferred_name="Taylor", bio="Student bio.")
        student_profile_id = student_profile.id
        completed_at = user.profile_completed_at

        user.set_admin_access(True)
        user.save(update_fields=["role"])
        user.refresh_from_db()

        self.assertEqual(user.role, Role.ADMIN)
        self.assertTrue(StudentProfile.objects.filter(user=user, pk=student_profile_id).exists())
        self.assertEqual(user.student_profile.preferred_name, "Taylor")
        self.assertEqual(user.student_profile.bio, "Student bio.")
        self.assertEqual(user.admin_profile.preferred_name, "Taylor")
        self.assertEqual(user.admin_profile.bio, "Student bio.")
        self.assertEqual(user.profile_completed_at, completed_at)

    def test_restored_student_reuses_preserved_student_profile(self):
        user = User.objects.create_user(username="stu-restore", email="stu-restore@bc.edu", password="test")
        student_profile = self._complete_student_profile(user, preferred_name="Morgan")

        user.set_admin_access(True)
        user.save(update_fields=["role"])
        user.set_admin_access(False)
        user.save(update_fields=["role"])
        user.refresh_from_db()

        self.assertEqual(user.role, Role.STUDENT)
        self.assertEqual(user.student_profile.id, student_profile.id)
        self.assertEqual(user.student_profile.preferred_name, "Morgan")
        self.assertIsNotNone(user.profile_completed_at)

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

    def test_database_constraint_rejects_invalid_role_updates(self):
        user = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")

        with self.assertRaises(IntegrityError):
            User.objects.filter(pk=user.pk).update(role="broken")

    def test_student_and_admin_profiles_are_created_for_matching_roles(self):
        student = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")
        admin = User.objects.create_user(username="adm", email="adm@bc.edu", password="test", role=Role.ADMIN)

        self.assertTrue(StudentProfile.objects.filter(user=student).exists())
        self.assertTrue(AdminProfile.objects.filter(user=admin).exists())

    def test_realtor_role_transition_moves_to_admin_profile(self):
        user = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")

        self.assertTrue(StudentProfile.objects.filter(user=user).exists())

        user.email = "stu@gmail.com"
        user.save(update_fields=["email"])

        self.assertFalse(StudentProfile.objects.filter(user=user).exists())
        self.assertTrue(AdminProfile.objects.filter(user=user).exists())

    def test_realtor_role_transition_clears_completion(self):
        user = User.objects.create_user(username="stu-realtor", email="stu-realtor@bc.edu", password="test")
        self._complete_student_profile(user)

        user.email = "stu-realtor@gmail.com"
        user.save(update_fields=["email"])
        user.refresh_from_db()

        self.assertEqual(user.role, Role.REALTOR)
        self.assertFalse(StudentProfile.objects.filter(user=user).exists())
        self.assertTrue(AdminProfile.objects.filter(user=user).exists())
        self.assertIsNone(user.profile_completed_at)

    def test_student_role_restoration_creates_blank_profile_when_previous_student_profile_was_removed(self):
        user = User.objects.create_user(username="stu-return", email="stu-return@bc.edu", password="test")
        self._complete_student_profile(user, preferred_name="Riley")

        user.email = "stu-return@gmail.com"
        user.save(update_fields=["email"])
        user.refresh_from_db()
        self.assertFalse(StudentProfile.objects.filter(user=user).exists())

        user.email = "stu-return@bc.edu"
        user.save(update_fields=["email"])
        user.refresh_from_db()

        self.assertEqual(user.role, Role.STUDENT)
        self.assertTrue(StudentProfile.objects.filter(user=user).exists())
        self.assertEqual(user.student_profile.preferred_name, "")
        self.assertEqual(user.student_profile.bio, "")
        self.assertIsNone(user.profile_completed_at)

    def test_str_representation(self):
        user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")

        self.assertEqual(str(user), "eagle (Student)")

    def test_google_avatar_url_uses_google_socialaccount_picture(self):
        user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")
        SocialAccount.objects.create(
            user=user,
            provider="google",
            uid="google-eagle",
            extra_data={"picture": "https://example.com/avatar.png"},
        )

        self.assertEqual(user.google_avatar_url, "https://example.com/avatar.png")

    def test_google_avatar_url_rejects_non_http_values(self):
        user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")
        SocialAccount.objects.create(
            user=user,
            provider="google",
            uid="google-unsafe-avatar",
            extra_data={"picture": "javascript:alert('xss')"},
        )

        self.assertEqual(user.google_avatar_url, "")

    def test_google_avatar_url_rejects_http_values(self):
        user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")
        SocialAccount.objects.create(
            user=user,
            provider="google",
            uid="google-http-avatar",
            extra_data={"picture": "http://example.com/avatar.png"},
        )

        self.assertEqual(user.google_avatar_url, "")

    def test_avatar_url_falls_back_to_profile_image_url(self):
        user = User.objects.create_user(
            username="eagle",
            email="eagle@bc.edu",
            password="test",
            profile_image_url="https://example.com/fallback-avatar.jpg",
        )

        self.assertEqual(user.avatar_url, "https://example.com/fallback-avatar.jpg")

    def test_legal_acceptance_is_persisted_on_login(self):
        user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")
        request = add_middleware(RequestFactory().get("/accounts/google/login/"))
        set_pending_legal_acceptance(request, accepted_at=timezone.now())

        user_logged_in.send(sender=user.__class__, request=request, user=user)
        user.refresh_from_db()

        self.assertIsNotNone(user.terms_accepted_at)
        self.assertIsNotNone(user.privacy_accepted_at)
        self.assertTrue(user.has_current_legal_acceptance)
        self.assertIn(RECENT_AUTH_SESSION_KEY, request.session)
        self.assertNotIn(LEGAL_ACCEPTANCE_SESSION_KEY, request.session)
        self.assertIsNotNone(get_recent_auth_at(request))

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


class HistoricalMigrationTests(SimpleTestCase):
    def test_profile_ui_fields_data_backfill_runs_before_type_casts(self):
        migration_module = import_module("users.migrations.0014_profile_ui_fields")
        operations = migration_module.Migration.operations

        runpython_index = next(index for index, op in enumerate(operations) if isinstance(op, migrations.RunPython))
        drink_alter_index = next(
            index
            for index, op in enumerate(operations)
            if isinstance(op, migrations.AlterField) and op.model_name == "studentprofile" and op.name == "drink"
        )
        party_alter_index = next(
            index
            for index, op in enumerate(operations)
            if isinstance(op, migrations.AlterField) and op.model_name == "studentprofile" and op.name == "party"
        )

        self.assertLess(runpython_index, drink_alter_index)
        self.assertLess(runpython_index, party_alter_index)
