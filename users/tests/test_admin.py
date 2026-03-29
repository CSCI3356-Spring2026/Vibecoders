from types import SimpleNamespace

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, SimpleTestCase

from listings.admin import ListingAdmin
from listings.models import Listing
from users.admin import CustomUserAdmin, UserFileAdmin
from users.models import CustomUser, UserFile


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


class ReadOnlyOperationsAdminTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/admin/")
        self.request.user = SimpleNamespace(is_active=True, is_staff=True)
        admin_site = AdminSite()
        self.listing_admin = ListingAdmin(Listing, admin_site)
        self.user_file_admin = UserFileAdmin(UserFile, admin_site)

    def test_listing_admin_blocks_add_and_change(self):
        self.assertFalse(self.listing_admin.has_add_permission(self.request))
        self.assertFalse(self.listing_admin.has_change_permission(self.request))
        self.assertTrue(self.listing_admin.has_view_permission(self.request))

    def test_user_file_admin_blocks_add_and_change(self):
        self.assertFalse(self.user_file_admin.has_add_permission(self.request))
        self.assertFalse(self.user_file_admin.has_change_permission(self.request))
        self.assertTrue(self.user_file_admin.has_view_permission(self.request))
