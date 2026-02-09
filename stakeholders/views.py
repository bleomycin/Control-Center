from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import ContactLogForm, StakeholderForm
from .models import ContactLog, Stakeholder


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
        entity_type = self.request.GET.get("type")
        if entity_type:
            qs = qs.filter(entity_type=entity_type)
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
