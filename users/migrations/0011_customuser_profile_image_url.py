from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0010_customuser_legal_policy_version_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="profile_image_url",
            field=models.URLField(blank=True, max_length=500),
        ),
    ]
