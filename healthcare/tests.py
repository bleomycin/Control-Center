import json
from datetime import date, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from dashboard.choices import invalidate_choice_cache
from dashboard.models import ChoiceOption

from .forms import (
    AdviceForm, AppointmentForm, ConditionForm, HealthcareTabForm,
    PrescriptionForm, ProviderForm, SupplementForm, TestResultForm,
    VisitForm,
)
from .models import (
    Advice, Appointment, Condition, HealthcareTab, Prescription,
    Provider, Supplement, TestResult, Visit,
)


# ---------------------------------------------------------------------------
# Helper mixin for seeding ChoiceOptions used by healthcare forms
# ---------------------------------------------------------------------------

class HealthcareTestMixin:
    """Seed required ChoiceOptions and invalidate cache before each test."""

    def setUp(self):
        super().setUp()
        invalidate_choice_cache()
        ChoiceOption.objects.get_or_create(
            category="provider_type", value="primary_care",
            defaults={"label": "Primary Care"},
        )
        ChoiceOption.objects.get_or_create(
            category="provider_type", value="specialist",
            defaults={"label": "Specialist"},
        )
        ChoiceOption.objects.get_or_create(
            category="test_type", value="lab",
            defaults={"label": "Lab"},
        )
        ChoiceOption.objects.get_or_create(
            category="test_type", value="imaging",
            defaults={"label": "Imaging"},
        )
        invalidate_choice_cache()


# ===========================================================================
# 1. Model Tests
# ===========================================================================

class HealthcareTabModelTests(TestCase):

    def test_str(self):
        tab = HealthcareTab.objects.create(label="My Providers", healthcare_types=["providers"])
        self.assertEqual(str(tab), "My Providers")

    def test_auto_slug(self):
        tab = HealthcareTab.objects.create(label="Test Results Tab", healthcare_types=["test_results"])
        self.assertEqual(tab.key, "test-results-tab")

    def test_slug_collision(self):
        HealthcareTab.objects.create(label="Meds", healthcare_types=["prescriptions"])
        tab2 = HealthcareTab.objects.create(label="Meds", healthcare_types=["supplements"])
        self.assertEqual(tab2.key, "meds-1")

    def test_slug_preserved_on_update(self):
        tab = HealthcareTab.objects.create(label="ABC", key="custom-key", healthcare_types=["providers"])
        tab.label = "New Label"
        tab.save()
        tab.refresh_from_db()
        self.assertEqual(tab.key, "custom-key")

    def test_ordering(self):
        HealthcareTab.objects.all().delete()
        HealthcareTab.objects.create(label="B", sort_order=2, healthcare_types=["visits"])
        HealthcareTab.objects.create(label="A", sort_order=1, healthcare_types=["providers"])
        tabs = list(HealthcareTab.objects.values_list("label", flat=True))
        self.assertEqual(tabs[0], "A")


class ProviderModelTests(TestCase):

    def test_str(self):
        p = Provider.objects.create(name="Dr. Smith")
        self.assertEqual(str(p), "Dr. Smith")

    def test_defaults(self):
        p = Provider.objects.create(name="Dr. Jones")
        self.assertEqual(p.status, "active")
        self.assertEqual(p.provider_type, "primary_care")

    def test_get_absolute_url(self):
        p = Provider.objects.create(name="Dr. X")
        self.assertEqual(p.get_absolute_url(), reverse("healthcare:provider_detail", args=[p.pk]))

    def test_ordering(self):
        Provider.objects.create(name="Zeta")
        Provider.objects.create(name="Alpha")
        names = list(Provider.objects.values_list("name", flat=True))
        self.assertEqual(names, sorted(names))


class ConditionModelTests(TestCase):

    def test_str(self):
        c = Condition.objects.create(name="Hypertension")
        self.assertEqual(str(c), "Hypertension")

    def test_defaults(self):
        c = Condition.objects.create(name="Flu")
        self.assertEqual(c.status, "active")

    def test_get_absolute_url(self):
        c = Condition.objects.create(name="Asthma")
        self.assertEqual(c.get_absolute_url(), reverse("healthcare:condition_detail", args=[c.pk]))


class PrescriptionModelTests(TestCase):

    def test_str(self):
        rx = Prescription.objects.create(medication_name="Ibuprofen")
        self.assertEqual(str(rx), "Ibuprofen")

    def test_defaults(self):
        rx = Prescription.objects.create(medication_name="Aspirin")
        self.assertEqual(rx.status, "active")
        self.assertFalse(rx.is_controlled)

    def test_get_absolute_url(self):
        rx = Prescription.objects.create(medication_name="Med")
        self.assertEqual(rx.get_absolute_url(), reverse("healthcare:prescription_detail", args=[rx.pk]))

    def test_is_refill_due_true(self):
        rx = Prescription.objects.create(
            medication_name="TestMed",
            next_refill_date=timezone.localdate() - timedelta(days=1),
        )
        self.assertTrue(rx.is_refill_due)

    def test_is_refill_due_false_future(self):
        rx = Prescription.objects.create(
            medication_name="TestMed",
            next_refill_date=timezone.localdate() + timedelta(days=5),
        )
        self.assertFalse(rx.is_refill_due)

    def test_is_refill_due_false_no_date(self):
        rx = Prescription.objects.create(medication_name="TestMed")
        self.assertFalse(rx.is_refill_due)

    def test_is_refill_due_today(self):
        rx = Prescription.objects.create(
            medication_name="TestMed",
            next_refill_date=timezone.localdate(),
        )
        self.assertTrue(rx.is_refill_due)


class SupplementModelTests(TestCase):

    def test_str(self):
        s = Supplement.objects.create(name="Vitamin D")
        self.assertEqual(str(s), "Vitamin D")

    def test_defaults(self):
        s = Supplement.objects.create(name="Omega-3")
        self.assertEqual(s.status, "active")

    def test_get_absolute_url(self):
        s = Supplement.objects.create(name="Zinc")
        self.assertEqual(s.get_absolute_url(), reverse("healthcare:supplement_detail", args=[s.pk]))


class TestResultModelTests(TestCase):

    def test_str(self):
        tr = TestResult.objects.create(test_name="CBC", date=date.today())
        self.assertEqual(str(tr), "CBC")

    def test_defaults(self):
        tr = TestResult.objects.create(test_name="CMP", date=date.today())
        self.assertEqual(tr.status, "pending")
        self.assertEqual(tr.test_type, "lab")

    def test_get_absolute_url(self):
        tr = TestResult.objects.create(test_name="TSH", date=date.today())
        self.assertEqual(tr.get_absolute_url(), reverse("healthcare:testresult_detail", args=[tr.pk]))


class VisitModelTests(TestCase):

    def test_str_with_provider(self):
        p = Provider.objects.create(name="Dr. Smith")
        v = Visit.objects.create(date=date(2025, 6, 15), visit_type="routine", provider=p)
        self.assertIn("Dr. Smith", str(v))
        self.assertIn("Routine", str(v))

    def test_str_without_provider(self):
        v = Visit.objects.create(date=date(2025, 6, 15), visit_type="urgent")
        self.assertIn("Unknown", str(v))

    def test_get_absolute_url(self):
        v = Visit.objects.create(date=date.today())
        self.assertEqual(v.get_absolute_url(), reverse("healthcare:visit_detail", args=[v.pk]))


class AdviceModelTests(TestCase):

    def test_str(self):
        a = Advice.objects.create(title="Eat more vegetables", advice_text="text", date=date.today())
        self.assertEqual(str(a), "Eat more vegetables")

    def test_defaults(self):
        a = Advice.objects.create(title="Walk daily", advice_text="text", date=date.today())
        self.assertEqual(a.status, "active")
        self.assertEqual(a.category, "other")

    def test_get_absolute_url(self):
        a = Advice.objects.create(title="Rest", advice_text="text", date=date.today())
        self.assertEqual(a.get_absolute_url(), reverse("healthcare:advice_detail", args=[a.pk]))


class AppointmentModelTests(TestCase):

    def test_str(self):
        a = Appointment.objects.create(title="Annual Checkup", date=date.today())
        self.assertEqual(str(a), "Annual Checkup")

    def test_defaults(self):
        a = Appointment.objects.create(title="Follow-up", date=date.today())
        self.assertEqual(a.status, "scheduled")
        self.assertEqual(a.visit_type, "routine")

    def test_get_absolute_url(self):
        a = Appointment.objects.create(title="Test", date=date.today())
        self.assertEqual(a.get_absolute_url(), reverse("healthcare:appointment_detail", args=[a.pk]))

    def test_scheduled_datetime_str_with_time(self):
        a = Appointment.objects.create(
            title="Morning", date=date(2025, 8, 1), time=time(9, 30),
        )
        self.assertEqual(a.scheduled_datetime_str, "2025-08-01T09:30:00")

    def test_scheduled_datetime_str_without_time(self):
        a = Appointment.objects.create(title="AllDay", date=date(2025, 8, 1))
        self.assertEqual(a.scheduled_datetime_str, "2025-08-01")


# ===========================================================================
# 2. Form Tests
# ===========================================================================

class HealthcareTabFormTests(TestCase):

    def test_valid_create(self):
        form = HealthcareTabForm(data={"label": "My Tab", "healthcare_types": ["providers"]})
        self.assertTrue(form.is_valid())

    def test_missing_label(self):
        form = HealthcareTabForm(data={"label": "", "healthcare_types": ["providers"]})
        self.assertFalse(form.is_valid())
        self.assertIn("label", form.errors)

    def test_missing_types(self):
        form = HealthcareTabForm(data={"label": "Tab"})
        self.assertFalse(form.is_valid())
        self.assertIn("healthcare_types", form.errors)

    def test_save_new(self):
        form = HealthcareTabForm(data={"label": "New Tab", "healthcare_types": ["visits", "advice"]})
        self.assertTrue(form.is_valid())
        tab = form.save()
        self.assertEqual(tab.label, "New Tab")
        self.assertEqual(tab.healthcare_types, ["visits", "advice"])

    def test_save_update(self):
        tab = HealthcareTab.objects.create(label="Old", healthcare_types=["providers"])
        form = HealthcareTabForm(data={"label": "Updated", "healthcare_types": ["visits"]}, instance=tab)
        self.assertTrue(form.is_valid())
        saved = form.save()
        self.assertEqual(saved.pk, tab.pk)
        self.assertEqual(saved.label, "Updated")


class ProviderFormTests(HealthcareTestMixin, TestCase):

    def test_valid(self):
        form = ProviderForm(data={"name": "Dr. Test", "provider_type": "primary_care", "status": "active"})
        self.assertTrue(form.is_valid())

    def test_missing_name(self):
        form = ProviderForm(data={"name": "", "provider_type": "primary_care", "status": "active"})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)


class ConditionFormTests(TestCase):

    def test_valid(self):
        form = ConditionForm(data={"name": "Diabetes", "status": "active"})
        self.assertTrue(form.is_valid())

    def test_missing_name(self):
        form = ConditionForm(data={"name": "", "status": "active"})
        self.assertFalse(form.is_valid())


class PrescriptionFormTests(HealthcareTestMixin, TestCase):

    def test_valid(self):
        form = PrescriptionForm(data={"medication_name": "Metformin", "status": "active"})
        self.assertTrue(form.is_valid())

    def test_missing_medication_name(self):
        form = PrescriptionForm(data={"medication_name": "", "status": "active"})
        self.assertFalse(form.is_valid())


class SupplementFormTests(TestCase):

    def test_valid(self):
        form = SupplementForm(data={"name": "Fish Oil", "status": "active"})
        self.assertTrue(form.is_valid())

    def test_missing_name(self):
        form = SupplementForm(data={"name": "", "status": "active"})
        self.assertFalse(form.is_valid())


class TestResultFormTests(HealthcareTestMixin, TestCase):

    def test_valid(self):
        form = TestResultForm(data={
            "test_name": "CBC", "test_type": "lab",
            "date": "2025-06-01", "status": "pending",
        })
        self.assertTrue(form.is_valid())

    def test_missing_date(self):
        form = TestResultForm(data={
            "test_name": "CBC", "test_type": "lab", "status": "pending",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("date", form.errors)


class VisitFormTests(TestCase):

    def test_valid(self):
        form = VisitForm(data={"date": "2025-07-01", "visit_type": "routine"})
        self.assertTrue(form.is_valid())

    def test_missing_date(self):
        form = VisitForm(data={"visit_type": "routine"})
        self.assertFalse(form.is_valid())


class AdviceFormTests(TestCase):

    def test_valid(self):
        form = AdviceForm(data={
            "title": "Walk more",
            "advice_text": "Walk 30 min daily.",
            "date": "2025-07-01",
            "category": "exercise",
            "status": "active",
        })
        self.assertTrue(form.is_valid())

    def test_missing_advice_text(self):
        form = AdviceForm(data={
            "title": "Walk",
            "date": "2025-07-01",
            "category": "exercise",
            "status": "active",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("advice_text", form.errors)


class AppointmentFormTests(HealthcareTestMixin, TestCase):

    def test_valid(self):
        form = AppointmentForm(data={
            "title": "Annual Checkup",
            "date": "2025-09-01",
            "status": "scheduled",
            "visit_type": "routine",
        })
        self.assertTrue(form.is_valid())

    def test_missing_title(self):
        form = AppointmentForm(data={
            "date": "2025-09-01",
            "status": "scheduled",
            "visit_type": "routine",
        })
        self.assertFalse(form.is_valid())

    def test_initial_date_time_from_query(self):
        form = AppointmentForm(initial={"date": "2025-10-01", "time": "10:00"})
        self.assertEqual(form.fields["date"].initial, "2025-10-01")
        self.assertEqual(form.fields["time"].initial, "10:00")


# ===========================================================================
# 3. List View Tests
# ===========================================================================

class HealthcareListViewTests(HealthcareTestMixin, TestCase):
    """List view tests. Seeded tabs from migration: active-care, records, planning."""

    def setUp(self):
        super().setUp()
        # The seed migration creates active-care (providers, prescriptions, supplements, conditions),
        # records (test_results, visits), planning (appointments, advice).
        self.provider = Provider.objects.create(name="Dr. List")
        self.rx = Prescription.objects.create(medication_name="Aspirin")

    def test_list_returns_200(self):
        resp = self.client.get(reverse("healthcare:healthcare_list"))
        self.assertEqual(resp.status_code, 200)

    def test_default_tab_is_first_seeded(self):
        resp = self.client.get(reverse("healthcare:healthcare_list"))
        # First seeded tab is "active-care"
        self.assertEqual(resp.context["current_tab"], "active-care")

    def test_tab_switching(self):
        resp = self.client.get(reverse("healthcare:healthcare_list"), {"tab": "records"})
        self.assertEqual(resp.context["current_tab"], "records")
        self.assertIn("visits", resp.context)

    def test_invalid_tab_falls_back_to_first(self):
        resp = self.client.get(reverse("healthcare:healthcare_list"), {"tab": "nonexistent"})
        self.assertEqual(resp.context["current_tab"], "active-care")

    def test_search_providers(self):
        resp = self.client.get(reverse("healthcare:healthcare_list"), {"tab": "active-care", "q": "List"})
        self.assertIn(self.provider, resp.context["providers"])

    def test_search_providers_no_match(self):
        resp = self.client.get(reverse("healthcare:healthcare_list"), {"tab": "active-care", "q": "zzz"})
        self.assertEqual(resp.context["providers"].count(), 0)

    def test_status_filter(self):
        Provider.objects.create(name="Dr. Inactive", status="inactive")
        resp = self.client.get(reverse("healthcare:healthcare_list"), {
            "tab": "active-care", "status": "active",
        })
        providers = resp.context["providers"]
        self.assertTrue(all(p.status == "active" for p in providers))

    def test_htmx_returns_partial(self):
        resp = self.client.get(
            reverse("healthcare:healthcare_list"),
            {"tab": "active-care"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        # HTMX returns partial template, not full page
        self.assertNotContains(resp, "<html")

    def test_sorting(self):
        Provider.objects.create(name="Zeta Provider")
        resp = self.client.get(reverse("healthcare:healthcare_list"), {
            "tab": "active-care", "sort": "name", "dir": "asc",
        })
        self.assertEqual(resp.status_code, 200)


# ===========================================================================
# 4. CRUD View Tests
# ===========================================================================

class ProviderCRUDTests(HealthcareTestMixin, TestCase):

    def test_create_get(self):
        resp = self.client.get(reverse("healthcare:provider_create"))
        self.assertEqual(resp.status_code, 200)

    def test_create_post(self):
        resp = self.client.post(reverse("healthcare:provider_create"), {
            "name": "Dr. New",
            "provider_type": "primary_care",
            "status": "active",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Provider.objects.filter(name="Dr. New").exists())

    def test_detail(self):
        p = Provider.objects.create(name="Dr. Detail")
        resp = self.client.get(reverse("healthcare:provider_detail", args=[p.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Dr. Detail")

    def test_update_get(self):
        p = Provider.objects.create(name="Dr. Edit")
        resp = self.client.get(reverse("healthcare:provider_edit", args=[p.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_update_post(self):
        p = Provider.objects.create(name="Dr. Old")
        resp = self.client.post(reverse("healthcare:provider_edit", args=[p.pk]), {
            "name": "Dr. Updated",
            "provider_type": "specialist",
            "status": "active",
        })
        self.assertEqual(resp.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.name, "Dr. Updated")

    def test_delete(self):
        p = Provider.objects.create(name="Dr. Delete")
        resp = self.client.post(reverse("healthcare:provider_delete", args=[p.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Provider.objects.filter(pk=p.pk).exists())


class ConditionCRUDTests(TestCase):

    def test_create_get(self):
        resp = self.client.get(reverse("healthcare:condition_create"))
        self.assertEqual(resp.status_code, 200)

    def test_create_post(self):
        resp = self.client.post(reverse("healthcare:condition_create"), {
            "name": "Hypertension",
            "status": "active",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Condition.objects.filter(name="Hypertension").exists())

    def test_detail(self):
        c = Condition.objects.create(name="Asthma")
        resp = self.client.get(reverse("healthcare:condition_detail", args=[c.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Asthma")

    def test_update_post(self):
        c = Condition.objects.create(name="Old Name")
        resp = self.client.post(reverse("healthcare:condition_edit", args=[c.pk]), {
            "name": "Updated Name",
            "status": "managed",
        })
        self.assertEqual(resp.status_code, 302)
        c.refresh_from_db()
        self.assertEqual(c.name, "Updated Name")

    def test_delete(self):
        c = Condition.objects.create(name="Delete Me")
        resp = self.client.post(reverse("healthcare:condition_delete", args=[c.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Condition.objects.filter(pk=c.pk).exists())


class PrescriptionCRUDTests(HealthcareTestMixin, TestCase):

    def test_create_get(self):
        resp = self.client.get(reverse("healthcare:prescription_create"))
        self.assertEqual(resp.status_code, 200)

    def test_create_post(self):
        resp = self.client.post(reverse("healthcare:prescription_create"), {
            "medication_name": "Lisinopril",
            "status": "active",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Prescription.objects.filter(medication_name="Lisinopril").exists())

    def test_detail(self):
        rx = Prescription.objects.create(medication_name="Metformin")
        resp = self.client.get(reverse("healthcare:prescription_detail", args=[rx.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Metformin")

    def test_update_post(self):
        rx = Prescription.objects.create(medication_name="OldMed")
        resp = self.client.post(reverse("healthcare:prescription_edit", args=[rx.pk]), {
            "medication_name": "NewMed",
            "status": "active",
        })
        self.assertEqual(resp.status_code, 302)
        rx.refresh_from_db()
        self.assertEqual(rx.medication_name, "NewMed")

    def test_delete(self):
        rx = Prescription.objects.create(medication_name="Delete Me")
        resp = self.client.post(reverse("healthcare:prescription_delete", args=[rx.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Prescription.objects.filter(pk=rx.pk).exists())


class SupplementCRUDTests(TestCase):

    def test_create_get(self):
        resp = self.client.get(reverse("healthcare:supplement_create"))
        self.assertEqual(resp.status_code, 200)

    def test_create_post(self):
        resp = self.client.post(reverse("healthcare:supplement_create"), {
            "name": "Vitamin D",
            "status": "active",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Supplement.objects.filter(name="Vitamin D").exists())

    def test_detail(self):
        s = Supplement.objects.create(name="Omega-3")
        resp = self.client.get(reverse("healthcare:supplement_detail", args=[s.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_update_post(self):
        s = Supplement.objects.create(name="Old Supp")
        resp = self.client.post(reverse("healthcare:supplement_edit", args=[s.pk]), {
            "name": "Updated Supp",
            "status": "active",
        })
        self.assertEqual(resp.status_code, 302)
        s.refresh_from_db()
        self.assertEqual(s.name, "Updated Supp")

    def test_delete(self):
        s = Supplement.objects.create(name="Delete Supp")
        resp = self.client.post(reverse("healthcare:supplement_delete", args=[s.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Supplement.objects.filter(pk=s.pk).exists())


class TestResultCRUDTests(HealthcareTestMixin, TestCase):

    def test_create_get(self):
        resp = self.client.get(reverse("healthcare:testresult_create"))
        self.assertEqual(resp.status_code, 200)

    def test_create_post(self):
        resp = self.client.post(reverse("healthcare:testresult_create"), {
            "test_name": "CBC",
            "test_type": "lab",
            "date": "2025-06-01",
            "status": "pending",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(TestResult.objects.filter(test_name="CBC").exists())

    def test_detail(self):
        tr = TestResult.objects.create(test_name="Lipid Panel", date=date.today())
        resp = self.client.get(reverse("healthcare:testresult_detail", args=[tr.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_update_post(self):
        tr = TestResult.objects.create(test_name="Old Test", date=date.today())
        resp = self.client.post(reverse("healthcare:testresult_edit", args=[tr.pk]), {
            "test_name": "New Test",
            "test_type": "lab",
            "date": "2025-06-01",
            "status": "normal",
        })
        self.assertEqual(resp.status_code, 302)
        tr.refresh_from_db()
        self.assertEqual(tr.test_name, "New Test")

    def test_delete(self):
        tr = TestResult.objects.create(test_name="Delete Test", date=date.today())
        resp = self.client.post(reverse("healthcare:testresult_delete", args=[tr.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(TestResult.objects.filter(pk=tr.pk).exists())


class VisitCRUDTests(TestCase):

    def test_create_get(self):
        resp = self.client.get(reverse("healthcare:visit_create"))
        self.assertEqual(resp.status_code, 200)

    def test_create_post(self):
        resp = self.client.post(reverse("healthcare:visit_create"), {
            "date": "2025-07-01",
            "visit_type": "routine",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Visit.objects.filter(visit_type="routine").exists())

    def test_detail(self):
        v = Visit.objects.create(date=date.today(), visit_type="urgent", reason="Fever")
        resp = self.client.get(reverse("healthcare:visit_detail", args=[v.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_update_post(self):
        v = Visit.objects.create(date=date.today(), visit_type="routine")
        resp = self.client.post(reverse("healthcare:visit_edit", args=[v.pk]), {
            "date": "2025-08-01",
            "visit_type": "follow_up",
        })
        self.assertEqual(resp.status_code, 302)
        v.refresh_from_db()
        self.assertEqual(v.visit_type, "follow_up")

    def test_delete(self):
        v = Visit.objects.create(date=date.today())
        resp = self.client.post(reverse("healthcare:visit_delete", args=[v.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Visit.objects.filter(pk=v.pk).exists())


class AdviceCRUDTests(TestCase):

    def test_create_get(self):
        resp = self.client.get(reverse("healthcare:advice_create"))
        self.assertEqual(resp.status_code, 200)

    def test_create_post(self):
        resp = self.client.post(reverse("healthcare:advice_create"), {
            "title": "Eat greens",
            "advice_text": "Eat leafy greens daily.",
            "date": "2025-07-01",
            "category": "diet",
            "status": "active",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Advice.objects.filter(title="Eat greens").exists())

    def test_detail(self):
        a = Advice.objects.create(title="Exercise", advice_text="Walk more", date=date.today())
        resp = self.client.get(reverse("healthcare:advice_detail", args=[a.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_update_post(self):
        a = Advice.objects.create(title="Old Title", advice_text="Text", date=date.today())
        resp = self.client.post(reverse("healthcare:advice_edit", args=[a.pk]), {
            "title": "New Title",
            "advice_text": "New text",
            "date": "2025-08-01",
            "category": "exercise",
            "status": "active",
        })
        self.assertEqual(resp.status_code, 302)
        a.refresh_from_db()
        self.assertEqual(a.title, "New Title")

    def test_delete(self):
        a = Advice.objects.create(title="Delete Me", advice_text="x", date=date.today())
        resp = self.client.post(reverse("healthcare:advice_delete", args=[a.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Advice.objects.filter(pk=a.pk).exists())


class AppointmentCRUDTests(HealthcareTestMixin, TestCase):

    def test_create_get(self):
        resp = self.client.get(reverse("healthcare:appointment_create"))
        self.assertEqual(resp.status_code, 200)

    def test_create_post(self):
        resp = self.client.post(reverse("healthcare:appointment_create"), {
            "title": "Checkup",
            "date": "2025-09-01",
            "visit_type": "routine",
            "status": "scheduled",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Appointment.objects.filter(title="Checkup").exists())

    def test_create_with_query_params(self):
        resp = self.client.get(reverse("healthcare:appointment_create") + "?date=2025-10-15&time=14:00")
        self.assertEqual(resp.status_code, 200)

    def test_detail(self):
        a = Appointment.objects.create(title="Eye Exam", date=date.today())
        resp = self.client.get(reverse("healthcare:appointment_detail", args=[a.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Eye Exam")

    def test_update_post(self):
        a = Appointment.objects.create(title="Old Appt", date=date.today())
        resp = self.client.post(reverse("healthcare:appointment_edit", args=[a.pk]), {
            "title": "Updated Appt",
            "date": "2025-09-15",
            "visit_type": "follow_up",
            "status": "confirmed",
        })
        self.assertEqual(resp.status_code, 302)
        a.refresh_from_db()
        self.assertEqual(a.title, "Updated Appt")

    def test_delete(self):
        a = Appointment.objects.create(title="Delete Appt", date=date.today())
        resp = self.client.post(reverse("healthcare:appointment_delete", args=[a.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Appointment.objects.filter(pk=a.pk).exists())


# ===========================================================================
# 5. Inline Status Update Tests
# ===========================================================================

class InlineStatusUpdateTests(HealthcareTestMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.provider = Provider.objects.create(name="Dr. Status")
        self.rx = Prescription.objects.create(medication_name="StatusMed")
        self.supplement = Supplement.objects.create(name="StatusSupp")
        self.testresult = TestResult.objects.create(test_name="StatusTest", date=date.today())
        self.advice = Advice.objects.create(title="StatusAdv", advice_text="x", date=date.today())
        self.appointment = Appointment.objects.create(title="StatusAppt", date=date.today())
        self.condition = Condition.objects.create(name="StatusCond")

    def test_provider_status_update(self):
        resp = self.client.post(
            reverse("healthcare:provider_inline_status", args=[self.provider.pk]),
            {"status": "inactive"},
        )
        self.assertEqual(resp.status_code, 200)
        self.provider.refresh_from_db()
        self.assertEqual(self.provider.status, "inactive")

    def test_provider_status_invalid(self):
        resp = self.client.post(
            reverse("healthcare:provider_inline_status", args=[self.provider.pk]),
            {"status": "bogus"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_prescription_status_update(self):
        resp = self.client.post(
            reverse("healthcare:prescription_inline_status", args=[self.rx.pk]),
            {"status": "completed"},
        )
        self.assertEqual(resp.status_code, 200)
        self.rx.refresh_from_db()
        self.assertEqual(self.rx.status, "completed")

    def test_supplement_status_update(self):
        resp = self.client.post(
            reverse("healthcare:supplement_inline_status", args=[self.supplement.pk]),
            {"status": "paused"},
        )
        self.assertEqual(resp.status_code, 200)
        self.supplement.refresh_from_db()
        self.assertEqual(self.supplement.status, "paused")

    def test_testresult_status_update(self):
        resp = self.client.post(
            reverse("healthcare:testresult_inline_status", args=[self.testresult.pk]),
            {"status": "normal"},
        )
        self.assertEqual(resp.status_code, 200)
        self.testresult.refresh_from_db()
        self.assertEqual(self.testresult.status, "normal")

    def test_advice_status_update(self):
        resp = self.client.post(
            reverse("healthcare:advice_inline_status", args=[self.advice.pk]),
            {"status": "archived"},
        )
        self.assertEqual(resp.status_code, 200)
        self.advice.refresh_from_db()
        self.assertEqual(self.advice.status, "archived")

    def test_appointment_status_update(self):
        resp = self.client.post(
            reverse("healthcare:appointment_inline_status", args=[self.appointment.pk]),
            {"status": "confirmed"},
        )
        self.assertEqual(resp.status_code, 200)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, "confirmed")

    def test_condition_status_update(self):
        resp = self.client.post(
            reverse("healthcare:condition_inline_status", args=[self.condition.pk]),
            {"status": "resolved"},
        )
        self.assertEqual(resp.status_code, 200)
        self.condition.refresh_from_db()
        self.assertEqual(self.condition.status, "resolved")


# ===========================================================================
# 6. CSV Export Tests
# ===========================================================================

class CSVExportTests(HealthcareTestMixin, TestCase):

    def setUp(self):
        super().setUp()
        Provider.objects.create(name="CSV Provider")
        Prescription.objects.create(medication_name="CSV Med")
        Supplement.objects.create(name="CSV Supp")
        TestResult.objects.create(test_name="CSV Test", date=date.today())
        Visit.objects.create(date=date.today(), visit_type="routine")
        Advice.objects.create(title="CSV Advice", advice_text="x", date=date.today())
        Appointment.objects.create(title="CSV Appt", date=date.today())
        Condition.objects.create(name="CSV Cond")

    def test_provider_csv(self):
        resp = self.client.get(reverse("healthcare:provider_export_csv"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("CSV Provider", resp.content.decode())

    def test_prescription_csv(self):
        resp = self.client.get(reverse("healthcare:prescription_export_csv"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("CSV Med", resp.content.decode())

    def test_supplement_csv(self):
        resp = self.client.get(reverse("healthcare:supplement_export_csv"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("CSV Supp", resp.content.decode())

    def test_testresult_csv(self):
        resp = self.client.get(reverse("healthcare:testresult_export_csv"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("CSV Test", resp.content.decode())

    def test_visit_csv(self):
        resp = self.client.get(reverse("healthcare:visit_export_csv"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")

    def test_advice_csv(self):
        resp = self.client.get(reverse("healthcare:advice_export_csv"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("CSV Advice", resp.content.decode())

    def test_appointment_csv(self):
        resp = self.client.get(reverse("healthcare:appointment_export_csv"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("CSV Appt", resp.content.decode())

    def test_condition_csv(self):
        resp = self.client.get(reverse("healthcare:condition_export_csv"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("CSV Cond", resp.content.decode())


# ===========================================================================
# 7. PDF Export Tests
# ===========================================================================

class PDFExportTests(HealthcareTestMixin, TestCase):

    def test_provider_pdf(self):
        p = Provider.objects.create(name="PDF Provider", notes_text="Some notes")
        resp = self.client.get(reverse("healthcare:provider_export_pdf", args=[p.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_prescription_pdf(self):
        rx = Prescription.objects.create(
            medication_name="PDF Med", purpose="Pain relief", notes_text="Internal note",
        )
        resp = self.client.get(reverse("healthcare:prescription_export_pdf", args=[rx.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_appointment_pdf(self):
        a = Appointment.objects.create(
            title="PDF Appt", date=date(2025, 9, 1), time=time(10, 0),
            duration_minutes=30, purpose="Follow up", preparation="Fasting",
            notes_text="Bring records",
        )
        resp = self.client.get(reverse("healthcare:appointment_export_pdf", args=[a.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_pdf_404_for_missing(self):
        resp = self.client.get(reverse("healthcare:provider_export_pdf", args=[99999]))
        self.assertEqual(resp.status_code, 404)


# ===========================================================================
# 8. Bulk Delete Tests
# ===========================================================================

class BulkDeleteTests(TestCase):

    def test_bulk_delete_provider_confirm(self):
        p1 = Provider.objects.create(name="Bulk1")
        p2 = Provider.objects.create(name="Bulk2")
        resp = self.client.post(
            reverse("healthcare:bulk_delete_provider"),
            {"selected": [p1.pk, p2.pk]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "2")

    def test_bulk_delete_provider_confirmed(self):
        p1 = Provider.objects.create(name="Bulk1")
        p2 = Provider.objects.create(name="Bulk2")
        resp = self.client.post(
            reverse("healthcare:bulk_delete_provider"),
            {"selected": [p1.pk, p2.pk], "confirm": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Provider.objects.count(), 0)

    def test_bulk_delete_prescription(self):
        rx = Prescription.objects.create(medication_name="BulkRx")
        resp = self.client.post(
            reverse("healthcare:bulk_delete_prescription"),
            {"selected": [rx.pk], "confirm": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Prescription.objects.filter(pk=rx.pk).exists())

    def test_bulk_delete_appointment(self):
        a = Appointment.objects.create(title="BulkAppt", date=date.today())
        resp = self.client.post(
            reverse("healthcare:bulk_delete_appointment"),
            {"selected": [a.pk], "confirm": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Appointment.objects.filter(pk=a.pk).exists())

    def test_bulk_delete_condition(self):
        c = Condition.objects.create(name="BulkCond")
        resp = self.client.post(
            reverse("healthcare:bulk_delete_condition"),
            {"selected": [c.pk], "confirm": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Condition.objects.filter(pk=c.pk).exists())

    def test_bulk_delete_supplement(self):
        s = Supplement.objects.create(name="BulkSupp")
        resp = self.client.post(
            reverse("healthcare:bulk_delete_supplement"),
            {"selected": [s.pk], "confirm": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Supplement.objects.filter(pk=s.pk).exists())

    def test_bulk_delete_testresult(self):
        tr = TestResult.objects.create(test_name="BulkTest", date=date.today())
        resp = self.client.post(
            reverse("healthcare:bulk_delete_testresult"),
            {"selected": [tr.pk], "confirm": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(TestResult.objects.filter(pk=tr.pk).exists())

    def test_bulk_delete_visit(self):
        v = Visit.objects.create(date=date.today())
        resp = self.client.post(
            reverse("healthcare:bulk_delete_visit"),
            {"selected": [v.pk], "confirm": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Visit.objects.filter(pk=v.pk).exists())

    def test_bulk_delete_advice(self):
        a = Advice.objects.create(title="BulkAdv", advice_text="x", date=date.today())
        resp = self.client.post(
            reverse("healthcare:bulk_delete_advice"),
            {"selected": [a.pk], "confirm": "1"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Advice.objects.filter(pk=a.pk).exists())


# ===========================================================================
# 9. Internal Notes Editing Tests
# ===========================================================================

class InternalNotesTests(TestCase):

    def setUp(self):
        self.provider = Provider.objects.create(name="Notes Provider")
        self.rx = Prescription.objects.create(medication_name="NotesRx")
        self.supplement = Supplement.objects.create(name="NotesSupp")
        self.testresult = TestResult.objects.create(test_name="NotesTest", date=date.today())
        self.visit = Visit.objects.create(date=date.today())
        self.advice = Advice.objects.create(title="NotesAdv", advice_text="x", date=date.today())
        self.appointment = Appointment.objects.create(title="NotesAppt", date=date.today())
        self.condition = Condition.objects.create(name="NotesCond")

    def test_provider_get_editor(self):
        resp = self.client.get(reverse("healthcare:provider_internal_notes", args=[self.provider.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_provider_get_display(self):
        resp = self.client.get(
            reverse("healthcare:provider_internal_notes", args=[self.provider.pk]),
            {"display": "1"},
        )
        self.assertEqual(resp.status_code, 200)

    def test_provider_post_save(self):
        resp = self.client.post(
            reverse("healthcare:provider_internal_notes", args=[self.provider.pk]),
            {"notes_text": "Updated internal notes"},
        )
        self.assertEqual(resp.status_code, 200)
        self.provider.refresh_from_db()
        self.assertEqual(self.provider.notes_text, "Updated internal notes")

    def test_prescription_internal_notes(self):
        resp = self.client.post(
            reverse("healthcare:prescription_internal_notes", args=[self.rx.pk]),
            {"notes_text": "Rx notes"},
        )
        self.assertEqual(resp.status_code, 200)
        self.rx.refresh_from_db()
        self.assertEqual(self.rx.notes_text, "Rx notes")

    def test_supplement_internal_notes(self):
        resp = self.client.post(
            reverse("healthcare:supplement_internal_notes", args=[self.supplement.pk]),
            {"notes_text": "Supp notes"},
        )
        self.assertEqual(resp.status_code, 200)
        self.supplement.refresh_from_db()
        self.assertEqual(self.supplement.notes_text, "Supp notes")

    def test_testresult_internal_notes(self):
        resp = self.client.post(
            reverse("healthcare:testresult_internal_notes", args=[self.testresult.pk]),
            {"notes_text": "Test notes"},
        )
        self.assertEqual(resp.status_code, 200)
        self.testresult.refresh_from_db()
        self.assertEqual(self.testresult.notes_text, "Test notes")

    def test_visit_internal_notes(self):
        resp = self.client.post(
            reverse("healthcare:visit_internal_notes", args=[self.visit.pk]),
            {"notes_text": "Visit notes"},
        )
        self.assertEqual(resp.status_code, 200)
        self.visit.refresh_from_db()
        self.assertEqual(self.visit.notes_text, "Visit notes")

    def test_advice_internal_notes(self):
        resp = self.client.post(
            reverse("healthcare:advice_internal_notes", args=[self.advice.pk]),
            {"notes_text": "Advice notes"},
        )
        self.assertEqual(resp.status_code, 200)
        self.advice.refresh_from_db()
        self.assertEqual(self.advice.notes_text, "Advice notes")

    def test_appointment_internal_notes(self):
        resp = self.client.post(
            reverse("healthcare:appointment_internal_notes", args=[self.appointment.pk]),
            {"notes_text": "Appt notes"},
        )
        self.assertEqual(resp.status_code, 200)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.notes_text, "Appt notes")

    def test_condition_internal_notes(self):
        resp = self.client.post(
            reverse("healthcare:condition_internal_notes", args=[self.condition.pk]),
            {"notes_text": "Cond notes"},
        )
        self.assertEqual(resp.status_code, 200)
        self.condition.refresh_from_db()
        self.assertEqual(self.condition.notes_text, "Cond notes")

    def test_internal_notes_strips_whitespace(self):
        resp = self.client.post(
            reverse("healthcare:provider_internal_notes", args=[self.provider.pk]),
            {"notes_text": "  trimmed  "},
        )
        self.provider.refresh_from_db()
        self.assertEqual(self.provider.notes_text, "trimmed")


# ===========================================================================
# 10. Tab Settings Tests
# ===========================================================================

class TabSettingsTests(TestCase):

    def test_tab_settings_page(self):
        resp = self.client.get(reverse("healthcare:healthcare_tab_settings"))
        self.assertEqual(resp.status_code, 200)

    def test_tab_add_get(self):
        resp = self.client.get(reverse("healthcare:healthcare_tab_add"))
        self.assertEqual(resp.status_code, 200)

    def test_tab_add_post(self):
        resp = self.client.post(reverse("healthcare:healthcare_tab_add"), {
            "label": "New Tab",
            "healthcare_types": ["providers", "prescriptions"],
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(HealthcareTab.objects.filter(label="New Tab").exists())

    def test_tab_edit_get(self):
        tab = HealthcareTab.objects.create(label="Editable", healthcare_types=["providers"])
        resp = self.client.get(reverse("healthcare:healthcare_tab_edit", args=[tab.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_tab_edit_post(self):
        tab = HealthcareTab.objects.create(label="Old Tab", healthcare_types=["providers"])
        resp = self.client.post(reverse("healthcare:healthcare_tab_edit", args=[tab.pk]), {
            "label": "Renamed Tab",
            "healthcare_types": ["visits"],
        })
        self.assertEqual(resp.status_code, 200)
        tab.refresh_from_db()
        self.assertEqual(tab.label, "Renamed Tab")

    def test_tab_edit_builtin_forbidden(self):
        tab = HealthcareTab.objects.create(
            label="Builtin", healthcare_types=["providers"], is_builtin=True,
        )
        resp = self.client.get(reverse("healthcare:healthcare_tab_edit", args=[tab.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_tab_delete_post(self):
        tab = HealthcareTab.objects.create(label="Del Tab", healthcare_types=["providers"])
        resp = self.client.post(reverse("healthcare:healthcare_tab_delete", args=[tab.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(HealthcareTab.objects.filter(pk=tab.pk).exists())

    def test_tab_delete_builtin_forbidden(self):
        tab = HealthcareTab.objects.create(
            label="Builtin Del", healthcare_types=["providers"], is_builtin=True,
        )
        resp = self.client.post(reverse("healthcare:healthcare_tab_delete", args=[tab.pk]))
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(HealthcareTab.objects.filter(pk=tab.pk).exists())


# ===========================================================================
# 11. Note Link/Unlink Tests
# ===========================================================================

class NoteLinkUnlinkTests(TestCase):

    def setUp(self):
        from notes.models import Note
        self.note = Note.objects.create(
            title="Test Note", content="Content", date=timezone.now(),
        )
        self.provider = Provider.objects.create(name="NoteProvider")
        self.rx = Prescription.objects.create(medication_name="NoteRx")
        self.appointment = Appointment.objects.create(title="NoteAppt", date=date.today())
        self.visit = Visit.objects.create(date=date.today())
        self.condition = Condition.objects.create(name="NoteCond")

    def test_provider_note_link_get(self):
        resp = self.client.get(reverse("healthcare:provider_note_link", args=[self.provider.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_provider_note_link_post(self):
        resp = self.client.post(
            reverse("healthcare:provider_note_link", args=[self.provider.pk]),
            {"note": self.note.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.provider, self.note.related_providers.all())

    def test_provider_note_unlink(self):
        self.note.related_providers.add(self.provider)
        resp = self.client.post(
            reverse("healthcare:provider_note_unlink", args=[self.provider.pk, self.note.pk]),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(self.provider, self.note.related_providers.all())

    def test_prescription_note_link(self):
        resp = self.client.post(
            reverse("healthcare:prescription_note_link", args=[self.rx.pk]),
            {"note": self.note.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.rx, self.note.related_prescriptions.all())

    def test_prescription_note_unlink(self):
        self.note.related_prescriptions.add(self.rx)
        resp = self.client.post(
            reverse("healthcare:prescription_note_unlink", args=[self.rx.pk, self.note.pk]),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(self.rx, self.note.related_prescriptions.all())

    def test_appointment_note_link(self):
        resp = self.client.post(
            reverse("healthcare:appointment_note_link", args=[self.appointment.pk]),
            {"note": self.note.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.appointment, self.note.related_appointments.all())

    def test_appointment_note_unlink(self):
        self.note.related_appointments.add(self.appointment)
        resp = self.client.post(
            reverse("healthcare:appointment_note_unlink", args=[self.appointment.pk, self.note.pk]),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(self.appointment, self.note.related_appointments.all())

    def test_visit_note_link(self):
        resp = self.client.post(
            reverse("healthcare:visit_note_link", args=[self.visit.pk]),
            {"note": self.note.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.visit, self.note.related_visits.all())

    def test_visit_note_unlink(self):
        self.note.related_visits.add(self.visit)
        resp = self.client.post(
            reverse("healthcare:visit_note_unlink", args=[self.visit.pk, self.note.pk]),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(self.visit, self.note.related_visits.all())

    def test_condition_note_link(self):
        resp = self.client.post(
            reverse("healthcare:condition_note_link", args=[self.condition.pk]),
            {"note": self.note.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.condition, self.note.related_conditions.all())

    def test_condition_note_unlink(self):
        self.note.related_conditions.add(self.condition)
        resp = self.client.post(
            reverse("healthcare:condition_note_unlink", args=[self.condition.pk, self.note.pk]),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(self.condition, self.note.related_conditions.all())


# ===========================================================================
# 12. Legal Link/Unlink Tests
# ===========================================================================

class LegalLinkUnlinkTests(TestCase):

    def setUp(self):
        from legal.models import LegalMatter
        self.matter = LegalMatter.objects.create(title="Test Case", status="active")
        self.provider = Provider.objects.create(name="LegalProvider")
        self.rx = Prescription.objects.create(medication_name="LegalRx")
        self.condition = Condition.objects.create(name="LegalCond")

    def test_provider_legal_link_get(self):
        resp = self.client.get(reverse("healthcare:provider_legal_link", args=[self.provider.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_provider_legal_link_post(self):
        resp = self.client.post(
            reverse("healthcare:provider_legal_link", args=[self.provider.pk]),
            {"legal_matter": self.matter.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.provider, self.matter.related_providers.all())

    def test_provider_legal_unlink(self):
        self.matter.related_providers.add(self.provider)
        resp = self.client.post(
            reverse("healthcare:provider_legal_unlink", args=[self.provider.pk, self.matter.pk]),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(self.provider, self.matter.related_providers.all())

    def test_prescription_legal_link(self):
        resp = self.client.post(
            reverse("healthcare:prescription_legal_link", args=[self.rx.pk]),
            {"legal_matter": self.matter.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.rx, self.matter.related_prescriptions.all())

    def test_prescription_legal_unlink(self):
        self.matter.related_prescriptions.add(self.rx)
        resp = self.client.post(
            reverse("healthcare:prescription_legal_unlink", args=[self.rx.pk, self.matter.pk]),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(self.rx, self.matter.related_prescriptions.all())

    def test_condition_legal_link(self):
        resp = self.client.post(
            reverse("healthcare:condition_legal_link", args=[self.condition.pk]),
            {"legal_matter": self.matter.pk},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.condition, self.matter.related_conditions.all())

    def test_condition_legal_unlink(self):
        self.matter.related_conditions.add(self.condition)
        resp = self.client.post(
            reverse("healthcare:condition_legal_unlink", args=[self.condition.pk, self.matter.pk]),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(self.condition, self.matter.related_conditions.all())


# ===========================================================================
# 13. Global Search Integration Tests
# ===========================================================================

class GlobalSearchTests(TestCase):

    def setUp(self):
        self.provider = Provider.objects.create(
            name="Dr. Searchable", specialty="Cardiology", practice_name="Heart Clinic",
        )
        self.rx = Prescription.objects.create(
            medication_name="SearchMed", generic_name="GenericSearch",
        )
        self.appointment = Appointment.objects.create(
            title="Search Appointment", date=date.today(), purpose="Search purpose",
        )

    def test_search_finds_provider_by_name(self):
        resp = self.client.get(reverse("dashboard:search"), {"q": "Searchable"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.provider, resp.context["hc_providers"])

    def test_search_finds_provider_by_specialty(self):
        resp = self.client.get(reverse("dashboard:search"), {"q": "Cardiology"})
        self.assertIn(self.provider, resp.context["hc_providers"])

    def test_search_finds_provider_by_practice(self):
        resp = self.client.get(reverse("dashboard:search"), {"q": "Heart Clinic"})
        self.assertIn(self.provider, resp.context["hc_providers"])

    def test_search_finds_prescription_by_name(self):
        resp = self.client.get(reverse("dashboard:search"), {"q": "SearchMed"})
        self.assertIn(self.rx, resp.context["hc_prescriptions"])

    def test_search_finds_prescription_by_generic(self):
        resp = self.client.get(reverse("dashboard:search"), {"q": "GenericSearch"})
        self.assertIn(self.rx, resp.context["hc_prescriptions"])

    def test_search_finds_appointment_by_title(self):
        resp = self.client.get(reverse("dashboard:search"), {"q": "Search Appointment"})
        self.assertIn(self.appointment, resp.context["hc_appointments"])

    def test_search_finds_appointment_by_purpose(self):
        resp = self.client.get(reverse("dashboard:search"), {"q": "Search purpose"})
        self.assertIn(self.appointment, resp.context["hc_appointments"])

    def test_search_no_results(self):
        resp = self.client.get(reverse("dashboard:search"), {"q": "zzznomatch"})
        self.assertEqual(len(resp.context["hc_providers"]), 0)
        self.assertEqual(len(resp.context["hc_prescriptions"]), 0)
        self.assertEqual(len(resp.context["hc_appointments"]), 0)

    def test_search_has_results_flag(self):
        resp = self.client.get(reverse("dashboard:search"), {"q": "Searchable"})
        self.assertTrue(resp.context["has_results"])


# ===========================================================================
# 14. Calendar Events Integration Tests
# ===========================================================================

class CalendarEventsTests(TestCase):

    def test_appointment_appears_in_calendar(self):
        appt = Appointment.objects.create(
            title="Calendar Appt", date=date.today(), status="scheduled",
        )
        resp = self.client.get(reverse("dashboard:calendar_events"))
        self.assertEqual(resp.status_code, 200)
        events = json.loads(resp.content)
        titles = [e["title"] for e in events]
        self.assertIn("Calendar Appt", titles)

    def test_cancelled_appointment_excluded(self):
        Appointment.objects.create(
            title="Cancelled Appt", date=date.today(), status="cancelled",
        )
        resp = self.client.get(reverse("dashboard:calendar_events"))
        events = json.loads(resp.content)
        titles = [e["title"] for e in events]
        self.assertNotIn("Cancelled Appt", titles)

    def test_completed_appointment_excluded(self):
        Appointment.objects.create(
            title="Done Appt", date=date.today(), status="completed",
        )
        resp = self.client.get(reverse("dashboard:calendar_events"))
        events = json.loads(resp.content)
        titles = [e["title"] for e in events]
        self.assertNotIn("Done Appt", titles)

    def test_appointment_with_time_is_timed_event(self):
        Appointment.objects.create(
            title="Timed Appt", date=date.today(),
            time=time(14, 0), status="scheduled",
        )
        resp = self.client.get(reverse("dashboard:calendar_events"))
        events = json.loads(resp.content)
        timed = [e for e in events if e["title"] == "Timed Appt"]
        self.assertEqual(len(timed), 1)
        self.assertFalse(timed[0].get("allDay", True))

    def test_refill_appears_in_calendar(self):
        Prescription.objects.create(
            medication_name="RefillMed", status="active",
            next_refill_date=date.today(),
        )
        resp = self.client.get(reverse("dashboard:calendar_events"))
        events = json.loads(resp.content)
        titles = [e["title"] for e in events]
        self.assertIn("Refill: RefillMed", titles)

    def test_refill_inactive_excluded(self):
        Prescription.objects.create(
            medication_name="InactiveMed", status="discontinued",
            next_refill_date=date.today(),
        )
        resp = self.client.get(reverse("dashboard:calendar_events"))
        events = json.loads(resp.content)
        titles = [e["title"] for e in events]
        self.assertNotIn("Refill: InactiveMed", titles)

    def test_calendar_event_color(self):
        Appointment.objects.create(
            title="Color Check", date=date.today(), status="scheduled",
        )
        resp = self.client.get(reverse("dashboard:calendar_events"))
        events = json.loads(resp.content)
        appt_events = [e for e in events if e["title"] == "Color Check"]
        self.assertEqual(appt_events[0]["color"], "#14b8a6")

    def test_refill_event_color(self):
        Prescription.objects.create(
            medication_name="ColorRx", status="active",
            next_refill_date=date.today(),
        )
        resp = self.client.get(reverse("dashboard:calendar_events"))
        events = json.loads(resp.content)
        refill_events = [e for e in events if e["title"] == "Refill: ColorRx"]
        self.assertEqual(refill_events[0]["color"], "#f59e0b")


# ===========================================================================
# 15. Dashboard Healthcare Summary Tests
# ===========================================================================

class DashboardHealthcareSummaryTests(TestCase):

    def test_dashboard_shows_upcoming_appointments(self):
        Appointment.objects.create(
            title="Soon Appt", date=timezone.localdate() + timedelta(days=3),
            status="scheduled",
        )
        resp = self.client.get(reverse("dashboard:index"))
        self.assertEqual(resp.status_code, 200)
        appts = resp.context["upcoming_appointments"]
        titles = [a.title for a in appts]
        self.assertIn("Soon Appt", titles)

    def test_dashboard_excludes_far_appointments(self):
        Appointment.objects.create(
            title="Far Appt", date=timezone.localdate() + timedelta(days=30),
            status="scheduled",
        )
        resp = self.client.get(reverse("dashboard:index"))
        appts = resp.context["upcoming_appointments"]
        titles = [a.title for a in appts]
        self.assertNotIn("Far Appt", titles)

    def test_dashboard_excludes_cancelled_appointments(self):
        Appointment.objects.create(
            title="Cancelled Summary", date=timezone.localdate() + timedelta(days=2),
            status="cancelled",
        )
        resp = self.client.get(reverse("dashboard:index"))
        appts = resp.context["upcoming_appointments"]
        titles = [a.title for a in appts]
        self.assertNotIn("Cancelled Summary", titles)

    def test_dashboard_active_prescription_count(self):
        Prescription.objects.create(medication_name="Active1", status="active")
        Prescription.objects.create(medication_name="Active2", status="active")
        Prescription.objects.create(medication_name="Stopped", status="discontinued")
        resp = self.client.get(reverse("dashboard:index"))
        self.assertEqual(resp.context["active_prescriptions_count"], 2)

    def test_dashboard_overdue_refills(self):
        Prescription.objects.create(
            medication_name="Overdue1", status="active",
            next_refill_date=timezone.localdate() - timedelta(days=1),
        )
        Prescription.objects.create(
            medication_name="NotDue", status="active",
            next_refill_date=timezone.localdate() + timedelta(days=10),
        )
        resp = self.client.get(reverse("dashboard:index"))
        self.assertEqual(resp.context["overdue_refills"], 1)

    def test_dashboard_appointment_in_deadlines(self):
        Appointment.objects.create(
            title="Deadline Appt", date=timezone.localdate() + timedelta(days=5),
            status="scheduled",
        )
        resp = self.client.get(reverse("dashboard:index"))
        deadlines = resp.context["upcoming_deadlines"]
        deadline_titles = [d["title"] for d in deadlines]
        self.assertTrue(any("Deadline Appt" in t for t in deadline_titles))


# ===========================================================================
# 16. Provider Detail Context Tests
# ===========================================================================

class ProviderDetailContextTests(TestCase):

    def setUp(self):
        self.provider = Provider.objects.create(name="Dr. Context")
        self.condition = Condition.objects.create(
            name="Test Condition", diagnosed_by=self.provider,
        )
        self.rx = Prescription.objects.create(
            medication_name="ContextMed", status="active",
            prescribing_provider=self.provider,
        )
        self.appt = Appointment.objects.create(
            title="Context Appt", date=date.today() + timedelta(days=5),
            status="scheduled", provider=self.provider,
        )
        self.visit = Visit.objects.create(
            date=date.today(), provider=self.provider,
        )
        self.testresult = TestResult.objects.create(
            test_name="Context Test", date=date.today(),
            ordering_provider=self.provider,
        )
        self.supplement = Supplement.objects.create(
            name="Context Supp", status="active",
            recommended_by=self.provider,
        )
        self.advice_obj = Advice.objects.create(
            title="Context Advice", advice_text="text", date=date.today(),
            status="active", given_by=self.provider,
        )

    def test_detail_includes_prescriptions(self):
        resp = self.client.get(reverse("healthcare:provider_detail", args=[self.provider.pk]))
        self.assertIn(self.rx, resp.context["prescriptions"])

    def test_detail_includes_appointments(self):
        resp = self.client.get(reverse("healthcare:provider_detail", args=[self.provider.pk]))
        self.assertIn(self.appt, resp.context["appointments"])

    def test_detail_includes_conditions(self):
        resp = self.client.get(reverse("healthcare:provider_detail", args=[self.provider.pk]))
        self.assertIn(self.condition, resp.context["conditions"])

    def test_detail_includes_visits(self):
        resp = self.client.get(reverse("healthcare:provider_detail", args=[self.provider.pk]))
        self.assertIn(self.visit, resp.context["visits"])

    def test_detail_includes_test_results(self):
        resp = self.client.get(reverse("healthcare:provider_detail", args=[self.provider.pk]))
        self.assertIn(self.testresult, resp.context["test_results"])

    def test_detail_includes_supplements(self):
        resp = self.client.get(reverse("healthcare:provider_detail", args=[self.provider.pk]))
        self.assertIn(self.supplement, resp.context["supplements"])

    def test_detail_includes_advice(self):
        resp = self.client.get(reverse("healthcare:provider_detail", args=[self.provider.pk]))
        self.assertIn(self.advice_obj, resp.context["advice"])


# ===========================================================================
# 17. Condition Detail Context Tests
# ===========================================================================

class ConditionDetailContextTests(TestCase):

    def setUp(self):
        self.condition = Condition.objects.create(name="Detail Condition")
        self.rx = Prescription.objects.create(
            medication_name="CondMed", related_condition=self.condition,
        )
        self.supplement = Supplement.objects.create(
            name="CondSupp", related_condition=self.condition,
        )
        self.visit = Visit.objects.create(
            date=date.today(), related_condition=self.condition,
        )
        self.advice_obj = Advice.objects.create(
            title="CondAdvice", advice_text="x", date=date.today(),
            related_condition=self.condition,
        )
        self.appt = Appointment.objects.create(
            title="CondAppt", date=date.today(),
            related_condition=self.condition,
        )

    def test_detail_includes_prescriptions(self):
        resp = self.client.get(reverse("healthcare:condition_detail", args=[self.condition.pk]))
        self.assertIn(self.rx, resp.context["prescriptions"])

    def test_detail_includes_supplements(self):
        resp = self.client.get(reverse("healthcare:condition_detail", args=[self.condition.pk]))
        self.assertIn(self.supplement, resp.context["supplements"])

    def test_detail_includes_visits(self):
        resp = self.client.get(reverse("healthcare:condition_detail", args=[self.condition.pk]))
        self.assertIn(self.visit, resp.context["visits"])

    def test_detail_includes_advice(self):
        resp = self.client.get(reverse("healthcare:condition_detail", args=[self.condition.pk]))
        self.assertIn(self.advice_obj, resp.context["advice"])

    def test_detail_includes_appointments(self):
        resp = self.client.get(reverse("healthcare:condition_detail", args=[self.condition.pk]))
        self.assertIn(self.appt, resp.context["appointments"])


# ===========================================================================
# 18. FK SET_NULL Behavior Tests
# ===========================================================================

class FKSetNullTests(TestCase):

    def test_prescription_provider_set_null(self):
        p = Provider.objects.create(name="Gone Dr")
        rx = Prescription.objects.create(
            medication_name="Orphan Med", prescribing_provider=p,
        )
        p.delete()
        rx.refresh_from_db()
        self.assertIsNone(rx.prescribing_provider)

    def test_condition_diagnosed_by_set_null(self):
        p = Provider.objects.create(name="Deleted Dr")
        c = Condition.objects.create(name="Orphan Cond", diagnosed_by=p)
        p.delete()
        c.refresh_from_db()
        self.assertIsNone(c.diagnosed_by)

    def test_visit_provider_set_null(self):
        p = Provider.objects.create(name="Leaving Dr")
        v = Visit.objects.create(date=date.today(), provider=p)
        p.delete()
        v.refresh_from_db()
        self.assertIsNone(v.provider)

    def test_supplement_condition_set_null(self):
        c = Condition.objects.create(name="Temp Cond")
        s = Supplement.objects.create(name="Supp", related_condition=c)
        c.delete()
        s.refresh_from_db()
        self.assertIsNone(s.related_condition)
