from django.test import TestCase, Client
from django.utils import timezone

from checklists.models import Checklist, ChecklistItem
from stakeholders.models import Stakeholder
from tasks.models import Task


class ChecklistModelTests(TestCase):
    def setUp(self):
        self.stakeholder = Stakeholder.objects.create(
            name="Test Person", entity_type="contact",
        )
        self.checklist = Checklist.objects.create(
            name="Items to request",
            related_stakeholder=self.stakeholder,
        )

    def test_str(self):
        self.assertEqual(str(self.checklist), "Items to request")

    def test_linked_entity(self):
        self.assertEqual(self.checklist.linked_entity, self.stakeholder)

    def test_get_absolute_url(self):
        self.assertEqual(
            self.checklist.get_absolute_url(),
            self.stakeholder.get_absolute_url(),
        )

    def test_is_overdue(self):
        self.checklist.due_date = timezone.localdate() - timezone.timedelta(days=1)
        self.assertTrue(self.checklist.is_overdue)

    def test_is_not_overdue(self):
        self.checklist.due_date = timezone.localdate() + timezone.timedelta(days=1)
        self.assertFalse(self.checklist.is_overdue)

    def test_is_due_soon(self):
        self.checklist.due_date = timezone.localdate() + timezone.timedelta(days=3)
        self.assertTrue(self.checklist.is_due_soon)


class ChecklistItemModelTests(TestCase):
    def setUp(self):
        self.stakeholder = Stakeholder.objects.create(
            name="Test Person", entity_type="contact",
        )
        self.checklist = Checklist.objects.create(
            name="Test CL", related_stakeholder=self.stakeholder,
        )
        self.item = ChecklistItem.objects.create(
            checklist=self.checklist, title="Get W-9",
        )

    def test_str(self):
        self.assertEqual(str(self.item), "Get W-9")

    def test_default_not_completed(self):
        self.assertFalse(self.item.is_completed)
        self.assertIsNone(self.item.completed_at)


class ChecklistViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.stakeholder = Stakeholder.objects.create(
            name="Thomas Wright", entity_type="contact",
        )

    def test_checklist_add(self):
        resp = self.client.post(
            f"/checklists/stakeholder/{self.stakeholder.pk}/add/",
            {"name": "Items to request"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Checklist.objects.count(), 1)
        cl = Checklist.objects.first()
        self.assertEqual(cl.name, "Items to request")
        self.assertEqual(cl.related_stakeholder, self.stakeholder)

    def test_checklist_add_with_due_date(self):
        resp = self.client.post(
            f"/checklists/stakeholder/{self.stakeholder.pk}/add/",
            {"name": "Due diligence", "due_date": "2026-04-15"},
        )
        self.assertEqual(resp.status_code, 200)
        cl = Checklist.objects.first()
        self.assertEqual(str(cl.due_date), "2026-04-15")

    def test_checklist_delete(self):
        cl = Checklist.objects.create(
            name="To delete", related_stakeholder=self.stakeholder,
        )
        ChecklistItem.objects.create(checklist=cl, title="item1")
        resp = self.client.post(f"/checklists/{cl.pk}/delete/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Checklist.objects.count(), 0)
        self.assertEqual(ChecklistItem.objects.count(), 0)

    def test_item_add(self):
        cl = Checklist.objects.create(
            name="Test CL", related_stakeholder=self.stakeholder,
        )
        resp = self.client.post(
            f"/checklists/{cl.pk}/items/add/",
            {"title": "Get W-9"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(cl.items.count(), 1)
        self.assertEqual(cl.items.first().title, "Get W-9")

    def test_item_toggle(self):
        cl = Checklist.objects.create(
            name="Test CL", related_stakeholder=self.stakeholder,
        )
        item = ChecklistItem.objects.create(checklist=cl, title="Item 1")
        resp = self.client.post(f"/checklists/items/{item.pk}/toggle/")
        self.assertEqual(resp.status_code, 200)
        item.refresh_from_db()
        self.assertTrue(item.is_completed)
        self.assertIsNotNone(item.completed_at)

        # Toggle back
        resp = self.client.post(f"/checklists/items/{item.pk}/toggle/")
        item.refresh_from_db()
        self.assertFalse(item.is_completed)
        self.assertIsNone(item.completed_at)

    def test_item_edit_get(self):
        cl = Checklist.objects.create(
            name="Test CL", related_stakeholder=self.stakeholder,
        )
        item = ChecklistItem.objects.create(checklist=cl, title="Old title")
        resp = self.client.get(f"/checklists/items/{item.pk}/edit/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Old title")

    def test_item_edit_post(self):
        cl = Checklist.objects.create(
            name="Test CL", related_stakeholder=self.stakeholder,
        )
        item = ChecklistItem.objects.create(checklist=cl, title="Old title")
        resp = self.client.post(
            f"/checklists/items/{item.pk}/edit/",
            {"title": "New title"},
        )
        self.assertEqual(resp.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.title, "New title")

    def test_item_edit_cancel(self):
        cl = Checklist.objects.create(
            name="Test CL", related_stakeholder=self.stakeholder,
        )
        item = ChecklistItem.objects.create(checklist=cl, title="Keep this")
        resp = self.client.get(f"/checklists/items/{item.pk}/edit/?cancel=1")
        self.assertEqual(resp.status_code, 200)

    def test_item_delete(self):
        cl = Checklist.objects.create(
            name="Test CL", related_stakeholder=self.stakeholder,
        )
        item = ChecklistItem.objects.create(checklist=cl, title="To delete")
        resp = self.client.post(f"/checklists/items/{item.pk}/delete/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(cl.items.count(), 0)


class DetailPageIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.stakeholder = Stakeholder.objects.create(
            name="Thomas Wright", entity_type="contact",
        )

    def test_stakeholder_detail_shows_checklist_section(self):
        resp = self.client.get(f"/stakeholders/{self.stakeholder.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Checklist name...")

    def test_stakeholder_detail_with_checklist(self):
        cl = Checklist.objects.create(
            name="Items to request", related_stakeholder=self.stakeholder,
        )
        ChecklistItem.objects.create(checklist=cl, title="W-9 form")
        resp = self.client.get(f"/stakeholders/{self.stakeholder.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Items to request")
        self.assertContains(resp, "W-9 form")

    def test_task_detail_shows_checklist_section(self):
        task = Task.objects.create(
            title="Test Task", status="not_started",
            priority="medium", direction="personal",
        )
        resp = self.client.get(f"/tasks/{task.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Checklist name...")


class ChecklistPdfTests(TestCase):
    def test_stakeholder_pdf_includes_checklist(self):
        s = Stakeholder.objects.create(
            name="PDF Test", entity_type="contact",
        )
        cl = Checklist.objects.create(
            name="PDF Checklist", related_stakeholder=s,
        )
        ChecklistItem.objects.create(checklist=cl, title="PDF Item", is_completed=True)
        resp = self.client.get(f"/stakeholders/{s.pk}/pdf/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
