from django.urls import reverse
from django.utils.text import Truncator


def _primary_image_from_prefetch(listing):
    prefetched = getattr(listing, "_prefetched_objects_cache", {})
    images = prefetched.get("images")
    if images is not None:
        return images[0] if images else None
    return listing.images.order_by("id").first()


def listing_marker_payload(listing):
    return {
        "id": listing.id,
        "price": f"${listing.price:.0f}",
        "title": listing.title,
        "lat": round(float(listing.latitude), 6),
        "lng": round(float(listing.longitude), 6),
        "url": reverse("listings:detail", args=[listing.pk]),
    }


def listing_card_payload(listing):
    image = _primary_image_from_prefetch(listing)
    can_favorite = bool(getattr(listing, "can_favorite", False))
    average_rating = getattr(listing, "average_rating", None)
    return {
        "id": listing.id,
        "url": reverse("listings:detail", args=[listing.pk]),
        "favorite_url": reverse("listings:toggle_favorite", args=[listing.pk]) if can_favorite else "",
        "is_favorited": bool(getattr(listing, "is_favorited", False)) if can_favorite else False,
        "title": listing.title,
        "address": listing.address,
        "price": f"${listing.price:.0f}/mo",
        "status": {
            "value": listing.status,
            "label": listing.get_status_display(),
            "state": listing.status.lower(),
        },
        "lease_type": listing.get_lease_type_display(),
        "property_type": listing.get_property_type_display(),
        "is_verified": bool(getattr(listing, "is_verified", False)),
        "average_rating": round(float(average_rating), 1) if average_rating is not None else None,
        "review_count": int(getattr(listing, "review_count", 0) or 0),
        "rooms": listing.rooms,
        "bathrooms": f"{listing.bathrooms:g}",
        "sq_ft": listing.sq_ft,
        "description": Truncator(listing.description).words(14, truncate="..."),
        "image_url": image.versioned_url if image else "",
        "owner_name": listing.owner.display_name,
        "owner_avatar_url": listing.owner.avatar_url,
    }
