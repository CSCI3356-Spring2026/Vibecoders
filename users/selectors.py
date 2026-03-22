from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from listings.models import Listing

from .models import Role, UserFile


def admin_listings_queryset(query="", selected_status=""):
    status_values = {status for status, _ in Listing.STATUS_CHOICES}
    queryset = Listing.objects.with_related()

    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(address__icontains=query)
            | Q(owner__email__icontains=query)
            | Q(owner__username__icontains=query)
        )
    if selected_status in status_values:
        queryset = queryset.filter(status=selected_status)

    return queryset


def admin_users_queryset(query="", selected_role="", selected_active=""):
    role_values = {role.value for role in Role}
    user_model = get_user_model()
    queryset = user_model.objects.all().order_by("username")

    if query:
        queryset = queryset.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )
    if selected_role in role_values:
        queryset = queryset.filter(role=selected_role)
    if selected_active in {"active", "inactive"}:
        queryset = queryset.filter(is_active=(selected_active == "active"))

    return queryset


def admin_dashboard_metrics():
    user_model = get_user_model()
    listing_metrics = Listing.objects.aggregate(
        total_listings=Count("id"),
        pending_listings=Count("id", filter=Q(status="PENDING")),
        approved_listings=Count("id", filter=Q(status="AVAILABLE")),
    )
    user_metrics = user_model.objects.aggregate(
        student_users=Count("id", filter=Q(role=Role.STUDENT)),
        realtor_users=Count("id", filter=Q(role=Role.REALTOR)),
        admin_users_total=Count("id", filter=Q(role=Role.ADMIN)),
    )
    return {
        **listing_metrics,
        **user_metrics,
    }


def accessible_user_files_queryset(user):
    if user.is_bc_admin:
        return UserFile.objects.select_related("owner")
    return UserFile.objects.filter(owner=user).select_related("owner")
