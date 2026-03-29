from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Mapping, Sequence

SLEEP_SCHEDULES = (
    ("early", "Early riser"),
    ("balanced", "Balanced"),
    ("late", "Night owl"),
)


@dataclass(frozen=True)
class BudgetRange:
    minimum: Decimal
    maximum: Decimal

    @property
    def is_valid(self) -> bool:
        return self.minimum <= self.maximum

    @property
    def midpoint(self) -> Decimal:
        return (self.minimum + self.maximum) / Decimal("2")

    @property
    def span(self) -> Decimal:
        return self.maximum - self.minimum


@dataclass(frozen=True)
class Preferences:
    budget: BudgetRange
    cleanliness: int
    social: int
    sleep_schedule: str
    desired_group_min: int
    desired_group_max: int
    location_keywords: tuple[str, ...] = ()


@dataclass
class GroupOption:
    option_id: str
    group_size: int
    fit_score: int
    budget_range: BudgetRange
    label: str
    headline: str
    summary: str
    market_temperature: str
    listings_count: int = 0
    listings: Sequence | None = None
    median_price_per_person: Decimal | None = None
    average_bathrooms_per_person: Decimal | None = None
    dominant_property_type: str = ""
    top_localities: tuple[str, ...] = ()
    inventory_score: int = 0
    price_score: int = 0
    size_score: int = 0
    comfort_score: int = 0


def _round_decimal(value: Decimal | None, digits: str = "0.1") -> Decimal | None:
    if value is None:
        return None
    return value.quantize(Decimal(digits), rounding=ROUND_HALF_UP)


def _median_decimal(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None

    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def _average_decimal(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _scenario_size_range(*, base_unit_size: int, preferences: Preferences) -> range:
    minimum = max(base_unit_size, preferences.desired_group_min)
    maximum = max(minimum, preferences.desired_group_max)
    return range(minimum, maximum + 1)


def _target_group_size(*, base_unit_size: int, preferences: Preferences) -> int:
    minimum = max(base_unit_size, preferences.desired_group_min)
    maximum = max(minimum, preferences.desired_group_max)
    if minimum == maximum:
        return minimum
    relative_preference = Decimal(preferences.social - 1) / Decimal("4")
    return minimum + round((maximum - minimum) * float(relative_preference))


def _size_score(*, group_size: int, base_unit_size: int, preferences: Preferences) -> int:
    minimum = max(base_unit_size, preferences.desired_group_min)
    maximum = max(minimum, preferences.desired_group_max)
    target_size = _target_group_size(base_unit_size=base_unit_size, preferences=preferences)
    max_distance = max(abs(minimum - target_size), abs(maximum - target_size), 1)
    distance = abs(group_size - target_size)
    return round(max(0.0, 1.0 - (distance / max_distance)) * 100)


def _price_score(median_price_per_person: Decimal | None, budget: BudgetRange) -> int:
    if median_price_per_person is None or not budget.is_valid:
        return 0

    half_span = budget.span / Decimal("2")
    if half_span <= 0:
        return 100 if median_price_per_person == budget.minimum else 0

    distance = abs(median_price_per_person - budget.midpoint)
    if distance >= half_span:
        return 0
    return round((1 - float(distance / half_span)) * 100)


def _comfort_target(cleanliness: int, sleep_schedule: str) -> Decimal:
    target = Decimal("0.35") + (Decimal(cleanliness - 1) * Decimal("0.05"))
    if sleep_schedule == "early":
        target += Decimal("0.05")
    return min(target, Decimal("0.65"))


def _comfort_score(
    average_bathrooms_per_person: Decimal | None,
    *,
    cleanliness: int,
    sleep_schedule: str,
) -> int:
    if average_bathrooms_per_person is None:
        return 0

    target = _comfort_target(cleanliness, sleep_schedule)
    max_delta = Decimal("0.35")
    delta = min(abs(average_bathrooms_per_person - target), max_delta)
    return round((1 - float(delta / max_delta)) * 100)


def _inventory_score(listings_count: int, max_inventory: int) -> int:
    if max_inventory <= 0:
        return 0
    return round((listings_count / max_inventory) * 100)


def _fit_score(*, inventory_score: int, price_score: int, size_score: int, comfort_score: int) -> int:
    weighted_total = inventory_score * 0.30 + price_score * 0.34 + size_score * 0.22 + comfort_score * 0.14
    return round(weighted_total)


def _listing_price_per_person(listing) -> Decimal:
    rooms = max(getattr(listing, "rooms", 1) or 1, 1)
    return Decimal(str(listing.price)) / Decimal(rooms)


def _listing_bathrooms_per_person(listing, *, group_size: int) -> Decimal:
    size = max(group_size, 1)
    return Decimal(str(listing.bathrooms)) / Decimal(size)


def _listing_locality(listing) -> str:
    address = (getattr(listing, "address", "") or "").strip()
    if not address:
        return ""
    parts = [part.strip() for part in address.split(",") if part.strip()]
    if len(parts) >= 2:
        return parts[1]
    return parts[0]


def _top_localities(listings: Sequence, *, limit: int = 2) -> tuple[str, ...]:
    counts = Counter(filter(None, (_listing_locality(listing) for listing in listings)))
    return tuple(locality for locality, _ in counts.most_common(limit))


def _dominant_property_type(listings: Sequence) -> str:
    counts = Counter(getattr(listing, "get_property_type_display")() for listing in listings)
    if not counts:
        return ""
    property_type, count = counts.most_common(1)[0]
    if count == len(listings):
        return property_type
    return f"Mostly {property_type.lower()}s"


def _market_temperature(listings_count: int) -> str:
    if listings_count == 0:
        return "No live inventory"
    if listings_count == 1:
        return "Single strong match"
    if listings_count <= 3:
        return "Limited inventory"
    if listings_count <= 7:
        return "Healthy inventory"
    return "Deep inventory"


def _scenario_tone(preferences: Preferences) -> str:
    if preferences.social >= 4 and preferences.cleanliness >= 4:
        return "high-alignment"
    if preferences.social >= 4:
        return "social"
    if preferences.cleanliness >= 4 and preferences.sleep_schedule == "early":
        return "quiet"
    if preferences.sleep_schedule == "late":
        return "late-night"
    return "balanced"


def _scenario_label(*, group_size: int, preferences: Preferences) -> str:
    tone = _scenario_tone(preferences)
    if tone == "high-alignment":
        return f"{group_size}-person curated plan"
    if tone == "social":
        return f"{group_size}-person social plan"
    if tone == "quiet":
        return f"{group_size}-person quiet plan"
    if tone == "late-night":
        return f"{group_size}-person night-owl plan"
    return f"{group_size}-person balanced plan"


def _scenario_headline(
    *,
    listings_count: int,
    median_price_per_person: Decimal | None,
    top_localities: tuple[str, ...],
) -> str:
    if listings_count == 0:
        return "No live matches yet for this setup."

    locality_clause = ""
    if top_localities:
        locality_clause = f" in {', '.join(top_localities)}"

    if median_price_per_person is None:
        return f"{listings_count} listing{'s' if listings_count != 1 else ''}{locality_clause}"

    return (
        f"{listings_count} listing{'s' if listings_count != 1 else ''}{locality_clause} "
        f"around ${median_price_per_person:,.0f} per person"
    )


def _scenario_summary(
    *,
    group_size: int,
    listings_count: int,
    dominant_property_type: str,
    top_localities: tuple[str, ...],
    preferences: Preferences,
) -> str:
    if listings_count == 0:
        if preferences.location_keywords:
            return "Widen the area focus or adjust budget to surface inventory for this group size."
        return "Adjust the budget band or target household size to surface more inventory."

    property_clause = dominant_property_type or "shared homes"
    locality_clause = ", ".join(top_localities) if top_localities else "the current search area"
    return (
        f"This {group_size}-person setup is strongest around {locality_clause} "
        f"with {property_clause.lower()} leading the current inventory mix."
    )


def listing_fit_score(listing, *, group_size: int, preferences: Preferences) -> int:
    price_score = _price_score(_listing_price_per_person(listing), preferences.budget)
    comfort_score = _comfort_score(
        _listing_bathrooms_per_person(listing, group_size=group_size),
        cleanliness=preferences.cleanliness,
        sleep_schedule=preferences.sleep_schedule,
    )
    amenity_bonus = 0
    amenities_text = " ".join(
        filter(
            None,
            [
                getattr(listing, "amenities", ""),
                getattr(listing, "utilities_included", ""),
            ],
        )
    ).lower()
    if "dishwasher" in amenities_text or "laundry" in amenities_text:
        amenity_bonus += 8
    if getattr(listing, "is_furnished", False):
        amenity_bonus += 4

    weighted_total = price_score * 0.68 + comfort_score * 0.24 + amenity_bonus
    return round(min(weighted_total, 100))


def rank_listings_for_group(listings: Sequence, *, group_size: int, preferences: Preferences) -> list:
    return sorted(
        listings,
        key=lambda listing: (
            listing_fit_score(listing, group_size=group_size, preferences=preferences),
            getattr(listing, "created_at", None),
        ),
        reverse=True,
    )


def build_group_options(
    *,
    base_unit_size: int,
    preferences: Preferences,
    listings_by_size: Mapping[int, Sequence],
    max_options: int = 6,
) -> list[GroupOption]:
    size_range = list(_scenario_size_range(base_unit_size=base_unit_size, preferences=preferences))
    if not size_range:
        return []

    max_inventory = max(len(listings_by_size.get(group_size, ())) for group_size in size_range)
    target_group_size = _target_group_size(base_unit_size=base_unit_size, preferences=preferences)
    options: list[GroupOption] = []

    for group_size in size_range:
        listings = list(listings_by_size.get(group_size, ()))
        ranked_listings = rank_listings_for_group(listings, group_size=group_size, preferences=preferences)
        price_points = [_listing_price_per_person(listing) for listing in ranked_listings]
        bathroom_ratios = [_listing_bathrooms_per_person(listing, group_size=group_size) for listing in ranked_listings]
        median_price_per_person = _round_decimal(_median_decimal(price_points))
        average_bathrooms_per_person = _round_decimal(_average_decimal(bathroom_ratios))
        top_localities = _top_localities(ranked_listings)
        dominant_property_type = _dominant_property_type(ranked_listings)

        inventory_score = _inventory_score(len(ranked_listings), max_inventory)
        price_score = _price_score(median_price_per_person, preferences.budget)
        size_score = _size_score(group_size=group_size, base_unit_size=base_unit_size, preferences=preferences)
        comfort_score = _comfort_score(
            average_bathrooms_per_person,
            cleanliness=preferences.cleanliness,
            sleep_schedule=preferences.sleep_schedule,
        )

        options.append(
            GroupOption(
                option_id=f"group-{group_size}",
                group_size=group_size,
                fit_score=_fit_score(
                    inventory_score=inventory_score,
                    price_score=price_score,
                    size_score=size_score,
                    comfort_score=comfort_score,
                ),
                budget_range=preferences.budget,
                label=_scenario_label(group_size=group_size, preferences=preferences),
                headline=_scenario_headline(
                    listings_count=len(ranked_listings),
                    median_price_per_person=median_price_per_person,
                    top_localities=top_localities,
                ),
                summary=_scenario_summary(
                    group_size=group_size,
                    listings_count=len(ranked_listings),
                    dominant_property_type=dominant_property_type,
                    top_localities=top_localities,
                    preferences=preferences,
                ),
                market_temperature=_market_temperature(len(ranked_listings)),
                listings_count=len(ranked_listings),
                listings=ranked_listings,
                median_price_per_person=median_price_per_person,
                average_bathrooms_per_person=average_bathrooms_per_person,
                dominant_property_type=dominant_property_type,
                top_localities=top_localities,
                inventory_score=inventory_score,
                price_score=price_score,
                size_score=size_score,
                comfort_score=comfort_score,
            )
        )

    options.sort(
        key=lambda option: (
            option.listings_count > 0,
            option.fit_score,
            option.listings_count,
            -abs(option.group_size - target_group_size),
        ),
        reverse=True,
    )
    return options[:max_options]
