from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.utils import get_page, preserved_query_suffix

from .forms import ListingForm, ListingInquiryForm
from .models import Listing, ListingImage, ListingInquiry

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


def _workspace_destination(user):
    if user.is_authenticated and user.has_listing_only_access:
        return "users:posts", "My Listings"
    return "listings:listing_list", "Listings"


def _marketplace_listings_for_user(user):
    if not user.is_authenticated:
        return Listing.objects.visible()
    if user.is_bc_admin:
        return Listing.objects.with_related()
    if user.can_browse_marketplace:
        return Listing.objects.visible()
    return Listing.objects.with_related().filter(owner=user)


def _listing_detail_queryset_for_user(user):
    if not user.is_authenticated:
        return Listing.objects.visible()
    if user.is_bc_admin:
        return Listing.objects.with_related()
    if user.can_browse_marketplace:
        return Listing.objects.visible()
    return Listing.objects.with_related().filter(owner=user)


def _get_listing_for_user(user, pk):
    return get_object_or_404(_listing_detail_queryset_for_user(user), pk=pk)


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


@login_required
def listing_list(request):
    base_queryset = _marketplace_listings_for_user(request.user)
    listings, active_filters = _apply_listing_filters(base_queryset, request.GET)
    listings_page = get_page(listings, request.GET.get("page"), LISTINGS_PER_PAGE)
    has_listing_only_access = request.user.is_authenticated and request.user.has_listing_only_access

    context = {
        "listings": listings_page,
        "listings_total": listings_page.paginator.count,
        "pagination_query": preserved_query_suffix(request.GET, "page"),
        "active_filters": active_filters,
        "max_price_filters": MAX_PRICE_FILTERS,
        "lease_type_filters": Listing.LEASE_TYPES,
        "move_in_filters": MOVE_IN_FILTERS,
        "has_listing_only_access": has_listing_only_access,
    }
    return render(request, "listings/listing_list.html", context)


@login_required
def listing_detail(request, pk):
    listing = _get_listing_for_user(request.user, pk)
    inquiry_form = None
    existing_inquiry = None
    owner_inquiries = None
    back_url_name, back_label = _workspace_destination(request.user)
    show_owner_inquiries = request.user.is_authenticated and (
        request.user.is_bc_admin or listing.owner_id == request.user.id
    )

    if request.user.is_authenticated and request.user.can_inquire_on_listings and listing.owner_id != request.user.id:
        existing_inquiry = ListingInquiry.objects.filter(listing=listing, sender=request.user).first()
        inquiry_form = ListingInquiryForm(instance=existing_inquiry)

    if show_owner_inquiries:
        owner_inquiries = listing.inquiries.select_related("sender")

    context = {
        "listing": listing,
        "inquiry_form": inquiry_form,
        "existing_inquiry": existing_inquiry,
        "owner_inquiries": owner_inquiries,
        "show_owner_inquiries": show_owner_inquiries,
        "back_url_name": back_url_name,
        "back_label": back_label,
    }
    return render(request, "listings/listing_detail.html", context)


@login_required
def inquire_listing(request, pk):
    if not request.user.can_inquire_on_listings:
        return HttpResponseForbidden("Verified student access is required to inquire about listings.")

    queryset = Listing.objects.with_related() if request.user.is_bc_admin else Listing.objects.visible()
    listing = get_object_or_404(queryset, pk=pk)
    if listing.owner_id == request.user.id:
        messages.error(request, "You cannot inquire about your own listing.")
        return redirect("listings:detail", pk=listing.pk)

    form = ListingInquiryForm(request.POST)
    if form.is_valid():
        _, created = ListingInquiry.objects.update_or_create(
            listing=listing,
            sender=request.user,
            defaults={"message": form.cleaned_data["message"]},
        )
        if created:
            messages.success(request, "Inquiry sent.")
        else:
            messages.success(request, "Inquiry updated.")
    else:
        messages.error(request, "Add a short note before sending your inquiry.")

    return redirect("listings:detail", pk=listing.pk)


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

    back_url_name, back_label = _workspace_destination(request.user)
    return render(
        request,
        "listings/listing_form.html",
        {
            "form": form,
            "is_edit": False,
            "back_url_name": back_url_name,
            "back_label": back_label,
        },
    )


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
    return render(
        request,
        "listings/listing_form.html",
        {
            "form": form,
            "is_edit": True,
            "listing": listing,
            "back_url_name": "users:posts",
            "back_label": "My Listings",
        },
    )


@login_required
def delete_listing(request, pk):
    listing = get_object_or_404(Listing, pk=pk, owner=request.user)
    if request.method == "POST":
        listing.delete()
    return redirect("users:posts")
