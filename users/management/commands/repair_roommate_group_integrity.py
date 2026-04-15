from django.core.management.base import BaseCommand

from users.roommate_group_integrity import repair_roommate_group_integrity


class Command(BaseCommand):
    help = "Audit and optionally repair roommate-group memberships, invites, and group-post counts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist safe repairs instead of running in audit mode.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        summary = repair_roommate_group_integrity(apply=apply_changes)

        mode_label = "repair" if apply_changes else "audit"
        self.stdout.write(f"Roommate group integrity {mode_label} summary:")
        self.stdout.write(f"  Groups missing lead membership: {summary['groups_missing_lead_membership']}")
        self.stdout.write(f"  Lead membership conflicts: {summary['lead_membership_conflicts']}")
        self.stdout.write(f"  Lead memberships created: {summary['lead_memberships_created']}")
        self.stdout.write(f"  Group posts out of sync: {summary['group_posts_out_of_sync']}")
        self.stdout.write(f"  Group posts resynced: {summary['group_posts_resynced']}")
        self.stdout.write(f"  Invalid active invites: {summary['invalid_active_invites']}")
        self.stdout.write(f"  Invalid active invites cancelled: {summary['invalid_active_invites_cancelled']}")
