from datetime import timedelta

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from stakeholders.models import Stakeholder

from .models import FollowUp, Task
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

    def test_optional_fks_set_null(self):
        s = Stakeholder.objects.create(name="Temp")
        task = Task.objects.create(title="FK Test", related_stakeholder=s)
        s.delete()
        task.refresh_from_db()
        self.assertIsNone(task.related_stakeholder)

    def test_completed_at_nullable(self):
        self.assertIsNone(self.task.completed_at)


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

    def test_cascade_on_stakeholder_delete(self):
        fu_task = Task.objects.create(title="Cascade Test")
        FollowUp.objects.create(
            task=fu_task,
            stakeholder=self.stakeholder,
            outreach_date=timezone.now(),
            method="email",
        )
        self.stakeholder.delete()
        self.assertEqual(FollowUp.objects.filter(task=fu_task).count(), 0)


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
        self.assertTemplateUsed(resp, "tasks/partials/_task_table_rows.html")

    def test_create_initial_stakeholder(self):
        resp = self.client.get(
            reverse("tasks:create"),
            {"stakeholder": self.stakeholder.pk},
        )
        self.assertEqual(resp.status_code, 200)

    def test_create_post(self):
        resp = self.client.post(reverse("tasks:create"), {
            "title": "New Task",
            "status": "not_started",
            "priority": "medium",
            "task_type": "one_time",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Task.objects.filter(title="New Task").exists())

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
        self.assertIn("Stakeholder", content)

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
            "priority": "low",
        })
        self.assertEqual(resp.status_code, 204)
        self.assertIn("HX-Trigger", resp)
        self.assertIn("HX-Redirect", resp)

    def test_followup_add(self):
        resp = self.client.post(
            reverse("tasks:followup_add", args=[self.task.pk]),
            {
                "stakeholder": self.stakeholder.pk,
                "outreach_date": "2025-01-15T10:00",
                "method": "call",
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


class NotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(name="Notify Person")

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
            response_received=False,
        )
        check_stale_followups()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Stale", mail.outbox[0].subject)

    def test_stale_none(self):
        result = check_stale_followups()
        self.assertIn("No stale", result)
