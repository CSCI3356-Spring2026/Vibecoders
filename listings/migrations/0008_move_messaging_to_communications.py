# Generated manually to transfer messaging state ownership to communications.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("communications", "0001_initial"),
        ("listings", "0007_listingconversation_listingmessage_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="ListingMessage"),
                migrations.DeleteModel(name="ListingConversation"),
            ],
        ),
    ]
