from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

import requests


class ListingQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related("owner").prefetch_related("images")

    def visible(self):
        return self.with_related().filter(is_hidden=False)


class Listing(models.Model):
    LEASE_TYPES = [
        ("SUBLEASE", "Sublease"),
        ("FULL", "Full Lease"),
        ("SHORT", "Short-term"),
    ]

    STATUS_CHOICES = [
        ("AVAILABLE", "Available"),
        ("PENDING", "Pending"),
        ("TAKEN", "Taken"),
    ]

    PROPERTY_TYPES = [
        ("apartment", "Apartment"),
        ("house", "House"),
        ("studio", "Studio"),
        ("dorm", "Dormitory"),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="listings")
    title = models.CharField(max_length=200)
    address = models.CharField(max_length=255, help_text="Street address or Area")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, help_text="Latitude for MapLibre")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, help_text="Longitude for MapLibre")
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

    has_yard = models.BooleanField(default=False)
    has_parking = models.BooleanField(default=False)
    is_furnished = models.BooleanField(default=False)

    distance_to_campus = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True, help_text="Distance in miles"
    )

    utilities_included = models.TextField(blank=True, help_text="List included utilities (e.g. WiFi, Water)")
    pet_policy = models.TextField(blank=True)
    amenities = models.TextField(blank=True, help_text="Comma separated list")
    security_features = models.TextField(blank=True)

    is_hidden = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ListingQuerySet.as_manager()
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_address = self.address

    def save(self, *args, **kwargs):
        address_changed = self.address != self._original_address
        coords_missing = not self.latitude or not self.longitude

        if self.address and (address_changed or coords_missing):
            lat, lon = self.geocode_address(self.address)
            if lat and lon:
                self.latitude = lat
                self.longitude = lon
        
        super().save(*args, **kwargs)
        self._original_address = self.address

    def geocode_address(self, address):
        """Helper method to fetch coordinates"""
        url = f"https://photon.komoot.io/api/?q={address}&limit=1&lat=42.36&lon=-71.05"
        headers = {'User-Agent': 'VibecodersProject/1.0'}
        try:
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                if data['features']:
                    # Photon returns [longitude, latitude]
                    lon, lat = data['features'][0]['geometry']['coordinates']
                    return lat, lon
        except Exception as e:
            print(f"Geocoding error for {address}: {e}")
        return None, None

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_hidden", "created_at"], name="listing_feed_idx"),
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
        ]

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date must be on or after the start date."})

    def __str__(self):
        return f"{self.title} - ${self.price}"

    @property
    def primary_image(self):
        prefetched = getattr(self, "_prefetched_objects_cache", {})
        images = prefetched.get("images")
        if images:
            return images[0]
        return self.images.order_by("id").first()


class ListingImage(models.Model):
    listing = models.ForeignKey(Listing, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="listing_photos/")

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"Image for {self.listing.title}"


def get_coords(address):
    #Helper to fetch lat/lng from Photon
    url = f"https://photon.komoot.io/api/?q={address}&limit=1"
    headers = {'User-Agent': 'VibecodersProject/1.0'}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data['features']:
                lon, lat = data['features'][0]['geometry']['coordinates']
                return lat, lon
    except Exception as e:
        print(f"Geocoding error: {e}")
    return None, None