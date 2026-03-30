from unittest.mock import patch, MagicMock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import EmailLink
from .views import _parse_email_date
from . import gmail


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

    def test_unlink_last_fk_deletes_record(self):
        """Unlinking the only FK should delete the EmailLink entirely."""
        resp = self.client.post(
            reverse("email_links:legal_matter_email_unlink",
                    args=[self.matter.pk, self.email.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(EmailLink.objects.filter(pk=self.email.pk).exists())

    def test_unlink_preserves_record_when_other_fk_remains(self):
        """Unlinking one FK should keep the record if another FK is still set."""
        from tasks.models import Task
        task = Task.objects.create(title="Keep Alive", direction="personal")
        self.email.related_task = task
        self.email.save()

        resp = self.client.post(
            reverse("email_links:legal_matter_email_unlink",
                    args=[self.matter.pk, self.email.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.email.refresh_from_db()
        self.assertIsNone(self.email.related_legal_matter)
        self.assertEqual(self.email.related_task, task)

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


class TaskEmailLinkUnlinkTest(TestCase):
    def setUp(self):
        from tasks.models import Task
        self.task = Task.objects.create(
            title="Test Task", direction="personal",
        )
        self.email = EmailLink.objects.create(
            message_id="task_test_123",
            subject="Test Task Email",
            from_email="test@example.com",
            date=timezone.now(),
            related_task=self.task,
        )

    def test_unlink_last_fk_deletes_record(self):
        """Unlinking the only FK on a task email should delete the record."""
        resp = self.client.post(
            reverse("email_links:task_email_unlink",
                    args=[self.task.pk, self.email.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(EmailLink.objects.filter(pk=self.email.pk).exists())

    def test_link_form_get(self):
        resp = self.client.get(
            reverse("email_links:task_email_link", args=[self.task.pk])
        )
        self.assertEqual(resp.status_code, 200)

    def test_link_post_creates_and_links(self):
        resp = self.client.post(
            reverse("email_links:task_email_link", args=[self.task.pk]),
            {
                "message_id": "task_new_msg_789",
                "subject": "New Task Email",
                "from_name": "Sender",
                "from_email": "sender@example.com",
                "date": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        el = EmailLink.objects.get(message_id="task_new_msg_789")
        self.assertEqual(el.related_task, self.task)
        self.assertEqual(el.subject, "New Task Email")

    def test_link_post_reuses_existing_message(self):
        resp = self.client.post(
            reverse("email_links:task_email_link", args=[self.task.pk]),
            {
                "message_id": "task_test_123",
                "subject": "Different Subject",
                "from_name": "",
                "from_email": "",
                "date": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(EmailLink.objects.filter(message_id="task_test_123").count(), 1)
        self.email.refresh_from_db()
        self.assertEqual(self.email.subject, "Test Task Email")
        self.assertEqual(self.email.related_task, self.task)

    def test_linked_entities_includes_task(self):
        el = EmailLink.objects.create(
            message_id="task_le_test", related_task=self.task,
        )
        self.assertEqual(el.linked_entities, [("Task", self.task)])


class EntityDeleteOrphanCleanupTest(TestCase):
    """Deleting an entity should auto-delete EmailLinks that become orphaned."""

    def test_delete_sole_linked_entity_deletes_email(self):
        from legal.models import LegalMatter
        matter = LegalMatter.objects.create(title="Doomed", status="active")
        email = EmailLink.objects.create(
            message_id="orphan_signal_1",
            subject="Will be orphaned",
            related_legal_matter=matter,
        )
        matter.delete()
        self.assertFalse(EmailLink.objects.filter(pk=email.pk).exists())

    def test_delete_entity_preserves_multi_linked_email(self):
        from legal.models import LegalMatter
        from tasks.models import Task
        matter = LegalMatter.objects.create(title="Goes Away", status="active")
        task = Task.objects.create(title="Stays", direction="personal")
        email = EmailLink.objects.create(
            message_id="orphan_signal_2",
            subject="Has two links",
            related_legal_matter=matter,
            related_task=task,
        )
        matter.delete()
        email.refresh_from_db()
        self.assertIsNone(email.related_legal_matter)
        self.assertEqual(email.related_task, task)

    def test_delete_task_deletes_orphaned_email(self):
        from tasks.models import Task
        task = Task.objects.create(title="Task to delete", direction="personal")
        email = EmailLink.objects.create(
            message_id="orphan_signal_3",
            related_task=task,
        )
        task.delete()
        self.assertFalse(EmailLink.objects.filter(pk=email.pk).exists())

    def test_delete_stakeholder_deletes_orphaned_email(self):
        from stakeholders.models import Stakeholder
        sh = Stakeholder.objects.create(name="Gone", entity_type="individual")
        email = EmailLink.objects.create(
            message_id="orphan_signal_4",
            related_stakeholder=sh,
        )
        sh.delete()
        self.assertFalse(EmailLink.objects.filter(pk=email.pk).exists())


class ReadEmailToolTest(TestCase):
    def setUp(self):
        from tasks.models import Task
        self.task = Task.objects.create(title="Read Email Test", direction="personal")
        self.email = EmailLink.objects.create(
            message_id="read_test_123",
            subject="Important Discussion",
            from_email="sender@example.com",
            from_name="Test Sender",
            date=timezone.now(),
            related_task=self.task,
        )

    @patch("email_links.gmail.is_available", return_value=True)
    @patch("email_links.gmail.get_thread_messages")
    def test_read_email_returns_content(self, mock_get, mock_avail):
        mock_get.return_value = [
            {"from_name": "Alice", "from_email": "alice@test.com",
             "date": "Thu, 27 Mar 2026 10:00:00 +0000",
             "body": "Here are the details you asked about."},
            {"from_name": "Bob", "from_email": "bob@test.com",
             "date": "Thu, 27 Mar 2026 11:00:00 +0000",
             "body": "Thanks, got it."},
        ]
        from assistant.tools import read_email
        result = read_email(id=self.email.pk)
        self.assertIn("content", result)
        self.assertIn("Important Discussion", result["content"])
        self.assertIn("Here are the details", result["content"])
        self.assertIn("Thanks, got it", result["content"])
        self.assertIn("Message 1", result["content"])
        self.assertIn("Message 2", result["content"])
        self.assertIn("Task: Read Email Test", result["content"])

    def test_read_email_not_found(self):
        from assistant.tools import read_email
        result = read_email(id=99999)
        self.assertIn("error", result)

    @patch("email_links.gmail.is_available", return_value=False)
    def test_read_email_gmail_unavailable(self, mock_avail):
        from assistant.tools import read_email
        result = read_email(id=self.email.pk)
        self.assertIn("error", result)
        self.assertIn("not connected", result["error"])


class GmailSearchViewIntegrationTest(TestCase):
    """Hit the actual view with mocked gmail, inspect rendered HTML."""

    def _url(self, **params):
        base = reverse("email_links:gmail_search")
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{base}?{qs}" if qs else base

    @patch("email_links.views.gmail")
    def test_page1_has_scroll_wrapper_and_load_more(self, mock_gmail):
        mock_gmail.is_available.return_value = True
        mock_gmail.search_threads.return_value = {
            "threads": [{"id": "t1", "subject": "Hello", "from_name": "A",
                         "from_email": "a@b.c", "date": "", "snippet": "",
                         "message_count": 1, "participants": ["A"]}],
            "next_page_token": "PAGE2",
        }
        resp = self.client.get(self._url(q="", link_url="/link/1/"))
        html = resp.content.decode()
        # Page 1 should have the scroll wrapper
        self.assertIn('class="max-h-64 overflow-y-auto', html)
        # Should have Load More button with the token
        self.assertIn("Load more", html)
        self.assertIn("page_token=PAGE2", html)
        # Should include link_url and label in Load More URL
        self.assertIn("link_url=", html)
        self.assertIn("label=", html)

    @patch("email_links.views.gmail")
    def test_page2_has_no_scroll_wrapper(self, mock_gmail):
        """Page 2+ should return bare rows, no wrapper div."""
        mock_gmail.is_available.return_value = True
        mock_gmail.search_threads.return_value = {
            "threads": [{"id": "t2", "subject": "Page2", "from_name": "B",
                         "from_email": "b@b.c", "date": "", "snippet": "",
                         "message_count": 1, "participants": ["B"]}],
            "next_page_token": None,
        }
        resp = self.client.get(self._url(q="", link_url="/link/1/", page_token="PAGE2"))
        html = resp.content.decode()
        # Page 2 must NOT have the wrapper div
        self.assertNotIn('class="max-h-64 overflow-y-auto', html)
        # No Load More since next_page_token is None
        self.assertNotIn("Load more", html)
        # But row content should be present
        self.assertIn("Page2", html)

    @patch("email_links.views.gmail")
    def test_label_passed_through_to_search_threads(self, mock_gmail):
        mock_gmail.is_available.return_value = True
        mock_gmail.search_threads.return_value = {
            "threads": [], "next_page_token": None,
        }
        self.client.get(self._url(q="test", label="INBOX", link_url="/x/"))
        mock_gmail.search_threads.assert_called_once_with(
            query="test", max_results=15, page_token=None, label_ids=["INBOX"],
        )

    @patch("email_links.views.gmail")
    def test_empty_label_param_treated_as_none(self, mock_gmail):
        mock_gmail.is_available.return_value = True
        mock_gmail.search_threads.return_value = {
            "threads": [], "next_page_token": None,
        }
        self.client.get(self._url(q="", label="", link_url="/x/"))
        mock_gmail.search_threads.assert_called_once_with(
            query="", max_results=15, page_token=None, label_ids=None,
        )

    @patch("email_links.views.gmail")
    def test_empty_page_token_treated_as_none(self, mock_gmail):
        mock_gmail.is_available.return_value = True
        mock_gmail.search_threads.return_value = {
            "threads": [], "next_page_token": None,
        }
        self.client.get(self._url(q="", page_token="", link_url="/x/"))
        mock_gmail.search_threads.assert_called_once_with(
            query="", max_results=15, page_token=None, label_ids=None,
        )

    @patch("email_links.views.gmail")
    def test_load_more_preserves_label_in_url(self, mock_gmail):
        """When browsing with a label, Load More URL should include that label."""
        mock_gmail.is_available.return_value = True
        mock_gmail.search_threads.return_value = {
            "threads": [{"id": "t1", "subject": "X", "from_name": "",
                         "from_email": "a@b.c", "date": "", "snippet": "",
                         "message_count": 1, "participants": []}],
            "next_page_token": "NEXT",
        }
        resp = self.client.get(self._url(q="inv", label="SENT", link_url="/x/"))
        html = resp.content.decode()
        # Load More URL must contain both the label and query
        self.assertIn("label=SENT", html)
        self.assertIn("q=inv", html)
        self.assertIn("page_token=NEXT", html)

    @patch("email_links.views.gmail")
    def test_xss_in_subject_escaped(self, mock_gmail):
        mock_gmail.is_available.return_value = True
        mock_gmail.search_threads.return_value = {
            "threads": [{"id": "t1", "subject": '<script>alert("xss")</script>',
                         "from_name": "", "from_email": "a@b.c", "date": "",
                         "snippet": "", "message_count": 1, "participants": []}],
            "next_page_token": None,
        }
        resp = self.client.get(self._url(q="", link_url="/x/"))
        html = resp.content.decode()
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    @patch("email_links.views.gmail")
    def test_xss_in_query_param_escaped_in_load_more(self, mock_gmail):
        mock_gmail.is_available.return_value = True
        mock_gmail.search_threads.return_value = {
            "threads": [{"id": "t1", "subject": "X", "from_name": "",
                         "from_email": "a@b.c", "date": "", "snippet": "",
                         "message_count": 1, "participants": []}],
            "next_page_token": "TOK",
        }
        resp = self.client.get(self._url(q='"><img src=x>', link_url="/x/"))
        html = resp.content.decode()
        # The raw injection must not appear unescaped
        self.assertNotIn('"><img src=x>', html)

    @patch("email_links.views.gmail")
    def test_browsing_label_shows_recent_header(self, mock_gmail):
        """No query and no label = browsing mode, should show 'Recent emails'."""
        mock_gmail.is_available.return_value = True
        mock_gmail.search_threads.return_value = {
            "threads": [{"id": "t1", "subject": "X", "from_name": "",
                         "from_email": "a@b.c", "date": "", "snippet": "",
                         "message_count": 1, "participants": []}],
            "next_page_token": None,
        }
        resp = self.client.get(self._url(q="", link_url="/x/"))
        self.assertIn(b"Recent emails", resp.content)

    @patch("email_links.views.gmail")
    def test_label_set_no_recent_header(self, mock_gmail):
        """With a label selected, 'Recent emails' header should not appear."""
        mock_gmail.is_available.return_value = True
        mock_gmail.search_threads.return_value = {
            "threads": [{"id": "t1", "subject": "X", "from_name": "",
                         "from_email": "a@b.c", "date": "", "snippet": "",
                         "message_count": 1, "participants": []}],
            "next_page_token": None,
        }
        resp = self.client.get(self._url(q="", label="INBOX", link_url="/x/"))
        self.assertNotIn(b"Recent emails", resp.content)

    @patch("email_links.views.gmail")
    def test_search_threads_returns_none_shows_error(self, mock_gmail):
        mock_gmail.is_available.return_value = True
        mock_gmail.search_threads.return_value = None
        resp = self.client.get(self._url(q="test", link_url="/x/"))
        self.assertIn(b"Failed to search Gmail", resp.content)

    @patch("email_links.views.gmail")
    def test_empty_results_shows_no_emails(self, mock_gmail):
        mock_gmail.is_available.return_value = True
        mock_gmail.search_threads.return_value = {
            "threads": [], "next_page_token": None,
        }
        resp = self.client.get(self._url(q="nonexistent", link_url="/x/"))
        self.assertIn(b"No emails found", resp.content)


class SearchThreadsPaginationTest(TestCase):
    """Test that search_threads passes pagination and label params correctly."""

    @patch("email_links.gmail._get_service")
    def test_returns_next_page_token(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        # threads().list() returns stubs + nextPageToken
        mock_service.users().threads().list().execute.return_value = {
            "threads": [{"id": "t1"}],
            "nextPageToken": "TOKEN_2",
        }
        # threads().get() returns a thread with one message
        mock_service.users().threads().get().execute.return_value = {
            "id": "t1",
            "snippet": "hello",
            "messages": [{
                "payload": {"headers": [
                    {"name": "Subject", "value": "Test"},
                    {"name": "From", "value": "Alice <alice@test.com>"},
                    {"name": "Date", "value": "Thu, 12 Mar 2026 12:00:00 +0000"},
                ]},
            }],
        }
        result = gmail.search_threads(query="test")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["next_page_token"], "TOKEN_2")
        self.assertEqual(len(result["threads"]), 1)
        self.assertEqual(result["threads"][0]["subject"], "Test")

    @patch("email_links.gmail._get_service")
    def test_page_token_passed_to_api(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.users().threads().list().execute.return_value = {"threads": []}
        gmail.search_threads(query="", page_token="MY_TOKEN")
        call_kwargs = mock_service.users().threads().list.call_args
        self.assertEqual(call_kwargs[1].get("pageToken"), "MY_TOKEN")

    @patch("email_links.gmail._get_service")
    def test_label_ids_passed_to_api(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.users().threads().list().execute.return_value = {"threads": []}
        gmail.search_threads(query="", label_ids=["INBOX"])
        call_kwargs = mock_service.users().threads().list.call_args
        self.assertEqual(call_kwargs[1].get("labelIds"), ["INBOX"])

    @patch("email_links.gmail._get_service")
    def test_empty_result_returns_dict(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.users().threads().list().execute.return_value = {"threads": []}
        result = gmail.search_threads()
        self.assertEqual(result, {"threads": [], "next_page_token": None})


class GetLabelsTest(TestCase):
    """Test get_labels caching and filtering."""

    def setUp(self):
        cache.delete(gmail.LABELS_CACHE_KEY)

    @patch("email_links.gmail._get_service")
    def test_returns_filtered_labels(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.users().labels().list().execute.return_value = {
            "labels": [
                {"id": "INBOX", "name": "INBOX", "type": "system"},
                {"id": "SENT", "name": "SENT", "type": "system"},
                {"id": "SPAM", "name": "SPAM", "type": "system"},
                {"id": "TRASH", "name": "TRASH", "type": "system"},
                {"id": "UNREAD", "name": "UNREAD", "type": "system"},
                {"id": "CATEGORY_SOCIAL", "name": "CATEGORY_SOCIAL", "type": "system"},
                {"id": "Label_1", "name": "My Label", "type": "user"},
            ],
        }
        result = gmail.get_labels()
        ids = [l["id"] for l in result]
        self.assertIn("INBOX", ids)
        self.assertIn("SENT", ids)
        self.assertIn("Label_1", ids)
        self.assertNotIn("SPAM", ids)
        self.assertNotIn("TRASH", ids)
        self.assertNotIn("UNREAD", ids)
        self.assertNotIn("CATEGORY_SOCIAL", ids)

    @patch("email_links.gmail._get_service")
    def test_labels_cached(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.users().labels().list().execute.return_value = {
            "labels": [{"id": "INBOX", "name": "INBOX", "type": "system"}],
        }
        first = gmail.get_labels()
        second = gmail.get_labels()
        self.assertEqual(first, second)
        # API should only be called once
        mock_service.users().labels().list().execute.assert_called_once()

    @patch("email_links.gmail._get_service")
    def test_system_labels_sorted_first(self, mock_get_service):
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        mock_service.users().labels().list().execute.return_value = {
            "labels": [
                {"id": "SENT", "name": "SENT", "type": "system"},
                {"id": "INBOX", "name": "INBOX", "type": "system"},
                {"id": "Label_1", "name": "Zebra", "type": "user"},
                {"id": "Label_2", "name": "Alpha", "type": "user"},
            ],
        }
        result = gmail.get_labels()
        names = [l["name"] for l in result]
        # System first in defined order, then user alphabetical
        self.assertEqual(names, ["Inbox", "Sent", "Alpha", "Zebra"])
