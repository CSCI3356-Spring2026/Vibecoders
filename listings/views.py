from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.utils import get_page, preserved_query_suffix

from .forms import ListingForm
from .models import Listing, ListingImage

LISTINGS_PER_PAGE = 12

MAX_PRICE_FILTERS = [
    ("", "Any budget"),
    ("1000", "$500 - $1,000"),
    ("1500", "$1,000 - $1,500"),
    ("2000", "$1,500 - $2,000"),
    ("2500", "$2,000 - $2,500"),
]

MOVE_IN_FILTERS = [
    ("", "Anytime"),
    ("30", "Next 30 days"),
    ("60", "Next 60 days"),
    ("120", "Next 120 days"),
]


def _visible_listings():
    return Listing.objects.visible()


def _get_visible_listing(pk):
    return get_object_or_404(_visible_listings(), pk=pk)


def _apply_listing_filters(queryset, params):
    query = params.get("q", "").strip()
    if query:
        queryset = queryset.filter(
            Q(title__icontains=query) | Q(address__icontains=query) | Q(description__icontains=query)
        )

    max_price = params.get("max_price", "").strip()
    if max_price:
        queryset = queryset.filter(price__lte=max_price)

    lease_type = params.get("lease_type", "").strip()
    if lease_type:
        queryset = queryset.filter(lease_type=lease_type)

    available_by = params.get("available_by", "").strip()
    if available_by.isdigit():
        move_in_deadline = timezone.localdate() + timedelta(days=int(available_by))
        queryset = queryset.filter(start_date__lte=move_in_deadline)

    return queryset, {
        "q": query,
        "max_price": max_price,
        "lease_type": lease_type,
        "available_by": available_by,
    }


def listing_list(request):
    listings, active_filters = _apply_listing_filters(_visible_listings(), request.GET)
    listings_page = get_page(listings, request.GET.get("page"), LISTINGS_PER_PAGE)

    context = {
        "listings": listings_page,
        "listings_total": listings_page.paginator.count,
        "pagination_query": preserved_query_suffix(request.GET, "page"),
        "active_filters": active_filters,
        "max_price_filters": MAX_PRICE_FILTERS,
        "lease_type_filters": Listing.LEASE_TYPES,
        "move_in_filters": MOVE_IN_FILTERS,
    }
    return render(request, "listings/listing_list.html", context)


def listing_detail(request, pk):
    listing = _get_visible_listing(pk)
    return render(request, "listings/listing_detail.html", {"listing": listing})


@login_required
def create_listing(request):
    if request.method == "POST":
        form = ListingForm(request.POST, request.FILES)
        if form.is_valid():
            listing = form.save(commit=False)
            listing.owner = request.user
            listing.save()
            for image in request.FILES.getlist("images"):
                ListingImage.objects.create(listing=listing, image=image)
            return redirect("listings:listing_list")
    else:
        form = ListingForm()

    return render(request, "listings/listing_form.html", {"form": form})


@login_required
def edit_listing(request, pk):
    listing = get_object_or_404(Listing, pk=pk, owner=request.user)
    if request.method == "POST":
        form = ListingForm(request.POST, request.FILES, instance=listing)
        if form.is_valid():
            form.save()
            for image in request.FILES.getlist("images"):
                ListingImage.objects.create(listing=listing, image=image)
            return redirect("users:posts")
    else:
        form = ListingForm(instance=listing)
    return render(request, "listings/listing_form.html", {"form": form})


@login_required
def delete_listing(request, pk):
    listing = get_object_or_404(Listing, pk=pk, owner=request.user)
    if request.method == "POST":
        listing.delete()
    return redirect("users:posts")
