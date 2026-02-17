from decimal import Decimal

from django.contrib import messages
from django.db.models import Sum, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from dashboard.choices import get_choices
from .forms import CashFlowEntryForm, InlineCashFlowForm
from .models import CashFlowEntry


def chart_data(request):
    """JSON endpoint for Chart.js — monthly trend and category breakdown."""
    today = timezone.localdate()
    six_months_ago = today.replace(day=1)
    for _ in range(5):
        six_months_ago = (six_months_ago - __import__('datetime').timedelta(days=1)).replace(day=1)

    # Monthly trend — last 6 months
    monthly = (
        CashFlowEntry.objects.filter(date__gte=six_months_ago, is_projected=False)
        .annotate(month=TruncMonth("date"))
        .values("month", "entry_type")
        .annotate(total=Sum("amount"))
        .order_by("month")
    )
    months_map = {}
    for row in monthly:
        label = row["month"].strftime("%b %Y")
        if label not in months_map:
            months_map[label] = {"inflow": 0, "outflow": 0}
        months_map[label][row["entry_type"]] = float(row["total"])

    month_labels = list(months_map.keys())
    inflows = [months_map[m]["inflow"] for m in month_labels]
    outflows = [months_map[m]["outflow"] for m in month_labels]

    # Category breakdown — top categories by total amount
    categories = (
        CashFlowEntry.objects.filter(is_projected=False)
        .exclude(category="")
        .values("category")
        .annotate(total=Sum("amount"))
        .order_by("-total")[:8]
    )
    cat_labels = [c["category"] for c in categories]
    cat_values = [float(c["total"]) for c in categories]

    return JsonResponse({
        "monthly": {"labels": month_labels, "inflows": inflows, "outflows": outflows},
        "categories": {"labels": cat_labels, "values": cat_values},
    })


def export_csv(request):
    from config.export import export_csv as do_export
    qs = CashFlowEntry.objects.all()
    fields = [
        ("date", "Date"),
        ("description", "Description"),
        ("entry_type", "Type"),
        ("category", "Category"),
        ("amount", "Amount"),
        ("is_projected", "Projected"),
        ("is_recurring", "Recurring"),
        ("recurrence_rule", "Recurrence"),
    ]
    return do_export(qs, fields, "cashflow")


class CashFlowListView(ListView):
    model = CashFlowEntry
    template_name = "cashflow/cashflow_list.html"
    context_object_name = "entries"
    paginate_by = 50

    def get_queryset(self):
        qs = super().get_queryset()
        entry_types = [t for t in self.request.GET.getlist("type") if t]
        if entry_types:
            qs = qs.filter(entry_type__in=entry_types)
        projected = self.request.GET.get("projected")
        if projected == "actual":
            qs = qs.filter(is_projected=False)
        elif projected == "projected":
            qs = qs.filter(is_projected=True)
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(description__icontains=q)
        date_from = self.request.GET.get("date_from")
        if date_from:
            qs = qs.filter(date__gte=date_from)
        date_to = self.request.GET.get("date_to")
        if date_to:
            qs = qs.filter(date__lte=date_to)
        category = self.request.GET.get("category", "").strip()
        if category:
            qs = qs.filter(category=category)
        stakeholder = self.request.GET.get("stakeholder", "").strip()
        if stakeholder:
            qs = qs.filter(related_stakeholder_id=stakeholder)
        asset = self.request.GET.get("asset", "").strip()
        if asset:
            qs = qs.filter(
                Q(related_property_id=asset) | Q(related_loan_id=asset) | Q(related_investment_id=asset)
            )
        ALLOWED_SORTS = {"description", "entry_type", "category", "date", "amount"}
        sort = self.request.GET.get("sort", "")
        if sort in ALLOWED_SORTS:
            direction = "" if self.request.GET.get("dir") == "asc" else "-"
            qs = qs.order_by(f"{direction}{sort}")
        return qs

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["cashflow/partials/_cashflow_table_rows.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search_query"] = self.request.GET.get("q", "")
        ctx["selected_type"] = self.request.GET.get("type", "")
        ctx["selected_projected"] = self.request.GET.get("projected", "")
        ctx["date_from"] = self.request.GET.get("date_from", "")
        ctx["date_to"] = self.request.GET.get("date_to", "")
        ctx["selected_types"] = self.request.GET.getlist("type")
        ctx["current_sort"] = self.request.GET.get("sort", "")
        ctx["current_dir"] = self.request.GET.get("dir", "")
        ctx["selected_category"] = self.request.GET.get("category", "")
        ctx["selected_stakeholder"] = self.request.GET.get("stakeholder", "")
        ctx["selected_asset"] = self.request.GET.get("asset", "")

        # Category choices for filter dropdown
        ctx["category_choices"] = get_choices("cashflow_category")

        # Stakeholder choices for filter dropdown
        from stakeholders.models import Stakeholder
        ctx["stakeholder_choices"] = Stakeholder.objects.values_list("pk", "name").order_by("name")

        # Running totals for currently filtered entries
        qs = self.get_queryset()
        totals = qs.aggregate(
            total_inflows=Sum("amount", filter=Q(entry_type="inflow"), default=Decimal("0")),
            total_outflows=Sum("amount", filter=Q(entry_type="outflow"), default=Decimal("0")),
        )
        ctx["total_inflows"] = totals["total_inflows"]
        ctx["total_outflows"] = totals["total_outflows"]
        ctx["net_flow"] = totals["total_inflows"] - totals["total_outflows"]

        from cashflow.alerts import get_liquidity_alerts
        ctx["liquidity_alerts"] = get_liquidity_alerts()
        return ctx


class CashFlowDetailView(DetailView):
    model = CashFlowEntry
    template_name = "cashflow/cashflow_detail.html"
    context_object_name = "entry"


class CashFlowCreateView(CreateView):
    model = CashFlowEntry
    form_class = CashFlowEntryForm
    template_name = "cashflow/cashflow_form.html"
    success_url = reverse_lazy("cashflow:list")

    def form_valid(self, form):
        messages.success(self.request, "Entry created.")
        return super().form_valid(form)


class CashFlowUpdateView(UpdateView):
    model = CashFlowEntry
    form_class = CashFlowEntryForm
    template_name = "cashflow/cashflow_form.html"
    success_url = reverse_lazy("cashflow:list")

    def form_valid(self, form):
        messages.success(self.request, "Entry updated.")
        return super().form_valid(form)


class CashFlowDeleteView(DeleteView):
    model = CashFlowEntry
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("cashflow:list")

    def form_valid(self, form):
        messages.success(self.request, f'Entry "{self.object}" deleted.')
        return super().form_valid(form)


def export_pdf_detail(request, pk):
    from config.pdf_export import render_pdf
    from dashboard.choices import get_choice_label
    entry = get_object_or_404(CashFlowEntry, pk=pk)
    sections = [
        {"heading": "Entry Details", "type": "info", "rows": [
            ("Description", entry.description),
            ("Amount", f"${entry.amount:,.2f}"),
            ("Type", entry.get_entry_type_display()),
            ("Category", get_choice_label("cashflow_category", entry.category) if entry.category else "-"),
            ("Date", entry.date.strftime("%B %d, %Y")),
            ("Projected", "Yes" if entry.is_projected else "No"),
            ("Recurring", f"Yes ({entry.get_recurrence_rule_display()})" if entry.is_recurring else "No"),
        ]},
    ]
    links = []
    if entry.related_stakeholder:
        links.append(("Stakeholder", entry.related_stakeholder.name))
    if entry.related_property:
        links.append(("Property", entry.related_property.name))
    if entry.related_loan:
        links.append(("Loan", entry.related_loan.name))
    if entry.related_investment:
        links.append(("Investment", entry.related_investment.name))
    if links:
        sections.append({"heading": "Related Entities", "type": "info", "rows": links})
    if entry.notes_text:
        sections.append({"heading": "Notes", "type": "text", "content": entry.notes_text})
    return render_pdf(request, f"cashflow-{entry.pk}", entry.description, sections=sections)


def bulk_delete(request):
    if request.method == "POST":
        pks = request.POST.getlist("selected")
        count = CashFlowEntry.objects.filter(pk__in=pks).count()
        if "confirm" not in request.POST:
            from django.urls import reverse
            return render(request, "partials/_bulk_confirm_delete.html", {
                "count": count, "selected_pks": pks,
                "action_url": reverse("cashflow:bulk_delete"),
            })
        CashFlowEntry.objects.filter(pk__in=pks).delete()
        messages.success(request, f"{count} entry(ies) deleted.")
    return redirect("cashflow:list")


def bulk_export_csv(request):
    from config.export import export_csv as do_export
    pks = request.GET.getlist("selected")
    qs = CashFlowEntry.objects.filter(pk__in=pks) if pks else CashFlowEntry.objects.none()
    fields = [
        ("date", "Date"),
        ("description", "Description"),
        ("entry_type", "Type"),
        ("category", "Category"),
        ("amount", "Amount"),
        ("is_projected", "Projected"),
    ]
    return do_export(qs, fields, "cashflow_selected")


# --- HTMX inline cashflow for detail pages ---

def _inline_cashflow_context(qs, entity_field, entity, delete_url_name):
    """Build context for inline cashflow list partials."""
    entries = qs.order_by("-date")
    totals = qs.aggregate(
        inflows=Sum("amount", filter=Q(entry_type="inflow"), default=Decimal("0")),
        outflows=Sum("amount", filter=Q(entry_type="outflow"), default=Decimal("0")),
    )
    return {
        "cashflow_entries": entries,
        "cashflow_inflows": totals["inflows"],
        "cashflow_outflows": totals["outflows"],
        "cashflow_net": totals["inflows"] - totals["outflows"],
        entity_field: entity,
        "delete_url_name": delete_url_name,
    }


def inline_cashflow_add(request, model_class, fk_field, entity_field, pk):
    """Generic HTMX inline cashflow add for any related entity."""
    from django.urls import reverse
    entity = get_object_or_404(model_class, pk=pk)
    add_url_name = f"cashflow:{entity_field}_cashflow_add"
    delete_url_name = f"cashflow:{entity_field}_cashflow_delete"
    if request.method == "POST":
        form = InlineCashFlowForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            setattr(entry, fk_field, entity)
            entry.save()
            qs = CashFlowEntry.objects.filter(**{fk_field: entity})
            return render(request, "cashflow/partials/_inline_cashflow_list.html",
                          _inline_cashflow_context(qs, entity_field, entity, delete_url_name))
    else:
        form = InlineCashFlowForm(initial={"date": timezone.localdate()})
    add_url = reverse(add_url_name, args=[pk])
    return render(request, "cashflow/partials/_inline_cashflow_form.html",
                  {"form": form, entity_field: entity, "add_url": add_url})


def inline_cashflow_delete(request, fk_field, pk):
    """Generic HTMX inline cashflow delete."""
    entry = get_object_or_404(CashFlowEntry, pk=pk)
    entity = getattr(entry, fk_field)
    entity_field = fk_field.replace("related_", "")
    delete_url_name = f"cashflow:{entity_field}_cashflow_delete"
    if request.method == "POST":
        entry.delete()
    qs = CashFlowEntry.objects.filter(**{fk_field: entity})
    return render(request, "cashflow/partials/_inline_cashflow_list.html",
                  _inline_cashflow_context(qs, entity_field, entity, delete_url_name))


# Concrete wrappers for each entity type

def property_cashflow_add(request, pk):
    from assets.models import RealEstate
    return inline_cashflow_add(request, RealEstate, "related_property", "property", pk)


def property_cashflow_delete(request, pk):
    return inline_cashflow_delete(request, "related_property", pk)


def loan_cashflow_add(request, pk):
    from assets.models import Loan
    return inline_cashflow_add(request, Loan, "related_loan", "loan", pk)


def loan_cashflow_delete(request, pk):
    return inline_cashflow_delete(request, "related_loan", pk)


def investment_cashflow_add(request, pk):
    from assets.models import Investment
    return inline_cashflow_add(request, Investment, "related_investment", "investment", pk)


def investment_cashflow_delete(request, pk):
    return inline_cashflow_delete(request, "related_investment", pk)


def stakeholder_cashflow_add(request, pk):
    from stakeholders.models import Stakeholder
    return inline_cashflow_add(request, Stakeholder, "related_stakeholder", "stakeholder", pk)


def stakeholder_cashflow_delete(request, pk):
    return inline_cashflow_delete(request, "related_stakeholder", pk)
