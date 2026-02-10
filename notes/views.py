from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from dashboard.choices import get_choice_label, get_choices
from stakeholders.models import Stakeholder
from .forms import AttachmentForm, NoteForm, QuickNoteForm
from .models import Attachment, Note


def export_csv(request):
    from legacy.export import export_csv as do_export
    qs = Note.objects.all()
    fields = [
        ("title", "Title"),
        ("note_type", "Type"),
        ("date", "Date"),
        ("content", "Content"),
    ]
    return do_export(qs, fields, "notes")


class NoteListView(ListView):
    model = Note
    template_name = "notes/note_list.html"
    context_object_name = "notes"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related(
            "participants", "related_stakeholders",
            "related_legal_matters", "related_properties", "related_tasks",
        ).annotate(attachment_count=Count("attachments"))
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(content__icontains=q))
        note_types = self.request.GET.getlist("type")
        if note_types:
            qs = qs.filter(note_type__in=note_types)
        date_from = self.request.GET.get("date_from")
        if date_from:
            qs = qs.filter(date__date__gte=date_from)
        date_to = self.request.GET.get("date_to")
        if date_to:
            qs = qs.filter(date__date__lte=date_to)
        stakeholder = self.request.GET.get("stakeholder", "").strip()
        if stakeholder:
            qs = qs.filter(
                Q(participants__pk=stakeholder) | Q(related_stakeholders__pk=stakeholder)
            ).distinct()
        ALLOWED_SORTS = {"title", "note_type", "date"}
        sort = self.request.GET.get("sort", "")
        if sort in ALLOWED_SORTS:
            direction = "" if self.request.GET.get("dir") == "asc" else "-"
            qs = qs.order_by(f"{direction}{sort}")
        return qs

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["notes/partials/_note_cards.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search_query"] = self.request.GET.get("q", "")
        ctx["note_types"] = get_choices("note_type")
        ctx["selected_type"] = self.request.GET.get("type", "")
        ctx["date_from"] = self.request.GET.get("date_from", "")
        ctx["date_to"] = self.request.GET.get("date_to", "")
        ctx["selected_types"] = self.request.GET.getlist("type")
        ctx["current_sort"] = self.request.GET.get("sort", "")
        ctx["current_dir"] = self.request.GET.get("dir", "")
        ctx["stakeholders"] = Stakeholder.objects.all().order_by("name")
        ctx["selected_stakeholder"] = self.request.GET.get("stakeholder", "")
        return ctx


class NoteCreateView(CreateView):
    model = Note
    form_class = NoteForm
    template_name = "notes/note_form.html"

    def get_initial(self):
        initial = super().get_initial()
        initial["date"] = timezone.now()
        return initial

    def form_valid(self, form):
        messages.success(self.request, "Note created.")
        return super().form_valid(form)


class NoteDetailView(DetailView):
    model = Note
    template_name = "notes/note_detail.html"
    context_object_name = "note"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["attachment_list"] = self.object.attachments.all()
        ctx["attachment_form"] = AttachmentForm()
        return ctx


class NoteUpdateView(UpdateView):
    model = Note
    form_class = NoteForm
    template_name = "notes/note_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Note updated.")
        return super().form_valid(form)


class NoteDeleteView(DeleteView):
    model = Note
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("notes:list")

    def form_valid(self, form):
        messages.success(self.request, f'Note "{self.object}" deleted.')
        return super().form_valid(form)


def export_pdf_detail(request, pk):
    from legacy.pdf_export import render_pdf
    n = get_object_or_404(Note, pk=pk)
    sections = [
        {"heading": "Content", "type": "text", "content": n.content},
    ]
    participants = n.participants.all()
    if participants:
        sections.append({"heading": "Participants", "type": "table",
                         "headers": ["Name", "Type", "Organization"],
                         "rows": [[p.name, get_choice_label("entity_type", p.entity_type), p.organization or "-"] for p in participants]})
    stakeholders = n.related_stakeholders.all()
    if stakeholders:
        sections.append({"heading": "Related Stakeholders", "type": "table",
                         "headers": ["Name", "Type"],
                         "rows": [[s.name, get_choice_label("entity_type", s.entity_type)] for s in stakeholders]})
    legal_matters = n.related_legal_matters.all()
    if legal_matters:
        sections.append({"heading": "Related Legal Matters", "type": "table",
                         "headers": ["Title", "Status"],
                         "rows": [[m.title, m.get_status_display()] for m in legal_matters]})
    attachments = n.attachments.all()
    if attachments:
        sections.append({"heading": "Attachments", "type": "table",
                         "headers": ["File", "Description", "Uploaded"],
                         "rows": [[a.file.name, a.description or "-", a.uploaded_at.strftime("%b %d, %Y")] for a in attachments]})
    return render_pdf(request, f"note-{n.pk}", n.title,
                      f"{get_choice_label('note_type', n.note_type)} — {n.date.strftime('%b %d, %Y %I:%M %p')}", sections)


def attachment_add(request, pk):
    note = get_object_or_404(Note, pk=pk)
    if request.method == "POST":
        form = AttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            att = form.save(commit=False)
            att.note = note
            att.save()
            return render(request, "notes/partials/_attachment_list.html",
                          {"attachment_list": note.attachments.all(), "note": note})
    else:
        form = AttachmentForm()
    return render(request, "notes/partials/_attachment_form.html",
                  {"form": form, "note": note})


def attachment_delete(request, pk):
    att = get_object_or_404(Attachment, pk=pk)
    note = att.note
    if request.method == "POST":
        att.delete()
    return render(request, "notes/partials/_attachment_list.html",
                  {"attachment_list": note.attachments.all(), "note": note})


def quick_capture(request):
    if request.method == "POST":
        form = QuickNoteForm(request.POST)
        if form.is_valid():
            form.save()
            response = HttpResponse(status=204)
            response["HX-Trigger"] = "closeModal"
            response["HX-Redirect"] = reverse_lazy("notes:list")
            return response
    else:
        form = QuickNoteForm(initial={"date": timezone.now()})
    return render(request, "notes/partials/_quick_capture_form.html", {"form": form})


def bulk_delete(request):
    if request.method == "POST":
        pks = request.POST.getlist("selected")
        count = Note.objects.filter(pk__in=pks).count()
        if "confirm" not in request.POST:
            from django.urls import reverse
            return render(request, "partials/_bulk_confirm_delete.html", {
                "count": count, "selected_pks": pks,
                "action_url": reverse("notes:bulk_delete"),
            })
        Note.objects.filter(pk__in=pks).delete()
        messages.success(request, f"{count} note(s) deleted.")
    return redirect("notes:list")


def bulk_export_csv(request):
    from legacy.export import export_csv as do_export
    pks = request.GET.getlist("selected")
    qs = Note.objects.filter(pk__in=pks) if pks else Note.objects.none()
    fields = [
        ("title", "Title"),
        ("note_type", "Type"),
        ("date", "Date"),
        ("content", "Content"),
    ]
    return do_export(qs, fields, "notes_selected")
