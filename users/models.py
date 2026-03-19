import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

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

    @property
    def email_domain(self):
        return _email_domain(self.email)

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

    def apply_email_role_policy(self):
        if self.role != Role.ADMIN:
            self.role = self.default_role_for_email(self.email)

    def set_admin_access(self, enabled):
        self.role = Role.ADMIN if enabled else self.default_role_for_email(self.email)

    def save(self, *args, **kwargs):
        normalized_email = self.normalize_email_address(self.email)
        if not normalized_email:
            raise ValueError("Users must have an email address.")
        self.email = normalized_email
        self.apply_email_role_policy()
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


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_role_profile(sender, instance, **kwargs):
    if instance.role == Role.STUDENT:
        StudentProfile.objects.get_or_create(user=instance)
    elif instance.role == Role.ADMIN:
        AdminProfile.objects.get_or_create(user=instance)


@receiver(post_delete, sender=UserFile)
def delete_user_file_blob(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)
