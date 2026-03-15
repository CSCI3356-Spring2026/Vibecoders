from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import ListingForm
from .models import Listing


# Minimal current views for listing-related pages
def search(request):
    return render(request, "listings/search.html")


def listing_detail(request):
    return render(request, "listings/listing_detail.html")


def listing_list(request):
    listings = Listing.objects.filter(is_hidden=False).order_by("-created_at")

    return render(request, "listings/listing_list.html", {"listings": listings})


@login_required
def create_listing(request):
    if request.method == "POST":
        form = ListingForm(request.POST)
        if form.is_valid():
            listing = form.save(commit=False)
            listing.owner = request.user
            listing.save()
            return redirect("listings:listing_list")  # Send them back to the feed
    else:
        form = ListingForm()

    return render(request, "listings/listing_form.html", {"form": form})
