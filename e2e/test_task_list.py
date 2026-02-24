from django.utils import timezone

from tasks.models import Task, SubTask
from notes.models import Note
from e2e.base import PlaywrightTestCase


class TaskExpandableDescriptionTests(PlaywrightTestCase):
    """Test expandable description on task list rows."""

    def setUp(self):
        super().setUp()
        # Create a task with a long description (>80 chars to trigger Show more)
        self.task = Task.objects.create(
            title="Task With Long Description",
            description=(
                "This is a very long description that exceeds the truncation threshold "
                "and should trigger the Show more button to appear on the task list row. "
                "It contains enough text to be meaningful when expanded."
            ),
            status="not_started",
            priority="medium",
            direction="personal",
        )

    def test_expandable_description(self):
        """Row shows truncated text -> click Show more -> full text -> Show less -> truncated."""
        self.page.goto(self.url("/tasks/"))

        pk = self.task.pk

        # Truncated preview should be visible
        preview = self.page.locator(f"#task-preview-{pk}")
        preview.wait_for(state="visible")
        self.assertTrue(preview.is_visible())

        # Full text should be hidden
        full = self.page.locator(f"#task-full-{pk}")
        self.assertTrue(full.is_hidden())

        # Show more button should be visible
        btn = self.page.locator(f"#task-expand-btn-{pk}")
        self.assertEqual("Show more", btn.text_content().strip())

        # Click Show more
        btn.click()

        # Full text should now be visible
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


class TaskFormTests(PlaywrightTestCase):
    """Test task create form layout and interactivity."""

    def test_form_wider_layout(self):
        """Task form uses max-w-4xl container."""
        self.page.goto(self.url("/tasks/create/"))

        container = self.page.locator(".max-w-4xl")
        container.wait_for(state="visible")
        self.assertTrue(container.is_visible())

    def test_form_reminder_and_recurring_visible(self):
        """Reminder and recurring options are always visible (not hidden in collapsible)."""
        self.page.goto(self.url("/tasks/create/"))

        # Reminder toggle should be visible directly
        reminder_toggle = self.page.locator("#reminder-toggle")
        reminder_toggle.wait_for(state="visible")
        self.assertTrue(reminder_toggle.is_visible())

        # Recurring checkbox should also be visible
        recurring_checkbox = self.page.locator("#id_is_recurring")
        self.assertTrue(recurring_checkbox.is_visible())

    def test_form_direction_changes_stakeholder_label(self):
        """Changing direction dropdown updates stakeholder field label."""
        self.page.goto(self.url("/tasks/create/"))

        # Default is "personal" -> label should be "Related stakeholders"
        label = self.page.locator("#stakeholder-label")
        label.wait_for(state="visible")
        self.assertIn("Related stakeholders", label.text_content())

        # Change direction to outbound
        self.page.select_option("#id_direction", "outbound")

        # Label should change to "Requested From"
        self.page.wait_for_function(
            "document.getElementById('stakeholder-label').textContent.includes('Requested From')"
        )
        self.assertIn("Requested From", label.text_content())

        # Change to inbound
        self.page.select_option("#id_direction", "inbound")

        self.page.wait_for_function(
            "document.getElementById('stakeholder-label').textContent.includes('Requested By')"
        )
        self.assertIn("Requested By", label.text_content())

    def test_form_meeting_shows_time_field(self):
        """Selecting meeting task type reveals the time field."""
        self.page.goto(self.url("/tasks/create/"))

        # Time wrapper should be hidden initially
        time_wrapper = self.page.locator("#due-time-wrapper")
        self.assertTrue(time_wrapper.is_hidden())

        # Select meeting type
        self.page.select_option("#id_task_type", "meeting")

        # Time wrapper should become visible
        time_wrapper.wait_for(state="visible")
        self.assertTrue(time_wrapper.is_visible())

        # Date label should change to "Meeting date"
        date_label = self.page.locator("#due-date-label")
        self.assertIn("Meeting date", date_label.text_content())

    def test_form_2col_direction_and_type(self):
        """Direction and Task type render side-by-side in a 2-col grid."""
        self.page.goto(self.url("/tasks/create/"))

        # Find 2-col grids
        grids = self.page.locator(".sm\\:grid-cols-2")
        grids.first.wait_for(state="visible")

        # First 2-col grid should contain direction and task_type
        first_grid = grids.first
        self.assertTrue(first_grid.locator("#id_direction").is_visible())
        self.assertTrue(first_grid.locator("#id_task_type").is_visible())

    def test_form_2col_status_and_priority(self):
        """Status and Priority render side-by-side in a 2-col grid."""
        self.page.goto(self.url("/tasks/create/"))

        # Status and priority should be in the same grid container
        # They're in the 3rd sm:grid-cols-2 (after direction+type and date+time)
        grids = self.page.locator(".sm\\:grid-cols-2")
        grids.first.wait_for(state="visible")

        # Find the grid that contains both status and priority
        found = False
        for i in range(grids.count()):
            grid = grids.nth(i)
            has_status = grid.locator("#id_status").count() > 0
            has_priority = grid.locator("#id_priority").count() > 0
            if has_status and has_priority:
                found = True
                break
        self.assertTrue(found, "Status and Priority should be in the same 2-col grid")

    def test_form_recurring_toggle_shows_rule(self):
        """Check recurring checkbox -> recurrence rule dropdown appears."""
        self.page.goto(self.url("/tasks/create/"))

        # Recurrence field should be hidden initially
        recurrence_field = self.page.locator("#recurrence-field")
        self.assertTrue(recurrence_field.is_hidden())

        # Check the recurring checkbox
        self.page.check("#id_is_recurring")

        # Recurrence field should become visible
        recurrence_field.wait_for(state="visible")
        self.assertTrue(recurrence_field.is_visible())

        # Uncheck -> hides again
        self.page.uncheck("#id_is_recurring")
        recurrence_field.wait_for(state="hidden")


class TaskListInlineStatusTests(PlaywrightTestCase):
    """Test inline status and priority cycling on task list rows."""

    def setUp(self):
        super().setUp()
        self.task = Task.objects.create(
            title="Status Cycle Task",
            status="not_started",
            priority="low",
            direction="personal",
        )

    def test_status_cycles_on_click(self):
        """Click status badge -> cycles not_started -> in_progress."""
        self.page.goto(self.url("/tasks/"))

        # Find the status button in the task row (desktop column)
        row = self.page.locator(f"#task-row-{self.task.pk}")
        row.wait_for(state="visible")

        # The status button shows "Not Started" and clicking cycles to "In Progress"
        status_btn = row.locator("button:has-text('Not Started')").first
        status_btn.click()

        # Wait for row to re-render with new status
        self.page.wait_for_selector(
            f"#task-row-{self.task.pk} button:has-text('In Progress')"
        )

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "in_progress")

    def test_priority_cycles_on_click(self):
        """Click priority badge -> cycles low -> medium."""
        self.page.goto(self.url("/tasks/"))

        row = self.page.locator(f"#task-row-{self.task.pk}")
        row.wait_for(state="visible")

        # Priority button shows "Low" and clicking cycles to "Medium"
        priority_btn = row.locator("button:has-text('Low')").first
        priority_btn.click()

        # Wait for row to re-render with new priority
        self.page.wait_for_selector(
            f"#task-row-{self.task.pk} button:has-text('Medium')"
        )

        self.task.refresh_from_db()
        self.assertEqual(self.task.priority, "medium")

    def test_complete_checkbox_on_list(self):
        """Click the checkbox circle on a list row -> task completes -> row fades."""
        self.page.goto(self.url("/tasks/"))

        row = self.page.locator(f"#task-row-{self.task.pk}")
        row.wait_for(state="visible")

        # Click the toggle-complete checkbox button in the row
        # The checkbox is in the second <td> (first visible action column)
        toggle_btn = row.locator("button").first
        toggle_btn.click()

        # Wait for row to get opacity-50 class (complete style) after HTMX row swap
        self.page.wait_for_function(
            f"document.getElementById('task-row-{self.task.pk}').classList.contains('opacity-50')"
        )

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "complete")


class TaskNoteIndicatorTests(PlaywrightTestCase):
    """Test note count indicator on task list rows and detail page."""

    def setUp(self):
        super().setUp()
        self.task_with_notes = Task.objects.create(
            title="Task With Notes",
            status="not_started",
            priority="medium",
            direction="personal",
        )
        self.task_without_notes = Task.objects.create(
            title="Task Without Notes",
            status="not_started",
            priority="low",
            direction="personal",
        )
        # Create 2 notes linked to the first task
        for i in range(2):
            note = Note.objects.create(
                title=f"Test Note {i + 1}",
                content=f"Content for note {i + 1}",
                date=timezone.now(),
                note_type="general",
            )
            note.related_tasks.add(self.task_with_notes)

    def test_note_indicator_shown_on_list_row(self):
        """Task with notes shows note icon + count on list row."""
        self.page.goto(self.url("/tasks/"))

        row = self.page.locator(f"#task-row-{self.task_with_notes.pk}")
        row.wait_for(state="visible")

        # Note indicator should be visible with count "2"
        note_link = row.locator("a[title='2 notes']")
        self.assertTrue(note_link.is_visible())
        self.assertIn("2", note_link.text_content())

    def test_no_note_indicator_when_no_notes(self):
        """Task without notes has no note indicator."""
        self.page.goto(self.url("/tasks/"))

        row = self.page.locator(f"#task-row-{self.task_without_notes.pk}")
        row.wait_for(state="visible")

        # No note indicator link should exist in this row
        note_links = row.locator("a[href*='#notes-section']")
        self.assertEqual(0, note_links.count())

    def test_note_indicator_links_to_detail_notes_section(self):
        """Clicking note indicator navigates to detail page notes section."""
        self.page.goto(self.url("/tasks/"))

        row = self.page.locator(f"#task-row-{self.task_with_notes.pk}")
        row.wait_for(state="visible")

        # Click the note indicator
        note_link = row.locator("a[title='2 notes']")
        note_link.click()

        # Should navigate to detail page
        self.page.wait_for_selector("#notes-section")
        self.assertIn(f"/tasks/{self.task_with_notes.pk}/", self.page.url)

    def test_detail_page_notes_section_shows_count(self):
        """Detail page shows note count in Notes section header."""
        self.page.goto(self.url(f"/tasks/{self.task_with_notes.pk}/"))

        notes_section = self.page.locator("#notes-section")
        notes_section.wait_for(state="visible")

        # Header should show "(2)"
        header = notes_section.locator("h2")
        self.assertIn("(2)", header.text_content())

    def test_detail_page_lists_linked_notes(self):
        """Detail page lists the linked notes with titles."""
        self.page.goto(self.url(f"/tasks/{self.task_with_notes.pk}/"))

        notes_section = self.page.locator("#notes-section")
        notes_section.wait_for(state="visible")

        text = notes_section.text_content()
        self.assertIn("Test Note 1", text)
        self.assertIn("Test Note 2", text)

    def test_detail_page_no_count_when_no_notes(self):
        """Detail page Notes header has no count when no notes exist."""
        self.page.goto(self.url(f"/tasks/{self.task_without_notes.pk}/"))

        notes_section = self.page.locator("#notes-section")
        notes_section.wait_for(state="visible")

        header = notes_section.locator("h2")
        header_text = header.text_content()
        self.assertIn("Notes", header_text)
        self.assertNotIn("(", header_text)
