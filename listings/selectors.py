from django.db.models import Avg, BooleanField, Count, Exists, OuterRef, Q, Value

from .models import Listing, ListingFavorite, ListingReport, ListingReview

ACTIVE_REPORT_STATUSES = [ListingReport.STATUS_OPEN, ListingReport.STATUS_IN_REVIEW]


def with_feedback_summary(queryset):
    return queryset.annotate(
        average_rating=Avg("reviews__rating"),
        review_count=Count("reviews", distinct=True),
        open_report_count=Count(
            "reports",
            filter=Q(reports__status__in=ACTIVE_REPORT_STATUSES),
            distinct=True,
        ),
    )


def listing_reviews_queryset(listing):
    return (
        ListingReview.objects.filter(listing=listing)
        .select_related("author")
        .prefetch_related("author__socialaccount_set")
    )


def listing_reports_queryset_for_admin(*, listing=None):
    queryset = ListingReport.objects.select_related(
        "listing",
        "listing__owner",
        "reporter",
        "reviewed_by",
    ).prefetch_related("reporter__socialaccount_set")
    if listing is not None:
        queryset = queryset.filter(listing=listing)
    return queryset


def marketplace_listings_for_user(user):
    public_listings = with_feedback_summary(Listing.objects.with_related().public()).order_by("-created_at")
    if not getattr(user, "is_authenticated", False):
        return public_listings
    if user.can_browse_marketplace:
        return public_listings
    return with_feedback_summary(Listing.objects.with_related().filter(owner=user)).order_by("-created_at")


def searchable_marketplace_listings_for_user(user):
    return marketplace_listings_for_user(user).filter(latitude__isnull=False, longitude__isnull=False)


def accessible_listing_detail_queryset(user):
    base_queryset = with_feedback_summary(Listing.objects.with_related())
    if not getattr(user, "is_authenticated", False):
        return base_queryset.public()
    if user.is_bc_admin:
        return base_queryset
    if user.can_browse_marketplace:
        return base_queryset.filter(Q(owner=user) | Listing.public_visibility_q())
    return base_queryset.filter(owner=user)


def messageable_listings_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return Listing.objects.none()
    return accessible_listing_detail_queryset(user)


def with_favorite_state(queryset, user):
    if not getattr(user, "is_authenticated", False):
        return queryset.annotate(is_favorited=Value(False, output_field=BooleanField()))

    favorites = ListingFavorite.objects.filter(user=user, listing_id=OuterRef("pk"))
    return queryset.annotate(is_favorited=Exists(favorites))
