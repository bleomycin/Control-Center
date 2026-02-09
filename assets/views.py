from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import InvestmentForm, LoanForm, RealEstateForm
from .models import Investment, Loan, RealEstate


def export_realestate_csv(request):
    from blaine.export import export_csv as do_export
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
    from blaine.export import export_csv as do_export
    qs = Investment.objects.all()
    fields = [
        ("name", "Name"),
        ("investment_type", "Type"),
        ("institution", "Institution"),
        ("current_value", "Current Value"),
    ]
    return do_export(qs, fields, "investments")


def export_loan_csv(request):
    from blaine.export import export_csv as do_export
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
    from blaine.pdf_export import render_pdf
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
    if p.stakeholder:
        sections[0]["rows"].append(("Stakeholder", p.stakeholder.name))
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
    from blaine.pdf_export import render_pdf
    inv = get_object_or_404(Investment, pk=pk)
    sections = [
        {"heading": "Investment Information", "type": "info", "rows": [
            ("Type", inv.investment_type or "N/A"),
            ("Institution", inv.institution or "N/A"),
            ("Current Value", f"${inv.current_value:,.0f}" if inv.current_value else "N/A"),
        ]},
    ]
    if inv.stakeholder:
        sections[0]["rows"].append(("Stakeholder", inv.stakeholder.name))
    if inv.notes_text:
        sections.append({"heading": "Notes", "type": "text", "content": inv.notes_text})
    return render_pdf(request, f"investment-{inv.pk}", inv.name, "Investment", sections)


def export_pdf_loan_detail(request, pk):
    from blaine.pdf_export import render_pdf
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
    if loan.lender:
        sections[0]["rows"].append(("Lender", loan.lender.name))
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
        statuses = self.request.GET.getlist("status")
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
        messages.success(self.request, "Property created.")
        return super().form_valid(form)


class RealEstateDetailView(DetailView):
    model = RealEstate
    template_name = "assets/realestate_detail.html"
    context_object_name = "property"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx["legal_matters"] = obj.legal_matters.all()[:5]
        ctx["tasks"] = obj.tasks.exclude(status="complete")[:5]
        ctx["notes"] = obj.notes.all()[:5]
        ctx["cash_flow_entries"] = obj.cash_flow_entries.all()[:10]
        return ctx


class RealEstateUpdateView(UpdateView):
    model = RealEstate
    form_class = RealEstateForm
    template_name = "assets/realestate_form.html"

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
        messages.success(self.request, "Investment created.")
        return super().form_valid(form)


class InvestmentDetailView(DetailView):
    model = Investment
    template_name = "assets/investment_detail.html"
    context_object_name = "investment"


class InvestmentUpdateView(UpdateView):
    model = Investment
    form_class = InvestmentForm
    template_name = "assets/investment_form.html"

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
        statuses = self.request.GET.getlist("status")
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
    from blaine.export import export_csv as do_export
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
    from blaine.export import export_csv as do_export
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
    from blaine.export import export_csv as do_export
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
