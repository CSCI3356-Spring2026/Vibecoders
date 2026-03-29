import tempfile

from django.core.exceptions import ValidationError
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

    def test_upload_rejects_title_over_max_length(self):
        self.client.force_login(self.user)
        upload = SimpleUploadedFile("lease.txt", b"hello", content_type="text/plain")

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                response = self.client.post(
                    reverse("users:files"),
                    {"title": "a" * 121, "file": upload},
                    follow=True,
                )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ensure this value has at most 120 characters")
        self.assertFalse(UserFile.objects.filter(owner=self.user).exists())

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
        self.assertNotContains(first_page, "confirm(")

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

    def test_delete_redirect_preserves_posted_query_with_url_encoding(self):
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                user_file = UserFile.objects.create(
                    owner=self.user,
                    title="Lease",
                    file=SimpleUploadedFile("lease.txt", b"hello", content_type="text/plain"),
                )

                response = self.client.post(
                    reverse("users:file_delete", args=[user_file.id]),
                    {"page": "2", "q": "lease & forms"},
                    follow=False,
                )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{reverse('users:files')}?page=2&q=lease+%26+forms")

    def test_delete_removes_file_from_storage(self):
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                user_file = UserFile.objects.create(
                    owner=self.user,
                    title="Lease",
                    file=SimpleUploadedFile("lease.txt", b"hello", content_type="text/plain"),
                )
                stored_name = user_file.file.name
                self.assertTrue(user_file.file.storage.exists(stored_name))

                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.post(reverse("users:file_delete", args=[user_file.id]))

                self.assertEqual(response.status_code, 302)
                self.assertFalse(user_file.file.storage.exists(stored_name))

    def test_upload_rejects_unsupported_file_type(self):
        self.client.force_login(self.user)
        upload = SimpleUploadedFile("script.exe", b"binary", content_type="application/octet-stream")

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                response = self.client.post(reverse("users:files"), {"title": "Bad", "file": upload}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload a PDF, image, text file, DOC, or DOCX file.")
        self.assertFalse(UserFile.objects.filter(owner=self.user, title="Bad").exists())

    def test_upload_rejects_invalid_pdf_content(self):
        self.client.force_login(self.user)
        upload = SimpleUploadedFile("lease.pdf", b"not actually a pdf", content_type="application/pdf")

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                response = self.client.post(reverse("users:files"), {"title": "Bad PDF", "file": upload}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload a valid PDF file.")
        self.assertFalse(UserFile.objects.filter(owner=self.user, title="Bad PDF").exists())

    def test_upload_rejects_invalid_image_content(self):
        self.client.force_login(self.user)
        upload = SimpleUploadedFile("avatar.png", b"not an image", content_type="image/png")

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                response = self.client.post(
                    reverse("users:files"),
                    {"title": "Bad Image", "file": upload},
                    follow=True,
                )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload a valid image file.")
        self.assertFalse(UserFile.objects.filter(owner=self.user, title="Bad Image").exists())

    @override_settings(USER_FILE_TOTAL_LIMIT=1)
    def test_model_enforces_document_library_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                UserFile.objects.create(
                    owner=self.user,
                    title="Lease",
                    file=SimpleUploadedFile("lease.txt", b"hello", content_type="text/plain"),
                )

                with self.assertRaises(ValidationError) as exc:
                    UserFile.objects.create(
                        owner=self.user,
                        title="Second lease",
                        file=SimpleUploadedFile("lease-2.txt", b"hello", content_type="text/plain"),
                    )

        self.assertIn("You can store up to 1 file in your document library.", exc.exception.message_dict["file"][0])

    @override_settings(USER_FILE_TOTAL_LIMIT=1)
    def test_upload_rejects_when_document_library_limit_is_reached(self):
        self.client.force_login(self.user)
        upload = SimpleUploadedFile("lease-2.txt", b"hello", content_type="text/plain")

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                UserFile.objects.create(
                    owner=self.user,
                    title="Lease",
                    file=SimpleUploadedFile("lease.txt", b"hello", content_type="text/plain"),
                )

                response = self.client.post(
                    reverse("users:files"),
                    {"title": "Second lease", "file": upload},
                    follow=True,
                )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You can store up to 1 file in your document library.")
        self.assertEqual(UserFile.objects.filter(owner=self.user).count(), 1)

    def test_owner_can_preview_file_through_authenticated_view(self):
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                user_file = UserFile.objects.create(
                    owner=self.user,
                    title="Lease",
                    file=SimpleUploadedFile("lease.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
                )

                response = self.client.get(reverse("users:file_preview", args=[user_file.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Frame-Options"], "SAMEORIGIN")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_other_user_cannot_preview_private_file(self):
        other_user = User.objects.create_user(username="other", email="other@bc.edu", password="test")

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                user_file = UserFile.objects.create(
                    owner=self.user,
                    title="Lease",
                    file=SimpleUploadedFile("lease.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
                )

                self.client.force_login(other_user)
                response = self.client.get(reverse("users:file_preview", args=[user_file.id]))

        self.assertEqual(response.status_code, 404)

    def test_private_file_is_not_served_from_raw_media_url(self):
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                user_file = UserFile.objects.create(
                    owner=self.user,
                    title="Lease",
                    file=SimpleUploadedFile("lease.txt", b"hello", content_type="text/plain"),
                )

                response = self.client.get(user_file.file.url)

        self.assertEqual(response.status_code, 404)

    def test_preview_rejects_non_previewable_file_types(self):
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                user_file = UserFile.objects.create(
                    owner=self.user,
                    title="Notes",
                    file=SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain"),
                )

                response = self.client.get(reverse("users:file_preview", args=[user_file.id]))

        self.assertEqual(response.status_code, 404)

    def test_admin_can_download_user_file(self):
        admin = User.objects.create_user(username="admin", email="admin@bc.edu", password="test", role="admin")

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                user_file = UserFile.objects.create(
                    owner=self.user,
                    title="Lease",
                    file=SimpleUploadedFile("lease.txt", b"hello", content_type="text/plain"),
                )

                self.client.force_login(admin)
                response = self.client.get(reverse("users:file_download", args=[user_file.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
