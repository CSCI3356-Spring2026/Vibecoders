from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render

from listings.selectors import marketplace_listings_for_user


def landing(request):
    visible_listings = marketplace_listings_for_user(request.user)
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


def terms_of_service(request):
    return render(request, "core/terms_of_service.html")


def privacy_policy(request):
    return render(request, "core/privacy_policy.html")


def healthz(request):
    response = JsonResponse({"status": "ok"})
    response["Cache-Control"] = "no-store"
    return response
