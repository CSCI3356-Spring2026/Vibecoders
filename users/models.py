import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

from roommates import models as roommate_models

from .profile_images import profile_image_url_from_data
from .validators import validate_user_upload


def _normalize_email_address(email):
    return (email or "").strip().lower()


def _email_domain(email):
    normalized_email = _normalize_email_address(email)
    if "@" not in normalized_email:
        return ""
    return normalized_email.rsplit("@", 1)[1]


def _document_library_limit_message(limit):
    noun = "file" if limit == 1 else "files"
    return f"You can store up to {limit} {noun} in your document library."


class Role(models.TextChoices):
    STUDENT = "student", "Student"
    REALTOR = "realtor", "Realtor"
    MODERATOR = "moderator", "Moderator"
    SUPPORT = "support", "Support"
    ADMIN = "platform_admin", "Platform Admin"


STAFF_ROLE_VALUES = {
    Role.MODERATOR,
    Role.SUPPORT,
    Role.ADMIN,
}
ADMIN_PROFILE_COPY_FIELDS = ("preferred_name", "age", "gender", "gender_other", "bio")
USER_REPORT_STATUS_OPEN = "open"
USER_REPORT_STATUS_IN_REVIEW = "in_review"
USER_REPORT_STATUS_RESOLVED = "resolved"
USER_REPORT_STATUS_DISMISSED = "dismissed"
USER_REPORT_STATUS_CHOICES = [
    (USER_REPORT_STATUS_OPEN, "Open"),
    (USER_REPORT_STATUS_IN_REVIEW, "In review"),
    (USER_REPORT_STATUS_RESOLVED, "Resolved"),
    (USER_REPORT_STATUS_DISMISSED, "Dismissed"),
]
USER_REPORT_REASON_SAFETY = "safety"
USER_REPORT_REASON_HARASSMENT = "harassment"
USER_REPORT_REASON_SPAM = "spam"
USER_REPORT_REASON_IMPERSONATION = "impersonation"
USER_REPORT_REASON_SCAM = "scam"
USER_REPORT_REASON_OTHER = "other"
USER_REPORT_REASON_CHOICES = [
    (USER_REPORT_REASON_SAFETY, "Safety concern"),
    (USER_REPORT_REASON_HARASSMENT, "Harassment or abusive behavior"),
    (USER_REPORT_REASON_SPAM, "Spam"),
    (USER_REPORT_REASON_IMPERSONATION, "Impersonation"),
    (USER_REPORT_REASON_SCAM, "Scam or suspicious behavior"),
    (USER_REPORT_REASON_OTHER, "Other"),
]
USER_REPORT_STATUS_VALUES = tuple(value for value, _ in USER_REPORT_STATUS_CHOICES)
USER_REPORT_REASON_VALUES = tuple(value for value, _ in USER_REPORT_REASON_CHOICES)
USER_REPORT_UPDATE_ACTION_NOTE = "note"
USER_REPORT_UPDATE_ACTION_IN_REVIEW = "in_review"
USER_REPORT_UPDATE_ACTION_DISMISSED = "dismissed"
USER_REPORT_UPDATE_ACTION_RESOLVED = "resolved"
USER_REPORT_UPDATE_ACTION_REOPENED = "reopened"
USER_REPORT_UPDATE_ACTION_WARNED = "warned"
USER_REPORT_UPDATE_ACTION_ROOMMATE_RESTRICTED = "roommate_restricted"
USER_REPORT_UPDATE_ACTION_USER_DEACTIVATED = "user_deactivated"
USER_REPORT_UPDATE_ACTION_CHOICES = [
    (USER_REPORT_UPDATE_ACTION_NOTE, "Comment added"),
    (USER_REPORT_UPDATE_ACTION_IN_REVIEW, "Moved to in review"),
    (USER_REPORT_UPDATE_ACTION_DISMISSED, "Dismissed"),
    (USER_REPORT_UPDATE_ACTION_RESOLVED, "Resolved"),
    (USER_REPORT_UPDATE_ACTION_REOPENED, "Reopened"),
    (USER_REPORT_UPDATE_ACTION_WARNED, "User warned"),
    (USER_REPORT_UPDATE_ACTION_ROOMMATE_RESTRICTED, "Roommate access restricted"),
    (USER_REPORT_UPDATE_ACTION_USER_DEACTIVATED, "Account deactivated"),
]


def _choice_values(choices):
    return tuple(value for value, _label in choices)


def _optional_choice_constraint(field_name, choices):
    return Q(**{f"{field_name}__in": _choice_values(choices)}) | Q(**{f"{field_name}": ""})


def _optional_positive_choice_constraint(field_name, choices):
    return Q(**{f"{field_name}__in": _choice_values(choices)}) | Q(**{f"{field_name}__isnull": True})


def _submission_context_changed(instance, *, identity_fields):
    if instance._state.adding or not instance.pk:
        return True

    original_values = type(instance).objects.filter(pk=instance.pk).values(*identity_fields).first()
    if original_values is None:
        return True
    return any(original_values[field_name] != getattr(instance, field_name) for field_name in identity_fields)


STUDENT_PROFILE_GENDER_CHOICES = [
    ("male", "Male"),
    ("female", "Female"),
    ("other", "Other"),
    ("prefer_not", "Prefer not to say"),
]
STUDENT_PROFILE_MESSY_LEVEL_CHOICES = [
    (1, "Extremely messy"),
    (2, "Messy"),
    (3, "Neutral"),
    (4, "Clean"),
    (5, "Extremely clean"),
]
STUDENT_PROFILE_GUEST_LEVEL_CHOICES = [
    (1, "Never"),
    (2, "Rarely"),
    (3, "Sometimes"),
    (4, "Often"),
    (5, "Everyday"),
]
STUDENT_PROFILE_NOISE_LEVEL_CHOICES = [
    (1, "Silent"),
    (2, "Quiet"),
    (3, "Neutral"),
    (4, "Loud"),
    (5, "Very loud"),
]
STUDENT_PROFILE_FREQUENCY_CHOICES = [
    (1, "Never"),
    (2, "Rarely"),
    (3, "Sometimes"),
    (4, "Often"),
    (5, "Daily"),
]


class CustomUser(AbstractUser):
    """Custom user model with role-aware marketplace access."""

    REQUIRED_FIELDS = ["email"]
    email = models.EmailField("email address", unique=True)
    profile_image_url = models.URLField(blank=True, max_length=500)
    uploaded_avatar = models.ImageField(upload_to="avatars/", blank=True)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT,
        db_index=True,
        help_text="Access level for the housing platform.",
    )
    profile_completed_at = models.DateTimeField(null=True, blank=True)
    active_warning_message = models.CharField(max_length=500, blank=True)
    active_warning_issued_at = models.DateTimeField(null=True, blank=True)
    active_warning_issued_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="warnings_issued",
    )
    active_warning_acknowledged_at = models.DateTimeField(null=True, blank=True)
    roommate_access_restricted_at = models.DateTimeField(null=True, blank=True)
    roommate_access_restricted_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="roommate_access_restrictions_applied",
    )
    roommate_access_restriction_reason = models.CharField(max_length=500, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    deactivated_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deactivated_users",
    )
    deactivation_reason = models.CharField(max_length=255, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    privacy_accepted_at = models.DateTimeField(null=True, blank=True)
    legal_policy_version = models.CharField(max_length=32, blank=True)

    class Meta(AbstractUser.Meta):
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=[role.value for role in Role]),
                name="customuser_role_valid",
            ),
        ]

    @staticmethod
    def normalize_email_address(email):
        return _normalize_email_address(email)

    @classmethod
    def student_email_domains(cls):
        configured_domains = getattr(settings, "STUDENT_EMAIL_DOMAINS", ["bc.edu"])
        return {domain.lower() for domain in configured_domains}

    @classmethod
    def normalize_role_value(cls, role):
        role_value = getattr(role, "value", role) or ""
        if role_value == "admin":
            return Role.ADMIN
        return role_value

    @classmethod
    def is_staff_role_value(cls, role):
        return cls.normalize_role_value(role) in STAFF_ROLE_VALUES

    @classmethod
    def default_role_for_email(cls, email):
        if _email_domain(email) in cls.student_email_domains():
            return Role.STUDENT
        return Role.REALTOR

    @classmethod
    def username_from_email(cls, email):
        username_field = cls._meta.get_field("username")
        max_length = username_field.max_length
        local_part = (email or "").strip().lower().split("@", 1)[0]
        normalized = re.sub(r"[^a-z0-9._-]+", "-", local_part).strip("._-")
        base = (normalized or "user")[:max_length]
        candidate = base
        suffix = 2

        while cls._default_manager.filter(username=candidate).exists():
            suffix_token = f"-{suffix}"
            candidate = f"{base[: max_length - len(suffix_token)]}{suffix_token}"
            suffix += 1

        return candidate

    @staticmethod
    def _avatar_url_from_extra_data(extra_data):
        return profile_image_url_from_data(extra_data)

    def _google_social_account(self):
        if not self.pk:
            return None

        prefetched_accounts = getattr(self, "_prefetched_objects_cache", {}).get("socialaccount_set")
        if prefetched_accounts is not None:
            for account in prefetched_accounts:
                if account.provider == "google":
                    return account
            return None

        return self.socialaccount_set.filter(provider="google").only("extra_data").first()

    @property
    def email_domain(self):
        return _email_domain(self.email)

    @property
    def display_name(self):
        return self.get_full_name() or self.username or self.email

    @property
    def google_avatar_url(self):
        account = self._google_social_account()
        if not account:
            return ""
        return self._avatar_url_from_extra_data(getattr(account, "extra_data", None))

    @property
    def avatar_url(self):
        if self.uploaded_avatar:
            return self.uploaded_avatar.url
        return self.google_avatar_url or self.profile_image_url or ""

    @property
    def has_verified_student_email(self):
        return self.email_domain in self.student_email_domains()

    @property
    def has_edu_email(self):
        return self.email_domain.endswith(".edu")

    @property
    def is_bc_admin(self):
        return self.is_platform_admin

    @property
    def is_student(self):
        return self.role == Role.STUDENT

    @property
    def is_realtor(self):
        return self.role == Role.REALTOR

    @property
    def is_moderator(self):
        return self.role == Role.MODERATOR

    @property
    def is_support(self):
        return self.role == Role.SUPPORT

    @property
    def is_platform_admin(self):
        return self.role == Role.ADMIN

    @property
    def is_staff_role(self):
        from .permissions import is_staff_role

        return is_staff_role(self)

    @property
    def can_access_admin_panel(self):
        return self.can_access_staff_console

    @property
    def can_access_staff_console(self):
        from .permissions import can_access_staff_console

        return can_access_staff_console(self)

    @property
    def can_manage_listing_moderation(self):
        from .permissions import can_manage_listing_moderation

        return can_manage_listing_moderation(self)

    @property
    def can_manage_reports(self):
        from .permissions import can_manage_reports

        return can_manage_reports(self)

    @property
    def can_manage_user_status(self):
        from .permissions import can_manage_user_status

        return can_manage_user_status(self)

    @property
    def can_manage_user_roles(self):
        from .permissions import can_manage_user_roles

        return can_manage_user_roles(self)

    @property
    def can_open_support_investigations(self):
        from .permissions import can_open_support_investigations

        return can_open_support_investigations(self)

    @property
    def can_view_sensitive_user_data(self):
        from .permissions import can_view_sensitive_user_data

        return can_view_sensitive_user_data(self)

    @property
    def can_browse_marketplace(self):
        from .permissions import can_browse_marketplace

        return can_browse_marketplace(self)

    @property
    def can_start_listing_conversations(self):
        from .permissions import can_start_listing_conversations

        return can_start_listing_conversations(self)

    @property
    def can_use_roommate_matching(self):
        from .permissions import can_use_roommate_matching

        return can_use_roommate_matching(self)

    @property
    def has_roommate_access_restriction(self):
        return self.roommate_access_restricted_at is not None

    @property
    def has_active_warning(self):
        return bool(
            self.active_warning_message
            and self.active_warning_issued_at
            and self.active_warning_acknowledged_at is None
        )

    @property
    def has_listing_only_access(self):
        from .permissions import has_listing_only_access

        return has_listing_only_access(self)

    @property
    def display_role(self):
        return self.get_role_display()

    @property
    def has_current_legal_acceptance(self):
        return (
            self.terms_accepted_at is not None
            and self.privacy_accepted_at is not None
            and self.legal_policy_version == getattr(settings, "LEGAL_DOCUMENT_VERSION", "")
        )

    @property
    def avatar_initial(self):
        source = self.get_full_name() or self.username or self.email or ""
        return source[:1].upper()

    def apply_email_role_policy(self):
        if not self.is_staff_role_value(self.role):
            self.role = self.default_role_for_email(self.email)

    def set_admin_access(self, enabled):
        self.role = Role.ADMIN if enabled else self.default_role_for_email(self.email)

    def restore_default_access_role(self):
        self.role = self.default_role_for_email(self.email)

    def set_staff_role(self, role):
        normalized_role = self.normalize_role_value(role)
        if normalized_role not in STAFF_ROLE_VALUES:
            raise ValueError("Staff role required.")
        self.role = normalized_role

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)

        original_email = self.email
        original_role = self.normalize_role_value(self.role)
        normalized_email = self.normalize_email_address(self.email)
        if not normalized_email:
            raise ValueError("Users must have an email address.")
        self.email = normalized_email
        self.role = self.normalize_role_value(self.role)
        self.apply_email_role_policy()
        if update_fields is not None:
            if self.email != original_email:
                update_fields.add("email")
            if self.role != original_role:
                update_fields.add("role")
            kwargs["update_fields"] = update_fields
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.display_role})"


class StudentProfile(models.Model):
    GENDER_CHOICES = STUDENT_PROFILE_GENDER_CHOICES
    MESSY_LEVEL_CHOICES = STUDENT_PROFILE_MESSY_LEVEL_CHOICES
    GUEST_LEVEL_CHOICES = STUDENT_PROFILE_GUEST_LEVEL_CHOICES
    NOISE_LEVEL_CHOICES = STUDENT_PROFILE_NOISE_LEVEL_CHOICES
    FREQUENCY_CHOICES = STUDENT_PROFILE_FREQUENCY_CHOICES

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_profile")
    preferred_name = models.CharField(max_length=120, blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=24, blank=True, choices=GENDER_CHOICES)
    gender_other = models.CharField(max_length=120, blank=True)
    major = models.CharField(max_length=120, blank=True)
    bio = models.CharField(max_length=300, blank=True)
    messy_level = models.PositiveSmallIntegerField(null=True, blank=True, choices=MESSY_LEVEL_CHOICES)
    guest_level = models.PositiveSmallIntegerField(null=True, blank=True, choices=GUEST_LEVEL_CHOICES)
    bedtime = models.PositiveSmallIntegerField(null=True, blank=True)
    noise_level = models.PositiveSmallIntegerField(null=True, blank=True, choices=NOISE_LEVEL_CHOICES)
    smoke = models.BooleanField(default=False)
    drink = models.PositiveSmallIntegerField(null=True, blank=True, choices=FREQUENCY_CHOICES)
    party = models.PositiveSmallIntegerField(null=True, blank=True, choices=FREQUENCY_CHOICES)
    pets = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(age__isnull=True) | (Q(age__gte=16) & Q(age__lte=99)),
                name="student_profile_age_valid",
            ),
            models.CheckConstraint(
                condition=_optional_choice_constraint("gender", STUDENT_PROFILE_GENDER_CHOICES),
                name="student_profile_gender_valid",
            ),
            models.CheckConstraint(
                condition=_optional_positive_choice_constraint("messy_level", STUDENT_PROFILE_MESSY_LEVEL_CHOICES),
                name="student_profile_messy_level_valid",
            ),
            models.CheckConstraint(
                condition=_optional_positive_choice_constraint("guest_level", STUDENT_PROFILE_GUEST_LEVEL_CHOICES),
                name="student_profile_guest_level_valid",
            ),
            models.CheckConstraint(
                condition=Q(bedtime__isnull=True) | (Q(bedtime__gte=0) & Q(bedtime__lte=23)),
                name="student_profile_bedtime_valid",
            ),
            models.CheckConstraint(
                condition=_optional_positive_choice_constraint("noise_level", STUDENT_PROFILE_NOISE_LEVEL_CHOICES),
                name="student_profile_noise_level_valid",
            ),
            models.CheckConstraint(
                condition=_optional_positive_choice_constraint("drink", STUDENT_PROFILE_FREQUENCY_CHOICES),
                name="student_profile_drink_valid",
            ),
            models.CheckConstraint(
                condition=_optional_positive_choice_constraint("party", STUDENT_PROFILE_FREQUENCY_CHOICES),
                name="student_profile_party_valid",
            ),
        ]

    def clean(self):
        super().clean()
        if self.gender == "other" and not self.gender_other:
            raise ValidationError({"gender_other": "Please share your gender or choose another option."})
        if self.gender != "other":
            self.gender_other = ""

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"StudentProfile({self.user.username})"


class AdminProfile(models.Model):
    GENDER_CHOICES = STUDENT_PROFILE_GENDER_CHOICES

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="admin_profile")
    preferred_name = models.CharField(max_length=120, blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=24, blank=True, choices=GENDER_CHOICES)
    gender_other = models.CharField(max_length=120, blank=True)
    bio = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(age__isnull=True) | (Q(age__gte=16) & Q(age__lte=99)),
                name="admin_profile_age_valid",
            ),
            models.CheckConstraint(
                condition=_optional_choice_constraint("gender", STUDENT_PROFILE_GENDER_CHOICES),
                name="admin_profile_gender_valid",
            ),
        ]

    def clean(self):
        super().clean()
        if self.gender == "other" and not self.gender_other:
            raise ValidationError({"gender_other": "Please share your gender or choose another option."})
        if self.gender != "other":
            self.gender_other = ""

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"AdminProfile({self.user.username})"


FavoriteRoommate = roommate_models.FavoriteRoommate
RoommateGroupInvite = roommate_models.RoommateGroupInvite
RoommateGroupInviteApproval = roommate_models.RoommateGroupInviteApproval


class UserReport(models.Model):
    STATUS_OPEN = USER_REPORT_STATUS_OPEN
    STATUS_IN_REVIEW = USER_REPORT_STATUS_IN_REVIEW
    STATUS_RESOLVED = USER_REPORT_STATUS_RESOLVED
    STATUS_DISMISSED = USER_REPORT_STATUS_DISMISSED
    REASON_SAFETY = USER_REPORT_REASON_SAFETY
    REASON_HARASSMENT = USER_REPORT_REASON_HARASSMENT
    REASON_SPAM = USER_REPORT_REASON_SPAM
    REASON_IMPERSONATION = USER_REPORT_REASON_IMPERSONATION
    REASON_SCAM = USER_REPORT_REASON_SCAM
    REASON_OTHER = USER_REPORT_REASON_OTHER

    STATUS_CHOICES = USER_REPORT_STATUS_CHOICES
    REASON_CHOICES = USER_REPORT_REASON_CHOICES

    reported_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports_received",
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_reports",
    )
    reason = models.CharField(max_length=24, choices=REASON_CHOICES)
    details = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_reports_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(reason__in=USER_REPORT_REASON_VALUES),
                name="user_report_reason_valid",
            ),
            models.CheckConstraint(
                condition=Q(status__in=USER_REPORT_STATUS_VALUES),
                name="user_report_status_valid",
            ),
            models.UniqueConstraint(
                fields=["reported_user", "reporter"],
                condition=Q(status__in=[USER_REPORT_STATUS_OPEN, USER_REPORT_STATUS_IN_REVIEW]),
                name="user_report_active_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "created_at"], name="user_report_status_idx"),
            models.Index(fields=["reported_user", "status"], name="user_report_target_idx"),
            models.Index(fields=["reporter", "created_at"], name="user_report_reporter_idx"),
        ]

    @property
    def is_closed(self):
        return self.status in {self.STATUS_RESOLVED, self.STATUS_DISMISSED}

    def clean(self):
        super().clean()
        if _submission_context_changed(self, identity_fields=("reported_user_id", "reporter_id")):
            user_model = get_user_model()
            reporter_is_student = user_model._default_manager.filter(pk=self.reporter_id, role=Role.STUDENT).exists()
            if self.reporter_id and not reporter_is_student:
                raise ValidationError({"details": "Only student accounts can report users."})
            if self.reported_user_id and self.reported_user_id == self.reporter_id:
                raise ValidationError({"details": "You cannot report your own account."})
            reported_user_is_student = user_model._default_manager.filter(
                pk=self.reported_user_id,
                role=Role.STUDENT,
                is_active=True,
                profile_completed_at__isnull=False,
            ).exists()
            if self.reported_user_id and not reported_user_is_student:
                raise ValidationError({"details": "Only active student roommate profiles can be reported."})
        if self.status in {self.STATUS_RESOLVED, self.STATUS_DISMISSED} and not (self.resolution_notes or "").strip():
            raise ValidationError({"resolution_notes": "Add resolution notes before closing a report."})

    def mark_status(self, *, status, reviewer, resolution_notes=""):
        self.status = status
        cleaned_notes = resolution_notes.strip()
        if status in {self.STATUS_RESOLVED, self.STATUS_DISMISSED} and not cleaned_notes:
            raise ValidationError({"resolution_notes": "Add resolution notes before closing a report."})
        if status == self.STATUS_OPEN:
            self.reviewed_by = None
            self.reviewed_at = None
            self.resolution_notes = ""
            return
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.resolution_notes = cleaned_notes

    def activity_action_for_status(self, status):
        if status == self.STATUS_OPEN:
            return USER_REPORT_UPDATE_ACTION_REOPENED
        if status == self.STATUS_IN_REVIEW:
            return USER_REPORT_UPDATE_ACTION_IN_REVIEW
        if status == self.STATUS_DISMISSED:
            return USER_REPORT_UPDATE_ACTION_DISMISSED
        if status == self.STATUS_RESOLVED:
            return USER_REPORT_UPDATE_ACTION_RESOLVED
        return USER_REPORT_UPDATE_ACTION_NOTE

    def add_update(self, *, actor, note="", action=""):
        return UserReportUpdate.objects.create(
            report=self,
            actor=actor,
            action=action or self.activity_action_for_status(self.status),
            note=(note or "").strip(),
        )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"User report {self.id} for user {self.reported_user_id}"


class UserReportUpdate(models.Model):
    ACTION_NOTE = USER_REPORT_UPDATE_ACTION_NOTE
    ACTION_IN_REVIEW = USER_REPORT_UPDATE_ACTION_IN_REVIEW
    ACTION_DISMISSED = USER_REPORT_UPDATE_ACTION_DISMISSED
    ACTION_RESOLVED = USER_REPORT_UPDATE_ACTION_RESOLVED
    ACTION_REOPENED = USER_REPORT_UPDATE_ACTION_REOPENED
    ACTION_WARNED = USER_REPORT_UPDATE_ACTION_WARNED
    ACTION_ROOMMATE_RESTRICTED = USER_REPORT_UPDATE_ACTION_ROOMMATE_RESTRICTED
    ACTION_USER_DEACTIVATED = USER_REPORT_UPDATE_ACTION_USER_DEACTIVATED

    ACTION_CHOICES = USER_REPORT_UPDATE_ACTION_CHOICES

    report = models.ForeignKey(UserReport, on_delete=models.CASCADE, related_name="updates")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_report_updates",
    )
    action = models.CharField(max_length=24, choices=ACTION_CHOICES)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["report", "created_at"], name="user_rep_upd_report_idx"),
            models.Index(fields=["actor", "created_at"], name="user_rep_upd_actor_idx"),
        ]

    def __str__(self):
        return f"Update for user report {self.report_id}: {self.get_action_display()}"


class SupportInvestigationQuerySet(models.QuerySet):
    def active(self):
        return self.filter(closed_at__isnull=True, expires_at__gt=timezone.now())


class SupportInvestigation(models.Model):
    subject = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="support_investigations",
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="opened_support_investigations",
    )
    reason = models.CharField(max_length=500)
    expires_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_support_investigations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    objects = SupportInvestigationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["subject", "expires_at"], name="support_inv_subject_idx"),
            models.Index(fields=["opened_by", "expires_at"], name="support_inv_opened_idx"),
        ]

    @property
    def is_active(self):
        return self.closed_at is None and self.expires_at > timezone.now()

    def clean(self):
        super().clean()
        if self.subject_id and self.opened_by_id and self.subject_id == self.opened_by_id:
            raise ValidationError({"subject": "Support investigations cannot target the acting staff account."})
        if self.opened_by_id and self.opened_by.role not in {Role.SUPPORT, Role.ADMIN}:
            raise ValidationError({"opened_by": "Only support or platform admins can open investigations."})
        if self.closed_at is None and self.expires_at and self.expires_at <= timezone.now():
            raise ValidationError({"expires_at": "Investigation access must expire in the future."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def close(self, *, actor):
        timestamp = timezone.now()
        self.closed_at = timestamp
        self.closed_by = actor
        self.save(update_fields=["closed_at", "closed_by"])
        return timestamp

    def __str__(self):
        return f"Investigation for {self.subject_id} by {self.opened_by_id}"


class AuditEvent(models.Model):
    action = models.CharField(max_length=64, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    target_repr = models.CharField(max_length=255, blank=True)
    reason = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["target_type", "target_id"], name="audit_event_target_idx"),
            models.Index(fields=["created_at"], name="audit_event_created_idx"),
        ]

    def __str__(self):
        return f"{self.action} ({self.created_at:%Y-%m-%d %H:%M:%S})"


class UserFile(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="files")
    title = models.CharField(max_length=120, blank=True)
    file = models.FileField(upload_to="user_uploads/%Y/%m/%d", validators=[validate_user_upload])
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["owner", "uploaded_at"], name="userfile_owner_uploaded_idx"),
        ]

    @property
    def display_title(self):
        if self.title:
            return self.title
        if self.file:
            return Path(self.file.name).name
        return ""

    def _validate_total_file_limit(self):
        if not self._state.adding or not self.owner_id:
            return

        get_user_model()._default_manager.select_for_update().filter(pk=self.owner_id).exists()
        existing_files_count = type(self).objects.filter(owner_id=self.owner_id).count()
        if existing_files_count >= settings.USER_FILE_TOTAL_LIMIT:
            raise ValidationError({"file": _document_library_limit_message(settings.USER_FILE_TOTAL_LIMIT)})

    def clean(self):
        super().clean()
        self._validate_total_file_limit()

    def save(self, *args, **kwargs):
        with transaction.atomic():
            self.full_clean()
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.display_title} ({self.owner})"


@receiver(post_delete, sender=UserFile)
def delete_user_file_blob(sender, instance, **kwargs):
    if instance.file:
        storage = instance.file.storage
        name = instance.file.name
        if name:
            transaction.on_commit(lambda: storage.delete(name))
