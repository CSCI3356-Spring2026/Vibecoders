from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("communications", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="listingconversation",
            name="owner_deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="listingconversation",
            name="participant_deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="listingconversation",
            index=models.Index(
                fields=["owner", "owner_deleted_at", "last_message_at"],
                name="list_conv_owner_vis_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="listingconversation",
            index=models.Index(
                fields=["participant", "participant_deleted_at", "last_message_at"],
                name="list_conv_part_vis_idx",
            ),
        ),
    ]
