from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from users.models import Role

User = get_user_model()


class Command(BaseCommand):
    help = "Set a user's role. Usage: set_user_role <email> <student|admin>"

    def add_arguments(self, parser):
        parser.add_argument("email", type=str, help="The user's email address")
        parser.add_argument("role", type=str, choices=["student", "admin"], help="Role to assign")

    def handle(self, *args, **options):
        email = options["email"]
        role = options["role"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f'User with email "{email}" does not exist.')

        user.role = Role.ADMIN if role == "admin" else Role.STUDENT
        user.save(update_fields=["role"])

        self.stdout.write(self.style.SUCCESS(f'Set {user.username} ({email}) role to "{user.display_role}".'))
