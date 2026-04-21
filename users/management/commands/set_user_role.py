from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from ...models import Role

User = get_user_model()


class Command(BaseCommand):
    help = "Set a user's role."

    def add_arguments(self, parser):
        parser.add_argument("email", type=str, help="The user's email address")
        parser.add_argument(
            "role",
            type=str,
            choices=["admin", *[role.value for role in Role]],
            help="Role to assign",
        )

    def handle(self, *args, **options):
        email = options["email"]
        role = User.normalize_role_value(options["role"])

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f'User with email "{email}" does not exist.')

        requested_role = Role(role)
        if requested_role in {Role.ADMIN, Role.MODERATOR, Role.SUPPORT}:
            user.set_staff_role(requested_role)
        else:
            expected_role = user.default_role_for_email(user.email)
            if requested_role != expected_role:
                raise CommandError(
                    f'{email} resolves to "{expected_role.value}" access based on the current email policy. '
                    f'Use "{expected_role.value}" or a staff role.'
                )
            user.restore_default_access_role()
        user.save(update_fields=["role"])

        self.stdout.write(self.style.SUCCESS(f'Set {user.username} ({email}) role to "{user.display_role}".'))
