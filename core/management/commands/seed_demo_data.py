from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.demo_seed import default_bundle_root, seed_demo_environment


class Command(BaseCommand):
    help = "Seed a realistic, repeatable local Padly demo environment with cached listing photos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--bundle-root",
            type=Path,
            default=default_bundle_root(),
            help="Directory for the gitignored local demo-data bundle and photo cache.",
        )
        parser.add_argument(
            "--reference-date",
            type=date.fromisoformat,
            default=None,
            help="Reference date for generated lease and roommate move-in windows (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--skip-image-downloads",
            action="store_true",
            help="Use cached source photos only and fail if the local cache is incomplete.",
        )
        parser.add_argument(
            "--refresh-photo-cache",
            action="store_true",
            help="Re-download and re-normalize the remote listing photos before seeding.",
        )

    def handle(self, *args, **options):
        try:
            summary = seed_demo_environment(
                bundle_root=options["bundle_root"],
                reference_date=options["reference_date"],
                skip_image_downloads=options["skip_image_downloads"],
                refresh_photo_cache=options["refresh_photo_cache"],
                stdout=self.stdout,
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS("Seeded Padly demo data successfully."))
        self.stdout.write(f"Bundle root: {summary['bundle_root']}")
        self.stdout.write(f"Summary JSON: {Path(summary['bundle_root']) / 'seed_summary.json'}")
        self.stdout.write(f"Summary text: {Path(summary['bundle_root']) / 'seed_summary.txt'}")
