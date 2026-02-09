from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import AttachmentForm, NoteForm, QuickNoteForm
from .models import Attachment, Note


def export_csv(request):
    from blaine.export import export_csv as do_export
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
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(title__icontains=q)
        note_type = self.request.GET.get("type")
        if note_type:
            qs = qs.filter(note_type=note_type)
        return qs

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["notes/partials/_note_table_rows.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search_query"] = self.request.GET.get("q", "")
        ctx["note_types"] = Note.NOTE_TYPE_CHOICES
        ctx["selected_type"] = self.request.GET.get("type", "")
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
    from blaine.pdf_export import render_pdf
    n = get_object_or_404(Note, pk=pk)
    sections = [
        {"heading": "Content", "type": "text", "content": n.content},
    ]
    participants = n.participants.all()
    if participants:
        sections.append({"heading": "Participants", "type": "table",
                         "headers": ["Name", "Type", "Organization"],
                         "rows": [[p.name, p.get_entity_type_display(), p.organization or "-"] for p in participants]})
    stakeholders = n.related_stakeholders.all()
    if stakeholders:
        sections.append({"heading": "Related Stakeholders", "type": "table",
                         "headers": ["Name", "Type"],
                         "rows": [[s.name, s.get_entity_type_display()] for s in stakeholders]})
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
                      f"{n.get_note_type_display()} — {n.date.strftime('%b %d, %Y %I:%M %p')}", sections)


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
