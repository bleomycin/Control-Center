from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from stakeholders.models import Stakeholder

from .models import Investment, Loan, RealEstate


class RealEstateModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(name="Owner")
        cls.prop = RealEstate.objects.create(
            name="Main Office",
            address="123 Main St",
            stakeholder=cls.stakeholder,
            estimated_value=Decimal("500000.00"),
        )

    def test_defaults(self):
        p = RealEstate.objects.create(name="Lot", address="456 Elm")
        self.assertEqual(p.status, "owned")
        self.assertIsNone(p.estimated_value)

    def test_str(self):
        self.assertEqual(str(self.prop), "Main Office")

    def test_get_absolute_url(self):
        self.assertEqual(
            self.prop.get_absolute_url(),
            reverse("assets:realestate_detail", kwargs={"pk": self.prop.pk}),
        )

    def test_stakeholder_set_null(self):
        self.stakeholder.delete()
        self.prop.refresh_from_db()
        self.assertIsNone(self.prop.stakeholder)

    def test_decimal_precision(self):
        p = RealEstate.objects.create(
            name="Test", address="x", estimated_value=Decimal("1234567890.12")
        )
        p.refresh_from_db()
        self.assertEqual(p.estimated_value, Decimal("1234567890.12"))

    def test_ordering(self):
        RealEstate.objects.create(name="Alpha", address="a")
        RealEstate.objects.create(name="Zulu", address="z")
        names = list(RealEstate.objects.values_list("name", flat=True))
        self.assertEqual(names, sorted(names))


class InvestmentModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(name="Investor")
        cls.inv = Investment.objects.create(
            name="Stock Portfolio",
            investment_type="equities",
            stakeholder=cls.stakeholder,
        )

    def test_create(self):
        self.assertEqual(self.inv.name, "Stock Portfolio")

    def test_str_and_url(self):
        self.assertEqual(str(self.inv), "Stock Portfolio")
        self.assertEqual(
            self.inv.get_absolute_url(),
            reverse("assets:investment_detail", kwargs={"pk": self.inv.pk}),
        )

    def test_stakeholder_set_null(self):
        self.stakeholder.delete()
        self.inv.refresh_from_db()
        self.assertIsNone(self.inv.stakeholder)


class LoanModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.lender = Stakeholder.objects.create(name="Bank")
        cls.loan = Loan.objects.create(
            name="Mortgage",
            lender=cls.lender,
            original_amount=Decimal("250000.00"),
            interest_rate=Decimal("4.500"),
        )

    def test_defaults(self):
        loan = Loan.objects.create(name="Simple Loan")
        self.assertEqual(loan.status, "active")

    def test_str_and_url(self):
        self.assertEqual(str(self.loan), "Mortgage")
        self.assertEqual(
            self.loan.get_absolute_url(),
            reverse("assets:loan_detail", kwargs={"pk": self.loan.pk}),
        )

    def test_lender_set_null(self):
        self.lender.delete()
        self.loan.refresh_from_db()
        self.assertIsNone(self.loan.lender)

    def test_decimal_fields(self):
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.interest_rate, Decimal("4.500"))


class AssetViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prop = RealEstate.objects.create(
            name="View Test Prop", address="789 Oak"
        )
        cls.inv = Investment.objects.create(
            name="View Test Inv", investment_type="bonds"
        )
        cls.loan = Loan.objects.create(
            name="View Test Loan",
            original_amount=Decimal("100000.00"),
        )

    # --- Real Estate ---
    def test_realestate_list(self):
        resp = self.client.get(reverse("assets:realestate_list"))
        self.assertEqual(resp.status_code, 200)

    def test_realestate_list_search(self):
        resp = self.client.get(reverse("assets:realestate_list"), {"q": "View Test"})
        self.assertContains(resp, "View Test Prop")

    def test_realestate_list_htmx(self):
        resp = self.client.get(
            reverse("assets:realestate_list"), HTTP_HX_REQUEST="true"
        )
        self.assertTemplateUsed(resp, "assets/partials/_realestate_table_rows.html")

    def test_realestate_create(self):
        resp = self.client.post(reverse("assets:realestate_create"), {
            "name": "New Prop",
            "address": "111 New St",
            "status": "owned",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(RealEstate.objects.filter(name="New Prop").exists())

    def test_realestate_detail(self):
        resp = self.client.get(reverse("assets:realestate_detail", args=[self.prop.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_realestate_csv(self):
        resp = self.client.get(reverse("assets:realestate_export_csv"))
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("Name", resp.content.decode())

    def test_realestate_pdf(self):
        resp = self.client.get(reverse("assets:realestate_export_pdf", args=[self.prop.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")

    # --- Investments ---
    def test_investment_list(self):
        resp = self.client.get(reverse("assets:investment_list"))
        self.assertEqual(resp.status_code, 200)

    def test_investment_list_htmx(self):
        resp = self.client.get(
            reverse("assets:investment_list"), HTTP_HX_REQUEST="true"
        )
        self.assertTemplateUsed(resp, "assets/partials/_investment_table_rows.html")

    def test_investment_create(self):
        resp = self.client.post(reverse("assets:investment_create"), {
            "name": "New Inv",
        })
        self.assertEqual(resp.status_code, 302)

    def test_investment_detail(self):
        resp = self.client.get(reverse("assets:investment_detail", args=[self.inv.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_investment_csv(self):
        resp = self.client.get(reverse("assets:investment_export_csv"))
        self.assertEqual(resp["Content-Type"], "text/csv")

    def test_investment_pdf(self):
        resp = self.client.get(reverse("assets:investment_export_pdf", args=[self.inv.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")

    # --- Loans ---
    def test_loan_list(self):
        resp = self.client.get(reverse("assets:loan_list"))
        self.assertEqual(resp.status_code, 200)

    def test_loan_list_htmx(self):
        resp = self.client.get(
            reverse("assets:loan_list"), HTTP_HX_REQUEST="true"
        )
        self.assertTemplateUsed(resp, "assets/partials/_loan_table_rows.html")

    def test_loan_create(self):
        resp = self.client.post(reverse("assets:loan_create"), {
            "name": "New Loan",
            "status": "active",
        })
        self.assertEqual(resp.status_code, 302)

    def test_loan_detail(self):
        resp = self.client.get(reverse("assets:loan_detail", args=[self.loan.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_loan_csv(self):
        resp = self.client.get(reverse("assets:loan_export_csv"))
        self.assertEqual(resp["Content-Type"], "text/csv")

    def test_loan_pdf(self):
        resp = self.client.get(reverse("assets:loan_export_pdf", args=[self.loan.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")
