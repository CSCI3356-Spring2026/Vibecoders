# Register your models here
from django.contrib import admin
from .models import Listing

@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    # This controls what columns show up in the list view
    list_display = ('title', 'owner', 'price', 'status', 'is_hidden')
    
    # This adds a sidebar filter
    list_filter = ('status', 'lease_type', 'is_hidden')
    
    # This adds a search bar
    search_fields = ('title', 'address')