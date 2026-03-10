from django.test import TestCase


# -----------------------------------------------------------------------------
# View tests
# -----------------------------------------------------------------------------
class CorePageTests(TestCase):
    # Test that the root page renders successfully with the correct template
    def test_root_page_renders(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/landing.html")
