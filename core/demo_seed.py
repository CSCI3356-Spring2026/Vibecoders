from __future__ import annotations

import hashlib
import io
import json
import shutil
import time
from datetime import timedelta
from pathlib import Path

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Q
from django.utils import timezone
from PIL import Image, ImageOps

from communications.models import ListingConversation
from communications.services import (
    send_conversation_message,
    start_direct_conversation,
    start_listing_conversation,
)
from listings.models import (
    Listing,
    ListingFavorite,
    ListingImage,
    ListingReport,
    ListingReportUpdate,
    ListingReview,
)
from listings.report_services import update_listing_report
from roommates.models import (
    FavoriteRoommate,
    RoommateGroup,
    RoommateGroupInvite,
    RoommateGroupMembership,
    RoommatePost,
)
from roommates.services import (
    create_group_invite,
    respond_to_group_invite,
    respond_to_invite_approval,
    save_roommate_group_details,
)
from users.models import (
    ADMIN_PROFILE_ORGANIZATION_INDIVIDUAL_OWNER,
    ADMIN_PROFILE_ORGANIZATION_PROPERTY_COMPANY,
    STUDENT_PROFILE_INSTITUTION_UNDERGRADUATE,
    Role,
    UserFile,
)
from users.profile_integrity import (
    mark_profile_completed_now,
    profile_satisfies_completion_requirements,
)

from .demo_seed_data import (
    DEMO_DIRECT_THREADS,
    DEMO_FAVORITE_ROOMMATES,
    DEMO_GROUP_INVITES,
    DEMO_LISTING_FAVORITES,
    DEMO_LISTING_THREADS,
    DEMO_LISTINGS,
    DEMO_PASSWORD,
    DEMO_PHOTOS,
    DEMO_REPORTS,
    DEMO_ROOMMATE_GROUPS,
    DEMO_ROOMMATE_SOLO_POSTS,
    DEMO_USER_FILES,
    DEMO_USERNAME_PREFIX,
    DEMO_USERS,
    STALE_LEGAL_VERSION,
)

PHOTO_DOWNLOAD_USER_AGENT = "PadlyDemoSeed/1.0 (local development asset cache)"
PHOTO_DOWNLOAD_TIMEOUT = (10, 60)
PHOTO_DOWNLOAD_ATTEMPTS = 5
PHOTO_MAX_DIMENSION = 1800
PHOTO_MIN_DIMENSION = 720
PHOTO_INITIAL_QUALITY = 86
PHOTO_MIN_QUALITY = 56


class DemoSeedError(Exception):
    """Raised when demo-data seeding cannot be completed safely."""


def default_bundle_root():
    return Path(settings.BASE_DIR) / "var" / "demo_seed"


def _sha256_bytes(content):
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_photo_source(photo_spec):
    errors = []
    for attempt in range(1, PHOTO_DOWNLOAD_ATTEMPTS + 1):
        try:
            response = requests.get(
                photo_spec["download_url"],
                headers={"User-Agent": PHOTO_DOWNLOAD_USER_AGENT},
                timeout=PHOTO_DOWNLOAD_TIMEOUT,
                allow_redirects=True,
            )
            if response.status_code in {429, 500, 502, 503, 504} and attempt < PHOTO_DOWNLOAD_ATTEMPTS:
                retry_after = response.headers.get("Retry-After", "").strip()
                if retry_after.isdigit():
                    sleep_seconds = max(1, int(retry_after))
                else:
                    sleep_seconds = 5 * attempt
                time.sleep(sleep_seconds)
                continue
            response.raise_for_status()
            content = response.content
            digest = _sha256_bytes(content)
            if digest != photo_spec["sha256"]:
                raise DemoSeedError(
                    f"Photo hash mismatch for {photo_spec['key']}: expected {photo_spec['sha256']}, got {digest}."
                )
            return content
        except (requests.RequestException, DemoSeedError) as exc:
            errors.append(str(exc))
            if attempt < PHOTO_DOWNLOAD_ATTEMPTS:
                time.sleep(attempt)
                continue
    joined_errors = " | ".join(errors)
    raise DemoSeedError(f"Unable to download photo {photo_spec['key']}: {joined_errors}")


def _pdf_escape(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf_bytes(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()] or ["Padly demo document"]
    stream_commands = ["BT", "/F1 12 Tf", "72 720 Td"]
    first_line = True
    for line in lines:
        escaped = _pdf_escape(line)
        if not first_line:
            stream_commands.append("0 -18 Td")
        stream_commands.append(f"({escaped}) Tj")
        first_line = False
    stream_commands.append("ET")
    stream = "\n".join(stream_commands).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
    ]

    parts = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(sum(len(part) for part in parts))
        parts.append(f"{index} 0 obj\n".encode("ascii"))
        parts.append(obj)
        parts.append(b"\nendobj\n")

    xref_offset = sum(len(part) for part in parts)
    parts.append(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    parts.append(b"0000000000 65535 f \n")
    for offset in offsets:
        parts.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    parts.append(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode("ascii"))
    parts.append(f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    return b"".join(parts)


class DemoSeedRunner:
    def __init__(
        self,
        *,
        bundle_root=None,
        reference_date=None,
        refresh_photo_cache=False,
        skip_image_downloads=False,
        stdout=None,
    ):
        self.reference_date = reference_date or timezone.localdate()
        if self.reference_date < timezone.localdate():
            raise DemoSeedError(
                "Reference date cannot be in the past because active roommate posts would fail validation."
            )

        self.bundle_root = Path(bundle_root or default_bundle_root())
        self.refresh_photo_cache = refresh_photo_cache
        self.skip_image_downloads = skip_image_downloads
        self.stdout = stdout
        self.user_model = get_user_model()

        self.photo_source_dir = self.bundle_root / "photos" / "source"
        self.photo_processed_dir = self.bundle_root / "photos" / "processed"
        self.generated_file_dir = self.bundle_root / "generated_files"
        self.summary_json_path = self.bundle_root / "seed_summary.json"
        self.summary_text_path = self.bundle_root / "seed_summary.txt"

        self.users = {}
        self.listings = {}
        self.roommate_groups = {}
        self.roommate_posts = {}
        self.roommate_invites = {}
        self.photo_metadata = {}

    def seed(self):
        self._ensure_debug_mode()
        self._ensure_directories()
        self._prepare_photo_cache()
        self._clear_existing_demo_namespace()

        self._create_users()
        self._create_listings()
        self._create_listing_threads()
        self._create_listing_favorites()
        self._create_listing_reports()
        self._apply_owner_archives()
        self._create_roommate_solo_posts()
        self._create_roommate_groups_and_posts()
        self._create_direct_threads()
        self._create_group_invites()
        self._create_favorite_roommates()
        self._create_user_files()

        summary = self._build_summary()
        self._write_summary(summary)
        return summary

    def _log(self, message):
        if self.stdout is not None:
            self.stdout.write(message)

    def _ensure_debug_mode(self):
        if settings.DEBUG:
            return
        raise DemoSeedError("seed_demo_data is restricted to DJANGO_DEBUG=true because it creates local demo media.")

    def _ensure_directories(self):
        for directory in (
            self.bundle_root,
            self.photo_source_dir,
            self.photo_processed_dir,
            self.generated_file_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        self._prune_directory(self.photo_source_dir, {photo["filename"] for photo in DEMO_PHOTOS})
        self._prune_directory(self.photo_processed_dir, {f"{photo['key']}.jpg" for photo in DEMO_PHOTOS})

        for child in self.generated_file_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    def _prune_directory(self, directory, expected_names):
        for child in directory.iterdir():
            if child.is_file() and child.name not in expected_names:
                child.unlink()

    def _prepare_photo_cache(self):
        for photo_spec in DEMO_PHOTOS:
            source_path = self.photo_source_dir / photo_spec["filename"]
            processed_path = self.photo_processed_dir / f"{photo_spec['key']}.jpg"

            if self.refresh_photo_cache and source_path.exists():
                source_path.unlink()
            if self.refresh_photo_cache and processed_path.exists():
                processed_path.unlink()

            if source_path.exists() and _sha256_file(source_path) != photo_spec["sha256"]:
                if self.skip_image_downloads:
                    raise DemoSeedError(
                        f"Cached source photo for {photo_spec['key']} has the wrong hash and downloads are disabled."
                    )
                source_path.unlink()

            if not source_path.exists():
                if self.skip_image_downloads:
                    raise DemoSeedError(
                        f"Missing cached source photo for {photo_spec['key']} and --skip-image-downloads was used."
                    )
                self._log(f"Downloading listing photo: {photo_spec['key']}")
                source_path.write_bytes(download_photo_source(photo_spec))

            if processed_path.exists() and processed_path.stat().st_size > settings.LISTING_IMAGE_MAX_BYTES:
                processed_path.unlink()

            if not processed_path.exists():
                self._log(f"Normalizing listing photo: {photo_spec['key']}")
                metadata = self._normalize_listing_photo(source_path, processed_path)
            else:
                metadata = self._processed_photo_metadata(processed_path)

            self.photo_metadata[photo_spec["key"]] = {
                "key": photo_spec["key"],
                "title": photo_spec["title"],
                "author": photo_spec["author"],
                "license": photo_spec["license"],
                "source_page_url": photo_spec["source_page_url"],
                "download_url": photo_spec["download_url"],
                "source_sha256": photo_spec["sha256"],
                "source_path": str(source_path),
                "processed_path": str(processed_path),
                **metadata,
            }

    def _normalize_listing_photo(self, source_path, destination_path):
        max_bytes = settings.LISTING_IMAGE_MAX_BYTES
        with Image.open(source_path) as image:
            normalized = ImageOps.exif_transpose(image)
            if normalized.mode != "RGB":
                normalized = normalized.convert("RGB")

            dimension = PHOTO_MAX_DIMENSION
            quality = PHOTO_INITIAL_QUALITY
            while True:
                candidate = normalized.copy()
                candidate.thumbnail((dimension, dimension), Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                candidate.save(
                    buffer,
                    format="JPEG",
                    quality=quality,
                    optimize=True,
                    progressive=True,
                )
                content = buffer.getvalue()
                if len(content) <= max_bytes or (dimension <= PHOTO_MIN_DIMENSION and quality <= PHOTO_MIN_QUALITY):
                    destination_path.write_bytes(content)
                    return {
                        "processed_sha256": _sha256_bytes(content),
                        "processed_size_bytes": len(content),
                        "processed_width": candidate.width,
                        "processed_height": candidate.height,
                    }

                if quality > PHOTO_MIN_QUALITY:
                    quality = max(PHOTO_MIN_QUALITY, quality - 6)
                else:
                    dimension = max(PHOTO_MIN_DIMENSION, int(dimension * 0.85))
                    quality = PHOTO_INITIAL_QUALITY

    def _processed_photo_metadata(self, processed_path):
        with Image.open(processed_path) as image:
            width, height = image.size
        return {
            "processed_sha256": _sha256_file(processed_path),
            "processed_size_bytes": processed_path.stat().st_size,
            "processed_width": width,
            "processed_height": height,
        }

    def _clear_existing_demo_namespace(self):
        deleted, _ = self.user_model._default_manager.filter(username__startswith=DEMO_USERNAME_PREFIX).delete()
        if deleted:
            self._log(f"Cleared existing demo rows: {deleted}")

    def _create_users(self):
        self._log("Creating demo users")
        for spec in DEMO_USERS:
            expected_role = Role(self.user_model.normalize_role_value(spec["role"]))
            user = self.user_model(
                username=spec["username"],
                email=spec["email"],
                first_name=spec["first_name"],
                last_name=spec["last_name"],
                is_active=True,
                is_staff=spec.get("is_staff", False),
                is_superuser=spec.get("is_superuser", False),
            )
            if expected_role in {Role.ADMIN, Role.MODERATOR, Role.SUPPORT}:
                user.set_staff_role(expected_role)
            user.save()

            if expected_role != user.role:
                raise DemoSeedError(
                    "Demo user "
                    f"{spec['username']} resolved to role {user.role} instead of the expected {expected_role}."
                )

            if expected_role == Role.ADMIN and spec.get("is_staff"):
                user.set_password(DEMO_PASSWORD)
            else:
                user.set_unusable_password()
            user.save(update_fields=["password"])

            self._apply_legal_state(user, spec["legal_state"])
            self._apply_profile_data(user, spec)
            self.users[spec["key"]] = user

    def _apply_legal_state(self, user, state):
        accepted_at = timezone.now() - timedelta(days=10)
        if state == "current":
            user.privacy_accepted_at = accepted_at - timedelta(minutes=2)
            user.terms_accepted_at = accepted_at
            user.legal_policy_version = settings.LEGAL_DOCUMENT_VERSION
        elif state == "stale":
            user.privacy_accepted_at = accepted_at - timedelta(minutes=2)
            user.terms_accepted_at = accepted_at
            user.legal_policy_version = STALE_LEGAL_VERSION
        elif state == "missing":
            user.privacy_accepted_at = None
            user.terms_accepted_at = None
            user.legal_policy_version = ""
        else:
            raise DemoSeedError(f"Unknown legal state {state!r} for {user.username}.")

        user.save(update_fields=["privacy_accepted_at", "terms_accepted_at", "legal_policy_version"])

    def _apply_profile_data(self, user, spec):
        profile_data = spec.get("profile")
        expected_role = Role(self.user_model.normalize_role_value(spec["role"]))
        if expected_role == Role.STUDENT:
            if profile_data:
                profile = user.student_profile
                profile.institution_status = profile_data.get(
                    "institution_status",
                    STUDENT_PROFILE_INSTITUTION_UNDERGRADUATE,
                )
                for field_name, value in profile_data.items():
                    setattr(profile, field_name, value)
                profile.save()
                if profile_satisfies_completion_requirements(user):
                    mark_profile_completed_now(user)
        elif expected_role in {Role.ADMIN, Role.MODERATOR, Role.SUPPORT, Role.REALTOR} and profile_data:
            profile = user.admin_profile
            if expected_role == Role.REALTOR:
                profile.organization_type = profile_data.get(
                    "organization_type",
                    ADMIN_PROFILE_ORGANIZATION_PROPERTY_COMPANY,
                )
                profile.organization_name = profile_data.get("organization_name") or f"{user.display_name} Housing"
            elif expected_role in {Role.ADMIN, Role.MODERATOR, Role.SUPPORT}:
                profile.organization_type = profile_data.get(
                    "organization_type",
                    ADMIN_PROFILE_ORGANIZATION_INDIVIDUAL_OWNER,
                )
            for field_name, value in profile_data.items():
                setattr(profile, field_name, value)
            profile.save()
            if profile_satisfies_completion_requirements(user):
                mark_profile_completed_now(user)

    def _create_listings(self):
        self._log("Creating demo listings")
        reviewer = self.users["nadia_admin"]
        for spec in DEMO_LISTINGS:
            listing = Listing(
                owner=self.users[spec["owner"]],
                title=spec["title"],
                address=spec["address"],
                latitude=spec["latitude"],
                longitude=spec["longitude"],
                price=spec["price"],
                description=spec["description"],
                start_date=self.reference_date + timedelta(days=spec["start_offset_days"]),
                end_date=self.reference_date + timedelta(days=spec["end_offset_days"]),
                lease_type=spec["lease_type"],
                status=spec["status"],
                rooms=spec["rooms"],
                bathrooms=spec["bathrooms"],
                sq_ft=spec["sq_ft"],
                property_type=spec["property_type"],
                space_type=spec.get("space_type", Listing.SPACE_ENTIRE_UNIT),
                has_yard=spec["has_yard"],
                has_parking=spec["has_parking"],
                is_furnished=spec["is_furnished"],
                distance_to_campus=spec["distance_to_campus"],
                utilities_estimate=spec["utilities_estimate"],
                parking_fee=spec["parking_fee"],
                security_deposit=spec["security_deposit"],
                application_fee=spec["application_fee"],
                broker_fee=spec.get("broker_fee", "0.00"),
                landlord_approval_required=spec.get("landlord_approval_required", False),
                original_lease_holder=spec.get("original_lease_holder", ""),
                documentation_type=spec.get("documentation_type", ""),
                no_stairs=spec.get("no_stairs", False),
                utilities_included=spec["utilities_included"],
                pet_policy=spec["pet_policy"],
                amenities=spec["amenities"],
                security_features=spec["security_features"],
                renter_requirements=spec.get("renter_requirements", ""),
            )
            listing.save()

            if spec["approval_status"] == Listing.APPROVAL_APPROVED:
                listing.approve(reviewer=reviewer, notes=spec["approval_notes"])
                listing.save(
                    update_fields=[
                        "approval_status",
                        "reviewed_by",
                        "reviewed_at",
                        "approved_at",
                        "approval_notes",
                        "submitted_for_approval_at",
                    ]
                )
            elif spec["approval_status"] == Listing.APPROVAL_REJECTED:
                listing.reject(reviewer=reviewer, notes=spec["approval_notes"])
                listing.save(
                    update_fields=[
                        "approval_status",
                        "reviewed_by",
                        "reviewed_at",
                        "approved_at",
                        "approval_notes",
                        "submitted_for_approval_at",
                    ]
                )
            elif spec["approval_status"] != Listing.APPROVAL_PENDING:
                raise DemoSeedError(f"Unknown approval status {spec['approval_status']!r} for listing {spec['key']}.")

            for index, photo_key in enumerate(spec["photos"], start=1):
                ListingImage.objects.create(
                    listing=listing,
                    image=self._listing_photo_upload(photo_key, listing_key=spec["key"], position=index),
                )

            self.listings[spec["key"]] = listing

    def _listing_photo_upload(self, photo_key, *, listing_key, position):
        processed_path = Path(self.photo_metadata[photo_key]["processed_path"])
        filename = f"{listing_key}-{position}.jpg"
        return SimpleUploadedFile(filename, processed_path.read_bytes(), content_type="image/jpeg")

    def _create_listing_threads(self):
        self._log("Creating listing conversations and reviews")
        for spec in DEMO_LISTING_THREADS:
            listing = self.listings[spec["listing"]]
            participant = self.users[spec["participant"]]
            first_sender, first_body = spec["messages"][0]
            if first_sender != "participant":
                raise DemoSeedError(
                    f"First listing-thread message for {spec['listing']} must be sent by the participant."
                )

            conversation, _, _ = start_listing_conversation(listing, participant, first_body)
            for sender_role, body in spec["messages"][1:]:
                sender = listing.owner if sender_role == "owner" else participant
                send_conversation_message(conversation, sender, body)

            review_spec = spec.get("review")
            if review_spec:
                ListingReview.objects.create(
                    listing=listing,
                    author=self.users[review_spec["author"]],
                    rating=review_spec["rating"],
                    comment=review_spec["comment"],
                )

    def _create_listing_favorites(self):
        self._log("Creating listing favorites")
        for user_key, listing_key in DEMO_LISTING_FAVORITES:
            ListingFavorite.objects.create(user=self.users[user_key], listing=self.listings[listing_key])

    def _create_listing_reports(self):
        self._log("Creating listing reports")
        for spec in DEMO_REPORTS:
            report = ListingReport.objects.create(
                listing=self.listings[spec["listing"]],
                reporter=self.users[spec["reporter"]],
                reason=spec["reason"],
                details=spec["details"],
            )
            for step in spec["status_flow"]:
                reviewer_key = step.get("reviewer")
                note = step.get("note", "")
                if reviewer_key is None and step["status"] == ListingReport.STATUS_OPEN:
                    action = step.get("action") or ListingReportUpdate.ACTION_NOTE
                    report.add_update(actor=None, note=note, action=action)
                    continue

                reviewer = self.users[reviewer_key]
                update_listing_report(
                    report,
                    status=step["status"],
                    reviewer=reviewer,
                    resolution_notes=note,
                )
                report.refresh_from_db()
                self.listings[spec["listing"]].refresh_from_db()

    def _apply_owner_archives(self):
        self._log("Applying owner-driven listing archives")
        for spec in DEMO_LISTINGS:
            archive_spec = spec.get("archive")
            if not archive_spec:
                continue
            listing = self.listings[spec["key"]]
            actor = self.users[archive_spec["by"]]
            listing.archive(
                by_user=actor,
                reason=archive_spec["reason"],
                notes=archive_spec.get("notes", ""),
            )
            listing.save(
                update_fields=[
                    "archived_at",
                    "archived_by",
                    "archive_reason",
                    "is_hidden",
                    "approval_notes",
                ]
            )

    def _create_roommate_solo_posts(self):
        self._log("Creating solo roommate posts")
        for spec in DEMO_ROOMMATE_SOLO_POSTS:
            author = self.users[spec["author"]]
            post = RoommatePost.objects.create(
                author=author,
                title=spec["title"],
                description=spec["description"],
                housing_status=spec["housing_status"],
                current_group_size=spec["current_group_size"],
                open_spots=spec["open_spots"],
                budget_min=spec["budget_min"],
                budget_max=spec["budget_max"],
                move_in_date=self.reference_date + timedelta(days=spec["move_in_offset_days"]),
                neighborhoods=spec["neighborhoods"],
            )
            self.roommate_posts[f"solo:{spec['author']}"] = post

    def _create_roommate_groups_and_posts(self):
        self._log("Creating roommate groups and group posts")
        for spec in DEMO_ROOMMATE_GROUPS:
            lead = self.users[spec["lead"]]
            group = save_roommate_group_details(
                lead=lead,
                name=spec["name"],
                description=spec["description"],
            )
            for member_key in spec["members"]:
                RoommateGroupMembership.objects.create(group=group, user=self.users[member_key])
            if spec.get("post"):
                post_spec = spec["post"]
                post = RoommatePost.objects.create(
                    group=group,
                    title=post_spec["title"],
                    description=post_spec["description"],
                    housing_status=post_spec["housing_status"],
                    current_group_size=group.member_count,
                    open_spots=post_spec["open_spots"],
                    budget_min=post_spec["budget_min"],
                    budget_max=post_spec["budget_max"],
                    move_in_date=self.reference_date + timedelta(days=post_spec["move_in_offset_days"]),
                    neighborhoods=post_spec["neighborhoods"],
                )
                self.roommate_posts[f"group:{spec['key']}"] = post
            self.roommate_groups[spec["key"]] = group

    def _create_direct_threads(self):
        self._log("Creating direct roommate chats")
        for spec in DEMO_DIRECT_THREADS:
            first_sender_key, first_body = spec["messages"][0]
            participant_keys = set(spec["participants"])
            if first_sender_key not in participant_keys:
                raise DemoSeedError("Direct-thread participant list does not include the first sender.")

            other_key = next(key for key in spec["participants"] if key != first_sender_key)
            conversation, _, _ = start_direct_conversation(
                self.users[first_sender_key],
                self.users[other_key],
                first_body,
            )
            for sender_key, body in spec["messages"][1:]:
                send_conversation_message(conversation, self.users[sender_key], body)

    def _create_group_invites(self):
        self._log("Creating roommate group invites")
        for spec in DEMO_GROUP_INVITES:
            inviter = self.users[spec["creator"]]
            invitee = self.users[spec["invitee"]]
            invite = create_group_invite(inviter, invitee)
            for approval_response in spec.get("approval_responses", []):
                invite = respond_to_invite_approval(
                    invite,
                    self.users[approval_response["member"]],
                    approve=approval_response["approve"],
                )
            invitee_response = spec.get("invitee_response")
            if invitee_response == "accept":
                invite = respond_to_group_invite(invite, invitee, accept=True)
            elif invitee_response == "decline":
                invite = respond_to_group_invite(invite, invitee, accept=False)
            self.roommate_invites[spec["key"]] = invite

    def _create_favorite_roommates(self):
        self._log("Creating roommate favorites")
        for user_key, favorite_key in DEMO_FAVORITE_ROOMMATES:
            FavoriteRoommate.objects.create(user=self.users[user_key], favorite_user=self.users[favorite_key])

    def _create_user_files(self):
        self._log("Creating private demo files")
        for spec in DEMO_USER_FILES:
            content = self._user_file_bytes(spec)
            source_path = self.generated_file_dir / spec["filename"]
            source_path.write_bytes(content)
            UserFile.objects.create(
                owner=self.users[spec["owner"]],
                title=spec["title"],
                file=SimpleUploadedFile(
                    spec["filename"],
                    content,
                    content_type=spec["content_type"],
                ),
            )

    def _user_file_bytes(self, spec):
        content_type = spec["content_type"]
        if content_type == "text/plain":
            return spec["body"].encode("utf-8")
        if content_type == "application/pdf":
            return build_pdf_bytes(spec["body"])
        raise DemoSeedError(f"Unsupported demo user-file type {content_type!r}.")

    def _build_summary(self):
        demo_users = self.user_model._default_manager.filter(username__startswith=DEMO_USERNAME_PREFIX)
        listings_qs = Listing.objects.filter(owner__username__startswith=DEMO_USERNAME_PREFIX)
        conversations_qs = ListingConversation.objects.filter(
            Q(owner__username__startswith=DEMO_USERNAME_PREFIX)
            | Q(participant__username__startswith=DEMO_USERNAME_PREFIX)
        )
        roommate_groups_qs = RoommateGroup.objects.filter(lead__username__startswith=DEMO_USERNAME_PREFIX)
        roommate_posts_qs = RoommatePost.objects.filter(
            Q(author__username__startswith=DEMO_USERNAME_PREFIX)
            | Q(group__lead__username__startswith=DEMO_USERNAME_PREFIX)
        )
        roommate_invites_qs = RoommateGroupInvite.objects.filter(
            Q(inviter__username__startswith=DEMO_USERNAME_PREFIX)
            | Q(invitee__username__startswith=DEMO_USERNAME_PREFIX)
        )

        listings = []
        for spec in DEMO_LISTINGS:
            listing = self.listings[spec["key"]]
            listing.refresh_from_db()
            listings.append(
                {
                    "key": spec["key"],
                    "id": listing.id,
                    "title": listing.title,
                    "owner_email": listing.owner.email,
                    "status": listing.status,
                    "approval_status": listing.approval_status,
                    "is_archived": listing.is_archived,
                    "archive_reason": listing.archive_reason,
                    "is_hidden": listing.is_hidden,
                }
            )

        users = []
        for spec in DEMO_USERS:
            user = self.users[spec["key"]]
            users.append(
                {
                    "key": spec["key"],
                    "email": user.email,
                    "role": user.role,
                    "profile_completed": user.profile_completed_at is not None,
                    "has_current_legal_acceptance": user.has_current_legal_acceptance,
                }
            )

        return {
            "generated_at": timezone.now().isoformat(),
            "reference_date": self.reference_date.isoformat(),
            "bundle_root": str(self.bundle_root),
            "media_root": str(settings.MEDIA_ROOT),
            "admin_login": {
                "email": self.users["nadia_admin"].email,
                "password": DEMO_PASSWORD,
                "note": "Raw Django admin only when DJANGO_ADMIN_ENABLED=true. Product login remains Google OAuth.",
            },
            "counts": {
                "users": demo_users.count(),
                "students": demo_users.filter(role=Role.STUDENT).count(),
                "realtors": demo_users.filter(role=Role.REALTOR).count(),
                "admins": demo_users.filter(role=Role.ADMIN).count(),
                "listings": listings_qs.count(),
                "archived_listings": listings_qs.filter(archived_at__isnull=False).count(),
                "listing_images": ListingImage.objects.filter(
                    listing__owner__username__startswith=DEMO_USERNAME_PREFIX
                ).count(),
                "listing_favorites": ListingFavorite.objects.filter(
                    listing__owner__username__startswith=DEMO_USERNAME_PREFIX
                ).count(),
                "listing_reviews": ListingReview.objects.filter(
                    listing__owner__username__startswith=DEMO_USERNAME_PREFIX
                ).count(),
                "listing_reports": ListingReport.objects.filter(
                    listing__owner__username__startswith=DEMO_USERNAME_PREFIX
                ).count(),
                "conversations": conversations_qs.count(),
                "messages": sum(conversation.messages.count() for conversation in conversations_qs),
                "roommate_groups": roommate_groups_qs.count(),
                "roommate_posts": roommate_posts_qs.count(),
                "roommate_invites": roommate_invites_qs.count(),
                "favorite_roommates": FavoriteRoommate.objects.filter(
                    user__username__startswith=DEMO_USERNAME_PREFIX
                ).count(),
                "user_files": UserFile.objects.filter(owner__username__startswith=DEMO_USERNAME_PREFIX).count(),
            },
            "users": users,
            "listings": listings,
            "photos": list(self.photo_metadata.values()),
        }

    def _write_summary(self, summary):
        self.summary_json_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

        lines = [
            "Padly demo data seeded",
            f"Reference date: {summary['reference_date']}",
            f"Bundle root: {summary['bundle_root']}",
            f"Media root: {summary['media_root']}",
            "",
            "Counts:",
        ]
        for key, value in summary["counts"].items():
            lines.append(f"- {key}: {value}")
        lines.extend(
            [
                "",
                "Admin login:",
                f"- email: {summary['admin_login']['email']}",
                f"- password: {summary['admin_login']['password']}",
                f"- note: {summary['admin_login']['note']}",
            ]
        )
        self.summary_text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def seed_demo_environment(
    *,
    bundle_root=None,
    reference_date=None,
    refresh_photo_cache=False,
    skip_image_downloads=False,
    stdout=None,
):
    runner = DemoSeedRunner(
        bundle_root=bundle_root,
        reference_date=reference_date,
        refresh_photo_cache=refresh_photo_cache,
        skip_image_downloads=skip_image_downloads,
        stdout=stdout,
    )
    return runner.seed()
