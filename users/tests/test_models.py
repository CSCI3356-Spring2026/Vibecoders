from django.test import TestCase

from ..models import Role
from .helpers import User


class CustomUserModelTests(TestCase):
    def test_default_role_is_student(self):
        user = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")

        self.assertEqual(user.role, Role.STUDENT)

    def test_is_bc_admin_false_for_student(self):
        user = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")

        self.assertFalse(user.is_bc_admin)

    def test_is_bc_admin_true_for_admin(self):
        user = User.objects.create_user(username="adm", email="adm@bc.edu", password="test", role=Role.ADMIN)

        self.assertTrue(user.is_bc_admin)

    def test_display_role_student(self):
        user = User.objects.create_user(username="stu", email="stu@bc.edu", password="test")

        self.assertEqual(user.display_role, "Student")

    def test_display_role_admin(self):
        user = User.objects.create_user(username="adm", email="adm@bc.edu", password="test", role=Role.ADMIN)

        self.assertEqual(user.display_role, "Admin")

    def test_str_representation(self):
        user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")

        self.assertEqual(str(user), "eagle (Student)")
