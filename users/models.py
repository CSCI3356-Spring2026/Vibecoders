import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .profile_images import profile_image_url_from_data
from .validators import validate_user_upload


def _normalize_email_address(email):
    return (email or "").strip().lower()


def _email_domain(email):
    normalized_email = _normalize_email_address(email)
    if "@" not in normalized_email:
        return ""
    return normalized_email.rsplit("@", 1)[1]


class Role(models.TextChoices):
    STUDENT = "student", "Student"
    REALTOR = "realtor", "Realtor"
    ADMIN = "admin", "Admin"


class CustomUser(AbstractUser):
    """Custom user model with role-aware marketplace access."""

    REQUIRED_FIELDS = ["email"]
    email = models.EmailField("email address", unique=True)
    profile_image_url = models.URLField(blank=True, max_length=500)
    role = models.CharField(
        max_length=12,
        choices=Role.choices,
        default=Role.STUDENT,
        db_index=True,
        help_text="Access level for the housing platform.",
    )
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
        return self.google_avatar_url or self.profile_image_url or ""

    @property
    def has_verified_student_email(self):
        return self.email_domain in self.student_email_domains()

    @property
    def has_edu_email(self):
        return self.email_domain.endswith(".edu")

    @property
    def is_bc_admin(self):
        """Return True if the user has the Admin role."""
        return self.role == Role.ADMIN

    @property
    def is_student(self):
        return self.role == Role.STUDENT

    @property
    def is_realtor(self):
        return self.role == Role.REALTOR

    @property
    def can_access_admin_panel(self):
        return self.is_bc_admin

    @property
    def can_browse_marketplace(self):
        return self.is_student or self.is_bc_admin

    @property
    def can_start_listing_conversations(self):
        return self.is_student or self.is_bc_admin

    @property
    def has_listing_only_access(self):
        return self.is_realtor

    @property
    def access_summary(self):
        if self.is_bc_admin:
            return "Admin access with marketplace oversight."
        if self.can_browse_marketplace:
            return "Verified student access to browse, message, and list."
        return "Listing-only access for external listers."

    @property
    def display_role(self):
        """Human-readable role label for templates (e.g. 'Student', 'Admin')."""
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
        if self.role != Role.ADMIN:
            self.role = self.default_role_for_email(self.email)

    def set_admin_access(self, enabled):
        self.role = Role.ADMIN if enabled else self.default_role_for_email(self.email)

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)

        original_email = self.email
        original_role = self.role
        normalized_email = self.normalize_email_address(self.email)
        if not normalized_email:
            raise ValueError("Users must have an email address.")
        self.email = normalized_email
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
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_profile")
    preferred_name = models.CharField(max_length=120, blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=32, blank=True)
    major = models.CharField(max_length=120, blank=True)
    bio = models.CharField(max_length=300, blank=True)
    messy_level = models.PositiveSmallIntegerField(null=True, blank=True)
    guest_level = models.PositiveSmallIntegerField(null=True, blank=True)
    bedtime = models.PositiveSmallIntegerField(null=True, blank=True)
    noise_level = models.PositiveSmallIntegerField(null=True, blank=True)
    smoke = models.BooleanField(default=False)
    drink = models.BooleanField(default=False)
    party = models.BooleanField(default=False)
    pets = models.BooleanField(default=False)

    def __str__(self):
        return f"StudentProfile({self.user.username})"


class AdminProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="admin_profile")
    preferred_name = models.CharField(max_length=120, blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=32, blank=True)
    bio = models.CharField(max_length=300, blank=True)

    def __str__(self):
        return f"AdminProfile({self.user.username})"


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

    def save(self, *args, **kwargs):
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
