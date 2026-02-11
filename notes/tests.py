from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from assets.models import RealEstate
from legal.models import LegalMatter
from stakeholders.models import Stakeholder
from tasks.models import Task

from .models import Attachment, Folder, Link, Note, Tag


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
        self.assertTemplateUsed(resp, "notes/partials/_note_cards.html")

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

    def test_search_matches_content(self):
        Note.objects.create(
            title="Boring Title",
            content="The quick brown fox jumps over the lazy dog",
            date=timezone.now(),
            note_type="general",
        )
        resp = self.client.get(reverse("notes:list"), {"q": "quick brown fox"})
        self.assertContains(resp, "Boring Title")

    def test_stakeholder_filter(self):
        s = Stakeholder.objects.create(name="Filter Person", entity_type="individual")
        note_with = Note.objects.create(
            title="With Stakeholder", content="x", date=timezone.now()
        )
        note_with.participants.add(s)
        Note.objects.create(
            title="Without Stakeholder", content="y", date=timezone.now()
        )
        resp = self.client.get(reverse("notes:list"), {"stakeholder": str(s.pk)})
        self.assertContains(resp, "With Stakeholder")
        self.assertNotContains(resp, "Without Stakeholder")

    def test_stakeholder_filter_related(self):
        s = Stakeholder.objects.create(name="Related Person", entity_type="individual")
        note_related = Note.objects.create(
            title="Related Note", content="x", date=timezone.now()
        )
        note_related.related_stakeholders.add(s)
        resp = self.client.get(reverse("notes:list"), {"stakeholder": str(s.pk)})
        self.assertContains(resp, "Related Note")

    def test_card_shows_participant_names(self):
        s = Stakeholder.objects.create(name="Alice Wonderland", entity_type="individual")
        note = Note.objects.create(
            title="Participant Note", content="test", date=timezone.now()
        )
        note.participants.add(s)
        resp = self.client.get(reverse("notes:list"))
        self.assertContains(resp, "Alice Wonderland")

    def test_detail_has_link_context(self):
        resp = self.client.get(reverse("notes:detail", args=[self.note.pk]))
        self.assertIn("link_list", resp.context)
        self.assertIn("link_form", resp.context)

    def test_link_add_get(self):
        resp = self.client.get(reverse("notes:link_add", args=[self.note.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_link_add_post(self):
        resp = self.client.post(
            reverse("notes:link_add", args=[self.note.pk]),
            {"url": "https://docs.google.com/doc/1", "description": "Test Doc"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Link.objects.filter(description="Test Doc").exists())

    def test_link_edit_get(self):
        link = Link.objects.create(
            note=self.note, url="https://example.com", description="Old Name"
        )
        resp = self.client.get(reverse("notes:link_edit", args=[link.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Old Name")

    def test_link_edit_post(self):
        link = Link.objects.create(
            note=self.note, url="https://example.com", description="Old Name"
        )
        resp = self.client.post(
            reverse("notes:link_edit", args=[link.pk]),
            {"url": "https://example.com/new", "description": "New Name"},
        )
        self.assertEqual(resp.status_code, 200)
        link.refresh_from_db()
        self.assertEqual(link.description, "New Name")
        self.assertEqual(link.url, "https://example.com/new")

    def test_link_delete(self):
        link = Link.objects.create(
            note=self.note, url="https://example.com", description="Del Link"
        )
        resp = self.client.post(reverse("notes:link_delete", args=[link.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Link.objects.filter(pk=link.pk).exists())

    def test_pdf_includes_links(self):
        Link.objects.create(
            note=self.note, url="https://example.com/report", description="Report"
        )
        resp = self.client.get(reverse("notes:export_pdf", args=[self.note.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_card_combined_count(self):
        note = Note.objects.create(
            title="Count Note", content="x", date=timezone.now()
        )
        f = SimpleUploadedFile("t.txt", b"d", content_type="text/plain")
        Attachment.objects.create(note=note, file=f, description="file")
        Link.objects.create(note=note, url="https://example.com", description="link")
        resp = self.client.get(reverse("notes:list"))
        self.assertContains(resp, "2")


class LinkModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.note = Note.objects.create(
            title="Link Note", content="content", date=timezone.now()
        )

    def test_create(self):
        link = Link.objects.create(
            note=self.note, url="https://docs.google.com/doc/123", description="GDoc"
        )
        self.assertEqual(link.note, self.note)
        self.assertEqual(link.description, "GDoc")

    def test_str(self):
        link = Link.objects.create(
            note=self.note, url="https://example.com", description="My Link"
        )
        self.assertEqual(str(link), "My Link")

    def test_cascade_on_note_delete(self):
        Link.objects.create(
            note=self.note, url="https://example.com", description="Gone"
        )
        self.note.delete()
        self.assertEqual(Link.objects.count(), 0)


class MarkdownRenderTests(TestCase):
    def test_detail_renders_markdown_bold(self):
        note = Note.objects.create(
            title="MD Note", content="**bold text**", date=timezone.now()
        )
        resp = self.client.get(reverse("notes:detail", args=[note.pk]))
        self.assertContains(resp, "<strong>bold text</strong>")

    def test_detail_renders_markdown_list(self):
        note = Note.objects.create(
            title="List Note", content="- item one\n- item two", date=timezone.now()
        )
        resp = self.client.get(reverse("notes:detail", args=[note.pk]))
        self.assertContains(resp, "<li>")

    def test_detail_renders_plain_text_ok(self):
        note = Note.objects.create(
            title="Plain Note", content="Just plain text here", date=timezone.now()
        )
        resp = self.client.get(reverse("notes:detail", args=[note.pk]))
        self.assertContains(resp, "Just plain text here")

    def test_template_filter_empty_string(self):
        from dashboard.templatetags.markdown_filter import render_markdown
        self.assertEqual(render_markdown(""), "")

    def test_pdf_strips_markdown(self):
        note = Note.objects.create(
            title="PDF MD", content="**bold** and *italic*", date=timezone.now()
        )
        resp = self.client.get(reverse("notes:export_pdf", args=[note.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_form_includes_easymde(self):
        resp = self.client.get(reverse("notes:create"))
        self.assertContains(resp, "easymde")


# ===== New tests for 7 features =====

class TagModelTests(TestCase):
    def test_create_tag(self):
        tag = Tag.objects.create(name="Legal", slug="legal", color="red")
        self.assertEqual(str(tag), "Legal")
        self.assertEqual(tag.slug, "legal")

    def test_auto_slug(self):
        tag = Tag.objects.create(name="Action Item")
        self.assertEqual(tag.slug, "action-item")

    def test_tag_ordering(self):
        Tag.objects.create(name="Zulu", slug="zulu")
        Tag.objects.create(name="Alpha", slug="alpha")
        self.assertEqual(Tag.objects.first().name, "Alpha")


class FolderModelTests(TestCase):
    def test_create_folder(self):
        f = Folder.objects.create(name="Legal", color="red")
        self.assertEqual(str(f), "Legal")

    def test_folder_ordering(self):
        Folder.objects.create(name="B Folder", sort_order=2)
        Folder.objects.create(name="A Folder", sort_order=1)
        self.assertEqual(Folder.objects.first().name, "A Folder")


class PinTests(TestCase):
    def test_toggle_pin(self):
        note = Note.objects.create(
            title="Pin Me", content="x", date=timezone.now(), is_pinned=False
        )
        resp = self.client.post(reverse("notes:toggle_pin", args=[note.pk]))
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp["HX-Trigger"], "noteListChanged")
        note.refresh_from_db()
        self.assertTrue(note.is_pinned)

    def test_toggle_unpin(self):
        note = Note.objects.create(
            title="Unpin Me", content="x", date=timezone.now(), is_pinned=True
        )
        self.client.post(reverse("notes:toggle_pin", args=[note.pk]))
        note.refresh_from_db()
        self.assertFalse(note.is_pinned)

    def test_pinned_notes_sort_first(self):
        Note.objects.create(title="Unpinned", content="x", date=timezone.now(), is_pinned=False)
        Note.objects.create(title="Pinned", content="x", date=timezone.now() - timezone.timedelta(days=5), is_pinned=True)
        resp = self.client.get(reverse("notes:list"))
        notes = list(resp.context["notes"])
        self.assertEqual(notes[0].title, "Pinned")

    def test_detail_shows_pin_button(self):
        note = Note.objects.create(title="Pin Detail", content="x", date=timezone.now())
        resp = self.client.get(reverse("notes:detail", args=[note.pk]))
        self.assertContains(resp, "Pin")

    def test_pin_on_detail_page(self):
        note = Note.objects.create(title="Detail Pin", content="x", date=timezone.now(), is_pinned=False)
        resp = self.client.post(reverse("notes:toggle_pin", args=[note.pk]), {"context": "detail"})
        self.assertEqual(resp.status_code, 302)
        note.refresh_from_db()
        self.assertTrue(note.is_pinned)


class MultiSelectTypeFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Note.objects.create(title="Call Note", content="x", date=timezone.now(), note_type="call")
        Note.objects.create(title="Email Note", content="x", date=timezone.now(), note_type="email")
        Note.objects.create(title="Meeting Note", content="x", date=timezone.now(), note_type="meeting")

    def test_single_type(self):
        resp = self.client.get(reverse("notes:list"), {"type": "call"})
        self.assertContains(resp, "Call Note")
        self.assertNotContains(resp, "Email Note")

    def test_multi_type(self):
        resp = self.client.get(reverse("notes:list"), {"type": ["call", "email"]})
        self.assertContains(resp, "Call Note")
        self.assertContains(resp, "Email Note")
        self.assertNotContains(resp, "Meeting Note")


class TagViewTests(TestCase):
    def test_tag_list(self):
        resp = self.client.get(reverse("notes:tag_list"))
        self.assertEqual(resp.status_code, 200)

    def test_tag_add_get(self):
        resp = self.client.get(reverse("notes:tag_add"))
        self.assertEqual(resp.status_code, 200)

    def test_tag_add_post(self):
        resp = self.client.post(reverse("notes:tag_add"), {"name": "NewTag", "color": "blue"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Tag.objects.filter(name="NewTag").exists())

    def test_tag_edit(self):
        tag = Tag.objects.create(name="OldTag", slug="oldtag")
        resp = self.client.post(
            reverse("notes:tag_edit", args=[tag.pk]),
            {"name": "EditedTag", "color": "green"},
        )
        self.assertEqual(resp.status_code, 200)
        tag.refresh_from_db()
        self.assertEqual(tag.name, "EditedTag")

    def test_tag_delete(self):
        tag = Tag.objects.create(name="DelTag", slug="deltag")
        resp = self.client.post(reverse("notes:tag_delete", args=[tag.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Tag.objects.filter(pk=tag.pk).exists())

    def test_tag_filter_on_list(self):
        tag = Tag.objects.create(name="Legal", slug="legal", color="red")
        note = Note.objects.create(title="Tagged Note", content="x", date=timezone.now())
        note.tags.add(tag)
        Note.objects.create(title="Untagged Note", content="x", date=timezone.now())
        resp = self.client.get(reverse("notes:list"), {"tag": "legal"})
        self.assertContains(resp, "Tagged Note")
        self.assertNotContains(resp, "Untagged Note")

    def test_tag_on_card(self):
        tag = Tag.objects.create(name="Finance", slug="finance", color="green")
        note = Note.objects.create(title="Card Tag Note", content="x", date=timezone.now())
        note.tags.add(tag)
        resp = self.client.get(reverse("notes:list"))
        self.assertContains(resp, "#Finance")

    def test_tag_on_detail(self):
        tag = Tag.objects.create(name="Project", slug="project", color="blue")
        note = Note.objects.create(title="Detail Tag Note", content="x", date=timezone.now())
        note.tags.add(tag)
        resp = self.client.get(reverse("notes:detail", args=[note.pk]))
        self.assertContains(resp, "#Project")


class FolderViewTests(TestCase):
    def test_folder_list(self):
        resp = self.client.get(reverse("notes:folder_list"))
        self.assertEqual(resp.status_code, 200)

    def test_folder_add_post(self):
        resp = self.client.post(reverse("notes:folder_add"), {"name": "Legal", "color": "red"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Folder.objects.filter(name="Legal").exists())

    def test_folder_edit(self):
        f = Folder.objects.create(name="OldFolder")
        resp = self.client.post(
            reverse("notes:folder_edit", args=[f.pk]),
            {"name": "NewFolder", "color": "green"},
        )
        self.assertEqual(resp.status_code, 200)
        f.refresh_from_db()
        self.assertEqual(f.name, "NewFolder")

    def test_folder_delete(self):
        f = Folder.objects.create(name="DelFolder")
        resp = self.client.post(reverse("notes:folder_delete", args=[f.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Folder.objects.filter(pk=f.pk).exists())

    def test_folder_tab_filter(self):
        f = Folder.objects.create(name="Legal", color="red")
        Note.objects.create(title="In Folder", content="x", date=timezone.now(), folder=f)
        Note.objects.create(title="No Folder", content="x", date=timezone.now())
        resp = self.client.get(reverse("notes:list"), {"folder": str(f.pk)})
        self.assertContains(resp, "In Folder")
        self.assertNotContains(resp, "No Folder")

    def test_unfiled_filter(self):
        f = Folder.objects.create(name="Legal", color="red")
        Note.objects.create(title="In Folder", content="x", date=timezone.now(), folder=f)
        Note.objects.create(title="Unfiled Note", content="x", date=timezone.now())
        resp = self.client.get(reverse("notes:list"), {"folder": "unfiled"})
        self.assertContains(resp, "Unfiled Note")
        self.assertNotContains(resp, "In Folder")

    def test_folder_on_card(self):
        f = Folder.objects.create(name="Properties", color="blue")
        Note.objects.create(title="Folder Card", content="x", date=timezone.now(), folder=f)
        resp = self.client.get(reverse("notes:list"))
        self.assertContains(resp, "Properties")

    def test_folder_on_detail(self):
        f = Folder.objects.create(name="Meetings", color="purple")
        note = Note.objects.create(title="Folder Detail", content="x", date=timezone.now(), folder=f)
        resp = self.client.get(reverse("notes:detail", args=[note.pk]))
        self.assertContains(resp, "Meetings")


class CompactListViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.note = Note.objects.create(
            title="Table Note", content="x", date=timezone.now()
        )

    def test_list_view_htmx(self):
        resp = self.client.get(
            reverse("notes:list"), {"view": "list"}, HTTP_HX_REQUEST="true"
        )
        self.assertTemplateUsed(resp, "notes/partials/_note_table_view.html")

    def test_cards_view_htmx(self):
        resp = self.client.get(
            reverse("notes:list"), {"view": "cards"}, HTTP_HX_REQUEST="true"
        )
        self.assertTemplateUsed(resp, "notes/partials/_note_list_content.html")

    def test_timeline_view_htmx(self):
        resp = self.client.get(
            reverse("notes:list"), {"view": "timeline"}, HTTP_HX_REQUEST="true"
        )
        self.assertTemplateUsed(resp, "notes/partials/_note_timeline_view.html")

    def test_list_view_shows_title(self):
        resp = self.client.get(
            reverse("notes:list"), {"view": "list"}, HTTP_HX_REQUEST="true"
        )
        self.assertContains(resp, "Table Note")


class QuickCaptureEnhancedTests(TestCase):
    def test_quick_capture_with_stakeholder(self):
        s = Stakeholder.objects.create(name="Quick Person")
        resp = self.client.post(reverse("notes:quick_capture"), {
            "title": "Quick With Stakeholder",
            "content": "x",
            "date": "2025-06-15T10:00",
            "note_type": "general",
            "stakeholder": str(s.pk),
        })
        self.assertEqual(resp.status_code, 204)
        note = Note.objects.get(title="Quick With Stakeholder")
        self.assertIn(s, note.participants.all())

    def test_quick_capture_with_task(self):
        t = Task.objects.create(title="Quick Task")
        resp = self.client.post(reverse("notes:quick_capture"), {
            "title": "Quick With Task",
            "content": "x",
            "date": "2025-06-15T10:00",
            "note_type": "general",
            "task": str(t.pk),
        })
        self.assertEqual(resp.status_code, 204)
        note = Note.objects.get(title="Quick With Task")
        self.assertIn(t, note.related_tasks.all())

    def test_quick_capture_with_folder(self):
        f = Folder.objects.create(name="QC Folder")
        resp = self.client.post(reverse("notes:quick_capture"), {
            "title": "Quick With Folder",
            "content": "x",
            "date": "2025-06-15T10:00",
            "note_type": "general",
            "folder": str(f.pk),
        })
        self.assertEqual(resp.status_code, 204)
        note = Note.objects.get(title="Quick With Folder")
        self.assertEqual(note.folder, f)

    def test_quick_capture_with_tags(self):
        tag = Tag.objects.create(name="QC Tag", slug="qc-tag")
        resp = self.client.post(reverse("notes:quick_capture"), {
            "title": "Quick With Tags",
            "content": "x",
            "date": "2025-06-15T10:00",
            "note_type": "general",
            "tags": [str(tag.pk)],
        })
        self.assertEqual(resp.status_code, 204)
        note = Note.objects.get(title="Quick With Tags")
        self.assertIn(tag, note.tags.all())


class TimelineViewTests(TestCase):
    def test_timeline_groups_context(self):
        Note.objects.create(title="Today Note", content="x", date=timezone.now())
        resp = self.client.get(
            reverse("notes:list"), {"view": "timeline"}, HTTP_HX_REQUEST="true"
        )
        self.assertIn("timeline_groups", resp.context)
        groups = resp.context["timeline_groups"]
        self.assertTrue(len(groups) > 0)
        self.assertEqual(groups[0]["label"], "Today")

    def test_timeline_pagination_50(self):
        resp = self.client.get(
            reverse("notes:list"), {"view": "timeline"}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(resp.status_code, 200)


class CSVExportEnhancedTests(TestCase):
    def test_csv_includes_pinned_and_tags(self):
        tag = Tag.objects.create(name="Export Tag", slug="export-tag")
        f = Folder.objects.create(name="Export Folder")
        note = Note.objects.create(
            title="Export Note", content="x", date=timezone.now(),
            is_pinned=True, folder=f,
        )
        note.tags.add(tag)
        resp = self.client.get(reverse("notes:export_csv"))
        content = resp.content.decode()
        self.assertIn("Pinned", content)
        self.assertIn("Folder", content)
        self.assertIn("Tags", content)

    def test_bulk_csv_includes_new_fields(self):
        note = Note.objects.create(
            title="Bulk Note", content="x", date=timezone.now(), is_pinned=True,
        )
        resp = self.client.get(reverse("notes:bulk_export_csv"), {"selected": [str(note.pk)]})
        content = resp.content.decode()
        self.assertIn("Pinned", content)


class PDFExportEnhancedTests(TestCase):
    def test_pdf_with_tags_and_folder(self):
        tag = Tag.objects.create(name="PDF Tag", slug="pdf-tag")
        f = Folder.objects.create(name="PDF Folder")
        note = Note.objects.create(
            title="PDF Note", content="x", date=timezone.now(),
            is_pinned=True, folder=f,
        )
        note.tags.add(tag)
        resp = self.client.get(reverse("notes:export_pdf", args=[note.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")


class SettingsHubTests(TestCase):
    def test_settings_hub_has_tag_link(self):
        resp = self.client.get(reverse("dashboard:settings_hub"))
        self.assertContains(resp, "Manage Tags")

    def test_settings_hub_has_folder_link(self):
        resp = self.client.get(reverse("dashboard:settings_hub"))
        self.assertContains(resp, "Manage Folders")
