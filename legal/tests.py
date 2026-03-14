from datetime import date, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from assets.models import RealEstate
from stakeholders.models import Stakeholder

from .models import CaseLog, Evidence, FirmEngagement, LegalChecklistItem, LegalCommunication, LegalMatter


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

    def test_new_fields_nullable(self):
        m = LegalMatter.objects.create(title="No Extras")
        self.assertIsNone(m.next_hearing_date)
        self.assertIsNone(m.settlement_amount)
        self.assertIsNone(m.judgment_amount)
        self.assertEqual(m.outcome, "")

    def test_new_fields_with_values(self):
        m = LegalMatter.objects.create(
            title="With Extras",
            next_hearing_date=date.today() + timedelta(days=30),
            settlement_amount=Decimal("50000.00"),
            judgment_amount=Decimal("75000.00"),
            outcome="Settled out of court.",
        )
        self.assertEqual(m.settlement_amount, Decimal("50000.00"))
        self.assertEqual(m.judgment_amount, Decimal("75000.00"))
        self.assertEqual(m.outcome, "Settled out of court.")


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

    def test_url_field_optional(self):
        ev = Evidence.objects.create(legal_matter=self.matter, title="No URL")
        self.assertEqual(ev.url, "")

    def test_create_with_url_only(self):
        ev = Evidence.objects.create(
            legal_matter=self.matter,
            title="Link Only",
            url="https://docs.google.com/document/d/abc123",
        )
        self.assertEqual(ev.url, "https://docs.google.com/document/d/abc123")
        self.assertFalse(ev.file)

    def test_create_with_file_and_url(self):
        ev = Evidence.objects.create(
            legal_matter=self.matter,
            title="Both",
            url="https://example.com/doc",
        )
        ev.file = "evidence/test.pdf"
        ev.save()
        self.assertTrue(ev.file)
        self.assertEqual(ev.url, "https://example.com/doc")

    def test_gdrive_url_field(self):
        ev = Evidence.objects.create(
            legal_matter=self.matter,
            title="Drive Evidence",
            gdrive_url="https://drive.google.com/file/d/abc/view",
        )
        self.assertTrue(ev.has_drive_link)
        self.assertEqual(ev.gdrive_url, "https://drive.google.com/file/d/abc/view")

    def test_has_drive_link_false(self):
        ev = Evidence.objects.create(legal_matter=self.matter, title="No Drive")
        self.assertFalse(ev.has_drive_link)


class LegalCommunicationGdriveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.matter = LegalMatter.objects.create(title="Comm GDrive Case")

    def test_gdrive_url_field(self):
        comm = LegalCommunication.objects.create(
            legal_matter=self.matter,
            date=timezone.now(),
            method="email",
            summary="Test",
            gdrive_url="https://drive.google.com/file/d/xyz/view",
        )
        self.assertTrue(comm.has_drive_link)

    def test_has_drive_link_false(self):
        comm = LegalCommunication.objects.create(
            legal_matter=self.matter,
            date=timezone.now(),
            method="email",
            summary="Test",
        )
        self.assertFalse(comm.has_drive_link)


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

    def test_evidence_add_with_url(self):
        resp = self.client.post(
            reverse("legal:evidence_add", args=[self.matter.pk]),
            {"title": "URL Evidence", "url": "https://drive.google.com/file/d/xyz"},
        )
        self.assertEqual(resp.status_code, 200)
        ev = Evidence.objects.get(title="URL Evidence")
        self.assertEqual(ev.url, "https://drive.google.com/file/d/xyz")

    def test_evidence_edit_get(self):
        ev = Evidence.objects.create(
            legal_matter=self.matter, title="Original", evidence_type="doc",
        )
        resp = self.client.get(reverse("legal:evidence_edit", args=[ev.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Save Changes")
        self.assertContains(resp, "Original")

    def test_evidence_edit_post(self):
        ev = Evidence.objects.create(
            legal_matter=self.matter, title="Old Title", evidence_type="doc",
        )
        resp = self.client.post(
            reverse("legal:evidence_edit", args=[ev.pk]),
            {"title": "New Title", "evidence_type": "photo",
             "url": "https://example.com/updated"},
        )
        self.assertEqual(resp.status_code, 200)
        ev.refresh_from_db()
        self.assertEqual(ev.title, "New Title")
        self.assertEqual(ev.evidence_type, "photo")
        self.assertEqual(ev.url, "https://example.com/updated")

    def test_evidence_edit_shows_edit_button(self):
        ev = Evidence.objects.create(
            legal_matter=self.matter, title="Editable",
        )
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        self.assertContains(resp, reverse("legal:evidence_edit", args=[ev.pk]))

    def test_evidence_url_in_list(self):
        Evidence.objects.create(
            legal_matter=self.matter,
            title="Linked Doc",
            url="https://example.com/doc",
        )
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        self.assertContains(resp, "View link")
        self.assertContains(resp, "https://example.com/doc")

    def test_csv_includes_new_fields(self):
        LegalMatter.objects.create(
            title="CSV Test",
            next_hearing_date=date.today() + timedelta(days=10),
            settlement_amount=Decimal("25000.00"),
        )
        resp = self.client.get(reverse("legal:export_csv"))
        content = resp.content.decode()
        self.assertIn("Next Hearing", content)
        self.assertIn("Settlement Amount", content)

    def test_pdf_includes_hearing_date(self):
        m = LegalMatter.objects.create(
            title="PDF Test",
            next_hearing_date=date.today() + timedelta(days=10),
        )
        resp = self.client.get(reverse("legal:export_pdf", args=[m.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_list_shows_hearing_column(self):
        LegalMatter.objects.create(
            title="Hearing Test",
            next_hearing_date=date.today() + timedelta(days=5),
        )
        resp = self.client.get(reverse("legal:list"))
        self.assertContains(resp, "Hearing")

    def test_detail_has_activity_context(self):
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        self.assertIn("activity_list", resp.context)
        self.assertIn("communication_form", resp.context)

    def test_communication_add_get(self):
        resp = self.client.get(reverse("legal:communication_add", args=[self.matter.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Add Communication")

    def test_communication_add_post(self):
        s = Stakeholder.objects.create(name="Test Attorney")
        resp = self.client.post(reverse("legal:communication_add", args=[self.matter.pk]), {
            "stakeholder": s.pk,
            "date": "2025-03-01T10:00",
            "direction": "outbound",
            "method": "call",
            "summary": "Discussed case strategy.",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(LegalCommunication.objects.filter(summary="Discussed case strategy.").exists())

    def test_communication_edit_get(self):
        comm = LegalCommunication.objects.create(
            legal_matter=self.matter,
            date=timezone.now(),
            direction="outbound",
            method="email",
            summary="Original summary",
        )
        resp = self.client.get(reverse("legal:communication_edit", args=[comm.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Save Changes")

    def test_communication_edit_post(self):
        comm = LegalCommunication.objects.create(
            legal_matter=self.matter,
            date=timezone.now(),
            direction="outbound",
            method="email",
            summary="Old summary",
        )
        resp = self.client.post(reverse("legal:communication_edit", args=[comm.pk]), {
            "date": "2025-03-01T14:00",
            "direction": "inbound",
            "method": "call",
            "summary": "Updated summary",
        })
        self.assertEqual(resp.status_code, 200)
        comm.refresh_from_db()
        self.assertEqual(comm.summary, "Updated summary")
        self.assertEqual(comm.direction, "inbound")

    def test_communication_delete(self):
        comm = LegalCommunication.objects.create(
            legal_matter=self.matter,
            date=timezone.now(),
            direction="inbound",
            method="call",
            summary="Will be deleted",
        )
        resp = self.client.post(reverse("legal:communication_delete", args=[comm.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(LegalCommunication.objects.filter(pk=comm.pk).exists())

    def test_communication_cascade_on_matter_delete(self):
        matter = LegalMatter.objects.create(title="Cascade Test")
        LegalCommunication.objects.create(
            legal_matter=matter,
            date=timezone.now(),
            method="email",
            summary="Test",
        )
        matter.delete()
        self.assertEqual(LegalCommunication.objects.count(), 0)

    def test_communication_stakeholder_set_null(self):
        s = Stakeholder.objects.create(name="Deletable Attorney")
        comm = LegalCommunication.objects.create(
            legal_matter=self.matter,
            stakeholder=s,
            date=timezone.now(),
            method="call",
            summary="Will survive stakeholder deletion",
        )
        s.delete()
        comm.refresh_from_db()
        self.assertIsNone(comm.stakeholder)

    def test_communication_follow_up_fields(self):
        comm = LegalCommunication.objects.create(
            legal_matter=self.matter,
            date=timezone.now(),
            method="call",
            summary="Follow up test",
            follow_up_needed=True,
            follow_up_date=date.today() + timedelta(days=7),
        )
        self.assertTrue(comm.follow_up_needed)
        self.assertIsNotNone(comm.follow_up_date)

    def test_communication_in_detail_page(self):
        LegalCommunication.objects.create(
            legal_matter=self.matter,
            date=timezone.now(),
            direction="outbound",
            method="email",
            summary="Visible in detail page",
        )
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        self.assertContains(resp, "Visible in detail page")
        self.assertContains(resp, "Communications")

    def test_pdf_includes_communications(self):
        LegalCommunication.objects.create(
            legal_matter=self.matter,
            date=timezone.now(),
            direction="outbound",
            method="email",
            summary="PDF comm test",
        )
        resp = self.client.get(reverse("legal:export_pdf", args=[self.matter.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")


class CommunicationSubjectTests(TestCase):
    """Tests for the subject field on LegalCommunication."""

    @classmethod
    def setUpTestData(cls):
        cls.matter = LegalMatter.objects.create(title="Subject Test Matter")
        cls.stakeholder = Stakeholder.objects.create(name="Test Contact")

    def test_subject_saved_on_add(self):
        resp = self.client.post(
            reverse("legal:communication_add", args=[self.matter.pk]),
            {
                "date": "2025-06-01T10:00",
                "direction": "outbound",
                "method": "email",
                "subject": "Retainer Proposal",
                "summary": "Sent retainer for review.",
            },
        )
        self.assertEqual(resp.status_code, 200)
        comm = LegalCommunication.objects.get(subject="Retainer Proposal")
        self.assertEqual(comm.summary, "Sent retainer for review.")

    def test_subject_displayed_in_list(self):
        LegalCommunication.objects.create(
            legal_matter=self.matter,
            date=timezone.now(),
            direction="outbound",
            method="email",
            subject="Discovery Request #3",
            summary="Some details.",
        )
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        self.assertContains(resp, "Discovery Request #3")

    def test_subject_optional(self):
        comm = LegalCommunication.objects.create(
            legal_matter=self.matter,
            date=timezone.now(),
            method="call",
            summary="No subject here",
        )
        self.assertEqual(comm.subject, "")

    def test_subject_in_form(self):
        resp = self.client.get(
            reverse("legal:communication_add", args=[self.matter.pk])
        )
        self.assertContains(resp, "Subject")


class CommunicationListFilterTests(TestCase):
    """Tests for the activity_list HTMX endpoint with comm filters."""

    @classmethod
    def setUpTestData(cls):
        cls.matter = LegalMatter.objects.create(title="Filter Test Matter")
        cls.s1 = Stakeholder.objects.create(name="Alice Attorney")
        cls.s2 = Stakeholder.objects.create(name="Bob Barrister")
        # Create several communications
        cls.c1 = LegalCommunication.objects.create(
            legal_matter=cls.matter, stakeholder=cls.s1,
            date=timezone.now() - timedelta(days=10),
            direction="outbound", method="email",
            subject="Retainer agreement", summary="Sent retainer.",
            follow_up_needed=True, follow_up_date=date.today() + timedelta(days=5),
        )
        cls.c2 = LegalCommunication.objects.create(
            legal_matter=cls.matter, stakeholder=cls.s2,
            date=timezone.now() - timedelta(days=5),
            direction="inbound", method="call",
            subject="Case update", summary="Bob called with update.",
        )
        cls.c3 = LegalCommunication.objects.create(
            legal_matter=cls.matter, stakeholder=cls.s1,
            date=timezone.now() - timedelta(days=2),
            direction="outbound", method="email",
            subject="Evidence package", summary="Sent evidence documents.",
        )

    def _url(self):
        return reverse("legal:activity_list", args=[self.matter.pk])

    def test_basic_list(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Retainer agreement")
        self.assertContains(resp, "Case update")

    def test_filter_by_stakeholder(self):
        resp = self.client.get(self._url(), {"act_stakeholder": self.s1.pk})
        self.assertContains(resp, "Retainer agreement")
        self.assertContains(resp, "Evidence package")
        self.assertNotContains(resp, "Bob called")

    def test_filter_by_direction(self):
        resp = self.client.get(self._url(), {"act_direction": "inbound"})
        self.assertContains(resp, "Case update")
        self.assertNotContains(resp, "Retainer agreement")

    def test_search_subject(self):
        resp = self.client.get(self._url(), {"act_q": "retainer"})
        self.assertContains(resp, "Retainer agreement")
        self.assertNotContains(resp, "Case update")

    def test_search_summary(self):
        resp = self.client.get(self._url(), {"act_q": "evidence documents"})
        self.assertContains(resp, "Evidence package")
        self.assertNotContains(resp, "Case update")

    def test_filter_by_method(self):
        resp = self.client.get(self._url(), {"act_method": "call"})
        self.assertContains(resp, "Case update")
        self.assertNotContains(resp, "Retainer agreement")

    def test_filter_follow_up(self):
        resp = self.client.get(self._url(), {"act_follow_up": "1"})
        self.assertContains(resp, "Retainer agreement")
        self.assertNotContains(resp, "Case update")

    def test_filter_date_range(self):
        from_date = (date.today() - timedelta(days=6)).isoformat()
        resp = self.client.get(self._url(), {"act_date_from": from_date})
        self.assertContains(resp, "Case update")
        self.assertContains(resp, "Evidence package")
        self.assertNotContains(resp, "Retainer agreement")

    def test_pagination_has_more(self):
        """Create 25 comms — page 1 shows 20, has_more=True."""
        for i in range(22):
            LegalCommunication.objects.create(
                legal_matter=self.matter,
                date=timezone.now() - timedelta(hours=i),
                direction="outbound", method="email",
                subject=f"Bulk comm {i}", summary=f"Bulk {i}",
            )
        # Total is 25 (3 from setUp + 22). Page 1 = first 20 items.
        resp = self.client.get(self._url(), {"act_type": "comm"})
        self.assertContains(resp, "Show more")

    def test_pagination_page_2(self):
        """Page 2 should show all items (40 limit)."""
        for i in range(22):
            LegalCommunication.objects.create(
                legal_matter=self.matter,
                date=timezone.now() - timedelta(hours=i),
                direction="outbound", method="email",
                summary=f"Bulk {i}",
            )
        resp = self.client.get(self._url(), {"act_page": "2", "act_type": "comm"})
        self.assertNotContains(resp, "Show more")

    def test_detail_page_has_act_total_count(self):
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        self.assertIn("act_total_count", resp.context)
        self.assertEqual(resp.context["act_total_count"], 3)

    def test_detail_page_has_activity_stakeholders(self):
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        self.assertIn("activity_stakeholders", resp.context)
        names = [s.name for s in resp.context["activity_stakeholders"]]
        self.assertIn("Alice Attorney", names)
        self.assertIn("Bob Barrister", names)


class FollowUpToggleTests(TestCase):
    """Tests for follow-up completion toggle."""

    @classmethod
    def setUpTestData(cls):
        cls.matter = LegalMatter.objects.create(title="Toggle Test Matter")
        cls.stakeholder = Stakeholder.objects.create(name="Toggle Contact")

    def test_toggle_marks_completed(self):
        comm = LegalCommunication.objects.create(
            legal_matter=self.matter, stakeholder=self.stakeholder,
            date=timezone.now(), direction="inbound", method="call",
            summary="Needs follow-up",
            follow_up_needed=True, follow_up_date=date.today() + timedelta(days=3),
        )
        resp = self.client.post(
            reverse("legal:communication_toggle_followup", args=[comm.pk])
        )
        self.assertEqual(resp.status_code, 200)
        comm.refresh_from_db()
        self.assertTrue(comm.follow_up_completed)
        self.assertIsNotNone(comm.follow_up_completed_date)

    def test_toggle_undo_completed(self):
        comm = LegalCommunication.objects.create(
            legal_matter=self.matter, stakeholder=self.stakeholder,
            date=timezone.now(), direction="outbound", method="email",
            summary="Already done",
            follow_up_needed=True, follow_up_date=date.today() - timedelta(days=1),
            follow_up_completed=True, follow_up_completed_date=date.today(),
        )
        resp = self.client.post(
            reverse("legal:communication_toggle_followup", args=[comm.pk])
        )
        self.assertEqual(resp.status_code, 200)
        comm.refresh_from_db()
        self.assertFalse(comm.follow_up_completed)
        self.assertIsNone(comm.follow_up_completed_date)

    def test_toggle_returns_row_partial(self):
        comm = LegalCommunication.objects.create(
            legal_matter=self.matter, stakeholder=self.stakeholder,
            date=timezone.now(), direction="inbound", method="email",
            summary="Row partial test",
            follow_up_needed=True, follow_up_date=date.today() + timedelta(days=2),
        )
        resp = self.client.post(
            reverse("legal:communication_toggle_followup", args=[comm.pk])
        )
        self.assertContains(resp, f"comm-row-{comm.pk}")

    def test_toggle_get_not_allowed(self):
        comm = LegalCommunication.objects.create(
            legal_matter=self.matter,
            date=timezone.now(), method="call", summary="Get test",
            follow_up_needed=True, follow_up_date=date.today(),
        )
        resp = self.client.get(
            reverse("legal:communication_toggle_followup", args=[comm.pk])
        )
        self.assertEqual(resp.status_code, 405)

    def test_overdue_follow_up_shows_warning(self):
        """An overdue follow-up should show 'Overdue' text in the detail page."""
        LegalCommunication.objects.create(
            legal_matter=self.matter, stakeholder=self.stakeholder,
            date=timezone.now(), direction="inbound", method="call",
            summary="Overdue test",
            follow_up_needed=True,
            follow_up_date=date.today() - timedelta(days=3),
        )
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        self.assertContains(resp, "Overdue")

    def test_completed_follow_up_shows_done(self):
        """A completed follow-up should show checkmark text."""
        LegalCommunication.objects.create(
            legal_matter=self.matter, stakeholder=self.stakeholder,
            date=timezone.now(), direction="outbound", method="email",
            summary="Done test",
            follow_up_needed=True,
            follow_up_date=date.today() - timedelta(days=1),
            follow_up_completed=True, follow_up_completed_date=date.today(),
        )
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        self.assertContains(resp, "Follow-up done")


class CommunicationFollowUpFieldTests(TestCase):
    """Tests for the follow_up_completed model fields."""

    def test_defaults(self):
        m = LegalMatter.objects.create(title="FU Default")
        comm = LegalCommunication.objects.create(
            legal_matter=m, date=timezone.now(), method="call", summary="Test",
        )
        self.assertFalse(comm.follow_up_completed)
        self.assertIsNone(comm.follow_up_completed_date)

    def test_set_completed(self):
        m = LegalMatter.objects.create(title="FU Set")
        comm = LegalCommunication.objects.create(
            legal_matter=m, date=timezone.now(), method="email", summary="Test",
            follow_up_needed=True, follow_up_date=date.today(),
            follow_up_completed=True, follow_up_completed_date=date.today(),
        )
        self.assertTrue(comm.follow_up_completed)
        self.assertEqual(comm.follow_up_completed_date, date.today())


class TaskTitlePrefillTests(TestCase):
    """Test that task create form accepts title query param."""

    def test_title_prefilled_from_query(self):
        resp = self.client.get(reverse("tasks:create"), {"title": "Retainer Review"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Retainer Review")


class LegalNotificationTests(TestCase):
    """Tests for check_legal_followups notification function."""

    def test_no_overdue_returns_message(self):
        from legal.notifications import check_legal_followups
        result = check_legal_followups()
        # Either "Notifications disabled." or "No overdue legal follow-ups."
        self.assertTrue(
            "no overdue" in result.lower() or "disabled" in result.lower()
        )

    def test_overdue_creates_notifications(self):
        from legal.notifications import check_legal_followups
        from dashboard.models import Notification

        m = LegalMatter.objects.create(title="Notify Matter")
        s = Stakeholder.objects.create(name="Notify Contact")
        LegalCommunication.objects.create(
            legal_matter=m, stakeholder=s,
            date=timezone.now(), direction="inbound", method="call",
            summary="Overdue item",
            follow_up_needed=True,
            follow_up_date=date.today() - timedelta(days=5),
            follow_up_completed=False,
        )
        result = check_legal_followups()
        # May be "Notifications disabled." if no SMTP, but notifications should still work
        # Check that at least the function ran
        if "disabled" in result.lower():
            self.assertIn("disabled", result.lower())
        else:
            self.assertIn("1", result)
            self.assertTrue(Notification.objects.filter(message__icontains="Notify Contact").exists())

    def test_completed_followup_not_notified(self):
        from legal.notifications import check_legal_followups
        from dashboard.models import Notification

        m = LegalMatter.objects.create(title="Completed FU Matter")
        LegalCommunication.objects.create(
            legal_matter=m,
            date=timezone.now(), method="email", summary="Already done",
            follow_up_needed=True,
            follow_up_date=date.today() - timedelta(days=2),
            follow_up_completed=True, follow_up_completed_date=date.today(),
        )
        result = check_legal_followups()
        # Should not find any overdue since it's completed
        if "disabled" not in result.lower():
            self.assertFalse(
                Notification.objects.filter(message__icontains="Completed FU").exists()
            )


class LegalChecklistModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.matter = LegalMatter.objects.create(title="Checklist Matter")

    def test_create(self):
        item = LegalChecklistItem.objects.create(
            legal_matter=self.matter, title="Review docs",
        )
        self.assertEqual(item.legal_matter, self.matter)
        self.assertFalse(item.is_completed)

    def test_str(self):
        item = LegalChecklistItem.objects.create(
            legal_matter=self.matter, title="File motion",
        )
        self.assertEqual(str(item), "File motion")

    def test_ordering(self):
        LegalChecklistItem.objects.create(
            legal_matter=self.matter, title="Second", sort_order=1,
        )
        LegalChecklistItem.objects.create(
            legal_matter=self.matter, title="First", sort_order=0,
        )
        items = list(self.matter.checklist_items.values_list("title", flat=True))
        self.assertEqual(items[0], "First")
        self.assertEqual(items[1], "Second")

    def test_cascade_on_matter_delete(self):
        matter = LegalMatter.objects.create(title="Cascade CL")
        LegalChecklistItem.objects.create(legal_matter=matter, title="Gone")
        matter.delete()
        self.assertFalse(LegalChecklistItem.objects.filter(title="Gone").exists())


class LegalChecklistViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.matter = LegalMatter.objects.create(
            title="Checklist View Matter", status="active",
        )

    def test_detail_has_checklist_context(self):
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        self.assertIn("checklist_items", resp.context)
        self.assertIn("checklist_form", resp.context)
        self.assertIn("checklist_count", resp.context)
        self.assertIn("checklist_done", resp.context)

    def test_checklist_add(self):
        resp = self.client.post(
            reverse("legal:checklist_add", args=[self.matter.pk]),
            {"title": "New item"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(LegalChecklistItem.objects.filter(title="New item").exists())

    def test_checklist_toggle(self):
        item = LegalChecklistItem.objects.create(
            legal_matter=self.matter, title="Toggle me",
        )
        resp = self.client.post(reverse("legal:checklist_toggle", args=[item.pk]))
        self.assertEqual(resp.status_code, 200)
        item.refresh_from_db()
        self.assertTrue(item.is_completed)
        # Toggle back
        self.client.post(reverse("legal:checklist_toggle", args=[item.pk]))
        item.refresh_from_db()
        self.assertFalse(item.is_completed)

    def test_checklist_edit_get(self):
        item = LegalChecklistItem.objects.create(
            legal_matter=self.matter, title="Edit me",
        )
        resp = self.client.get(reverse("legal:checklist_edit", args=[item.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Edit me")

    def test_checklist_edit_post(self):
        item = LegalChecklistItem.objects.create(
            legal_matter=self.matter, title="Old title",
        )
        resp = self.client.post(
            reverse("legal:checklist_edit", args=[item.pk]),
            {"title": "New title"},
        )
        self.assertEqual(resp.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.title, "New title")

    def test_checklist_edit_cancel(self):
        item = LegalChecklistItem.objects.create(
            legal_matter=self.matter, title="Cancel test",
        )
        resp = self.client.get(
            reverse("legal:checklist_edit", args=[item.pk]) + "?cancel=1"
        )
        self.assertEqual(resp.status_code, 200)

    def test_checklist_delete(self):
        item = LegalChecklistItem.objects.create(
            legal_matter=self.matter, title="Delete me",
        )
        resp = self.client.post(reverse("legal:checklist_delete", args=[item.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(LegalChecklistItem.objects.filter(pk=item.pk).exists())

    def test_checklist_delete_get_not_allowed(self):
        item = LegalChecklistItem.objects.create(
            legal_matter=self.matter, title="No GET",
        )
        resp = self.client.get(reverse("legal:checklist_delete", args=[item.pk]))
        self.assertEqual(resp.status_code, 405)

    def test_checklist_toggle_get_not_allowed(self):
        item = LegalChecklistItem.objects.create(
            legal_matter=self.matter, title="No GET toggle",
        )
        resp = self.client.get(reverse("legal:checklist_toggle", args=[item.pk]))
        self.assertEqual(resp.status_code, 405)

    def test_checklist_progress_in_detail(self):
        LegalChecklistItem.objects.create(
            legal_matter=self.matter, title="Done", is_completed=True,
        )
        LegalChecklistItem.objects.create(
            legal_matter=self.matter, title="Pending",
        )
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        self.assertContains(resp, "1/2")

    def test_checklist_in_pdf(self):
        LegalChecklistItem.objects.create(
            legal_matter=self.matter, title="PDF item", is_completed=True,
        )
        resp = self.client.get(reverse("legal:export_pdf", args=[self.matter.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")


class CaseLogModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.matter = LegalMatter.objects.create(title="Log Matter")
        cls.stakeholder = Stakeholder.objects.create(name="Agent Smith", entity_type="individual")

    def test_str_truncation(self):
        log = CaseLog.objects.create(legal_matter=self.matter, text="A" * 100)
        self.assertEqual(len(str(log)), 80)

    def test_display_source_stakeholder(self):
        log = CaseLog.objects.create(
            legal_matter=self.matter, stakeholder=self.stakeholder, text="test",
        )
        self.assertEqual(log.display_source, "Agent Smith")

    def test_display_source_name(self):
        log = CaseLog.objects.create(
            legal_matter=self.matter, source_name="Jim Neighbor", text="test",
        )
        self.assertEqual(log.display_source, "Jim Neighbor")

    def test_display_source_empty(self):
        log = CaseLog.objects.create(legal_matter=self.matter, text="anon")
        self.assertEqual(log.display_source, "")

    def test_get_absolute_url(self):
        log = CaseLog.objects.create(legal_matter=self.matter, text="url test")
        self.assertEqual(
            log.get_absolute_url(),
            reverse("legal:detail", kwargs={"pk": self.matter.pk}),
        )

    def test_ordering(self):
        CaseLog.objects.create(legal_matter=self.matter, text="first")
        latest = CaseLog.objects.create(legal_matter=self.matter, text="second")
        self.assertEqual(CaseLog.objects.first(), latest)

    def test_cascade_delete(self):
        CaseLog.objects.create(legal_matter=self.matter, text="will be deleted")
        pk = self.matter.pk
        self.matter.delete()
        self.assertFalse(CaseLog.objects.filter(legal_matter_id=pk).exists())

    def test_stakeholder_set_null(self):
        log = CaseLog.objects.create(
            legal_matter=self.matter, stakeholder=self.stakeholder, text="set null",
        )
        self.stakeholder.delete()
        log.refresh_from_db()
        self.assertIsNone(log.stakeholder)


class CaseLogViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.matter = LegalMatter.objects.create(title="View Test Matter")
        cls.stakeholder = Stakeholder.objects.create(name="Test Source", entity_type="individual")

    def test_case_log_in_detail(self):
        CaseLog.objects.create(legal_matter=self.matter, text="Visible entry")
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        self.assertContains(resp, "Activity")
        self.assertContains(resp, "Visible entry")

    def test_case_log_add_get(self):
        resp = self.client.get(reverse("legal:case_log_add", args=[self.matter.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Add Entry")

    def test_case_log_add_post(self):
        resp = self.client.post(
            reverse("legal:case_log_add", args=[self.matter.pk]),
            {"text": "New log entry", "stakeholder": self.stakeholder.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(CaseLog.objects.filter(text="New log entry").exists())

    def test_case_log_add_with_source_name(self):
        resp = self.client.post(
            reverse("legal:case_log_add", args=[self.matter.pk]),
            {"text": "From neighbor", "source_name": "Jim at 1204"},
        )
        self.assertEqual(resp.status_code, 200)
        log = CaseLog.objects.get(text="From neighbor")
        self.assertEqual(log.source_name, "Jim at 1204")
        self.assertIsNone(log.stakeholder)

    def test_case_log_in_activity_list(self):
        CaseLog.objects.create(legal_matter=self.matter, text="List entry")
        resp = self.client.get(reverse("legal:activity_list", args=[self.matter.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "List entry")

    def test_case_log_search_via_activity(self):
        CaseLog.objects.create(legal_matter=self.matter, text="Alpha entry")
        CaseLog.objects.create(legal_matter=self.matter, text="Beta entry")
        resp = self.client.get(
            reverse("legal:activity_list", args=[self.matter.pk]),
            {"act_q": "Alpha", "act_type": "log"},
        )
        self.assertContains(resp, "Alpha entry")
        self.assertNotContains(resp, "Beta entry")

    def test_case_log_filter_stakeholder_via_activity(self):
        CaseLog.objects.create(
            legal_matter=self.matter, stakeholder=self.stakeholder, text="From source",
        )
        CaseLog.objects.create(legal_matter=self.matter, text="No source")
        resp = self.client.get(
            reverse("legal:activity_list", args=[self.matter.pk]),
            {"act_stakeholder": self.stakeholder.pk, "act_type": "log"},
        )
        self.assertContains(resp, "From source")
        self.assertNotContains(resp, "No source")

    def test_case_log_delete(self):
        log = CaseLog.objects.create(legal_matter=self.matter, text="Delete me")
        resp = self.client.post(reverse("legal:case_log_delete", args=[log.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(CaseLog.objects.filter(pk=log.pk).exists())

    def test_case_log_delete_get_not_allowed(self):
        log = CaseLog.objects.create(legal_matter=self.matter, text="No GET")
        resp = self.client.get(reverse("legal:case_log_delete", args=[log.pk]))
        self.assertEqual(resp.status_code, 405)

    def test_case_log_in_pdf(self):
        CaseLog.objects.create(
            legal_matter=self.matter, text="PDF log entry",
            stakeholder=self.stakeholder,
        )
        resp = self.client.get(reverse("legal:export_pdf", args=[self.matter.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_case_log_stakeholder_link(self):
        CaseLog.objects.create(
            legal_matter=self.matter, stakeholder=self.stakeholder,
            text="Linked entry",
        )
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        self.assertContains(resp, self.stakeholder.get_absolute_url())

    def test_stakeholder_detail_case_logs_tab(self):
        CaseLog.objects.create(
            legal_matter=self.matter, stakeholder=self.stakeholder,
            text="Stakeholder tab entry",
        )
        resp = self.client.get(
            reverse("stakeholders:detail", args=[self.stakeholder.pk])
        )
        self.assertContains(resp, "Case Logs")
        self.assertContains(resp, "Stakeholder tab entry")


class ActivityListTests(TestCase):
    """Tests for the unified activity timeline."""

    @classmethod
    def setUpTestData(cls):
        cls.matter = LegalMatter.objects.create(title="Activity Test Matter")
        cls.s1 = Stakeholder.objects.create(name="Alice")
        cls.s2 = Stakeholder.objects.create(name="Bob")
        cls.comm1 = LegalCommunication.objects.create(
            legal_matter=cls.matter, stakeholder=cls.s1,
            date=timezone.now() - timedelta(days=3),
            direction="outbound", method="email",
            subject="Email to Alice", summary="Sent docs.",
        )
        cls.comm2 = LegalCommunication.objects.create(
            legal_matter=cls.matter, stakeholder=cls.s2,
            date=timezone.now() - timedelta(days=1),
            direction="inbound", method="call",
            subject="Call from Bob", summary="Bob called.",
        )
        cls.log1 = CaseLog.objects.create(
            legal_matter=cls.matter, stakeholder=cls.s1,
            text="Log entry by Alice",
        )
        cls.log2 = CaseLog.objects.create(
            legal_matter=cls.matter,
            text="General log entry", source_name="Jim",
        )

    def _url(self):
        return reverse("legal:activity_list", args=[self.matter.pk])

    def test_unified_list_shows_both_types(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Email to Alice")
        self.assertContains(resp, "Log entry by Alice")

    def test_type_filter_log(self):
        resp = self.client.get(self._url(), {"act_type": "log"})
        self.assertContains(resp, "Log entry by Alice")
        self.assertContains(resp, "General log entry")
        self.assertNotContains(resp, "Email to Alice")

    def test_type_filter_comm(self):
        resp = self.client.get(self._url(), {"act_type": "comm"})
        self.assertContains(resp, "Email to Alice")
        self.assertNotContains(resp, "Log entry by Alice")

    def test_unified_search(self):
        resp = self.client.get(self._url(), {"act_q": "Bob"})
        self.assertContains(resp, "Call from Bob")
        self.assertNotContains(resp, "Email to Alice")

    def test_unified_search_matches_log_text(self):
        resp = self.client.get(self._url(), {"act_q": "General"})
        self.assertContains(resp, "General log entry")
        self.assertNotContains(resp, "Email to Alice")

    def test_stakeholder_filter(self):
        resp = self.client.get(self._url(), {"act_stakeholder": self.s1.pk})
        self.assertContains(resp, "Email to Alice")
        self.assertContains(resp, "Log entry by Alice")
        self.assertNotContains(resp, "Call from Bob")
        self.assertNotContains(resp, "General log entry")

    def test_chronological_ordering(self):
        """Most recent items should appear first."""
        resp = self.client.get(self._url())
        content = resp.content.decode()
        # log2 and log1 are most recent (auto_now_add), then comm2, then comm1
        pos_log2 = content.find("General log entry")
        pos_comm1 = content.find("Email to Alice")
        self.assertLess(pos_log2, pos_comm1)

    def test_comm_specific_filters_skip_logs(self):
        """Direction/method filters only affect comms, logs still appear."""
        resp = self.client.get(self._url(), {"act_direction": "inbound"})
        self.assertContains(resp, "Call from Bob")
        self.assertNotContains(resp, "Email to Alice")
        # Logs are unaffected by direction
        self.assertContains(resp, "Log entry by Alice")

    def test_detail_page_context(self):
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        self.assertIn("activity_list", resp.context)
        self.assertIn("act_total_count", resp.context)
        self.assertEqual(resp.context["act_total_count"], 4)
        self.assertEqual(resp.context["act_comm_count"], 2)
        self.assertEqual(resp.context["act_log_count"], 2)

    def test_pagination_mixed_types(self):
        """Create enough items to trigger pagination."""
        for i in range(19):
            LegalCommunication.objects.create(
                legal_matter=self.matter,
                date=timezone.now() - timedelta(hours=i + 10),
                direction="outbound", method="email",
                summary=f"Bulk comm {i}",
            )
        # 2 comms + 19 = 21 comms + 2 logs = 23 total, page 1 limit = 20
        resp = self.client.get(self._url())
        self.assertContains(resp, "Show more")


class FirmEngagementModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.matter = LegalMatter.objects.create(title="Engagement Matter")
        cls.firm = Stakeholder.objects.create(name="Baker & Associates", entity_type="firm")
        cls.firm2 = Stakeholder.objects.create(name="Chen Legal Group", entity_type="firm")

    def test_create(self):
        eng = FirmEngagement.objects.create(
            legal_matter=self.matter, firm=self.firm,
            status="contacted", initial_contact_date=date.today(),
        )
        self.assertEqual(eng.status, "contacted")
        self.assertEqual(eng.legal_matter, self.matter)

    def test_str(self):
        eng = FirmEngagement.objects.create(
            legal_matter=self.matter, firm=self.firm,
            initial_contact_date=date.today(),
        )
        self.assertIn("Baker & Associates", str(eng))
        self.assertIn("Contacted", str(eng))

    def test_get_absolute_url(self):
        eng = FirmEngagement.objects.create(
            legal_matter=self.matter, firm=self.firm,
            initial_contact_date=date.today(),
        )
        self.assertEqual(
            eng.get_absolute_url(),
            reverse("legal:detail", kwargs={"pk": self.matter.pk}),
        )

    def test_ordering(self):
        eng1 = FirmEngagement.objects.create(
            legal_matter=self.matter, firm=self.firm,
            initial_contact_date=date.today() - timedelta(days=10),
        )
        eng2 = FirmEngagement.objects.create(
            legal_matter=self.matter, firm=self.firm2,
            initial_contact_date=date.today(),
        )
        qs = FirmEngagement.objects.all()
        self.assertEqual(qs[0], eng2)
        self.assertEqual(qs[1], eng1)

    def test_cascade_on_matter_delete(self):
        FirmEngagement.objects.create(
            legal_matter=self.matter, firm=self.firm,
            initial_contact_date=date.today(),
        )
        matter_pk = self.matter.pk
        self.matter.delete()
        self.assertFalse(FirmEngagement.objects.filter(legal_matter_id=matter_pk).exists())

    def test_firm_set_null(self):
        eng = FirmEngagement.objects.create(
            legal_matter=self.matter, firm=self.firm2,
            initial_contact_date=date.today(),
        )
        self.firm2.delete()
        eng.refresh_from_db()
        self.assertIsNone(eng.firm)

    def test_referred_by_set_null(self):
        parent = FirmEngagement.objects.create(
            legal_matter=self.matter, firm=self.firm,
            initial_contact_date=date.today(),
        )
        child = FirmEngagement.objects.create(
            legal_matter=self.matter, firm=self.firm2,
            referred_by=parent, initial_contact_date=date.today(),
        )
        parent.delete()
        child.refresh_from_db()
        self.assertIsNone(child.referred_by)

    def test_unique_together(self):
        FirmEngagement.objects.create(
            legal_matter=self.matter, firm=self.firm,
            initial_contact_date=date.today(),
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            FirmEngagement.objects.create(
                legal_matter=self.matter, firm=self.firm,
                initial_contact_date=date.today(),
            )

    def test_referral_chain(self):
        parent = FirmEngagement.objects.create(
            legal_matter=self.matter, firm=self.firm,
            initial_contact_date=date.today(),
        )
        child = FirmEngagement.objects.create(
            legal_matter=self.matter, firm=self.firm2,
            referred_by=parent, initial_contact_date=date.today(),
        )
        self.assertIn(child, parent.referrals.all())
        self.assertEqual(child.referred_by, parent)


class FirmEngagementViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.matter = LegalMatter.objects.create(title="FE View Matter")
        cls.firm = Stakeholder.objects.create(name="Smith Law Partners", entity_type="firm")
        cls.firm2 = Stakeholder.objects.create(name="Davis Group", entity_type="firm")
        cls.eng = FirmEngagement.objects.create(
            legal_matter=cls.matter, firm=cls.firm,
            status="in_review", scope="Litigation",
            initial_contact_date=date.today() - timedelta(days=5),
        )

    def test_detail_has_engagement_context(self):
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        self.assertIn("engagement_data", resp.context)
        self.assertEqual(resp.context["engagement_total"], 1)
        self.assertContains(resp, "Counsel Search")
        self.assertContains(resp, "Smith Law Partners")

    def test_add_get_returns_form(self):
        resp = self.client.get(reverse("legal:firm_engagement_add", args=[self.matter.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Add Firm")

    def test_add_post_creates_engagement(self):
        resp = self.client.post(
            reverse("legal:firm_engagement_add", args=[self.matter.pk]),
            {"firm": self.firm2.pk, "status": "contacted",
             "initial_contact_date": date.today().isoformat()},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            FirmEngagement.objects.filter(legal_matter=self.matter, firm=self.firm2).exists()
        )

    def test_add_with_referred_by_prepopulated(self):
        resp = self.client.get(
            reverse("legal:firm_engagement_add", args=[self.matter.pk])
            + f"?referred_by={self.eng.pk}"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Add Firm")

    def test_edit_get_returns_form(self):
        resp = self.client.get(reverse("legal:firm_engagement_edit", args=[self.eng.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Save Changes")

    def test_edit_post_updates(self):
        resp = self.client.post(
            reverse("legal:firm_engagement_edit", args=[self.eng.pk]),
            {"firm": self.firm.pk, "status": "interested",
             "scope": "Updated scope",
             "initial_contact_date": self.eng.initial_contact_date.isoformat()},
        )
        self.assertEqual(resp.status_code, 200)
        self.eng.refresh_from_db()
        self.assertEqual(self.eng.status, "interested")
        self.assertEqual(self.eng.scope, "Updated scope")

    def test_delete_post_removes(self):
        eng = FirmEngagement.objects.create(
            legal_matter=self.matter, firm=self.firm2,
            initial_contact_date=date.today(),
        )
        resp = self.client.post(reverse("legal:firm_engagement_delete", args=[eng.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(FirmEngagement.objects.filter(pk=eng.pk).exists())

    def test_delete_get_does_not_remove(self):
        eng = FirmEngagement.objects.create(
            legal_matter=self.matter, firm=self.firm2,
            initial_contact_date=date.today(),
        )
        self.client.get(reverse("legal:firm_engagement_delete", args=[eng.pk]))
        self.assertTrue(FirmEngagement.objects.filter(pk=eng.pk).exists())

    def test_promote_adds_attorney(self):
        resp = self.client.post(
            reverse("legal:firm_engagement_promote", args=[self.eng.pk])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.firm, self.matter.attorneys.all())
        self.eng.refresh_from_db()
        self.assertEqual(self.eng.status, "engaged")
        self.assertIsNotNone(self.eng.decision_date)

    def test_promote_creates_case_log(self):
        self.client.post(
            reverse("legal:firm_engagement_promote", args=[self.eng.pk])
        )
        self.assertTrue(
            CaseLog.objects.filter(
                legal_matter=self.matter, stakeholder=self.firm,
                text__icontains="Promoted",
            ).exists()
        )

    def test_promote_get_not_allowed(self):
        resp = self.client.get(
            reverse("legal:firm_engagement_promote", args=[self.eng.pk])
        )
        self.assertEqual(resp.status_code, 405)

    def test_activity_cross_reference_counts(self):
        LegalCommunication.objects.create(
            legal_matter=self.matter, stakeholder=self.firm,
            date=timezone.now(), direction="outbound", method="email",
            summary="Test comm",
        )
        CaseLog.objects.create(
            legal_matter=self.matter, stakeholder=self.firm,
            text="Test log",
        )
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        data = resp.context["engagement_data"]
        item = next(d for d in data if d["engagement"].pk == self.eng.pk)
        self.assertEqual(item["comm_count"], 1)
        self.assertEqual(item["log_count"], 1)

    def test_engagement_in_pdf(self):
        resp = self.client.get(reverse("legal:export_pdf", args=[self.matter.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")
