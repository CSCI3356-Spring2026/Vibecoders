from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class Role(models.TextChoices):
    STUDENT = "student", "Student"
    ADMIN = "admin", "Admin"


# Custom user model with role support for Student/Admin distinction
class CustomUser(AbstractUser):
    """Custom user model with role support for Student/Admin distinction."""

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.STUDENT,
        help_text="Designates whether this user is a Student or Admin.",
    )

    @property
    def is_bc_admin(self):
        """Return True if the user has the Admin role."""
        return self.role == Role.ADMIN

    @property
    def display_role(self):
        """Human-readable role label for templates (e.g. 'Student', 'Admin')."""
        return self.get_role_display()

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
    file = models.FileField(upload_to="user_uploads/%Y/%m/%d")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    @property
    def display_title(self):
        if self.title:
            return self.title
        if self.file:
            return Path(self.file.name).name
        return ""

    def __str__(self):
        return f"{self.display_title} ({self.owner})"


# Uses Role to determine which attributes to assign
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_role_profile(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.role == Role.STUDENT:
        StudentProfile.objects.create(user=instance)
    elif instance.role == Role.ADMIN:
        AdminProfile.objects.create(user=instance)
