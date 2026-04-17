import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("listings", "0024_one_group_per_user"),
    ]

    operations = [
        migrations.AddField(
            model_name="roommatepost",
            name="address",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="roommatepost",
            name="linked_listing",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="roommate_posts",
                to="listings.listing",
            ),
        ),
        migrations.AddConstraint(
            model_name="roommatepost",
            constraint=models.CheckConstraint(
                condition=models.Q(("housing_status", "need_home")) | ~models.Q(("address", "")),
                name="roommate_post_address_required_for_have_home",
            ),
        ),
    ]
