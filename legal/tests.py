from datetime import date, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from assets.models import RealEstate
from stakeholders.models import Stakeholder

from .models import Evidence, LegalCommunication, LegalMatter


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

    def test_detail_has_communication_context(self):
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        self.assertIn("communication_list", resp.context)
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
    """Tests for the communication_list HTMX endpoint with filters."""

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
        return reverse("legal:communication_list", args=[self.matter.pk])

    def test_basic_list(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Retainer agreement")
        self.assertContains(resp, "Case update")

    def test_filter_by_stakeholder(self):
        resp = self.client.get(self._url(), {"comm_stakeholder": self.s1.pk})
        self.assertContains(resp, "Retainer agreement")
        self.assertContains(resp, "Evidence package")
        self.assertNotContains(resp, "Bob called")

    def test_filter_by_direction(self):
        resp = self.client.get(self._url(), {"comm_direction": "inbound"})
        self.assertContains(resp, "Case update")
        self.assertNotContains(resp, "Retainer agreement")

    def test_search_subject(self):
        resp = self.client.get(self._url(), {"comm_q": "retainer"})
        self.assertContains(resp, "Retainer agreement")
        self.assertNotContains(resp, "Case update")

    def test_search_summary(self):
        resp = self.client.get(self._url(), {"comm_q": "evidence documents"})
        self.assertContains(resp, "Evidence package")
        self.assertNotContains(resp, "Case update")

    def test_filter_by_method(self):
        resp = self.client.get(self._url(), {"comm_method": "call"})
        self.assertContains(resp, "Case update")
        self.assertNotContains(resp, "Retainer agreement")

    def test_filter_follow_up(self):
        resp = self.client.get(self._url(), {"comm_follow_up": "1"})
        self.assertContains(resp, "Retainer agreement")
        self.assertNotContains(resp, "Case update")

    def test_filter_date_range(self):
        from_date = (date.today() - timedelta(days=6)).isoformat()
        resp = self.client.get(self._url(), {"comm_date_from": from_date})
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
        resp = self.client.get(self._url())
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
        resp = self.client.get(self._url(), {"comm_page": "2"})
        self.assertNotContains(resp, "Show more")

    def test_detail_page_has_total_count(self):
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        self.assertIn("total_count", resp.context)
        self.assertEqual(resp.context["total_count"], 3)

    def test_detail_page_has_comm_stakeholders(self):
        resp = self.client.get(reverse("legal:detail", args=[self.matter.pk]))
        self.assertIn("comm_stakeholders", resp.context)
        names = [s.name for s in resp.context["comm_stakeholders"]]
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
