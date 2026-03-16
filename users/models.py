from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


# Inital roles, Student or Admin
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


class UserFile(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="files")
    title = models.CharField(max_length=120)
    file = models.FileField(upload_to="user_uploads/%Y/%m/%d")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.title} ({self.owner})"
