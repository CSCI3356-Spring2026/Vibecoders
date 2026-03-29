from django.contrib import admin

from .models import Listing, ListingImage


class ListingImageInline(admin.TabularInline):
    model = ListingImage
    extra = 0


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "price", "approval_status", "status", "is_hidden", "created_at")
    list_filter = ("approval_status", "status", "lease_type", "property_type", "is_hidden")
    search_fields = ("title", "address", "owner__username", "owner__email")
    list_select_related = ("owner",)
    inlines = [ListingImageInline]

    def get_readonly_fields(self, request, obj=None):
        if obj is not None:
            return ("owner",)
        return ()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        user = getattr(request, "user", None)
        return bool(getattr(user, "is_active", False) and getattr(user, "is_staff", False))
