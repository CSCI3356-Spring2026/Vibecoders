from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from communications.forms import ConversationMessageForm
from communications.models import ListingConversation
from communications.services import start_listing_conversation
from core.utils import get_page, preserved_query_suffix

from .forms import ListingForm
from .models import Listing, ListingImage
from .selectors import marketplace_listings_for_user

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
    if user.has_listing_only_access:
        return "users:posts", "My Listings"
    return "listings:listing_list", "Listings"


def _save_uploaded_listing_images(listing, uploaded_images):
    if len(uploaded_images) > settings.LISTING_IMAGE_UPLOAD_LIMIT:
        raise ValidationError({"images": f"You can upload up to {settings.LISTING_IMAGE_UPLOAD_LIMIT} images."})

    existing_images_count = listing.images.count()
    if existing_images_count + len(uploaded_images) > settings.LISTING_IMAGE_TOTAL_LIMIT:
        raise ValidationError(
            {"images": (f"Each listing can have up to {settings.LISTING_IMAGE_TOTAL_LIMIT} images total.")}
        )

    pending_images = []
    for image in uploaded_images:
        listing_image = ListingImage(listing=listing, image=image)
        listing_image.full_clean()
        pending_images.append(listing_image)

    for listing_image in pending_images:
        listing_image.save()


def _add_form_validation_errors(form, exc):
    if hasattr(exc, "message_dict"):
        for field_name, messages_list in exc.message_dict.items():
            target_field = "images" if field_name == "image" else field_name
            for message in messages_list:
                form.add_error(target_field, message)
        return

    for message in exc.messages:
        form.add_error("images", message)


def _save_listing_form(form, owner, uploaded_images):
    with transaction.atomic():
        listing = form.save(commit=False)
        if listing._state.adding:
            listing.owner = owner
        listing.save()
        _save_uploaded_listing_images(listing, uploaded_images)


def _get_listing_for_user(user, pk):
    return get_object_or_404(marketplace_listings_for_user(user), pk=pk)


def _apply_listing_filters(queryset, params):
    query = params.get("q", "").strip()
    if query:
        queryset = queryset.filter(
            Q(title__icontains=query) | Q(address__icontains=query) | Q(description__icontains=query)
        )

    max_price = params.get("max_price", "").strip()
    if max_price:
        try:
            max_price_value = Decimal(max_price)
        except InvalidOperation:
            max_price = ""
        else:
            if max_price_value > 0:
                queryset = queryset.filter(price__lte=max_price_value)
            else:
                max_price = ""

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
    base_queryset = marketplace_listings_for_user(request.user)
    listings, active_filters = _apply_listing_filters(base_queryset, request.GET)
    listings_page = get_page(listings, request.GET.get("page"), LISTINGS_PER_PAGE)

    context = {
        "listings": listings_page,
        "listings_total": listings_page.paginator.count,
        "pagination_query": preserved_query_suffix(request.GET, "page"),
        "active_filters": active_filters,
        "max_price_filters": MAX_PRICE_FILTERS,
        "lease_type_filters": Listing.LEASE_TYPES,
        "move_in_filters": MOVE_IN_FILTERS,
        "has_listing_only_access": request.user.has_listing_only_access,
    }
    return render(request, "listings/listing_list.html", context)


@login_required
def listing_detail(request, pk):
    listing = _get_listing_for_user(request.user, pk)
    listing_images = list(listing.images.all())
    message_form = None
    existing_conversation = None
    owner_conversations = None
    back_url_name, back_label = _workspace_destination(request.user)
    show_owner_conversations = listing.owner_id == request.user.id

    if request.user.can_start_listing_conversations and listing.owner_id != request.user.id:
        existing_conversation = ListingConversation.objects.visible_to(request.user).filter(listing=listing).first()
        if existing_conversation:
            existing_conversation.ui_has_unread = existing_conversation.has_unread_for(request.user)
        message_form = ConversationMessageForm()

    if show_owner_conversations:
        owner_conversations = list(
            listing.conversations.select_related("participant").order_by("-last_message_at", "-created_at")[:8]
        )
        for conversation in owner_conversations:
            conversation.ui_counterparty_name = (
                conversation.participant.get_full_name() or conversation.participant.username
            )
            conversation.ui_has_unread = conversation.has_unread_for(request.user)

    context = {
        "listing": listing,
        "listing_images": listing_images,
        "message_form": message_form,
        "existing_conversation": existing_conversation,
        "owner_conversations": owner_conversations,
        "show_owner_conversations": show_owner_conversations,
        "back_url_name": back_url_name,
        "back_label": back_label,
    }
    return render(request, "listings/listing_detail.html", context)


@login_required
@require_POST
def message_listing(request, pk):
    if not request.user.can_start_listing_conversations:
        return HttpResponseForbidden("Verified student access is required to message about listings.")

    listing = _get_listing_for_user(request.user, pk)
    if listing.owner_id == request.user.id:
        messages.error(request, "You cannot message yourself about your own listing.")
        return redirect("listings:detail", pk=listing.pk)

    form = ConversationMessageForm(request.POST)
    if form.is_valid():
        try:
            conversation, _, created = start_listing_conversation(listing, request.user, form.cleaned_data["body"])
        except ValidationError:
            messages.error(request, "Enter a message before sending.")
        else:
            messages.success(request, "Conversation started." if created else "Message sent.")
            return redirect("communications:detail", conversation_id=conversation.pk)
    else:
        messages.error(request, "Enter a message before sending.")

    return redirect("listings:detail", pk=listing.pk)


@login_required
def create_listing(request):
    if request.method == "POST":
        form = ListingForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_images = request.FILES.getlist("images")
            try:
                _save_listing_form(form, request.user, uploaded_images)
            except ValidationError as exc:
                _add_form_validation_errors(form, exc)
            else:
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
            uploaded_images = request.FILES.getlist("images")
            try:
                _save_listing_form(form, request.user, uploaded_images)
            except ValidationError as exc:
                _add_form_validation_errors(form, exc)
            else:
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
@require_POST
def delete_listing(request, pk):
    listing = get_object_or_404(Listing, pk=pk, owner=request.user)
    listing.delete()
    return redirect("users:posts")
