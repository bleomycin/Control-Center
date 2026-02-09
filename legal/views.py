from django.contrib import messages
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import EvidenceForm, LegalMatterForm
from .models import Evidence, LegalMatter


class LegalMatterListView(ListView):
    model = LegalMatter
    template_name = "legal/legal_list.html"
    context_object_name = "matters"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(title__icontains=q)
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        matter_type = self.request.GET.get("type")
        if matter_type:
            qs = qs.filter(matter_type=matter_type)
        return qs

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["legal/partials/_legal_table_rows.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search_query"] = self.request.GET.get("q", "")
        ctx["status_choices"] = LegalMatter.STATUS_CHOICES
        ctx["type_choices"] = LegalMatter.MATTER_TYPE_CHOICES
        ctx["selected_status"] = self.request.GET.get("status", "")
        ctx["selected_type"] = self.request.GET.get("type", "")
        return ctx


class LegalMatterCreateView(CreateView):
    model = LegalMatter
    form_class = LegalMatterForm
    template_name = "legal/legal_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Legal matter created.")
        return super().form_valid(form)


class LegalMatterDetailView(DetailView):
    model = LegalMatter
    template_name = "legal/legal_detail.html"
    context_object_name = "matter"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        obj = self.object
        ctx["evidence_list"] = obj.evidence.all()
        ctx["evidence_form"] = EvidenceForm()
        ctx["tasks"] = obj.tasks.exclude(status="complete")[:5]
        ctx["notes"] = obj.notes.all()[:5]
        return ctx


class LegalMatterUpdateView(UpdateView):
    model = LegalMatter
    form_class = LegalMatterForm
    template_name = "legal/legal_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Legal matter updated.")
        return super().form_valid(form)


class LegalMatterDeleteView(DeleteView):
    model = LegalMatter
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("legal:list")

    def form_valid(self, form):
        messages.success(self.request, f'Legal matter "{self.object}" deleted.')
        return super().form_valid(form)


def export_csv(request):
    from blaine.export import export_csv as do_export
    qs = LegalMatter.objects.all()
    fields = [
        ("title", "Title"),
        ("case_number", "Case Number"),
        ("matter_type", "Type"),
        ("status", "Status"),
        ("jurisdiction", "Jurisdiction"),
        ("court", "Court"),
        ("filing_date", "Filing Date"),
    ]
    return do_export(qs, fields, "legal_matters")


def export_pdf_detail(request, pk):
    from blaine.pdf_export import render_pdf
    m = get_object_or_404(LegalMatter, pk=pk)
    sections = [
        {"heading": "Case Information", "type": "info", "rows": [
            ("Case Number", m.case_number or "N/A"),
            ("Jurisdiction", m.jurisdiction or "N/A"),
            ("Court", m.court or "N/A"),
            ("Filing Date", m.filing_date.strftime("%b %d, %Y") if m.filing_date else "N/A"),
        ]},
    ]
    if m.description:
        sections.append({"heading": "Description", "type": "text", "content": m.description})
    attorneys = m.attorneys.all()
    if attorneys:
        sections.append({"heading": "Attorneys", "type": "table",
                         "headers": ["Name", "Organization", "Email", "Phone"],
                         "rows": [[a.name, a.organization or "-", a.email or "-", a.phone or "-"] for a in attorneys]})
    stakeholders = m.related_stakeholders.all()
    if stakeholders:
        sections.append({"heading": "Related Stakeholders", "type": "table",
                         "headers": ["Name", "Type", "Organization"],
                         "rows": [[s.name, s.get_entity_type_display(), s.organization or "-"] for s in stakeholders]})
    evidence = m.evidence.all()
    if evidence:
        sections.append({"heading": "Evidence", "type": "table",
                         "headers": ["Title", "Type", "Date Obtained"],
                         "rows": [[e.title, e.evidence_type or "-",
                                   e.date_obtained.strftime("%b %d, %Y") if e.date_obtained else "-"] for e in evidence]})
    tasks = m.tasks.exclude(status="complete")
    if tasks:
        sections.append({"heading": "Related Tasks", "type": "table",
                         "headers": ["Title", "Status", "Priority", "Due Date"],
                         "rows": [[t.title, t.get_status_display(), t.get_priority_display(),
                                   t.due_date.strftime("%b %d, %Y") if t.due_date else "-"] for t in tasks]})
    return render_pdf(request, f"legal-matter-{m.pk}", m.title,
                      f"{m.get_matter_type_display()} — {m.get_status_display()}", sections)


def evidence_add(request, pk):
    matter = get_object_or_404(LegalMatter, pk=pk)
    if request.method == "POST":
        form = EvidenceForm(request.POST, request.FILES)
        if form.is_valid():
            ev = form.save(commit=False)
            ev.legal_matter = matter
            ev.save()
            return render(request, "legal/partials/_evidence_list.html",
                          {"evidence_list": matter.evidence.all(), "matter": matter})
    else:
        form = EvidenceForm()
    return render(request, "legal/partials/_evidence_form.html",
                  {"form": form, "matter": matter})


def evidence_delete(request, pk):
    ev = get_object_or_404(Evidence, pk=pk)
    matter = ev.legal_matter
    if request.method == "POST":
        ev.delete()
    return render(request, "legal/partials/_evidence_list.html",
                  {"evidence_list": matter.evidence.all(), "matter": matter})
