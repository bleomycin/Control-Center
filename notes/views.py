from collections import OrderedDict
from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from dashboard.choices import get_choice_label, get_choices
from stakeholders.models import Stakeholder
from .forms import AttachmentForm, FolderForm, LinkForm, NoteForm, QuickNoteForm, TagForm
from .models import Attachment, Folder, Link, Note, Tag


def export_csv(request):
    from legacy.export import export_csv as do_export
    qs = Note.objects.select_related("folder").prefetch_related("tags").all()
    for n in qs:
        n._tag_names = ", ".join(t.name for t in n.tags.all())
        n._folder_name = n.folder.name if n.folder else ""
    fields = [
        ("title", "Title"),
        ("note_type", "Type"),
        ("date", "Date"),
        ("is_pinned", "Pinned"),
        ("_folder_name", "Folder"),
        ("_tag_names", "Tags"),
        ("content", "Content"),
    ]
    return do_export(qs, fields, "notes")


ALLOWED_SORTS = {"title", "note_type", "date"}


class NoteListView(ListView):
    model = Note
    template_name = "notes/note_list.html"
    context_object_name = "notes"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().select_related("folder").prefetch_related(
            "participants", "related_stakeholders",
            "related_legal_matters", "related_properties",
            "related_investments", "related_loans", "related_tasks",
            "related_policies", "related_vehicles", "related_aircraft", "tags",
        ).annotate(
            attachment_count=Count("attachments", distinct=True),
            link_count=Count("links", distinct=True),
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(content__icontains=q))
        note_types = [t for t in self.request.GET.getlist("type") if t]
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
        # Tag filter
        tags = [t for t in self.request.GET.getlist("tag") if t]
        if tags:
            qs = qs.filter(tags__slug__in=tags).distinct()
        # Folder filter
        folder_tab = self.request.GET.get("folder", "")
        if folder_tab == "unfiled":
            qs = qs.filter(folder__isnull=True)
        elif folder_tab and folder_tab not in ("all", ""):
            try:
                qs = qs.filter(folder__pk=int(folder_tab))
            except (ValueError, TypeError):
                pass
        # Sorting — always pin first
        sort = self.request.GET.get("sort", "")
        if sort in ALLOWED_SORTS:
            direction = "" if self.request.GET.get("dir") == "asc" else "-"
            qs = qs.order_by("-is_pinned", f"{direction}{sort}")
        else:
            qs = qs.order_by("-is_pinned", "-date")
        return qs

    def get_template_names(self):
        view_mode = self.request.GET.get("view", "cards")
        if self.request.headers.get("HX-Request"):
            if view_mode == "list":
                return ["notes/partials/_note_table_view.html"]
            if view_mode == "timeline":
                return ["notes/partials/_note_timeline_view.html"]
            return ["notes/partials/_note_list_content.html"]
        return [self.template_name]

    def get_paginate_by(self, queryset):
        if self.request.GET.get("view") == "timeline":
            return 50
        return self.paginate_by

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
        ctx["all_tags"] = Tag.objects.all()
        ctx["selected_tags"] = self.request.GET.getlist("tag")
        ctx["folders"] = Folder.objects.annotate(note_count=Count("notes")).all()
        ctx["current_folder"] = self.request.GET.get("folder", "")
        ctx["unfiled_count"] = Note.objects.filter(folder__isnull=True).count()
        ctx["current_view"] = self.request.GET.get("view", "cards")
        # Timeline grouping
        if ctx["current_view"] == "timeline":
            today = timezone.localdate()
            yesterday = today - timedelta(days=1)
            week_start = today - timedelta(days=today.weekday())
            month_start = today.replace(day=1)

            def date_group_key(note):
                d = timezone.localdate(note.date) if hasattr(note.date, 'date') else note.date
                if d == today:
                    return "Today"
                elif d == yesterday:
                    return "Yesterday"
                elif d >= week_start:
                    return "This Week"
                elif d >= month_start:
                    return "This Month"
                else:
                    return d.strftime("%B %Y")

            # Use OrderedDict to merge notes into unique groups (handles
            # pinned notes breaking consecutive-groupby ordering).
            groups = OrderedDict()
            # Seed fixed groups in display order so they always appear first
            for label in ("Today", "Yesterday", "This Week", "This Month"):
                groups[label] = []
            for note in ctx["notes"]:
                key = date_group_key(note)
                groups.setdefault(key, []).append(note)
            # Build final list, dropping empty fixed groups
            ctx["timeline_groups"] = [
                {"label": k, "notes": v} for k, v in groups.items() if v
            ]
        return ctx


class NoteCreateView(CreateView):
    model = Note
    form_class = NoteForm
    template_name = "notes/note_form.html"

    def get_initial(self):
        initial = super().get_initial()
        date_param = self.request.GET.get("date", "").strip()
        if date_param:
            from datetime import datetime as dt
            try:
                parsed = dt.fromisoformat(date_param)
                initial["date"] = timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed
            except (ValueError, TypeError):
                initial["date"] = timezone.now()
        else:
            initial["date"] = timezone.now()
        for field in ("title", "content", "note_type"):
            if self.request.GET.get(field):
                initial[field] = self.request.GET[field]
        if self.request.GET.get("task"):
            initial["related_tasks"] = [self.request.GET["task"]]
        if self.request.GET.get("stakeholder"):
            initial["participants"] = [self.request.GET["stakeholder"]]
        if self.request.GET.get("property"):
            initial["related_properties"] = [self.request.GET["property"]]
        if self.request.GET.get("investment"):
            initial["related_investments"] = [self.request.GET["investment"]]
        if self.request.GET.get("loan"):
            initial["related_loans"] = [self.request.GET["loan"]]
        if self.request.GET.get("policy"):
            initial["related_policies"] = [self.request.GET["policy"]]
        if self.request.GET.get("vehicle"):
            initial["related_vehicles"] = [self.request.GET["vehicle"]]
        if self.request.GET.get("aircraft"):
            initial["related_aircraft"] = [self.request.GET["aircraft"]]
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
        ctx["link_list"] = self.object.links.all()
        ctx["link_form"] = LinkForm()
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


def _strip_markdown(text):
    """Convert markdown to plain text for PDF export."""
    import re
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)  # headings
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # bold
    text = re.sub(r'\*(.+?)\*', r'\1', text)  # italic
    text = re.sub(r'~~(.+?)~~', r'\1', text)  # strikethrough
    text = re.sub(r'`(.+?)`', r'\1', text)  # inline code
    text = re.sub(r'^\s*[-*+]\s+', '  - ', text, flags=re.MULTILINE)  # bullets
    text = re.sub(r'^\s*\d+\.\s+', '  - ', text, flags=re.MULTILINE)  # numbered
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)  # links
    text = re.sub(r'^>\s?', '', text, flags=re.MULTILINE)  # blockquotes
    return text


def export_pdf_detail(request, pk):
    from legacy.pdf_export import render_pdf
    n = get_object_or_404(Note, pk=pk)
    info_rows = [
        ("Type", get_choice_label("note_type", n.note_type)),
        ("Date", n.date.strftime("%b %d, %Y %I:%M %p")),
        ("Pinned", "Yes" if n.is_pinned else "No"),
    ]
    if n.folder:
        info_rows.append(("Folder", n.folder.name))
    tag_names = ", ".join(t.name for t in n.tags.all())
    if tag_names:
        info_rows.append(("Tags", tag_names))
    sections = [
        {"heading": "Details", "type": "info", "rows": info_rows},
        {"heading": "Content", "type": "text", "content": _strip_markdown(n.content)},
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
    properties = n.related_properties.all()
    if properties:
        sections.append({"heading": "Related Properties", "type": "table",
                         "headers": ["Name", "Type"],
                         "rows": [[p.name, p.property_type or "-"] for p in properties]})
    investments = n.related_investments.all()
    if investments:
        sections.append({"heading": "Related Investments", "type": "table",
                         "headers": ["Name", "Type"],
                         "rows": [[i.name, i.investment_type or "-"] for i in investments]})
    loans = n.related_loans.all()
    if loans:
        sections.append({"heading": "Related Loans", "type": "table",
                         "headers": ["Name", "Status"],
                         "rows": [[lo.name, lo.get_status_display()] for lo in loans]})
    policies = n.related_policies.all()
    if policies:
        sections.append({"heading": "Related Insurance Policies", "type": "table",
                         "headers": ["Name", "Status"],
                         "rows": [[p.name, p.get_status_display()] for p in policies]})
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
    links = n.links.all()
    if links:
        sections.append({"heading": "Links", "type": "table",
                         "headers": ["Description", "URL", "Added"],
                         "rows": [[lk.description, lk.url, lk.created_at.strftime("%b %d, %Y")] for lk in links]})
    return render_pdf(request, f"note-{n.pk}", n.title,
                      f"{get_choice_label('note_type', n.note_type)} — {n.date.strftime('%b %d, %Y %I:%M %p')}", sections)


def toggle_pin(request, pk):
    note = get_object_or_404(Note, pk=pk)
    if request.method == "POST":
        note.is_pinned = not note.is_pinned
        note.save(update_fields=["is_pinned"])
    context = request.POST.get("context", "list")
    if context == "detail":
        return redirect(note.get_absolute_url())
    # Return 204 + HX-Trigger to refresh the full note list
    response = HttpResponse(status=204)
    response["HX-Trigger"] = "noteListChanged"
    return response


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


def link_add(request, pk):
    note = get_object_or_404(Note, pk=pk)
    if request.method == "POST":
        form = LinkForm(request.POST)
        if form.is_valid():
            link = form.save(commit=False)
            link.note = note
            link.save()
            return render(request, "notes/partials/_link_list.html",
                          {"link_list": note.links.all(), "note": note})
    else:
        form = LinkForm()
    return render(request, "notes/partials/_link_form.html",
                  {"form": form, "note": note})


def link_edit(request, pk):
    link = get_object_or_404(Link, pk=pk)
    note = link.note
    if request.method == "POST":
        form = LinkForm(request.POST, instance=link)
        if form.is_valid():
            form.save()
            return render(request, "notes/partials/_link_list.html",
                          {"link_list": note.links.all(), "note": note})
    else:
        form = LinkForm(instance=link)
    from django.urls import reverse
    return render(request, "notes/partials/_link_form.html",
                  {"form": form, "note": note,
                   "form_url": reverse("notes:link_edit", args=[pk]),
                   "edit_mode": True})


def link_delete(request, pk):
    link = get_object_or_404(Link, pk=pk)
    note = link.note
    if request.method == "POST":
        link.delete()
    return render(request, "notes/partials/_link_list.html",
                  {"link_list": note.links.all(), "note": note})


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


def bulk_apply_tags(request):
    if request.method == "POST":
        pks = request.POST.getlist("selected")
        tag_pks = request.POST.getlist("tags")
        mode = request.POST.get("mode", "add")
        if pks and tag_pks:
            tags = Tag.objects.filter(pk__in=tag_pks)
            for note in Note.objects.filter(pk__in=pks):
                if mode == "remove":
                    note.tags.remove(*tags)
                else:
                    note.tags.add(*tags)
        response = HttpResponse(status=204)
        response["HX-Trigger"] = "noteListChanged"
        return response
    return HttpResponse(status=400)


def bulk_move_folder(request):
    if request.method == "POST":
        pks = request.POST.getlist("selected")
        folder_id = request.POST.get("folder", "")
        if pks:
            try:
                folder_val = int(folder_id) if folder_id else None
            except (ValueError, TypeError):
                return HttpResponse(status=400)
            Note.objects.filter(pk__in=pks).update(folder_id=folder_val)
        response = HttpResponse(status=204)
        response["HX-Trigger"] = "noteListChanged"
        return response
    return HttpResponse(status=400)


def bulk_export_csv(request):
    from legacy.export import export_csv as do_export
    pks = request.GET.getlist("selected")
    qs = Note.objects.filter(pk__in=pks) if pks else Note.objects.none()
    qs = qs.select_related("folder").prefetch_related("tags")
    for n in qs:
        n._tag_names = ", ".join(t.name for t in n.tags.all())
        n._folder_name = n.folder.name if n.folder else ""
    fields = [
        ("title", "Title"),
        ("note_type", "Type"),
        ("date", "Date"),
        ("is_pinned", "Pinned"),
        ("_folder_name", "Folder"),
        ("_tag_names", "Tags"),
        ("content", "Content"),
    ]
    return do_export(qs, fields, "notes_selected")


# --- Tag CRUD ---

def tag_list(request):
    tags = Tag.objects.annotate(note_count=Count("notes")).all()
    return render(request, "notes/tag_settings.html", {"tags": tags})


def tag_add(request):
    if request.method == "POST":
        form = TagForm(request.POST)
        if form.is_valid():
            form.save()
            tags = Tag.objects.annotate(note_count=Count("notes")).all()
            return render(request, "notes/partials/_tag_list.html", {"tags": tags})
    else:
        form = TagForm()
    return render(request, "notes/partials/_tag_form.html", {"form": form})


def tag_edit(request, pk):
    tag = get_object_or_404(Tag, pk=pk)
    if request.method == "POST":
        form = TagForm(request.POST, instance=tag)
        if form.is_valid():
            form.save()
            tags = Tag.objects.annotate(note_count=Count("notes")).all()
            return render(request, "notes/partials/_tag_list.html", {"tags": tags})
    else:
        form = TagForm(instance=tag)
    from django.urls import reverse
    return render(request, "notes/partials/_tag_form.html", {
        "form": form,
        "form_url": reverse("notes:tag_edit", args=[pk]),
        "edit_mode": True,
    })


def tag_delete(request, pk):
    tag = get_object_or_404(Tag, pk=pk)
    if request.method == "POST":
        tag.delete()
    tags = Tag.objects.annotate(note_count=Count("notes")).all()
    return render(request, "notes/partials/_tag_list.html", {"tags": tags})


# --- Folder CRUD ---

def _folder_list_response(request, template="notes/partials/_folder_list.html"):
    folders = Folder.objects.annotate(note_count=Count("notes")).all()
    resp = render(request, template, {"folders": folders})
    resp["HX-Trigger"] = "foldersChanged"
    return resp


def folder_tabs(request):
    folders = Folder.objects.annotate(note_count=Count("notes")).all()
    unfiled_count = Note.objects.filter(folder__isnull=True).count()
    return render(request, "notes/partials/_folder_tabs.html", {
        "folders": folders,
        "unfiled_count": unfiled_count,
        "current_folder": request.GET.get("folder", ""),
    })


def folder_list(request):
    folders = Folder.objects.annotate(note_count=Count("notes")).all()
    return render(request, "notes/folder_settings.html", {"folders": folders})


def folder_add(request):
    if request.method == "POST":
        form = FolderForm(request.POST)
        if form.is_valid():
            form.save()
            return _folder_list_response(request)
    else:
        form = FolderForm()
    return render(request, "notes/partials/_folder_form.html", {"form": form})


def folder_edit(request, pk):
    folder = get_object_or_404(Folder, pk=pk)
    if request.method == "POST":
        form = FolderForm(request.POST, instance=folder)
        if form.is_valid():
            form.save()
            return _folder_list_response(request)
    else:
        form = FolderForm(instance=folder)
    from django.urls import reverse
    return render(request, "notes/partials/_folder_form.html", {
        "form": form,
        "form_url": reverse("notes:folder_edit", args=[pk]),
        "edit_mode": True,
    })


def folder_delete(request, pk):
    folder = get_object_or_404(Folder, pk=pk)
    if request.method == "POST":
        folder.delete()
    return _folder_list_response(request)
