from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0012_customuser_customuser_role_valid"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="profile_completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
