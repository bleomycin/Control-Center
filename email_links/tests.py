from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import EmailLink
from .views import _parse_email_date


class EmailLinkModelTest(TestCase):
    def test_web_url(self):
        el = EmailLink(message_id="abc123")
        self.assertEqual(el.web_url, "https://mail.google.com/mail/u/0/#all/abc123")

    def test_str_returns_subject(self):
        el = EmailLink(message_id="x", subject="Test Subject")
        self.assertEqual(str(el), "Test Subject")

    def test_str_falls_back_to_message_id(self):
        el = EmailLink(message_id="x", subject="")
        self.assertEqual(str(el), "x")

    def test_unique_message_id(self):
        EmailLink.objects.create(message_id="unique1", subject="First")
        with self.assertRaises(Exception):
            EmailLink.objects.create(message_id="unique1", subject="Second")

    def test_linked_entities_empty(self):
        el = EmailLink(message_id="x")
        self.assertEqual(el.linked_entities, [])

    def test_parse_rfc2822_date(self):
        dt = _parse_email_date("Thu, 12 Mar 2026 12:22:20 +0000")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 3)
        self.assertEqual(dt.day, 12)

    def test_parse_empty_date(self):
        self.assertIsNone(_parse_email_date(""))
        self.assertIsNone(_parse_email_date(None))


class EmailLinkViewTest(TestCase):
    def test_gmail_search_no_query(self):
        resp = self.client.get(reverse("email_links:gmail_search"))
        self.assertEqual(resp.status_code, 200)

    def test_email_body_404(self):
        resp = self.client.get(reverse("email_links:email_body", args=[9999]))
        self.assertEqual(resp.status_code, 404)


class EmailLinkUnlinkTest(TestCase):
    def setUp(self):
        from legal.models import LegalMatter
        self.matter = LegalMatter.objects.create(
            title="Test Matter", status="active",
        )
        self.email = EmailLink.objects.create(
            message_id="test123",
            subject="Test Email",
            from_email="test@example.com",
            date=timezone.now(),
            related_legal_matter=self.matter,
        )

    def test_unlink_removes_fk(self):
        resp = self.client.post(
            reverse("email_links:legal_matter_email_unlink",
                    args=[self.matter.pk, self.email.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.email.refresh_from_db()
        self.assertIsNone(self.email.related_legal_matter)

    def test_link_form_get(self):
        resp = self.client.get(
            reverse("email_links:legal_matter_email_link", args=[self.matter.pk])
        )
        self.assertEqual(resp.status_code, 200)

    def test_link_post_creates_and_links(self):
        resp = self.client.post(
            reverse("email_links:legal_matter_email_link", args=[self.matter.pk]),
            {
                "message_id": "new_msg_456",
                "subject": "New Email",
                "from_name": "Sender",
                "from_email": "sender@example.com",
                "date": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        el = EmailLink.objects.get(message_id="new_msg_456")
        self.assertEqual(el.related_legal_matter, self.matter)
        self.assertEqual(el.subject, "New Email")

    def test_link_post_reuses_existing_message(self):
        """get_or_create should reuse existing EmailLink by message_id."""
        resp = self.client.post(
            reverse("email_links:legal_matter_email_link", args=[self.matter.pk]),
            {
                "message_id": "test123",
                "subject": "Different Subject",
                "from_name": "",
                "from_email": "",
                "date": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        # Should still be the same record
        self.assertEqual(EmailLink.objects.filter(message_id="test123").count(), 1)
        self.email.refresh_from_db()
        # Original subject preserved (get_or_create doesn't update)
        self.assertEqual(self.email.subject, "Test Email")
        self.assertEqual(self.email.related_legal_matter, self.matter)
