from datetime import time, timedelta
from unittest.mock import patch

from django.core import mail
from django.core.mail.backends.locmem import EmailBackend as LocMemBackend
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from stakeholders.models import Stakeholder

from .models import FollowUp, SubTask, Task
from .notifications import check_overdue_tasks, check_stale_followups, check_upcoming_reminders


class TaskModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.task = Task.objects.create(title="Test Task")

    def test_defaults(self):
        self.assertEqual(self.task.status, "not_started")
        self.assertEqual(self.task.priority, "medium")
        self.assertEqual(self.task.task_type, "one_time")

    def test_str(self):
        self.assertEqual(str(self.task), "Test Task")

    def test_get_absolute_url(self):
        self.assertEqual(
            self.task.get_absolute_url(),
            reverse("tasks:detail", kwargs={"pk": self.task.pk}),
        )

    def test_ordering(self):
        Task.objects.create(title="Due Later", due_date=timezone.localdate() + timedelta(days=5))
        Task.objects.create(title="Due Soon", due_date=timezone.localdate() + timedelta(days=1))
        tasks = list(Task.objects.filter(due_date__isnull=False))
        self.assertTrue(tasks[0].due_date <= tasks[1].due_date)

    def test_m2m_stakeholders(self):
        s = Stakeholder.objects.create(name="M2M Test")
        self.task.related_stakeholders.add(s)
        self.assertIn(s, self.task.related_stakeholders.all())
        self.task.related_stakeholders.remove(s)
        self.assertNotIn(s, self.task.related_stakeholders.all())

    def test_m2m_stakeholder_delete_does_not_cascade(self):
        s = Stakeholder.objects.create(name="Temp")
        self.task.related_stakeholders.add(s)
        s.delete()
        self.task.refresh_from_db()
        self.assertEqual(self.task.related_stakeholders.count(), 0)

    def test_completed_at_nullable(self):
        self.assertIsNone(self.task.completed_at)

    def test_multiple_stakeholders(self):
        s1 = Stakeholder.objects.create(name="Person A")
        s2 = Stakeholder.objects.create(name="Person B")
        self.task.related_stakeholders.add(s1, s2)
        self.assertEqual(self.task.related_stakeholders.count(), 2)


class FollowUpModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(name="FU Person")
        cls.task = Task.objects.create(title="FU Task")

    def test_create(self):
        fu = FollowUp.objects.create(
            task=self.task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now(),
            method="email",
        )
        self.assertEqual(fu.task, self.task)

    def test_str(self):
        fu = FollowUp.objects.create(
            task=self.task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now(),
            method="call",
        )
        self.assertIn("FU Task", str(fu))
        self.assertIn("FU Person", str(fu))

    def test_cascade_on_task_delete(self):
        FollowUp.objects.create(
            task=self.task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now(),
            method="email",
        )
        self.task.delete()
        self.assertEqual(FollowUp.objects.count(), 0)

    def test_set_null_on_stakeholder_delete(self):
        fu_task = Task.objects.create(title="Cascade Test")
        fu = FollowUp.objects.create(
            task=fu_task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now(),
            method="email",
        )
        self.stakeholder.delete()
        fu.refresh_from_db()
        self.assertIsNone(fu.stakeholder)


class TaskViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(name="View Stakeholder")
        cls.task = Task.objects.create(
            title="View Test Task",
            status="not_started",
            priority="high",
            due_date=timezone.localdate() + timedelta(days=3),
        )

    def test_list(self):
        resp = self.client.get(reverse("tasks:list"))
        self.assertEqual(resp.status_code, 200)

    def test_list_search(self):
        resp = self.client.get(reverse("tasks:list"), {"q": "View Test"})
        self.assertContains(resp, "View Test Task")

    def test_list_status_filter(self):
        resp = self.client.get(reverse("tasks:list"), {"status": "not_started"})
        self.assertContains(resp, "View Test Task")

    def test_list_priority_filter(self):
        resp = self.client.get(reverse("tasks:list"), {"priority": "high"})
        self.assertContains(resp, "View Test Task")

    def test_list_htmx(self):
        resp = self.client.get(reverse("tasks:list"), HTTP_HX_REQUEST="true")
        self.assertTemplateUsed(resp, "tasks/partials/_table_view.html")

    def test_create_initial_stakeholder(self):
        resp = self.client.get(
            reverse("tasks:create"),
            {"stakeholder": self.stakeholder.pk},
        )
        self.assertEqual(resp.status_code, 200)

    def test_create_post(self):
        resp = self.client.post(reverse("tasks:create"), {
            "title": "New Task",
            "direction": "personal",
            "status": "not_started",
            "priority": "medium",
            "task_type": "one_time",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Task.objects.filter(title="New Task").exists())

    def test_create_post_with_stakeholders(self):
        s2 = Stakeholder.objects.create(name="Second SH")
        resp = self.client.post(reverse("tasks:create"), {
            "title": "Multi SH Task",
            "direction": "personal",
            "status": "not_started",
            "priority": "medium",
            "task_type": "one_time",
            "related_stakeholders": [self.stakeholder.pk, s2.pk],
        })
        self.assertEqual(resp.status_code, 302)
        task = Task.objects.get(title="Multi SH Task")
        self.assertEqual(task.related_stakeholders.count(), 2)

    def test_detail(self):
        resp = self.client.get(reverse("tasks:detail", args=[self.task.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("follow_ups", resp.context)
        self.assertIn("followup_form", resp.context)

    def test_update(self):
        resp = self.client.post(
            reverse("tasks:edit", args=[self.task.pk]),
            {
                "title": "Updated Task",
                "direction": "personal",
                "status": "in_progress",
                "priority": "high",
                "task_type": "one_time",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, "Updated Task")

    def test_delete(self):
        t = Task.objects.create(title="To Delete")
        resp = self.client.post(reverse("tasks:delete", args=[t.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Task.objects.filter(pk=t.pk).exists())

    def test_csv(self):
        resp = self.client.get(reverse("tasks:export_csv"))
        self.assertEqual(resp["Content-Type"], "text/csv")
        content = resp.content.decode()
        self.assertIn("Title", content)
        self.assertIn("Stakeholders", content)

    def test_pdf(self):
        resp = self.client.get(reverse("tasks:export_pdf", args=[self.task.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_toggle_complete(self):
        resp = self.client.post(reverse("tasks:toggle_complete", args=[self.task.pk]))
        self.assertEqual(resp.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "complete")
        self.assertIsNotNone(self.task.completed_at)

        # Toggle back
        resp = self.client.post(reverse("tasks:toggle_complete", args=[self.task.pk]))
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "not_started")
        self.assertIsNone(self.task.completed_at)

    def test_quick_create_get(self):
        resp = self.client.get(reverse("tasks:quick_create"))
        self.assertEqual(resp.status_code, 200)

    def test_quick_create_post(self):
        resp = self.client.post(reverse("tasks:quick_create"), {
            "title": "Quick Task",
            "task_type": "one_time",
            "priority": "low",
        })
        self.assertEqual(resp.status_code, 204)
        self.assertIn("HX-Trigger", resp)
        self.assertIn("HX-Redirect", resp)

    def test_quick_create_meeting(self):
        resp = self.client.post(reverse("tasks:quick_create"), {
            "title": "Team Standup",
            "task_type": "meeting",
            "due_date": "2025-03-01",
            "due_time": "10:00",
            "priority": "medium",
        })
        self.assertEqual(resp.status_code, 204)
        task = Task.objects.get(title="Team Standup")
        self.assertEqual(task.task_type, "meeting")
        self.assertEqual(str(task.due_time), "10:00:00")

    def test_quick_create_meeting_time_requires_date(self):
        resp = self.client.post(reverse("tasks:quick_create"), {
            "title": "No Date Meeting",
            "task_type": "meeting",
            "due_time": "14:00",
            "priority": "low",
        })
        self.assertEqual(resp.status_code, 200)  # re-renders with error

    def test_followup_add(self):
        resp = self.client.post(
            reverse("tasks:followup_add", args=[self.task.pk]),
            {
                "stakeholder": self.stakeholder.pk,
                "outreach_date": "2025-01-15T10:00",
                "method": "call",
                "follow_up_days": "3",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(FollowUp.objects.count(), 1)

    def test_followup_delete(self):
        fu = FollowUp.objects.create(
            task=self.task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now(),
            method="email",
        )
        resp = self.client.post(reverse("tasks:followup_delete", args=[fu.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(FollowUp.objects.filter(pk=fu.pk).exists())

    def test_followup_edit_get(self):
        fu = FollowUp.objects.create(
            task=self.task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now(),
            method="call",
            notes_text="Original note",
        )
        resp = self.client.get(reverse("tasks:followup_edit", args=[fu.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Original note")

    def test_followup_edit_post(self):
        fu = FollowUp.objects.create(
            task=self.task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now(),
            method="call",
            notes_text="Original note",
        )
        resp = self.client.post(
            reverse("tasks:followup_edit", args=[fu.pk]),
            {
                "stakeholder": self.stakeholder.pk,
                "outreach_date": "2025-01-20T14:00",
                "method": "email",
                "follow_up_days": "5",
                "notes_text": "Updated note",
            },
        )
        self.assertEqual(resp.status_code, 200)
        fu.refresh_from_db()
        self.assertEqual(fu.method, "email")
        self.assertEqual(fu.notes_text, "Updated note")
        self.assertEqual(fu.follow_up_days, 5)

    def test_grouped_choices_in_form(self):
        Stakeholder.objects.create(name="Attorney A", entity_type="attorney")
        Stakeholder.objects.create(name="Lender B", entity_type="lender")
        resp = self.client.get(reverse("tasks:create"))
        content = resp.content.decode()
        self.assertIn("<optgroup", content)


class NotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(name="Notify Person")

    def setUp(self):
        from dashboard.models import EmailSettings

        EmailSettings.objects.update_or_create(pk=1, defaults={
            "smtp_host": "localhost",
            "from_email": "test@legacy.local",
            "admin_email": "admin@legacy.local",
            "notifications_enabled": True,
        })
        # Use in-memory email backend so tests don't need a real SMTP server
        patcher = patch(
            "dashboard.email.get_smtp_connection",
            return_value=LocMemBackend(),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_overdue_sends_email(self):
        Task.objects.create(
            title="Overdue",
            due_date=timezone.localdate() - timedelta(days=2),
            status="not_started",
        )
        check_overdue_tasks()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Overdue", mail.outbox[0].subject)

    def test_overdue_no_tasks(self):
        result = check_overdue_tasks()
        self.assertIn("No overdue", result)
        self.assertEqual(len(mail.outbox), 0)

    def test_overdue_excludes_complete(self):
        Task.objects.create(
            title="Done",
            due_date=timezone.localdate() - timedelta(days=2),
            status="complete",
        )
        result = check_overdue_tasks()
        self.assertIn("No overdue", result)

    def test_upcoming_sends_email(self):
        Task.objects.create(
            title="Upcoming",
            reminder_date=timezone.now() + timedelta(hours=6),
            status="not_started",
        )
        check_upcoming_reminders()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Reminder", mail.outbox[0].subject)

    def test_upcoming_none(self):
        result = check_upcoming_reminders()
        self.assertIn("No upcoming", result)

    def test_upcoming_excludes_complete(self):
        Task.objects.create(
            title="Done Reminder",
            reminder_date=timezone.now() + timedelta(hours=6),
            status="complete",
        )
        result = check_upcoming_reminders()
        self.assertIn("No upcoming", result)

    def test_stale_sends_email(self):
        task = Task.objects.create(title="Stale Task")
        FollowUp.objects.create(
            task=task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now() - timedelta(days=5),
            method="email",
            reminder_enabled=True,
            response_received=False,
        )
        check_stale_followups()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Stale", mail.outbox[0].subject)

    def test_stale_none(self):
        result = check_stale_followups()
        self.assertIn("No stale", result)

    def test_stale_excludes_complete_tasks(self):
        task = Task.objects.create(title="Done Task", status="complete")
        FollowUp.objects.create(
            task=task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now() - timedelta(days=10),
            method="email",
            reminder_enabled=True,
            follow_up_days=3,
            response_received=False,
        )
        result = check_stale_followups()
        self.assertIn("No stale", result)

    def test_stale_respects_per_followup_days(self):
        task = Task.objects.create(title="Custom Days Task")
        # 4 days ago with 7-day window — should NOT be stale yet
        FollowUp.objects.create(
            task=task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now() - timedelta(days=4),
            method="call",
            reminder_enabled=True,
            follow_up_days=7,
            response_received=False,
        )
        result = check_stale_followups()
        self.assertIn("No stale", result)

    def test_stale_triggers_with_custom_days(self):
        task = Task.objects.create(title="Custom Days Task 2")
        # 4 days ago with 2-day window — SHOULD be stale
        FollowUp.objects.create(
            task=task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now() - timedelta(days=4),
            method="call",
            reminder_enabled=True,
            follow_up_days=2,
            response_received=False,
        )
        check_stale_followups()
        self.assertEqual(len(mail.outbox), 1)

    def test_stale_skips_reminder_disabled(self):
        task = Task.objects.create(title="No Reminder Task")
        FollowUp.objects.create(
            task=task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now() - timedelta(days=10),
            method="email",
            reminder_enabled=False,
            follow_up_days=3,
            response_received=False,
        )
        result = check_stale_followups()
        self.assertIn("No stale", result)


class FollowUpModelExtendedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(name="Extended FU Person")
        cls.task = Task.objects.create(title="Extended FU Task")

    def test_follow_up_days_default(self):
        fu = FollowUp.objects.create(
            task=self.task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now(),
            method="email",
        )
        self.assertEqual(fu.follow_up_days, 3)

    def test_reminder_enabled_default_false(self):
        fu = FollowUp.objects.create(
            task=self.task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now(),
            method="email",
        )
        self.assertFalse(fu.reminder_enabled)

    def test_reminder_due_date(self):
        outreach = timezone.now() - timedelta(days=5)
        fu = FollowUp.objects.create(
            task=self.task,
            stakeholder=self.stakeholder,
            outreach_date=outreach,
            method="email",
            follow_up_days=7,
        )
        expected = outreach + timedelta(days=7)
        self.assertEqual(fu.reminder_due_date, expected)

    def test_is_stale_true(self):
        fu = FollowUp.objects.create(
            task=self.task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now() - timedelta(days=5),
            method="email",
            reminder_enabled=True,
            follow_up_days=3,
            response_received=False,
        )
        self.assertTrue(fu.is_stale)

    def test_is_stale_false_within_window(self):
        fu = FollowUp.objects.create(
            task=self.task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now() - timedelta(days=1),
            method="email",
            reminder_enabled=True,
            follow_up_days=3,
            response_received=False,
        )
        self.assertFalse(fu.is_stale)

    def test_is_stale_false_when_responded(self):
        fu = FollowUp.objects.create(
            task=self.task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now() - timedelta(days=10),
            method="email",
            reminder_enabled=True,
            follow_up_days=3,
            response_received=True,
            response_date=timezone.now(),
        )
        self.assertFalse(fu.is_stale)

    def test_is_stale_false_when_reminder_disabled(self):
        fu = FollowUp.objects.create(
            task=self.task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now() - timedelta(days=10),
            method="email",
            reminder_enabled=False,
            follow_up_days=3,
            response_received=False,
        )
        self.assertFalse(fu.is_stale)


class FollowUpRespondViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(name="Respond Person")
        cls.task = Task.objects.create(title="Respond Task")

    def test_followup_respond(self):
        fu = FollowUp.objects.create(
            task=self.task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now() - timedelta(days=2),
            method="email",
            response_received=False,
        )
        resp = self.client.post(reverse("tasks:followup_respond", args=[fu.pk]))
        self.assertEqual(resp.status_code, 200)
        fu.refresh_from_db()
        self.assertTrue(fu.response_received)
        self.assertIsNotNone(fu.response_date)

    def test_followup_respond_undo(self):
        fu = FollowUp.objects.create(
            task=self.task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now() - timedelta(days=2),
            method="email",
            response_received=True,
            response_date=timezone.now(),
        )
        resp = self.client.post(reverse("tasks:followup_respond", args=[fu.pk]))
        self.assertEqual(resp.status_code, 200)
        fu.refresh_from_db()
        self.assertFalse(fu.response_received)
        self.assertIsNone(fu.response_date)

    def test_task_create_with_followup(self):
        resp = self.client.post(reverse("tasks:create"), {
            "title": "Task With FU",
            "direction": "outbound",
            "status": "not_started",
            "priority": "medium",
            "task_type": "one_time",
            "related_stakeholders": [self.stakeholder.pk],
            "fu_create": "on",
            "fu_method": "call",
            "fu_reminder_enabled": "on",
            "fu_follow_up_days": "5",
            "fu_notes": "Test follow-up note",
        })
        self.assertEqual(resp.status_code, 302)
        task = Task.objects.get(title="Task With FU")
        self.assertEqual(task.follow_ups.count(), 1)
        fu = task.follow_ups.first()
        self.assertEqual(fu.stakeholder, self.stakeholder)
        self.assertEqual(fu.method, "call")
        self.assertTrue(fu.reminder_enabled)
        self.assertEqual(fu.follow_up_days, 5)
        self.assertEqual(fu.notes_text, "Test follow-up note")

    def test_task_create_followup_reminder_defaults_off(self):
        resp = self.client.post(reverse("tasks:create"), {
            "title": "Task FU No Reminder",
            "direction": "personal",
            "status": "not_started",
            "priority": "medium",
            "task_type": "one_time",
            "related_stakeholders": [self.stakeholder.pk],
            "fu_create": "on",
            "fu_method": "email",
            "fu_follow_up_days": "3",
        })
        self.assertEqual(resp.status_code, 302)
        task = Task.objects.get(title="Task FU No Reminder")
        fu = task.follow_ups.first()
        self.assertFalse(fu.reminder_enabled)

    def test_task_create_without_followup(self):
        resp = self.client.post(reverse("tasks:create"), {
            "title": "Task Without FU",
            "direction": "personal",
            "status": "not_started",
            "priority": "medium",
            "task_type": "one_time",
            "related_stakeholders": [self.stakeholder.pk],
        })
        self.assertEqual(resp.status_code, 302)
        task = Task.objects.get(title="Task Without FU")
        self.assertEqual(task.follow_ups.count(), 0)

    def test_task_create_followup_skipped_without_stakeholder(self):
        resp = self.client.post(reverse("tasks:create"), {
            "title": "Task No Stakeholder",
            "direction": "personal",
            "status": "not_started",
            "priority": "medium",
            "task_type": "one_time",
            "fu_create": "on",
            "fu_method": "email",
            "fu_follow_up_days": "3",
        })
        self.assertEqual(resp.status_code, 302)
        task = Task.objects.get(title="Task No Stakeholder")
        self.assertEqual(task.follow_ups.count(), 0)


class TaskDirectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(name="Direction Person")

    def test_default_direction_is_personal(self):
        t = Task.objects.create(title="Default Direction")
        self.assertEqual(t.direction, "personal")

    def test_create_outbound_task(self):
        resp = self.client.post(reverse("tasks:create"), {
            "title": "Outbound Task",
            "direction": "outbound",
            "status": "not_started",
            "priority": "medium",
            "task_type": "one_time",
            "related_stakeholders": [self.stakeholder.pk],
        })
        self.assertEqual(resp.status_code, 302)
        task = Task.objects.get(title="Outbound Task")
        self.assertEqual(task.direction, "outbound")

    def test_create_inbound_task(self):
        resp = self.client.post(reverse("tasks:create"), {
            "title": "Inbound Task",
            "direction": "inbound",
            "status": "not_started",
            "priority": "medium",
            "task_type": "one_time",
            "related_stakeholders": [self.stakeholder.pk],
        })
        self.assertEqual(resp.status_code, 302)
        task = Task.objects.get(title="Inbound Task")
        self.assertEqual(task.direction, "inbound")

    def test_direction_filter_on_list(self):
        Task.objects.create(title="Out1", direction="outbound")
        Task.objects.create(title="In1", direction="inbound")
        Task.objects.create(title="Per1", direction="personal")
        resp = self.client.get(reverse("tasks:list"), {"direction": "outbound"})
        self.assertContains(resp, "Out1")
        self.assertNotContains(resp, "In1")
        self.assertNotContains(resp, "Per1")

    def test_detail_shows_direction_badge(self):
        t = Task.objects.create(title="Outbound Detail", direction="outbound")
        resp = self.client.get(reverse("tasks:detail", args=[t.pk]))
        self.assertContains(resp, "Outbound")

    def test_initial_direction_from_querystring(self):
        resp = self.client.get(
            reverse("tasks:create"),
            {"direction": "outbound", "stakeholder": self.stakeholder.pk},
        )
        self.assertEqual(resp.status_code, 200)

    def test_pdf_includes_direction(self):
        t = Task.objects.create(title="PDF Direction", direction="outbound")
        resp = self.client.get(reverse("tasks:export_pdf", args=[t.pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")


class FollowUpResponseNotesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(name="Response Notes Person")
        cls.task = Task.objects.create(title="Response Notes Task")

    def test_followup_respond_get_returns_form(self):
        fu = FollowUp.objects.create(
            task=self.task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now() - timedelta(days=2),
            method="email",
            response_received=False,
        )
        resp = self.client.get(reverse("tasks:followup_respond", args=[fu.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "tasks/partials/_followup_respond_form.html")
        self.assertContains(resp, "response_notes")

    def test_followup_respond_post_saves_notes(self):
        fu = FollowUp.objects.create(
            task=self.task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now() - timedelta(days=2),
            method="email",
            response_received=False,
        )
        resp = self.client.post(
            reverse("tasks:followup_respond", args=[fu.pk]),
            {"response_notes": "They agreed to the terms"},
        )
        self.assertEqual(resp.status_code, 200)
        fu.refresh_from_db()
        self.assertTrue(fu.response_received)
        self.assertIsNotNone(fu.response_date)
        self.assertEqual(fu.response_notes, "They agreed to the terms")

    def test_followup_respond_undo_preserves_notes(self):
        fu = FollowUp.objects.create(
            task=self.task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now() - timedelta(days=2),
            method="email",
            response_received=True,
            response_date=timezone.now(),
            response_notes="Original response notes",
        )
        resp = self.client.post(reverse("tasks:followup_respond", args=[fu.pk]))
        self.assertEqual(resp.status_code, 200)
        fu.refresh_from_db()
        self.assertFalse(fu.response_received)
        self.assertIsNone(fu.response_date)
        self.assertEqual(fu.response_notes, "Original response notes")

    def test_response_notes_displayed_in_list(self):
        fu = FollowUp.objects.create(
            task=self.task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now(),
            method="call",
            response_received=True,
            response_date=timezone.now(),
            response_notes="Said they will send the docs Friday",
        )
        resp = self.client.get(reverse("tasks:detail", args=[self.task.pk]))
        self.assertContains(resp, "Said they will send the docs Friday")


class MeetingTaskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(name="Meeting Person")

    def test_is_meeting_true(self):
        t = Task.objects.create(title="Mtg", task_type="meeting")
        self.assertTrue(t.is_meeting)

    def test_is_meeting_false(self):
        t = Task.objects.create(title="Normal")
        self.assertFalse(t.is_meeting)

    def test_scheduled_datetime_str_with_time(self):
        t = Task.objects.create(
            title="Timed Mtg",
            task_type="meeting",
            due_date=timezone.localdate(),
            due_time=time(14, 0),
        )
        self.assertIn("T14:00:00", t.scheduled_datetime_str)

    def test_scheduled_datetime_str_without_time(self):
        t = Task.objects.create(
            title="Date Only",
            due_date=timezone.localdate(),
        )
        self.assertNotIn("T", t.scheduled_datetime_str)
        self.assertEqual(t.scheduled_datetime_str, t.due_date.isoformat())

    def test_scheduled_datetime_str_no_date(self):
        t = Task.objects.create(title="No Date")
        self.assertEqual(t.scheduled_datetime_str, "")

    def test_create_meeting_via_form(self):
        resp = self.client.post(reverse("tasks:create"), {
            "title": "Board Meeting",
            "direction": "personal",
            "status": "not_started",
            "priority": "medium",
            "task_type": "meeting",
            "due_date": "2026-03-15",
            "due_time": "14:00",
        })
        self.assertEqual(resp.status_code, 302)
        task = Task.objects.get(title="Board Meeting")
        self.assertTrue(task.is_meeting)
        self.assertEqual(task.due_time, time(14, 0))

    def test_due_time_without_due_date_rejected(self):
        resp = self.client.post(reverse("tasks:create"), {
            "title": "Time No Date",
            "direction": "personal",
            "status": "not_started",
            "priority": "medium",
            "task_type": "meeting",
            "due_time": "14:00",
        })
        self.assertEqual(resp.status_code, 200)  # re-renders form with error
        self.assertFalse(Task.objects.filter(title="Time No Date").exists())

    def test_detail_shows_meeting_time(self):
        t = Task.objects.create(
            title="Detail Mtg",
            task_type="meeting",
            due_date=timezone.localdate(),
            due_time=time(14, 30),
        )
        resp = self.client.get(reverse("tasks:detail", args=[t.pk]))
        self.assertContains(resp, "Meeting Time")
        self.assertContains(resp, "2:30 PM")
        self.assertContains(resp, "Meeting Notes")

    def test_detail_non_meeting_no_meeting_notes(self):
        t = Task.objects.create(title="Normal Task")
        resp = self.client.get(reverse("tasks:detail", args=[t.pk]))
        self.assertNotContains(resp, "Meeting Notes")
        self.assertContains(resp, "Notes")

    def test_calendar_meeting_event(self):
        t = Task.objects.create(
            title="Cal Meeting",
            task_type="meeting",
            due_date=timezone.localdate(),
            due_time=time(10, 0),
        )
        resp = self.client.get(reverse("dashboard:calendar_events"))
        data = resp.json()
        meeting_events = [e for e in data if "Cal Meeting" in e["title"]]
        self.assertEqual(len(meeting_events), 1)
        event = meeting_events[0]
        self.assertIn("T10:00:00", event["start"])
        self.assertEqual(event["display"], "block")
        self.assertEqual(event["color"], "#3b82f6")
        self.assertEqual(event["extendedProps"]["type"], "meeting")

    def test_task_type_filter(self):
        Task.objects.create(title="Meeting A", task_type="meeting")
        Task.objects.create(title="Normal B", task_type="one_time")
        resp = self.client.get(reverse("tasks:list"), {"task_type": "meeting"})
        self.assertContains(resp, "Meeting A")
        self.assertNotContains(resp, "Normal B")

    def test_sort_by_created_at(self):
        Task.objects.create(title="First Task")
        Task.objects.create(title="Second Task")
        resp = self.client.get(reverse("tasks:list"), {"sort": "created_at", "dir": "desc"})
        self.assertEqual(resp.status_code, 200)


class KanbanViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.task1 = Task.objects.create(title="Board Task 1", status="not_started")
        cls.task2 = Task.objects.create(title="Board Task 2", status="in_progress")
        cls.task3 = Task.objects.create(title="Board Task 3", status="complete")

    def test_board_view_full_page(self):
        resp = self.client.get(reverse("tasks:list"), {"view": "board"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "kanban-board")
        self.assertContains(resp, "Board Task 1")
        self.assertContains(resp, "Board Task 2")

    def test_board_view_htmx(self):
        resp = self.client.get(
            reverse("tasks:list"), {"view": "board"}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "tasks/partials/_kanban_board.html")

    def test_board_view_no_pagination(self):
        # Board view should show all tasks without pagination
        for i in range(30):
            Task.objects.create(title=f"Bulk Task {i}", status="not_started")
        resp = self.client.get(reverse("tasks:list"), {"view": "board"})
        self.assertEqual(resp.status_code, 200)
        # Should contain all tasks, not just 25
        self.assertContains(resp, "Bulk Task 29")

    def test_board_context_has_kanban_columns(self):
        resp = self.client.get(reverse("tasks:list"), {"view": "board"})
        self.assertIn("kanban_columns", resp.context)
        columns = resp.context["kanban_columns"]
        self.assertEqual(len(columns), 4)
        statuses = [c["status"] for c in columns]
        self.assertEqual(statuses, ["not_started", "in_progress", "waiting", "complete"])

    def test_board_filters_work(self):
        resp = self.client.get(
            reverse("tasks:list"), {"view": "board", "status": "in_progress"}
        )
        self.assertContains(resp, "Board Task 2")

    def test_kanban_update(self):
        resp = self.client.post(
            reverse("tasks:kanban_update", args=[self.task1.pk]),
            {"status": "in_progress"},
        )
        self.assertEqual(resp.status_code, 204)
        self.task1.refresh_from_db()
        self.assertEqual(self.task1.status, "in_progress")

    def test_kanban_update_complete_sets_completed_at(self):
        resp = self.client.post(
            reverse("tasks:kanban_update", args=[self.task1.pk]),
            {"status": "complete"},
        )
        self.assertEqual(resp.status_code, 204)
        self.task1.refresh_from_db()
        self.assertEqual(self.task1.status, "complete")
        self.assertIsNotNone(self.task1.completed_at)

    def test_kanban_update_invalid_status(self):
        resp = self.client.post(
            reverse("tasks:kanban_update", args=[self.task1.pk]),
            {"status": "invalid"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_kanban_update_get_not_allowed(self):
        resp = self.client.get(
            reverse("tasks:kanban_update", args=[self.task1.pk])
        )
        self.assertEqual(resp.status_code, 405)

    def test_table_view_default(self):
        resp = self.client.get(reverse("tasks:list"))
        self.assertContains(resp, "task-table-body")
        self.assertNotContains(resp, "kanban-board")


class InlineUpdateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.task = Task.objects.create(
            title="Inline Task",
            status="not_started",
            priority="medium",
            due_date=timezone.localdate(),
        )

    def test_inline_update_status(self):
        resp = self.client.post(
            reverse("tasks:inline_update", args=[self.task.pk]),
            {"field": "status", "value": "in_progress"},
        )
        self.assertEqual(resp.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "in_progress")

    def test_inline_update_status_complete_sets_completed_at(self):
        resp = self.client.post(
            reverse("tasks:inline_update", args=[self.task.pk]),
            {"field": "status", "value": "complete"},
        )
        self.assertEqual(resp.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "complete")
        self.assertIsNotNone(self.task.completed_at)

    def test_inline_update_priority(self):
        resp = self.client.post(
            reverse("tasks:inline_update", args=[self.task.pk]),
            {"field": "priority", "value": "high"},
        )
        self.assertEqual(resp.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.priority, "high")

    def test_inline_update_due_date(self):
        resp = self.client.post(
            reverse("tasks:inline_update", args=[self.task.pk]),
            {"field": "due_date", "value": "2026-06-15"},
        )
        self.assertEqual(resp.status_code, 200)
        self.task.refresh_from_db()
        from datetime import date
        self.assertEqual(self.task.due_date, date(2026, 6, 15))

    def test_inline_update_due_date_clear(self):
        resp = self.client.post(
            reverse("tasks:inline_update", args=[self.task.pk]),
            {"field": "due_date", "value": ""},
        )
        self.assertEqual(resp.status_code, 200)
        self.task.refresh_from_db()
        self.assertIsNone(self.task.due_date)

    def test_inline_update_invalid_field(self):
        resp = self.client.post(
            reverse("tasks:inline_update", args=[self.task.pk]),
            {"field": "title", "value": "hacked"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_inline_update_invalid_status_value(self):
        resp = self.client.post(
            reverse("tasks:inline_update", args=[self.task.pk]),
            {"field": "status", "value": "invalid"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_inline_update_invalid_date(self):
        resp = self.client.post(
            reverse("tasks:inline_update", args=[self.task.pk]),
            {"field": "due_date", "value": "not-a-date"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_inline_update_get_not_allowed(self):
        resp = self.client.get(
            reverse("tasks:inline_update", args=[self.task.pk])
        )
        self.assertEqual(resp.status_code, 405)

    def test_inline_update_returns_row_partial(self):
        resp = self.client.post(
            reverse("tasks:inline_update", args=[self.task.pk]),
            {"field": "status", "value": "waiting"},
        )
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn(f"task-row-{self.task.pk}", content)

    def test_toggle_complete_returns_row_for_table(self):
        resp = self.client.post(
            reverse("tasks:toggle_complete", args=[self.task.pk])
        )
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn(f"task-row-{self.task.pk}", content)

    def test_toggle_complete_returns_badge_for_detail(self):
        resp = self.client.post(
            reverse("tasks:toggle_complete", args=[self.task.pk]),
            {"context": "detail"},
        )
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertNotIn(f"task-row-{self.task.pk}", content)
        self.assertIn("rounded-full", content)


class StakeholderFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.s1 = Stakeholder.objects.create(name="Alice")
        cls.s2 = Stakeholder.objects.create(name="Bob")
        cls.t1 = Task.objects.create(title="Alice Task")
        cls.t1.related_stakeholders.add(cls.s1)
        cls.t2 = Task.objects.create(title="Bob Task")
        cls.t2.related_stakeholders.add(cls.s2)
        cls.t3 = Task.objects.create(title="No Person Task")

    def test_filter_by_stakeholder(self):
        resp = self.client.get(reverse("tasks:list"), {"stakeholder": self.s1.pk})
        self.assertContains(resp, "Alice Task")
        self.assertNotContains(resp, "Bob Task")
        self.assertNotContains(resp, "No Person Task")

    def test_no_filter_shows_all(self):
        resp = self.client.get(reverse("tasks:list"))
        self.assertContains(resp, "Alice Task")
        self.assertContains(resp, "Bob Task")
        self.assertContains(resp, "No Person Task")

    def test_stakeholder_dropdown_in_context(self):
        resp = self.client.get(reverse("tasks:list"))
        self.assertIn("stakeholders", resp.context)
        self.assertIn("selected_stakeholder", resp.context)


class StaleFollowupIndicatorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(name="Stale FU Person")

    def test_has_stale_followups_true(self):
        task = Task.objects.create(title="Stale Task")
        FollowUp.objects.create(
            task=task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now() - timedelta(days=10),
            method="email",
            reminder_enabled=True,
            follow_up_days=3,
            response_received=False,
        )
        self.assertTrue(task.has_stale_followups)

    def test_has_stale_followups_false_no_followups(self):
        task = Task.objects.create(title="Clean Task")
        self.assertFalse(task.has_stale_followups)

    def test_has_stale_followups_false_all_responded(self):
        task = Task.objects.create(title="Responded Task")
        FollowUp.objects.create(
            task=task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now() - timedelta(days=10),
            method="email",
            reminder_enabled=True,
            follow_up_days=3,
            response_received=True,
            response_date=timezone.now(),
        )
        self.assertFalse(task.has_stale_followups)

    def test_stale_dot_in_row(self):
        task = Task.objects.create(title="Stale Dot Task")
        FollowUp.objects.create(
            task=task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now() - timedelta(days=10),
            method="email",
            reminder_enabled=True,
            follow_up_days=3,
            response_received=False,
        )
        resp = self.client.get(reverse("tasks:list"))
        self.assertContains(resp, "Stale follow-up")


class GroupedViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.t1 = Task.objects.create(title="GV Task 1", status="not_started", priority="high")
        cls.t2 = Task.objects.create(title="GV Task 2", status="in_progress", priority="low")
        cls.t3 = Task.objects.create(title="GV Task 3", status="complete", priority="high",
                                      due_date=timezone.localdate() - timedelta(days=5))

    def test_group_by_status(self):
        resp = self.client.get(reverse("tasks:list"), {"group": "status"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("grouped_tasks", resp.context)
        groups = resp.context["grouped_tasks"]
        self.assertEqual(len(groups), 4)  # all 4 status groups always present

    def test_group_by_priority(self):
        resp = self.client.get(reverse("tasks:list"), {"group": "priority"})
        self.assertEqual(resp.status_code, 200)
        groups = resp.context["grouped_tasks"]
        self.assertEqual(len(groups), 4)

    def test_group_by_due_date(self):
        resp = self.client.get(reverse("tasks:list"), {"group": "due_date"})
        self.assertEqual(resp.status_code, 200)
        groups = resp.context["grouped_tasks"]
        # Should have at least Overdue and No Date buckets
        labels = [g["label"] for g in groups]
        self.assertIn("Overdue", labels)
        self.assertIn("No Date", labels)

    def test_group_by_stakeholder(self):
        s = Stakeholder.objects.create(name="Grouped Person")
        self.t1.related_stakeholders.add(s)
        resp = self.client.get(reverse("tasks:list"), {"group": "stakeholder"})
        self.assertEqual(resp.status_code, 200)
        groups = resp.context["grouped_tasks"]
        labels = [g["label"] for g in groups]
        self.assertIn("Grouped Person", labels)
        self.assertIn("No Stakeholder", labels)

    def test_grouped_htmx_returns_partial(self):
        resp = self.client.get(
            reverse("tasks:list"), {"group": "status"}, HTTP_HX_REQUEST="true"
        )
        self.assertTemplateUsed(resp, "tasks/partials/_grouped_table_view.html")

    def test_no_pagination_in_grouped_view(self):
        for i in range(30):
            Task.objects.create(title=f"GP Task {i}")
        resp = self.client.get(reverse("tasks:list"), {"group": "status"})
        self.assertContains(resp, "GP Task 29")


class SubTaskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.task = Task.objects.create(title="Subtask Parent")

    def test_subtask_add(self):
        resp = self.client.post(
            reverse("tasks:subtask_add", args=[self.task.pk]),
            {"title": "Buy supplies"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(SubTask.objects.filter(task=self.task).count(), 1)

    def test_subtask_toggle(self):
        st = SubTask.objects.create(task=self.task, title="Toggleable")
        self.assertFalse(st.is_completed)
        resp = self.client.post(reverse("tasks:subtask_toggle", args=[st.pk]))
        self.assertEqual(resp.status_code, 200)
        st.refresh_from_db()
        self.assertTrue(st.is_completed)
        # Toggle back
        self.client.post(reverse("tasks:subtask_toggle", args=[st.pk]))
        st.refresh_from_db()
        self.assertFalse(st.is_completed)

    def test_subtask_delete(self):
        st = SubTask.objects.create(task=self.task, title="To Delete")
        resp = self.client.post(reverse("tasks:subtask_delete", args=[st.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(SubTask.objects.filter(pk=st.pk).exists())

    def test_subtask_cascade_on_task_delete(self):
        t = Task.objects.create(title="Parent to Delete")
        st = SubTask.objects.create(task=t, title="Child")
        st_pk = st.pk
        t.delete()
        self.assertFalse(SubTask.objects.filter(pk=st_pk).exists())

    def test_subtask_in_detail_context(self):
        SubTask.objects.create(task=self.task, title="Detail Sub")
        resp = self.client.get(reverse("tasks:detail", args=[self.task.pk]))
        self.assertIn("subtasks", resp.context)
        self.assertIn("subtask_form", resp.context)
        self.assertEqual(resp.context["subtask_count"], 1)

    def test_subtask_progress_in_list(self):
        st1 = SubTask.objects.create(task=self.task, title="Done", is_completed=True)
        st2 = SubTask.objects.create(task=self.task, title="Not Done")
        resp = self.client.get(reverse("tasks:list"))
        self.assertContains(resp, "1/2")


class RecurringTaskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(name="Recurring Person")

    def test_compute_next_due_date_weekly(self):
        from datetime import date
        t = Task(due_date=date(2026, 3, 1), recurrence_rule="weekly")
        self.assertEqual(t.compute_next_due_date(), date(2026, 3, 8))

    def test_compute_next_due_date_monthly(self):
        from datetime import date
        t = Task(due_date=date(2026, 1, 31), recurrence_rule="monthly")
        # Jan 31 → Feb 28 (end-of-month clamping)
        self.assertEqual(t.compute_next_due_date(), date(2026, 2, 28))

    def test_compute_next_due_date_yearly_leap(self):
        from datetime import date
        t = Task(due_date=date(2024, 2, 29), recurrence_rule="yearly")
        self.assertEqual(t.compute_next_due_date(), date(2025, 2, 28))

    def test_compute_next_due_date_quarterly(self):
        from datetime import date
        t = Task(due_date=date(2026, 11, 15), recurrence_rule="quarterly")
        self.assertEqual(t.compute_next_due_date(), date(2027, 2, 15))

    def test_create_next_recurrence(self):
        from datetime import date
        t = Task.objects.create(
            title="Weekly Report",
            due_date=date(2026, 3, 1),
            priority="high",
            direction="outbound",
            is_recurring=True,
            recurrence_rule="weekly",
        )
        t.related_stakeholders.add(self.stakeholder)
        new_task = t.create_next_recurrence()
        self.assertIsNotNone(new_task)
        self.assertEqual(new_task.title, "Weekly Report")
        self.assertEqual(new_task.due_date, date(2026, 3, 8))
        self.assertEqual(new_task.status, "not_started")
        self.assertTrue(new_task.is_recurring)
        self.assertEqual(new_task.related_stakeholders.count(), 1)

    def test_toggle_complete_creates_recurrence(self):
        from datetime import date
        t = Task.objects.create(
            title="Recurring Toggle",
            due_date=date(2026, 3, 1),
            is_recurring=True,
            recurrence_rule="daily",
        )
        initial_count = Task.objects.count()
        self.client.post(reverse("tasks:toggle_complete", args=[t.pk]))
        self.assertEqual(Task.objects.count(), initial_count + 1)
        new_task = Task.objects.filter(title="Recurring Toggle", status="not_started").last()
        self.assertEqual(new_task.due_date, date(2026, 3, 2))

    def test_kanban_update_creates_recurrence(self):
        from datetime import date
        t = Task.objects.create(
            title="Kanban Recur",
            due_date=date(2026, 3, 1),
            is_recurring=True,
            recurrence_rule="weekly",
        )
        initial_count = Task.objects.count()
        self.client.post(
            reverse("tasks:kanban_update", args=[t.pk]),
            {"status": "complete"},
        )
        self.assertEqual(Task.objects.count(), initial_count + 1)

    def test_inline_update_creates_recurrence(self):
        from datetime import date
        t = Task.objects.create(
            title="Inline Recur",
            due_date=date(2026, 3, 1),
            is_recurring=True,
            recurrence_rule="monthly",
        )
        initial_count = Task.objects.count()
        self.client.post(
            reverse("tasks:inline_update", args=[t.pk]),
            {"field": "status", "value": "complete"},
        )
        self.assertEqual(Task.objects.count(), initial_count + 1)

    def test_bulk_complete_creates_recurrence(self):
        from datetime import date
        t = Task.objects.create(
            title="Bulk Recur",
            due_date=date(2026, 3, 1),
            is_recurring=True,
            recurrence_rule="biweekly",
        )
        initial_count = Task.objects.count()
        self.client.post(reverse("tasks:bulk_complete"), {"selected": [t.pk]})
        self.assertEqual(Task.objects.count(), initial_count + 1)

    def test_non_recurring_no_recurrence_on_complete(self):
        t = Task.objects.create(title="One Time Task")
        initial_count = Task.objects.count()
        self.client.post(reverse("tasks:toggle_complete", args=[t.pk]))
        self.assertEqual(Task.objects.count(), initial_count)

    def test_form_validation_recurring_without_rule(self):
        resp = self.client.post(reverse("tasks:create"), {
            "title": "Bad Recurring",
            "direction": "personal",
            "status": "not_started",
            "priority": "medium",
            "task_type": "one_time",
            "is_recurring": "on",
        })
        self.assertEqual(resp.status_code, 200)  # re-renders form
        self.assertFalse(Task.objects.filter(title="Bad Recurring").exists())

    def test_form_validation_recurring_without_date(self):
        resp = self.client.post(reverse("tasks:create"), {
            "title": "No Date Recurring",
            "direction": "personal",
            "status": "not_started",
            "priority": "medium",
            "task_type": "one_time",
            "is_recurring": "on",
            "recurrence_rule": "weekly",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Task.objects.filter(title="No Date Recurring").exists())
