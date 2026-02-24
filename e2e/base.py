import os

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import sync_playwright

# LiveServerTestCase uses a threaded server; Django's async safety check
# incorrectly flags synchronous DB calls from the test-cleanup thread.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


class PlaywrightTestCase(StaticLiveServerTestCase):
    """Base class for Playwright browser tests.

    Shares a single browser instance across all tests in a class,
    but creates a fresh page for each test for isolation.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        # Clear the choice cache so DB-backed dropdowns reflect the
        # restored seed data after TransactionTestCase flushes.
        from dashboard.choices import invalidate_choice_cache

        invalidate_choice_cache()
        self.page = self.browser.new_page()

    def tearDown(self):
        self.page.close()

    def url(self, path):
        """Construct full URL from a path (e.g. '/tasks/')."""
        return f"{self.live_server_url}{path}"
