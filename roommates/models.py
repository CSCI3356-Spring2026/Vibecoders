from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

ROOMMATE_POST_HOUSING_HAVE_HOME = "have_home"
ROOMMATE_POST_HOUSING_NEED_HOME = "need_home"
ROOMMATE_POST_HOUSING_CHOICES = [
    (ROOMMATE_POST_HOUSING_HAVE_HOME, "Already have a place"),
    (ROOMMATE_POST_HOUSING_NEED_HOME, "Still need a place"),
]
ROOMMATE_POST_HOUSING_VALUES = tuple(value for value, _ in ROOMMATE_POST_HOUSING_CHOICES)


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
                Q(
                    author__is_active=True,
                    author__role="student",
                    author__profile_completed_at__isnull=False,
                )
                | Q(
                    group__lead__is_active=True,
                    group__lead__role="student",
                    group__lead__profile_completed_at__isnull=False,
                    group__is_active=True,
                )
            )
        )


class RoommateGroup(models.Model):
    lead = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="led_roommate_group")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="RoommateGroupMembership",
        related_name="roommate_groups",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "listings_roommategroup"
        ordering = ["-updated_at", "-created_at"]
        indexes = [
            models.Index(fields=["is_active", "updated_at"], name="roommate_group_active_idx"),
        ]

    def __str__(self):
        return self.name

    @property
    def member_count(self):
        prefetched = getattr(self, "_prefetched_objects_cache", {})
        members = prefetched.get("members")
        if members is not None:
            return len(members)
        return self.members.count()

    @property
    def member_names(self):
        prefetched = getattr(self, "_prefetched_objects_cache", {})
        members = prefetched.get("members")
        if members is None:
            members = self.members.all()
        return [member.display_name for member in members]

    def clean(self):
        super().clean()
        if not self.lead_id:
            return
        user_model = get_user_model()
        if not user_model._default_manager.filter(
            pk=self.lead_id,
            role="student",
            is_active=True,
            profile_completed_at__isnull=False,
        ).exists():
            raise ValidationError({"name": "Only students with completed roommate profiles can lead a group."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class RoommateGroupMembership(models.Model):
    group = models.ForeignKey(RoommateGroup, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="roommate_memberships")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "listings_roommategroupmembership"
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["group", "user"], name="roommate_group_membership_unique"),
            models.UniqueConstraint(fields=["user"], name="roommate_group_membership_one_group_per_user"),
        ]
        indexes = [
            models.Index(fields=["group", "created_at"], name="roommate_group_member_idx"),
            models.Index(fields=["user", "created_at"], name="roommate_group_user_idx"),
        ]

    def clean(self):
        super().clean()
        if not self.user_id:
            return
        user_model = get_user_model()
        if not user_model._default_manager.filter(
            pk=self.user_id,
            role="student",
            is_active=True,
            profile_completed_at__isnull=False,
        ).exists():
            raise ValidationError({"user": "Only students with completed roommate profiles can join a group."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class RoommatePost(models.Model):
    HOUSING_HAVE_HOME = ROOMMATE_POST_HOUSING_HAVE_HOME
    HOUSING_NEED_HOME = ROOMMATE_POST_HOUSING_NEED_HOME
    HOUSING_CHOICES = ROOMMATE_POST_HOUSING_CHOICES

    author = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="roommate_post",
        null=True,
        blank=True,
    )
    group = models.OneToOneField(
        RoommateGroup,
        on_delete=models.CASCADE,
        related_name="roommate_post",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=120)
    description = models.TextField()
    housing_status = models.CharField(
        max_length=16,
        choices=HOUSING_CHOICES,
        default=HOUSING_NEED_HOME,
        db_index=True,
    )
    current_group_size = models.PositiveSmallIntegerField(default=1)
    open_spots = models.PositiveSmallIntegerField(default=None, null=True, blank=True)
    budget_min = models.DecimalField(max_digits=8, decimal_places=0)
    budget_max = models.DecimalField(max_digits=8, decimal_places=0)
    move_in_date = models.DateField(db_index=True)
    neighborhoods = models.CharField(max_length=240, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = RoommatePostQuerySet.as_manager()

    class Meta:
        db_table = "listings_roommatepost"
        ordering = ["-updated_at", "-created_at"]
        indexes = [
            models.Index(fields=["is_active", "updated_at"], name="roommate_post_active_idx"),
            models.Index(fields=["housing_status", "move_in_date"], name="roommate_post_housing_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(Q(author__isnull=False) & Q(group__isnull=True))
                | (Q(author__isnull=True) & Q(group__isnull=False)),
                name="roommate_post_exactly_one_owner",
            ),
            models.CheckConstraint(
                condition=Q(housing_status__in=ROOMMATE_POST_HOUSING_VALUES),
                name="roommate_post_housing_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(current_group_size__gte=1),
                name="roommate_post_group_size_gte_one",
            ),
            models.CheckConstraint(
                condition=(
                    Q(housing_status=ROOMMATE_POST_HOUSING_HAVE_HOME, open_spots__gte=1)
                    | (
                        Q(housing_status__in=[ROOMMATE_POST_HOUSING_NEED_HOME])
                        & (Q(open_spots__isnull=True) | Q(open_spots__gte=1))
                    )
                ),
                name="roommate_post_open_spots_valid",
            ),
            models.CheckConstraint(
                condition=Q(budget_min__gte=0),
                name="roommate_post_budget_min_gte_zero",
            ),
            models.CheckConstraint(
                condition=Q(budget_max__gte=0),
                name="roommate_post_budget_max_gte_zero",
            ),
            models.CheckConstraint(
                condition=Q(budget_max__gte=F("budget_min")),
                name="roommate_post_budget_max_gte_min",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.owner_display_name})"

    @property
    def target_household_size(self):
        if self.open_spots is None:
            return None
        return self.current_group_size + self.open_spots

    @property
    def owner_user(self):
        if self.group_id:
            return self.group.lead
        return self.author

    @property
    def owner_display_name(self):
        if self.group_id:
            return self.group.name
        if self.author_id:
            return self.author.display_name
        return ""

    @property
    def lead_user(self):
        return self.owner_user

    @property
    def member_users(self):
        if self.group_id:
            prefetched = getattr(self.group, "_prefetched_objects_cache", {})
            members = prefetched.get("members")
            return list(members) if members is not None else list(self.group.members.all())
        return [self.author] if self.author_id else []

    @property
    def neighborhoods_list(self):
        return [item.strip() for item in self.neighborhoods.split(",") if item.strip()]

    def clean(self):
        super().clean()
        if bool(self.author_id) == bool(self.group_id):
            raise ValidationError({"title": "Choose either an individual post owner or a group owner."})

        user_model = get_user_model()
        if (
            self.author_id
            and not user_model._default_manager.filter(
                pk=self.author_id,
                role="student",
                is_active=True,
                profile_completed_at__isnull=False,
            ).exists()
        ):
            raise ValidationError({"title": "Only students with completed roommate profiles can post."})
        if self.group_id:
            if not RoommateGroup.objects.filter(
                pk=self.group_id,
                is_active=True,
                lead__role="student",
                lead__is_active=True,
                lead__profile_completed_at__isnull=False,
            ).exists():
                raise ValidationError({"title": "Only active student groups with completed profiles can post."})
            self.current_group_size = self.group.member_count

        if self.budget_min is not None and self.budget_max is not None and self.budget_min > self.budget_max:
            raise ValidationError({"budget_max": "Budget max must be greater than or equal to budget min."})
        if self.housing_status == self.HOUSING_HAVE_HOME and self.open_spots is None:
            raise ValidationError({"open_spots": "Add how many open roommate spots you have."})
        if self.open_spots is not None and self.open_spots < 1:
            raise ValidationError({"open_spots": "Open roommate spots must be at least 1."})
        if self.move_in_date and self.move_in_date < timezone.localdate():
            raise ValidationError({"move_in_date": "Move-in date must be today or later."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class RoommateGroupInvite(models.Model):
    STATUS_PENDING_APPROVAL = "pending_approval"
    STATUS_PENDING_INVITEE = "pending_invitee"
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING_APPROVAL, "Awaiting group approval"),
        (STATUS_PENDING_INVITEE, "Awaiting invitee response"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    group = models.ForeignKey(RoommateGroup, on_delete=models.CASCADE, related_name="invites")
    inviter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_roommate_group_invites",
    )
    invitee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_roommate_group_invites",
    )
    conversation = models.ForeignKey(
        "communications.ListingConversation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="roommate_group_invites",
    )
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_PENDING_APPROVAL, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "users_roommategroupinvite"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "invitee"],
                condition=models.Q(status__in=["pending_approval", "pending_invitee"]),
                name="roommate_group_invite_active_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["invitee", "status", "created_at"], name="rg_invite_in_idx"),
            models.Index(fields=["group", "status", "created_at"], name="rg_invite_group_idx"),
        ]

    def __str__(self):
        return f"Invite {self.pk} to {self.invitee_id} ({self.status})"


class RoommateGroupInviteApproval(models.Model):
    invite = models.ForeignKey(RoommateGroupInvite, on_delete=models.CASCADE, related_name="approvals")
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="roommate_group_invite_approvals",
    )
    approved = models.BooleanField(null=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "users_roommategroupinviteapproval"
        constraints = [
            models.UniqueConstraint(fields=["invite", "member"], name="roommate_group_invite_approval_unique"),
        ]
        indexes = [
            models.Index(fields=["member", "responded_at"], name="rg_invite_approval_mem_idx"),
        ]

    def __str__(self):
        return f"InviteApproval({self.invite_id}, {self.member_id})"


class FavoriteRoommate(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorite_roommates",
    )
    favorite_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorited_by_students",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "users_favoriteroommate"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "favorite_user"], name="favorite_roommate_unique_pair"),
            models.CheckConstraint(
                condition=~models.Q(user=models.F("favorite_user")),
                name="favorite_roommate_user_ne_favorite_user",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "created_at"], name="favorite_roommate_user_idx"),
            models.Index(fields=["favorite_user", "created_at"], name="favorite_roommate_target_idx"),
        ]

    def clean(self):
        super().clean()
        if self.user_id and self.favorite_user_id and self.user_id == self.favorite_user_id:
            raise ValidationError({"favorite_user": "You cannot favorite yourself."})
        if self.user_id and getattr(self.user, "role", None) != "student":
            raise ValidationError({"user": "Only student accounts can favorite roommate candidates."})
        if self.favorite_user_id and getattr(self.favorite_user, "role", None) != "student":
            raise ValidationError({"favorite_user": "Only student profiles can be favorited."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user_id}->{self.favorite_user_id}"
