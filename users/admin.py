from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser, UserFile


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """Admin configuration for CustomUser with role field visible."""

    list_display = ("username", "email", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")

    # Add 'role' to the existing fieldsets
    fieldsets = UserAdmin.fieldsets + (("Role", {"fields": ("role",)}),)

    # Add 'role' to the add-user form
    add_fieldsets = UserAdmin.add_fieldsets + (("Role", {"fields": ("role",)}),)


@admin.register(UserFile)
class UserFileAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "uploaded_at")
    search_fields = ("title", "owner__username", "owner__email")
    list_select_related = ("owner",)
