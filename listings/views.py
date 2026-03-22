from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from communications.forms import ConversationMessageForm
from communications.models import ListingConversation
from communications.services import (
    MESSAGE_SEND_RATE_LIMIT_ERROR,
    consume_message_send_rate_limit,
    start_listing_conversation,
)
from core.utils import get_page, preserved_query_suffix

from .filtering import MAX_PRICE_FILTERS, MOVE_IN_FILTERS, apply_listing_filters
from .form_services import handle_listing_form_submission, validation_message
from .forms import ListingForm
from .models import Listing
from .selectors import accessible_listing_detail_queryset, marketplace_listings_for_user, messageable_listings_for_user

LISTINGS_PER_PAGE = 12


def _workspace_destination(user):
    if user.has_listing_only_access:
        return "users:posts", "My Listings"
    return "listings:listing_list", "Listings"


def _selected_remove_image_ids(form):
    if not form.is_bound:
        return set()
    return set(form.data.getlist(form.add_prefix("remove_images")))


def _listing_form_context(form, *, is_edit, back_url_name, back_label, listing=None):
    context = {
        "form": form,
        "form_summary": form.build_summary(),
        "selected_remove_image_ids": _selected_remove_image_ids(form),
        "is_edit": is_edit,
        "back_url_name": back_url_name,
        "back_label": back_label,
    }
    if listing is not None:
        context["listing"] = listing
    return context


def _get_listing_for_user(user, pk):
    return get_object_or_404(accessible_listing_detail_queryset(user), pk=pk)


@login_required
def listing_list(request):
    base_queryset = marketplace_listings_for_user(request.user)
    listings, active_filters = apply_listing_filters(base_queryset, request.GET)
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
    can_message_listing = (
        request.user.can_start_listing_conversations
        and listing.owner_id != request.user.id
        and listing.is_publicly_active
    )

    if request.user.can_start_listing_conversations and listing.owner_id != request.user.id:
        existing_conversation = (
            ListingConversation.objects.visible_to(request.user).with_related().filter(listing=listing).first()
        )
        if existing_conversation:
            existing_conversation.ui_has_unread = existing_conversation.has_unread_for(request.user)
        if can_message_listing:
            message_form = ConversationMessageForm()

    if show_owner_conversations:
        owner_conversations = list(
            ListingConversation.objects.visible_to(request.user)
            .with_related()
            .filter(listing=listing)
            .order_by("-last_message_at", "-created_at")[:8]
        )
        for conversation in owner_conversations:
            conversation.ui_counterparty_name = conversation.participant.display_name
            conversation.ui_has_unread = conversation.has_unread_for(request.user)

    context = {
        "listing": listing,
        "listing_images": listing_images,
        "message_form": message_form,
        "existing_conversation": existing_conversation,
        "can_message_listing": can_message_listing,
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

    listing = get_object_or_404(messageable_listings_for_user(request.user), pk=pk)
    if listing.owner_id == request.user.id:
        messages.error(request, "You cannot message yourself about your own listing.")
        return redirect("listings:detail", pk=listing.pk)
    if not consume_message_send_rate_limit(request.user):
        messages.error(request, MESSAGE_SEND_RATE_LIMIT_ERROR)
        return redirect("listings:detail", pk=listing.pk)

    form = ConversationMessageForm(request.POST)
    if form.is_valid():
        try:
            conversation, _, created = start_listing_conversation(listing, request.user, form.cleaned_data["body"])
        except ValidationError as exc:
            messages.error(request, validation_message(exc, "Enter a message before sending."))
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
        listing = handle_listing_form_submission(form=form, owner=request.user)
        if listing is not None:
            messages.success(request, "Listing created.")
            return redirect("listings:detail", pk=listing.pk)
    else:
        form = ListingForm()

    back_url_name, back_label = _workspace_destination(request.user)
    return render(
        request,
        "listings/listing_form.html",
        _listing_form_context(form, is_edit=False, back_url_name=back_url_name, back_label=back_label),
    )


@login_required
def edit_listing(request, pk):
    listing = get_object_or_404(Listing, pk=pk, owner=request.user)
    if request.method == "POST":
        form = ListingForm(request.POST, request.FILES, instance=listing)
        listing = handle_listing_form_submission(form=form, owner=request.user)
        if listing is not None:
            messages.success(request, "Listing updated.")
            return redirect("listings:detail", pk=listing.pk)
    else:
        form = ListingForm(instance=listing)
    return render(
        request,
        "listings/listing_form.html",
        _listing_form_context(
            form,
            is_edit=True,
            listing=listing,
            back_url_name="users:posts",
            back_label="My Listings",
        ),
    )


@login_required
@require_POST
def delete_listing(request, pk):
    listing = get_object_or_404(Listing, pk=pk, owner=request.user)
    listing.delete()
    return redirect("users:posts")
