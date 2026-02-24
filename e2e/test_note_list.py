from django.utils import timezone

from dashboard.models import ChoiceOption
from notes.models import Note, Tag
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

    def test_form_3col_layout(self):
        """Date, Note type, and Folder render in a 3-col grid on desktop."""
        self.page.goto(self.url("/notes/create/"))

        # The 3-col grid container should exist
        grid = self.page.locator(".sm\\:grid-cols-3")
        grid.wait_for(state="visible")
        self.assertTrue(grid.is_visible())

        # It should contain all 3 fields
        self.assertTrue(grid.locator("#id_date").is_visible())
        self.assertTrue(grid.locator("#id_note_type").is_visible())
        self.assertTrue(grid.locator("#id_folder").is_visible())

    def test_form_tag_pills_toggle(self):
        """Clicking tag pill toggles its visual active state."""
        Tag.objects.create(name="Urgent", slug="urgent", color="red")
        Tag.objects.create(name="Personal", slug="personal", color="blue")
        self.page.goto(self.url("/notes/create/"))

        # Find the first tag pill span
        pills = self.page.locator(".form-tag-pill")
        pills.first.wait_for(state="visible")
        self.assertEqual(2, pills.count())

        first_pill = pills.first

        # Initially should have inactive styling (border-gray-600)
        self.assertIn("border-gray-600", first_pill.get_attribute("class"))

        # Click the pill (click the label which wraps it)
        first_pill.click()

        # After click, should have active styling (data-active-bg class applied)
        active_bg = first_pill.get_attribute("data-active-bg")
        self.page.wait_for_function(
            f"document.querySelector('.form-tag-pill').classList.contains('{active_bg}')"
        )
        self.assertIn(active_bg, first_pill.get_attribute("class"))
        self.assertNotIn("border-gray-600", first_pill.get_attribute("class"))

        # Click again to deselect
        first_pill.click()

        # Should revert to inactive
        self.page.wait_for_function(
            "document.querySelector('.form-tag-pill').classList.contains('border-gray-600')"
        )
        self.assertIn("border-gray-600", first_pill.get_attribute("class"))


class NoteTagFilterPillTests(PlaywrightTestCase):
    """Test tag filter pills on the notes list."""

    def setUp(self):
        super().setUp()
        self.tag1 = Tag.objects.create(name="Urgent", slug="urgent", color="red")
        self.tag2 = Tag.objects.create(name="Personal", slug="personal", color="blue")
        self.tagged_note = Note.objects.create(
            title="Tagged Note", content="Has tag", date=timezone.now(), note_type="general"
        )
        self.tagged_note.tags.add(self.tag1)
        self.untagged_note = Note.objects.create(
            title="Untagged Note", content="No tag", date=timezone.now(), note_type="general"
        )

    def test_tag_pill_click_activates_styling(self):
        """Clicking a tag filter pill toggles its active color classes."""
        self.page.goto(self.url("/notes/"))
        self.page.click("#note-filter-toggle-btn")

        # Find the Urgent tag pill
        pill_span = self.page.locator("input[name='tag'][value='urgent'] + span")
        pill_span.wait_for(state="visible")

        # Initially inactive
        self.assertIn("border-gray-600", pill_span.get_attribute("class"))

        # Click to activate
        pill_span.click()

        # Should get active color (data-active-bg attribute applied as class)
        active_bg = pill_span.get_attribute("data-active-bg")
        self.page.wait_for_function(
            f"document.querySelector(\"input[name='tag'][value='urgent'] + span\").classList.contains('{active_bg}')"
        )
        self.assertIn(active_bg, pill_span.get_attribute("class"))
        self.assertNotIn("border-gray-600", pill_span.get_attribute("class"))

    def test_tag_pill_filters_notes(self):
        """Clicking a tag pill filters notes to only those with the tag."""
        self.page.goto(self.url("/notes/"))

        # Both notes visible initially
        content = self.page.locator("#note-content")
        content.wait_for(state="visible")
        self.assertIn("Tagged Note", content.text_content())
        self.assertIn("Untagged Note", content.text_content())

        # Open filters, click the Urgent tag pill
        self.page.click("#note-filter-toggle-btn")
        pill_span = self.page.locator("input[name='tag'][value='urgent'] + span")
        pill_span.wait_for(state="visible")
        pill_span.click()

        # Wait for HTMX filter — only tagged note should remain
        self.page.wait_for_function(
            "!document.getElementById('note-content').textContent.includes('Untagged Note')"
        )
        content = self.page.locator("#note-content")
        self.assertIn("Tagged Note", content.text_content())
        self.assertNotIn("Untagged Note", content.text_content())


class NoteTypeFilterPillTests(PlaywrightTestCase):
    """Test note type colored filter pills on the notes list."""

    def setUp(self):
        super().setUp()
        # ChoiceOption seed data is wiped by TransactionTestCase flush;
        # recreate the note_type choices needed for filter pills to render.
        for val, label in [("call", "Call"), ("email", "Email"), ("meeting", "Meeting")]:
            ChoiceOption.objects.get_or_create(
                category="note_type", value=val, defaults={"label": label, "is_active": True}
            )
        self.call_note = Note.objects.create(
            title="Call Note", content="Phone call", date=timezone.now(), note_type="call"
        )
        self.email_note = Note.objects.create(
            title="Email Note", content="Email content", date=timezone.now(), note_type="email"
        )
        self.meeting_note = Note.objects.create(
            title="Meeting Note", content="Meeting", date=timezone.now(), note_type="meeting"
        )

    def test_type_pills_visible_in_filter_panel(self):
        """Type filter pills are visible when filter panel is opened."""
        self.page.goto(self.url("/notes/"))

        # Open the filter panel
        self.page.click("#note-filter-toggle-btn")

        # Type pills should be visible
        type_pills = self.page.locator("input[name='type'] + span")
        type_pills.first.wait_for(state="visible")
        self.assertGreaterEqual(type_pills.count(), 3)

    def test_type_pill_click_activates_styling(self):
        """Clicking a type pill toggles its active color classes."""
        self.page.goto(self.url("/notes/"))
        self.page.click("#note-filter-toggle-btn")

        # Find the Call pill (first one typically)
        call_checkbox = self.page.locator("input[name='type'][value='call']")
        call_pill = call_checkbox.locator("+ span")
        call_pill.wait_for(state="visible")

        # Initially inactive
        self.assertIn("border-gray-600", call_pill.get_attribute("class"))

        # Click to activate
        call_pill.click()

        # Should get active color classes from data attributes
        active_bg = call_pill.get_attribute("data-active-bg")
        self.page.wait_for_function(
            f"document.querySelector(\"input[name='type'][value='call'] + span\").classList.contains('{active_bg}')"
        )
        self.assertIn(active_bg, call_pill.get_attribute("class"))

    def test_type_pill_filters_notes(self):
        """Clicking a type pill filters the note list to that type."""
        self.page.goto(self.url("/notes/"))

        # All 3 notes should be visible initially
        self.page.wait_for_selector("#note-content")
        content = self.page.locator("#note-content")
        self.assertIn("Call Note", content.text_content())
        self.assertIn("Email Note", content.text_content())
        self.assertIn("Meeting Note", content.text_content())

        # Open filter panel and click the "call" type pill
        self.page.click("#note-filter-toggle-btn")
        call_pill = self.page.locator("input[name='type'][value='call'] + span")
        call_pill.wait_for(state="visible")
        call_pill.click()

        # Wait for HTMX to swap content (Call Note should remain, others filtered out)
        self.page.wait_for_function(
            "!document.getElementById('note-content').textContent.includes('Email Note')"
        )
        content = self.page.locator("#note-content")
        self.assertIn("Call Note", content.text_content())
        self.assertNotIn("Email Note", content.text_content())
        self.assertNotIn("Meeting Note", content.text_content())
