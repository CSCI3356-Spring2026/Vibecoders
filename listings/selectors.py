from .models import Listing


def marketplace_listings_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return Listing.objects.visible()
    if user.is_bc_admin:
        return Listing.objects.with_related()
    if user.can_browse_marketplace:
        return Listing.objects.visible()
    return Listing.objects.with_related().filter(owner=user)
