from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from ..models import Role
from .helpers import User


class SetUserRoleCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")

    def test_promote_to_admin(self):
        call_command("set_user_role", "eagle@bc.edu", "admin", stdout=StringIO())
        self.user.refresh_from_db()

        self.assertEqual(self.user.role, Role.ADMIN)

    def test_demote_to_student(self):
        self.user.role = Role.ADMIN
        self.user.save()
        call_command("set_user_role", "eagle@bc.edu", "student", stdout=StringIO())
        self.user.refresh_from_db()

        self.assertEqual(self.user.role, Role.STUDENT)

    def test_nonexistent_user_raises(self):
        with self.assertRaises(CommandError):
            call_command("set_user_role", "nobody@bc.edu", "admin", stderr=StringIO())
