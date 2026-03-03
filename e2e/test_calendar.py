from datetime import date, time, timedelta
from decimal import Decimal

from django.utils import timezone

from assets.models import Loan
from tasks.models import Task
from e2e.base import PlaywrightTestCase


class CalendarDayMaxEventsTests(PlaywrightTestCase):
    """Test dayMaxEvents overflow on desktop month view."""

    def setUp(self):
        super().setUp()
        # Create 6 tasks on the same day to exceed the limit of 4
        today = timezone.localdate()
        for i in range(6):
            Task.objects.create(
                title=f"Overflow Task {i + 1}",
                due_date=today,
                status="not_started",
                priority="medium",
                direction="personal",
            )

    def test_more_link_shown_when_events_exceed_limit(self):
        """Desktop month view shows '+N more' link when >4 events on a day."""
        self.page.goto(self.url("/calendar/"))

        # Wait for calendar to render events
        self.page.wait_for_selector(".fc-event")

        # Should see a "+N more" link because we have 6 events and limit is 4
        more_link = self.page.locator(".fc-daygrid-more-link")
        more_link.wait_for(state="visible", timeout=5000)
        self.assertTrue(more_link.is_visible())
        self.assertIn("more", more_link.text_content().lower())


class CalendarMeetingTimeSlotTests(PlaywrightTestCase):
    """Test that meetings with due_time appear in time slots, not all-day row."""

    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.meeting = Task.objects.create(
            title="Team Standup",
            due_date=today,
            due_time=time(10, 0),
            task_type="meeting",
            status="not_started",
            priority="medium",
            direction="personal",
        )

    def test_meeting_has_time_in_event_data(self):
        """Calendar events endpoint returns allDay: false for meetings with time."""
        # Check the JSON endpoint directly
        today = timezone.localdate()
        start = today - timedelta(days=1)
        end = today + timedelta(days=1)
        response = self.client.get(
            f"/calendar/events/?start={start.isoformat()}&end={end.isoformat()}"
        )
        events = response.json()

        meeting_events = [e for e in events if e.get("extendedProps", {}).get("type") == "meeting"]
        self.assertTrue(len(meeting_events) > 0)
        meeting = meeting_events[0]
        self.assertFalse(meeting.get("allDay", True))
        self.assertIn("T10:00:00", meeting["start"])


class CalendarTooltipTests(PlaywrightTestCase):
    """Test hover tooltips on calendar events."""

    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.task = Task.objects.create(
            title="Tooltip Test Task",
            due_date=today,
            status="not_started",
            priority="medium",
            direction="personal",
        )

    def test_event_has_title_attribute(self):
        """Calendar events have a title attribute for browser tooltip."""
        self.page.goto(self.url("/calendar/"))

        # Wait for event to render
        event = self.page.locator(".fc-event").first
        event.wait_for(state="visible", timeout=5000)

        # The event element should have a title attribute
        title_attr = event.get_attribute("title")
        self.assertIsNotNone(title_attr)
        self.assertIn("Tooltip Test Task", title_attr)


class CalendarClickToCreateTests(PlaywrightTestCase):
    """Test clicking empty day to create a task with pre-filled date."""

    def test_click_empty_day_navigates_to_create(self):
        """Clicking an empty day cell navigates to task create form with date."""
        self.page.goto(self.url("/calendar/"))

        # Wait for the calendar to render
        self.page.wait_for_selector(".fc-daygrid-day")

        # Find a day cell that is in the future (avoid today which might have events)
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        day_cell = self.page.locator(f'[data-date="{tomorrow}"]')

        if day_cell.count() > 0:
            # Click the day cell's background area
            day_cell.click()

            # Should navigate to task create with due_date param
            self.page.wait_for_url("**/tasks/create/**", timeout=5000)
            self.assertIn("due_date=", self.page.url)
            self.assertIn(tomorrow, self.page.url)

    def test_task_create_prefills_date_from_query(self):
        """Task create form pre-fills due_date from query parameter."""
        target_date = "2026-03-15"
        self.page.goto(self.url(f"/tasks/create/?due_date={target_date}"))

        # The due_date field should be pre-filled
        date_input = self.page.locator("#id_due_date")
        date_input.wait_for(state="visible")
        self.assertEqual(target_date, date_input.input_value())


class CalendarDirectionArrowTests(PlaywrightTestCase):
    """Test direction arrow prefixes on calendar events."""

    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.outbound_task = Task.objects.create(
            title="Send Report",
            due_date=today,
            status="not_started",
            priority="medium",
            direction="outbound",
        )
        self.inbound_task = Task.objects.create(
            title="Receive Documents",
            due_date=today,
            status="not_started",
            priority="medium",
            direction="inbound",
        )

    def test_direction_arrows_in_event_titles(self):
        """Outbound tasks show arrow-up-right, inbound show arrow-down-left."""
        today = timezone.localdate()
        start = today - timedelta(days=1)
        end = today + timedelta(days=1)
        response = self.client.get(
            f"/calendar/events/?start={start.isoformat()}&end={end.isoformat()}"
        )
        events = response.json()

        titles = {e["title"] for e in events}
        # Check for arrow prefixes (↗ and ↙)
        self.assertTrue(
            any("\u2197" in t and "Send Report" in t for t in titles),
            f"Expected outbound arrow in titles: {titles}"
        )
        self.assertTrue(
            any("\u2199" in t and "Receive Documents" in t for t in titles),
            f"Expected inbound arrow in titles: {titles}"
        )

    def test_no_prefix_for_personal(self):
        """Personal tasks have no direction prefix."""
        Task.objects.all().delete()
        today = timezone.localdate()
        Task.objects.create(
            title="Personal Task",
            due_date=today,
            status="not_started",
            priority="medium",
            direction="personal",
        )
        start = today - timedelta(days=1)
        end = today + timedelta(days=1)
        response = self.client.get(
            f"/calendar/events/?start={start.isoformat()}&end={end.isoformat()}"
        )
        events = response.json()
        task_events = [e for e in events if e.get("extendedProps", {}).get("type") == "task"]
        self.assertEqual(task_events[0]["title"], "Personal Task")


class CalendarPaymentAmountTests(PlaywrightTestCase):
    """Test dollar amounts on payment calendar events."""

    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.loan_with_payment = Loan.objects.create(
            name="Mortgage Loan",
            status="active",
            next_payment_date=today,
            monthly_payment=Decimal("2500.00"),
        )
        self.loan_without_payment = Loan.objects.create(
            name="Personal Loan",
            status="active",
            next_payment_date=today,
            monthly_payment=None,
        )

    def test_payment_events_show_dollar_amount(self):
        """Payment events with monthly_payment show dollar amount."""
        today = timezone.localdate()
        start = today - timedelta(days=1)
        end = today + timedelta(days=1)
        response = self.client.get(
            f"/calendar/events/?start={start.isoformat()}&end={end.isoformat()}"
        )
        events = response.json()
        payment_events = [e for e in events if e.get("extendedProps", {}).get("type") == "payment"]

        # Loan with payment should show "$2,500 — Mortgage Loan"
        mortgage_events = [e for e in payment_events if "Mortgage" in e["title"]]
        self.assertEqual(len(mortgage_events), 1)
        self.assertIn("$2,500", mortgage_events[0]["title"])

        # Loan without payment should show "Payment: Personal Loan"
        personal_events = [e for e in payment_events if "Personal" in e["title"]]
        self.assertEqual(len(personal_events), 1)
        self.assertIn("Payment:", personal_events[0]["title"])


class CalendarFilterToggleTests(PlaywrightTestCase):
    """Test calendar filter toggle buttons."""

    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.task = Task.objects.create(
            title="Filter Test Task",
            due_date=today,
            status="not_started",
            priority="medium",
            direction="personal",
        )

    def test_filter_toggle_hides_events(self):
        """Clicking a filter toggle hides events of that type."""
        self.page.goto(self.url("/calendar/"))

        # Wait for events to load
        self.page.wait_for_selector(".fc-event")

        # Click the Tasks filter toggle on desktop to disable it
        task_toggle = self.page.locator('#calendar-filters-desktop .cal-toggle[data-type="task"]')
        task_toggle.click()

        # The toggle should lose 'active' class
        self.page.wait_for_function(
            "!document.querySelector('#calendar-filters-desktop .cal-toggle[data-type=\"task\"]').classList.contains('active')"
        )

        # Task events should be hidden
        events = self.page.locator(".fc-event")
        for i in range(events.count()):
            display = events.nth(i).evaluate("el => getComputedStyle(el).display")
            self.assertEqual(display, "none")
