import json
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from assets.models import Loan
from stakeholders.models import Stakeholder

from .alerts import get_liquidity_alerts
from .models import CashFlowEntry


class CashFlowEntryModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.entry = CashFlowEntry.objects.create(
            description="Test Income",
            amount=Decimal("5000.00"),
            entry_type="inflow",
            category="salary",
            date=timezone.localdate(),
        )

    def test_create(self):
        self.assertEqual(self.entry.description, "Test Income")

    def test_str(self):
        s = str(self.entry)
        self.assertIn("Test Income", s)
        self.assertIn("inflow", s)

    def test_ordering(self):
        CashFlowEntry.objects.create(
            description="Old", amount=Decimal("100"), entry_type="inflow",
            date=timezone.localdate() - timedelta(days=30),
        )
        CashFlowEntry.objects.create(
            description="New", amount=Decimal("100"), entry_type="inflow",
            date=timezone.localdate(),
        )
        first = CashFlowEntry.objects.first()
        self.assertEqual(first.date, timezone.localdate())

    def test_optional_fks_set_null(self):
        s = Stakeholder.objects.create(name="Temp")
        entry = CashFlowEntry.objects.create(
            description="FK Test", amount=Decimal("100"), entry_type="inflow",
            date=timezone.localdate(), related_stakeholder=s,
        )
        s.delete()
        entry.refresh_from_db()
        self.assertIsNone(entry.related_stakeholder)

    def test_amount_precision(self):
        entry = CashFlowEntry.objects.create(
            description="Precise", amount=Decimal("123456789012.34"),
            entry_type="outflow", date=timezone.localdate(),
        )
        entry.refresh_from_db()
        self.assertEqual(entry.amount, Decimal("123456789012.34"))


class CashFlowViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.inflow = CashFlowEntry.objects.create(
            description="View Inflow", amount=Decimal("1000"),
            entry_type="inflow", date=today,
        )
        cls.outflow = CashFlowEntry.objects.create(
            description="View Outflow", amount=Decimal("500"),
            entry_type="outflow", date=today,
        )

    def test_list(self):
        resp = self.client.get(reverse("cashflow:list"))
        self.assertEqual(resp.status_code, 200)

    def test_list_type_filter(self):
        resp = self.client.get(reverse("cashflow:list"), {"type": "inflow"})
        self.assertContains(resp, "View Inflow")
        self.assertNotContains(resp, "View Outflow")

    def test_list_projected_filter(self):
        CashFlowEntry.objects.create(
            description="Projected", amount=Decimal("300"),
            entry_type="inflow", date=timezone.localdate(), is_projected=True,
        )
        resp = self.client.get(reverse("cashflow:list"), {"projected": "projected"})
        self.assertContains(resp, "Projected")

    def test_list_search(self):
        resp = self.client.get(reverse("cashflow:list"), {"q": "View Inflow"})
        self.assertContains(resp, "View Inflow")

    def test_list_htmx(self):
        resp = self.client.get(reverse("cashflow:list"), HTTP_HX_REQUEST="true")
        self.assertTemplateUsed(resp, "cashflow/partials/_cashflow_table_rows.html")

    def test_list_context_totals(self):
        resp = self.client.get(reverse("cashflow:list"))
        self.assertIn("total_inflows", resp.context)
        self.assertIn("total_outflows", resp.context)
        self.assertIn("net_flow", resp.context)

    def test_list_context_alerts(self):
        resp = self.client.get(reverse("cashflow:list"))
        self.assertIn("liquidity_alerts", resp.context)

    def test_create(self):
        resp = self.client.post(reverse("cashflow:create"), {
            "description": "New Entry",
            "amount": "750.00",
            "entry_type": "inflow",
            "date": "2025-06-15",
        })
        self.assertEqual(resp.status_code, 302)

    def test_csv(self):
        resp = self.client.get(reverse("cashflow:export_csv"))
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("Description", resp.content.decode())


class ChartDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        CashFlowEntry.objects.create(
            description="Actual Income", amount=Decimal("2000"),
            entry_type="inflow", category="salary", date=today, is_projected=False,
        )
        CashFlowEntry.objects.create(
            description="Projected Income", amount=Decimal("1000"),
            entry_type="inflow", category="bonus", date=today, is_projected=True,
        )

    def test_returns_json(self):
        resp = self.client.get(reverse("cashflow:chart_data"))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn("monthly", data)
        self.assertIn("categories", data)

    def test_monthly_aggregation(self):
        resp = self.client.get(reverse("cashflow:chart_data"))
        data = json.loads(resp.content)
        self.assertIn("labels", data["monthly"])
        self.assertIn("inflows", data["monthly"])

    def test_excludes_projected(self):
        resp = self.client.get(reverse("cashflow:chart_data"))
        data = json.loads(resp.content)
        # Only actual entry in monthly
        if data["monthly"]["inflows"]:
            self.assertEqual(data["monthly"]["inflows"][0], 2000.0)

    def test_category_breakdown(self):
        resp = self.client.get(reverse("cashflow:chart_data"))
        data = json.loads(resp.content)
        self.assertIn("labels", data["categories"])
        self.assertIn("values", data["categories"])


class LiquidityAlertTests(TestCase):
    def test_net_negative_flow(self):
        today = timezone.localdate()
        CashFlowEntry.objects.create(
            description="Income", amount=Decimal("1000"),
            entry_type="inflow", date=today, is_projected=False,
        )
        CashFlowEntry.objects.create(
            description="Expense", amount=Decimal("2000"),
            entry_type="outflow", date=today, is_projected=False,
        )
        alerts = get_liquidity_alerts()
        critical = [a for a in alerts if a["level"] == "critical"]
        self.assertTrue(len(critical) >= 1)
        self.assertIn("Negative", critical[0]["title"])

    def test_no_alert_positive_flow(self):
        today = timezone.localdate()
        CashFlowEntry.objects.create(
            description="Big Income", amount=Decimal("5000"),
            entry_type="inflow", date=today, is_projected=False,
        )
        CashFlowEntry.objects.create(
            description="Small Expense", amount=Decimal("1000"),
            entry_type="outflow", date=today, is_projected=False,
        )
        alerts = get_liquidity_alerts()
        critical = [a for a in alerts if a["level"] == "critical"]
        self.assertEqual(len(critical), 0)

    def test_large_upcoming_payments(self):
        today = timezone.localdate()
        Loan.objects.create(
            name="Big Loan",
            status="active",
            monthly_payment=Decimal("6000.00"),
            next_payment_date=today + timedelta(days=10),
        )
        alerts = get_liquidity_alerts()
        warnings = [a for a in alerts if a["title"] == "Large Upcoming Payments"]
        self.assertEqual(len(warnings), 1)

    def test_no_alert_under_threshold(self):
        today = timezone.localdate()
        Loan.objects.create(
            name="Small Loan",
            status="active",
            monthly_payment=Decimal("2000.00"),
            next_payment_date=today + timedelta(days=10),
        )
        alerts = get_liquidity_alerts()
        warnings = [a for a in alerts if a["title"] == "Large Upcoming Payments"]
        self.assertEqual(len(warnings), 0)

    def test_projected_shortfall(self):
        today = timezone.localdate()
        CashFlowEntry.objects.create(
            description="Proj In", amount=Decimal("1000"),
            entry_type="inflow", date=today + timedelta(days=5),
            is_projected=True,
        )
        CashFlowEntry.objects.create(
            description="Proj Out", amount=Decimal("3000"),
            entry_type="outflow", date=today + timedelta(days=5),
            is_projected=True,
        )
        alerts = get_liquidity_alerts()
        shortfall = [a for a in alerts if a["title"] == "Projected Shortfall"]
        self.assertEqual(len(shortfall), 1)
