from django.test import TestCase

# -----------------------------------------------------------------------------
# View tests
# -----------------------------------------------------------------------------


# Basic smoke tests to ensure listing-related pages render without error
class ListingPageTests(TestCase):
    def test_listing_pages_render(self):
        for path in ("/listings/", "/listings/detail/", "/listings/create/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
