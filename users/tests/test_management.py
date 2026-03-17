from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from ..models import Role
from .helpers import User


class SetUserRoleCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")
        self.external_user = User.objects.create_user(username="agent", email="agent@gmail.com", password="test")

    def test_promote_to_admin(self):
        call_command("set_user_role", "eagle@bc.edu", "admin", stdout=StringIO())
        self.user.refresh_from_db()

        self.assertEqual(self.user.role, Role.ADMIN)

    def test_restore_bc_user_to_student(self):
        self.user.role = Role.ADMIN
        self.user.save()
        call_command("set_user_role", "eagle@bc.edu", "student", stdout=StringIO())
        self.user.refresh_from_db()

        self.assertEqual(self.user.role, Role.STUDENT)

    def test_restore_external_user_to_realtor(self):
        self.external_user.role = Role.ADMIN
        self.external_user.save()
        call_command("set_user_role", "agent@gmail.com", "realtor", stdout=StringIO())
        self.external_user.refresh_from_db()

        self.assertEqual(self.external_user.role, Role.REALTOR)

    def test_invalid_student_assignment_for_external_email_raises(self):
        self.external_user.role = Role.ADMIN
        self.external_user.save()

        with self.assertRaises(CommandError):
            call_command("set_user_role", "agent@gmail.com", "student", stderr=StringIO())

    def test_nonexistent_user_raises(self):
        with self.assertRaises(CommandError):
            call_command("set_user_role", "nobody@bc.edu", "admin", stderr=StringIO())
