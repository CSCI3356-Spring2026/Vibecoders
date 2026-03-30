from .models import StudentProfile

_FIELD_WEIGHTS = {
    "messy_level": 0.20,
    "noise_level": 0.15,
    "bedtime": 0.15,
    "smoke": 0.15,
    "guest_level": 0.10,
    "drink": 0.10,
    "party": 0.10,
    "pets": 0.05,
}

_SCALE_MAX = {
    "messy_level": 4,  # range 1–5
    "noise_level": 4,
    "guest_level": 4,
    "drink": 4,
    "party": 4,
    "bedtime": 23,  # range 0–23
}


def compute_compatibility(profile_a: StudentProfile, profile_b: StudentProfile) -> int | None:
    """
    Compute a 0–100 compatibility score between two StudentProfiles.
    Returns None if neither profile has any scoreable fields filled in.
    Fields that are None on either profile are skipped; weights are redistributed.
    """
    total_weight = 0.0
    weighted_score = 0.0

    for field, weight in _FIELD_WEIGHTS.items():
        val_a = getattr(profile_a, field)
        val_b = getattr(profile_b, field)

        if val_a is None or val_b is None:
            continue

        if field in ("smoke", "pets"):
            field_score = 1.0 if val_a == val_b else 0.0
        else:
            max_diff = _SCALE_MAX[field]
            field_score = 1.0 - abs(val_a - val_b) / max_diff

        total_weight += weight
        weighted_score += weight * field_score

    if total_weight == 0:
        return None

    return round((weighted_score / total_weight) * 100)
