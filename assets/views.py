from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import (AssetTabForm, InvestmentForm, InvestmentParticipantForm, LoanForm,
                     LoanPartyForm, PropertyOwnershipForm, RealEstateForm)
from .models import (AssetTab, Investment, InvestmentParticipant, Loan, LoanParty,
                     PropertyOwnership, RealEstate)


# --- Asset Tab Config ---

def _get_asset_tab_config():
    """Build dynamic tab config from AssetTab + computed Other tab."""
    tabs = list(AssetTab.objects.all())
    all_types = {"properties", "investments", "loans"}

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
        "total_count": counts["properties"] + counts["investments"] + counts["loans"],
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

    # For status filters / date filters in single-type tabs
    if len(current_asset_types) == 1:
        if current_asset_types[0] in ("properties", "loans"):
            ctx["status_choices"] = ctx.get("property_status_choices") or ctx.get("loan_status_choices", [])
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
