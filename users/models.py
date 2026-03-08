from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    STUDENT = "student", "Student"
    ADMIN = "admin", "Admin"


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
