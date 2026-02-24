from tasks.models import Task, SubTask
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

    def test_form_collapsible_options(self):
        """Options section starts collapsed, opens on click to show reminder/recurring."""
        self.page.goto(self.url("/tasks/create/"))

        # The details element should exist
        details = self.page.locator("details")
        details.wait_for(state="attached")

        # Reminder field should be hidden initially (inside closed details)
        reminder_toggle = self.page.locator("#reminder-toggle")
        self.assertTrue(reminder_toggle.is_hidden())

        # Click summary to open
        self.page.click("summary:has-text('Options')")

        # Wait for the details to open and content to be visible
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

    def test_form_recurring_toggle_shows_rule(self):
        """Check recurring checkbox -> recurrence rule dropdown appears."""
        self.page.goto(self.url("/tasks/create/"))

        # Open Options section
        self.page.click("summary:has-text('Options')")

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
