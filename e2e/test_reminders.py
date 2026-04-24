from datetime import timedelta

from django.utils import timezone

from dashboard.models import CalendarFeedSettings
from tasks.models import Task
from e2e.base import PlaywrightTestCase


class DashboardUpcomingRemindersTests(PlaywrightTestCase):
    """Test the Upcoming Reminders panel on the dashboard."""

    def setUp(self):
        super().setUp()
        now = timezone.now()
        # Task with reminder in 2 days — should appear
        self.task_soon = Task.objects.create(
            title="Call Lawyer Soon",
            reminder_date=now + timedelta(days=2),
            status="not_started",
            priority="high",
            direction="outbound",
        )
        # Task with reminder in 10 days — outside 7-day window
        self.task_later = Task.objects.create(
            title="Review Contract Later",
            reminder_date=now + timedelta(days=10),
            status="not_started",
            priority="medium",
            direction="personal",
        )
        # Completed task with reminder — should NOT appear
        self.task_complete = Task.objects.create(
            title="Done Task",
            reminder_date=now + timedelta(days=1),
            status="complete",
            priority="low",
            direction="personal",
        )
        # Task without reminder — should NOT appear
        self.task_no_reminder = Task.objects.create(
            title="No Reminder Task",
            status="not_started",
            priority="medium",
            direction="personal",
        )

    def test_panel_shows_upcoming_reminder_task(self):
        """Dashboard Upcoming Reminders panel shows tasks with reminder_date within 7 days."""
        self.page.goto(self.url("/?v=legacy"))
        self.page.wait_for_load_state("networkidle")

        # Default viewport (1280x720) is >= lg, so desktop panel is visible
        panel = self.page.locator("#reminders-desktop")
        panel.wait_for(state="visible")
        self.assertIn("Call Lawyer Soon", panel.text_content())

    def test_panel_excludes_far_future_reminders(self):
        """Tasks with reminder_date beyond 7 days don't appear in the panel."""
        self.page.goto(self.url("/?v=legacy"))
        self.page.wait_for_load_state("networkidle")

        panel = self.page.locator("#reminders-desktop")
        panel.wait_for(state="visible")
        self.assertNotIn("Review Contract Later", panel.text_content())

    def test_panel_excludes_complete_tasks(self):
        """Completed tasks with reminders don't show in the panel."""
        self.page.goto(self.url("/?v=legacy"))
        self.page.wait_for_load_state("networkidle")

        panel = self.page.locator("#reminders-desktop")
        panel.wait_for(state="visible")
        self.assertNotIn("Done Task", panel.text_content())

    def test_panel_shows_count_badge(self):
        """The panel header shows a count badge for the number of upcoming reminders."""
        self.page.goto(self.url("/?v=legacy"))
        self.page.wait_for_load_state("networkidle")

        badge = self.page.locator("#reminders-desktop .bg-purple-900\\/50.text-purple-300")
        badge.wait_for(state="visible")
        self.assertIn("1", badge.text_content())

    def test_panel_empty_state(self):
        """When no reminders, the panel shows an empty message."""
        Task.objects.all().delete()
        self.page.goto(self.url("/?v=legacy"))
        self.page.wait_for_load_state("networkidle")

        empty_msg = self.page.locator("#reminders-desktop >> text=No upcoming reminders")
        empty_msg.wait_for(state="visible")
        self.assertTrue(empty_msg.is_visible())


class TaskListReminderBadgeTests(PlaywrightTestCase):
    """Test reminder bell badge on task list rows."""

    def setUp(self):
        super().setUp()
        self.task_with_reminder = Task.objects.create(
            title="Task With Reminder",
            reminder_date=timezone.now() + timedelta(days=1),
            status="not_started",
            priority="medium",
            direction="personal",
        )
        self.task_without_reminder = Task.objects.create(
            title="Task No Reminder",
            status="not_started",
            priority="low",
            direction="personal",
        )

    def test_bell_icon_shown_for_task_with_reminder(self):
        """Task row shows bell icon when reminder_date is set."""
        self.page.goto(self.url("/tasks/"))

        row = self.page.locator(f"#task-row-{self.task_with_reminder.pk}")
        row.wait_for(state="visible")

        # Bell emoji (🔔) should appear in the row
        bell = row.locator("span[title*='Reminder']")
        self.assertTrue(bell.count() > 0)

    def test_no_bell_icon_for_task_without_reminder(self):
        """Task row does not show bell icon when no reminder_date."""
        self.page.goto(self.url("/tasks/"))

        row = self.page.locator(f"#task-row-{self.task_without_reminder.pk}")
        row.wait_for(state="visible")

        bell = row.locator("span[title*='Reminder']")
        self.assertEqual(0, bell.count())


class TaskKanbanReminderBadgeTests(PlaywrightTestCase):
    """Test reminder bell badge on kanban cards."""

    def setUp(self):
        super().setUp()
        self.task_with_reminder = Task.objects.create(
            title="Kanban Reminder Task",
            reminder_date=timezone.now() + timedelta(days=1),
            status="not_started",
            priority="medium",
            direction="personal",
        )
        self.task_without_reminder = Task.objects.create(
            title="Kanban No Reminder",
            status="not_started",
            priority="low",
            direction="personal",
        )

    def test_bell_icon_on_kanban_card(self):
        """Kanban card shows bell icon when reminder_date is set."""
        self.page.goto(self.url("/tasks/?view=board"))
        self.page.wait_for_load_state("networkidle")

        card = self.page.locator(f'[data-task-id="{self.task_with_reminder.pk}"]')
        card.wait_for(state="visible")

        bell = card.locator("span[title*='Reminder']")
        self.assertTrue(bell.count() > 0)

    def test_no_bell_on_kanban_card_without_reminder(self):
        """Kanban card without reminder_date has no bell icon."""
        self.page.goto(self.url("/tasks/?view=board"))
        self.page.wait_for_load_state("networkidle")

        card = self.page.locator(f'[data-task-id="{self.task_without_reminder.pk}"]')
        card.wait_for(state="visible")

        bell = card.locator("span[title*='Reminder']")
        self.assertEqual(0, bell.count())


class TaskDetailReminderBadgeTests(PlaywrightTestCase):
    """Test reminder badge on task detail metadata row."""

    def setUp(self):
        super().setUp()
        self.task = Task.objects.create(
            title="Detail Reminder Task",
            reminder_date=timezone.now() + timedelta(days=3),
            status="not_started",
            priority="high",
            direction="outbound",
        )

    def test_reminder_badge_on_detail_page(self):
        """Task detail page shows reminder badge with date in metadata row."""
        self.page.goto(self.url(f"/tasks/{self.task.pk}/"))

        metadata = self.page.locator("#task-metadata-block")
        metadata.wait_for(state="visible")

        # Should show a purple reminder badge
        reminder_badge = metadata.locator("span.bg-purple-900\\/50")
        self.assertTrue(reminder_badge.count() > 0)

        # Badge text should contain the bell emoji
        badge_text = reminder_badge.text_content()
        self.assertIn("\U0001f514", badge_text)

    def test_no_reminder_badge_when_not_set(self):
        """Task without reminder_date has no reminder badge on detail page."""
        task_no_reminder = Task.objects.create(
            title="No Reminder Detail Task",
            status="not_started",
            priority="medium",
            direction="personal",
        )
        self.page.goto(self.url(f"/tasks/{task_no_reminder.pk}/"))

        metadata = self.page.locator("#task-metadata-block")
        metadata.wait_for(state="visible")

        # No purple reminder badge
        reminder_badges = metadata.locator("span.bg-purple-900\\/50")
        self.assertEqual(0, reminder_badges.count())


class CalendarFeedReminderSettingsTests(PlaywrightTestCase):
    """Test the Reminders section on the Calendar Feed Settings page."""

    def setUp(self):
        super().setUp()
        # Enable the calendar feed
        settings = CalendarFeedSettings.load()
        settings.enabled = True
        if not settings.token:
            settings.regenerate_token()
        settings.save()

    def test_reminders_section_visible(self):
        """Calendar feed settings page shows the Reminders section."""
        self.page.goto(self.url("/settings/calendar-feed/"))
        self.page.wait_for_load_state("networkidle")

        header = self.page.locator("text=Reminders")
        header.wait_for(state="visible")
        self.assertTrue(header.is_visible())

    def test_reminder_dropdowns_present_for_each_type(self):
        """Each event type has two reminder dropdown selects."""
        self.page.goto(self.url("/settings/calendar-feed/"))
        self.page.wait_for_load_state("networkidle")

        # Check meetings has two selects
        meetings_sel1 = self.page.locator("select[name='reminder_meetings_1']")
        meetings_sel2 = self.page.locator("select[name='reminder_meetings_2']")
        self.assertTrue(meetings_sel1.is_visible())
        self.assertTrue(meetings_sel2.is_visible())

        # Check tasks has two selects
        tasks_sel1 = self.page.locator("select[name='reminder_tasks_1']")
        tasks_sel2 = self.page.locator("select[name='reminder_tasks_2']")
        self.assertTrue(tasks_sel1.is_visible())
        self.assertTrue(tasks_sel2.is_visible())

    def test_default_meeting_reminders_preselected(self):
        """Meetings default to 60min and 15min reminders."""
        self.page.goto(self.url("/settings/calendar-feed/"))
        self.page.wait_for_load_state("networkidle")

        sel1 = self.page.locator("select[name='reminder_meetings_1']")
        sel2 = self.page.locator("select[name='reminder_meetings_2']")
        self.assertEqual("60", sel1.input_value())
        self.assertEqual("15", sel2.input_value())

    def test_save_reminder_settings(self):
        """Saving reminder settings persists them."""
        self.page.goto(self.url("/settings/calendar-feed/"))
        self.page.wait_for_load_state("networkidle")

        # Change tasks reminders from None to 30 min and 5 min
        self.page.select_option("select[name='reminder_tasks_1']", "30")
        self.page.select_option("select[name='reminder_tasks_2']", "5")

        # Submit the reminders form (find the Save button within the reminders section)
        reminders_form = self.page.locator("input[name='action'][value='update_reminders']").locator("..")
        reminders_form.locator("button[type='submit']").click()

        # Page should reload — verify persisted values
        self.page.wait_for_load_state("networkidle")
        sel1 = self.page.locator("select[name='reminder_tasks_1']")
        sel2 = self.page.locator("select[name='reminder_tasks_2']")
        self.assertEqual("30", sel1.input_value())
        self.assertEqual("5", sel2.input_value())

        # Verify DB
        settings = CalendarFeedSettings.load()
        task_reminders = settings.get_reminders("tasks")
        self.assertIn(30, task_reminders)
        self.assertIn(5, task_reminders)

    def test_feed_url_visible_when_enabled(self):
        """When feed is enabled, the feed URL is shown."""
        self.page.goto(self.url("/settings/calendar-feed/"))
        self.page.wait_for_load_state("networkidle")

        url_input = self.page.locator("#feed-url")
        self.assertTrue(url_input.is_visible())
        feed_value = url_input.input_value()
        self.assertIn("feed.ics", feed_value)
        self.assertIn("token=", feed_value)

    def test_event_type_checkboxes_visible(self):
        """Event type checkboxes are shown when feed is enabled."""
        self.page.goto(self.url("/settings/calendar-feed/"))
        self.page.wait_for_load_state("networkidle")

        header = self.page.locator("text=Events Included")
        header.wait_for(state="visible")

        # Should have checkboxes for event types
        checkboxes = self.page.locator("input[name='event_types']")
        self.assertTrue(checkboxes.count() >= 5)


class ReminderBadgeMobileTests(PlaywrightTestCase):
    """Test reminder badge visibility on mobile viewport."""

    def setUp(self):
        super().setUp()
        self.page.set_viewport_size({"width": 420, "height": 912})
        self.task = Task.objects.create(
            title="Mobile Reminder Task",
            reminder_date=timezone.now() + timedelta(days=1),
            due_date=timezone.localdate() + timedelta(days=1),
            status="not_started",
            priority="high",
            direction="outbound",
        )

    def test_reminder_bell_visible_on_mobile_task_list(self):
        """Bell icon appears on mobile task list rows."""
        self.page.goto(self.url("/tasks/"))

        row = self.page.locator(f"#task-row-{self.task.pk}")
        row.wait_for(state="visible")

        # Bell should be in the title cell (visible on mobile)
        bell = row.locator("span[title*='Reminder']")
        self.assertTrue(bell.count() > 0)

    def test_dashboard_reminders_panel_on_mobile(self):
        """Dashboard Upcoming Reminders panel renders on mobile near the top."""
        self.page.goto(self.url("/?v=legacy"))
        self.page.wait_for_load_state("networkidle")

        # Mobile panel should be visible, desktop panel hidden
        mobile_panel = self.page.locator("#reminders-mobile")
        mobile_panel.wait_for(state="visible")
        self.assertTrue(mobile_panel.is_visible())
        self.assertIn("Mobile Reminder Task", mobile_panel.text_content())

        desktop_panel = self.page.locator("#reminders-desktop")
        self.assertTrue(desktop_panel.is_hidden())

    def test_calendar_settings_reminders_stacked_on_mobile(self):
        """Calendar feed settings reminder grid stacks to single column on mobile."""
        settings = CalendarFeedSettings.load()
        settings.enabled = True
        if not settings.token:
            settings.regenerate_token()
        settings.save()

        self.page.goto(self.url("/settings/calendar-feed/"))
        self.page.wait_for_load_state("networkidle")

        # Mobile labels should be visible (they're hidden on desktop with sm:hidden)
        mobile_label = self.page.locator("label.sm\\:hidden").first
        self.assertTrue(mobile_label.is_visible())
