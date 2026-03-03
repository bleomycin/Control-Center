from collections import OrderedDict

from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import (AdviceForm, AppointmentForm, ConditionForm, HealthcareTabForm,
                     PrescriptionForm, ProviderForm, SupplementForm, TestResultForm,
                     VisitForm)
from .models import (Advice, Appointment, Condition, HealthcareTab, Prescription,
                     Provider, Supplement, TestResult, Visit)


# --- Healthcare Tab Config ---

def _get_healthcare_tab_config():
    """Build dynamic tab config from HealthcareTab + computed Other tab."""
    tabs = list(HealthcareTab.objects.all())
    all_types = {"providers", "prescriptions", "supplements", "test_results",
                 "visits", "advice", "appointments", "conditions"}

    claimed = set()
    for tab in tabs:
        if not tab.is_builtin:
            claimed.update(tab.healthcare_types)

    unclaimed = all_types - claimed

    counts = {
        "providers": Provider.objects.count(),
        "prescriptions": Prescription.objects.count(),
        "supplements": Supplement.objects.count(),
        "test_results": TestResult.objects.count(),
        "visits": Visit.objects.count(),
        "advice": Advice.objects.count(),
        "appointments": Appointment.objects.count(),
        "conditions": Condition.objects.count(),
    }

    result = []
    for tab in tabs:
        tab_count = sum(counts.get(t, 0) for t in tab.healthcare_types)
        result.append({
            "key": tab.key,
            "label": tab.label,
            "healthcare_types": tab.healthcare_types,
            "is_builtin": tab.is_builtin,
            "pk": tab.pk,
            "count": tab_count,
        })

    if unclaimed:
        tab_count = sum(counts.get(t, 0) for t in unclaimed)
        result.append({
            "key": "other",
            "label": "Other",
            "healthcare_types": sorted(unclaimed),
            "is_builtin": False,
            "pk": None,
            "count": tab_count,
        })

    return result, counts


# --- Unified Healthcare List ---

def healthcare_list(request):
    tabs, counts = _get_healthcare_tab_config()
    tab_key = request.GET.get("tab", "")
    valid_keys = {t["key"] for t in tabs}
    if tab_key not in valid_keys:
        tab_key = tabs[0]["key"] if tabs else "all"

    current_healthcare_types = []
    for t in tabs:
        if t["key"] == tab_key:
            current_healthcare_types = t["healthcare_types"]
            break

    q = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "")
    direction = "" if request.GET.get("dir") == "asc" else "-"

    ctx = {
        "tabs": tabs,
        "current_tab": tab_key,
        "current_healthcare_types": current_healthcare_types,
        "tab_counts": counts,
        "search_query": q,
        "current_sort": sort,
        "current_dir": request.GET.get("dir", ""),
        "total_count": sum(counts.values()),
    }

    if "providers" in current_healthcare_types:
        qs = Provider.objects.all()
        if q:
            qs = qs.filter(name__icontains=q)
        statuses = [s for s in request.GET.getlist("status") if s]
        if statuses:
            qs = qs.filter(status__in=statuses)
        if len(current_healthcare_types) == 1:
            ALLOWED_SORTS = {"name", "status", "specialty", "provider_type"}
            if sort in ALLOWED_SORTS:
                qs = qs.order_by(f"{direction}{sort}")
        ctx["providers"] = qs
        ctx["provider_status_choices"] = Provider.STATUS_CHOICES

    if "prescriptions" in current_healthcare_types:
        qs = Prescription.objects.select_related("prescribing_provider").all()
        if q:
            qs = qs.filter(medication_name__icontains=q)
        statuses = [s for s in request.GET.getlist("status") if s]
        if statuses:
            qs = qs.filter(status__in=statuses)
        if len(current_healthcare_types) == 1:
            ALLOWED_SORTS = {"medication_name", "status", "dosage", "next_refill_date"}
            if sort in ALLOWED_SORTS:
                qs = qs.order_by(f"{direction}{sort}")
        ctx["prescriptions"] = qs
        ctx["prescription_status_choices"] = Prescription.STATUS_CHOICES

    if "supplements" in current_healthcare_types:
        qs = Supplement.objects.select_related("recommended_by").all()
        if q:
            qs = qs.filter(name__icontains=q)
        statuses = [s for s in request.GET.getlist("status") if s]
        if statuses:
            qs = qs.filter(status__in=statuses)
        if len(current_healthcare_types) == 1:
            ALLOWED_SORTS = {"name", "status", "brand"}
            if sort in ALLOWED_SORTS:
                qs = qs.order_by(f"{direction}{sort}")
        ctx["supplements"] = qs
        ctx["supplement_status_choices"] = Supplement.STATUS_CHOICES

    if "test_results" in current_healthcare_types:
        qs = TestResult.objects.select_related("ordering_provider", "related_condition").all()
        if q:
            qs = qs.filter(test_name__icontains=q)
        statuses = [s for s in request.GET.getlist("status") if s]
        if statuses:
            qs = qs.filter(status__in=statuses)

        # Condition filter
        condition_filter = request.GET.get("condition_filter", "")
        if condition_filter == "routine":
            qs = qs.filter(related_condition__isnull=True)
        elif condition_filter.isdigit():
            qs = qs.filter(related_condition_id=int(condition_filter))

        if len(current_healthcare_types) == 1:
            ALLOWED_SORTS = {"test_name", "status", "date", "test_type"}
            if sort in ALLOWED_SORTS:
                qs = qs.order_by(f"{direction}{sort}")
        ctx["test_results"] = qs
        ctx["test_result_status_choices"] = TestResult.STATUS_CHOICES

        # Build condition-grouped data
        all_conditions = Condition.objects.all()
        ctx["all_conditions"] = all_conditions

        # Group test results by condition
        groups = OrderedDict()
        for tr in qs:
            cond = tr.related_condition
            if cond not in groups:
                groups[cond] = []
            groups[cond].append(tr)

        # Sort: active conditions first, then by name; None ("Routine Labs") last
        sorted_groups = []
        active_statuses = {"active", "monitoring"}
        cond_groups = [(c, results) for c, results in groups.items() if c is not None]
        cond_groups.sort(key=lambda x: (0 if x[0].status in active_statuses else 1, x[0].name))
        for cond, results in cond_groups:
            sorted_groups.append({"condition": cond, "results": results})
        if None in groups:
            sorted_groups.append({"condition": None, "results": groups[None]})

        ctx["test_result_groups"] = sorted_groups
        ctx["test_result_total"] = sum(len(g["results"]) for g in sorted_groups)
        ctx["condition_filter"] = condition_filter

    if "visits" in current_healthcare_types:
        qs = Visit.objects.select_related("provider").all()
        if q:
            qs = qs.filter(reason__icontains=q)
        if len(current_healthcare_types) == 1:
            ALLOWED_SORTS = {"date", "visit_type", "provider__name"}
            if sort in ALLOWED_SORTS:
                qs = qs.order_by(f"{direction}{sort}")
        ctx["visits"] = qs

    if "advice" in current_healthcare_types:
        qs = Advice.objects.select_related("given_by").all()
        if q:
            qs = qs.filter(title__icontains=q)
        statuses = [s for s in request.GET.getlist("status") if s]
        if statuses:
            qs = qs.filter(status__in=statuses)
        if len(current_healthcare_types) == 1:
            ALLOWED_SORTS = {"title", "status", "date", "category"}
            if sort in ALLOWED_SORTS:
                qs = qs.order_by(f"{direction}{sort}")
        ctx["advice_list"] = qs
        ctx["advice_status_choices"] = Advice.STATUS_CHOICES

    if "appointments" in current_healthcare_types:
        qs = Appointment.objects.select_related("provider").all()
        if q:
            qs = qs.filter(title__icontains=q)
        statuses = [s for s in request.GET.getlist("status") if s]
        if statuses:
            qs = qs.filter(status__in=statuses)
        if len(current_healthcare_types) == 1:
            ALLOWED_SORTS = {"title", "status", "date", "visit_type"}
            if sort in ALLOWED_SORTS:
                qs = qs.order_by(f"{direction}{sort}")
        ctx["appointments"] = qs
        ctx["appointment_status_choices"] = Appointment.STATUS_CHOICES

    if "conditions" in current_healthcare_types:
        qs = Condition.objects.select_related("diagnosed_by").all()
        if q:
            qs = qs.filter(name__icontains=q)
        statuses = [s for s in request.GET.getlist("status") if s]
        if statuses:
            qs = qs.filter(status__in=statuses)
        if len(current_healthcare_types) == 1:
            ALLOWED_SORTS = {"name", "status", "severity", "diagnosed_date"}
            if sort in ALLOWED_SORTS:
                qs = qs.order_by(f"{direction}{sort}")
        ctx["conditions"] = qs
        ctx["condition_status_choices"] = Condition.STATUS_CHOICES

    ctx["hide_checkboxes"] = len(current_healthcare_types) > 1

    if len(current_healthcare_types) == 1:
        htype = current_healthcare_types[0]
        if htype in ("providers", "prescriptions", "supplements", "test_results",
                     "appointments", "conditions", "advice"):
            ctx["status_choices"] = (
                ctx.get("provider_status_choices")
                or ctx.get("prescription_status_choices")
                or ctx.get("supplement_status_choices")
                or ctx.get("test_result_status_choices")
                or ctx.get("appointment_status_choices")
                or ctx.get("condition_status_choices")
                or ctx.get("advice_status_choices", [])
            )
            ctx["selected_statuses"] = [s for s in request.GET.getlist("status") if s]
            ctx["date_from"] = request.GET.get("date_from", "")
            ctx["date_to"] = request.GET.get("date_to", "")

    is_htmx = request.headers.get("HX-Request")
    if is_htmx:
        return render(request, "healthcare/partials/_healthcare_tab_content.html", ctx)
    return render(request, "healthcare/healthcare_list.html", ctx)


# --- Healthcare Tab Settings ---

def healthcare_tab_settings(request):
    tabs = HealthcareTab.objects.all()
    return render(request, "healthcare/healthcare_tab_settings.html", {"tabs": tabs})


def healthcare_tab_add(request):
    if request.method == "POST":
        form = HealthcareTabForm(request.POST)
        if form.is_valid():
            form.save()
            tabs = HealthcareTab.objects.all()
            return render(request, "healthcare/partials/_healthcare_tab_settings_list.html", {"tabs": tabs})
    else:
        form = HealthcareTabForm()
    return render(request, "healthcare/partials/_healthcare_tab_settings_form.html", {"form": form})


def healthcare_tab_edit(request, pk):
    tab = get_object_or_404(HealthcareTab, pk=pk)
    if tab.is_builtin:
        return HttpResponse(status=403)
    if request.method == "POST":
        form = HealthcareTabForm(request.POST, instance=tab)
        if form.is_valid():
            form.save()
            tabs = HealthcareTab.objects.all()
            return render(request, "healthcare/partials/_healthcare_tab_settings_list.html", {"tabs": tabs})
    else:
        form = HealthcareTabForm(instance=tab)
    return render(request, "healthcare/partials/_healthcare_tab_settings_form.html", {
        "form": form,
        "form_url": reverse("healthcare:healthcare_tab_edit", args=[pk]),
        "edit_mode": True,
    })


def healthcare_tab_delete(request, pk):
    tab = get_object_or_404(HealthcareTab, pk=pk)
    if tab.is_builtin:
        return HttpResponse(status=403)
    if request.method == "POST":
        tab.delete()
    tabs = HealthcareTab.objects.all()
    return render(request, "healthcare/partials/_healthcare_tab_settings_list.html", {"tabs": tabs})


# --- Inline Status Updates ---

def _inline_update_status(request, model_class, pk, template, context_name, choices):
    obj = get_object_or_404(model_class, pk=pk)
    status = request.POST.get("status", "")
    valid = [s[0] for s in choices]
    if status not in valid:
        return HttpResponseBadRequest("Invalid status")
    obj.status = status
    obj.save(update_fields=["status"])
    return render(request, template, {context_name: obj})


def inline_update_provider_status(request, pk):
    return _inline_update_status(
        request, Provider, pk, "healthcare/partials/_provider_row.html",
        "provider", Provider.STATUS_CHOICES)


def inline_update_prescription_status(request, pk):
    return _inline_update_status(
        request, Prescription, pk, "healthcare/partials/_prescription_row.html",
        "prescription", Prescription.STATUS_CHOICES)


def inline_update_supplement_status(request, pk):
    return _inline_update_status(
        request, Supplement, pk, "healthcare/partials/_supplement_row.html",
        "supplement", Supplement.STATUS_CHOICES)


def inline_update_testresult_status(request, pk):
    return _inline_update_status(
        request, TestResult, pk, "healthcare/partials/_testresult_row.html",
        "result", TestResult.STATUS_CHOICES)


def inline_update_advice_status(request, pk):
    return _inline_update_status(
        request, Advice, pk, "healthcare/partials/_advice_row.html",
        "adv", Advice.STATUS_CHOICES)


def inline_update_appointment_status(request, pk):
    return _inline_update_status(
        request, Appointment, pk, "healthcare/partials/_appointment_row.html",
        "appt", Appointment.STATUS_CHOICES)


def inline_update_condition_status(request, pk):
    return _inline_update_status(
        request, Condition, pk, "healthcare/partials/_condition_row.html",
        "condition", Condition.STATUS_CHOICES)


# --- CSV Exports ---

def export_provider_csv(request):
    from config.export import export_csv as do_export
    qs = Provider.objects.all()
    fields = [
        ("name", "Name"), ("provider_type", "Type"), ("specialty", "Specialty"),
        ("practice_name", "Practice"), ("phone", "Phone"), ("status", "Status"),
    ]
    return do_export(qs, fields, "providers")


def export_prescription_csv(request):
    from config.export import export_csv as do_export
    qs = Prescription.objects.all()
    fields = [
        ("medication_name", "Medication"), ("generic_name", "Generic"),
        ("dosage", "Dosage"), ("frequency", "Frequency"),
        ("rx_number", "Rx #"), ("status", "Status"),
    ]
    return do_export(qs, fields, "prescriptions")


def export_supplement_csv(request):
    from config.export import export_csv as do_export
    qs = Supplement.objects.all()
    fields = [
        ("name", "Name"), ("brand", "Brand"), ("dosage", "Dosage"),
        ("frequency", "Frequency"), ("status", "Status"),
    ]
    return do_export(qs, fields, "supplements")


def export_testresult_csv(request):
    from config.export import export_csv as do_export
    qs = TestResult.objects.all()
    fields = [
        ("test_name", "Test"), ("test_type", "Type"), ("date", "Date"),
        ("result_value", "Value"), ("reference_range", "Range"),
        ("status", "Status"),
    ]
    return do_export(qs, fields, "test_results")


def export_visit_csv(request):
    from config.export import export_csv as do_export
    qs = Visit.objects.all()
    fields = [
        ("date", "Date"), ("visit_type", "Type"), ("reason", "Reason"),
        ("diagnosis", "Diagnosis"), ("copay", "Copay"),
    ]
    return do_export(qs, fields, "visits")


def export_advice_csv(request):
    from config.export import export_csv as do_export
    qs = Advice.objects.all()
    fields = [
        ("title", "Title"), ("category", "Category"), ("date", "Date"),
        ("status", "Status"),
    ]
    return do_export(qs, fields, "advice")


def export_appointment_csv(request):
    from config.export import export_csv as do_export
    qs = Appointment.objects.all()
    fields = [
        ("title", "Title"), ("date", "Date"), ("time", "Time"),
        ("visit_type", "Type"), ("status", "Status"),
    ]
    return do_export(qs, fields, "appointments")


def export_condition_csv(request):
    from config.export import export_csv as do_export
    qs = Condition.objects.all()
    fields = [
        ("name", "Name"), ("icd_code", "ICD Code"), ("status", "Status"),
        ("severity", "Severity"), ("diagnosed_date", "Diagnosed"),
    ]
    return do_export(qs, fields, "conditions")


# --- PDF Exports ---

def export_pdf_provider_detail(request, pk):
    from config.pdf_export import render_pdf
    p = get_object_or_404(Provider, pk=pk)
    sections = [
        {"heading": "Provider Information", "type": "info", "rows": [
            ("Type", p.provider_type or "N/A"),
            ("Specialty", p.specialty or "N/A"),
            ("Practice", p.practice_name or "N/A"),
            ("NPI", p.npi or "N/A"),
            ("License #", p.license_number or "N/A"),
            ("Phone", p.phone or "N/A"),
            ("Fax", p.fax or "N/A"),
            ("Email", p.email or "N/A"),
            ("Address", p.address or "N/A"),
        ]},
    ]
    if p.notes_text:
        sections.append({"heading": "Notes", "type": "text", "content": p.notes_text})
    return render_pdf(request, f"provider-{p.pk}", p.name,
                      f"Provider — {p.get_status_display()}", sections)


def export_pdf_prescription_detail(request, pk):
    from config.pdf_export import render_pdf
    rx = get_object_or_404(Prescription, pk=pk)
    sections = [
        {"heading": "Prescription Information", "type": "info", "rows": [
            ("Medication", rx.medication_name),
            ("Generic Name", rx.generic_name or "N/A"),
            ("Dosage", rx.dosage or "N/A"),
            ("Frequency", rx.get_frequency_display() if rx.frequency else "N/A"),
            ("Route", rx.route or "N/A"),
            ("Rx Number", rx.rx_number or "N/A"),
            ("Pharmacy", rx.pharmacy or "N/A"),
            ("Controlled", "Yes" if rx.is_controlled else "No"),
            ("Refills", f"{rx.refills_remaining}/{rx.refills_total}" if rx.refills_total else "N/A"),
        ]},
    ]
    if rx.purpose:
        sections.append({"heading": "Purpose", "type": "text", "content": rx.purpose})
    if rx.notes_text:
        sections.append({"heading": "Notes", "type": "text", "content": rx.notes_text})
    return render_pdf(request, f"prescription-{rx.pk}", rx.medication_name,
                      f"Prescription — {rx.get_status_display()}", sections)


def export_pdf_appointment_detail(request, pk):
    from config.pdf_export import render_pdf
    appt = get_object_or_404(Appointment, pk=pk)
    sections = [
        {"heading": "Appointment Information", "type": "info", "rows": [
            ("Date", appt.date.strftime("%b %d, %Y") if appt.date else "N/A"),
            ("Time", appt.time.strftime("%I:%M %p") if appt.time else "N/A"),
            ("Duration", f"{appt.duration_minutes} min" if appt.duration_minutes else "N/A"),
            ("Provider", str(appt.provider) if appt.provider else "N/A"),
            ("Facility", appt.facility or "N/A"),
            ("Type", appt.get_visit_type_display()),
        ]},
    ]
    if appt.purpose:
        sections.append({"heading": "Purpose", "type": "text", "content": appt.purpose})
    if appt.preparation:
        sections.append({"heading": "Preparation", "type": "text", "content": appt.preparation})
    if appt.notes_text:
        sections.append({"heading": "Notes", "type": "text", "content": appt.notes_text})
    return render_pdf(request, f"appointment-{appt.pk}", appt.title,
                      f"Appointment — {appt.get_status_display()}", sections)


# --- Providers ---

class ProviderCreateView(CreateView):
    model = Provider
    form_class = ProviderForm
    template_name = "healthcare/provider_form.html"

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("stakeholder"):
            initial["stakeholder"] = self.request.GET["stakeholder"]
        return initial

    def form_valid(self, form):
        messages.success(self.request, "Provider created.")
        return super().form_valid(form)


class ProviderDetailView(DetailView):
    model = Provider
    template_name = "healthcare/provider_detail.html"
    context_object_name = "provider"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx["prescriptions"] = obj.prescriptions.all()
        ctx["appointments"] = obj.appointments.all()
        ctx["visits"] = obj.visits.all()
        ctx["test_results"] = obj.ordered_tests.all()
        ctx["supplements"] = obj.recommended_supplements.all()
        ctx["advice"] = obj.advice_given.all()
        ctx["conditions"] = obj.diagnosed_conditions.all()
        ctx["notes"] = obj.notes.all() if hasattr(obj, "notes") else []
        ctx["internal_notes_url"] = reverse("healthcare:provider_internal_notes", args=[obj.pk])
        return ctx


class ProviderUpdateView(UpdateView):
    model = Provider
    form_class = ProviderForm
    template_name = "healthcare/provider_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Provider updated.")
        return super().form_valid(form)


class ProviderDeleteView(DeleteView):
    model = Provider
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("healthcare:healthcare_list")

    def form_valid(self, form):
        messages.success(self.request, f'Provider "{self.object}" deleted.')
        return super().form_valid(form)


# --- Conditions ---

class ConditionCreateView(CreateView):
    model = Condition
    form_class = ConditionForm
    template_name = "healthcare/condition_form.html"

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("provider"):
            initial["diagnosed_by"] = self.request.GET["provider"]
        return initial

    def form_valid(self, form):
        messages.success(self.request, "Condition created.")
        return super().form_valid(form)


class ConditionDetailView(DetailView):
    model = Condition
    template_name = "healthcare/condition_detail.html"
    context_object_name = "condition"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx["prescriptions"] = obj.prescriptions.all()
        ctx["supplements"] = obj.supplements.all()
        ctx["test_results"] = obj.test_results.all()[:5]
        ctx["visits"] = obj.visits.all()[:5]
        ctx["advice"] = obj.advice_records.all()
        ctx["appointments"] = obj.appointments.all()[:5]
        ctx["internal_notes_url"] = reverse("healthcare:condition_internal_notes", args=[obj.pk])
        return ctx


class ConditionUpdateView(UpdateView):
    model = Condition
    form_class = ConditionForm
    template_name = "healthcare/condition_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Condition updated.")
        return super().form_valid(form)


class ConditionDeleteView(DeleteView):
    model = Condition
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("healthcare:healthcare_list")

    def form_valid(self, form):
        messages.success(self.request, f'Condition "{self.object}" deleted.')
        return super().form_valid(form)


# --- Prescriptions ---

class PrescriptionCreateView(CreateView):
    model = Prescription
    form_class = PrescriptionForm
    template_name = "healthcare/prescription_form.html"

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("provider"):
            initial["prescribing_provider"] = self.request.GET["provider"]
        if self.request.GET.get("condition"):
            initial["related_condition"] = self.request.GET["condition"]
        return initial

    def form_valid(self, form):
        messages.success(self.request, "Prescription created.")
        return super().form_valid(form)


class PrescriptionDetailView(DetailView):
    model = Prescription
    template_name = "healthcare/prescription_detail.html"
    context_object_name = "prescription"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx["internal_notes_url"] = reverse("healthcare:prescription_internal_notes", args=[obj.pk])
        return ctx


class PrescriptionUpdateView(UpdateView):
    model = Prescription
    form_class = PrescriptionForm
    template_name = "healthcare/prescription_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Prescription updated.")
        return super().form_valid(form)


class PrescriptionDeleteView(DeleteView):
    model = Prescription
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("healthcare:healthcare_list")

    def form_valid(self, form):
        messages.success(self.request, f'Prescription "{self.object}" deleted.')
        return super().form_valid(form)


# --- Supplements ---

class SupplementCreateView(CreateView):
    model = Supplement
    form_class = SupplementForm
    template_name = "healthcare/supplement_form.html"

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("provider"):
            initial["recommended_by"] = self.request.GET["provider"]
        if self.request.GET.get("condition"):
            initial["related_condition"] = self.request.GET["condition"]
        return initial

    def form_valid(self, form):
        messages.success(self.request, "Supplement created.")
        return super().form_valid(form)


class SupplementDetailView(DetailView):
    model = Supplement
    template_name = "healthcare/supplement_detail.html"
    context_object_name = "supplement"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx["internal_notes_url"] = reverse("healthcare:supplement_internal_notes", args=[obj.pk])
        return ctx


class SupplementUpdateView(UpdateView):
    model = Supplement
    form_class = SupplementForm
    template_name = "healthcare/supplement_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Supplement updated.")
        return super().form_valid(form)


class SupplementDeleteView(DeleteView):
    model = Supplement
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("healthcare:healthcare_list")

    def form_valid(self, form):
        messages.success(self.request, f'Supplement "{self.object}" deleted.')
        return super().form_valid(form)


# --- Test Results ---

class TestResultCreateView(CreateView):
    model = TestResult
    form_class = TestResultForm
    template_name = "healthcare/testresult_form.html"

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("provider"):
            initial["ordering_provider"] = self.request.GET["provider"]
        if self.request.GET.get("condition"):
            initial["related_condition"] = self.request.GET["condition"]
        return initial

    def form_valid(self, form):
        messages.success(self.request, "Test result created.")
        return super().form_valid(form)


class TestResultDetailView(DetailView):
    model = TestResult
    template_name = "healthcare/testresult_detail.html"
    context_object_name = "result"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx["internal_notes_url"] = reverse("healthcare:testresult_internal_notes", args=[obj.pk])
        return ctx


class TestResultUpdateView(UpdateView):
    model = TestResult
    form_class = TestResultForm
    template_name = "healthcare/testresult_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Test result updated.")
        return super().form_valid(form)


class TestResultDeleteView(DeleteView):
    model = TestResult
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("healthcare:healthcare_list")

    def form_valid(self, form):
        messages.success(self.request, f'Test result "{self.object}" deleted.')
        return super().form_valid(form)


# --- Visits ---

class VisitCreateView(CreateView):
    model = Visit
    form_class = VisitForm
    template_name = "healthcare/visit_form.html"

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("provider"):
            initial["provider"] = self.request.GET["provider"]
        if self.request.GET.get("condition"):
            initial["related_condition"] = self.request.GET["condition"]
        return initial

    def form_valid(self, form):
        messages.success(self.request, "Visit recorded.")
        return super().form_valid(form)


class VisitDetailView(DetailView):
    model = Visit
    template_name = "healthcare/visit_detail.html"
    context_object_name = "visit"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx["advice"] = obj.advice_records.all()
        ctx["internal_notes_url"] = reverse("healthcare:visit_internal_notes", args=[obj.pk])
        return ctx


class VisitUpdateView(UpdateView):
    model = Visit
    form_class = VisitForm
    template_name = "healthcare/visit_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Visit updated.")
        return super().form_valid(form)


class VisitDeleteView(DeleteView):
    model = Visit
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("healthcare:healthcare_list")

    def form_valid(self, form):
        messages.success(self.request, f'Visit "{self.object}" deleted.')
        return super().form_valid(form)


# --- Advice ---

class AdviceCreateView(CreateView):
    model = Advice
    form_class = AdviceForm
    template_name = "healthcare/advice_form.html"

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("provider"):
            initial["given_by"] = self.request.GET["provider"]
        if self.request.GET.get("visit"):
            initial["related_visit"] = self.request.GET["visit"]
        if self.request.GET.get("condition"):
            initial["related_condition"] = self.request.GET["condition"]
        return initial

    def form_valid(self, form):
        messages.success(self.request, "Advice created.")
        return super().form_valid(form)


class AdviceDetailView(DetailView):
    model = Advice
    template_name = "healthcare/advice_detail.html"
    context_object_name = "advice"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx["internal_notes_url"] = reverse("healthcare:advice_internal_notes", args=[obj.pk])
        return ctx


class AdviceUpdateView(UpdateView):
    model = Advice
    form_class = AdviceForm
    template_name = "healthcare/advice_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Advice updated.")
        return super().form_valid(form)


class AdviceDeleteView(DeleteView):
    model = Advice
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("healthcare:healthcare_list")

    def form_valid(self, form):
        messages.success(self.request, f'Advice "{self.object}" deleted.')
        return super().form_valid(form)


# --- Appointments ---

class AppointmentCreateView(CreateView):
    model = Appointment
    form_class = AppointmentForm
    template_name = "healthcare/appointment_form.html"

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("date"):
            initial["date"] = self.request.GET["date"]
        if self.request.GET.get("time"):
            initial["time"] = self.request.GET["time"]
        if self.request.GET.get("provider"):
            initial["provider"] = self.request.GET["provider"]
        if self.request.GET.get("condition"):
            initial["related_condition"] = self.request.GET["condition"]
        return initial

    def form_valid(self, form):
        messages.success(self.request, "Appointment created.")
        return super().form_valid(form)


class AppointmentDetailView(DetailView):
    model = Appointment
    template_name = "healthcare/appointment_detail.html"
    context_object_name = "appointment"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx["internal_notes_url"] = reverse("healthcare:appointment_internal_notes", args=[obj.pk])
        return ctx


class AppointmentUpdateView(UpdateView):
    model = Appointment
    form_class = AppointmentForm
    template_name = "healthcare/appointment_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Appointment updated.")
        return super().form_valid(form)


class AppointmentDeleteView(DeleteView):
    model = Appointment
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("healthcare:healthcare_list")

    def form_valid(self, form):
        messages.success(self.request, f'Appointment "{self.object}" deleted.')
        return super().form_valid(form)


# --- Bulk Operations ---

def _bulk_delete(request, model_class, list_url_name):
    if request.method == "POST":
        pks = request.POST.getlist("selected")
        count = model_class.objects.filter(pk__in=pks).count()
        if "confirm" not in request.POST:
            return render(request, "partials/_bulk_confirm_delete.html", {
                "count": count, "selected_pks": pks,
                "action_url": reverse(list_url_name),
            })
        model_class.objects.filter(pk__in=pks).delete()
        messages.success(request, f"{count} item(s) deleted.")
    return redirect("healthcare:healthcare_list")


def bulk_delete_provider(request):
    return _bulk_delete(request, Provider, "healthcare:bulk_delete_provider")


def bulk_delete_prescription(request):
    return _bulk_delete(request, Prescription, "healthcare:bulk_delete_prescription")


def bulk_delete_supplement(request):
    return _bulk_delete(request, Supplement, "healthcare:bulk_delete_supplement")


def bulk_delete_testresult(request):
    return _bulk_delete(request, TestResult, "healthcare:bulk_delete_testresult")


def bulk_delete_visit(request):
    return _bulk_delete(request, Visit, "healthcare:bulk_delete_visit")


def bulk_delete_advice(request):
    return _bulk_delete(request, Advice, "healthcare:bulk_delete_advice")


def bulk_delete_appointment(request):
    return _bulk_delete(request, Appointment, "healthcare:bulk_delete_appointment")


def bulk_delete_condition(request):
    return _bulk_delete(request, Condition, "healthcare:bulk_delete_condition")


# --- Internal Notes Editing ---

def _internal_notes_edit(request, model_class, pk, url_name):
    """Shared handler for inline internal notes editing on healthcare detail pages."""
    obj = get_object_or_404(model_class, pk=pk)
    edit_url = reverse(url_name, args=[pk])
    if request.method == "POST":
        obj.notes_text = request.POST.get("notes_text", "").strip()
        obj.save(update_fields=["notes_text"])
        return render(request, "healthcare/partials/_healthcare_internal_notes_display.html",
                      {"asset": obj, "edit_url": edit_url})
    if request.GET.get("display"):
        return render(request, "healthcare/partials/_healthcare_internal_notes_display.html",
                      {"asset": obj, "edit_url": edit_url})
    return render(request, "healthcare/partials/_healthcare_internal_notes_editor.html",
                  {"asset": obj, "edit_url": edit_url})


def provider_internal_notes(request, pk):
    return _internal_notes_edit(request, Provider, pk, "healthcare:provider_internal_notes")


def prescription_internal_notes(request, pk):
    return _internal_notes_edit(request, Prescription, pk, "healthcare:prescription_internal_notes")


def supplement_internal_notes(request, pk):
    return _internal_notes_edit(request, Supplement, pk, "healthcare:supplement_internal_notes")


def testresult_internal_notes(request, pk):
    return _internal_notes_edit(request, TestResult, pk, "healthcare:testresult_internal_notes")


def visit_internal_notes(request, pk):
    return _internal_notes_edit(request, Visit, pk, "healthcare:visit_internal_notes")


def advice_internal_notes(request, pk):
    return _internal_notes_edit(request, Advice, pk, "healthcare:advice_internal_notes")


def appointment_internal_notes(request, pk):
    return _internal_notes_edit(request, Appointment, pk, "healthcare:appointment_internal_notes")


def condition_internal_notes(request, pk):
    return _internal_notes_edit(request, Condition, pk, "healthcare:condition_internal_notes")


# --- FK-Based Link/Unlink (Provider & Condition hubs) ---

def _fk_link(request, parent_class, parent_pk, child_class, fk_field, form_class,
             list_template, link_url_name, unlink_url_name, list_id):
    """Generic handler for FK-based inline linking on detail pages."""
    parent = get_object_or_404(parent_class, pk=parent_pk)
    if request.method == "POST":
        form = form_class(request.POST)
        if form.is_valid():
            item = form.cleaned_data["item"]
            setattr(item, fk_field, parent)
            item.save(update_fields=[fk_field])
            items = child_class.objects.filter(**{fk_field: parent})
            return render(request, list_template, {
                "items": items,
                "unlink_url_name": unlink_url_name,
                "parent_pk": parent.pk,
            })
    else:
        form = form_class()
    return render(request, "healthcare/partials/_healthcare_fk_link_form.html", {
        "form": form,
        "link_url": reverse(link_url_name, args=[parent_pk]),
        "list_id": list_id,
    })


def _fk_unlink(request, parent_class, parent_pk, child_class, child_pk, fk_field,
               list_template, unlink_url_name):
    """Generic handler for FK-based inline unlinking on detail pages."""
    parent = get_object_or_404(parent_class, pk=parent_pk)
    child = get_object_or_404(child_class, pk=child_pk)
    if request.method == "POST":
        if getattr(child, f"{fk_field}_id") == parent.pk:
            setattr(child, fk_field, None)
            child.save(update_fields=[fk_field])
    items = child_class.objects.filter(**{fk_field: parent})
    return render(request, list_template, {
        "items": items,
        "unlink_url_name": unlink_url_name,
        "parent_pk": parent.pk,
    })


# Provider FK link/unlink wrappers

def provider_prescription_link(request, pk):
    from .forms import PrescriptionLinkForm
    return _fk_link(request, Provider, pk, Prescription, "prescribing_provider",
                    PrescriptionLinkForm,
                    "healthcare/partials/_linked_prescriptions_list.html",
                    "healthcare:provider_prescription_link",
                    "healthcare:provider_prescription_unlink",
                    "prescription-list")


def provider_prescription_unlink(request, pk, item_pk):
    return _fk_unlink(request, Provider, pk, Prescription, item_pk,
                      "prescribing_provider",
                      "healthcare/partials/_linked_prescriptions_list.html",
                      "healthcare:provider_prescription_unlink")


def provider_supplement_link(request, pk):
    from .forms import SupplementLinkForm
    return _fk_link(request, Provider, pk, Supplement, "recommended_by",
                    SupplementLinkForm,
                    "healthcare/partials/_linked_supplements_list.html",
                    "healthcare:provider_supplement_link",
                    "healthcare:provider_supplement_unlink",
                    "supplement-list")


def provider_supplement_unlink(request, pk, item_pk):
    return _fk_unlink(request, Provider, pk, Supplement, item_pk,
                      "recommended_by",
                      "healthcare/partials/_linked_supplements_list.html",
                      "healthcare:provider_supplement_unlink")


def provider_testresult_link(request, pk):
    from .forms import TestResultLinkForm
    return _fk_link(request, Provider, pk, TestResult, "ordering_provider",
                    TestResultLinkForm,
                    "healthcare/partials/_linked_testresults_list.html",
                    "healthcare:provider_testresult_link",
                    "healthcare:provider_testresult_unlink",
                    "testresult-list")


def provider_testresult_unlink(request, pk, item_pk):
    return _fk_unlink(request, Provider, pk, TestResult, item_pk,
                      "ordering_provider",
                      "healthcare/partials/_linked_testresults_list.html",
                      "healthcare:provider_testresult_unlink")


def provider_visit_link(request, pk):
    from .forms import VisitLinkForm
    return _fk_link(request, Provider, pk, Visit, "provider",
                    VisitLinkForm,
                    "healthcare/partials/_linked_visits_list.html",
                    "healthcare:provider_visit_link",
                    "healthcare:provider_visit_unlink",
                    "visit-list")


def provider_visit_unlink(request, pk, item_pk):
    return _fk_unlink(request, Provider, pk, Visit, item_pk,
                      "provider",
                      "healthcare/partials/_linked_visits_list.html",
                      "healthcare:provider_visit_unlink")


def provider_appointment_link(request, pk):
    from .forms import AppointmentLinkForm
    return _fk_link(request, Provider, pk, Appointment, "provider",
                    AppointmentLinkForm,
                    "healthcare/partials/_linked_appointments_list.html",
                    "healthcare:provider_appointment_link",
                    "healthcare:provider_appointment_unlink",
                    "appointment-list")


def provider_appointment_unlink(request, pk, item_pk):
    return _fk_unlink(request, Provider, pk, Appointment, item_pk,
                      "provider",
                      "healthcare/partials/_linked_appointments_list.html",
                      "healthcare:provider_appointment_unlink")


def provider_condition_link(request, pk):
    from .forms import ConditionLinkForm
    return _fk_link(request, Provider, pk, Condition, "diagnosed_by",
                    ConditionLinkForm,
                    "healthcare/partials/_linked_conditions_list.html",
                    "healthcare:provider_condition_link",
                    "healthcare:provider_condition_unlink",
                    "condition-list")


def provider_condition_unlink(request, pk, item_pk):
    return _fk_unlink(request, Provider, pk, Condition, item_pk,
                      "diagnosed_by",
                      "healthcare/partials/_linked_conditions_list.html",
                      "healthcare:provider_condition_unlink")


def provider_advice_link(request, pk):
    from .forms import AdviceLinkForm
    return _fk_link(request, Provider, pk, Advice, "given_by",
                    AdviceLinkForm,
                    "healthcare/partials/_linked_advice_list.html",
                    "healthcare:provider_advice_link",
                    "healthcare:provider_advice_unlink",
                    "advice-list")


def provider_advice_unlink(request, pk, item_pk):
    return _fk_unlink(request, Provider, pk, Advice, item_pk,
                      "given_by",
                      "healthcare/partials/_linked_advice_list.html",
                      "healthcare:provider_advice_unlink")


# Condition FK link/unlink wrappers

def condition_prescription_link(request, pk):
    from .forms import PrescriptionLinkForm
    return _fk_link(request, Condition, pk, Prescription, "related_condition",
                    PrescriptionLinkForm,
                    "healthcare/partials/_linked_prescriptions_list.html",
                    "healthcare:condition_prescription_link",
                    "healthcare:condition_prescription_unlink",
                    "prescription-list")


def condition_prescription_unlink(request, pk, item_pk):
    return _fk_unlink(request, Condition, pk, Prescription, item_pk,
                      "related_condition",
                      "healthcare/partials/_linked_prescriptions_list.html",
                      "healthcare:condition_prescription_unlink")


def condition_supplement_link(request, pk):
    from .forms import SupplementLinkForm
    return _fk_link(request, Condition, pk, Supplement, "related_condition",
                    SupplementLinkForm,
                    "healthcare/partials/_linked_supplements_list.html",
                    "healthcare:condition_supplement_link",
                    "healthcare:condition_supplement_unlink",
                    "supplement-list")


def condition_supplement_unlink(request, pk, item_pk):
    return _fk_unlink(request, Condition, pk, Supplement, item_pk,
                      "related_condition",
                      "healthcare/partials/_linked_supplements_list.html",
                      "healthcare:condition_supplement_unlink")


def condition_testresult_link(request, pk):
    from .forms import TestResultLinkForm
    return _fk_link(request, Condition, pk, TestResult, "related_condition",
                    TestResultLinkForm,
                    "healthcare/partials/_linked_testresults_list.html",
                    "healthcare:condition_testresult_link",
                    "healthcare:condition_testresult_unlink",
                    "testresult-list")


def condition_testresult_unlink(request, pk, item_pk):
    return _fk_unlink(request, Condition, pk, TestResult, item_pk,
                      "related_condition",
                      "healthcare/partials/_linked_testresults_list.html",
                      "healthcare:condition_testresult_unlink")


def condition_visit_link(request, pk):
    from .forms import VisitLinkForm
    return _fk_link(request, Condition, pk, Visit, "related_condition",
                    VisitLinkForm,
                    "healthcare/partials/_linked_visits_list.html",
                    "healthcare:condition_visit_link",
                    "healthcare:condition_visit_unlink",
                    "visit-list")


def condition_visit_unlink(request, pk, item_pk):
    return _fk_unlink(request, Condition, pk, Visit, item_pk,
                      "related_condition",
                      "healthcare/partials/_linked_visits_list.html",
                      "healthcare:condition_visit_unlink")


def condition_advice_link(request, pk):
    from .forms import AdviceLinkForm
    return _fk_link(request, Condition, pk, Advice, "related_condition",
                    AdviceLinkForm,
                    "healthcare/partials/_linked_advice_list.html",
                    "healthcare:condition_advice_link",
                    "healthcare:condition_advice_unlink",
                    "advice-list")


def condition_advice_unlink(request, pk, item_pk):
    return _fk_unlink(request, Condition, pk, Advice, item_pk,
                      "related_condition",
                      "healthcare/partials/_linked_advice_list.html",
                      "healthcare:condition_advice_unlink")


def condition_appointment_link(request, pk):
    from .forms import AppointmentLinkForm
    return _fk_link(request, Condition, pk, Appointment, "related_condition",
                    AppointmentLinkForm,
                    "healthcare/partials/_linked_appointments_list.html",
                    "healthcare:condition_appointment_link",
                    "healthcare:condition_appointment_unlink",
                    "appointment-list")


def condition_appointment_unlink(request, pk, item_pk):
    return _fk_unlink(request, Condition, pk, Appointment, item_pk,
                      "related_condition",
                      "healthcare/partials/_linked_appointments_list.html",
                      "healthcare:condition_appointment_unlink")


# Visit FK link/unlink wrappers (advice)

def visit_advice_link(request, pk):
    from .forms import AdviceLinkForm
    return _fk_link(request, Visit, pk, Advice, "related_visit",
                    AdviceLinkForm,
                    "healthcare/partials/_linked_advice_list.html",
                    "healthcare:visit_advice_link",
                    "healthcare:visit_advice_unlink",
                    "advice-list")


def visit_advice_unlink(request, pk, item_pk):
    return _fk_unlink(request, Visit, pk, Advice, item_pk,
                      "related_visit",
                      "healthcare/partials/_linked_advice_list.html",
                      "healthcare:visit_advice_unlink")


# --- Note Link/Unlink ---

def _note_list_ctx(notes_qs, unlink_url_name, obj_pk):
    return {
        "notes": notes_qs,
        "unlink_url_name": unlink_url_name,
        "asset_pk": obj_pk,
    }


def _note_link(request, model_class, pk, m2m_field, link_url_name, unlink_url_name):
    from .forms import HealthcareNoteLinkForm
    obj = get_object_or_404(model_class, pk=pk)
    if request.method == "POST":
        form = HealthcareNoteLinkForm(request.POST)
        if form.is_valid():
            note = form.cleaned_data["note"]
            getattr(note, m2m_field).add(obj)
            mgr = getattr(obj, "notes", None)
            notes_qs = mgr.all() if mgr is not None else model_class.objects.none()
            return render(request, "healthcare/partials/_healthcare_note_list.html",
                          _note_list_ctx(notes_qs, unlink_url_name, obj.pk))
    else:
        form = HealthcareNoteLinkForm()
    return render(request, "healthcare/partials/_healthcare_note_form.html", {
        "form": form,
        "link_url": reverse(link_url_name, args=[obj.pk]),
    })


def _note_unlink(request, model_class, pk, note_pk, m2m_field, unlink_url_name):
    from notes.models import Note
    obj = get_object_or_404(model_class, pk=pk)
    note = get_object_or_404(Note, pk=note_pk)
    if request.method == "POST":
        getattr(note, m2m_field).remove(obj)
    mgr = getattr(obj, "notes", None)
    notes_qs = mgr.all() if mgr is not None else model_class.objects.none()
    return render(request, "healthcare/partials/_healthcare_note_list.html",
                  _note_list_ctx(notes_qs, unlink_url_name, obj.pk))


def provider_note_link(request, pk):
    return _note_link(request, Provider, pk, "related_providers",
                      "healthcare:provider_note_link", "healthcare:provider_note_unlink")


def provider_note_unlink(request, pk, note_pk):
    return _note_unlink(request, Provider, pk, note_pk, "related_providers",
                        "healthcare:provider_note_unlink")


def prescription_note_link(request, pk):
    return _note_link(request, Prescription, pk, "related_prescriptions",
                      "healthcare:prescription_note_link", "healthcare:prescription_note_unlink")


def prescription_note_unlink(request, pk, note_pk):
    return _note_unlink(request, Prescription, pk, note_pk, "related_prescriptions",
                        "healthcare:prescription_note_unlink")


def appointment_note_link(request, pk):
    return _note_link(request, Appointment, pk, "related_appointments",
                      "healthcare:appointment_note_link", "healthcare:appointment_note_unlink")


def appointment_note_unlink(request, pk, note_pk):
    return _note_unlink(request, Appointment, pk, note_pk, "related_appointments",
                        "healthcare:appointment_note_unlink")


def visit_note_link(request, pk):
    return _note_link(request, Visit, pk, "related_visits",
                      "healthcare:visit_note_link", "healthcare:visit_note_unlink")


def visit_note_unlink(request, pk, note_pk):
    return _note_unlink(request, Visit, pk, note_pk, "related_visits",
                        "healthcare:visit_note_unlink")


def condition_note_link(request, pk):
    return _note_link(request, Condition, pk, "related_conditions",
                      "healthcare:condition_note_link", "healthcare:condition_note_unlink")


def condition_note_unlink(request, pk, note_pk):
    return _note_unlink(request, Condition, pk, note_pk, "related_conditions",
                        "healthcare:condition_note_unlink")


# --- Legal Link/Unlink ---

def _legal_list_ctx(legal_qs, unlink_url_name, obj_pk):
    return {
        "legal_matters": legal_qs,
        "unlink_url_name": unlink_url_name,
        "asset_pk": obj_pk,
    }


def _legal_link(request, model_class, pk, m2m_field, link_url_name, unlink_url_name):
    from .forms import HealthcareLegalLinkForm
    obj = get_object_or_404(model_class, pk=pk)
    if request.method == "POST":
        form = HealthcareLegalLinkForm(request.POST)
        if form.is_valid():
            matter = form.cleaned_data["legal_matter"]
            getattr(matter, m2m_field).add(obj)
            mgr = getattr(obj, "legal_matters", None)
            legal_qs = mgr.all() if mgr is not None else model_class.objects.none()
            return render(request, "healthcare/partials/_healthcare_legal_list.html",
                          _legal_list_ctx(legal_qs, unlink_url_name, obj.pk))
    else:
        form = HealthcareLegalLinkForm()
    return render(request, "healthcare/partials/_healthcare_legal_form.html", {
        "form": form,
        "link_url": reverse(link_url_name, args=[obj.pk]),
    })


def _legal_unlink(request, model_class, pk, legal_pk, m2m_field, unlink_url_name):
    from legal.models import LegalMatter
    obj = get_object_or_404(model_class, pk=pk)
    matter = get_object_or_404(LegalMatter, pk=legal_pk)
    if request.method == "POST":
        getattr(matter, m2m_field).remove(obj)
    mgr = getattr(obj, "legal_matters", None)
    legal_qs = mgr.all() if mgr is not None else model_class.objects.none()
    return render(request, "healthcare/partials/_healthcare_legal_list.html",
                  _legal_list_ctx(legal_qs, unlink_url_name, obj.pk))


def provider_legal_link(request, pk):
    return _legal_link(request, Provider, pk, "related_providers",
                       "healthcare:provider_legal_link", "healthcare:provider_legal_unlink")


def provider_legal_unlink(request, pk, legal_pk):
    return _legal_unlink(request, Provider, pk, legal_pk, "related_providers",
                         "healthcare:provider_legal_unlink")


def prescription_legal_link(request, pk):
    return _legal_link(request, Prescription, pk, "related_prescriptions",
                       "healthcare:prescription_legal_link", "healthcare:prescription_legal_unlink")


def prescription_legal_unlink(request, pk, legal_pk):
    return _legal_unlink(request, Prescription, pk, legal_pk, "related_prescriptions",
                         "healthcare:prescription_legal_unlink")


def condition_legal_link(request, pk):
    return _legal_link(request, Condition, pk, "related_conditions",
                       "healthcare:condition_legal_link", "healthcare:condition_legal_unlink")


def condition_legal_unlink(request, pk, legal_pk):
    return _legal_unlink(request, Condition, pk, legal_pk, "related_conditions",
                         "healthcare:condition_legal_unlink")
