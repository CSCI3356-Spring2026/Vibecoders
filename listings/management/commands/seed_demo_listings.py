from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from ...models import Listing, ListingInquiry
from ...sample_data import DEMO_USERS, demo_inquiry_definitions, demo_listing_definitions

User = get_user_model()


class Command(BaseCommand):
    help = "Seed the local database with deterministic demo users, listings, and inquiries."

    def handle(self, *args, **options):
        created_users = 0
        updated_users = 0
        created_listings = 0
        updated_listings = 0
        created_inquiries = 0
        updated_inquiries = 0
        users_by_email = {}
        listing_definitions = demo_listing_definitions()

        for user_data in DEMO_USERS:
            user, created = self._upsert_user(user_data)
            users_by_email[user.email] = user
            if created:
                created_users += 1
            else:
                updated_users += 1

        for listing_data in listing_definitions:
            owner_email = listing_data["owner_email"]
            owner = users_by_email.get(owner_email)
            if owner is None:
                raise CommandError(
                    f'Cannot seed listing "{listing_data["title"]}" because owner "{owner_email}" is missing.'
                )

            defaults = {key: value for key, value in listing_data.items() if key != "owner_email"}
            _, created = Listing.objects.update_or_create(
                owner=owner,
                title=listing_data["title"],
                defaults=defaults,
            )
            if created:
                created_listings += 1
            else:
                updated_listings += 1

        listing_titles = [data["title"] for data in listing_definitions]
        listings_by_title = {listing.title: listing for listing in Listing.objects.filter(title__in=listing_titles)}

        for inquiry_data in demo_inquiry_definitions():
            listing = listings_by_title.get(inquiry_data["listing_title"])
            sender = users_by_email.get(inquiry_data["sender_email"])
            if listing is None:
                raise CommandError(f'Cannot seed inquiry because listing "{inquiry_data["listing_title"]}" is missing.')
            if sender is None:
                raise CommandError(f'Cannot seed inquiry because sender "{inquiry_data["sender_email"]}" is missing.')
            if listing.owner_id == sender.id:
                raise CommandError(f'Seed inquiry sender "{sender.email}" cannot own listing "{listing.title}".')

            _, created = ListingInquiry.objects.update_or_create(
                listing=listing,
                sender=sender,
                defaults={"message": inquiry_data["message"]},
            )
            if created:
                created_inquiries += 1
            else:
                updated_inquiries += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded demo marketplace data: "
                f"{created_users} users created, {updated_users} users updated; "
                f"{created_listings} listings created, {updated_listings} listings updated; "
                f"{created_inquiries} inquiries created, {updated_inquiries} inquiries updated."
            )
        )

    def _upsert_user(self, user_data):
        email_user = User.objects.filter(email=user_data["email"]).order_by("pk").first()
        username_user = User.objects.filter(username=user_data["username"]).order_by("pk").first()

        if email_user and username_user and email_user.pk != username_user.pk:
            raise CommandError(
                "Seed user lookup matched different records for "
                f'email "{user_data["email"]}" and username "{user_data["username"]}".'
            )

        user = email_user or username_user
        created = user is None
        field_names = ["username", "email", "first_name", "last_name"]

        if created:
            user = User.objects.create_user(
                username=user_data["username"],
                email=user_data["email"],
                first_name=user_data["first_name"],
                last_name=user_data["last_name"],
            )
            return user, True

        for field_name in field_names:
            setattr(user, field_name, user_data[field_name])
        user.save(update_fields=[*field_names, "role"])
        return user, False
