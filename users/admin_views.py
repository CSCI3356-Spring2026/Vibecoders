from functools import wraps

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from communications.models import ListingConversation, ListingMessage
from communications.selectors import user_related_conversations_queryset, user_related_messages_queryset
from core.utils import get_page, preserved_query_suffix, safe_next_url
from listings.models import Listing

from .models import Role
from .selectors import admin_listings_queryset, admin_users_queryset

ADMIN_LISTINGS_PER_PAGE = 20
ADMIN_USERS_PER_PAGE = 20
ADMIN_USER_DETAIL_PREVIEW_LIMIT = 15


def admin_required_view(view_func):
    @login_required
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_bc_admin:
            return HttpResponseForbidden("Admin access required.")
        return view_func(request, *args, **kwargs)

    return wrapped


@admin_required_view
def admin_dashboard(request):
    query = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "").strip()
    listings_qs = admin_listings_queryset(query=query, selected_status=selected_status)

    User = get_user_model()
    filtered_listings_count = listings_qs.count()
    context = {
        "listings": listings_qs[:10],
        "filtered_listings_count": filtered_listings_count,
        "total_listings": Listing.objects.count(),
        "pending_listings": Listing.objects.filter(status="PENDING").count(),
        "approved_listings": Listing.objects.filter(status="AVAILABLE").count(),
        "student_users": User.objects.filter(role=Role.STUDENT).count(),
        "realtor_users": User.objects.filter(role=Role.REALTOR).count(),
        "admin_users_total": User.objects.filter(role=Role.ADMIN).count(),
        "total_conversations": ListingConversation.objects.count(),
        "total_messages": ListingMessage.objects.count(),
        "query": query,
        "selected_status": selected_status,
        "status_options": Listing.STATUS_CHOICES,
    }
    return render(request, "users/admin_dashboard.html", context)


@admin_required_view
def admin_listings(request):
    query = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "").strip()
    listings_qs = admin_listings_queryset(query=query, selected_status=selected_status)
    listings_page = get_page(listings_qs, request.GET.get("page"), ADMIN_LISTINGS_PER_PAGE)

    context = {
        "listings": listings_page,
        "listings_total": listings_page.paginator.count,
        "pagination_query": preserved_query_suffix(request.GET, "page"),
        "query": query,
        "selected_status": selected_status,
        "status_options": Listing.STATUS_CHOICES,
    }
    return render(request, "users/admin_listings.html", context)


@admin_required_view
@require_POST
def admin_delete_listing(request, listing_id):
    listing = get_object_or_404(Listing, id=listing_id)
    listing.delete()
    redirect_to = safe_next_url(
        request,
        request.POST.get("next"),
        reverse("users:admin_listings"),
    )
    return redirect(redirect_to)


@admin_required_view
def admin_users(request):
    query = request.GET.get("q", "").strip()
    selected_role = request.GET.get("role", "").strip()
    selected_active = request.GET.get("active", "").strip()
    users_qs = admin_users_queryset(
        query=query,
        selected_role=selected_role,
        selected_active=selected_active,
    )
    users_page = get_page(users_qs, request.GET.get("page"), ADMIN_USERS_PER_PAGE)

    context = {
        "users": users_page,
        "users_total": users_page.paginator.count,
        "pagination_query": preserved_query_suffix(request.GET, "page"),
        "query": query,
        "selected_role": selected_role,
        "selected_active": selected_active,
        "role_options": Role.choices,
    }
    return render(request, "users/admin_users.html", context)


@admin_required_view
def admin_user_detail(request, user_id):
    User = get_user_model()
    user_obj = get_object_or_404(User, id=user_id)
    listings_qs = user_obj.listings.with_related()
    files_qs = user_obj.files.all()
    conversations_qs = user_related_conversations_queryset(user_obj)
    messages_qs = user_related_messages_queryset(user_obj)

    context = {
        "managed_user": user_obj,
        "managed_listings": listings_qs[:ADMIN_USER_DETAIL_PREVIEW_LIMIT],
        "managed_files": files_qs[:ADMIN_USER_DETAIL_PREVIEW_LIMIT],
        "managed_conversations": conversations_qs[:ADMIN_USER_DETAIL_PREVIEW_LIMIT],
        "managed_messages": messages_qs.order_by("-created_at")[:ADMIN_USER_DETAIL_PREVIEW_LIMIT],
        "managed_listings_count": listings_qs.count(),
        "managed_files_count": files_qs.count(),
        "managed_conversations_count": conversations_qs.count(),
        "managed_messages_count": messages_qs.count(),
        "activity_preview_limit": ADMIN_USER_DETAIL_PREVIEW_LIMIT,
    }
    return render(request, "users/admin_user_detail.html", context)


@admin_required_view
@require_POST
def admin_set_role(request, user_id):
    User = get_user_model()
    user_obj = get_object_or_404(User, id=user_id)
    if user_obj.id == request.user.id:
        return HttpResponseForbidden("You cannot change your own role.")

    action = request.POST.get("action", "").strip()
    if action == "grant_admin":
        user_obj.set_admin_access(True)
    elif action == "restore_default":
        user_obj.set_admin_access(False)
    else:
        return HttpResponseForbidden("Invalid role action.")

    user_obj.save(update_fields=["role"])
    return redirect("users:admin_users")


@admin_required_view
@require_POST
def admin_toggle_active(request, user_id):
    User = get_user_model()
    user_obj = get_object_or_404(User, id=user_id)
    if user_obj.id == request.user.id:
        return HttpResponseForbidden("You cannot deactivate your own account.")

    user_obj.is_active = not user_obj.is_active
    user_obj.save(update_fields=["is_active"])
    return redirect("users:admin_users")
