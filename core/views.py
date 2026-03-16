from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.utils import timezone

from listings.models import Listing


def landing(request):
    visible_listings = Listing.objects.visible()
    move_in_cutoff = timezone.localdate() + timedelta(days=30)
    market_stats = visible_listings.aggregate(
        active_count=Count("id"),
        sublease_count=Count("id", filter=Q(lease_type="SUBLEASE")),
        move_in_count=Count("id", filter=Q(start_date__lte=move_in_cutoff)),
    )
    featured_listings = list(visible_listings[:5])
    hero_listing = featured_listings[0] if featured_listings else None
    spotlight_listings = featured_listings[1:5] or featured_listings[:4]

    context = {
        "hero_listing": hero_listing,
        "spotlight_listings": spotlight_listings,
        "market_stats": market_stats,
    }
    return render(request, "core/landing.html", context)


@login_required
def welcome(request):
    return redirect("users:dashboard")
