from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, SimpleTestCase

from users.admin import CustomUserAdmin
from users.models import CustomUser


class CustomUserAdminTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/admin/users/customuser/add/")
        self.admin = CustomUserAdmin(CustomUser, AdminSite())

    def test_role_is_read_only_on_change_view(self):
        self.assertIn("role", self.admin.get_readonly_fields(self.request))

    def test_role_is_not_editable_in_add_fieldsets(self):
        add_fieldsets = self.admin.get_add_fieldsets(self.request)
        flattened_fields = []
        for _, options in add_fieldsets:
            fields = options.get("fields", ())
            if isinstance(fields, tuple):
                flattened_fields.extend(fields)
            else:
                flattened_fields.append(fields)

        self.assertNotIn("role", flattened_fields)
