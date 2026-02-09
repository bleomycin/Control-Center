import json

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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
        self.assertTemplateUsed(resp, "stakeholders/partials/_stakeholder_table_rows.html")

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
