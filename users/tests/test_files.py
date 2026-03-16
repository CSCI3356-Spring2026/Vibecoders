import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from ..models import UserFile
from .helpers import User


class UserFilesViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")

    def test_login_required(self):
        response = self.client.get(reverse("users:files"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_upload_creates_file(self):
        self.client.force_login(self.user)
        upload = SimpleUploadedFile("sample.txt", b"hello", content_type="text/plain")

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                response = self.client.post(
                    reverse("users:files"),
                    {"title": "Lease", "file": upload},
                    follow=True,
                )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(UserFile.objects.filter(owner=self.user, title="Lease").exists())

    def test_upload_without_title_defaults_to_filename(self):
        self.client.force_login(self.user)
        upload = SimpleUploadedFile("lease-agreement.txt", b"hello", content_type="text/plain")

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                response = self.client.post(
                    reverse("users:files"),
                    {"title": "", "file": upload},
                    follow=True,
                )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(UserFile.objects.filter(owner=self.user, title="lease-agreement.txt").exists())

    def test_files_view_is_paginated(self):
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                for index in range(13):
                    upload = SimpleUploadedFile(f"doc-{index}.txt", b"hello", content_type="text/plain")
                    self.client.post(reverse("users:files"), {"title": f"Doc {index}", "file": upload})

                first_page = self.client.get(reverse("users:files"))
                second_page = self.client.get(reverse("users:files"), {"page": 2})

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(second_page.status_code, 200)
        self.assertNotContains(first_page, "Doc 0")
        self.assertContains(second_page, "Doc 0")

    def test_delete_redirect_preserves_page_and_query(self):
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                user_file = UserFile.objects.create(
                    owner=self.user,
                    title="Lease",
                    file=SimpleUploadedFile("lease.txt", b"hello", content_type="text/plain"),
                )

                response = self.client.post(
                    f"{reverse('users:file_delete', args=[user_file.id])}?page=2&q=lease",
                    follow=False,
                )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{reverse('users:files')}?page=2&q=lease")
