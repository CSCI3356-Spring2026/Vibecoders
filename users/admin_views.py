import logging
from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from communications.models import ListingConversation, ListingMessage
from communications.selectors import user_related_conversations_queryset, user_related_messages_queryset
from core.utils import get_page, preserved_query_suffix, safe_next_url
from listings.forms import AdminListingApprovalForm, AdminListingReportResolutionForm
from listings.models import Listing, ListingReport
from listings.selectors import listing_reports_queryset_for_admin, listing_reviews_queryset, with_feedback_summary

from .models import Role
from .selectors import admin_dashboard_metrics, admin_listings_queryset, admin_reports_queryset, admin_users_queryset

ADMIN_LISTINGS_PER_PAGE = 20
ADMIN_USERS_PER_PAGE = 20
ADMIN_REPORTS_PER_PAGE = 20
ADMIN_USER_DETAIL_PREVIEW_LIMIT = 15

logger = logging.getLogger(__name__)


def _admin_listing_detail_context(listing, *, approval_form=None):
    reports = list(listing_reports_queryset_for_admin(listing=listing))
    reviews = list(listing_reviews_queryset(listing))
    for report in reports:
        report.ui_form = AdminListingReportResolutionForm(
            instance=report,
            prefix=f"report-{report.id}",
        )

    return {
        "listing": listing,
        "reports": reports,
        "reviews": reviews,
        "approval_form": approval_form or AdminListingApprovalForm(initial={"review_notes": listing.approval_notes}),
    }


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
    selected_review_status = request.GET.get("review_status", "").strip()
    listings_qs = admin_listings_queryset(
        query=query,
        selected_status=selected_status,
        selected_review_status=selected_review_status,
    )

    filtered_listings_count = listings_qs.count()
    metrics = admin_dashboard_metrics()
    context = {
        "listings": listings_qs[:10],
        "filtered_listings_count": filtered_listings_count,
        **metrics,
        "total_conversations": ListingConversation.objects.count(),
        "total_messages": ListingMessage.objects.count(),
        "query": query,
        "selected_status": selected_status,
        "selected_review_status": selected_review_status,
        "status_options": Listing.STATUS_CHOICES,
        "review_status_options": Listing.APPROVAL_CHOICES,
    }
    return render(request, "users/admin_dashboard.html", context)


@admin_required_view
def admin_listings(request):
    query = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "").strip()
    selected_review_status = request.GET.get("review_status", "").strip()
    listings_qs = admin_listings_queryset(
        query=query,
        selected_status=selected_status,
        selected_review_status=selected_review_status,
    )
    listings_page = get_page(listings_qs, request.GET.get("page"), ADMIN_LISTINGS_PER_PAGE)

    context = {
        "listings": listings_page,
        "listings_total": listings_page.paginator.count,
        "pagination_query": preserved_query_suffix(request.GET, "page"),
        "query": query,
        "selected_status": selected_status,
        "selected_review_status": selected_review_status,
        "status_options": Listing.STATUS_CHOICES,
        "review_status_options": Listing.APPROVAL_CHOICES,
    }
    return render(request, "users/admin_listings.html", context)


@admin_required_view
def admin_listing_detail(request, listing_id):
    listing = get_object_or_404(with_feedback_summary(Listing.objects.with_related()), id=listing_id)
    return render(request, "users/admin_listing_detail.html", _admin_listing_detail_context(listing))


@admin_required_view
@require_POST
def admin_review_listing(request, listing_id):
    listing = get_object_or_404(with_feedback_summary(Listing.objects.with_related()), id=listing_id)
    form = AdminListingApprovalForm(request.POST)
    action = request.POST.get("action", "").strip()
    if not form.is_valid():
        messages.error(request, "Keep review notes under 2,000 characters.")
        return render(
            request,
            "users/admin_listing_detail.html",
            _admin_listing_detail_context(listing, approval_form=form),
        )

    review_notes = form.cleaned_data["review_notes"]
    if action == "approve":
        listing.approve(reviewer=request.user, notes=review_notes)
        logger.info("listing_approved listing_id=%s reviewer_id=%s", listing.id, request.user.id)
        messages.success(request, "Listing approved.")
    elif action == "reject":
        if not review_notes:
            form.add_error("review_notes", "Add review notes when rejecting a listing.")
            messages.error(request, "Rejections need review notes so the owner knows what to fix.")
            return render(
                request,
                "users/admin_listing_detail.html",
                _admin_listing_detail_context(listing, approval_form=form),
            )
        listing.reject(reviewer=request.user, notes=review_notes)
        logger.info("listing_rejected listing_id=%s reviewer_id=%s", listing.id, request.user.id)
        messages.success(request, "Listing rejected.")
    else:
        return HttpResponseForbidden("Invalid review action.")

    listing.save(
        update_fields=[
            "approval_status",
            "submitted_for_approval_at",
            "reviewed_at",
            "approved_at",
            "reviewed_by",
            "approval_notes",
        ]
    )
    return redirect("users:admin_listing_detail", listing_id=listing.id)


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
def admin_reports(request):
    query = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "").strip()
    selected_reason = request.GET.get("reason", "").strip()
    reports_qs = admin_reports_queryset(
        query=query,
        selected_status=selected_status,
        selected_reason=selected_reason,
    )
    reports_page = get_page(reports_qs, request.GET.get("page"), ADMIN_REPORTS_PER_PAGE)
    for report in reports_page.object_list:
        report.ui_form = AdminListingReportResolutionForm(instance=report, prefix=f"report-{report.id}")

    context = {
        "reports": reports_page,
        "reports_total": reports_page.paginator.count,
        "pagination_query": preserved_query_suffix(request.GET, "page"),
        "query": query,
        "selected_status": selected_status,
        "selected_reason": selected_reason,
        "status_options": ListingReport.STATUS_CHOICES,
        "reason_options": ListingReport.REASON_CHOICES,
    }
    return render(request, "users/admin_reports.html", context)


@admin_required_view
@require_POST
def admin_update_report(request, report_id):
    report = get_object_or_404(ListingReport.objects.select_related("listing"), id=report_id)
    form = AdminListingReportResolutionForm(request.POST, instance=report, prefix=f"report-{report.id}")
    if not form.is_valid():
        messages.error(request, "Add valid resolution notes before updating the report.")
        return redirect("users:admin_reports")

    updated_report = form.save(commit=False)
    updated_report.mark_status(
        status=updated_report.status,
        reviewer=request.user,
        resolution_notes=updated_report.resolution_notes,
    )
    updated_report.save(
        update_fields=[
            "status",
            "reviewed_by",
            "reviewed_at",
            "resolution_notes",
            "updated_at",
        ]
    )
    logger.info(
        "listing_report_updated report_id=%s listing_id=%s reviewer_id=%s status=%s",
        updated_report.id,
        updated_report.listing_id,
        request.user.id,
        updated_report.status,
    )
    messages.success(request, "Report updated.")
    redirect_to = safe_next_url(
        request,
        request.POST.get("next"),
        reverse("users:admin_reports"),
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
    user_model = get_user_model()
    user_obj = get_object_or_404(
        user_model.objects.annotate(
            managed_listings_count=Count("listings", distinct=True),
            managed_files_count=Count("files", distinct=True),
        ),
        id=user_id,
    )
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
        "managed_listings_count": user_obj.managed_listings_count,
        "managed_files_count": user_obj.managed_files_count,
        "managed_conversations_count": conversations_qs.count(),
        "managed_messages_count": messages_qs.count(),
        "activity_preview_limit": ADMIN_USER_DETAIL_PREVIEW_LIMIT,
    }
    return render(request, "users/admin_user_detail.html", context)


@admin_required_view
@require_POST
def admin_set_role(request, user_id):
    user_model = get_user_model()
    user_obj = get_object_or_404(user_model, id=user_id)
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
    user_model = get_user_model()
    user_obj = get_object_or_404(user_model, id=user_id)
    if user_obj.id == request.user.id:
        return HttpResponseForbidden("You cannot deactivate your own account.")

    user_obj.is_active = not user_obj.is_active
    user_obj.save(update_fields=["is_active"])
    return redirect("users:admin_users")
