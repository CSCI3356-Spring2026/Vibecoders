from django.db.models import Q

from .models import Listing


def marketplace_listings_for_user(user):
    public_listings = Listing.objects.with_related().public()
    if not getattr(user, "is_authenticated", False):
        return public_listings
    if user.is_bc_admin:
        return Listing.objects.with_related()
    if user.can_browse_marketplace:
        return public_listings
    return Listing.objects.with_related().filter(owner=user)


def accessible_listing_detail_queryset(user):
    base_queryset = Listing.objects.with_related()
    if not getattr(user, "is_authenticated", False):
        return base_queryset.public()
    if user.is_bc_admin:
        return base_queryset
    if user.can_browse_marketplace:
        return base_queryset.filter(Q(owner=user) | Listing.public_visibility_q())
    return base_queryset.filter(owner=user)


def messageable_listings_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return Listing.objects.none()
    return accessible_listing_detail_queryset(user)
