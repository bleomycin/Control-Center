import json

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from assets.models import (
    Investment, InvestmentParticipant, Loan, LoanParty,
    PropertyOwnership, RealEstate,
)
from .models import ContactLog, Relationship, Stakeholder


class StakeholderModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(
            name="John Doe",
            entity_type="advisor",
            email="john@example.com",
            phone="555-1234",
            organization="Acme Corp",
        )

    def test_create_defaults(self):
        s = Stakeholder.objects.create(name="Jane")
        self.assertEqual(s.entity_type, "contact")
        self.assertIsNone(s.trust_rating)
        self.assertIsNone(s.risk_rating)
        self.assertEqual(s.email, "")

    def test_str(self):
        self.assertEqual(str(self.stakeholder), "John Doe")

    def test_get_absolute_url(self):
        self.assertEqual(
            self.stakeholder.get_absolute_url(),
            reverse("stakeholders:detail", kwargs={"pk": self.stakeholder.pk}),
        )

    def test_ordering(self):
        Stakeholder.objects.create(name="Alice")
        Stakeholder.objects.create(name="Zara")
        names = list(Stakeholder.objects.values_list("name", flat=True))
        self.assertEqual(names, sorted(names))

    def test_trust_rating_min_validator(self):
        s = Stakeholder(name="Bad", trust_rating=0)
        with self.assertRaises(ValidationError):
            s.full_clean()

    def test_trust_rating_max_validator(self):
        s = Stakeholder(name="Bad", trust_rating=6)
        with self.assertRaises(ValidationError):
            s.full_clean()

    def test_risk_rating_min_validator(self):
        s = Stakeholder(name="Bad", risk_rating=0)
        with self.assertRaises(ValidationError):
            s.full_clean()

    def test_risk_rating_max_validator(self):
        s = Stakeholder(name="Bad", risk_rating=6)
        with self.assertRaises(ValidationError):
            s.full_clean()

    def test_valid_ratings(self):
        s = Stakeholder(name="Good", trust_rating=1, risk_rating=5)
        s.full_clean()  # should not raise

    def test_nullable_ratings(self):
        s = Stakeholder.objects.create(name="Nullable")
        self.assertIsNone(s.trust_rating)
        self.assertIsNone(s.risk_rating)


class RelationshipModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.s1 = Stakeholder.objects.create(name="Alice")
        cls.s2 = Stakeholder.objects.create(name="Bob")

    def test_create(self):
        r = Relationship.objects.create(
            from_stakeholder=self.s1,
            to_stakeholder=self.s2,
            relationship_type="partner",
        )
        self.assertEqual(r.from_stakeholder, self.s1)

    def test_str(self):
        r = Relationship.objects.create(
            from_stakeholder=self.s1,
            to_stakeholder=self.s2,
            relationship_type="advisor",
        )
        self.assertIn("Alice", str(r))
        self.assertIn("Bob", str(r))
        self.assertIn("advisor", str(r))

    def test_unique_together(self):
        Relationship.objects.create(
            from_stakeholder=self.s1,
            to_stakeholder=self.s2,
            relationship_type="partner",
        )
        with self.assertRaises(IntegrityError):
            Relationship.objects.create(
                from_stakeholder=self.s1,
                to_stakeholder=self.s2,
                relationship_type="partner",
            )

    def test_cascade_delete(self):
        Relationship.objects.create(
            from_stakeholder=self.s1,
            to_stakeholder=self.s2,
            relationship_type="partner",
        )
        self.s1.delete()
        self.assertEqual(Relationship.objects.count(), 0)


class ContactLogModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(name="Alice")

    def test_create(self):
        log = ContactLog.objects.create(
            stakeholder=self.stakeholder,
            date=timezone.now(),
            method="call",
            summary="Discussed project.",
        )
        self.assertEqual(log.stakeholder, self.stakeholder)

    def test_ordering(self):
        ContactLog.objects.create(
            stakeholder=self.stakeholder,
            date=timezone.now() - timezone.timedelta(days=2),
            method="call",
            summary="Old",
        )
        ContactLog.objects.create(
            stakeholder=self.stakeholder,
            date=timezone.now(),
            method="email",
            summary="New",
        )
        logs = list(ContactLog.objects.all())
        self.assertEqual(logs[0].summary, "New")

    def test_cascade_on_stakeholder_delete(self):
        ContactLog.objects.create(
            stakeholder=self.stakeholder,
            date=timezone.now(),
            method="call",
            summary="Test",
        )
        self.stakeholder.delete()
        self.assertEqual(ContactLog.objects.count(), 0)


class StakeholderViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(
            name="Test Person",
            entity_type="advisor",
            email="test@example.com",
        )

    def test_list_status_code(self):
        resp = self.client.get(reverse("stakeholders:list"))
        self.assertEqual(resp.status_code, 200)

    def test_list_search(self):
        resp = self.client.get(reverse("stakeholders:list"), {"q": "Test"})
        self.assertContains(resp, "Test Person")

    def test_list_search_no_match(self):
        resp = self.client.get(reverse("stakeholders:list"), {"q": "zzzzz"})
        self.assertNotContains(resp, "Test Person")

    def test_list_type_filter(self):
        resp = self.client.get(reverse("stakeholders:list"), {"type": "advisor"})
        self.assertContains(resp, "Test Person")

    def test_list_htmx_partial(self):
        resp = self.client.get(
            reverse("stakeholders:list"),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "stakeholders/partials/_tab_content.html")

    def test_create_get(self):
        resp = self.client.get(reverse("stakeholders:create"))
        self.assertEqual(resp.status_code, 200)

    def test_create_post_valid(self):
        resp = self.client.post(reverse("stakeholders:create"), {
            "name": "New Person",
            "entity_type": "contact",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Stakeholder.objects.filter(name="New Person").exists())

    def test_create_post_invalid(self):
        resp = self.client.post(reverse("stakeholders:create"), {
            "name": "",
            "entity_type": "contact",
        })
        self.assertEqual(resp.status_code, 200)  # re-renders form

    def test_detail(self):
        resp = self.client.get(reverse("stakeholders:detail", args=[self.stakeholder.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("contact_logs", resp.context)
        self.assertIn("contact_log_form", resp.context)

    def test_update(self):
        resp = self.client.post(
            reverse("stakeholders:edit", args=[self.stakeholder.pk]),
            {"name": "Updated Person", "entity_type": "advisor"},
        )
        self.assertEqual(resp.status_code, 302)
        self.stakeholder.refresh_from_db()
        self.assertEqual(self.stakeholder.name, "Updated Person")

    def test_delete(self):
        s = Stakeholder.objects.create(name="To Delete")
        resp = self.client.post(reverse("stakeholders:delete", args=[s.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Stakeholder.objects.filter(pk=s.pk).exists())

    def test_csv_export(self):
        resp = self.client.get(reverse("stakeholders:export_csv"))
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("attachment", resp["Content-Disposition"])
        content = resp.content.decode()
        self.assertIn("Name", content)

    def test_pdf_export(self):
        resp = self.client.get(reverse("stakeholders:export_pdf", args=[self.stakeholder.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn("attachment", resp["Content-Disposition"])

    def test_contact_log_add(self):
        resp = self.client.post(
            reverse("stakeholders:contact_log_add", args=[self.stakeholder.pk]),
            {
                "date": "2025-01-15T10:00",
                "method": "call",
                "summary": "Test log entry",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(ContactLog.objects.filter(summary="Test log entry").exists())

    def test_contact_log_delete(self):
        log = ContactLog.objects.create(
            stakeholder=self.stakeholder,
            date=timezone.now(),
            method="email",
            summary="To delete",
        )
        resp = self.client.post(reverse("stakeholders:contact_log_delete", args=[log.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ContactLog.objects.filter(pk=log.pk).exists())

    def test_graph_data_returns_json(self):
        resp = self.client.get(reverse("stakeholders:graph_data", args=[self.stakeholder.pk]))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn("nodes", data)
        self.assertIn("edges", data)

    def test_graph_data_includes_center_node(self):
        resp = self.client.get(reverse("stakeholders:graph_data", args=[self.stakeholder.pk]))
        data = json.loads(resp.content)
        center_nodes = [n for n in data["nodes"] if n["is_center"]]
        self.assertEqual(len(center_nodes), 1)
        self.assertEqual(center_nodes[0]["name"], self.stakeholder.name)

    def test_graph_data_includes_relationships(self):
        other = Stakeholder.objects.create(name="Other Person")
        Relationship.objects.create(
            from_stakeholder=self.stakeholder,
            to_stakeholder=other,
            relationship_type="colleague",
        )
        resp = self.client.get(reverse("stakeholders:graph_data", args=[self.stakeholder.pk]))
        data = json.loads(resp.content)
        self.assertEqual(len(data["nodes"]), 2)
        self.assertEqual(len(data["edges"]), 1)
        self.assertEqual(data["edges"][0]["label"], "colleague")


class StakeholderHierarchyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.firm = Stakeholder.objects.create(
            name="Acme Firm", entity_type="firm", email="info@acme.com",
        )
        cls.employee1 = Stakeholder.objects.create(
            name="Alice Employee", entity_type="professional",
            parent_organization=cls.firm,
        )
        cls.employee2 = Stakeholder.objects.create(
            name="Bob Employee", entity_type="professional",
            parent_organization=cls.firm,
        )

    def test_firm_employees_reverse_lookup(self):
        employees = list(self.firm.employees.all())
        self.assertEqual(len(employees), 2)
        self.assertIn(self.employee1, employees)
        self.assertIn(self.employee2, employees)

    def test_delete_firm_nullifies_employees(self):
        self.firm.delete()
        self.employee1.refresh_from_db()
        self.employee2.refresh_from_db()
        self.assertIsNone(self.employee1.parent_organization)
        self.assertIsNone(self.employee2.parent_organization)

    def test_firm_detail_shows_team_members(self):
        resp = self.client.get(reverse("stakeholders:detail", args=[self.firm.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Team Members")
        self.assertContains(resp, "Alice Employee")
        self.assertContains(resp, "Bob Employee")

    def test_employee_detail_links_to_firm(self):
        resp = self.client.get(reverse("stakeholders:detail", args=[self.employee1.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Acme Firm")
        self.assertContains(resp, self.firm.get_absolute_url())

    def test_graph_data_includes_employees(self):
        resp = self.client.get(reverse("stakeholders:graph_data", args=[self.firm.pk]))
        data = json.loads(resp.content)
        node_names = [n["name"] for n in data["nodes"]]
        self.assertIn("Alice Employee", node_names)
        self.assertIn("Bob Employee", node_names)
        edge_labels = [e["label"] for e in data["edges"]]
        self.assertIn("employs", edge_labels)

    def test_create_with_parent_organization_prefill(self):
        resp = self.client.get(
            reverse("stakeholders:create"),
            {"parent_organization": self.firm.pk},
        )
        self.assertEqual(resp.status_code, 200)


class StakeholderTabTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.firm = Stakeholder.objects.create(
            name="Test Firm", entity_type="firm", email="firm@test.com",
            trust_rating=5, risk_rating=1,
        )
        cls.employee = Stakeholder.objects.create(
            name="Employee One", entity_type="professional",
            parent_organization=cls.firm, email="emp@test.com",
        )
        cls.attorney = Stakeholder.objects.create(
            name="Test Attorney", entity_type="attorney",
        )
        cls.lender = Stakeholder.objects.create(
            name="Test Lender", entity_type="lender",
        )
        cls.advisor = Stakeholder.objects.create(
            name="Test Advisor", entity_type="advisor",
        )
        cls.contact = Stakeholder.objects.create(
            name="Test Contact", entity_type="contact",
        )

    def test_all_tab_excludes_employees(self):
        resp = self.client.get(reverse("stakeholders:list"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["current_tab"], "all")
        stakeholder_names = [s.name for s in resp.context["stakeholders"]]
        self.assertNotIn("Employee One", stakeholder_names)
        self.assertIn("Test Firm", stakeholder_names)
        self.assertIn("Test Attorney", stakeholder_names)

    def test_firms_tab_returns_firm_cards(self):
        resp = self.client.get(
            reverse("stakeholders:list"), {"tab": "firms"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "stakeholders/partials/_firm_cards.html")
        self.assertContains(resp, "Test Firm")
        self.assertContains(resp, "Employee One")

    def test_attorneys_tab_shows_only_attorneys(self):
        resp = self.client.get(reverse("stakeholders:list"), {"tab": "attorneys"})
        self.assertEqual(resp.status_code, 200)
        stakeholder_names = [s.name for s in resp.context["stakeholders"]]
        self.assertIn("Test Attorney", stakeholder_names)
        self.assertNotIn("Test Lender", stakeholder_names)
        self.assertNotIn("Test Firm", stakeholder_names)

    def test_firms_tab_search_matches_employee_name(self):
        resp = self.client.get(
            reverse("stakeholders:list"), {"tab": "firms", "q": "Employee"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Test Firm")

    def test_tab_counts_correct(self):
        resp = self.client.get(reverse("stakeholders:list"))
        counts = resp.context["tab_counts"]
        # All = non-employees (firm + attorney + lender + advisor + contact = 5)
        self.assertEqual(counts["all"], 5)
        self.assertEqual(counts["firms"], 1)
        self.assertEqual(counts["attorneys"], 1)
        self.assertEqual(counts["lenders"], 1)
        self.assertEqual(counts["advisors"], 1)  # advisor only (professional is employee)
        self.assertEqual(counts["other"], 1)  # contact


class StakeholderAssetInlineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(name="Asset Owner", entity_type="contact")
        cls.prop = RealEstate.objects.create(name="123 Main St", address="123 Main St")
        cls.inv = Investment.objects.create(name="Growth Fund")
        cls.loan = Loan.objects.create(name="Home Loan")

    def test_property_ownership_add_get(self):
        resp = self.client.get(reverse("stakeholders:property_ownership_add", args=[self.stakeholder.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Property")

    def test_property_ownership_add_post(self):
        resp = self.client.post(
            reverse("stakeholders:property_ownership_add", args=[self.stakeholder.pk]),
            {"property": self.prop.pk, "role": "Owner", "ownership_percentage": "50.00"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(PropertyOwnership.objects.filter(stakeholder=self.stakeholder, property=self.prop).exists())

    def test_property_ownership_delete(self):
        ownership = PropertyOwnership.objects.create(
            stakeholder=self.stakeholder, property=self.prop, role="Owner", ownership_percentage=100,
        )
        resp = self.client.post(reverse("stakeholders:property_ownership_delete", args=[ownership.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(PropertyOwnership.objects.filter(pk=ownership.pk).exists())

    def test_investment_participant_add_post(self):
        resp = self.client.post(
            reverse("stakeholders:investment_participant_add", args=[self.stakeholder.pk]),
            {"investment": self.inv.pk, "role": "Investor", "ownership_percentage": "25.00"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(InvestmentParticipant.objects.filter(stakeholder=self.stakeholder, investment=self.inv).exists())

    def test_investment_participant_delete(self):
        participant = InvestmentParticipant.objects.create(
            stakeholder=self.stakeholder, investment=self.inv, role="Investor", ownership_percentage=25,
        )
        resp = self.client.post(reverse("stakeholders:investment_participant_delete", args=[participant.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(InvestmentParticipant.objects.filter(pk=participant.pk).exists())

    def test_loan_party_add_post(self):
        resp = self.client.post(
            reverse("stakeholders:loan_party_add", args=[self.stakeholder.pk]),
            {"loan": self.loan.pk, "role": "Borrower", "ownership_percentage": "100.00"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(LoanParty.objects.filter(stakeholder=self.stakeholder, loan=self.loan).exists())

    def test_loan_party_delete(self):
        party = LoanParty.objects.create(
            stakeholder=self.stakeholder, loan=self.loan, role="Borrower", ownership_percentage=100,
        )
        resp = self.client.post(reverse("stakeholders:loan_party_delete", args=[party.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(LoanParty.objects.filter(pk=party.pk).exists())

    def test_detail_shows_ownership_details(self):
        PropertyOwnership.objects.create(
            stakeholder=self.stakeholder, property=self.prop, role="Co-owner", ownership_percentage=50,
        )
        resp = self.client.get(reverse("stakeholders:detail", args=[self.stakeholder.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "123 Main St")
        self.assertContains(resp, "Co-owner")
        self.assertContains(resp, "50")
