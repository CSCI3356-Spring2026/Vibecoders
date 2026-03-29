from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser, UserFile


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """Admin configuration for CustomUser with role visible but not editable in raw admin."""

    list_display = ("username", "email", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")
    fieldsets = UserAdmin.fieldsets + (("Role", {"fields": ("role",)}),)
    readonly_fields = ("role",)

    def get_add_fieldsets(self, request, obj=None):
        return self.add_fieldsets


@admin.register(UserFile)
class UserFileAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "uploaded_at")
    search_fields = ("title", "owner__username", "owner__email")
    list_select_related = ("owner",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        user = getattr(request, "user", None)
        return bool(getattr(user, "is_active", False) and getattr(user, "is_staff", False))
