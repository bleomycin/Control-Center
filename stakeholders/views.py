from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

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
        ctx["entity_types"] = Stakeholder.ENTITY_TYPE_CHOICES
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
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx["contact_logs"] = obj.contact_logs.all()[:10]
        ctx["contact_log_form"] = ContactLogForm()
        ctx["tasks"] = obj.tasks.exclude(status="complete")[:5]
        ctx["notes"] = obj.notes.all()[:5]
        ctx["legal_matters"] = obj.legal_matters.all()[:5]
        ctx["properties"] = obj.properties.all()[:5]
        ctx["investments"] = obj.investments.all()[:5]
        ctx["loans"] = obj.loans_as_lender.all()[:5]
        ctx["relationships_from"] = obj.relationships_from.select_related("to_stakeholder").all()
        ctx["relationships_to"] = obj.relationships_to.select_related("from_stakeholder").all()
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
    from blaine.export import export_csv as do_export
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
    from blaine.pdf_export import render_pdf
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
                         "rows": [[l.date.strftime("%b %d, %Y"), l.get_method_display(),
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
                         "rows": [[n.title, n.get_note_type_display(), n.date.strftime("%b %d, %Y")] for n in notes]})
    subtitle = f"{s.get_entity_type_display()}"
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
    """JSON endpoint for Cytoscape.js relationship graph."""
    center = get_object_or_404(Stakeholder, pk=pk)
    nodes = {}
    edges = []

    def add_node(s, is_center=False):
        if s.pk not in nodes:
            nodes[s.pk] = {
                "id": str(s.pk),
                "name": s.name,
                "type": s.get_entity_type_display(),
                "url": s.get_absolute_url(),
                "is_center": is_center,
            }

    add_node(center, is_center=True)

    # Direct relationships (1st degree)
    connected_ids = set()
    for rel in Relationship.objects.filter(from_stakeholder=center).select_related("to_stakeholder"):
        add_node(rel.to_stakeholder)
        connected_ids.add(rel.to_stakeholder.pk)
        edges.append({"source": str(center.pk), "target": str(rel.to_stakeholder.pk), "label": rel.relationship_type})
    for rel in Relationship.objects.filter(to_stakeholder=center).select_related("from_stakeholder"):
        add_node(rel.from_stakeholder)
        connected_ids.add(rel.from_stakeholder.pk)
        edges.append({"source": str(rel.from_stakeholder.pk), "target": str(center.pk), "label": rel.relationship_type})

    # 2nd degree relationships (between connected stakeholders)
    if connected_ids:
        for rel in Relationship.objects.filter(
            from_stakeholder_id__in=connected_ids,
            to_stakeholder_id__in=connected_ids,
        ).select_related("from_stakeholder", "to_stakeholder"):
            add_node(rel.from_stakeholder)
            add_node(rel.to_stakeholder)
            edges.append({"source": str(rel.from_stakeholder.pk), "target": str(rel.to_stakeholder.pk), "label": rel.relationship_type})

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
    from blaine.export import export_csv as do_export
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
