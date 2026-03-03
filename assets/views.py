from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import (AircraftForm, AircraftOwnerForm, AssetPolicyLinkForm, AssetTabForm,
                     InsurancePolicyForm, InvestmentForm, InvestmentParticipantForm,
                     LoanForm, LoanPartyForm, PolicyHolderForm, PropertyOwnershipForm,
                     RealEstateForm, VehicleForm, VehicleOwnerForm)
from .models import (Aircraft, AircraftOwner, AssetTab, InsurancePolicy, Investment,
                     InvestmentParticipant, Loan, LoanParty, PolicyHolder,
                     PropertyOwnership, RealEstate, Vehicle, VehicleOwner)


# --- Asset Tab Config ---

def _get_asset_tab_config():
    """Build dynamic tab config from AssetTab + computed Other tab."""
    tabs = list(AssetTab.objects.all())
    all_types = {"properties", "investments", "loans", "policies", "vehicles", "aircraft"}

    # Collect asset_types claimed by non-builtin tabs
    claimed = set()
    for tab in tabs:
        if not tab.is_builtin:
            claimed.update(tab.asset_types)

    unclaimed = all_types - claimed

    # Counts
    counts = {
        "properties": RealEstate.objects.count(),
        "investments": Investment.objects.count(),
        "loans": Loan.objects.count(),
        "policies": InsurancePolicy.objects.count(),
        "vehicles": Vehicle.objects.count(),
        "aircraft": Aircraft.objects.count(),
    }

    result = []
    for tab in tabs:
        tab_count = sum(counts.get(t, 0) for t in tab.asset_types)
        result.append({
            "key": tab.key,
            "label": tab.label,
            "asset_types": tab.asset_types,
            "is_builtin": tab.is_builtin,
            "pk": tab.pk,
            "count": tab_count,
        })

    if unclaimed:
        tab_count = sum(counts.get(t, 0) for t in unclaimed)
        result.append({
            "key": "other",
            "label": "Other",
            "asset_types": sorted(unclaimed),
            "is_builtin": False,
            "pk": None,
            "count": tab_count,
        })

    return result, counts


# --- Unified Asset List ---

def asset_list(request):
    tabs, counts = _get_asset_tab_config()
    tab_key = request.GET.get("tab", "")
    valid_keys = {t["key"] for t in tabs}
    if tab_key not in valid_keys:
        tab_key = tabs[0]["key"] if tabs else "all"

    # Find current tab's asset_types
    current_asset_types = []
    for t in tabs:
        if t["key"] == tab_key:
            current_asset_types = t["asset_types"]
            break

    q = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "")
    direction = "" if request.GET.get("dir") == "asc" else "-"

    ctx = {
        "tabs": tabs,
        "current_tab": tab_key,
        "current_asset_types": current_asset_types,
        "tab_counts": counts,
        "search_query": q,
        "current_sort": sort,
        "current_dir": request.GET.get("dir", ""),
        "total_count": sum(counts.values()),
    }

    if "properties" in current_asset_types:
        qs = RealEstate.objects.all()
        if q:
            qs = qs.filter(name__icontains=q)
        statuses = [s for s in request.GET.getlist("status") if s]
        if statuses:
            qs = qs.filter(status__in=statuses)
        date_from = request.GET.get("date_from")
        if date_from:
            qs = qs.filter(acquisition_date__gte=date_from)
        date_to = request.GET.get("date_to")
        if date_to:
            qs = qs.filter(acquisition_date__lte=date_to)
        if len(current_asset_types) == 1:
            ALLOWED_SORTS = {"name", "status", "estimated_value", "acquisition_date"}
            if sort in ALLOWED_SORTS:
                qs = qs.order_by(f"{direction}{sort}")
        ctx["properties"] = qs
        ctx["property_status_choices"] = RealEstate.STATUS_CHOICES

    if "investments" in current_asset_types:
        qs = Investment.objects.all()
        if q:
            qs = qs.filter(name__icontains=q)
        if len(current_asset_types) == 1:
            ALLOWED_SORTS = {"name", "investment_type", "current_value"}
            if sort in ALLOWED_SORTS:
                qs = qs.order_by(f"{direction}{sort}")
        ctx["investments"] = qs

    if "loans" in current_asset_types:
        qs = Loan.objects.all()
        if q:
            qs = qs.filter(name__icontains=q)
        statuses = [s for s in request.GET.getlist("status") if s]
        if statuses:
            qs = qs.filter(status__in=statuses)
        date_from = request.GET.get("date_from")
        if date_from:
            qs = qs.filter(next_payment_date__gte=date_from)
        date_to = request.GET.get("date_to")
        if date_to:
            qs = qs.filter(next_payment_date__lte=date_to)
        if len(current_asset_types) == 1:
            ALLOWED_SORTS = {"name", "status", "current_balance", "next_payment_date"}
            if sort in ALLOWED_SORTS:
                qs = qs.order_by(f"{direction}{sort}")
        ctx["loans"] = qs
        ctx["loan_status_choices"] = Loan.STATUS_CHOICES

    if "policies" in current_asset_types:
        qs = InsurancePolicy.objects.select_related("carrier").all()
        if q:
            qs = qs.filter(name__icontains=q)
        statuses = [s for s in request.GET.getlist("status") if s]
        if statuses:
            qs = qs.filter(status__in=statuses)
        date_from = request.GET.get("date_from")
        if date_from:
            qs = qs.filter(expiration_date__gte=date_from)
        date_to = request.GET.get("date_to")
        if date_to:
            qs = qs.filter(expiration_date__lte=date_to)
        if len(current_asset_types) == 1:
            ALLOWED_SORTS = {"name", "status", "premium_amount", "expiration_date"}
            if sort in ALLOWED_SORTS:
                qs = qs.order_by(f"{direction}{sort}")
        ctx["policies"] = qs
        ctx["policy_status_choices"] = InsurancePolicy.STATUS_CHOICES

    if "vehicles" in current_asset_types:
        qs = Vehicle.objects.all()
        if q:
            qs = qs.filter(name__icontains=q)
        statuses = [s for s in request.GET.getlist("status") if s]
        if statuses:
            qs = qs.filter(status__in=statuses)
        date_from = request.GET.get("date_from")
        if date_from:
            qs = qs.filter(acquisition_date__gte=date_from)
        date_to = request.GET.get("date_to")
        if date_to:
            qs = qs.filter(acquisition_date__lte=date_to)
        if len(current_asset_types) == 1:
            ALLOWED_SORTS = {"name", "status", "estimated_value", "year"}
            if sort in ALLOWED_SORTS:
                qs = qs.order_by(f"{direction}{sort}")
        ctx["vehicles"] = qs
        ctx["vehicle_status_choices"] = Vehicle.STATUS_CHOICES

    if "aircraft" in current_asset_types:
        qs = Aircraft.objects.all()
        if q:
            qs = qs.filter(name__icontains=q)
        statuses = [s for s in request.GET.getlist("status") if s]
        if statuses:
            qs = qs.filter(status__in=statuses)
        date_from = request.GET.get("date_from")
        if date_from:
            qs = qs.filter(acquisition_date__gte=date_from)
        date_to = request.GET.get("date_to")
        if date_to:
            qs = qs.filter(acquisition_date__lte=date_to)
        if len(current_asset_types) == 1:
            ALLOWED_SORTS = {"name", "status", "estimated_value", "total_hours"}
            if sort in ALLOWED_SORTS:
                qs = qs.order_by(f"{direction}{sort}")
        ctx["aircraft_list"] = qs
        ctx["aircraft_status_choices"] = Aircraft.STATUS_CHOICES

    ctx["hide_checkboxes"] = len(current_asset_types) > 1

    # For status filters / date filters in single-type tabs
    if len(current_asset_types) == 1:
        if current_asset_types[0] in ("properties", "loans", "policies", "vehicles", "aircraft"):
            ctx["status_choices"] = (
                ctx.get("property_status_choices")
                or ctx.get("loan_status_choices")
                or ctx.get("policy_status_choices")
                or ctx.get("vehicle_status_choices")
                or ctx.get("aircraft_status_choices", [])
            )
            ctx["selected_statuses"] = [s for s in request.GET.getlist("status") if s]
            ctx["date_from"] = request.GET.get("date_from", "")
            ctx["date_to"] = request.GET.get("date_to", "")

    is_htmx = request.headers.get("HX-Request")
    if is_htmx:
        return render(request, "assets/partials/_asset_tab_content.html", ctx)
    return render(request, "assets/asset_list.html", ctx)


# --- Asset Tab Settings ---

def asset_tab_settings(request):
    tabs = AssetTab.objects.all()
    return render(request, "assets/asset_tab_settings.html", {"tabs": tabs})


def asset_tab_add(request):
    if request.method == "POST":
        form = AssetTabForm(request.POST)
        if form.is_valid():
            form.save()
            tabs = AssetTab.objects.all()
            return render(request, "assets/partials/_asset_tab_settings_list.html", {"tabs": tabs})
    else:
        form = AssetTabForm()
    return render(request, "assets/partials/_asset_tab_settings_form.html", {"form": form})


def asset_tab_edit(request, pk):
    tab = get_object_or_404(AssetTab, pk=pk)
    if tab.is_builtin:
        return HttpResponse(status=403)
    if request.method == "POST":
        form = AssetTabForm(request.POST, instance=tab)
        if form.is_valid():
            form.save()
            tabs = AssetTab.objects.all()
            return render(request, "assets/partials/_asset_tab_settings_list.html", {"tabs": tabs})
    else:
        form = AssetTabForm(instance=tab)
    return render(request, "assets/partials/_asset_tab_settings_form.html", {
        "form": form,
        "form_url": reverse("assets:asset_tab_edit", args=[pk]),
        "edit_mode": True,
    })


def asset_tab_delete(request, pk):
    tab = get_object_or_404(AssetTab, pk=pk)
    if tab.is_builtin:
        return HttpResponse(status=403)
    if request.method == "POST":
        tab.delete()
    tabs = AssetTab.objects.all()
    return render(request, "assets/partials/_asset_tab_settings_list.html", {"tabs": tabs})


def inline_update_realestate_status(request, pk):
    prop = get_object_or_404(RealEstate, pk=pk)
    status = request.POST.get("status", "")
    valid = [s[0] for s in RealEstate.STATUS_CHOICES]
    if status not in valid:
        return HttpResponseBadRequest("Invalid status")
    prop.status = status
    prop.save(update_fields=["status"])
    return render(request, "assets/partials/_realestate_row.html", {"prop": prop})


def inline_update_loan_status(request, pk):
    loan = get_object_or_404(Loan, pk=pk)
    status = request.POST.get("status", "")
    valid = [s[0] for s in Loan.STATUS_CHOICES]
    if status not in valid:
        return HttpResponseBadRequest("Invalid status")
    loan.status = status
    loan.save(update_fields=["status"])
    return render(request, "assets/partials/_loan_row.html", {"loan": loan})


def export_realestate_csv(request):
    from legacy.export import export_csv as do_export
    qs = RealEstate.objects.all()
    fields = [
        ("name", "Name"),
        ("address", "Address"),
        ("property_type", "Type"),
        ("estimated_value", "Estimated Value"),
        ("status", "Status"),
        ("acquisition_date", "Acquisition Date"),
    ]
    return do_export(qs, fields, "real_estate")


def export_investment_csv(request):
    from legacy.export import export_csv as do_export
    qs = Investment.objects.all()
    fields = [
        ("name", "Name"),
        ("investment_type", "Type"),
        ("institution", "Institution"),
        ("current_value", "Current Value"),
    ]
    return do_export(qs, fields, "investments")


def export_loan_csv(request):
    from legacy.export import export_csv as do_export
    qs = Loan.objects.all()
    fields = [
        ("name", "Name"),
        ("current_balance", "Balance"),
        ("interest_rate", "Rate"),
        ("monthly_payment", "Monthly Payment"),
        ("next_payment_date", "Next Payment"),
        ("status", "Status"),
    ]
    return do_export(qs, fields, "loans")


def export_pdf_realestate_detail(request, pk):
    from legacy.pdf_export import render_pdf
    p = get_object_or_404(RealEstate, pk=pk)
    sections = [
        {"heading": "Property Information", "type": "info", "rows": [
            ("Address", p.address),
            ("Type", p.property_type or "N/A"),
            ("Estimated Value", f"${p.estimated_value:,.0f}" if p.estimated_value else "N/A"),
            ("Acquisition Date", p.acquisition_date.strftime("%b %d, %Y") if p.acquisition_date else "N/A"),
            ("Jurisdiction", p.jurisdiction or "N/A"),
        ]},
    ]
    owners = p.ownerships.select_related("stakeholder").all()
    if owners:
        owner_str = ", ".join(f"{o.stakeholder.name} ({o.role} {o.ownership_percentage}%)" if o.ownership_percentage else f"{o.stakeholder.name} ({o.role})" for o in owners)
        sections[0]["rows"].append(("Stakeholders", owner_str))
    if p.notes_text:
        sections.append({"heading": "Notes", "type": "text", "content": p.notes_text})
    entries = p.cash_flow_entries.all()
    if entries:
        sections.append({"heading": "Cash Flow Entries", "type": "table",
                         "headers": ["Date", "Description", "Type", "Amount"],
                         "rows": [[e.date.strftime("%b %d, %Y"), e.description, e.get_entry_type_display(),
                                   f"{'+'if e.entry_type == 'inflow' else '-'}${e.amount:,.0f}"] for e in entries]})
    return render_pdf(request, f"property-{p.pk}", p.name,
                      f"Real Estate — {p.get_status_display()}", sections)


def export_pdf_investment_detail(request, pk):
    from legacy.pdf_export import render_pdf
    inv = get_object_or_404(Investment, pk=pk)
    sections = [
        {"heading": "Investment Information", "type": "info", "rows": [
            ("Type", inv.investment_type or "N/A"),
            ("Institution", inv.institution or "N/A"),
            ("Current Value", f"${inv.current_value:,.0f}" if inv.current_value else "N/A"),
        ]},
    ]
    participants = inv.participants.select_related("stakeholder").all()
    if participants:
        part_str = ", ".join(f"{p.stakeholder.name} ({p.role} {p.ownership_percentage}%)" if p.ownership_percentage else f"{p.stakeholder.name} ({p.role})" for p in participants)
        sections[0]["rows"].append(("Stakeholders", part_str))
    if inv.notes_text:
        sections.append({"heading": "Notes", "type": "text", "content": inv.notes_text})
    return render_pdf(request, f"investment-{inv.pk}", inv.name, "Investment", sections)


def export_pdf_loan_detail(request, pk):
    from legacy.pdf_export import render_pdf
    loan = get_object_or_404(Loan, pk=pk)
    sections = [
        {"heading": "Loan Information", "type": "info", "rows": [
            ("Original Amount", f"${loan.original_amount:,.0f}" if loan.original_amount else "N/A"),
            ("Current Balance", f"${loan.current_balance:,.0f}" if loan.current_balance else "N/A"),
            ("Monthly Payment", f"${loan.monthly_payment:,.2f}" if loan.monthly_payment else "N/A"),
            ("Interest Rate", f"{loan.interest_rate}%" if loan.interest_rate else "N/A"),
            ("Next Payment", loan.next_payment_date.strftime("%b %d, %Y") if loan.next_payment_date else "N/A"),
            ("Maturity Date", loan.maturity_date.strftime("%b %d, %Y") if loan.maturity_date else "N/A"),
        ]},
    ]
    parties = loan.parties.select_related("stakeholder").all()
    if parties:
        party_str = ", ".join(f"{p.stakeholder.name} ({p.role} {p.ownership_percentage}%)" if p.ownership_percentage else f"{p.stakeholder.name} ({p.role})" for p in parties)
        sections[0]["rows"].append(("Parties", party_str))
    if loan.borrower_description:
        sections[0]["rows"].append(("Borrower", loan.borrower_description))
    if loan.collateral:
        sections.append({"heading": "Collateral", "type": "text", "content": loan.collateral})
    if loan.notes_text:
        sections.append({"heading": "Notes", "type": "text", "content": loan.notes_text})
    entries = loan.cash_flow_entries.all()
    if entries:
        sections.append({"heading": "Cash Flow Entries", "type": "table",
                         "headers": ["Date", "Description", "Type", "Amount"],
                         "rows": [[e.date.strftime("%b %d, %Y"), e.description, e.get_entry_type_display(),
                                   f"{'+'if e.entry_type == 'inflow' else '-'}${e.amount:,.0f}"] for e in entries]})
    return render_pdf(request, f"loan-{loan.pk}", loan.name,
                      f"Loan — {loan.get_status_display()}", sections)


# --- Real Estate ---
class RealEstateListView(ListView):
    model = RealEstate
    template_name = "assets/realestate_list.html"
    context_object_name = "properties"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        statuses = [s for s in self.request.GET.getlist("status") if s]
        if statuses:
            qs = qs.filter(status__in=statuses)
        date_from = self.request.GET.get("date_from")
        if date_from:
            qs = qs.filter(acquisition_date__gte=date_from)
        date_to = self.request.GET.get("date_to")
        if date_to:
            qs = qs.filter(acquisition_date__lte=date_to)
        ALLOWED_SORTS = {"name", "status", "estimated_value", "acquisition_date"}
        sort = self.request.GET.get("sort", "")
        if sort in ALLOWED_SORTS:
            direction = "" if self.request.GET.get("dir") == "asc" else "-"
            qs = qs.order_by(f"{direction}{sort}")
        return qs

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["assets/partials/_realestate_table_rows.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search_query"] = self.request.GET.get("q", "")
        ctx["status_choices"] = RealEstate.STATUS_CHOICES
        ctx["selected_status"] = self.request.GET.get("status", "")
        ctx["date_from"] = self.request.GET.get("date_from", "")
        ctx["date_to"] = self.request.GET.get("date_to", "")
        ctx["selected_statuses"] = self.request.GET.getlist("status")
        ctx["current_sort"] = self.request.GET.get("sort", "")
        ctx["current_dir"] = self.request.GET.get("dir", "")
        return ctx


class RealEstateCreateView(CreateView):
    model = RealEstate
    form_class = RealEstateForm
    template_name = "assets/realestate_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        stakeholder = form.cleaned_data.get("initial_stakeholder")
        if stakeholder:
            PropertyOwnership.objects.create(
                property=self.object,
                stakeholder=stakeholder,
                role=form.cleaned_data.get("initial_role", ""),
                ownership_percentage=form.cleaned_data.get("initial_percentage"),
            )
        messages.success(self.request, "Property created.")
        return response


class RealEstateDetailView(DetailView):
    model = RealEstate
    template_name = "assets/realestate_detail.html"
    context_object_name = "property"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx["loans"] = obj.loans.prefetch_related("parties__stakeholder").all()
        ctx["legal_matters"] = obj.legal_matters.all()[:5]
        ctx["tasks"] = obj.tasks.exclude(status="complete")[:5]
        ctx["notes"] = obj.notes.all()[:5]
        ctx["cash_flow_entries"] = obj.cash_flow_entries.all()[:10]
        ctx["insurance_policies"] = obj.insurance_policies.all()
        return ctx


class RealEstateUpdateView(UpdateView):
    model = RealEstate
    form_class = RealEstateForm
    template_name = "assets/realestate_form.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        del form.fields["initial_stakeholder"]
        del form.fields["initial_role"]
        del form.fields["initial_percentage"]
        return form

    def form_valid(self, form):
        messages.success(self.request, "Property updated.")
        return super().form_valid(form)


class RealEstateDeleteView(DeleteView):
    model = RealEstate
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("assets:realestate_list")

    def form_valid(self, form):
        messages.success(self.request, f'Property "{self.object}" deleted.')
        return super().form_valid(form)


# --- Investments ---
class InvestmentListView(ListView):
    model = Investment
    template_name = "assets/investment_list.html"
    context_object_name = "investments"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        ALLOWED_SORTS = {"name", "investment_type", "current_value"}
        sort = self.request.GET.get("sort", "")
        if sort in ALLOWED_SORTS:
            direction = "" if self.request.GET.get("dir") == "asc" else "-"
            qs = qs.order_by(f"{direction}{sort}")
        return qs

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["assets/partials/_investment_table_rows.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search_query"] = self.request.GET.get("q", "")
        ctx["current_sort"] = self.request.GET.get("sort", "")
        ctx["current_dir"] = self.request.GET.get("dir", "")
        return ctx


class InvestmentCreateView(CreateView):
    model = Investment
    form_class = InvestmentForm
    template_name = "assets/investment_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        stakeholder = form.cleaned_data.get("initial_stakeholder")
        if stakeholder:
            InvestmentParticipant.objects.create(
                investment=self.object,
                stakeholder=stakeholder,
                role=form.cleaned_data.get("initial_role", ""),
                ownership_percentage=form.cleaned_data.get("initial_percentage"),
            )
        messages.success(self.request, "Investment created.")
        return response


class InvestmentDetailView(DetailView):
    model = Investment
    template_name = "assets/investment_detail.html"
    context_object_name = "investment"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["loans"] = self.object.loans.prefetch_related("parties__stakeholder").all()
        ctx["notes"] = self.object.notes.all()[:5]
        return ctx


class InvestmentUpdateView(UpdateView):
    model = Investment
    form_class = InvestmentForm
    template_name = "assets/investment_form.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        del form.fields["initial_stakeholder"]
        del form.fields["initial_role"]
        del form.fields["initial_percentage"]
        return form

    def form_valid(self, form):
        messages.success(self.request, "Investment updated.")
        return super().form_valid(form)


class InvestmentDeleteView(DeleteView):
    model = Investment
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("assets:investment_list")

    def form_valid(self, form):
        messages.success(self.request, f'Investment "{self.object}" deleted.')
        return super().form_valid(form)


# --- Loans ---
class LoanListView(ListView):
    model = Loan
    template_name = "assets/loan_list.html"
    context_object_name = "loans"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        statuses = [s for s in self.request.GET.getlist("status") if s]
        if statuses:
            qs = qs.filter(status__in=statuses)
        date_from = self.request.GET.get("date_from")
        if date_from:
            qs = qs.filter(next_payment_date__gte=date_from)
        date_to = self.request.GET.get("date_to")
        if date_to:
            qs = qs.filter(next_payment_date__lte=date_to)
        ALLOWED_SORTS = {"name", "status", "current_balance", "next_payment_date"}
        sort = self.request.GET.get("sort", "")
        if sort in ALLOWED_SORTS:
            direction = "" if self.request.GET.get("dir") == "asc" else "-"
            qs = qs.order_by(f"{direction}{sort}")
        return qs

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["assets/partials/_loan_table_rows.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search_query"] = self.request.GET.get("q", "")
        ctx["status_choices"] = Loan.STATUS_CHOICES
        ctx["selected_status"] = self.request.GET.get("status", "")
        ctx["date_from"] = self.request.GET.get("date_from", "")
        ctx["date_to"] = self.request.GET.get("date_to", "")
        ctx["selected_statuses"] = self.request.GET.getlist("status")
        ctx["current_sort"] = self.request.GET.get("sort", "")
        ctx["current_dir"] = self.request.GET.get("dir", "")
        return ctx


class LoanCreateView(CreateView):
    model = Loan
    form_class = LoanForm
    template_name = "assets/loan_form.html"

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("property"):
            initial["related_property"] = self.request.GET["property"]
        if self.request.GET.get("investment"):
            initial["related_investment"] = self.request.GET["investment"]
        return initial

    def form_valid(self, form):
        messages.success(self.request, "Loan created.")
        return super().form_valid(form)


class LoanDetailView(DetailView):
    model = Loan
    template_name = "assets/loan_detail.html"
    context_object_name = "loan"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["cash_flow_entries"] = self.object.cash_flow_entries.all()[:10]
        ctx["notes"] = self.object.notes.all()[:5]
        return ctx


class LoanUpdateView(UpdateView):
    model = Loan
    form_class = LoanForm
    template_name = "assets/loan_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Loan updated.")
        return super().form_valid(form)


class LoanDeleteView(DeleteView):
    model = Loan
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("assets:loan_list")

    def form_valid(self, form):
        messages.success(self.request, f'Loan "{self.object}" deleted.')
        return super().form_valid(form)


def bulk_delete_realestate(request):
    if request.method == "POST":
        pks = request.POST.getlist("selected")
        count = RealEstate.objects.filter(pk__in=pks).count()
        if "confirm" not in request.POST:
            from django.urls import reverse
            return render(request, "partials/_bulk_confirm_delete.html", {
                "count": count, "selected_pks": pks,
                "action_url": reverse("assets:realestate_bulk_delete"),
            })
        RealEstate.objects.filter(pk__in=pks).delete()
        messages.success(request, f"{count} property(ies) deleted.")
    return redirect("assets:realestate_list")


def bulk_export_realestate_csv(request):
    from legacy.export import export_csv as do_export
    pks = request.GET.getlist("selected")
    qs = RealEstate.objects.filter(pk__in=pks) if pks else RealEstate.objects.none()
    fields = [
        ("name", "Name"),
        ("address", "Address"),
        ("property_type", "Type"),
        ("estimated_value", "Estimated Value"),
        ("status", "Status"),
        ("acquisition_date", "Acquisition Date"),
    ]
    return do_export(qs, fields, "real_estate_selected")


def bulk_delete_investment(request):
    if request.method == "POST":
        pks = request.POST.getlist("selected")
        count = Investment.objects.filter(pk__in=pks).count()
        if "confirm" not in request.POST:
            from django.urls import reverse
            return render(request, "partials/_bulk_confirm_delete.html", {
                "count": count, "selected_pks": pks,
                "action_url": reverse("assets:investment_bulk_delete"),
            })
        Investment.objects.filter(pk__in=pks).delete()
        messages.success(request, f"{count} investment(s) deleted.")
    return redirect("assets:investment_list")


def bulk_export_investment_csv(request):
    from legacy.export import export_csv as do_export
    pks = request.GET.getlist("selected")
    qs = Investment.objects.filter(pk__in=pks) if pks else Investment.objects.none()
    fields = [
        ("name", "Name"),
        ("investment_type", "Type"),
        ("institution", "Institution"),
        ("current_value", "Current Value"),
    ]
    return do_export(qs, fields, "investments_selected")


def bulk_delete_loan(request):
    if request.method == "POST":
        pks = request.POST.getlist("selected")
        count = Loan.objects.filter(pk__in=pks).count()
        if "confirm" not in request.POST:
            from django.urls import reverse
            return render(request, "partials/_bulk_confirm_delete.html", {
                "count": count, "selected_pks": pks,
                "action_url": reverse("assets:loan_bulk_delete"),
            })
        Loan.objects.filter(pk__in=pks).delete()
        messages.success(request, f"{count} loan(s) deleted.")
    return redirect("assets:loan_list")


def bulk_export_loan_csv(request):
    from legacy.export import export_csv as do_export
    pks = request.GET.getlist("selected")
    qs = Loan.objects.filter(pk__in=pks) if pks else Loan.objects.none()
    fields = [
        ("name", "Name"),
        ("current_balance", "Balance"),
        ("interest_rate", "Rate"),
        ("monthly_payment", "Monthly Payment"),
        ("next_payment_date", "Next Payment"),
        ("status", "Status"),
    ]
    return do_export(qs, fields, "loans_selected")


# --- Inline stakeholder management ---

def ownership_add(request, pk):
    prop = get_object_or_404(RealEstate, pk=pk)
    if request.method == "POST":
        form = PropertyOwnershipForm(request.POST)
        if form.is_valid():
            ownership = form.save(commit=False)
            ownership.property = prop
            ownership.save()
            return render(request, "assets/partials/_ownership_list.html",
                          {"ownerships": prop.ownerships.select_related("stakeholder").all(), "property": prop})
    else:
        form = PropertyOwnershipForm()
    return render(request, "assets/partials/_ownership_form.html",
                  {"form": form, "property": prop})


def ownership_delete(request, pk):
    ownership = get_object_or_404(PropertyOwnership, pk=pk)
    prop = ownership.property
    if request.method == "POST":
        ownership.delete()
    return render(request, "assets/partials/_ownership_list.html",
                  {"ownerships": prop.ownerships.select_related("stakeholder").all(), "property": prop})


def participant_add(request, pk):
    inv = get_object_or_404(Investment, pk=pk)
    if request.method == "POST":
        form = InvestmentParticipantForm(request.POST)
        if form.is_valid():
            participant = form.save(commit=False)
            participant.investment = inv
            participant.save()
            return render(request, "assets/partials/_participant_list.html",
                          {"participants": inv.participants.select_related("stakeholder").all(), "investment": inv})
    else:
        form = InvestmentParticipantForm()
    return render(request, "assets/partials/_participant_form.html",
                  {"form": form, "investment": inv})


def participant_delete(request, pk):
    participant = get_object_or_404(InvestmentParticipant, pk=pk)
    inv = participant.investment
    if request.method == "POST":
        participant.delete()
    return render(request, "assets/partials/_participant_list.html",
                  {"participants": inv.participants.select_related("stakeholder").all(), "investment": inv})


def loan_party_add(request, pk):
    loan = get_object_or_404(Loan, pk=pk)
    if request.method == "POST":
        form = LoanPartyForm(request.POST)
        if form.is_valid():
            party = form.save(commit=False)
            party.loan = loan
            party.save()
            return render(request, "assets/partials/_party_list.html",
                          {"parties": loan.parties.select_related("stakeholder").all(), "loan": loan})
    else:
        form = LoanPartyForm()
    return render(request, "assets/partials/_party_form.html",
                  {"form": form, "loan": loan})


def loan_party_delete(request, pk):
    party = get_object_or_404(LoanParty, pk=pk)
    loan = party.loan
    if request.method == "POST":
        party.delete()
    return render(request, "assets/partials/_party_list.html",
                  {"parties": loan.parties.select_related("stakeholder").all(), "loan": loan})


# --- Insurance Policies ---

class InsurancePolicyListView(ListView):
    model = InsurancePolicy
    template_name = "assets/policy_list.html"
    context_object_name = "policies"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().select_related("carrier")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        statuses = [s for s in self.request.GET.getlist("status") if s]
        if statuses:
            qs = qs.filter(status__in=statuses)
        ALLOWED_SORTS = {"name", "status", "premium_amount", "expiration_date"}
        sort = self.request.GET.get("sort", "")
        if sort in ALLOWED_SORTS:
            direction = "" if self.request.GET.get("dir") == "asc" else "-"
            qs = qs.order_by(f"{direction}{sort}")
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search_query"] = self.request.GET.get("q", "")
        ctx["status_choices"] = InsurancePolicy.STATUS_CHOICES
        ctx["selected_statuses"] = self.request.GET.getlist("status")
        ctx["current_sort"] = self.request.GET.get("sort", "")
        ctx["current_dir"] = self.request.GET.get("dir", "")
        return ctx


class InsurancePolicyCreateView(CreateView):
    model = InsurancePolicy
    form_class = InsurancePolicyForm
    template_name = "assets/policy_form.html"

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("property"):
            initial["covered_properties"] = [self.request.GET["property"]]
        if self.request.GET.get("vehicle"):
            initial["covered_vehicles"] = [self.request.GET["vehicle"]]
        if self.request.GET.get("aircraft"):
            initial["covered_aircraft"] = [self.request.GET["aircraft"]]
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        stakeholder = form.cleaned_data.get("initial_stakeholder")
        if stakeholder:
            PolicyHolder.objects.create(
                policy=self.object,
                stakeholder=stakeholder,
                role=form.cleaned_data.get("initial_role", ""),
            )
        messages.success(self.request, "Insurance policy created.")
        return response


class InsurancePolicyDetailView(DetailView):
    model = InsurancePolicy
    template_name = "assets/policy_detail.html"
    context_object_name = "policy"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["policyholders"] = self.object.policyholders.select_related("stakeholder").all()
        ctx["covered_properties"] = self.object.covered_properties.all()
        ctx["covered_vehicles"] = self.object.covered_vehicles.all()
        ctx["covered_aircraft"] = self.object.covered_aircraft.all()
        ctx["notes"] = self.object.notes.all()[:5]
        return ctx


class InsurancePolicyUpdateView(UpdateView):
    model = InsurancePolicy
    form_class = InsurancePolicyForm
    template_name = "assets/policy_form.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        del form.fields["initial_stakeholder"]
        del form.fields["initial_role"]
        return form

    def form_valid(self, form):
        messages.success(self.request, "Insurance policy updated.")
        return super().form_valid(form)


class InsurancePolicyDeleteView(DeleteView):
    model = InsurancePolicy
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("assets:policy_list")

    def form_valid(self, form):
        messages.success(self.request, f'Policy "{self.object}" deleted.')
        return super().form_valid(form)


def inline_update_policy_status(request, pk):
    policy = get_object_or_404(InsurancePolicy, pk=pk)
    status = request.POST.get("status", "")
    valid = [s[0] for s in InsurancePolicy.STATUS_CHOICES]
    if status not in valid:
        return HttpResponseBadRequest("Invalid status")
    policy.status = status
    policy.save(update_fields=["status"])
    return render(request, "assets/partials/_policy_row.html", {"policy": policy})


def export_policy_csv(request):
    from legacy.export import export_csv as do_export
    from dashboard.choices import get_choice_label
    qs = InsurancePolicy.objects.select_related("carrier").all()
    for p in qs:
        p._carrier_name = p.carrier.name if p.carrier else ""
        p._policy_type_label = get_choice_label("policy_type", p.policy_type)
    fields = [
        ("name", "Name"),
        ("policy_number", "Policy Number"),
        ("_policy_type_label", "Type"),
        ("_carrier_name", "Carrier"),
        ("premium_amount", "Premium"),
        ("premium_frequency", "Frequency"),
        ("status", "Status"),
        ("effective_date", "Effective Date"),
        ("expiration_date", "Expiration Date"),
    ]
    return do_export(qs, fields, "insurance_policies")


def bulk_export_policy_csv(request):
    from legacy.export import export_csv as do_export
    from dashboard.choices import get_choice_label
    pks = request.GET.getlist("selected")
    qs = InsurancePolicy.objects.filter(pk__in=pks) if pks else InsurancePolicy.objects.none()
    qs = qs.select_related("carrier")
    for p in qs:
        p._carrier_name = p.carrier.name if p.carrier else ""
        p._policy_type_label = get_choice_label("policy_type", p.policy_type)
    fields = [
        ("name", "Name"),
        ("policy_number", "Policy Number"),
        ("_policy_type_label", "Type"),
        ("_carrier_name", "Carrier"),
        ("premium_amount", "Premium"),
        ("status", "Status"),
        ("expiration_date", "Expiration Date"),
    ]
    return do_export(qs, fields, "insurance_policies_selected")


def export_pdf_policy_detail(request, pk):
    from legacy.pdf_export import render_pdf
    from dashboard.choices import get_choice_label
    p = get_object_or_404(InsurancePolicy.objects.select_related("carrier", "agent"), pk=pk)
    sections = [
        {"heading": "Policy Information", "type": "info", "rows": [
            ("Policy Number", p.policy_number or "N/A"),
            ("Type", get_choice_label("policy_type", p.policy_type)),
            ("Status", p.get_status_display()),
            ("Carrier", p.carrier.name if p.carrier else "N/A"),
            ("Agent", p.agent.name if p.agent else "N/A"),
            ("Premium", f"${p.premium_amount:,.2f} ({p.get_premium_frequency_display()})" if p.premium_amount else "N/A"),
            ("Deductible", f"${p.deductible:,.2f}" if p.deductible else "N/A"),
            ("Coverage Limit", f"${p.coverage_limit:,.0f}" if p.coverage_limit else "N/A"),
            ("Effective Date", p.effective_date.strftime("%b %d, %Y") if p.effective_date else "N/A"),
            ("Expiration Date", p.expiration_date.strftime("%b %d, %Y") if p.expiration_date else "N/A"),
            ("Auto Renew", "Yes" if p.auto_renew else "No"),
        ]},
    ]
    holders = p.policyholders.select_related("stakeholder").all()
    if holders:
        sections.append({"heading": "Policyholders", "type": "table",
                         "headers": ["Name", "Role"],
                         "rows": [[h.stakeholder.name, h.role or "-"] for h in holders]})
    props = p.covered_properties.all()
    if props:
        sections.append({"heading": "Covered Properties", "type": "table",
                         "headers": ["Name", "Address"],
                         "rows": [[pr.name, pr.address] for pr in props]})
    vehicles = p.covered_vehicles.all()
    if vehicles:
        sections.append({"heading": "Covered Vehicles", "type": "table",
                         "headers": ["Name", "Year", "Make/Model"],
                         "rows": [[v.name, str(v.year or "-"), f"{v.make} {v.model_name}".strip() or "-"] for v in vehicles]})
    aircraft = p.covered_aircraft.all()
    if aircraft:
        sections.append({"heading": "Covered Aircraft", "type": "table",
                         "headers": ["Name", "Tail Number", "Type"],
                         "rows": [[a.name, a.tail_number or "-", a.aircraft_type] for a in aircraft]})
    if p.notes_text:
        sections.append({"heading": "Notes", "type": "text", "content": p.notes_text})
    return render_pdf(request, f"policy-{p.pk}", p.name,
                      f"Insurance Policy — {p.get_status_display()}", sections)


def bulk_delete_policy(request):
    if request.method == "POST":
        pks = request.POST.getlist("selected")
        count = InsurancePolicy.objects.filter(pk__in=pks).count()
        if "confirm" not in request.POST:
            return render(request, "partials/_bulk_confirm_delete.html", {
                "count": count, "selected_pks": pks,
                "action_url": reverse("assets:policy_bulk_delete"),
            })
        InsurancePolicy.objects.filter(pk__in=pks).delete()
        messages.success(request, f"{count} policy(ies) deleted.")
    return redirect("assets:policy_list")


def policyholder_add(request, pk):
    policy = get_object_or_404(InsurancePolicy, pk=pk)
    if request.method == "POST":
        form = PolicyHolderForm(request.POST)
        if form.is_valid():
            holder = form.save(commit=False)
            holder.policy = policy
            holder.save()
            return render(request, "assets/partials/_policyholder_list.html",
                          {"policyholders": policy.policyholders.select_related("stakeholder").all(), "policy": policy})
    else:
        form = PolicyHolderForm()
    return render(request, "assets/partials/_policyholder_form.html",
                  {"form": form, "policy": policy})


def policyholder_delete(request, pk):
    holder = get_object_or_404(PolicyHolder, pk=pk)
    policy = holder.policy
    if request.method == "POST":
        holder.delete()
    return render(request, "assets/partials/_policyholder_list.html",
                  {"policyholders": policy.policyholders.select_related("stakeholder").all(), "policy": policy})


# --- Vehicles ---

class VehicleListView(ListView):
    model = Vehicle
    template_name = "assets/vehicle_list.html"
    context_object_name = "vehicles"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        statuses = [s for s in self.request.GET.getlist("status") if s]
        if statuses:
            qs = qs.filter(status__in=statuses)
        ALLOWED_SORTS = {"name", "status", "estimated_value", "year"}
        sort = self.request.GET.get("sort", "")
        if sort in ALLOWED_SORTS:
            direction = "" if self.request.GET.get("dir") == "asc" else "-"
            qs = qs.order_by(f"{direction}{sort}")
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search_query"] = self.request.GET.get("q", "")
        ctx["status_choices"] = Vehicle.STATUS_CHOICES
        ctx["selected_statuses"] = self.request.GET.getlist("status")
        ctx["current_sort"] = self.request.GET.get("sort", "")
        ctx["current_dir"] = self.request.GET.get("dir", "")
        return ctx


class VehicleCreateView(CreateView):
    model = Vehicle
    form_class = VehicleForm
    template_name = "assets/vehicle_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        stakeholder = form.cleaned_data.get("initial_stakeholder")
        if stakeholder:
            VehicleOwner.objects.create(
                vehicle=self.object,
                stakeholder=stakeholder,
                role=form.cleaned_data.get("initial_role", ""),
                ownership_percentage=form.cleaned_data.get("initial_percentage"),
            )
        messages.success(self.request, "Vehicle created.")
        return response


class VehicleDetailView(DetailView):
    model = Vehicle
    template_name = "assets/vehicle_detail.html"
    context_object_name = "vehicle"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["insurance_policies"] = self.object.insurance_policies.all()
        ctx["notes"] = self.object.notes.all()[:5]
        return ctx


class VehicleUpdateView(UpdateView):
    model = Vehicle
    form_class = VehicleForm
    template_name = "assets/vehicle_form.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        del form.fields["initial_stakeholder"]
        del form.fields["initial_role"]
        del form.fields["initial_percentage"]
        return form

    def form_valid(self, form):
        messages.success(self.request, "Vehicle updated.")
        return super().form_valid(form)


class VehicleDeleteView(DeleteView):
    model = Vehicle
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("assets:vehicle_list")

    def form_valid(self, form):
        messages.success(self.request, f'Vehicle "{self.object}" deleted.')
        return super().form_valid(form)


def inline_update_vehicle_status(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    status = request.POST.get("status", "")
    valid = [s[0] for s in Vehicle.STATUS_CHOICES]
    if status not in valid:
        return HttpResponseBadRequest("Invalid status")
    vehicle.status = status
    vehicle.save(update_fields=["status"])
    return render(request, "assets/partials/_vehicle_row.html", {"vehicle": vehicle})


def export_vehicle_csv(request):
    from legacy.export import export_csv as do_export
    from dashboard.choices import get_choice_label
    qs = Vehicle.objects.all()
    for v in qs:
        v._vehicle_type_label = get_choice_label("vehicle_type", v.vehicle_type)
    fields = [
        ("name", "Name"),
        ("vin", "VIN"),
        ("year", "Year"),
        ("make", "Make"),
        ("model_name", "Model"),
        ("_vehicle_type_label", "Type"),
        ("estimated_value", "Estimated Value"),
        ("status", "Status"),
    ]
    return do_export(qs, fields, "vehicles")


def bulk_export_vehicle_csv(request):
    from legacy.export import export_csv as do_export
    from dashboard.choices import get_choice_label
    pks = request.GET.getlist("selected")
    qs = Vehicle.objects.filter(pk__in=pks) if pks else Vehicle.objects.none()
    for v in qs:
        v._vehicle_type_label = get_choice_label("vehicle_type", v.vehicle_type)
    fields = [
        ("name", "Name"),
        ("vin", "VIN"),
        ("year", "Year"),
        ("make", "Make"),
        ("model_name", "Model"),
        ("_vehicle_type_label", "Type"),
        ("estimated_value", "Estimated Value"),
        ("status", "Status"),
    ]
    return do_export(qs, fields, "vehicles_selected")


def export_pdf_vehicle_detail(request, pk):
    from legacy.pdf_export import render_pdf
    from dashboard.choices import get_choice_label
    v = get_object_or_404(Vehicle, pk=pk)
    sections = [
        {"heading": "Vehicle Information", "type": "info", "rows": [
            ("VIN", v.vin or "N/A"),
            ("Year", str(v.year) if v.year else "N/A"),
            ("Make", v.make or "N/A"),
            ("Model", v.model_name or "N/A"),
            ("Type", get_choice_label("vehicle_type", v.vehicle_type)),
            ("Color", v.color or "N/A"),
            ("License Plate", v.license_plate or "N/A"),
            ("Registration State", v.registration_state or "N/A"),
            ("Mileage", f"{v.mileage:,}" if v.mileage else "N/A"),
            ("Estimated Value", f"${v.estimated_value:,.0f}" if v.estimated_value else "N/A"),
            ("Acquisition Date", v.acquisition_date.strftime("%b %d, %Y") if v.acquisition_date else "N/A"),
        ]},
    ]
    owners = v.owners.select_related("stakeholder").all()
    if owners:
        owner_str = ", ".join(
            f"{o.stakeholder.name} ({o.role} {o.ownership_percentage}%)" if o.ownership_percentage
            else f"{o.stakeholder.name} ({o.role})" for o in owners
        )
        sections[0]["rows"].append(("Owners", owner_str))
    if v.notes_text:
        sections.append({"heading": "Notes", "type": "text", "content": v.notes_text})
    return render_pdf(request, f"vehicle-{v.pk}", v.name,
                      f"Vehicle — {v.get_status_display()}", sections)


def bulk_delete_vehicle(request):
    if request.method == "POST":
        pks = request.POST.getlist("selected")
        count = Vehicle.objects.filter(pk__in=pks).count()
        if "confirm" not in request.POST:
            return render(request, "partials/_bulk_confirm_delete.html", {
                "count": count, "selected_pks": pks,
                "action_url": reverse("assets:vehicle_bulk_delete"),
            })
        Vehicle.objects.filter(pk__in=pks).delete()
        messages.success(request, f"{count} vehicle(s) deleted.")
    return redirect("assets:vehicle_list")


def vehicle_owner_add(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    if request.method == "POST":
        form = VehicleOwnerForm(request.POST)
        if form.is_valid():
            owner = form.save(commit=False)
            owner.vehicle = vehicle
            owner.save()
            return render(request, "assets/partials/_vehicle_owner_list.html",
                          {"owners": vehicle.owners.select_related("stakeholder").all(), "vehicle": vehicle})
    else:
        form = VehicleOwnerForm()
    return render(request, "assets/partials/_vehicle_owner_form.html",
                  {"form": form, "vehicle": vehicle})


def vehicle_owner_delete(request, pk):
    owner = get_object_or_404(VehicleOwner, pk=pk)
    vehicle = owner.vehicle
    if request.method == "POST":
        owner.delete()
    return render(request, "assets/partials/_vehicle_owner_list.html",
                  {"owners": vehicle.owners.select_related("stakeholder").all(), "vehicle": vehicle})


# --- Aircraft ---

class AircraftListView(ListView):
    model = Aircraft
    template_name = "assets/aircraft_list.html"
    context_object_name = "aircraft_list"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        statuses = [s for s in self.request.GET.getlist("status") if s]
        if statuses:
            qs = qs.filter(status__in=statuses)
        ALLOWED_SORTS = {"name", "status", "estimated_value", "total_hours"}
        sort = self.request.GET.get("sort", "")
        if sort in ALLOWED_SORTS:
            direction = "" if self.request.GET.get("dir") == "asc" else "-"
            qs = qs.order_by(f"{direction}{sort}")
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search_query"] = self.request.GET.get("q", "")
        ctx["status_choices"] = Aircraft.STATUS_CHOICES
        ctx["selected_statuses"] = self.request.GET.getlist("status")
        ctx["current_sort"] = self.request.GET.get("sort", "")
        ctx["current_dir"] = self.request.GET.get("dir", "")
        return ctx


class AircraftCreateView(CreateView):
    model = Aircraft
    form_class = AircraftForm
    template_name = "assets/aircraft_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        stakeholder = form.cleaned_data.get("initial_stakeholder")
        if stakeholder:
            AircraftOwner.objects.create(
                aircraft=self.object,
                stakeholder=stakeholder,
                role=form.cleaned_data.get("initial_role", ""),
                ownership_percentage=form.cleaned_data.get("initial_percentage"),
            )
        messages.success(self.request, "Aircraft created.")
        return response


class AircraftDetailView(DetailView):
    model = Aircraft
    template_name = "assets/aircraft_detail.html"
    context_object_name = "aircraft"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["insurance_policies"] = self.object.insurance_policies.all()
        ctx["notes"] = self.object.notes.all()[:5]
        return ctx


class AircraftUpdateView(UpdateView):
    model = Aircraft
    form_class = AircraftForm
    template_name = "assets/aircraft_form.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        del form.fields["initial_stakeholder"]
        del form.fields["initial_role"]
        del form.fields["initial_percentage"]
        return form

    def form_valid(self, form):
        messages.success(self.request, "Aircraft updated.")
        return super().form_valid(form)


class AircraftDeleteView(DeleteView):
    model = Aircraft
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("assets:aircraft_list")

    def form_valid(self, form):
        messages.success(self.request, f'Aircraft "{self.object}" deleted.')
        return super().form_valid(form)


def inline_update_aircraft_status(request, pk):
    ac = get_object_or_404(Aircraft, pk=pk)
    status = request.POST.get("status", "")
    valid = [s[0] for s in Aircraft.STATUS_CHOICES]
    if status not in valid:
        return HttpResponseBadRequest("Invalid status")
    ac.status = status
    ac.save(update_fields=["status"])
    return render(request, "assets/partials/_aircraft_row.html", {"ac": ac})


def export_aircraft_csv(request):
    from legacy.export import export_csv as do_export
    from dashboard.choices import get_choice_label
    qs = Aircraft.objects.all()
    for a in qs:
        a._aircraft_type_label = get_choice_label("aircraft_type", a.aircraft_type)
    fields = [
        ("name", "Name"),
        ("tail_number", "Tail Number"),
        ("year", "Year"),
        ("make", "Make"),
        ("model_name", "Model"),
        ("_aircraft_type_label", "Type"),
        ("estimated_value", "Estimated Value"),
        ("total_hours", "Total Hours"),
        ("status", "Status"),
    ]
    return do_export(qs, fields, "aircraft")


def bulk_export_aircraft_csv(request):
    from legacy.export import export_csv as do_export
    from dashboard.choices import get_choice_label
    pks = request.GET.getlist("selected")
    qs = Aircraft.objects.filter(pk__in=pks) if pks else Aircraft.objects.none()
    for a in qs:
        a._aircraft_type_label = get_choice_label("aircraft_type", a.aircraft_type)
    fields = [
        ("name", "Name"),
        ("tail_number", "Tail Number"),
        ("year", "Year"),
        ("make", "Make"),
        ("model_name", "Model"),
        ("_aircraft_type_label", "Type"),
        ("estimated_value", "Estimated Value"),
        ("total_hours", "Total Hours"),
        ("status", "Status"),
    ]
    return do_export(qs, fields, "aircraft_selected")


def export_pdf_aircraft_detail(request, pk):
    from legacy.pdf_export import render_pdf
    from dashboard.choices import get_choice_label
    ac = get_object_or_404(Aircraft, pk=pk)
    sections = [
        {"heading": "Aircraft Information", "type": "info", "rows": [
            ("Tail Number", ac.tail_number or "N/A"),
            ("Serial Number", ac.serial_number or "N/A"),
            ("Year", str(ac.year) if ac.year else "N/A"),
            ("Make", ac.make or "N/A"),
            ("Model", ac.model_name or "N/A"),
            ("Type", get_choice_label("aircraft_type", ac.aircraft_type)),
            ("Engines", str(ac.num_engines) if ac.num_engines else "N/A"),
            ("Base Airport", ac.base_airport or "N/A"),
            ("Total Hours", f"{ac.total_hours:,.1f}" if ac.total_hours else "N/A"),
            ("Estimated Value", f"${ac.estimated_value:,.0f}" if ac.estimated_value else "N/A"),
            ("Acquisition Date", ac.acquisition_date.strftime("%b %d, %Y") if ac.acquisition_date else "N/A"),
            ("Registration Country", ac.registration_country or "N/A"),
        ]},
    ]
    owners = ac.owners.select_related("stakeholder").all()
    if owners:
        owner_str = ", ".join(
            f"{o.stakeholder.name} ({o.role} {o.ownership_percentage}%)" if o.ownership_percentage
            else f"{o.stakeholder.name} ({o.role})" for o in owners
        )
        sections[0]["rows"].append(("Owners", owner_str))
    if ac.notes_text:
        sections.append({"heading": "Notes", "type": "text", "content": ac.notes_text})
    return render_pdf(request, f"aircraft-{ac.pk}", ac.name,
                      f"Aircraft — {ac.get_status_display()}", sections)


def bulk_delete_aircraft(request):
    if request.method == "POST":
        pks = request.POST.getlist("selected")
        count = Aircraft.objects.filter(pk__in=pks).count()
        if "confirm" not in request.POST:
            return render(request, "partials/_bulk_confirm_delete.html", {
                "count": count, "selected_pks": pks,
                "action_url": reverse("assets:aircraft_bulk_delete"),
            })
        Aircraft.objects.filter(pk__in=pks).delete()
        messages.success(request, f"{count} aircraft deleted.")
    return redirect("assets:aircraft_list")


def aircraft_owner_add(request, pk):
    ac = get_object_or_404(Aircraft, pk=pk)
    if request.method == "POST":
        form = AircraftOwnerForm(request.POST)
        if form.is_valid():
            owner = form.save(commit=False)
            owner.aircraft = ac
            owner.save()
            return render(request, "assets/partials/_aircraft_owner_list.html",
                          {"owners": ac.owners.select_related("stakeholder").all(), "aircraft": ac})
    else:
        form = AircraftOwnerForm()
    return render(request, "assets/partials/_aircraft_owner_form.html",
                  {"form": form, "aircraft": ac})


def aircraft_owner_delete(request, pk):
    owner = get_object_or_404(AircraftOwner, pk=pk)
    ac = owner.aircraft
    if request.method == "POST":
        owner.delete()
    return render(request, "assets/partials/_aircraft_owner_list.html",
                  {"owners": ac.owners.select_related("stakeholder").all(), "aircraft": ac})


# --- Asset ↔ Policy linking ---

def _policy_list_ctx(asset, m2m_field, unlink_url_name, new_policy_param):
    return {
        "policies": getattr(asset, "insurance_policies").all(),
        "unlink_url_name": unlink_url_name,
        "asset_pk": asset.pk,
        "new_policy_url": reverse("assets:policy_create") + f"?{new_policy_param}={asset.pk}",
    }


def property_policy_link(request, pk):
    prop = get_object_or_404(RealEstate, pk=pk)
    if request.method == "POST":
        form = AssetPolicyLinkForm(request.POST)
        if form.is_valid():
            policy = form.cleaned_data["policy"]
            policy.covered_properties.add(prop)
            return render(request, "assets/partials/_asset_policy_list.html",
                          _policy_list_ctx(prop, "covered_properties", "assets:property_policy_unlink", "property"))
    else:
        form = AssetPolicyLinkForm()
    return render(request, "assets/partials/_asset_policy_form.html", {
        "form": form,
        "link_url": reverse("assets:property_policy_link", args=[prop.pk]),
    })


def property_policy_unlink(request, pk, policy_pk):
    prop = get_object_or_404(RealEstate, pk=pk)
    policy = get_object_or_404(InsurancePolicy, pk=policy_pk)
    if request.method == "POST":
        policy.covered_properties.remove(prop)
    return render(request, "assets/partials/_asset_policy_list.html",
                  _policy_list_ctx(prop, "covered_properties", "assets:property_policy_unlink", "property"))


def vehicle_policy_link(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    if request.method == "POST":
        form = AssetPolicyLinkForm(request.POST)
        if form.is_valid():
            policy = form.cleaned_data["policy"]
            policy.covered_vehicles.add(vehicle)
            return render(request, "assets/partials/_asset_policy_list.html",
                          _policy_list_ctx(vehicle, "covered_vehicles", "assets:vehicle_policy_unlink", "vehicle"))
    else:
        form = AssetPolicyLinkForm()
    return render(request, "assets/partials/_asset_policy_form.html", {
        "form": form,
        "link_url": reverse("assets:vehicle_policy_link", args=[vehicle.pk]),
    })


def vehicle_policy_unlink(request, pk, policy_pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)
    policy = get_object_or_404(InsurancePolicy, pk=policy_pk)
    if request.method == "POST":
        policy.covered_vehicles.remove(vehicle)
    return render(request, "assets/partials/_asset_policy_list.html",
                  _policy_list_ctx(vehicle, "covered_vehicles", "assets:vehicle_policy_unlink", "vehicle"))


def aircraft_policy_link(request, pk):
    ac = get_object_or_404(Aircraft, pk=pk)
    if request.method == "POST":
        form = AssetPolicyLinkForm(request.POST)
        if form.is_valid():
            policy = form.cleaned_data["policy"]
            policy.covered_aircraft.add(ac)
            return render(request, "assets/partials/_asset_policy_list.html",
                          _policy_list_ctx(ac, "covered_aircraft", "assets:aircraft_policy_unlink", "aircraft"))
    else:
        form = AssetPolicyLinkForm()
    return render(request, "assets/partials/_asset_policy_form.html", {
        "form": form,
        "link_url": reverse("assets:aircraft_policy_link", args=[ac.pk]),
    })


def aircraft_policy_unlink(request, pk, policy_pk):
    ac = get_object_or_404(Aircraft, pk=pk)
    policy = get_object_or_404(InsurancePolicy, pk=policy_pk)
    if request.method == "POST":
        policy.covered_aircraft.remove(ac)
    return render(request, "assets/partials/_asset_policy_list.html",
                  _policy_list_ctx(ac, "covered_aircraft", "assets:aircraft_policy_unlink", "aircraft"))
