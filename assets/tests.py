from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from stakeholders.models import Stakeholder

from .models import (
    Investment, InvestmentParticipant, Loan, LoanParty,
    PropertyOwnership, RealEstate,
)


class RealEstateModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(name="Owner")
        cls.prop = RealEstate.objects.create(
            name="Main Office",
            address="123 Main St",
            estimated_value=Decimal("500000.00"),
        )
        cls.ownership = PropertyOwnership.objects.create(
            property=cls.prop,
            stakeholder=cls.stakeholder,
            ownership_percentage=Decimal("100.00"),
            role="Owner",
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

    def test_stakeholder_m2m(self):
        self.assertIn(self.stakeholder, self.prop.stakeholders.all())

    def test_ownership_cascade_on_stakeholder_delete(self):
        s = Stakeholder.objects.create(name="Temp Owner")
        p = RealEstate.objects.create(name="Temp", address="x")
        PropertyOwnership.objects.create(property=p, stakeholder=s, role="Owner")
        s.delete()
        self.assertEqual(p.stakeholders.count(), 0)

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
        )
        cls.participant = InvestmentParticipant.objects.create(
            investment=cls.inv,
            stakeholder=cls.stakeholder,
            ownership_percentage=Decimal("100.00"),
            role="Lead Investor",
        )

    def test_create(self):
        self.assertEqual(self.inv.name, "Stock Portfolio")

    def test_str_and_url(self):
        self.assertEqual(str(self.inv), "Stock Portfolio")
        self.assertEqual(
            self.inv.get_absolute_url(),
            reverse("assets:investment_detail", kwargs={"pk": self.inv.pk}),
        )

    def test_stakeholder_m2m(self):
        self.assertIn(self.stakeholder, self.inv.stakeholders.all())


class LoanModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.lender = Stakeholder.objects.create(name="Bank")
        cls.loan = Loan.objects.create(
            name="Mortgage",
            original_amount=Decimal("250000.00"),
            interest_rate=Decimal("4.500"),
        )
        cls.party = LoanParty.objects.create(
            loan=cls.loan,
            stakeholder=cls.lender,
            role="Lender",
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

    def test_stakeholder_m2m(self):
        self.assertIn(self.lender, self.loan.stakeholders.all())

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


class LoanAssetLinkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prop = RealEstate.objects.create(name="Linked Property", address="1 Main")
        cls.inv = Investment.objects.create(name="Linked Investment")
        cls.loan = Loan.objects.create(
            name="Property Mortgage", status="active",
            related_property=cls.prop,
            current_balance=Decimal("200000.00"),
            interest_rate=Decimal("5.000"),
            monthly_payment=Decimal("1200.00"),
        )
        cls.inv_loan = Loan.objects.create(
            name="Margin Loan", status="active",
            related_investment=cls.inv,
        )

    def test_property_detail_shows_linked_loan(self):
        resp = self.client.get(reverse("assets:realestate_detail", args=[self.prop.pk]))
        self.assertContains(resp, "Property Mortgage")
        self.assertContains(resp, "200,000")

    def test_investment_detail_shows_linked_loan(self):
        resp = self.client.get(reverse("assets:investment_detail", args=[self.inv.pk]))
        self.assertContains(resp, "Margin Loan")

    def test_loan_detail_shows_linked_property(self):
        resp = self.client.get(reverse("assets:loan_detail", args=[self.loan.pk]))
        self.assertContains(resp, "Linked Property")
        self.assertContains(resp, self.prop.get_absolute_url())

    def test_loan_detail_shows_linked_investment(self):
        resp = self.client.get(reverse("assets:loan_detail", args=[self.inv_loan.pk]))
        self.assertContains(resp, "Linked Investment")
        self.assertContains(resp, self.inv.get_absolute_url())

    def test_loan_create_prefills_property(self):
        resp = self.client.get(reverse("assets:loan_create"), {"property": self.prop.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'selected>{self.prop.name}')

    def test_loan_create_prefills_investment(self):
        resp = self.client.get(reverse("assets:loan_create"), {"investment": self.inv.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'selected>{self.inv.name}')

    def test_property_set_null_on_delete(self):
        self.prop.delete()
        self.loan.refresh_from_db()
        self.assertIsNone(self.loan.related_property)


class AssetCreateWithInitialOwnerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(name="Legacy", entity_type="contact")

    def test_property_create_with_initial_owner(self):
        resp = self.client.post(reverse("assets:realestate_create"), {
            "name": "New House", "address": "42 Oak", "status": "owned",
            "initial_stakeholder": self.stakeholder.pk,
            "initial_role": "Owner",
            "initial_percentage": "100.00",
        })
        self.assertEqual(resp.status_code, 302)
        prop = RealEstate.objects.get(name="New House")
        ownership = PropertyOwnership.objects.get(property=prop)
        self.assertEqual(ownership.stakeholder, self.stakeholder)
        self.assertEqual(ownership.role, "Owner")
        self.assertEqual(ownership.ownership_percentage, Decimal("100.00"))

    def test_property_create_without_initial_owner(self):
        resp = self.client.post(reverse("assets:realestate_create"), {
            "name": "Empty Lot", "address": "99 Elm", "status": "owned",
        })
        self.assertEqual(resp.status_code, 302)
        prop = RealEstate.objects.get(name="Empty Lot")
        self.assertEqual(prop.ownerships.count(), 0)

    def test_investment_create_with_initial_participant(self):
        resp = self.client.post(reverse("assets:investment_create"), {
            "name": "New Fund",
            "initial_stakeholder": self.stakeholder.pk,
            "initial_role": "Lead Investor",
            "initial_percentage": "50.00",
        })
        self.assertEqual(resp.status_code, 302)
        inv = Investment.objects.get(name="New Fund")
        participant = InvestmentParticipant.objects.get(investment=inv)
        self.assertEqual(participant.stakeholder, self.stakeholder)
        self.assertEqual(participant.role, "Lead Investor")

    def test_property_edit_hides_initial_owner_fields(self):
        prop = RealEstate.objects.create(name="Existing", address="1 St")
        resp = self.client.get(reverse("assets:realestate_edit", args=[prop.pk]))
        self.assertNotContains(resp, "Initial Owner")


class UnifiedAssetListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prop = RealEstate.objects.create(
            name="Test Property", address="100 Main St",
            estimated_value=Decimal("500000.00"), status="owned",
        )
        cls.inv = Investment.objects.create(
            name="Test Investment", investment_type="equities",
        )
        cls.loan = Loan.objects.create(
            name="Test Loan", status="active",
            current_balance=Decimal("200000.00"),
        )

    def test_asset_list_default_tab(self):
        resp = self.client.get(reverse("assets:asset_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Test Property")
        self.assertTemplateUsed(resp, "assets/asset_list.html")

    def test_asset_list_properties_tab(self):
        resp = self.client.get(reverse("assets:asset_list"), {"tab": "properties"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Test Property")

    def test_asset_list_investments_tab(self):
        resp = self.client.get(reverse("assets:asset_list"), {"tab": "investments"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Test Investment")

    def test_asset_list_loans_tab(self):
        resp = self.client.get(reverse("assets:asset_list"), {"tab": "loans"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Test Loan")

    def test_asset_list_invalid_tab_defaults_to_properties(self):
        resp = self.client.get(reverse("assets:asset_list"), {"tab": "invalid"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Test Property")

    def test_asset_list_htmx_returns_partial(self):
        resp = self.client.get(
            reverse("assets:asset_list"), {"tab": "properties"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "assets/partials/_asset_tab_content.html")

    def test_asset_list_htmx_investments(self):
        resp = self.client.get(
            reverse("assets:asset_list"), {"tab": "investments"},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(resp, "Test Investment")
        self.assertTemplateUsed(resp, "assets/partials/_asset_tab_content.html")

    def test_asset_list_htmx_loans(self):
        resp = self.client.get(
            reverse("assets:asset_list"), {"tab": "loans"},
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(resp, "Test Loan")

    def test_asset_list_search_properties(self):
        resp = self.client.get(reverse("assets:asset_list"), {"tab": "properties", "q": "Test Prop"})
        self.assertContains(resp, "Test Property")

    def test_asset_list_search_no_match(self):
        resp = self.client.get(reverse("assets:asset_list"), {"tab": "properties", "q": "Nonexistent"})
        self.assertNotContains(resp, "Test Property")

    def test_asset_list_filter_status(self):
        resp = self.client.get(reverse("assets:asset_list"), {"tab": "properties", "status": "sold"})
        self.assertNotContains(resp, "Test Property")

    def test_asset_list_tab_counts(self):
        resp = self.client.get(reverse("assets:asset_list"))
        self.assertEqual(resp.context["tab_counts"]["properties"], 1)
        self.assertEqual(resp.context["tab_counts"]["investments"], 1)
        self.assertEqual(resp.context["tab_counts"]["loans"], 1)


class InlineStatusUpdateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prop = RealEstate.objects.create(
            name="Inline Prop", address="1 Test", status="owned",
        )
        cls.loan = Loan.objects.create(
            name="Inline Loan", status="active",
        )

    def test_realestate_inline_status_update(self):
        resp = self.client.post(
            reverse("assets:realestate_inline_status", args=[self.prop.pk]),
            {"status": "sold"},
        )
        self.assertEqual(resp.status_code, 200)
        self.prop.refresh_from_db()
        self.assertEqual(self.prop.status, "sold")
        self.assertTemplateUsed(resp, "assets/partials/_realestate_row.html")

    def test_realestate_inline_status_invalid(self):
        resp = self.client.post(
            reverse("assets:realestate_inline_status", args=[self.prop.pk]),
            {"status": "bogus"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_realestate_inline_status_empty(self):
        resp = self.client.post(
            reverse("assets:realestate_inline_status", args=[self.prop.pk]),
            {},
        )
        self.assertEqual(resp.status_code, 400)

    def test_loan_inline_status_update(self):
        resp = self.client.post(
            reverse("assets:loan_inline_status", args=[self.loan.pk]),
            {"status": "paid_off"},
        )
        self.assertEqual(resp.status_code, 200)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.status, "paid_off")
        self.assertTemplateUsed(resp, "assets/partials/_loan_row.html")

    def test_loan_inline_status_invalid(self):
        resp = self.client.post(
            reverse("assets:loan_inline_status", args=[self.loan.pk]),
            {"status": "bogus"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_realestate_inline_status_404(self):
        resp = self.client.post(
            reverse("assets:realestate_inline_status", args=[99999]),
            {"status": "owned"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_loan_inline_status_404(self):
        resp = self.client.post(
            reverse("assets:loan_inline_status", args=[99999]),
            {"status": "active"},
        )
        self.assertEqual(resp.status_code, 404)
