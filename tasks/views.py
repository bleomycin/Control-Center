from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from django.http import HttpResponse

from dashboard.choices import get_choice_label
from .forms import FollowUpForm, QuickTaskForm, TaskForm
from .models import FollowUp, Task


class TaskListView(ListView):
    model = Task
    template_name = "tasks/task_list.html"
    context_object_name = "tasks"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related("related_stakeholders")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(title__icontains=q)
        statuses = [s for s in self.request.GET.getlist("status") if s]
        if statuses:
            qs = qs.filter(status__in=statuses)
        priority = self.request.GET.get("priority")
        if priority:
            qs = qs.filter(priority=priority)
        date_from = self.request.GET.get("date_from")
        if date_from:
            qs = qs.filter(due_date__gte=date_from)
        date_to = self.request.GET.get("date_to")
        if date_to:
            qs = qs.filter(due_date__lte=date_to)
        directions = [d for d in self.request.GET.getlist("direction") if d]
        if directions:
            qs = qs.filter(direction__in=directions)
        task_types = [t for t in self.request.GET.getlist("task_type") if t]
        if task_types:
            qs = qs.filter(task_type__in=task_types)
        ALLOWED_SORTS = {"title", "status", "priority", "due_date", "direction", "created_at"}
        sort = self.request.GET.get("sort", "")
        if sort in ALLOWED_SORTS:
            direction = "" if self.request.GET.get("dir") == "asc" else "-"
            qs = qs.order_by(f"{direction}{sort}")
        return qs

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["tasks/partials/_task_table_rows.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search_query"] = self.request.GET.get("q", "")
        ctx["status_choices"] = Task.STATUS_CHOICES
        ctx["priority_choices"] = Task.PRIORITY_CHOICES
        ctx["selected_status"] = self.request.GET.get("status", "")
        ctx["selected_priority"] = self.request.GET.get("priority", "")
        ctx["date_from"] = self.request.GET.get("date_from", "")
        ctx["date_to"] = self.request.GET.get("date_to", "")
        ctx["selected_statuses"] = self.request.GET.getlist("status")
        ctx["current_sort"] = self.request.GET.get("sort", "")
        ctx["current_dir"] = self.request.GET.get("dir", "")
        ctx["direction_choices"] = Task.DIRECTION_CHOICES
        ctx["selected_directions"] = self.request.GET.getlist("direction")
        ctx["type_choices"] = Task.TASK_TYPE_CHOICES
        ctx["selected_types"] = self.request.GET.getlist("task_type")
        return ctx


class TaskCreateView(CreateView):
    model = Task
    form_class = TaskForm
    template_name = "tasks/task_form.html"

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("stakeholder"):
            initial["related_stakeholders"] = [self.request.GET["stakeholder"]]
        if self.request.GET.get("legal"):
            initial["related_legal_matter"] = self.request.GET["legal"]
        if self.request.GET.get("property"):
            initial["related_property"] = self.request.GET["property"]
        if self.request.GET.get("direction"):
            initial["direction"] = self.request.GET["direction"]
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        task = self.object
        first_stakeholder = task.related_stakeholders.first()
        if form.cleaned_data.get("fu_create") and first_stakeholder:
            FollowUp.objects.create(
                task=task,
                stakeholder=first_stakeholder,
                outreach_date=timezone.now(),
                method=form.cleaned_data.get("fu_method", ""),
                reminder_enabled=form.cleaned_data.get("fu_reminder_enabled", False),
                follow_up_days=form.cleaned_data.get("fu_follow_up_days") or 3,
                notes_text=form.cleaned_data.get("fu_notes", ""),
            )
        messages.success(self.request, "Task created.")
        return response


class TaskDetailView(DetailView):
    model = Task
    template_name = "tasks/task_detail.html"
    context_object_name = "task"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["follow_ups"] = self.object.follow_ups.select_related("stakeholder").all()
        ctx["followup_form"] = FollowUpForm()
        ctx["notes"] = self.object.notes.all()[:5]
        return ctx


class TaskUpdateView(UpdateView):
    model = Task
    form_class = TaskForm
    template_name = "tasks/task_form.html"

    def form_valid(self, form):
        messages.success(self.request, "Task updated.")
        return super().form_valid(form)


class TaskDeleteView(DeleteView):
    model = Task
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("tasks:list")

    def form_valid(self, form):
        messages.success(self.request, f'Task "{self.object}" deleted.')
        return super().form_valid(form)


def quick_create(request):
    if request.method == "POST":
        form = QuickTaskForm(request.POST)
        if form.is_valid():
            form.save()
            response = HttpResponse(status=204)
            response["HX-Trigger"] = "closeModal"
            response["HX-Redirect"] = reverse_lazy("tasks:list")
            return response
    else:
        form = QuickTaskForm()
    return render(request, "tasks/partials/_quick_task_form.html", {"form": form})


def export_csv(request):
    from legacy.export import export_csv as do_export
    qs = Task.objects.prefetch_related("related_stakeholders").all()
    fields = [
        ("title", "Title"),
        ("direction", "Direction"),
        ("status", "Status"),
        ("priority", "Priority"),
        ("due_date", "Due Date"),
        ("_due_time_str", "Time"),
        ("_stakeholder_names", "Stakeholders"),
        ("description", "Description"),
    ]
    # Annotate tasks with a joined stakeholder names string
    tasks_list = []
    for task in qs:
        task._stakeholder_names = ", ".join(
            s.name for s in task.related_stakeholders.all()
        ) or ""
        task._due_time_str = task.due_time.strftime("%-I:%M %p") if task.due_time else ""
        tasks_list.append(task)
    return do_export(tasks_list, fields, "tasks")


def export_pdf_detail(request, pk):
    from legacy.pdf_export import render_pdf
    t = get_object_or_404(Task.objects.prefetch_related("related_stakeholders"), pk=pk)
    direction_label = t.get_direction_display()
    stakeholder_label = "Stakeholders"
    if t.direction == "outbound":
        stakeholder_label = "Requested From"
    elif t.direction == "inbound":
        stakeholder_label = "Requested By"
    due_date_str = t.due_date.strftime("%b %d, %Y") if t.due_date else "None"
    if t.due_time:
        due_date_str += f" at {t.due_time.strftime('%-I:%M %p')}"
    sections = [
        {"heading": "Task Information", "type": "info", "rows": [
            ("Direction", direction_label),
            ("Due Date", due_date_str),
            ("Type", t.get_task_type_display()),
            ("Created", t.created_at.strftime("%b %d, %Y %I:%M %p")),
        ]},
    ]
    if t.completed_at:
        sections[0]["rows"].append(("Completed", t.completed_at.strftime("%b %d, %Y %I:%M %p")))
    stakeholder_names = ", ".join(s.name for s in t.related_stakeholders.all())
    if stakeholder_names:
        sections[0]["rows"].append((stakeholder_label, stakeholder_names))
    if t.related_legal_matter:
        sections[0]["rows"].append(("Legal Matter", t.related_legal_matter.title))
    if t.related_property:
        sections[0]["rows"].append(("Property", t.related_property.name))
    if t.description:
        sections.append({"heading": "Description", "type": "text", "content": t.description})
    follow_ups = t.follow_ups.select_related("stakeholder").all()
    if follow_ups:
        def _fu_notes(fu):
            parts = []
            if fu.notes_text:
                text = (fu.notes_text[:60] + "...") if len(fu.notes_text) > 60 else fu.notes_text
                parts.append(text)
            if fu.response_notes:
                resp = (fu.response_notes[:60] + "...") if len(fu.response_notes) > 60 else fu.response_notes
                parts.append(f"Response: {resp}")
            return " | ".join(parts) or "-"
        sections.append({"heading": "Follow-ups", "type": "table",
                         "headers": ["Date", "Stakeholder", "Method", "Reminder", "Response", "Notes"],
                         "rows": [[fu.outreach_date.strftime("%b %d, %Y"), fu.stakeholder.name,
                                   get_choice_label("contact_method", fu.method),
                                   f"{fu.follow_up_days} days" if fu.reminder_enabled else "Off",
                                   f"Yes ({fu.response_date.strftime('%b %d')})" if fu.response_received else "Pending",
                                   _fu_notes(fu)]
                                  for fu in follow_ups]})
    notes = t.notes.all()
    if notes:
        sections.append({"heading": "Related Notes", "type": "table",
                         "headers": ["Title", "Type", "Date"],
                         "rows": [[n.title, get_choice_label("note_type", n.note_type), n.date.strftime("%b %d, %Y")] for n in notes]})
    return render_pdf(request, f"task-{t.pk}", t.title,
                      f"{t.get_status_display()} — {t.get_priority_display()} Priority", sections)


def toggle_complete(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if task.status == "complete":
        task.status = "not_started"
        task.completed_at = None
    else:
        task.status = "complete"
        task.completed_at = timezone.now()
    task.save()
    return render(request, "tasks/partials/_task_status_badge.html", {"task": task})


def followup_add(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if request.method == "POST":
        form = FollowUpForm(request.POST)
        if form.is_valid():
            fu = form.save(commit=False)
            fu.task = task
            fu.save()
            return render(request, "tasks/partials/_followup_list.html",
                          {"follow_ups": task.follow_ups.select_related("stakeholder").all(), "task": task})
    else:
        initial = {"outreach_date": timezone.now().strftime("%Y-%m-%dT%H:%M")}
        first_stakeholder = task.related_stakeholders.first()
        if first_stakeholder:
            initial["stakeholder"] = first_stakeholder.pk
        form = FollowUpForm(initial=initial)
    from django.urls import reverse
    return render(request, "tasks/partials/_followup_form.html",
                  {"form": form, "task": task, "form_url": reverse("tasks:followup_add", args=[pk])})


def followup_edit(request, pk):
    fu = get_object_or_404(FollowUp, pk=pk)
    task = fu.task
    if request.method == "POST":
        form = FollowUpForm(request.POST, instance=fu)
        if form.is_valid():
            form.save()
            return render(request, "tasks/partials/_followup_list.html",
                          {"follow_ups": task.follow_ups.select_related("stakeholder").all(), "task": task})
    else:
        form = FollowUpForm(instance=fu)
    from django.urls import reverse
    return render(request, "tasks/partials/_followup_form.html",
                  {"form": form, "task": task, "form_url": reverse("tasks:followup_edit", args=[pk]),
                   "edit_mode": True})


def followup_respond(request, pk):
    fu = get_object_or_404(FollowUp, pk=pk)
    task = fu.task
    if request.method == "POST":
        if fu.response_received:
            # Undo — clear response but keep response_notes
            fu.response_received = False
            fu.response_date = None
        else:
            fu.response_received = True
            fu.response_date = timezone.now()
            fu.response_notes = request.POST.get("response_notes", "")
        fu.save()
        return render(request, "tasks/partials/_followup_list.html",
                      {"follow_ups": task.follow_ups.select_related("stakeholder").all(), "task": task})
    # GET — return inline response form
    return render(request, "tasks/partials/_followup_respond_form.html", {"fu": fu, "task": task})


def followup_delete(request, pk):
    fu = get_object_or_404(FollowUp, pk=pk)
    task = fu.task
    if request.method == "POST":
        fu.delete()
    return render(request, "tasks/partials/_followup_list.html",
                  {"follow_ups": task.follow_ups.select_related("stakeholder").all(), "task": task})


def bulk_delete(request):
    if request.method == "POST":
        pks = request.POST.getlist("selected")
        count = Task.objects.filter(pk__in=pks).count()
        if "confirm" not in request.POST:
            from django.urls import reverse
            return render(request, "partials/_bulk_confirm_delete.html", {
                "count": count, "selected_pks": pks,
                "action_url": reverse("tasks:bulk_delete"),
            })
        Task.objects.filter(pk__in=pks).delete()
        messages.success(request, f"{count} task(s) deleted.")
    return redirect("tasks:list")


def bulk_export_csv(request):
    from legacy.export import export_csv as do_export
    pks = request.GET.getlist("selected")
    qs = Task.objects.filter(pk__in=pks) if pks else Task.objects.none()
    fields = [
        ("title", "Title"),
        ("status", "Status"),
        ("priority", "Priority"),
        ("due_date", "Due Date"),
        ("_due_time_str", "Time"),
    ]
    tasks_list = []
    for task in qs:
        task._due_time_str = task.due_time.strftime("%-I:%M %p") if task.due_time else ""
        tasks_list.append(task)
    return do_export(tasks_list, fields, "tasks_selected")


def bulk_complete(request):
    if request.method == "POST":
        pks = request.POST.getlist("selected")
        count = Task.objects.filter(pk__in=pks).exclude(status="complete").update(status="complete")
        messages.success(request, f"{count} task(s) marked complete.")
    return redirect("tasks:list")
