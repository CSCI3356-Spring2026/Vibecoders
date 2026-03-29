from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations
from typing import Sequence

SLEEP_SCHEDULES = (
    ("early", "Early riser"),
    ("balanced", "Balanced"),
    ("late", "Night owl"),
)


@dataclass(frozen=True)
class BudgetRange:
    minimum: Decimal
    maximum: Decimal

    def overlap_ratio(self, other: "BudgetRange") -> float:
        overlap_min = max(self.minimum, other.minimum)
        overlap_max = min(self.maximum, other.maximum)
        if overlap_min >= overlap_max:
            return 0.0
        span_min = min(self.minimum, other.minimum)
        span_max = max(self.maximum, other.maximum)
        span = span_max - span_min
        if span <= 0:
            return 0.0
        return float((overlap_max - overlap_min) / span)

    @property
    def is_valid(self) -> bool:
        return self.minimum <= self.maximum


@dataclass(frozen=True)
class Preferences:
    budget: BudgetRange
    cleanliness: int
    social: int
    sleep_schedule: str
    desired_group_min: int
    desired_group_max: int
    location_keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class Unit:
    unit_id: str
    label: str
    size: int
    preferences: Preferences


@dataclass
class GroupOption:
    option_id: str
    units: tuple[Unit, ...]
    group_size: int
    compatibility_score: int
    budget_range: BudgetRange
    label: str
    listings_count: int = 0
    listings: Sequence | None = None


def _scale_similarity(value_a: int, value_b: int, max_diff: int) -> float:
    return max(0.0, 1.0 - (abs(value_a - value_b) / max_diff))


def _sleep_match_score(schedule_a: str, schedule_b: str) -> float:
    if schedule_a == schedule_b:
        return 1.0
    if "balanced" in (schedule_a, schedule_b):
        return 0.7
    return 0.4


def unit_compatibility(unit_a: Unit, unit_b: Unit) -> int:
    budget_score = unit_a.preferences.budget.overlap_ratio(unit_b.preferences.budget)
    cleanliness_score = _scale_similarity(unit_a.preferences.cleanliness, unit_b.preferences.cleanliness, 4)
    social_score = _scale_similarity(unit_a.preferences.social, unit_b.preferences.social, 4)
    sleep_score = _sleep_match_score(unit_a.preferences.sleep_schedule, unit_b.preferences.sleep_schedule)

    weighted = budget_score * 0.35 + cleanliness_score * 0.2 + social_score * 0.2 + sleep_score * 0.25
    return round(weighted * 100)


def group_compatibility(units: Sequence[Unit]) -> int:
    if len(units) < 2:
        return 100
    scores = [unit_compatibility(unit_a, unit_b) for unit_a, unit_b in combinations(units, 2)]
    return round(sum(scores) / len(scores))


def _group_budget_range(units: Sequence[Unit]) -> BudgetRange:
    minimum = max(unit.preferences.budget.minimum for unit in units)
    maximum = min(unit.preferences.budget.maximum for unit in units)
    return BudgetRange(minimum, maximum)


def _is_group_size_compatible(units: Sequence[Unit], group_size: int) -> bool:
    return all(unit.preferences.desired_group_min <= group_size <= unit.preferences.desired_group_max for unit in units)


def build_group_options(
    base_unit: Unit,
    candidate_units: Sequence[Unit],
    *,
    max_options: int = 6,
) -> list[GroupOption]:
    options: list[GroupOption] = []
    for count in range(1, len(candidate_units) + 1):
        for combo in combinations(candidate_units, count):
            units = (base_unit,) + combo
            group_size = sum(unit.size for unit in units)
            if not _is_group_size_compatible(units, group_size):
                continue

            budget_range = _group_budget_range(units)
            score = group_compatibility(units)
            label = " + ".join(unit.label for unit in units)
            option_id = "group-" + "-".join(unit.unit_id for unit in units)

            options.append(
                GroupOption(
                    option_id=option_id,
                    units=units,
                    group_size=group_size,
                    compatibility_score=score,
                    budget_range=budget_range,
                    label=label,
                )
            )

    options.sort(key=lambda option: (option.compatibility_score, option.group_size), reverse=True)
    return options[:max_options]


def sample_candidate_units() -> list[Unit]:
    return [
        Unit(
            unit_id="group-a",
            label="Compatible duo",
            size=2,
            preferences=Preferences(
                budget=BudgetRange(Decimal("1100"), Decimal("1700")),
                cleanliness=4,
                social=3,
                sleep_schedule="balanced",
                desired_group_min=4,
                desired_group_max=6,
                location_keywords=("Allston", "Brighton"),
            ),
        ),
        Unit(
            unit_id="group-b",
            label="Compatible trio",
            size=3,
            preferences=Preferences(
                budget=BudgetRange(Decimal("900"), Decimal("1500")),
                cleanliness=3,
                social=4,
                sleep_schedule="late",
                desired_group_min=4,
                desired_group_max=6,
                location_keywords=("Chestnut Hill",),
            ),
        ),
        Unit(
            unit_id="solo-c",
            label="Quiet solo",
            size=1,
            preferences=Preferences(
                budget=BudgetRange(Decimal("1000"), Decimal("1600")),
                cleanliness=5,
                social=2,
                sleep_schedule="early",
                desired_group_min=3,
                desired_group_max=5,
                location_keywords=("Newton", "Brighton"),
            ),
        ),
        Unit(
            unit_id="solo-d",
            label="Flexible solo",
            size=1,
            preferences=Preferences(
                budget=BudgetRange(Decimal("950"), Decimal("1800")),
                cleanliness=4,
                social=3,
                sleep_schedule="balanced",
                desired_group_min=4,
                desired_group_max=6,
                location_keywords=("Allston",),
            ),
        ),
    ]
