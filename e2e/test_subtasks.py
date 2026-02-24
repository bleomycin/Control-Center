from tasks.models import Task, SubTask
from e2e.base import PlaywrightTestCase


class SubtaskDetailPageTests(PlaywrightTestCase):
    """Test subtask CRUD on the task detail page checklist section."""

    def setUp(self):
        super().setUp()
        self.task = Task.objects.create(
            title="Task With Subtasks",
            description="Test task",
            status="not_started",
            priority="medium",
            direction="personal",
        )
        self.st1 = SubTask.objects.create(
            task=self.task, title="First subtask", sort_order=0, is_completed=False,
        )
        self.st2 = SubTask.objects.create(
            task=self.task, title="Second subtask", sort_order=1, is_completed=True,
        )

    def test_subtask_list_shows_counter_and_progress(self):
        """Detail page shows N/M counter and progress bar."""
        self.page.goto(self.url(f"/tasks/{self.task.pk}/"))

        # Counter should show 1/2 (one completed out of two)
        subtask_section = self.page.locator("#subtask-list")
        subtask_section.wait_for(state="visible")
        text = subtask_section.text_content()
        self.assertIn("1/2", text)

        # Progress bar should exist
        progress_bar = self.page.locator("#subtask-list .bg-green-500")
        self.assertTrue(progress_bar.is_visible())

    def test_subtask_add(self):
        """Add a subtask via the inline form."""
        self.page.goto(self.url(f"/tasks/{self.task.pk}/"))

        # Fill the add form
        add_input = self.page.locator("#subtask-list input[name='title']")
        add_input.wait_for(state="visible")
        add_input.fill("Third subtask")

        # Click Add
        self.page.click("#subtask-list button:has-text('Add')")

        # Wait for HTMX swap — counter should update to 1/3
        self.page.wait_for_function(
            "document.querySelector('#subtask-list').textContent.includes('1/3')"
        )

        # New subtask should appear in the list
        self.assertIn(
            "Third subtask",
            self.page.locator("#subtask-list").text_content(),
        )

        # Verify DB
        self.assertEqual(self.task.subtasks.count(), 3)

    def test_subtask_toggle_complete(self):
        """Toggle a subtask from incomplete to complete."""
        self.page.goto(self.url(f"/tasks/{self.task.pk}/"))

        # Click the toggle button for the first (incomplete) subtask
        toggle_btn = self.page.locator(f"#subtask-row-{self.st1.pk} button").first
        toggle_btn.click()

        # Counter should update to 2/2
        self.page.wait_for_function(
            "document.querySelector('#subtask-list').textContent.includes('2/2')"
        )

        # Verify DB
        self.st1.refresh_from_db()
        self.assertTrue(self.st1.is_completed)

    def test_subtask_toggle_uncomplete(self):
        """Toggle a completed subtask back to incomplete."""
        self.page.goto(self.url(f"/tasks/{self.task.pk}/"))

        # Click the toggle button for the second (completed) subtask
        toggle_btn = self.page.locator(f"#subtask-row-{self.st2.pk} button").first
        toggle_btn.click()

        # Counter should update to 0/2
        self.page.wait_for_function(
            "document.querySelector('#subtask-list').textContent.includes('0/2')"
        )

        # Verify DB
        self.st2.refresh_from_db()
        self.assertFalse(self.st2.is_completed)

    def test_subtask_edit_save(self):
        """Click edit pencil -> input appears -> change title -> Save."""
        self.page.goto(self.url(f"/tasks/{self.task.pk}/"))

        # Click the edit (pencil) button on the first subtask
        edit_btn = self.page.locator(
            f"#subtask-row-{self.st1.pk} button[title='Edit']"
        )
        edit_btn.click()

        # Edit form should appear with input pre-filled
        edit_input = self.page.wait_for_selector(
            "input[name='title'][value='First subtask']"
        )
        self.assertIsNotNone(edit_input)

        # Change the title
        edit_input.fill("Updated first subtask")

        # Click Save
        self.page.click("#subtask-list button:has-text('Save')")

        # Wait for the list to re-render with new title
        self.page.wait_for_function(
            "document.querySelector('#subtask-list').textContent.includes('Updated first subtask')"
        )

        # Verify DB
        self.st1.refresh_from_db()
        self.assertEqual(self.st1.title, "Updated first subtask")

    def test_subtask_edit_cancel(self):
        """Click edit -> Cancel -> original title restored, no DB change."""
        self.page.goto(self.url(f"/tasks/{self.task.pk}/"))

        # Click edit
        edit_btn = self.page.locator(
            f"#subtask-row-{self.st1.pk} button[title='Edit']"
        )
        edit_btn.click()

        # Wait for edit form
        self.page.wait_for_selector("input[name='title'][value='First subtask']")

        # Click Cancel
        self.page.click("#subtask-list button:has-text('Cancel')")

        # Original row should be back
        self.page.wait_for_selector(f"#subtask-row-{self.st1.pk}")
        row_text = self.page.locator(f"#subtask-row-{self.st1.pk}").text_content()
        self.assertIn("First subtask", row_text)

        # DB unchanged
        self.st1.refresh_from_db()
        self.assertEqual(self.st1.title, "First subtask")

    def test_subtask_delete(self):
        """Delete a subtask and verify counter updates."""
        self.page.goto(self.url(f"/tasks/{self.task.pk}/"))

        # Click the delete button on the first subtask
        delete_btn = self.page.locator(
            f"#subtask-row-{self.st1.pk} button[title='Delete']"
        )
        delete_btn.click()

        # Counter should update to 1/1 (only the completed one remains)
        self.page.wait_for_function(
            "document.querySelector('#subtask-list').textContent.includes('1/1')"
        )

        # First subtask should be gone from the list
        self.assertNotIn(
            "First subtask",
            self.page.locator("#subtask-list").text_content(),
        )

        # Verify DB
        self.assertEqual(self.task.subtasks.count(), 1)

    def test_completed_subtask_has_line_through(self):
        """Completed subtasks show line-through styling."""
        self.page.goto(self.url(f"/tasks/{self.task.pk}/"))

        # The completed subtask row should have line-through text
        completed_span = self.page.locator(
            f"#subtask-row-{self.st2.pk} span.line-through"
        )
        completed_span.wait_for(state="visible")
        self.assertIn("Second subtask", completed_span.text_content())

        # The incomplete subtask should NOT have line-through
        incomplete_span = self.page.locator(f"#subtask-row-{self.st1.pk} span.flex-1")
        classes = incomplete_span.get_attribute("class")
        self.assertNotIn("line-through", classes)


class SubtaskInlineExpandTests(PlaywrightTestCase):
    """Test the inline subtask expand panel on the task list page."""

    def setUp(self):
        super().setUp()
        self.task = Task.objects.create(
            title="Task For Expand Test",
            status="not_started",
            priority="medium",
            direction="personal",
        )
        self.st1 = SubTask.objects.create(
            task=self.task, title="Sub A", sort_order=0, is_completed=False,
        )
        self.st2 = SubTask.objects.create(
            task=self.task, title="Sub B", sort_order=1, is_completed=True,
        )

    def test_subtask_counter_visible_on_list(self):
        """Task with subtasks shows N/M counter on the list page."""
        self.page.goto(self.url("/tasks/"))

        counter = self.page.locator(f"#subtask-counter-{self.task.pk}")
        counter.wait_for(state="visible")
        self.assertEqual("1/2", counter.text_content().strip())

    def test_click_counter_expands_panel(self):
        """Click the subtask counter -> inline panel loads and shows."""
        self.page.goto(self.url("/tasks/"))

        # Panel should be hidden initially
        panel = self.page.locator(f"#subtask-expand-{self.task.pk}")
        self.assertTrue(panel.is_hidden())

        # Click the counter
        self.page.click(f"#subtask-counter-{self.task.pk}")

        # Panel should become visible with subtask items
        panel.wait_for(state="visible")
        panel_text = panel.text_content()
        self.assertIn("Sub A", panel_text)
        self.assertIn("Sub B", panel_text)

    def test_click_counter_again_collapses(self):
        """Click counter twice -> panel expands then collapses."""
        self.page.goto(self.url("/tasks/"))

        panel = self.page.locator(f"#subtask-expand-{self.task.pk}")

        # First click: expand
        self.page.click(f"#subtask-counter-{self.task.pk}")
        panel.wait_for(state="visible")

        # Second click: collapse
        self.page.click(f"#subtask-counter-{self.task.pk}")
        panel.wait_for(state="hidden")

    def test_toggle_subtask_in_panel_updates_counter(self):
        """Toggle a subtask in the expanded panel -> OOB counter updates."""
        self.page.goto(self.url("/tasks/"))

        # Expand the panel
        self.page.click(f"#subtask-counter-{self.task.pk}")
        panel = self.page.locator(f"#subtask-expand-{self.task.pk}")
        panel.wait_for(state="visible")

        # Click the toggle for the incomplete subtask (first checkbox button in panel)
        toggle_buttons = panel.locator("button")
        toggle_buttons.first.click()

        # Counter should update via OOB swap to 2/2
        self.page.wait_for_function(
            f"document.getElementById('subtask-counter-{self.task.pk}').textContent.trim() === '2/2'"
        )

        # Verify DB
        self.st1.refresh_from_db()
        self.assertTrue(self.st1.is_completed)

    def test_task_without_subtasks_has_no_counter(self):
        """A task with no subtasks doesn't show a counter on the list."""
        task_no_subs = Task.objects.create(
            title="No Subtasks Here",
            status="not_started",
            priority="medium",
            direction="personal",
        )
        self.page.goto(self.url("/tasks/"))

        # Counter element should not exist for this task
        counter = self.page.locator(f"#subtask-counter-{task_no_subs.pk}")
        self.assertEqual(0, counter.count())
