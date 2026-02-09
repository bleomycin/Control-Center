from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from assets.models import RealEstate
from stakeholders.models import Stakeholder

from .models import Evidence, LegalMatter


class LegalMatterModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.matter = LegalMatter.objects.create(
            title="Test Case",
            case_number="2025-001",
            matter_type="litigation",
            status="active",
        )

    def test_defaults(self):
        m = LegalMatter.objects.create(title="Default")
        self.assertEqual(m.matter_type, "other")
        self.assertEqual(m.status, "active")

    def test_str(self):
        self.assertEqual(str(self.matter), "Test Case")

    def test_get_absolute_url(self):
        self.assertEqual(
            self.matter.get_absolute_url(),
            reverse("legal:detail", kwargs={"pk": self.matter.pk}),
        )

    def test_ordering(self):
        LegalMatter.objects.create(title="Older")
        latest = LegalMatter.objects.create(title="Newest")
        first = LegalMatter.objects.first()
        self.assertEqual(first, latest)

    def test_m2m_attorneys(self):
        attorney = Stakeholder.objects.create(name="Atty Smith", entity_type="attorney")
        self.matter.attorneys.add(attorney)
        self.assertIn(attorney, self.matter.attorneys.all())

    def test_m2m_properties(self):
        prop = RealEstate.objects.create(name="Test Prop", address="123 Main")
        self.matter.related_properties.add(prop)
        self.assertIn(prop, self.matter.related_properties.all())


class EvidenceModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.matter = LegalMatter.objects.create(title="Evidence Case")

    def test_create(self):
        ev = Evidence.objects.create(
            legal_matter=self.matter,
            title="Exhibit A",
            evidence_type="document",
        )
        self.assertEqual(ev.legal_matter, self.matter)

    def test_str(self):
        ev = Evidence.objects.create(legal_matter=self.matter, title="Exhibit B")
        self.assertEqual(str(ev), "Exhibit B")

    def test_cascade_on_matter_delete(self):
        Evidence.objects.create(legal_matter=self.matter, title="Will Delete")
        self.matter.delete()
        self.assertEqual(Evidence.objects.count(), 0)

    def test_file_field_optional(self):
        ev = Evidence.objects.create(legal_matter=self.matter, title="No File")
        self.assertFalse(ev.file)


class LegalViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.matter = LegalMatter.objects.create(
            title="View Test Matter",
            matter_type="litigation",
            status="active",
        )

    def test_list(self):
        resp = self.client.get(reverse("legal:list"))
        self.assertEqual(resp.status_code, 200)

    def test_list_search(self):
        resp = self.client.get(reverse("legal:list"), {"q": "View Test"})
        self.assertContains(resp, "View Test Matter")

    def test_list_status_filter(self):
        resp = self.client.get(reverse("legal:list"), {"status": "active"})
        self.assertContains(resp, "View Test Matter")

    def test_list_type_filter(self):
        resp = self.client.get(reverse("legal:list"), {"type": "litigation"})
        self.assertContains(resp, "View Test Matter")

    def test_list_htmx(self):
        resp = self.client.get(reverse("legal:list"), HTTP_HX_REQUEST="true")
        self.assertTemplateUsed(resp, "legal/partials/_legal_table_rows.html")

    def test_create_with_m2m(self):
        attorney = Stakeholder.objects.create(name="Atty", entity_type="attorney")
        resp = self.client.post(reverse("legal:create"), {
            "title": "New Matter",
            "matter_type": "compliance",
            "status": "pending",
            "attorneys": [attorney.pk],
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(LegalMatter.objects.filter(title="New Matter").exists())

    def test_detail(self):
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("evidence_list", resp.context)
        self.assertIn("evidence_form", resp.context)

    def test_csv(self):
        resp = self.client.get(reverse("legal:export_csv"))
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("Title", resp.content.decode())

    def test_pdf(self):
        resp = self.client.get(reverse("legal:export_pdf", args=[self.matter.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_evidence_add(self):
        uploaded = SimpleUploadedFile("test.pdf", b"fakecontent", content_type="application/pdf")
        resp = self.client.post(
            reverse("legal:evidence_add", args=[self.matter.pk]),
            {"title": "New Evidence", "file": uploaded},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Evidence.objects.filter(title="New Evidence").exists())

    def test_evidence_delete(self):
        ev = Evidence.objects.create(legal_matter=self.matter, title="To Delete")
        resp = self.client.post(reverse("legal:evidence_delete", args=[ev.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Evidence.objects.filter(pk=ev.pk).exists())
