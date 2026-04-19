from django.db import migrations, models


def _student_profile_frequency_choice_field(name, *, nullable):
    field = models.PositiveSmallIntegerField(
        blank=True,
        null=nullable,
        choices=[(1, "Never"), (2, "Rarely"), (3, "Sometimes"), (4, "Often"), (5, "Daily")],
    )
    field.set_attributes_from_name(name)
    return field


def _student_profile_frequency_not_null_columns(schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s
                  AND column_name IN (%s, %s)
                  AND is_nullable = 'NO'
                """,
                ["users_studentprofile", "drink", "party"],
            )
            return {column_name for (column_name,) in cursor.fetchall()}

    if schema_editor.connection.vendor == "sqlite":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("PRAGMA table_info(users_studentprofile)")
            return {row[1] for row in cursor.fetchall() if row[1] in {"drink", "party"} and row[3]}

    return set()


def _make_student_profile_frequency_fields_nullable(apps, schema_editor):
    columns_to_fix = _student_profile_frequency_not_null_columns(schema_editor)
    if not columns_to_fix:
        return

    student_model = apps.get_model("users", "StudentProfile")
    for field_name in ("drink", "party"):
        if field_name not in columns_to_fix:
            continue
        schema_editor.alter_field(
            student_model,
            _student_profile_frequency_choice_field(field_name, nullable=False),
            _student_profile_frequency_choice_field(field_name, nullable=True),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0020_remove_roommategroup_created_by_and_more"),
    ]

    operations = [
        migrations.RunPython(
            _make_student_profile_frequency_fields_nullable,
            migrations.RunPython.noop,
        ),
    ]
