from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from listings.models import Listing


def _landing_listings_for_user(user):
    if not user.is_authenticated:
        return Listing.objects.visible()
    if user.is_bc_admin:
        return Listing.objects.with_related()
    if user.can_browse_marketplace:
        return Listing.objects.visible()
    return Listing.objects.with_related().filter(owner=user)


def landing(request):
    visible_listings = _landing_listings_for_user(request.user)
    featured_listings = list(visible_listings[:5])
    hero_listing = featured_listings[0] if featured_listings else None
    spotlight_listings = featured_listings[1:5] or featured_listings[:4]

    context = {
        "hero_listing": hero_listing,
        "spotlight_listings": spotlight_listings,
        "has_listing_only_access": request.user.is_authenticated and request.user.has_listing_only_access,
    }
    return render(request, "core/landing.html", context)


@login_required
def welcome(request):
    return redirect("users:dashboard")
