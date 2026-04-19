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
        if not gender and not gender_other:
            continue
        profile.gender = gender
        if gender_other:
            profile.gender_other = gender_other
        profile.save(update_fields=["gender", "gender_other"])

    for profile in admin_model.objects.all():
        gender, gender_other = _normalize_gender(profile.gender)
        if not gender and not gender_other:
            continue
        profile.gender = gender
        if gender_other:
            profile.gender_other = gender_other
        profile.save(update_fields=["gender", "gender_other"])


def _migrate_student_profile_frequency_fields(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            """
            ALTER TABLE users_studentprofile
            ALTER COLUMN drink TYPE smallint
            USING CASE
                WHEN drink IS TRUE THEN 4
                WHEN drink IS FALSE THEN 1
                ELSE NULL
            END,
            ALTER COLUMN party TYPE smallint
            USING CASE
                WHEN party IS TRUE THEN 4
                WHEN party IS FALSE THEN 1
                ELSE NULL
            END
            """
        )
        return

    schema_editor.execute(
        """
        UPDATE users_studentprofile
        SET drink = CASE
                WHEN drink = 1 THEN 4
                WHEN drink = 0 THEN 1
                ELSE NULL
            END,
            party = CASE
                WHEN party = 1 THEN 4
                WHEN party = 0 THEN 1
                ELSE NULL
            END
        """
    )


def _reverse_student_profile_frequency_fields(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            """
            ALTER TABLE users_studentprofile
            ALTER COLUMN drink TYPE boolean
            USING CASE
                WHEN drink IS NULL THEN NULL
                WHEN drink >= 4 THEN TRUE
                ELSE FALSE
            END,
            ALTER COLUMN party TYPE boolean
            USING CASE
                WHEN party IS NULL THEN NULL
                WHEN party >= 4 THEN TRUE
                ELSE FALSE
            END
            """
        )
        return

    schema_editor.execute(
        """
        UPDATE users_studentprofile
        SET drink = CASE
                WHEN drink IS NULL THEN NULL
                WHEN drink >= 4 THEN 1
                ELSE 0
            END,
            party = CASE
                WHEN party IS NULL THEN NULL
                WHEN party >= 4 THEN 1
                ELSE 0
            END
        """
    )


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
        migrations.RunPython(_migrate_profile_fields, migrations.RunPython.noop),
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
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    _migrate_student_profile_frequency_fields,
                    _reverse_student_profile_frequency_fields,
                ),
            ],
            state_operations=[
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
            ],
        ),
    ]
