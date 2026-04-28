from importlib import import_module

from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.signals import user_logged_in
from django.core.exceptions import ValidationError
from django.db import IntegrityError, migrations
from django.test import SimpleTestCase, TestCase
from django.test.client import RequestFactory
from django.utils import timezone

from ..legal import LEGAL_ACCEPTANCE_SESSION_KEY, set_pending_legal_acceptance
from ..models import AdminProfile, Role, StudentProfile, UserReport
from ..session_security import RECENT_AUTH_SESSION_KEY, get_recent_auth_at
from .helpers import User, add_middleware


class CustomUserModelTests(TestCase):
    def _complete_student_profile(self, user, **overrides):
        profile = user.student_profile
        defaults = {
            "preferred_name": user.first_name or user.username,
            "age": 20,
            "gender": "male",
            "institution_status": "undergraduate",
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

        self.assertEqual(user.display_role, "Platform Admin")

    def test_realtor_cannot_start_listing_conversations(self):
        user = User.objects.create_user(username="agent", email="agent@gmail.com", password="test")

        self.assertFalse(user.can_start_listing_conversations)
        self.assertTrue(user.has_listing_only_access)

    def test_student_can_browse_and_message(self):
        user = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")

        self.assertTrue(user.can_browse_marketplace)
        self.assertTrue(user.can_start_listing_conversations)

    def test_roommate_access_restriction_disables_roommate_matching(self):
        user = User.objects.create_user(username="restricted", email="restricted@bc.edu", password="test")
        user.profile_completed_at = timezone.now()
        user.roommate_access_restricted_at = timezone.now()
        user.save(update_fields=["profile_completed_at", "roommate_access_restricted_at"])

        self.assertFalse(user.can_use_roommate_matching)

    def test_active_warning_property_requires_unacknowledged_warning(self):
        user = User.objects.create_user(username="warned", email="warned@bc.edu", password="test")
        user.active_warning_message = "Warning"
        user.active_warning_issued_at = timezone.now()
        user.save(update_fields=["active_warning_message", "active_warning_issued_at"])

        self.assertTrue(user.has_active_warning)

        user.active_warning_acknowledged_at = timezone.now()
        user.save(update_fields=["active_warning_acknowledged_at"])

        self.assertFalse(user.has_active_warning)

    def test_moderator_permissions_are_scoped_to_moderation_work(self):
        user = User.objects.create_user(username="mod", email="mod@bc.edu", password="test", role=Role.MODERATOR)

        self.assertTrue(user.can_access_staff_console)
        self.assertTrue(user.can_manage_listing_moderation)
        self.assertTrue(user.can_manage_reports)
        self.assertTrue(user.can_browse_marketplace)
        self.assertFalse(user.can_manage_user_roles)
        self.assertFalse(user.can_manage_user_status)
        self.assertFalse(user.can_open_support_investigations)
        self.assertFalse(user.can_view_sensitive_user_data)
        self.assertFalse(user.can_start_listing_conversations)

    def test_support_permissions_are_scoped_to_sensitive_review_work(self):
        user = User.objects.create_user(username="support", email="support@bc.edu", password="test", role=Role.SUPPORT)

        self.assertTrue(user.can_access_staff_console)
        self.assertTrue(user.can_open_support_investigations)
        self.assertTrue(user.can_view_sensitive_user_data)
        self.assertTrue(user.can_browse_marketplace)
        self.assertFalse(user.can_manage_listing_moderation)
        self.assertFalse(user.can_manage_reports)
        self.assertFalse(user.can_manage_user_roles)
        self.assertFalse(user.can_manage_user_status)
        self.assertFalse(user.can_start_listing_conversations)

    def test_platform_admin_permissions_include_full_staff_access(self):
        user = User.objects.create_user(username="admin-2", email="admin-2@bc.edu", password="test", role=Role.ADMIN)

        self.assertTrue(user.can_access_staff_console)
        self.assertTrue(user.can_manage_listing_moderation)
        self.assertTrue(user.can_manage_reports)
        self.assertTrue(user.can_manage_user_roles)
        self.assertTrue(user.can_manage_user_status)
        self.assertTrue(user.can_open_support_investigations)
        self.assertTrue(user.can_view_sensitive_user_data)
        self.assertTrue(user.can_browse_marketplace)
        self.assertFalse(user.can_start_listing_conversations)

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

    def test_student_can_create_user_report_for_other_student(self):
        reporter = User.objects.create_user(username="reporter", email="reporter@bc.edu", password="test")
        reported_user = User.objects.create_user(username="target", email="target@bc.edu", password="test")
        reporter.profile_completed_at = timezone.now()
        reported_user.profile_completed_at = timezone.now()
        reporter.save(update_fields=["profile_completed_at"])
        reported_user.save(update_fields=["profile_completed_at"])

        report = UserReport.objects.create(
            reported_user=reported_user,
            reporter=reporter,
            reason=UserReport.REASON_SAFETY,
            details="Shared threatening messages.",
        )

        self.assertEqual(report.status, UserReport.STATUS_OPEN)

    def test_student_can_create_user_report_for_realtor_owner(self):
        reporter = User.objects.create_user(username="owner-reporter", email="owner-reporter@bc.edu", password="test")
        reported_user = User.objects.create_user(
            username="owner-target",
            email="owner-target@example.com",
            password="test",
        )

        report = UserReport.objects.create(
            reported_user=reported_user,
            reporter=reporter,
            reason=UserReport.REASON_INAPPROPRIATE,
            details="Posted inappropriate listing content.",
        )

        self.assertEqual(reported_user.role, Role.REALTOR)
        self.assertEqual(report.status, UserReport.STATUS_OPEN)

    def test_user_report_rejects_self_reporting(self):
        reporter = User.objects.create_user(username="self-report", email="self-report@bc.edu", password="test")
        reporter.profile_completed_at = timezone.now()
        reporter.save(update_fields=["profile_completed_at"])

        report = UserReport(
            reported_user=reporter,
            reporter=reporter,
            reason=UserReport.REASON_OTHER,
            details="test",
        )

        with self.assertRaises(ValidationError):
            report.full_clean()

    def test_user_report_rejects_non_student_reporters(self):
        reporter = User.objects.create_user(username="agent", email="agent@gmail.com", password="test")
        reported_user = User.objects.create_user(username="target-two", email="target-two@bc.edu", password="test")
        reported_user.profile_completed_at = timezone.now()
        reported_user.save(update_fields=["profile_completed_at"])

        report = UserReport(
            reported_user=reported_user,
            reporter=reporter,
            reason=UserReport.REASON_SCAM,
            details="Suspicious profile.",
        )

        with self.assertRaises(ValidationError):
            report.full_clean()

    def test_student_and_admin_profiles_are_created_for_matching_roles(self):
        student = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")
        admin = User.objects.create_user(username="adm", email="adm@bc.edu", password="test", role=Role.ADMIN)

        self.assertTrue(StudentProfile.objects.filter(user=student).exists())
        self.assertTrue(AdminProfile.objects.filter(user=admin).exists())

    def test_realtor_company_profile_requires_organization_name(self):
        realtor = User.objects.create_user(username="company-agent", email="company-agent@example.com", password="test")
        profile = realtor.admin_profile
        profile.preferred_name = "Company Agent"
        profile.bio = "Manages housing listings."
        profile.organization_type = "property_company"
        profile.organization_name = ""

        with self.assertRaisesMessage(ValidationError, "Enter the company or organization name."):
            profile.save()

    def test_new_student_profile_allows_blank_frequency_fields(self):
        user = User.objects.create_user(username="blank-profile", email="blank-profile@bc.edu", password="test")

        profile = user.student_profile

        self.assertIsNone(profile.drink)
        self.assertIsNone(profile.party)

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

    def test_student_profile_rejects_invalid_gender_choice(self):
        user = User.objects.create_user(username="invalid-student", email="invalid-student@bc.edu", password="test")
        profile = user.student_profile
        profile.gender = "woman"

        with self.assertRaises(ValidationError) as exc:
            profile.save()

        self.assertIn("Value 'woman' is not a valid choice.", exc.exception.message_dict["gender"][0])

    def test_admin_profile_rejects_invalid_gender_choice(self):
        user = User.objects.create_user(
            username="invalid-admin",
            email="invalid-admin@bc.edu",
            password="test",
            role=Role.ADMIN,
        )
        profile = user.admin_profile
        profile.gender = "woman"

        with self.assertRaises(ValidationError) as exc:
            profile.save()

        self.assertIn("Value 'woman' is not a valid choice.", exc.exception.message_dict["gender"][0])


class HistoricalMigrationTests(SimpleTestCase):
    def test_profile_ui_fields_use_custom_database_conversion_for_boolean_frequency_fields(self):
        migration_module = import_module("users.migrations.0014_profile_ui_fields")
        operations = migration_module.Migration.operations

        frequency_operation = next(op for op in operations if isinstance(op, migrations.SeparateDatabaseAndState))
        self.assertTrue(any(isinstance(op, migrations.RunPython) for op in frequency_operation.database_operations))

        state_altered_fields = {
            (op.model_name, op.name)
            for op in frequency_operation.state_operations
            if isinstance(op, migrations.AlterField)
        }
        top_level_altered_fields = {
            (op.model_name, op.name) for op in operations if isinstance(op, migrations.AlterField)
        }

        self.assertIn(("studentprofile", "drink"), state_altered_fields)
        self.assertIn(("studentprofile", "party"), state_altered_fields)
        self.assertNotIn(("studentprofile", "drink"), top_level_altered_fields)
        self.assertNotIn(("studentprofile", "party"), top_level_altered_fields)

    def test_follow_up_migration_repairs_not_null_frequency_columns(self):
        migration_module = import_module("users.migrations.0021_studentprofile_frequency_fields_nullable")
        operations = migration_module.Migration.operations

        self.assertEqual(len(operations), 1)
        self.assertIsInstance(operations[0], migrations.RunPython)
