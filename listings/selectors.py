from django.db.models import Avg, BooleanField, Case, Count, Exists, IntegerField, OuterRef, Prefetch, Q, Value, When

from .models import (
    Listing,
    ListingFavorite,
    ListingReport,
    ListingReportUpdate,
    ListingReview,
    RoommateGroup,
    RoommatePost,
)

ACTIVE_REPORT_STATUSES = [ListingReport.STATUS_OPEN, ListingReport.STATUS_IN_REVIEW]


def _archived_listing_conversation_exists(user):
    from communications.models import ListingConversation

    return Exists(
        ListingConversation.objects.visible_to(user).filter(
            listing_id=OuterRef("pk"),
        )
    )


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


def _marketplace_listing_scope(user):
    public_listings = Listing.objects.public()
    if not getattr(user, "is_authenticated", False):
        return public_listings
    if user.can_browse_marketplace:
        return public_listings
    return Listing.objects.filter(owner=user)


def listing_reviews_queryset(listing):
    return (
        ListingReview.objects.filter(listing=listing)
        .select_related("author")
        .prefetch_related("author__socialaccount_set")
    )


def listing_reports_queryset_for_admin(*, listing=None):
    status_priority = Case(
        When(status=ListingReport.STATUS_OPEN, then=Value(0)),
        When(status=ListingReport.STATUS_IN_REVIEW, then=Value(1)),
        When(status=ListingReport.STATUS_RESOLVED, then=Value(2)),
        default=Value(3),
        output_field=IntegerField(),
    )
    queryset = (
        ListingReport.objects.select_related(
            "listing",
            "listing__owner",
            "reporter",
            "reviewed_by",
        )
        .prefetch_related(
            "reporter__socialaccount_set",
            Prefetch(
                "updates",
                queryset=ListingReportUpdate.objects.select_related("actor").order_by("-created_at", "-id"),
            ),
        )
        .annotate(status_priority=status_priority)
        .order_by("status_priority", "-created_at")
    )
    if listing is not None:
        queryset = queryset.filter(listing=listing)
    return queryset


def marketplace_listings_for_user(user):
    return with_feedback_summary(_marketplace_listing_scope(user).with_related()).order_by("-created_at")


def searchable_marketplace_listings_for_user(user):
    return (
        _marketplace_listing_scope(user).filter(latitude__isnull=False, longitude__isnull=False).order_by("-created_at")
    )


def accessible_listing_detail_queryset(user):
    base_queryset = with_feedback_summary(Listing.objects.with_related())
    if not getattr(user, "is_authenticated", False):
        return base_queryset.public()
    if user.is_bc_admin:
        return base_queryset
    archived_conversation_exists = _archived_listing_conversation_exists(user)
    if user.can_browse_marketplace:
        return base_queryset.annotate(has_visible_conversation=archived_conversation_exists).filter(
            Q(owner=user)
            | Listing.public_visibility_q()
            | Q(
                archived_at__isnull=False,
                has_visible_conversation=True,
            )
        )
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


def roommate_post_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return None
    return RoommatePost.objects.with_related().filter(author=user).first()


def roommate_group_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return None
    return RoommateGroup.objects.prefetch_related("members").filter(lead=user).first()


def roommate_group_post_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return None
    return RoommatePost.objects.with_related().filter(group__lead=user).first()


def active_roommate_post_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return None
    return RoommatePost.objects.active().filter(Q(author=user) | Q(group__lead=user)).first()


def open_listings_matching_roommate_post(user, roommate_post):
    if roommate_post is None:
        return Listing.objects.none()

    queryset = with_favorite_state(marketplace_listings_for_user(user), user)
    move_in_date = getattr(roommate_post, "move_in_date", None)
    if move_in_date:
        queryset = queryset.filter(start_date__lte=move_in_date, end_date__gte=move_in_date)

    target_size = roommate_post.target_household_size or roommate_post.current_group_size
    if target_size:
        queryset = queryset.filter(rooms__gte=target_size)

    return queryset.order_by("-created_at")


def filtered_roommate_posts_queryset(
    user,
    *,
    query="",
    housing_status="",
    max_budget=None,
    move_in_by=None,
    open_spots_min=None,
    people_in_group=None,
):
    queryset = RoommatePost.objects.active()
    if getattr(user, "is_authenticated", False):
        queryset = queryset.exclude(Q(author=user) | Q(group__lead=user))

    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(neighborhoods__icontains=query)
            | Q(group__name__icontains=query)
            | Q(author__first_name__icontains=query)
            | Q(author__last_name__icontains=query)
            | Q(author__username__icontains=query)
            | Q(author__student_profile__major__icontains=query)
            | Q(group__lead__first_name__icontains=query)
            | Q(group__lead__last_name__icontains=query)
            | Q(group__lead__username__icontains=query)
            | Q(group__members__first_name__icontains=query)
            | Q(group__members__last_name__icontains=query)
            | Q(group__members__student_profile__major__icontains=query)
        )
    if housing_status in {value for value, _ in RoommatePost.HOUSING_CHOICES}:
        if housing_status == RoommatePost.HOUSING_HAVE_HOME:
            queryset = queryset.filter(housing_status=RoommatePost.HOUSING_HAVE_HOME)
        else:
            queryset = queryset.filter(housing_status=housing_status)
    if max_budget is not None:
        queryset = queryset.filter(budget_min__lte=max_budget)
    if move_in_by is not None:
        queryset = queryset.filter(move_in_date__lte=move_in_by)
    if open_spots_min is not None:
        queryset = queryset.filter(open_spots__gte=open_spots_min)
    if people_in_group is not None:
        queryset = queryset.filter(open_spots__gte=people_in_group)

    return queryset.distinct().order_by("-updated_at", "-created_at")
