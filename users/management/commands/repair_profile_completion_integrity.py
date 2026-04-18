from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from ...profile_integrity import (
    clear_profile_completion,
    mark_profile_completed_now,
    profile_satisfies_completion_requirements,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Repair profile_completed_at based on each user's current role and required profile fields."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=200,
            help="Number of users to stream from the database at a time.",
        )

    def handle(self, *args, **options):
        batch_size = max(1, options["batch_size"])
        users = User.objects.order_by("id").select_related("student_profile", "admin_profile")

        scanned = 0
        completion_cleared = 0
        completion_set = 0

        for user in users.iterator(chunk_size=batch_size):
            scanned += 1
            profile_is_complete = profile_satisfies_completion_requirements(user)

            if profile_is_complete:
                if mark_profile_completed_now(user):
                    completion_set += 1
                continue

            if clear_profile_completion(user):
                completion_cleared += 1

        self.stdout.write(self.style.SUCCESS(f"Users scanned: {scanned}"))
        self.stdout.write(self.style.SUCCESS(f"Profile completions set: {completion_set}"))
        self.stdout.write(self.style.SUCCESS(f"Profile completions cleared: {completion_cleared}"))
