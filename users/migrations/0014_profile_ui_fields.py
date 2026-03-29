from django.db import migrations, models


def _normalize_gender(value):
    if value is None:
        return "", ""
    raw = str(value).strip()
    if not raw:
        return "", ""
    lowered = raw.lower()
    gender_map = {
        "male": "male",
        "m": "male",
        "man": "male",
        "female": "female",
        "f": "female",
        "woman": "female",
        "other": "other",
        "prefer_not": "prefer_not",
        "prefer not": "prefer_not",
        "prefer not to say": "prefer_not",
        "no": "prefer_not",
        "n/a": "prefer_not",
    }
    if lowered in gender_map:
        normalized = gender_map[lowered]
        return normalized, "" if normalized != "other" else raw
    return "other", raw


def _migrate_profile_fields(apps, schema_editor):
    student_model = apps.get_model("users", "StudentProfile")
    admin_model = apps.get_model("users", "AdminProfile")

    for profile in student_model.objects.all():
        gender, gender_other = _normalize_gender(profile.gender)
        if gender or gender_other:
            profile.gender = gender
            if gender_other:
                profile.gender_other = gender_other

        if profile.drink is not None:
            if profile.drink in (True, 1):
                profile.drink = 4
            elif profile.drink in (False, 0):
                profile.drink = 1
        if profile.party is not None:
            if profile.party in (True, 1):
                profile.party = 4
            elif profile.party in (False, 0):
                profile.party = 1
        profile.save(update_fields=["gender", "gender_other", "drink", "party"])

    for profile in admin_model.objects.all():
        gender, gender_other = _normalize_gender(profile.gender)
        if gender or gender_other:
            profile.gender = gender
            if gender_other:
                profile.gender_other = gender_other
        profile.save(update_fields=["gender", "gender_other"])


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0013_customuser_profile_completed_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentprofile",
            name="gender_other",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="adminprofile",
            name="gender_other",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AlterField(
            model_name="studentprofile",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[
                    ("male", "Male"),
                    ("female", "Female"),
                    ("other", "Other"),
                    ("prefer_not", "Prefer not to say"),
                ],
                max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name="adminprofile",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[
                    ("male", "Male"),
                    ("female", "Female"),
                    ("other", "Other"),
                    ("prefer_not", "Prefer not to say"),
                ],
                max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name="studentprofile",
            name="messy_level",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                choices=[(1, "Extremely messy"), (2, "Messy"), (3, "Neutral"), (4, "Clean"), (5, "Extremely clean")],
            ),
        ),
        migrations.AlterField(
            model_name="studentprofile",
            name="guest_level",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                choices=[(1, "Never"), (2, "Rarely"), (3, "Sometimes"), (4, "Often"), (5, "Everyday")],
            ),
        ),
        migrations.AlterField(
            model_name="studentprofile",
            name="noise_level",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                choices=[(1, "Silent"), (2, "Quiet"), (3, "Neutral"), (4, "Loud"), (5, "Very loud")],
            ),
        ),
        migrations.AlterField(
            model_name="studentprofile",
            name="drink",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                choices=[(1, "Never"), (2, "Rarely"), (3, "Sometimes"), (4, "Often"), (5, "Daily")],
            ),
        ),
        migrations.AlterField(
            model_name="studentprofile",
            name="party",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                choices=[(1, "Never"), (2, "Rarely"), (3, "Sometimes"), (4, "Often"), (5, "Daily")],
            ),
        ),
        migrations.RunPython(_migrate_profile_fields, migrations.RunPython.noop),
    ]
