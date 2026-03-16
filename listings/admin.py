from django.contrib import admin

from .models import Listing, ListingImage


class ListingImageInline(admin.TabularInline):
    model = ListingImage
    extra = 0


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "price", "status", "is_hidden", "created_at")
    list_filter = ("status", "lease_type", "property_type", "is_hidden")
    search_fields = ("title", "address", "owner__username", "owner__email")
    list_select_related = ("owner",)
    inlines = [ListingImageInline]
