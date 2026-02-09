from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from dashboard.choices import get_choice_label, get_choices
from .forms import ContactLogForm, StakeholderForm
from .models import ContactLog, Relationship, Stakeholder


class StakeholderListView(ListView):
    model = Stakeholder
    template_name = "stakeholders/stakeholder_list.html"
    context_object_name = "stakeholders"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        entity_types = self.request.GET.getlist("type")
        if entity_types:
            qs = qs.filter(entity_type__in=entity_types)
        ALLOWED_SORTS = {"name", "entity_type", "organization", "trust_rating", "risk_rating"}
        sort = self.request.GET.get("sort", "")
        if sort in ALLOWED_SORTS:
            direction = "" if self.request.GET.get("dir") == "asc" else "-"
            qs = qs.order_by(f"{direction}{sort}")
        return qs

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["stakeholders/partials/_stakeholder_table_rows.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search_query"] = self.request.GET.get("q", "")
        ctx["entity_types"] = get_choices("entity_type")
        ctx["selected_type"] = self.request.GET.get("type", "")
        ctx["selected_types"] = self.request.GET.getlist("type")
        ctx["current_sort"] = self.request.GET.get("sort", "")
        ctx["current_dir"] = self.request.GET.get("dir", "")
        return ctx


class StakeholderCreateView(CreateView):
    model = Stakeholder
    form_class = StakeholderForm
    template_name = "stakeholders/stakeholder_form.html"

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
        ctx["all_properties"] = obj.properties.all()
        ctx["all_investments"] = obj.investments.all()
        ctx["all_loans"] = obj.loans_as_lender.all()
        ctx["all_cashflow"] = CashFlowEntry.objects.filter(related_stakeholder=obj)

        # Relationships
        ctx["relationships_from"] = obj.relationships_from.select_related("to_stakeholder").all()
        ctx["relationships_to"] = obj.relationships_to.select_related("from_stakeholder").all()

        # Counts for tab badges
        ctx["counts"] = {
            "stakeholders": ctx["relationships_from"].count() + ctx["relationships_to"].count(),
            "properties": ctx["all_properties"].count(),
            "investments": ctx["all_investments"].count(),
            "loans": ctx["all_loans"].count(),
            "legal_matters": ctx["all_legal_matters"].count(),
            "tasks": ctx["all_tasks"].count(),
            "notes": ctx["all_notes"].count(),
            "cashflow": ctx["all_cashflow"].count(),
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
    qs = Stakeholder.objects.all()
    fields = [
        ("name", "Name"),
        ("entity_type", "Type"),
        ("email", "Email"),
        ("phone", "Phone"),
        ("organization", "Organization"),
        ("trust_rating", "Trust Rating"),
        ("risk_rating", "Risk Rating"),
    ]
    return do_export(qs, fields, "stakeholders")


def export_pdf_detail(request, pk):
    from legacy.pdf_export import render_pdf
    s = get_object_or_404(Stakeholder, pk=pk)
    sections = [
        {"heading": "Contact Information", "type": "info", "rows": [
            ("Email", s.email or "N/A"),
            ("Phone", s.phone or "N/A"),
            ("Organization", s.organization or "N/A"),
            ("Trust Rating", f"{s.trust_rating}/5" if s.trust_rating else "N/A"),
            ("Risk Rating", f"{s.risk_rating}/5" if s.risk_rating else "N/A"),
        ]},
    ]
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
        rows = [[r.to_stakeholder.name, r.relationship_type, "Outgoing"] for r in rels_from]
        rows += [[r.from_stakeholder.name, r.relationship_type, "Incoming"] for r in rels_to]
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
    if s.organization:
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
    return render(request, "stakeholders/partials/_contact_log_list.html",
                  {"contact_logs": stakeholder.contact_logs.all()[:10], "stakeholder": stakeholder})


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

    # Connected stakeholders (1st degree relationships)
    connected_stakeholder_ids = set()
    for rel in Relationship.objects.filter(from_stakeholder=center).select_related("to_stakeholder"):
        s = rel.to_stakeholder
        add_node(f"s-{s.pk}", s.name, get_choice_label("entity_type", s.entity_type),
                 "ellipse", s.get_absolute_url())
        connected_stakeholder_ids.add(s.pk)
        edges.append({"source": f"s-{center.pk}", "target": f"s-{s.pk}", "label": rel.relationship_type})

    for rel in Relationship.objects.filter(to_stakeholder=center).select_related("from_stakeholder"):
        s = rel.from_stakeholder
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

    # Properties
    for prop in center.properties.all():
        add_node(f"p-{prop.pk}", prop.name, "Property", "roundrectangle", prop.get_absolute_url())
        edges.append({"source": f"s-{center.pk}", "target": f"p-{prop.pk}", "label": "owns"})

    # Investments
    for inv in center.investments.all():
        add_node(f"i-{inv.pk}", inv.name, "Investment", "diamond", inv.get_absolute_url())
        edges.append({"source": f"s-{center.pk}", "target": f"i-{inv.pk}", "label": "invests"})

    # Loans (as lender)
    for loan in center.loans_as_lender.all():
        add_node(f"l-{loan.pk}", loan.name, "Loan", "triangle", loan.get_absolute_url())
        edges.append({"source": f"s-{center.pk}", "target": f"l-{loan.pk}", "label": "lender"})

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
    qs = Stakeholder.objects.filter(pk__in=pks) if pks else Stakeholder.objects.none()
    fields = [
        ("name", "Name"),
        ("entity_type", "Type"),
        ("email", "Email"),
        ("phone", "Phone"),
        ("organization", "Organization"),
        ("trust_rating", "Trust Rating"),
        ("risk_rating", "Risk Rating"),
    ]
    return do_export(qs, fields, "stakeholders_selected")
