import json
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from assets.models import Loan
from cashflow.models import CashFlowEntry
from notes.models import Note
from stakeholders.models import ContactLog, Stakeholder
from tasks.models import FollowUp, Task

from .views import _parse_date, get_activity_timeline


class DashboardViewTests(TestCase):
    def test_status_code(self):
        resp = self.client.get(reverse("dashboard:index"))
        self.assertEqual(resp.status_code, 200)

    def test_context_keys(self):
        resp = self.client.get(reverse("dashboard:index"))
        for key in ("overdue_tasks", "upcoming_tasks", "stale_followups",
                     "recent_activity", "liquidity_alerts", "cashflow"):
            self.assertIn(key, resp.context, f"Missing context key: {key}")

    def test_overdue_tasks_in_context(self):
        Task.objects.create(
            title="Overdue",
            due_date=timezone.localdate() - timedelta(days=2),
            status="not_started",
        )
        resp = self.client.get(reverse("dashboard:index"))
        self.assertTrue(resp.context["overdue_tasks"].exists())

    def test_upcoming_tasks(self):
        Task.objects.create(
            title="Soon",
            due_date=timezone.localdate() + timedelta(days=3),
            status="not_started",
        )
        resp = self.client.get(reverse("dashboard:index"))
        self.assertTrue(resp.context["upcoming_tasks"].exists())

    def test_stale_followups(self):
        s = Stakeholder.objects.create(name="Stale Person")
        t = Task.objects.create(title="Stale Task")
        FollowUp.objects.create(
            task=t, stakeholder=s,
            outreach_date=timezone.now() - timedelta(days=5),
            method="email", response_received=False,
        )
        resp = self.client.get(reverse("dashboard:index"))
        self.assertTrue(resp.context["stale_followups"].exists())

    def test_cashflow_summary(self):
        today = timezone.localdate()
        CashFlowEntry.objects.create(
            description="Income", amount=Decimal("3000"),
            entry_type="inflow", date=today, is_projected=False,
        )
        CashFlowEntry.objects.create(
            description="Expense", amount=Decimal("1000"),
            entry_type="outflow", date=today, is_projected=False,
        )
        resp = self.client.get(reverse("dashboard:index"))
        cf = resp.context["cashflow"]
        self.assertEqual(cf["actual_inflows"], Decimal("3000"))
        self.assertEqual(cf["actual_outflows"], Decimal("1000"))


class GlobalSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(name="Searchable Person")
        cls.task = Task.objects.create(title="Searchable Task")

    def test_status_code(self):
        resp = self.client.get(reverse("dashboard:search"))
        self.assertEqual(resp.status_code, 200)

    def test_empty_query(self):
        resp = self.client.get(reverse("dashboard:search"), {"q": ""})
        self.assertFalse(resp.context["has_results"])

    def test_finds_stakeholder(self):
        resp = self.client.get(reverse("dashboard:search"), {"q": "Searchable Person"})
        self.assertTrue(resp.context["has_results"])
        self.assertTrue(resp.context["stakeholders"].exists())

    def test_finds_across_models(self):
        resp = self.client.get(reverse("dashboard:search"), {"q": "Searchable"})
        self.assertTrue(resp.context["has_results"])
        self.assertTrue(resp.context["stakeholders"].exists())
        self.assertTrue(resp.context["tasks_results"].exists())

    def test_htmx_partial(self):
        resp = self.client.get(
            reverse("dashboard:search"),
            {"q": "test"},
            HTTP_HX_REQUEST="true",
        )
        self.assertTemplateUsed(resp, "dashboard/partials/_search_results.html")

    def test_limit_results(self):
        for i in range(15):
            Stakeholder.objects.create(name=f"Bulk Person {i}")
        resp = self.client.get(reverse("dashboard:search"), {"q": "Bulk Person"})
        self.assertTrue(len(resp.context["stakeholders"]) <= 10)


class ActivityTimelineTests(TestCase):
    def test_empty_returns_list(self):
        items = get_activity_timeline()
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 0)

    def test_contact_log_item_keys(self):
        s = Stakeholder.objects.create(name="Timeline Person")
        ContactLog.objects.create(
            stakeholder=s, date=timezone.now(), method="call", summary="Test call",
        )
        items = get_activity_timeline()
        self.assertTrue(len(items) >= 1)
        item = [i for i in items if i["type"] == "contact"][0]
        for key in ("date", "type", "color", "icon", "title", "summary", "url"):
            self.assertIn(key, item)

    def test_includes_multiple_types(self):
        s = Stakeholder.objects.create(name="Multi")
        ContactLog.objects.create(
            stakeholder=s, date=timezone.now(), method="call", summary="call",
        )
        Note.objects.create(title="Note", content="c", date=timezone.now())
        Task.objects.create(title="Task")
        items = get_activity_timeline()
        types = {i["type"] for i in items}
        self.assertIn("contact", types)
        self.assertIn("note", types)
        self.assertIn("task", types)

    def test_sorted_reverse_chronological(self):
        s = Stakeholder.objects.create(name="Sort")
        ContactLog.objects.create(
            stakeholder=s, date=timezone.now() - timedelta(days=5),
            method="call", summary="old",
        )
        Note.objects.create(title="Recent", content="c", date=timezone.now())
        items = get_activity_timeline()
        if len(items) >= 2:
            self.assertGreaterEqual(items[0]["date"], items[1]["date"])

    def test_respects_limit(self):
        s = Stakeholder.objects.create(name="Limit")
        for i in range(5):
            ContactLog.objects.create(
                stakeholder=s, date=timezone.now() - timedelta(hours=i),
                method="call", summary=f"call {i}",
            )
        items = get_activity_timeline(limit=3)
        self.assertEqual(len(items), 3)

    def test_timeline_view(self):
        resp = self.client.get(reverse("dashboard:timeline"))
        self.assertEqual(resp.status_code, 200)


class CalendarTests(TestCase):
    def test_calendar_view(self):
        resp = self.client.get(reverse("dashboard:calendar"))
        self.assertEqual(resp.status_code, 200)

    def test_events_returns_json(self):
        resp = self.client.get(reverse("dashboard:calendar_events"))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIsInstance(data, list)

    def test_events_include_tasks(self):
        Task.objects.create(
            title="Calendar Task",
            due_date=timezone.localdate() + timedelta(days=1),
            status="not_started",
        )
        resp = self.client.get(reverse("dashboard:calendar_events"))
        data = json.loads(resp.content)
        task_events = [e for e in data if e.get("extendedProps", {}).get("type") == "task"]
        self.assertTrue(len(task_events) >= 1)

    def test_events_include_loan_payments(self):
        Loan.objects.create(
            name="Calendar Loan",
            status="active",
            next_payment_date=timezone.localdate() + timedelta(days=5),
        )
        resp = self.client.get(reverse("dashboard:calendar_events"))
        data = json.loads(resp.content)
        payment_events = [e for e in data if e.get("extendedProps", {}).get("type") == "payment"]
        self.assertTrue(len(payment_events) >= 1)

    def test_date_filtering(self):
        today = timezone.localdate()
        Task.objects.create(
            title="In Range", due_date=today + timedelta(days=2), status="not_started",
        )
        Task.objects.create(
            title="Out of Range", due_date=today + timedelta(days=60), status="not_started",
        )
        resp = self.client.get(reverse("dashboard:calendar_events"), {
            "start": str(today),
            "end": str(today + timedelta(days=30)),
        })
        data = json.loads(resp.content)
        titles = [e["title"] for e in data]
        self.assertIn("In Range", titles)
        self.assertNotIn("Out of Range", titles)

    def test_parse_date_valid(self):
        result = _parse_date("2025-06-15T00:00:00")
        self.assertIsNotNone(result)

    def test_parse_date_invalid(self):
        result = _parse_date("not-a-date")
        self.assertIsNone(result)

    def test_parse_date_empty(self):
        result = _parse_date("")
        self.assertIsNone(result)
