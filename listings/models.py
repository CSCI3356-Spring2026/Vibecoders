from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

from roommates import models as roommate_models

from .validators import validate_listing_image

LISTING_STATUS_AVAILABLE = "AVAILABLE"
LISTING_STATUS_PENDING = "PENDING"
LISTING_STATUS_TAKEN = "TAKEN"

LISTING_LEASE_TYPES = [
    ("SUBLEASE", "Sublease"),
    ("FULL", "Full Lease"),
    ("SHORT", "Short-term"),
]
LISTING_STATUS_CHOICES = [
    (LISTING_STATUS_AVAILABLE, "Available"),
    (LISTING_STATUS_PENDING, "Pending"),
    (LISTING_STATUS_TAKEN, "Rented"),
]
LISTING_PROPERTY_TYPES = [
    ("apartment", "Apartment"),
    ("house", "House"),
    ("studio", "Studio"),
    ("dorm", "Dormitory"),
]
LISTING_SPACE_ENTIRE_UNIT = "ENTIRE_UNIT"
LISTING_SPACE_PRIVATE_ROOM = "PRIVATE_ROOM"
LISTING_SPACE_SHARED_ROOM = "SHARED_ROOM"
LISTING_SPACE_TYPES = [
    (LISTING_SPACE_ENTIRE_UNIT, "Whole apartment / house"),
    (LISTING_SPACE_PRIVATE_ROOM, "Private room"),
    (LISTING_SPACE_SHARED_ROOM, "Shared room"),
]
LISTING_APPROVAL_PENDING = "pending"
LISTING_APPROVAL_APPROVED = "approved"
LISTING_APPROVAL_REJECTED = "rejected"
LISTING_APPROVAL_CHOICES = [
    (LISTING_APPROVAL_PENDING, "Pending review"),
    (LISTING_APPROVAL_APPROVED, "Approved"),
    (LISTING_APPROVAL_REJECTED, "Rejected"),
]
LISTING_ARCHIVE_REASON_OWNER = "owner"
LISTING_ARCHIVE_REASON_ADMIN = "admin"
LISTING_ARCHIVE_REASON_REPORT = "report"
LISTING_ARCHIVE_REASON_CHOICES = [
    (LISTING_ARCHIVE_REASON_OWNER, "Owner archived"),
    (LISTING_ARCHIVE_REASON_ADMIN, "Admin archived"),
    (LISTING_ARCHIVE_REASON_REPORT, "Archived from report"),
]
LISTING_REPORT_STATUS_OPEN = "open"
LISTING_REPORT_STATUS_IN_REVIEW = "in_review"
LISTING_REPORT_STATUS_RESOLVED = "resolved"
LISTING_REPORT_STATUS_DISMISSED = "dismissed"
LISTING_REPORT_STATUS_CHOICES = [
    (LISTING_REPORT_STATUS_OPEN, "Open"),
    (LISTING_REPORT_STATUS_IN_REVIEW, "In review"),
    (LISTING_REPORT_STATUS_RESOLVED, "Resolved"),
    (LISTING_REPORT_STATUS_DISMISSED, "Dismissed"),
]
LISTING_REPORT_REASON_SCAM = "scam"
LISTING_REPORT_REASON_INACCURATE = "inaccurate"
LISTING_REPORT_REASON_SAFETY = "safety"
LISTING_REPORT_REASON_SPAM = "spam"
LISTING_REPORT_REASON_UNAVAILABLE = "unavailable"
LISTING_REPORT_REASON_INAPPROPRIATE = "inappropriate"
LISTING_REPORT_REASON_OTHER = "other"
LISTING_REPORT_REASON_CHOICES = [
    (LISTING_REPORT_REASON_SCAM, "Scam or suspicious"),
    (LISTING_REPORT_REASON_INACCURATE, "Inaccurate listing details"),
    (LISTING_REPORT_REASON_SAFETY, "Safety concern"),
    (LISTING_REPORT_REASON_SPAM, "Spam or duplicate"),
    (LISTING_REPORT_REASON_UNAVAILABLE, "No longer available"),
    (LISTING_REPORT_REASON_INAPPROPRIATE, "Inappropriate content"),
    (LISTING_REPORT_REASON_OTHER, "Other"),
]
LISTING_APPROVAL_VALUES = tuple(value for value, _ in LISTING_APPROVAL_CHOICES)
LISTING_LEASE_TYPE_VALUES = tuple(value for value, _ in LISTING_LEASE_TYPES)
LISTING_STATUS_VALUES = tuple(value for value, _ in LISTING_STATUS_CHOICES)
LISTING_PROPERTY_TYPE_VALUES = tuple(value for value, _ in LISTING_PROPERTY_TYPES)
LISTING_SPACE_TYPE_VALUES = tuple(value for value, _ in LISTING_SPACE_TYPES)
LISTING_REPORT_STATUS_VALUES = tuple(value for value, _ in LISTING_REPORT_STATUS_CHOICES)
LISTING_REPORT_REASON_VALUES = tuple(value for value, _ in LISTING_REPORT_REASON_CHOICES)
LISTING_REPORT_UPDATE_ACTION_NOTE = "note"
LISTING_REPORT_UPDATE_ACTION_IN_REVIEW = "in_review"
LISTING_REPORT_UPDATE_ACTION_DISMISSED = "dismissed"
LISTING_REPORT_UPDATE_ACTION_LISTING_CLOSED = "listing_closed"
LISTING_REPORT_UPDATE_ACTION_REOPENED = "reopened"
LISTING_REPORT_UPDATE_ACTION_CHOICES = [
    (LISTING_REPORT_UPDATE_ACTION_NOTE, "Comment added"),
    (LISTING_REPORT_UPDATE_ACTION_IN_REVIEW, "Moved to in review"),
    (LISTING_REPORT_UPDATE_ACTION_DISMISSED, "Dismissed"),
    (LISTING_REPORT_UPDATE_ACTION_LISTING_CLOSED, "Listing removed from marketplace"),
    (LISTING_REPORT_UPDATE_ACTION_REOPENED, "Reopened"),
]
LISTING_DOCUMENTATION_TYPE_CHOICES = [
    ("lease", "Standard Lease"),
    ("sublease", "Sublease Agreement"),
    ("license", "License Agreement"),
    ("other", "Other"),
]
LISTING_DOCUMENTATION_TYPE_VALUES = tuple(value for value, _ in LISTING_DOCUMENTATION_TYPE_CHOICES)

ROOMMATE_POST_HOUSING_HAVE_HOME = "have_home"
ROOMMATE_POST_HOUSING_NEED_HOME = "need_home"
ROOMMATE_POST_HOUSING_CHOICES = [
    (ROOMMATE_POST_HOUSING_HAVE_HOME, "Already have a place"),
    (ROOMMATE_POST_HOUSING_NEED_HOME, "Still need a place"),
]
ROOMMATE_POST_HOUSING_VALUES = tuple(value for value, _ in ROOMMATE_POST_HOUSING_CHOICES)


def _submission_context_changed(instance, *, identity_fields):
    if instance._state.adding or not instance.pk:
        return True

    original_values = type(instance).objects.filter(pk=instance.pk).values(*identity_fields).first()
    if original_values is None:
        return True
    return any(original_values[field_name] != getattr(instance, field_name) for field_name in identity_fields)


class ListingQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related("owner", "reviewed_by").prefetch_related("images", "owner__socialaccount_set")

    def public(self, *, as_of=None):
        return self.filter(Listing.public_visibility_q(as_of=as_of))

    def visible(self):
        return self.with_related().public()


class RoommatePostQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related(
            "author",
            "author__student_profile",
            "group",
            "group__lead",
            "group__lead__student_profile",
        ).prefetch_related(
            "author__socialaccount_set",
            "group__lead__socialaccount_set",
            "group__members__student_profile",
            "group__members__socialaccount_set",
        )

    def active(self):
        return (
            self.with_related()
            .filter(
                is_active=True,
                move_in_date__gte=timezone.localdate(),
            )
            .filter(
                (
                    Q(
                        author__is_active=True,
                        author__role="student",
                        author__profile_completed_at__isnull=False,
                    )
                )
                | (
                    Q(
                        group__lead__is_active=True,
                        group__lead__role="student",
                        group__lead__profile_completed_at__isnull=False,
                        group__is_active=True,
                    )
                )
            )
        )


class Listing(models.Model):
    STATUS_AVAILABLE = LISTING_STATUS_AVAILABLE
    STATUS_PENDING = LISTING_STATUS_PENDING
    STATUS_TAKEN = LISTING_STATUS_TAKEN
    SPACE_ENTIRE_UNIT = LISTING_SPACE_ENTIRE_UNIT
    SPACE_PRIVATE_ROOM = LISTING_SPACE_PRIVATE_ROOM
    SPACE_SHARED_ROOM = LISTING_SPACE_SHARED_ROOM
    APPROVAL_PENDING = LISTING_APPROVAL_PENDING
    APPROVAL_APPROVED = LISTING_APPROVAL_APPROVED
    APPROVAL_REJECTED = LISTING_APPROVAL_REJECTED
    ARCHIVE_REASON_OWNER = LISTING_ARCHIVE_REASON_OWNER
    ARCHIVE_REASON_ADMIN = LISTING_ARCHIVE_REASON_ADMIN
    ARCHIVE_REASON_REPORT = LISTING_ARCHIVE_REASON_REPORT

    LEASE_TYPES = LISTING_LEASE_TYPES
    STATUS_CHOICES = LISTING_STATUS_CHOICES
    PROPERTY_TYPES = LISTING_PROPERTY_TYPES
    SPACE_TYPES = LISTING_SPACE_TYPES
    APPROVAL_CHOICES = LISTING_APPROVAL_CHOICES
    ARCHIVE_REASON_CHOICES = LISTING_ARCHIVE_REASON_CHOICES
    DOCUMENTATION_TYPE_CHOICES = LISTING_DOCUMENTATION_TYPE_CHOICES

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="listings")
    title = models.CharField(max_length=200)
    address = models.CharField(max_length=255, help_text="Street address or Area")
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, help_text="Minimal description of the dorm")

    start_date = models.DateField()
    end_date = models.DateField()
    lease_type = models.CharField(max_length=20, choices=LEASE_TYPES, default="FULL")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="AVAILABLE")

    rooms = models.PositiveIntegerField(default=1)
    bathrooms = models.DecimalField(max_digits=3, decimal_places=1, default=1.0)
    sq_ft = models.PositiveIntegerField(null=True, blank=True)
    property_type = models.CharField(max_length=20, choices=PROPERTY_TYPES, default="apartment")
    space_type = models.CharField(max_length=20, choices=SPACE_TYPES, default=LISTING_SPACE_ENTIRE_UNIT)

    has_yard = models.BooleanField(default=False)
    has_parking = models.BooleanField(default=False)
    is_furnished = models.BooleanField(default=False)

    distance_to_campus = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True, help_text="Distance in miles"
    )
    utilities_estimate = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    parking_fee = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    security_deposit = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    application_fee = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    broker_fee = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    landlord_approval_required = models.BooleanField(default=False)
    original_lease_holder = models.CharField(max_length=200, blank=True)
    documentation_type = models.CharField(max_length=20, choices=LISTING_DOCUMENTATION_TYPE_CHOICES, blank=True)
    no_stairs = models.BooleanField(default=False)

    utilities_included = models.TextField(blank=True, help_text="List included utilities (e.g. WiFi, Water)")
    pet_policy = models.TextField(blank=True)
    amenities = models.TextField(blank=True, help_text="Comma separated list")
    security_features = models.TextField(blank=True)
    renter_requirements = models.TextField(
        blank=True,
        help_text="Roommate or renter expectations such as smoking, cleanliness, guests, or paperwork.",
    )

    approval_status = models.CharField(max_length=16, choices=APPROVAL_CHOICES, default=APPROVAL_PENDING, db_index=True)
    submitted_for_approval_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_listings",
    )
    approval_notes = models.TextField(blank=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archived_listings",
    )
    archive_reason = models.CharField(max_length=16, choices=ARCHIVE_REASON_CHOICES, blank=True)
    is_hidden = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ListingQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_hidden", "status", "end_date", "created_at"], name="listing_public_idx"),
            models.Index(fields=["owner", "created_at"], name="listing_owner_idx"),
            models.Index(fields=["status", "created_at"], name="listing_status_idx"),
            models.Index(fields=["approval_status", "created_at"], name="listing_approval_idx"),
            models.Index(fields=["archived_at", "created_at"], name="listing_archived_idx"),
            models.Index(fields=["latitude", "longitude"], name="listing_lat_lng_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")),
                name="listing_end_date_gte_start_date",
            ),
            models.CheckConstraint(
                condition=Q(price__gt=0),
                name="listing_price_gt_zero",
            ),
            models.CheckConstraint(
                condition=Q(rooms__gte=1),
                name="listing_rooms_gte_one",
            ),
            models.CheckConstraint(
                condition=Q(bathrooms__gt=0),
                name="listing_bathrooms_gt_zero",
            ),
            models.CheckConstraint(
                condition=Q(utilities_estimate__isnull=True) | Q(utilities_estimate__gte=0),
                name="listing_utilities_estimate_gte_zero",
            ),
            models.CheckConstraint(
                condition=Q(parking_fee__isnull=True) | Q(parking_fee__gte=0),
                name="listing_parking_fee_gte_zero",
            ),
            models.CheckConstraint(
                condition=Q(security_deposit__isnull=True) | Q(security_deposit__gte=0),
                name="listing_security_deposit_gte_zero",
            ),
            models.CheckConstraint(
                condition=Q(application_fee__isnull=True) | Q(application_fee__gte=0),
                name="listing_application_fee_gte_zero",
            ),
            models.CheckConstraint(
                condition=Q(distance_to_campus__isnull=True) | Q(distance_to_campus__gte=0),
                name="listing_distance_to_campus_gte_zero",
            ),
            models.CheckConstraint(
                condition=Q(broker_fee__isnull=True) | Q(broker_fee__gte=0),
                name="listing_broker_fee_gte_zero",
            ),
            models.CheckConstraint(
                condition=Q(documentation_type="") | Q(documentation_type__in=LISTING_DOCUMENTATION_TYPE_VALUES),
                name="listing_documentation_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(lease_type__in=LISTING_LEASE_TYPE_VALUES),
                name="listing_lease_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(status__in=LISTING_STATUS_VALUES),
                name="listing_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(property_type__in=LISTING_PROPERTY_TYPE_VALUES),
                name="listing_property_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(space_type__in=LISTING_SPACE_TYPE_VALUES),
                name="listing_space_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(approval_status__in=LISTING_APPROVAL_VALUES),
                name="listing_approval_status_valid",
            ),
        ]

    @classmethod
    def public_visibility_q(cls, *, as_of=None):
        return Q(
            owner__is_active=True,
            is_hidden=False,
            archived_at__isnull=True,
            approval_status=cls.APPROVAL_APPROVED,
            status=cls.STATUS_AVAILABLE,
            end_date__gte=as_of or timezone.localdate(),
        )

    def _validate_owner_immutability(self):
        if not self.pk:
            return

        original_owner_id = type(self).objects.filter(pk=self.pk).values_list("owner_id", flat=True).first()
        if original_owner_id is not None and self.owner_id != original_owner_id:
            raise ValidationError({"owner": "Listing ownership cannot be reassigned after creation."})

    def clean(self):
        super().clean()
        self._validate_owner_immutability()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date must be on or after the start date."})

    def save(self, *args, **kwargs):
        if self.submitted_for_approval_at is None:
            self.submitted_for_approval_at = timezone.now()
        if self.approval_status == self.APPROVAL_APPROVED:
            if self.reviewed_at is None:
                self.reviewed_at = self.submitted_for_approval_at
            if self.approved_at is None:
                self.approved_at = self.reviewed_at
        elif self.approval_status == self.APPROVAL_REJECTED and self.reviewed_at is None:
            self.reviewed_at = timezone.now()
        self._validate_owner_immutability()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} - ${self.price}"

    def _decimal_value(self, field_name):
        value = getattr(self, field_name)
        if value in (None, ""):
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0")

    @property
    def estimated_monthly_total(self):
        return (
            self._decimal_value("price")
            + self._decimal_value("utilities_estimate")
            + self._decimal_value("parking_fee")
        )

    @property
    def estimated_upfront_total(self):
        return (
            self._decimal_value("price")
            + self._decimal_value("security_deposit")
            + self._decimal_value("application_fee")
            + self._decimal_value("broker_fee")
        )

    @property
    def primary_image(self):
        prefetched = getattr(self, "_prefetched_objects_cache", {})
        images = prefetched.get("images")
        if images:
            return images[0]
        return self.images.order_by("id").first()

    @property
    def is_publicly_active(self):
        return (
            self.owner_id is not None
            and getattr(self.owner, "is_active", False)
            and not self.is_hidden
            and self.archived_at is None
            and self.approval_status == self.APPROVAL_APPROVED
            and self.status == self.STATUS_AVAILABLE
            and self.end_date >= timezone.localdate()
        )

    @property
    def has_map_coordinates(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def is_approved(self):
        return self.approval_status == self.APPROVAL_APPROVED

    @property
    def is_pending_review(self):
        return self.approval_status == self.APPROVAL_PENDING

    @property
    def is_rejected(self):
        return self.approval_status == self.APPROVAL_REJECTED

    @property
    def is_verified(self):
        return self.is_approved and self.approved_at is not None

    @property
    def is_archived(self):
        return self.archived_at is not None

    def submit_for_approval(self):
        self.approval_status = self.APPROVAL_PENDING
        self.submitted_for_approval_at = timezone.now()
        self.reviewed_at = None
        self.approved_at = None
        self.reviewed_by = None
        self.approval_notes = ""

    def approve(self, *, reviewer, notes=""):
        reviewed_at = timezone.now()
        self.approval_status = self.APPROVAL_APPROVED
        self.reviewed_by = reviewer
        self.reviewed_at = reviewed_at
        self.approved_at = reviewed_at
        self.approval_notes = notes.strip()
        if self.submitted_for_approval_at is None:
            self.submitted_for_approval_at = reviewed_at

    def reject(self, *, reviewer, notes=""):
        reviewed_at = timezone.now()
        self.approval_status = self.APPROVAL_REJECTED
        self.reviewed_by = reviewer
        self.reviewed_at = reviewed_at
        self.approved_at = None
        self.approval_notes = notes.strip()
        if self.submitted_for_approval_at is None:
            self.submitted_for_approval_at = reviewed_at

    def archive(self, *, by_user, reason, notes=""):
        if reason not in {
            self.ARCHIVE_REASON_OWNER,
            self.ARCHIVE_REASON_ADMIN,
            self.ARCHIVE_REASON_REPORT,
        }:
            raise ValidationError({"archive_reason": "Choose a valid archive reason."})

        archived_at = timezone.now()
        self.archived_at = archived_at
        self.archived_by = by_user
        self.archive_reason = reason
        self.is_hidden = True

        cleaned_notes = (notes or "").strip()
        if reason == self.ARCHIVE_REASON_REPORT:
            self.approval_status = self.APPROVAL_REJECTED
            self.reviewed_by = by_user
            self.reviewed_at = archived_at
            self.approved_at = None
            self.approval_notes = cleaned_notes
            if self.submitted_for_approval_at is None:
                self.submitted_for_approval_at = archived_at
        elif cleaned_notes:
            self.approval_notes = cleaned_notes

    def archive_from_report(self, *, reviewer, notes=""):
        self.archive(
            by_user=reviewer,
            reason=self.ARCHIVE_REASON_REPORT,
            notes=notes,
        )

    def close_from_report(self, *, reviewer, notes=""):
        self.archive_from_report(reviewer=reviewer, notes=notes)


class ListingImage(models.Model):
    listing = models.ForeignKey(Listing, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="listing_photos/", validators=[validate_listing_image])

    class Meta:
        ordering = ["id"]

    def _validate_total_image_limit(self):
        if not self._state.adding or not self.listing_id:
            return

        locked_listing = Listing.objects.select_for_update().get(pk=self.listing_id)
        existing_images_count = locked_listing.images.count()
        if existing_images_count >= settings.LISTING_IMAGE_TOTAL_LIMIT:
            raise ValidationError(
                {"image": f"Each listing can have up to {settings.LISTING_IMAGE_TOTAL_LIMIT} images total."}
            )

    def save(self, *args, **kwargs):
        with transaction.atomic():
            self._validate_total_image_limit()
            self.full_clean()
            super().save(*args, **kwargs)

    def __str__(self):
        return f"Image for {self.listing.title}"

    @property
    def versioned_url(self):
        if not self.image:
            return ""

        url = self.image.url
        try:
            modified_at = self.image.storage.get_modified_time(self.image.name)
        except (FileNotFoundError, NotImplementedError, OSError, ValueError):
            return url

        return f"{url}?v={int(modified_at.timestamp())}"


@receiver(post_delete, sender=ListingImage)
def delete_listing_image_file(sender, instance, **kwargs):
    if instance.image:
        storage = instance.image.storage
        name = instance.image.name
        if name:
            transaction.on_commit(lambda: storage.delete(name))


class ListingFavorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="listing_favorites",
    )
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="favorites")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "listing"], name="listing_favorite_unique"),
        ]
        indexes = [
            models.Index(fields=["user", "created_at"], name="listing_favorite_user_idx"),
            models.Index(fields=["listing", "created_at"], name="listing_favorite_listing_idx"),
        ]

    def clean(self):
        super().clean()
        listing_owner_id = getattr(self.listing, "owner_id", None)
        if listing_owner_id is None and self.listing_id:
            listing_owner_id = Listing.objects.filter(pk=self.listing_id).values_list("owner_id", flat=True).first()
        if self.user_id and listing_owner_id == self.user_id:
            raise ValidationError({"listing": "You cannot save your own listing."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user_id} favorited listing {self.listing_id}"


RoommateGroup = roommate_models.RoommateGroup
RoommateGroupMembership = roommate_models.RoommateGroupMembership
RoommatePost = roommate_models.RoommatePost


class ListingReview(models.Model):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="reviews")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="listing_reviews")
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["listing", "author"], name="listing_review_unique"),
            models.CheckConstraint(
                condition=Q(rating__gte=1) & Q(rating__lte=5),
                name="listing_review_rating_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["listing", "updated_at"], name="listing_review_listing_idx"),
            models.Index(fields=["author", "updated_at"], name="listing_review_author_idx"),
        ]

    def clean(self):
        super().clean()
        if not self.listing_id:
            return
        if _submission_context_changed(self, identity_fields=("listing_id", "author_id")):
            user_model = get_user_model()
            if self.author_id and not user_model._default_manager.filter(pk=self.author_id, role="student").exists():
                raise ValidationError({"comment": "Only student accounts can leave resident reviews."})
            listing_owner_id = getattr(self.listing, "owner_id", None)
            if listing_owner_id is None:
                listing_owner_id = Listing.objects.filter(pk=self.listing_id).values_list("owner_id", flat=True).first()
            if self.author_id and listing_owner_id == self.author_id:
                raise ValidationError({"comment": "You cannot review your own listing."})
            if not Listing.objects.filter(
                pk=self.listing_id,
                approval_status=Listing.APPROVAL_APPROVED,
                archived_at__isnull=True,
                is_hidden=False,
            ).exists():
                raise ValidationError({"comment": "Only approved listings can receive public reviews."})
            if self.author_id and not self.listing.conversations.filter(participant_id=self.author_id).exists():
                raise ValidationError({"comment": "Contact the lister before leaving a resident review."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ListingReport(models.Model):
    STATUS_OPEN = LISTING_REPORT_STATUS_OPEN
    STATUS_IN_REVIEW = LISTING_REPORT_STATUS_IN_REVIEW
    STATUS_RESOLVED = LISTING_REPORT_STATUS_RESOLVED
    STATUS_DISMISSED = LISTING_REPORT_STATUS_DISMISSED
    REASON_SCAM = LISTING_REPORT_REASON_SCAM
    REASON_INACCURATE = LISTING_REPORT_REASON_INACCURATE
    REASON_SAFETY = LISTING_REPORT_REASON_SAFETY
    REASON_SPAM = LISTING_REPORT_REASON_SPAM
    REASON_UNAVAILABLE = LISTING_REPORT_REASON_UNAVAILABLE
    REASON_INAPPROPRIATE = LISTING_REPORT_REASON_INAPPROPRIATE
    REASON_OTHER = LISTING_REPORT_REASON_OTHER

    REASON_CHOICES = LISTING_REPORT_REASON_CHOICES
    STATUS_CHOICES = LISTING_REPORT_STATUS_CHOICES

    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="reports")
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="listing_reports")
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    details = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="listing_reports_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(reason__in=LISTING_REPORT_REASON_VALUES),
                name="listing_report_reason_valid",
            ),
            models.CheckConstraint(
                condition=Q(status__in=LISTING_REPORT_STATUS_VALUES),
                name="listing_report_status_valid",
            ),
            models.UniqueConstraint(
                fields=["listing", "reporter"],
                condition=Q(status__in=[LISTING_REPORT_STATUS_OPEN, LISTING_REPORT_STATUS_IN_REVIEW]),
                name="listing_report_active_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "created_at"], name="listing_report_status_idx"),
            models.Index(fields=["listing", "status"], name="listing_report_listing_idx"),
            models.Index(fields=["reporter", "created_at"], name="listing_report_reporter_idx"),
        ]

    @property
    def is_closed(self):
        return self.status in {self.STATUS_RESOLVED, self.STATUS_DISMISSED}

    @property
    def closes_listing(self):
        return self.status == self.STATUS_RESOLVED

    def clean(self):
        super().clean()
        if not self.listing_id:
            return
        if _submission_context_changed(self, identity_fields=("listing_id", "reporter_id")):
            user_model = get_user_model()
            reporter_is_student = user_model._default_manager.filter(pk=self.reporter_id, role="student").exists()
            if self.reporter_id and not reporter_is_student:
                raise ValidationError({"details": "Only student accounts can report listings."})
            listing_owner_id = getattr(self.listing, "owner_id", None)
            if listing_owner_id is None:
                listing_owner_id = Listing.objects.filter(pk=self.listing_id).values_list("owner_id", flat=True).first()
            if self.reporter_id and listing_owner_id == self.reporter_id:
                raise ValidationError({"details": "You cannot report your own listing."})
            if not Listing.objects.filter(
                pk=self.listing_id,
                approval_status=Listing.APPROVAL_APPROVED,
                archived_at__isnull=True,
                is_hidden=False,
            ).exists():
                raise ValidationError({"details": "Only approved listings can be reported."})
        if self.status in {self.STATUS_RESOLVED, self.STATUS_DISMISSED} and not (self.resolution_notes or "").strip():
            raise ValidationError({"resolution_notes": "Add resolution notes before closing a report."})

    def mark_status(self, *, status, reviewer, resolution_notes=""):
        self.status = status
        cleaned_notes = resolution_notes.strip()
        if status in {self.STATUS_RESOLVED, self.STATUS_DISMISSED} and not cleaned_notes:
            raise ValidationError({"resolution_notes": "Add resolution notes before closing a report."})
        if status == self.STATUS_OPEN:
            self.reviewed_by = None
            self.reviewed_at = None
            self.resolution_notes = ""
            return
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.resolution_notes = cleaned_notes

    def activity_action_for_status(self, status):
        if status == self.STATUS_OPEN:
            return LISTING_REPORT_UPDATE_ACTION_REOPENED
        if status == self.STATUS_IN_REVIEW:
            return LISTING_REPORT_UPDATE_ACTION_IN_REVIEW
        if status == self.STATUS_DISMISSED:
            return LISTING_REPORT_UPDATE_ACTION_DISMISSED
        if status == self.STATUS_RESOLVED:
            return LISTING_REPORT_UPDATE_ACTION_LISTING_CLOSED
        return LISTING_REPORT_UPDATE_ACTION_NOTE

    def add_update(self, *, actor, note="", action=""):
        return ListingReportUpdate.objects.create(
            report=self,
            actor=actor,
            action=action or self.activity_action_for_status(self.status),
            note=(note or "").strip(),
        )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ListingReportUpdate(models.Model):
    ACTION_NOTE = LISTING_REPORT_UPDATE_ACTION_NOTE
    ACTION_IN_REVIEW = LISTING_REPORT_UPDATE_ACTION_IN_REVIEW
    ACTION_DISMISSED = LISTING_REPORT_UPDATE_ACTION_DISMISSED
    ACTION_LISTING_CLOSED = LISTING_REPORT_UPDATE_ACTION_LISTING_CLOSED
    ACTION_REOPENED = LISTING_REPORT_UPDATE_ACTION_REOPENED

    ACTION_CHOICES = LISTING_REPORT_UPDATE_ACTION_CHOICES

    report = models.ForeignKey(ListingReport, on_delete=models.CASCADE, related_name="updates")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="listing_report_updates",
    )
    action = models.CharField(max_length=24, choices=ACTION_CHOICES)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["report", "created_at"], name="list_rep_upd_report_idx"),
            models.Index(fields=["actor", "created_at"], name="list_rep_upd_actor_idx"),
        ]

    def __str__(self):
        return f"Update for report {self.report_id}: {self.get_action_display()}"
