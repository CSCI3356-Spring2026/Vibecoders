import logging
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from communications.selectors import user_related_conversations_queryset, user_related_messages_queryset
from core.utils import get_page, preserved_query_suffix, safe_next_url
from listings.forms import AdminListingApprovalForm, AdminListingReportResolutionForm
from listings.lifecycle import archive_listing
from listings.models import Listing, ListingReport
from listings.report_services import update_listing_report
from listings.selectors import listing_reports_queryset_for_admin, listing_reviews_queryset, with_feedback_summary

from .account_lifecycle import deactivate_user, reactivate_user
from .admin_state import may_deactivate, may_lose_admin_access
from .audit import record_audit_event
from .forms import AdminUserRoleForm, SupportInvestigationForm
from .models import Role, SupportInvestigation
from .permissions import (
    active_investigation_for_viewer,
    moderation_required_view,
    platform_admin_required_view,
    reports_required_view,
    staff_required_view,
    support_required_view,
)
from .selectors import admin_dashboard_snapshot, admin_listings_queryset, admin_reports_queryset, admin_users_queryset
from .session_security import has_recent_privileged_auth

ADMIN_LISTINGS_PER_PAGE = 20
ADMIN_USERS_PER_PAGE = 20
ADMIN_REPORTS_PER_PAGE = 20
ADMIN_USER_DETAIL_PREVIEW_LIMIT = 15

logger = logging.getLogger(__name__)


def _require_recent_staff_auth(request, *, redirect_to):
    if has_recent_privileged_auth(request):
        return None
    messages.error(request, "Sign in again before performing sensitive staff actions.")
    return redirect(redirect_to)


def _admin_report_form(report, *, data=None):
    return AdminListingReportResolutionForm(
        data=data,
        instance=report,
        prefix=f"report-{report.id}",
    )


def _admin_report_timeline(report, *, limit=None):
    updates = list(report.updates.all())
    if limit is not None:
        updates = updates[:limit]
    return updates


def _admin_report_metrics(queryset):
    return queryset.aggregate(
        open_reports=Count("id", filter=Q(status=ListingReport.STATUS_OPEN)),
        in_review_reports=Count("id", filter=Q(status=ListingReport.STATUS_IN_REVIEW)),
        closed_reports=Count(
            "id",
            filter=Q(status__in=[ListingReport.STATUS_RESOLVED, ListingReport.STATUS_DISMISSED]),
        ),
        affected_listings=Count("listing_id", distinct=True),
    )


def _admin_report_filter_state(*, request=None, next_url=None):
    if request is not None and request.method == "GET":
        data = request.GET
        page = request.GET.get("page")
    else:
        parsed = parse_qs(urlsplit(next_url or "").query)
        data = {key: values[0] for key, values in parsed.items() if values}
        page = data.get("page")
    return {
        "query": (data.get("q") or "").strip(),
        "selected_status": (data.get("status") or "").strip(),
        "selected_reason": (data.get("reason") or "").strip(),
        "page": page,
    }


def _admin_reports_context(
    *,
    request=None,
    page=None,
    query="",
    selected_status="",
    selected_reason="",
    report_forms=None,
    next_url=None,
):
    reports_qs = admin_reports_queryset(
        query=query,
        selected_status=selected_status,
        selected_reason=selected_reason,
    )
    report_metrics = _admin_report_metrics(
        admin_reports_queryset(
            query=query,
            selected_status=selected_status,
            selected_reason=selected_reason,
            include_closed=True,
        )
    )
    page_number = page
    if page_number is None and request is not None:
        page_number = request.GET.get("page")
    reports_page = get_page(reports_qs, page_number, ADMIN_REPORTS_PER_PAGE)
    form_map = report_forms or {}
    report_next_url = next_url or (request.get_full_path() if request is not None else reverse("users:admin_reports"))
    for report in reports_page.object_list:
        report.ui_form = form_map.get(report.id) or _admin_report_form(report)
        report.ui_next = report_next_url
        report.ui_updates = _admin_report_timeline(report, limit=3)
        report.ui_update_count = len(report.updates.all())
        report.ui_has_more_updates = report.ui_update_count > len(report.ui_updates)

    return {
        "reports": reports_page,
        "reports_total": reports_page.paginator.count,
        "pagination_query": preserved_query_suffix(request.GET, "page") if request is not None else "",
        "query": query,
        "selected_status": selected_status,
        "selected_reason": selected_reason,
        "status_options": ListingReport.STATUS_CHOICES,
        "reason_options": ListingReport.REASON_CHOICES,
        **report_metrics,
    }


def _render_invalid_report_update(request, report, form, *, message):
    messages.error(request, message)
    next_url = safe_next_url(
        request,
        request.POST.get("next"),
        reverse("users:admin_reports"),
    )
    next_path = urlsplit(next_url).path
    listing_detail_path = reverse("users:admin_listing_detail", args=[report.listing_id])
    if next_path == listing_detail_path:
        listing = get_object_or_404(with_feedback_summary(Listing.objects.with_related()), id=report.listing_id)
        return render(
            request,
            "users/admin_listing_detail.html",
            _admin_listing_detail_context(request, listing, report_forms={report.id: form}, next_url=next_url),
        )

    filter_state = _admin_report_filter_state(next_url=next_url)
    context = _admin_reports_context(
        page=filter_state["page"],
        query=filter_state["query"],
        selected_status=filter_state["selected_status"],
        selected_reason=filter_state["selected_reason"],
        report_forms={report.id: form},
        next_url=next_url,
    )
    return render(request, "users/admin_reports.html", context)


def _admin_listing_detail_context(request, listing, *, approval_form=None, report_forms=None, next_url=None):
    reports = list(listing_reports_queryset_for_admin(listing=listing))
    reviews = list(listing_reviews_queryset(listing))
    form_map = report_forms or {}
    report_next_url = next_url or reverse("users:admin_listing_detail", args=[listing.id])
    for report in reports:
        report.ui_form = form_map.get(report.id) or _admin_report_form(report)
        report.ui_next = report_next_url
        report.ui_updates = _admin_report_timeline(report)
        report.ui_update_count = len(report.ui_updates)
        report.ui_has_more_updates = False

    return {
        "listing": listing,
        "reports": reports,
        "reviews": reviews,
        "approval_form": approval_form or AdminListingApprovalForm(initial={"review_notes": listing.approval_notes}),
        "can_archive_listing": request.user.can_manage_listing_moderation,
    }


def _role_form_for_user(user):
    return AdminUserRoleForm(initial={"role": user.role})


def _investigation_form():
    return SupportInvestigationForm()


def _active_investigations_for_subject(subject_user):
    return SupportInvestigation.objects.active().filter(subject=subject_user).select_related("opened_by")


def _admin_user_detail_context(request, managed_user, *, investigation_form=None):
    listings_qs = managed_user.listings.with_related()
    active_investigation = active_investigation_for_viewer(request.user, managed_user)
    conversations_qs = user_related_conversations_queryset(managed_user)
    messages_qs = user_related_messages_queryset(managed_user)
    show_sensitive_activity = active_investigation is not None
    if show_sensitive_activity:
        record_audit_event(
            action="support_investigation.viewed",
            actor=request.user,
            target=managed_user,
            reason=active_investigation.reason,
            metadata={"investigation_id": active_investigation.pk},
        )

    return {
        "managed_user": managed_user,
        "managed_listings": listings_qs[:ADMIN_USER_DETAIL_PREVIEW_LIMIT],
        "managed_files": managed_user.files.all()[:ADMIN_USER_DETAIL_PREVIEW_LIMIT] if show_sensitive_activity else [],
        "managed_conversations": conversations_qs[:ADMIN_USER_DETAIL_PREVIEW_LIMIT] if show_sensitive_activity else [],
        "managed_messages": messages_qs.order_by("-created_at")[:ADMIN_USER_DETAIL_PREVIEW_LIMIT]
        if show_sensitive_activity
        else [],
        "managed_listings_count": getattr(managed_user, "managed_listings_count", listings_qs.count()),
        "managed_files_count": getattr(managed_user, "managed_files_count", managed_user.files.count()),
        "managed_conversations_count": conversations_qs.count(),
        "managed_messages_count": messages_qs.count(),
        "activity_preview_limit": ADMIN_USER_DETAIL_PREVIEW_LIMIT,
        "show_sensitive_activity": show_sensitive_activity,
        "active_investigation": active_investigation,
        "subject_active_investigations": _active_investigations_for_subject(managed_user)[:5],
        "can_open_investigation": request.user.can_open_support_investigations and request.user.id != managed_user.id,
        "investigation_form": investigation_form or _investigation_form(),
    }


@staff_required_view
def admin_dashboard(request):
    query = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "").strip()
    selected_review_status = request.GET.get("review_status", "").strip()
    metrics = admin_dashboard_snapshot(
        query=query,
        selected_status=selected_status,
        selected_review_status=selected_review_status,
    )
    context = {
        **metrics,
        "query": query,
        "selected_status": selected_status,
        "selected_review_status": selected_review_status,
        "status_options": Listing.STATUS_CHOICES,
        "review_status_options": Listing.APPROVAL_CHOICES,
    }
    return render(request, "users/admin_dashboard.html", context)


@moderation_required_view
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


@moderation_required_view
def admin_listing_detail(request, listing_id):
    listing = get_object_or_404(with_feedback_summary(Listing.objects.with_related()), id=listing_id)
    return render(request, "users/admin_listing_detail.html", _admin_listing_detail_context(request, listing))


@moderation_required_view
@require_POST
def admin_review_listing(request, listing_id):
    recent_auth_redirect = _require_recent_staff_auth(
        request,
        redirect_to=reverse("users:admin_listing_detail", args=[listing_id]),
    )
    if recent_auth_redirect is not None:
        return recent_auth_redirect

    listing = get_object_or_404(with_feedback_summary(Listing.objects.with_related()), id=listing_id)
    form = AdminListingApprovalForm(request.POST)
    action = request.POST.get("action", "").strip()
    if not form.is_valid():
        messages.error(request, "Keep review notes under 2,000 characters.")
        return render(
            request,
            "users/admin_listing_detail.html",
            _admin_listing_detail_context(request, listing, approval_form=form),
        )

    review_notes = form.cleaned_data["review_notes"]
    if action == "approve":
        listing.approve(reviewer=request.user, notes=review_notes)
        logger.info("listing.review.approved listing_id=%s actor_id=%s", listing.id, request.user.id)
        record_audit_event(
            action="listing.reviewed",
            actor=request.user,
            target=listing,
            reason=review_notes,
            metadata={"decision": "approved"},
        )
        messages.success(request, "Listing approved.")
    elif action == "reject":
        if not review_notes:
            form.add_error("review_notes", "Add review notes when rejecting a listing.")
            messages.error(request, "Rejections need review notes so the owner knows what to fix.")
            return render(
                request,
                "users/admin_listing_detail.html",
                _admin_listing_detail_context(request, listing, approval_form=form),
            )
        listing.reject(reviewer=request.user, notes=review_notes)
        logger.info("listing.review.rejected listing_id=%s actor_id=%s", listing.id, request.user.id)
        record_audit_event(
            action="listing.reviewed",
            actor=request.user,
            target=listing,
            reason=review_notes,
            metadata={"decision": "rejected"},
        )
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


@moderation_required_view
@require_POST
def admin_archive_listing(request, listing_id):
    recent_auth_redirect = _require_recent_staff_auth(
        request,
        redirect_to=reverse("users:admin_listing_detail", args=[listing_id]),
    )
    if recent_auth_redirect is not None:
        return recent_auth_redirect

    listing = get_object_or_404(Listing, id=listing_id)
    archive_listing(
        listing,
        actor=request.user,
        reason=Listing.ARCHIVE_REASON_ADMIN,
    )
    record_audit_event(
        action="listing.archived",
        actor=request.user,
        target=listing,
        reason="Staff archive",
    )
    redirect_to = safe_next_url(
        request,
        request.POST.get("next"),
        reverse("users:admin_listings"),
    )
    return redirect(redirect_to)


@moderation_required_view
@require_POST
def admin_delete_listing(request, listing_id):
    return admin_archive_listing(request, listing_id)


@reports_required_view
def admin_reports(request):
    filter_state = _admin_report_filter_state(request=request)
    context = _admin_reports_context(
        request=request,
        query=filter_state["query"],
        selected_status=filter_state["selected_status"],
        selected_reason=filter_state["selected_reason"],
    )
    return render(request, "users/admin_reports.html", context)


@reports_required_view
@require_POST
def admin_update_report(request, report_id):
    recent_auth_redirect = _require_recent_staff_auth(request, redirect_to=reverse("users:admin_reports"))
    if recent_auth_redirect is not None:
        return recent_auth_redirect

    report = get_object_or_404(ListingReport.objects.select_related("listing"), id=report_id)
    form = _admin_report_form(report, data=request.POST)
    if not form.is_valid():
        return _render_invalid_report_update(
            request,
            report,
            form,
            message="Add a moderator note before closing out a report.",
        )

    try:
        listing_closed = update_listing_report(
            report,
            status=form.cleaned_data["status"],
            reviewer=request.user,
            resolution_notes=form.cleaned_data["resolution_notes"],
        )
    except ValidationError as exc:
        if hasattr(exc, "message_dict"):
            for field_name, errors in exc.message_dict.items():
                target_field = field_name if field_name in form.fields else "resolution_notes"
                for error in errors:
                    form.add_error(target_field, error)
        else:
            for error in exc.messages:
                form.add_error("resolution_notes", error)
        return _render_invalid_report_update(
            request,
            report,
            form,
            message="Add a moderator note before closing out a report.",
        )
    logger.info(
        "listing.report.updated report_id=%s listing_id=%s actor_id=%s status=%s",
        report.id,
        report.listing_id,
        request.user.id,
        report.status,
    )
    record_audit_event(
        action="listing_report.updated",
        actor=request.user,
        target=report,
        reason=form.cleaned_data["resolution_notes"],
        metadata={"status": report.status, "listing_closed": listing_closed},
    )
    if listing_closed:
        messages.success(request, "Report resolved and listing removed from the marketplace.")
    elif report.status == ListingReport.STATUS_DISMISSED:
        messages.success(request, "Report dismissed.")
    elif report.status == ListingReport.STATUS_IN_REVIEW:
        messages.success(request, "Report moved to in review.")
    else:
        messages.success(request, "Report reopened.")
    redirect_to = safe_next_url(
        request,
        request.POST.get("next"),
        reverse("users:admin_reports"),
    )
    return redirect(redirect_to)


@staff_required_view
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

    role_forms = {user.pk: _role_form_for_user(user) for user in users_page.object_list}
    context = {
        "users": users_page,
        "users_total": users_page.paginator.count,
        "pagination_query": preserved_query_suffix(request.GET, "page"),
        "query": query,
        "selected_role": selected_role,
        "selected_active": selected_active,
        "role_options": Role.choices,
        "role_forms": role_forms,
    }
    return render(request, "users/admin_users.html", context)


@staff_required_view
def admin_user_detail(request, user_id):
    user_model = get_user_model()
    user_obj = get_object_or_404(
        user_model.objects.annotate(
            managed_listings_count=Count("listings", distinct=True),
            managed_files_count=Count("files", distinct=True),
        ),
        id=user_id,
    )
    context = _admin_user_detail_context(request, user_obj)
    return render(request, "users/admin_user_detail.html", context)


@support_required_view
@require_POST
def admin_open_investigation(request, user_id):
    recent_auth_redirect = _require_recent_staff_auth(
        request,
        redirect_to=reverse("users:admin_user_detail", args=[user_id]),
    )
    if recent_auth_redirect is not None:
        return recent_auth_redirect

    user_model = get_user_model()
    user_obj = get_object_or_404(user_model, id=user_id)
    if user_obj.id == request.user.id:
        return HttpResponseForbidden("You cannot investigate your own account.")

    form = SupportInvestigationForm(request.POST)
    if not form.is_valid():
        context = _admin_user_detail_context(request, user_obj, investigation_form=form)
        return render(request, "users/admin_user_detail.html", context)

    expires_at = timezone.now() + timedelta(hours=getattr(settings, "SUPPORT_INVESTIGATION_DURATION_HOURS", 24))
    investigation = SupportInvestigation.objects.create(
        subject=user_obj,
        opened_by=request.user,
        reason=form.cleaned_data["reason"],
        expires_at=expires_at,
    )
    record_audit_event(
        action="support_investigation.opened",
        actor=request.user,
        target=user_obj,
        reason=investigation.reason,
        metadata={"investigation_id": investigation.pk, "expires_at": expires_at.isoformat()},
    )
    messages.success(request, "Sensitive access granted for this account.")
    return redirect("users:admin_user_detail", user_id=user_obj.id)


@support_required_view
@require_POST
def admin_close_investigation(request, investigation_id):
    investigation = get_object_or_404(
        SupportInvestigation.objects.select_related("subject"),
        id=investigation_id,
        opened_by=request.user,
        closed_at__isnull=True,
    )
    recent_auth_redirect = _require_recent_staff_auth(
        request,
        redirect_to=reverse("users:admin_user_detail", args=[investigation.subject_id]),
    )
    if recent_auth_redirect is not None:
        return recent_auth_redirect

    investigation.close(actor=request.user)
    record_audit_event(
        action="support_investigation.closed",
        actor=request.user,
        target=investigation.subject,
        reason=investigation.reason,
        metadata={"investigation_id": investigation.pk},
    )
    messages.success(request, "Sensitive access closed.")
    return redirect("users:admin_user_detail", user_id=investigation.subject_id)


@platform_admin_required_view
@require_POST
def admin_set_role(request, user_id):
    recent_auth_redirect = _require_recent_staff_auth(request, redirect_to=reverse("users:admin_users"))
    if recent_auth_redirect is not None:
        return recent_auth_redirect

    user_model = get_user_model()
    user_obj = get_object_or_404(user_model, id=user_id)
    if user_obj.id == request.user.id:
        return HttpResponseForbidden("You cannot change your own role.")

    requested_role_raw = user_obj.normalize_role_value(request.POST.get("role", "").strip())
    try:
        requested_role = Role(requested_role_raw)
    except ValueError:
        return HttpResponseForbidden("Invalid role.")

    if requested_role != Role.ADMIN and user_obj.role == Role.ADMIN and not may_lose_admin_access(user_obj):
        messages.error(request, "You cannot remove platform admin access from the last active platform admin.")
        return redirect("users:admin_users")

    previous_role = user_obj.display_role
    if requested_role in {Role.STUDENT, Role.REALTOR}:
        expected_role = user_obj.default_role_for_email(user_obj.email)
        if requested_role != expected_role:
            messages.error(
                request,
                f"{user_obj.email} resolves to {expected_role.label.lower()} access based on the current email policy.",
            )
            return redirect("users:admin_users")
        user_obj.restore_default_access_role()
    else:
        user_obj.set_staff_role(requested_role)

    user_obj.save(update_fields=["role"])
    record_audit_event(
        action="user.role_changed",
        actor=request.user,
        target=user_obj,
        reason=f"{previous_role} -> {user_obj.display_role}",
        metadata={"role": user_obj.role},
    )
    messages.success(request, f"Role updated to {user_obj.display_role}.")
    return redirect("users:admin_users")


@platform_admin_required_view
@require_POST
def admin_toggle_active(request, user_id):
    recent_auth_redirect = _require_recent_staff_auth(request, redirect_to=reverse("users:admin_users"))
    if recent_auth_redirect is not None:
        return recent_auth_redirect

    user_model = get_user_model()
    user_obj = get_object_or_404(user_model, id=user_id)
    if user_obj.id == request.user.id:
        return HttpResponseForbidden("You cannot deactivate your own account.")
    if user_obj.deleted_at is not None and not user_obj.is_active:
        messages.error(request, "Closed accounts cannot be reactivated.")
        return redirect("users:admin_users")

    if user_obj.is_active:
        if not may_deactivate(user_obj):
            messages.error(request, "You cannot deactivate the last active platform admin account.")
            return redirect("users:admin_users")
        deactivate_user(user_obj, actor=request.user, reason="Staff deactivation")
        messages.success(request, "User deactivated.")
    else:
        reactivate_user(user_obj, actor=request.user, reason="Staff reactivation")
        messages.success(request, "User reactivated.")
    return redirect("users:admin_users")
