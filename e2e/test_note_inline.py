from django.utils import timezone

from dashboard.models import ChoiceOption
from notes.models import Note, Tag, Folder
from e2e.base import PlaywrightTestCase


class NoteInlineEditTests(PlaywrightTestCase):
    """Test HTMX inline editing on the note detail page."""

    def setUp(self):
        super().setUp()
        # Ensure note_type choices exist (TransactionTestCase may flush seed data)
        for val, label, order in [
            ("call", "Call", 0),
            ("email", "Email", 1),
            ("meeting", "Meeting", 2),
            ("general", "General", 5),
        ]:
            ChoiceOption.objects.get_or_create(
                category="note_type", value=val,
                defaults={"label": label, "sort_order": order},
            )
        self.note = Note.objects.create(
            title="Test Note Title",
            content="Original **markdown** content",
            date=timezone.now(),
            note_type="general",
        )

    def test_inline_title_edit(self):
        """Click pencil -> edit title -> Save -> title and breadcrumb update."""
        self.page.goto(self.url(f"/notes/{self.note.pk}/"))

        # Click the pencil button
        self.page.click("#note-title-block button[title='Edit title']")

        # Input should appear
        title_input = self.page.wait_for_selector("#note-title-block input[name='title']")
        self.assertIsNotNone(title_input)

        # Clear and type new title
        title_input.fill("Updated Note Title")

        # Click Save
        self.page.click("#note-title-block button[type='submit']")

        # Wait for display to swap back
        h1 = self.page.wait_for_selector("#note-title-block h1")
        self.assertIn("Updated Note Title", h1.text_content())

        # Breadcrumb should update
        breadcrumb = self.page.text_content("#note-breadcrumb-title")
        self.assertEqual("Updated Note Title", breadcrumb)

        # Verify DB
        self.note.refresh_from_db()
        self.assertEqual(self.note.title, "Updated Note Title")

    def test_inline_title_cancel(self):
        """Click pencil -> Cancel -> original title back."""
        self.page.goto(self.url(f"/notes/{self.note.pk}/"))

        self.page.click("#note-title-block button[title='Edit title']")
        self.page.wait_for_selector("#note-title-block input[name='title']")

        # Cancel
        self.page.click("#note-title-block button:has-text('Cancel')")

        # Original title should be restored
        h1 = self.page.wait_for_selector("#note-title-block h1")
        self.assertIn("Test Note Title", h1.text_content())

    def test_inline_content_edit(self):
        """Click Edit on content -> editor appears -> edit -> Save -> updates."""
        # Use mobile viewport to prevent EasyMDE from initializing
        # (EasyMDE only loads when window.innerWidth >= 640)
        self.page.set_viewport_size({"width": 400, "height": 800})
        self.page.goto(self.url(f"/notes/{self.note.pk}/"))

        # Click Edit button on content block
        self.page.click("#note-content-block button:has-text('Edit')")

        # Textarea should be visible (no EasyMDE at this viewport)
        textarea = self.page.wait_for_selector(
            "#note-content-block textarea[name='content']", state="visible"
        )

        # Clear and type new content
        textarea.fill("New content with **bold** text")

        # Save
        self.page.click("#note-content-block button[type='submit']")

        # Wait for display to swap back — the prose-markdown div should contain rendered content
        content_div = self.page.wait_for_selector("#note-content-block .prose-markdown")
        content_text = content_div.text_content()
        self.assertIn("New content with", content_text)
        self.assertIn("bold", content_text)

        # Verify DB
        self.note.refresh_from_db()
        self.assertEqual(self.note.content, "New content with **bold** text")

    def test_inline_content_cancel(self):
        """Click Edit -> Cancel -> original content back."""
        self.page.set_viewport_size({"width": 400, "height": 800})
        self.page.goto(self.url(f"/notes/{self.note.pk}/"))

        self.page.click("#note-content-block button:has-text('Edit')")

        # Wait for the textarea to be visible
        self.page.wait_for_selector(
            "#note-content-block textarea[name='content']", state="visible"
        )

        # Cancel
        self.page.click("#note-content-block button:has-text('Cancel')")

        # Original content should be restored
        content_div = self.page.wait_for_selector("#note-content-block .prose-markdown")
        self.assertIn("markdown", content_div.text_content())

    def test_inline_metadata_edit(self):
        """Click Edit on metadata -> change type -> Save -> badge updates."""
        self.page.goto(self.url(f"/notes/{self.note.pk}/"))

        # Click Edit
        self.page.click("#note-metadata-block button:has-text('Edit')")

        # Type dropdown should appear
        type_select = self.page.wait_for_selector("#note-metadata-block select[name='note_type']")
        self.assertIsNotNone(type_select)

        # Change type to "email"
        type_select.select_option("email")

        # Save
        self.page.click("#note-metadata-block button[type='submit']")

        # Wait for display to swap back
        self.page.wait_for_selector("#note-metadata-block button:has-text('Edit')")

        # Verify DB
        self.note.refresh_from_db()
        self.assertEqual(self.note.note_type, "email")

    def test_inline_metadata_cancel(self):
        """Click Edit -> Cancel -> original metadata restored."""
        self.page.goto(self.url(f"/notes/{self.note.pk}/"))

        self.page.click("#note-metadata-block button:has-text('Edit')")
        self.page.wait_for_selector("#note-metadata-block select[name='note_type']")

        # Cancel
        self.page.click("#note-metadata-block button:has-text('Cancel')")

        # Edit button should be back (display mode)
        self.page.wait_for_selector("#note-metadata-block button:has-text('Edit')")

        # DB unchanged
        self.note.refresh_from_db()
        self.assertEqual(self.note.note_type, "general")

    def test_inline_metadata_pinned_toggle(self):
        """Toggle pinned checkbox in metadata editor."""
        self.page.goto(self.url(f"/notes/{self.note.pk}/"))

        # Edit metadata
        self.page.click("#note-metadata-block button:has-text('Edit')")
        pinned_checkbox = self.page.wait_for_selector(
            "#note-metadata-block input[name='is_pinned']"
        )

        # Should start unchecked
        self.assertFalse(pinned_checkbox.is_checked())

        # Check it
        pinned_checkbox.check()

        # Save
        self.page.click("#note-metadata-block button[type='submit']")
        self.page.wait_for_selector("#note-metadata-block button:has-text('Edit')")

        # Verify DB
        self.note.refresh_from_db()
        self.assertTrue(self.note.is_pinned)


class NoteInlineMetadataTagTests(PlaywrightTestCase):
    """Test tag pill toggle in note metadata editor."""

    def setUp(self):
        super().setUp()
        self.tag = Tag.objects.create(name="Important", slug="important", color="red")
        self.note = Note.objects.create(
            title="Note With Tags",
            content="Some content",
            date=timezone.now(),
            note_type="general",
        )

    def test_tag_pills_toggle(self):
        """In metadata editor, click tag pill -> gets active classes -> click again -> loses them."""
        self.page.goto(self.url(f"/notes/{self.note.pk}/"))

        # Edit metadata
        self.page.click("#note-metadata-block button:has-text('Edit')")

        # Wait for tags section
        tag_pill = self.page.wait_for_selector(".meta-tag-pill")
        self.assertIsNotNone(tag_pill)

        # Initially, the tag should have inactive styling (border-gray-600)
        self.assertIn("border-gray-600", tag_pill.get_attribute("class"))

        # Click the tag label (the hidden checkbox toggles it)
        tag_pill.click()

        # After click, should have active color classes
        classes = tag_pill.get_attribute("class")
        self.assertNotIn("border-gray-600", classes)

        # Click again to deactivate
        tag_pill.click()

        # Should be back to inactive
        classes = tag_pill.get_attribute("class")
        self.assertIn("border-gray-600", classes)

    def test_tag_selection_persists_on_save(self):
        """Select a tag, save, verify it's applied."""
        self.page.goto(self.url(f"/notes/{self.note.pk}/"))

        # Edit metadata
        self.page.click("#note-metadata-block button:has-text('Edit')")

        # Click the tag to select it
        tag_pill = self.page.wait_for_selector(".meta-tag-pill")
        tag_pill.click()

        # Save
        self.page.click("#note-metadata-block button[type='submit']")
        self.page.wait_for_selector("#note-metadata-block button:has-text('Edit')")

        # Verify DB — tag should be applied
        self.note.refresh_from_db()
        self.assertIn(self.tag.pk, list(self.note.tags.values_list("pk", flat=True)))


class NoteMarkdownRenderingTests(PlaywrightTestCase):
    """Test that markdown content renders correctly after inline editing."""

    def setUp(self):
        super().setUp()
        self.note = Note.objects.create(
            title="Markdown Test Note",
            content="# Heading\n\n**Bold text** and *italic text*\n\n- List item 1\n- List item 2",
            date=timezone.now(),
            note_type="general",
        )

    def test_markdown_renders_on_detail_page(self):
        """Note detail shows rendered markdown (h1, bold, italic, list)."""
        self.page.goto(self.url(f"/notes/{self.note.pk}/"))

        content = self.page.locator("#note-content-block .prose-markdown")
        content.wait_for(state="visible")

        # Check for rendered HTML elements
        self.assertTrue(content.locator("h1").count() > 0 or content.locator("h2").count() > 0)
        self.assertTrue(content.locator("strong").count() > 0)
        self.assertTrue(content.locator("em").count() > 0)
        self.assertTrue(content.locator("li").count() >= 2)

    def test_inline_edit_markdown_re_renders(self):
        """Edit content inline -> save -> new markdown renders correctly."""
        self.page.set_viewport_size({"width": 400, "height": 800})
        self.page.goto(self.url(f"/notes/{self.note.pk}/"))

        # Edit content
        self.page.click("#note-content-block button:has-text('Edit')")
        textarea = self.page.wait_for_selector(
            "#note-content-block textarea[name='content']", state="visible"
        )
        textarea.fill("## New Heading\n\nA paragraph with `inline code`.")

        # Save
        self.page.click("#note-content-block button[type='submit']")

        # Wait for rendered content
        content = self.page.locator("#note-content-block .prose-markdown")
        content.wait_for(state="visible")

        # Should have rendered markdown
        self.assertIn("New Heading", content.text_content())
        self.assertTrue(content.locator("code").count() > 0)


class NotePinFlowTests(PlaywrightTestCase):
    """Test pin/unpin flow on note detail page."""

    def setUp(self):
        super().setUp()
        self.note = Note.objects.create(
            title="Pinnable Note",
            content="Some content",
            date=timezone.now(),
            note_type="general",
            is_pinned=False,
        )

    def test_pin_button_pins_note(self):
        """Click Pin button -> note becomes pinned -> button says Unpin."""
        self.page.goto(self.url(f"/notes/{self.note.pk}/"))

        # Pin button should say "Pin"
        pin_btn = self.page.locator("button:has-text('Pin')")
        pin_btn.click()

        # Page redirects back to detail. Wait for it.
        self.page.wait_for_selector("#note-title-block")

        # Verify DB
        self.note.refresh_from_db()
        self.assertTrue(self.note.is_pinned)

    def test_unpin_button_unpins_note(self):
        """Pinned note -> click Unpin -> note becomes unpinned."""
        self.note.is_pinned = True
        self.note.save()

        self.page.goto(self.url(f"/notes/{self.note.pk}/"))

        # Should say "Unpin"
        unpin_btn = self.page.locator("button:has-text('Unpin')")
        unpin_btn.click()

        # Page redirects back
        self.page.wait_for_selector("#note-title-block")

        self.note.refresh_from_db()
        self.assertFalse(self.note.is_pinned)

    def test_pinned_badge_shows_in_metadata(self):
        """Pinned note shows 'Pinned' badge in metadata display."""
        self.note.is_pinned = True
        self.note.save()

        self.page.goto(self.url(f"/notes/{self.note.pk}/"))

        # Metadata block should contain "Pinned" text
        metadata = self.page.locator("#note-metadata-block")
        metadata.wait_for(state="visible")
        self.assertIn("Pinned", metadata.text_content())
