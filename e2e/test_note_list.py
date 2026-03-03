from django.utils import timezone

from notes.models import Note
from e2e.base import PlaywrightTestCase


class NoteExpandableCardTests(PlaywrightTestCase):
    """Test expandable content on note list cards."""

    def setUp(self):
        super().setUp()
        # Create a note with long content (>150 chars to trigger Show more)
        self.note = Note.objects.create(
            title="Note With Long Content",
            content=(
                "This is a very long note content that exceeds the truncation threshold "
                "and should trigger the Show more button to appear on the note card. "
                "It contains enough text to be meaningful and interesting when fully expanded. "
                "The content goes on and on to make sure it crosses the 150 character boundary."
            ),
            date=timezone.now(),
            note_type="general",
        )

    def test_expandable_card_content(self):
        """Card shows truncated text -> Show more -> full content -> Show less -> collapses."""
        self.page.goto(self.url("/notes/"))

        pk = self.note.pk

        # Truncated preview should be visible
        preview = self.page.locator(f"#note-preview-{pk}")
        preview.wait_for(state="visible")
        self.assertTrue(preview.is_visible())

        # Full content should be hidden
        full = self.page.locator(f"#note-full-{pk}")
        self.assertTrue(full.is_hidden())

        # Show more button should exist
        btn = self.page.locator(f"#note-expand-btn-{pk}")
        self.assertEqual("Show more", btn.text_content().strip())

        # Click Show more
        btn.click()

        # Full content should now be visible
        full.wait_for(state="visible")
        self.assertTrue(full.is_visible())

        # Preview should be hidden
        self.assertTrue(preview.is_hidden())

        # Button text should change
        self.assertEqual("Show less", btn.text_content().strip())

        # Click Show less
        btn.click()

        # Preview should be visible again
        preview.wait_for(state="visible")
        self.assertTrue(preview.is_visible())
        self.assertTrue(full.is_hidden())
        self.assertEqual("Show more", btn.text_content().strip())


class NoteFormTests(PlaywrightTestCase):
    """Test note create form layout and interactivity."""

    def test_form_wider_layout(self):
        """Note form uses max-w-4xl container."""
        self.page.goto(self.url("/notes/create/"))

        container = self.page.locator(".max-w-4xl")
        container.wait_for(state="visible")
        self.assertTrue(container.is_visible())

    def test_form_entity_fields_collapsible(self):
        """Related Entities section is collapsed by default, opens on click."""
        self.page.goto(self.url("/notes/create/"))

        # The details element with "Related Entities" should exist
        details = self.page.locator("details")
        details.wait_for(state="attached")

        # Entity fields inside should be hidden (details is closed)
        # The grid inside details contains the entity fields
        entity_grid = self.page.locator("details .grid")
        self.assertTrue(entity_grid.is_hidden())

        # Click summary to open
        self.page.click("summary:has-text('Related Entities')")

        # Wait for entity fields to be visible
        entity_grid.wait_for(state="visible")
        self.assertTrue(entity_grid.is_visible())
