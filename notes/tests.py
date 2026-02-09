from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from assets.models import RealEstate
from legal.models import LegalMatter
from stakeholders.models import Stakeholder
from tasks.models import Task

from .models import Attachment, Note


class NoteModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.note = Note.objects.create(
            title="Test Note",
            content="Some content",
            date=timezone.now(),
            note_type="general",
        )

    def test_create(self):
        self.assertEqual(self.note.title, "Test Note")

    def test_str(self):
        self.assertEqual(str(self.note), "Test Note")

    def test_get_absolute_url(self):
        self.assertEqual(
            self.note.get_absolute_url(),
            reverse("notes:detail", kwargs={"pk": self.note.pk}),
        )

    def test_ordering(self):
        Note.objects.create(
            title="Old", content="old", date=timezone.now() - timezone.timedelta(days=5)
        )
        Note.objects.create(
            title="New", content="new", date=timezone.now()
        )
        first = Note.objects.first()
        self.assertEqual(first.title, "New")

    def test_m2m_all_related_models(self):
        s = Stakeholder.objects.create(name="Related")
        lm = LegalMatter.objects.create(title="Related Case")
        prop = RealEstate.objects.create(name="Related Prop", address="123")
        task = Task.objects.create(title="Related Task")

        self.note.related_stakeholders.add(s)
        self.note.related_legal_matters.add(lm)
        self.note.related_properties.add(prop)
        self.note.related_tasks.add(task)

        self.assertIn(s, self.note.related_stakeholders.all())
        self.assertIn(lm, self.note.related_legal_matters.all())
        self.assertIn(prop, self.note.related_properties.all())
        self.assertIn(task, self.note.related_tasks.all())


class AttachmentModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.note = Note.objects.create(
            title="Attach Note", content="content", date=timezone.now()
        )

    def test_create_with_file(self):
        f = SimpleUploadedFile("test.txt", b"hello", content_type="text/plain")
        att = Attachment.objects.create(note=self.note, file=f, description="Test file")
        self.assertEqual(att.note, self.note)
        self.assertTrue(att.file)

    def test_str_with_description(self):
        f = SimpleUploadedFile("doc.pdf", b"pdf", content_type="application/pdf")
        att = Attachment.objects.create(note=self.note, file=f, description="My Doc")
        self.assertEqual(str(att), "My Doc")

    def test_str_without_description(self):
        f = SimpleUploadedFile("doc.pdf", b"pdf", content_type="application/pdf")
        att = Attachment.objects.create(note=self.note, file=f)
        self.assertIn("doc", str(att))

    def test_cascade_on_note_delete(self):
        f = SimpleUploadedFile("del.txt", b"data", content_type="text/plain")
        Attachment.objects.create(note=self.note, file=f)
        self.note.delete()
        self.assertEqual(Attachment.objects.count(), 0)


class NoteViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.note = Note.objects.create(
            title="View Test Note",
            content="View content",
            date=timezone.now(),
            note_type="meeting",
        )

    def test_list(self):
        resp = self.client.get(reverse("notes:list"))
        self.assertEqual(resp.status_code, 200)

    def test_list_search(self):
        resp = self.client.get(reverse("notes:list"), {"q": "View Test"})
        self.assertContains(resp, "View Test Note")

    def test_list_type_filter(self):
        resp = self.client.get(reverse("notes:list"), {"type": "meeting"})
        self.assertContains(resp, "View Test Note")

    def test_list_htmx(self):
        resp = self.client.get(reverse("notes:list"), HTTP_HX_REQUEST="true")
        self.assertTemplateUsed(resp, "notes/partials/_note_table_rows.html")

    def test_create(self):
        resp = self.client.post(reverse("notes:create"), {
            "title": "New Note",
            "content": "New content",
            "date": "2025-06-15T10:00",
            "note_type": "general",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Note.objects.filter(title="New Note").exists())

    def test_detail(self):
        resp = self.client.get(reverse("notes:detail", args=[self.note.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("attachment_list", resp.context)
        self.assertIn("attachment_form", resp.context)

    def test_update(self):
        resp = self.client.post(
            reverse("notes:edit", args=[self.note.pk]),
            {
                "title": "Updated Note",
                "content": "Updated",
                "date": "2025-06-15T10:00",
                "note_type": "meeting",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.note.refresh_from_db()
        self.assertEqual(self.note.title, "Updated Note")

    def test_delete(self):
        n = Note.objects.create(title="Del", content="x", date=timezone.now())
        resp = self.client.post(reverse("notes:delete", args=[n.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Note.objects.filter(pk=n.pk).exists())

    def test_csv(self):
        resp = self.client.get(reverse("notes:export_csv"))
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("Title", resp.content.decode())

    def test_pdf(self):
        resp = self.client.get(reverse("notes:export_pdf", args=[self.note.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_attachment_add(self):
        f = SimpleUploadedFile("upload.txt", b"data", content_type="text/plain")
        resp = self.client.post(
            reverse("notes:attachment_add", args=[self.note.pk]),
            {"file": f, "description": "Uploaded"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Attachment.objects.filter(description="Uploaded").exists())

    def test_attachment_delete(self):
        f = SimpleUploadedFile("rm.txt", b"data", content_type="text/plain")
        att = Attachment.objects.create(note=self.note, file=f)
        resp = self.client.post(reverse("notes:attachment_delete", args=[att.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Attachment.objects.filter(pk=att.pk).exists())

    def test_quick_capture_get(self):
        resp = self.client.get(reverse("notes:quick_capture"))
        self.assertEqual(resp.status_code, 200)

    def test_quick_capture_post(self):
        resp = self.client.post(reverse("notes:quick_capture"), {
            "title": "Quick Note",
            "content": "Quick content",
            "date": "2025-06-15T10:00",
            "note_type": "general",
        })
        self.assertEqual(resp.status_code, 204)
        self.assertIn("HX-Trigger", resp)
        self.assertIn("HX-Redirect", resp)
