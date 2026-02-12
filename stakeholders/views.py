from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from django.views.decorators.http import require_POST

from dashboard.choices import get_choice_label, get_choices
from .forms import ContactLogForm, EmployeeAssignForm, StakeholderForm, StakeholderPropertyForm, StakeholderInvestmentForm, StakeholderLoanForm, StakeholderTabForm
from .models import ContactLog, Relationship, Stakeholder, StakeholderTab


def _get_tab_config():
    """Build dynamic tab config from StakeholderTab + computed Other tab."""
    tabs = list(StakeholderTab.objects.all())
    # Collect all entity_types claimed by user tabs (excluding builtins)
    claimed = set()
    for tab in tabs:
        if not tab.is_builtin:
            claimed.update(tab.entity_types)

    # Get all active entity_type values (excluding "firm")
    all_types = {v for v, _label in get_choices("entity_type") if v != "firm"}
    unclaimed = all_types - claimed

    result = []
    for tab in tabs:
        result.append({
            "key": tab.key,
            "label": tab.label,
            "types": tab.entity_types,
            "is_builtin": tab.is_builtin,
            "pk": tab.pk,
        })

    # Add dynamic "Other" tab if unclaimed types exist
    if unclaimed:
        result.append({
            "key": "other",
            "label": "Other",
            "types": sorted(unclaimed),
            "is_builtin": False,
            "pk": None,  # dynamic, not stored
        })

    return result


class StakeholderListView(ListView):
    model = Stakeholder
    template_name = "stakeholders/stakeholder_list.html"
    context_object_name = "stakeholders"
    paginate_by = 25

    def get_tab_config(self):
        if not hasattr(self, "_tab_config"):
            self._tab_config = _get_tab_config()
        return self._tab_config

    def get_current_tab(self):
        tab = self.request.GET.get("tab", "all")
        valid_keys = {t["key"] for t in self.get_tab_config()}
        return tab if tab in valid_keys else "all"

    def _get_tab_types(self, tab_key):
        for t in self.get_tab_config():
            if t["key"] == tab_key:
                return t["types"]
        return []

    def get_queryset(self):
        tab = self.get_current_tab()

        # Firms tab is handled separately (card layout, no table queryset needed)
        if tab == "firms":
            return Stakeholder.objects.none()

        qs = super().get_queryset().select_related("parent_organization")

        # Tab-specific filtering
        if tab == "all":
            pass  # Show everyone
        else:
            tab_types = self._get_tab_types(tab)
            if tab_types:
                qs = qs.filter(entity_type__in=tab_types, parent_organization__isnull=True)
            else:
                # Tab with no entity_types configured — show nothing
                return qs.none()

        # Search
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)

        # Type filter (only on "all" tab)
        if tab == "all":
            entity_types = [t for t in self.request.GET.getlist("type") if t]
            if entity_types:
                qs = qs.filter(entity_type__in=entity_types)

        # Sorting
        ALLOWED_SORTS = {"name", "entity_type", "organization", "trust_rating", "risk_rating"}
        sort = self.request.GET.get("sort", "")
        if sort in ALLOWED_SORTS:
            direction = "" if self.request.GET.get("dir") == "asc" else "-"
            qs = qs.order_by(f"{direction}{sort}")
        return qs

    def get_firms_queryset(self):
        """Get firms with prefetched employees, optionally filtered by search."""
        qs = Stakeholder.objects.filter(entity_type="firm").prefetch_related("employees")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(employees__name__icontains=q)).distinct()
        return qs

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["stakeholders/partials/_tab_content.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tab = self.get_current_tab()
        tab_config = self.get_tab_config()
        ctx["current_tab"] = tab
        ctx["search_query"] = self.request.GET.get("q", "")
        ctx["entity_types"] = get_choices("entity_type")
        ctx["entity_type_choices"] = get_choices("entity_type")
        ctx["selected_type"] = self.request.GET.get("type", "")
        ctx["selected_types"] = self.request.GET.getlist("type")
        ctx["current_sort"] = self.request.GET.get("sort", "")
        ctx["current_dir"] = self.request.GET.get("dir", "")

        # Tab counts
        total = Stakeholder.objects.count()
        non_employees = Stakeholder.objects.filter(parent_organization__isnull=True)
        ctx["total_count"] = total
        tab_counts = {}
        for t in tab_config:
            if t["key"] == "all":
                tab_counts["all"] = total
            elif t["key"] == "firms":
                tab_counts["firms"] = Stakeholder.objects.filter(entity_type="firm").count()
            elif t["types"]:
                tab_counts[t["key"]] = non_employees.filter(entity_type__in=t["types"]).count()
            else:
                tab_counts[t["key"]] = 0
        ctx["tab_counts"] = tab_counts

        # Build tabs list for template iteration
        ctx["tabs"] = [
            {"key": t["key"], "label": t["label"], "count": tab_counts.get(t["key"], 0)}
            for t in tab_config
        ]

        # Firms data for firms tab
        if tab == "firms":
            ctx["firms"] = self.get_firms_queryset()

        return ctx


class StakeholderCreateView(CreateView):
    model = Stakeholder
    form_class = StakeholderForm
    template_name = "stakeholders/stakeholder_form.html"

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("parent_organization"):
            initial["parent_organization"] = self.request.GET["parent_organization"]
        return initial

    def form_valid(self, form):
        messages.success(self.request, "Stakeholder created.")
        return super().form_valid(form)


class StakeholderDetailView(DetailView):
    model = Stakeholder
    template_name = "stakeholders/stakeholder_detail.html"
    context_object_name = "stakeholder"

    def get_context_data(self, **kwargs):
        from cashflow.models import CashFlowEntry
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx["contact_logs"] = obj.contact_logs.all()[:10]
        ctx["contact_log_form"] = ContactLogForm()

        # All related entities (no limit for tabs view)
        ctx["all_tasks"] = obj.tasks.all()
        ctx["all_notes"] = obj.notes.all()
        ctx["all_legal_matters"] = obj.legal_matters.all()

        # Properties, investments, loans via through models
        from assets.models import PropertyOwnership, InvestmentParticipant, LoanParty
        ctx["property_ownerships"] = PropertyOwnership.objects.filter(stakeholder=obj).select_related("property")
        ctx["investment_participants"] = InvestmentParticipant.objects.filter(stakeholder=obj).select_related("investment")
        ctx["loan_parties"] = LoanParty.objects.filter(stakeholder=obj).select_related("loan")
        ctx["all_cashflow"] = CashFlowEntry.objects.filter(related_stakeholder=obj)

        # Firm/employee hierarchy
        ctx["employees"] = obj.employees.all() if obj.entity_type == "firm" else None

        # Relationships
        ctx["relationships_from"] = obj.relationships_from.select_related("to_stakeholder").all()
        ctx["relationships_to"] = obj.relationships_to.select_related("from_stakeholder").all()

        # Counts for tab badges
        employee_count = ctx["employees"].count() if ctx["employees"] is not None else 0
        ctx["counts"] = {
            "stakeholders": ctx["relationships_from"].count() + ctx["relationships_to"].count(),
            "properties": ctx["property_ownerships"].count(),
            "investments": ctx["investment_participants"].count(),
            "loans": ctx["loan_parties"].count(),
            "legal_matters": ctx["all_legal_matters"].count(),
            "tasks": ctx["all_tasks"].count(),
            "notes": ctx["all_notes"].count(),
            "cashflow": ctx["all_cashflow"].count(),
            "employees": employee_count,
        }

        return ctx


class StakeholderUpdateView(UpdateView):
    model = Stakeholder
    form_class = StakeholderForm
    template_name = "stakeholders/stakeholder_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Stakeholder updated.")
        return super().form_valid(form)


class StakeholderDeleteView(DeleteView):
    model = Stakeholder
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("stakeholders:list")

    def form_valid(self, form):
        messages.success(self.request, f'Stakeholder "{self.object}" deleted.')
        return super().form_valid(form)


def export_csv(request):
    from legacy.export import export_csv as do_export
    qs = Stakeholder.objects.select_related("parent_organization").all()
    fields = [
        ("name", "Name"),
        ("entity_type", "Type"),
        ("email", "Email"),
        ("phone", "Phone"),
        ("organization", "Organization"),
        ("parent_organization__name", "Firm"),
        ("trust_rating", "Trust Rating"),
        ("risk_rating", "Risk Rating"),
    ]
    return do_export(qs, fields, "stakeholders")


def export_pdf_detail(request, pk):
    from legacy.pdf_export import render_pdf
    s = get_object_or_404(Stakeholder, pk=pk)
    firm_name = s.parent_organization.name if s.parent_organization else None
    sections = [
        {"heading": "Contact Information", "type": "info", "rows": [
            ("Email", s.email or "N/A"),
            ("Phone", s.phone or "N/A"),
            ("Organization", s.organization or "N/A"),
            ("Firm", firm_name or "N/A"),
            ("Trust Rating", f"{s.trust_rating}/5" if s.trust_rating else "N/A"),
            ("Risk Rating", f"{s.risk_rating}/5" if s.risk_rating else "N/A"),
        ]},
    ]
    # Team members for firms
    if s.entity_type == "firm":
        employees = s.employees.all()
        if employees:
            sections.append({"heading": "Team Members", "type": "table",
                             "headers": ["Name", "Type", "Email", "Phone"],
                             "rows": [[e.name, get_choice_label("entity_type", e.entity_type),
                                       e.email or "-", e.phone or "-"] for e in employees]})
    if s.notes_text:
        sections.append({"heading": "Notes", "type": "text", "content": s.notes_text})
    logs = s.contact_logs.all()
    if logs:
        sections.append({"heading": "Contact Log", "type": "table",
                         "headers": ["Date", "Method", "Summary", "Follow-up"],
                         "rows": [[l.date.strftime("%b %d, %Y"), get_choice_label("contact_method", l.method),
                                   l.summary[:80], "Yes" if l.follow_up_needed else "No"] for l in logs]})
    rels_from = s.relationships_from.select_related("to_stakeholder").all()
    rels_to = s.relationships_to.select_related("from_stakeholder").all()
    if rels_from or rels_to:
        rows = [[r.to_stakeholder.name, r.relationship_type, "Outgoing"] for r in rels_from if r.to_stakeholder]
        rows += [[r.from_stakeholder.name, r.relationship_type, "Incoming"] for r in rels_to if r.from_stakeholder]
        sections.append({"heading": "Relationships", "type": "table",
                         "headers": ["Name", "Relationship", "Direction"], "rows": rows})
    tasks = s.tasks.exclude(status="complete")
    if tasks:
        sections.append({"heading": "Active Tasks", "type": "table",
                         "headers": ["Title", "Status", "Priority", "Due Date"],
                         "rows": [[t.title, t.get_status_display(), t.get_priority_display(),
                                   t.due_date.strftime("%b %d, %Y") if t.due_date else "-"] for t in tasks]})
    notes = s.notes.all()
    if notes:
        sections.append({"heading": "Recent Notes", "type": "table",
                         "headers": ["Title", "Type", "Date"],
                         "rows": [[n.title, get_choice_label("note_type", n.note_type), n.date.strftime("%b %d, %Y")] for n in notes]})
    subtitle = f"{get_choice_label('entity_type', s.entity_type)}"
    if s.parent_organization:
        subtitle += f" — {s.parent_organization.name}"
    elif s.organization:
        subtitle += f" — {s.organization}"
    return render_pdf(request, f"stakeholder-{s.pk}", s.name, subtitle, sections)


def contact_log_add(request, pk):
    stakeholder = get_object_or_404(Stakeholder, pk=pk)
    if request.method == "POST":
        form = ContactLogForm(request.POST)
        if form.is_valid():
            log = form.save(commit=False)
            log.stakeholder = stakeholder
            log.save()
            return render(request, "stakeholders/partials/_contact_log_list.html",
                          {"contact_logs": stakeholder.contact_logs.all()[:10], "stakeholder": stakeholder})
    else:
        form = ContactLogForm()
    return render(request, "stakeholders/partials/_contact_log_form.html",
                  {"form": form, "stakeholder": stakeholder})


def contact_log_delete(request, pk):
    log = get_object_or_404(ContactLog, pk=pk)
    stakeholder = log.stakeholder
    if request.method == "POST":
        log.delete()
    if stakeholder:
        return render(request, "stakeholders/partials/_contact_log_list.html",
                      {"contact_logs": stakeholder.contact_logs.all()[:10], "stakeholder": stakeholder})
    return HttpResponse(status=204)


def relationship_graph_data(request, pk):
    """JSON endpoint for Cytoscape.js relationship graph - shows all connected entities."""
    from assets.models import RealEstate, Investment, Loan
    from legal.models import LegalMatter
    from tasks.models import Task
    from cashflow.models import CashFlowEntry

    center = get_object_or_404(Stakeholder, pk=pk)
    nodes = {}
    edges = []

    def add_node(entity_id, name, entity_type, shape, url, is_center=False):
        """Add a node to the graph with type-specific styling."""
        if entity_id not in nodes:
            nodes[entity_id] = {
                "id": entity_id,
                "name": name,
                "entity_type": entity_type,
                "shape": shape,
                "url": url,
                "is_center": is_center,
            }

    # Center stakeholder
    add_node(f"s-{center.pk}", center.name, get_choice_label("entity_type", center.entity_type),
             "ellipse", center.get_absolute_url(), is_center=True)

    # Firm/employee hierarchy edges
    if center.parent_organization:
        firm = center.parent_organization
        add_node(f"s-{firm.pk}", firm.name, get_choice_label("entity_type", firm.entity_type),
                 "ellipse", firm.get_absolute_url())
        edges.append({"source": f"s-{firm.pk}", "target": f"s-{center.pk}", "label": "employs"})
        # Sibling employees
        for emp in firm.employees.exclude(pk=center.pk):
            add_node(f"s-{emp.pk}", emp.name, get_choice_label("entity_type", emp.entity_type),
                     "ellipse", emp.get_absolute_url())
            edges.append({"source": f"s-{firm.pk}", "target": f"s-{emp.pk}", "label": "employs"})

    for emp in center.employees.all():
        add_node(f"s-{emp.pk}", emp.name, get_choice_label("entity_type", emp.entity_type),
                 "ellipse", emp.get_absolute_url())
        edges.append({"source": f"s-{center.pk}", "target": f"s-{emp.pk}", "label": "employs"})

    # Connected stakeholders (1st degree relationships)
    connected_stakeholder_ids = set()
    for rel in Relationship.objects.filter(from_stakeholder=center).select_related("to_stakeholder"):
        s = rel.to_stakeholder
        if not s:
            continue
        add_node(f"s-{s.pk}", s.name, get_choice_label("entity_type", s.entity_type),
                 "ellipse", s.get_absolute_url())
        connected_stakeholder_ids.add(s.pk)
        edges.append({"source": f"s-{center.pk}", "target": f"s-{s.pk}", "label": rel.relationship_type})

    for rel in Relationship.objects.filter(to_stakeholder=center).select_related("from_stakeholder"):
        s = rel.from_stakeholder
        if not s:
            continue
        add_node(f"s-{s.pk}", s.name, get_choice_label("entity_type", s.entity_type),
                 "ellipse", s.get_absolute_url())
        connected_stakeholder_ids.add(s.pk)
        edges.append({"source": f"s-{s.pk}", "target": f"s-{center.pk}", "label": rel.relationship_type})

    # 2nd degree stakeholder relationships (between connected stakeholders)
    if connected_stakeholder_ids:
        for rel in Relationship.objects.filter(
            from_stakeholder_id__in=connected_stakeholder_ids,
            to_stakeholder_id__in=connected_stakeholder_ids,
        ).select_related("from_stakeholder", "to_stakeholder"):
            add_node(f"s-{rel.from_stakeholder.pk}", rel.from_stakeholder.name,
                     get_choice_label("entity_type", rel.from_stakeholder.entity_type),
                     "ellipse", rel.from_stakeholder.get_absolute_url())
            add_node(f"s-{rel.to_stakeholder.pk}", rel.to_stakeholder.name,
                     get_choice_label("entity_type", rel.to_stakeholder.entity_type),
                     "ellipse", rel.to_stakeholder.get_absolute_url())
            edges.append({"source": f"s-{rel.from_stakeholder.pk}",
                         "target": f"s-{rel.to_stakeholder.pk}", "label": rel.relationship_type})

    # Properties (via ownership)
    for ownership in center.property_ownerships.all():
        prop = ownership.property
        add_node(f"p-{prop.pk}", prop.name, "Property", "roundrectangle", prop.get_absolute_url())
        label = ownership.role or "owns"
        if ownership.ownership_percentage:
            label += f" ({ownership.ownership_percentage}%)"
        edges.append({"source": f"s-{center.pk}", "target": f"p-{prop.pk}", "label": label})

    # Investments (via participation)
    for participation in center.investment_participations.all():
        inv = participation.investment
        add_node(f"i-{inv.pk}", inv.name, "Investment", "diamond", inv.get_absolute_url())
        label = participation.role or "invests"
        if participation.ownership_percentage:
            label += f" ({participation.ownership_percentage}%)"
        edges.append({"source": f"s-{center.pk}", "target": f"i-{inv.pk}", "label": label})

    # Loans (via loan parties)
    for party in center.loan_parties.all():
        loan = party.loan
        add_node(f"l-{loan.pk}", loan.name, "Loan", "triangle", loan.get_absolute_url())
        label = party.role or "party"
        if party.ownership_percentage:
            label += f" ({party.ownership_percentage}%)"
        edges.append({"source": f"s-{center.pk}", "target": f"l-{loan.pk}", "label": label})

    # Legal matters (as attorney or related party)
    for matter in center.legal_matters.all():
        add_node(f"m-{matter.pk}", matter.title, "Legal Matter", "hexagon", matter.get_absolute_url())
        edges.append({"source": f"s-{center.pk}", "target": f"m-{matter.pk}", "label": "involved"})

    for matter in center.legal_matters_as_attorney.all():
        node_id = f"m-{matter.pk}"
        if node_id not in nodes:
            add_node(node_id, matter.title, "Legal Matter", "hexagon", matter.get_absolute_url())
        edges.append({"source": f"s-{center.pk}", "target": node_id, "label": "attorney"})

    # High-priority active tasks
    for task in center.tasks.filter(priority__in=["critical", "high"]).exclude(status="complete")[:5]:
        add_node(f"t-{task.pk}", task.title, "Task", "star", task.get_absolute_url())
        edges.append({"source": f"s-{center.pk}", "target": f"t-{task.pk}", "label": task.get_priority_display()})

    return JsonResponse({"nodes": list(nodes.values()), "edges": edges})


def bulk_delete(request):
    if request.method == "POST":
        pks = request.POST.getlist("selected")
        count = Stakeholder.objects.filter(pk__in=pks).count()
        if "confirm" not in request.POST:
            from django.urls import reverse
            return render(request, "partials/_bulk_confirm_delete.html", {
                "count": count, "selected_pks": pks,
                "action_url": reverse("stakeholders:bulk_delete"),
            })
        Stakeholder.objects.filter(pk__in=pks).delete()
        messages.success(request, f"{count} stakeholder(s) deleted.")
    return redirect("stakeholders:list")


def bulk_export_csv(request):
    from legacy.export import export_csv as do_export
    pks = request.GET.getlist("selected")
    qs = Stakeholder.objects.filter(pk__in=pks).select_related("parent_organization") if pks else Stakeholder.objects.none()
    fields = [
        ("name", "Name"),
        ("entity_type", "Type"),
        ("email", "Email"),
        ("phone", "Phone"),
        ("organization", "Organization"),
        ("parent_organization__name", "Firm"),
        ("trust_rating", "Trust Rating"),
        ("risk_rating", "Risk Rating"),
    ]
    return do_export(qs, fields, "stakeholders_selected")


# --- Inline asset ownership management (stakeholder-side) ---

def property_ownership_add(request, pk):
    from assets.models import PropertyOwnership
    stakeholder = get_object_or_404(Stakeholder, pk=pk)
    if request.method == "POST":
        form = StakeholderPropertyForm(request.POST)
        if form.is_valid():
            ownership = form.save(commit=False)
            ownership.stakeholder = stakeholder
            ownership.save()
            return render(request, "stakeholders/partials/_sh_ownership_list.html",
                          {"ownerships": PropertyOwnership.objects.filter(stakeholder=stakeholder).select_related("property"),
                           "stakeholder": stakeholder})
    else:
        form = StakeholderPropertyForm()
    return render(request, "stakeholders/partials/_sh_ownership_form.html",
                  {"form": form, "stakeholder": stakeholder})


def property_ownership_delete(request, pk):
    from assets.models import PropertyOwnership
    ownership = get_object_or_404(PropertyOwnership, pk=pk)
    stakeholder = ownership.stakeholder
    if request.method == "POST":
        ownership.delete()
    return render(request, "stakeholders/partials/_sh_ownership_list.html",
                  {"ownerships": PropertyOwnership.objects.filter(stakeholder=stakeholder).select_related("property"),
                   "stakeholder": stakeholder})


def investment_participant_add(request, pk):
    from assets.models import InvestmentParticipant
    stakeholder = get_object_or_404(Stakeholder, pk=pk)
    if request.method == "POST":
        form = StakeholderInvestmentForm(request.POST)
        if form.is_valid():
            participant = form.save(commit=False)
            participant.stakeholder = stakeholder
            participant.save()
            return render(request, "stakeholders/partials/_sh_participant_list.html",
                          {"participants": InvestmentParticipant.objects.filter(stakeholder=stakeholder).select_related("investment"),
                           "stakeholder": stakeholder})
    else:
        form = StakeholderInvestmentForm()
    return render(request, "stakeholders/partials/_sh_participant_form.html",
                  {"form": form, "stakeholder": stakeholder})


def investment_participant_delete(request, pk):
    from assets.models import InvestmentParticipant
    participant = get_object_or_404(InvestmentParticipant, pk=pk)
    stakeholder = participant.stakeholder
    if request.method == "POST":
        participant.delete()
    return render(request, "stakeholders/partials/_sh_participant_list.html",
                  {"participants": InvestmentParticipant.objects.filter(stakeholder=stakeholder).select_related("investment"),
                   "stakeholder": stakeholder})


def loan_party_add(request, pk):
    from assets.models import LoanParty
    stakeholder = get_object_or_404(Stakeholder, pk=pk)
    if request.method == "POST":
        form = StakeholderLoanForm(request.POST)
        if form.is_valid():
            party = form.save(commit=False)
            party.stakeholder = stakeholder
            party.save()
            return render(request, "stakeholders/partials/_sh_party_list.html",
                          {"parties": LoanParty.objects.filter(stakeholder=stakeholder).select_related("loan"),
                           "stakeholder": stakeholder})
    else:
        form = StakeholderLoanForm()
    return render(request, "stakeholders/partials/_sh_party_form.html",
                  {"form": form, "stakeholder": stakeholder})


def loan_party_delete(request, pk):
    from assets.models import LoanParty
    party = get_object_or_404(LoanParty, pk=pk)
    stakeholder = party.stakeholder
    if request.method == "POST":
        party.delete()
    return render(request, "stakeholders/partials/_sh_party_list.html",
                  {"parties": LoanParty.objects.filter(stakeholder=stakeholder).select_related("loan"),
                   "stakeholder": stakeholder})


# --- Inline employee management (firm detail) ---

def _employee_list_context(firm):
    return {
        "employees": firm.employees.all(),
        "stakeholder": firm,
    }


def employee_add(request, pk):
    firm = get_object_or_404(Stakeholder, pk=pk, entity_type="firm")
    if request.method == "POST":
        form = EmployeeAssignForm(request.POST, firm=firm)
        if form.is_valid():
            emp = form.cleaned_data["stakeholder"]
            emp.parent_organization = firm
            emp.save()
            return render(request, "stakeholders/partials/_employee_list.html",
                          _employee_list_context(firm))
    else:
        form = EmployeeAssignForm(firm=firm)
    return render(request, "stakeholders/partials/_employee_form.html",
                  {"form": form, "stakeholder": firm})


@require_POST
def employee_remove(request, pk):
    emp = get_object_or_404(Stakeholder, pk=pk)
    firm = emp.parent_organization
    emp.parent_organization = None
    emp.save()
    if firm:
        return render(request, "stakeholders/partials/_employee_list.html",
                      _employee_list_context(firm))
    return HttpResponse("")


# --- Inline entity type editing ---

@require_POST
def inline_update_type(request, pk):
    stakeholder = get_object_or_404(Stakeholder.objects.select_related("parent_organization"), pk=pk)
    value = request.POST.get("entity_type", "")
    valid_values = {v for v, _l in get_choices("entity_type")}
    if value not in valid_values:
        return HttpResponse(status=400)
    stakeholder.entity_type = value
    stakeholder.save()
    return render(request, "stakeholders/partials/_stakeholder_row.html", {
        "s": stakeholder,
        "entity_type_choices": get_choices("entity_type"),
    })


# --- Tab management views ---

def tab_settings(request):
    tabs = StakeholderTab.objects.all()
    return render(request, "stakeholders/tab_settings.html", {"tabs": tabs})


def tab_add(request):
    if request.method == "POST":
        form = StakeholderTabForm(request.POST)
        if form.is_valid():
            form.save()
            tabs = StakeholderTab.objects.all()
            return render(request, "stakeholders/partials/_tab_settings_list.html", {"tabs": tabs})
    else:
        form = StakeholderTabForm()
    return render(request, "stakeholders/partials/_tab_settings_form.html", {"form": form})


def tab_edit(request, pk):
    tab = get_object_or_404(StakeholderTab, pk=pk)
    if tab.is_builtin:
        return HttpResponse(status=403)
    if request.method == "POST":
        form = StakeholderTabForm(request.POST, instance=tab)
        if form.is_valid():
            form.save()
            tabs = StakeholderTab.objects.all()
            return render(request, "stakeholders/partials/_tab_settings_list.html", {"tabs": tabs})
    else:
        form = StakeholderTabForm(instance=tab)
    from django.urls import reverse
    return render(request, "stakeholders/partials/_tab_settings_form.html", {
        "form": form,
        "form_url": reverse("stakeholders:tab_edit", args=[pk]),
        "edit_mode": True,
    })


def tab_delete(request, pk):
    tab = get_object_or_404(StakeholderTab, pk=pk)
    if tab.is_builtin:
        return HttpResponse(status=403)
    if request.method == "POST":
        tab.delete()
    tabs = StakeholderTab.objects.all()
    return render(request, "stakeholders/partials/_tab_settings_list.html", {"tabs": tabs})
