from django.contrib import messages
from django.db.models import Case, Count, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView
from django.views.decorators.http import require_POST

from django.http import HttpResponse

from datetime import date as _date, timedelta

from dashboard.choices import get_choice_label
from stakeholders.models import Stakeholder
from .forms import FollowUpForm, QuickTaskForm, SubTaskForm, TaskForm
from .models import FollowUp, SubTask, Task


def _build_grouped_tasks(tasks, group_by):
    """Group a list of tasks by the given field for grouped table view."""
    if group_by == "status":
        order = ["not_started", "in_progress", "waiting", "complete"]
        labels = dict(Task.STATUS_CHOICES)
        buckets = {k: [] for k in order}
        for t in tasks:
            buckets.get(t.status, buckets["not_started"]).append(t)
        return [{"label": labels[k], "tasks": buckets[k], "count": len(buckets[k])} for k in order]

    if group_by == "priority":
        order = ["critical", "high", "medium", "low"]
        labels = dict(Task.PRIORITY_CHOICES)
        buckets = {k: [] for k in order}
        for t in tasks:
            buckets.get(t.priority, buckets["medium"]).append(t)
        return [{"label": labels[k], "tasks": buckets[k], "count": len(buckets[k])} for k in order]

    if group_by == "due_date":
        today = timezone.localdate()
        end_of_week = today + timedelta(days=(6 - today.weekday()))
        buckets = {"Overdue": [], "Today": [], "This Week": [], "Later": [], "No Date": []}
        for t in tasks:
            if not t.due_date:
                buckets["No Date"].append(t)
            elif t.due_date < today:
                buckets["Overdue"].append(t)
            elif t.due_date == today:
                buckets["Today"].append(t)
            elif t.due_date <= end_of_week:
                buckets["This Week"].append(t)
            else:
                buckets["Later"].append(t)
        return [{"label": k, "tasks": v, "count": len(v)} for k, v in buckets.items() if v]

    if group_by == "stakeholder":
        buckets = {}
        no_stakeholder = []
        for t in tasks:
            stakeholders = list(t.related_stakeholders.all())
            if not stakeholders:
                no_stakeholder.append(t)
            else:
                for s in stakeholders:
                    buckets.setdefault(s.name, []).append(t)
        groups = [{"label": name, "tasks": tlist, "count": len(tlist)} for name, tlist in sorted(buckets.items())]
        if no_stakeholder:
            groups.append({"label": "No Stakeholder", "tasks": no_stakeholder, "count": len(no_stakeholder)})
        return groups

    return []


class TaskListView(ListView):
    model = Task
    template_name = "tasks/task_list.html"
    context_object_name = "tasks"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related("related_stakeholders", "follow_ups").annotate(
            subtask_count=Count("subtasks", distinct=True),
            subtask_done=Count("subtasks", filter=Q(subtasks__is_completed=True), distinct=True),
        )
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
        stakeholder = self.request.GET.get("stakeholder", "").strip()
        if stakeholder:
            qs = qs.filter(related_stakeholders__pk=stakeholder).distinct()
        ALLOWED_SORTS = {"title", "status", "priority", "due_date", "direction", "created_at"}
        sort = self.request.GET.get("sort", "")
        if sort in ALLOWED_SORTS:
            direction = "" if self.request.GET.get("dir") == "asc" else "-"
            if sort == "priority":
                qs = qs.annotate(_priority_order=Case(
                    When(priority="critical", then=Value(0)),
                    When(priority="high", then=Value(1)),
                    When(priority="medium", then=Value(2)),
                    When(priority="low", then=Value(3)),
                    default=Value(4),
                )).order_by(f"{direction}_priority_order")
            elif sort == "status":
                qs = qs.annotate(_status_order=Case(
                    When(status="not_started", then=Value(0)),
                    When(status="in_progress", then=Value(1)),
                    When(status="waiting", then=Value(2)),
                    When(status="complete", then=Value(3)),
                    default=Value(4),
                )).order_by(f"{direction}_status_order")
            else:
                qs = qs.order_by(f"{direction}{sort}")
        else:
            qs = qs.order_by("-created_at")
        return qs

    def get_paginate_by(self, queryset):
        if self.request.GET.get("view") == "board":
            return None
        if self.request.GET.get("group"):
            return None
        return self.paginate_by

    def get_template_names(self):
        view_mode = self.request.GET.get("view", "table")
        group_by = self.request.GET.get("group", "")
        if self.request.headers.get("HX-Request"):
            if view_mode == "board":
                return ["tasks/partials/_kanban_board.html"]
            if group_by:
                return ["tasks/partials/_grouped_table_view.html"]
            return ["tasks/partials/_table_view.html"]
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
        ctx["current_sort"] = self.request.GET.get("sort", "") or "created_at"
        ctx["current_dir"] = self.request.GET.get("dir", "") or "desc"
        ctx["direction_choices"] = Task.DIRECTION_CHOICES
        ctx["selected_directions"] = self.request.GET.getlist("direction")
        ctx["type_choices"] = Task.TASK_TYPE_CHOICES
        ctx["selected_types"] = self.request.GET.getlist("task_type")
        ctx["current_view"] = self.request.GET.get("view", "table")
        ctx["stakeholders"] = Stakeholder.objects.all().order_by("name")
        ctx["selected_stakeholder"] = self.request.GET.get("stakeholder", "")
        group_by = self.request.GET.get("group", "")
        ctx["current_group"] = group_by
        ctx["group_choices"] = [
            ("", "No Grouping"), ("status", "Status"), ("priority", "Priority"),
            ("due_date", "Due Date"), ("stakeholder", "Stakeholder"),
        ]
        if group_by in ("status", "priority", "due_date", "stakeholder"):
            all_tasks = list(self.get_queryset())
            ctx["grouped_tasks"] = _build_grouped_tasks(all_tasks, group_by)

        # Build kanban columns for board view
        if ctx["current_view"] == "board":
            tasks = ctx["tasks"] if "tasks" in ctx else self.get_queryset()
            column_config = [
                ("not_started", "Not Started", "border-gray-500"),
                ("in_progress", "In Progress", "border-blue-500"),
                ("waiting", "Waiting", "border-yellow-500"),
                ("complete", "Complete", "border-green-500"),
            ]
            kanban_columns = []
            for status, label, border_color in column_config:
                col_tasks = [t for t in tasks if t.status == status]
                kanban_columns.append({
                    "status": status,
                    "label": label,
                    "border_color": border_color,
                    "tasks": col_tasks,
                })
            ctx["kanban_columns"] = kanban_columns

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
        subtasks = self.object.subtasks.all()
        ctx["subtasks"] = subtasks
        ctx["subtask_form"] = SubTaskForm()
        ctx["subtask_count"] = subtasks.count()
        ctx["subtask_done"] = subtasks.filter(is_completed=True).count()
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
    from config.export import export_csv as do_export
    qs = Task.objects.prefetch_related("related_stakeholders").annotate(
        _st_count=Count("subtasks", distinct=True),
        _st_done=Count("subtasks", filter=Q(subtasks__is_completed=True), distinct=True),
    ).all()
    fields = [
        ("title", "Title"),
        ("direction", "Direction"),
        ("status", "Status"),
        ("priority", "Priority"),
        ("due_date", "Due Date"),
        ("_due_time_str", "Time"),
        ("_stakeholder_names", "Stakeholders"),
        ("_subtask_progress", "Checklist"),
        ("_recurrence_str", "Recurrence"),
        ("description", "Description"),
    ]
    tasks_list = []
    for task in qs:
        task._stakeholder_names = ", ".join(
            s.name for s in task.related_stakeholders.all()
        ) or ""
        task._due_time_str = task.due_time.strftime("%-I:%M %p") if task.due_time else ""
        task._subtask_progress = f"{task._st_done}/{task._st_count}" if task._st_count else ""
        task._recurrence_str = task.get_recurrence_rule_display() if task.is_recurring else ""
        tasks_list.append(task)
    return do_export(tasks_list, fields, "tasks")


def export_pdf_detail(request, pk):
    from config.pdf_export import render_pdf
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
    if t.is_recurring:
        sections[0]["rows"].append(("Recurrence", t.get_recurrence_rule_display()))
    if t.description:
        sections.append({"heading": "Description", "type": "text", "content": t.description})
    subtasks = t.subtasks.all()
    if subtasks:
        sections.append({"heading": "Checklist", "type": "table",
                         "headers": ["Item", "Status"],
                         "rows": [[st.title, "Done" if st.is_completed else "Pending"] for st in subtasks]})
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
                         "rows": [[fu.outreach_date.strftime("%b %d, %Y"), fu.stakeholder.name if fu.stakeholder else "—",
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


def _handle_recurring_completion(task):
    """Create the next recurrence when a recurring task is completed."""
    if task.is_recurring and task.status == "complete":
        return task.create_next_recurrence()
    return None


@require_POST
def toggle_complete(request, pk):
    task = get_object_or_404(Task.objects.prefetch_related("related_stakeholders"), pk=pk)
    if task.status == "complete":
        task.status = "not_started"
        task.completed_at = None
    else:
        task.status = "complete"
        task.completed_at = timezone.now()
    task.save()
    _handle_recurring_completion(task)
    # Return full row for table context, badge for detail context
    context = request.POST.get("context", "")
    if context == "detail":
        return render(request, "tasks/partials/_task_status_badge.html", {"task": task})
    return render(request, "tasks/partials/_task_row.html", {"task": task})


@require_POST
def kanban_update(request, pk):
    task = get_object_or_404(Task.objects.prefetch_related("related_stakeholders"), pk=pk)
    status = request.POST.get("status", "")
    valid_statuses = [c[0] for c in Task.STATUS_CHOICES]
    if status not in valid_statuses:
        return HttpResponse(status=400)
    task.status = status
    if status == "complete":
        task.completed_at = timezone.now()
    else:
        task.completed_at = None
    task.save()
    _handle_recurring_completion(task)
    return HttpResponse(status=204)


@require_POST
def inline_update(request, pk):
    task = get_object_or_404(Task.objects.prefetch_related("related_stakeholders"), pk=pk)
    field = request.POST.get("field")
    value = request.POST.get("value", "")
    allowed_fields = {
        "status": [c[0] for c in Task.STATUS_CHOICES],
        "priority": [c[0] for c in Task.PRIORITY_CHOICES],
        "due_date": None,
    }
    if field not in allowed_fields:
        return HttpResponse(status=400)
    if field == "due_date":
        from datetime import date as d
        try:
            task.due_date = d.fromisoformat(value) if value else None
        except ValueError:
            return HttpResponse(status=400)
    elif value in allowed_fields[field]:
        setattr(task, field, value)
        if field == "status":
            task.completed_at = timezone.now() if value == "complete" else None
    else:
        return HttpResponse(status=400)
    task.save()
    if field == "status":
        _handle_recurring_completion(task)
    return render(request, "tasks/partials/_task_row.html", {"task": task})


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
        initial = {"outreach_date": timezone.localtime().strftime("%Y-%m-%dT%H:%M")}
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


def _subtask_list_context(task):
    subtasks = task.subtasks.all()
    return {
        "subtasks": subtasks,
        "task": task,
        "subtask_form": SubTaskForm(),
        "subtask_count": subtasks.count(),
        "subtask_done": subtasks.filter(is_completed=True).count(),
    }


def subtask_add(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if request.method == "POST":
        form = SubTaskForm(request.POST)
        if form.is_valid():
            st = form.save(commit=False)
            st.task = task
            st.sort_order = task.subtasks.count()
            st.save()
    return render(request, "tasks/partials/_subtask_list.html", _subtask_list_context(task))


@require_POST
def subtask_toggle(request, pk):
    st = get_object_or_404(SubTask, pk=pk)
    st.is_completed = not st.is_completed
    st.save()
    return render(request, "tasks/partials/_subtask_list.html", _subtask_list_context(st.task))


def subtask_edit(request, pk):
    st = get_object_or_404(SubTask, pk=pk)
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        if title:
            st.title = title
            st.save()
        return render(request, "tasks/partials/_subtask_list.html", _subtask_list_context(st.task))
    # GET with ?cancel: re-render the full list (dismiss edit form)
    if request.GET.get("cancel"):
        return render(request, "tasks/partials/_subtask_list.html", _subtask_list_context(st.task))
    # GET: return inline edit form for this single subtask
    return render(request, "tasks/partials/_subtask_edit_form.html", {"st": st})


@require_POST
def subtask_delete(request, pk):
    st = get_object_or_404(SubTask, pk=pk)
    task = st.task
    st.delete()
    return render(request, "tasks/partials/_subtask_list.html", _subtask_list_context(task))


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
    from config.export import export_csv as do_export
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
        tasks = Task.objects.filter(pk__in=pks).exclude(status="complete").prefetch_related("related_stakeholders")
        count = 0
        for task in tasks:
            task.status = "complete"
            task.completed_at = timezone.now()
            task.save()
            _handle_recurring_completion(task)
            count += 1
        messages.success(request, f"{count} task(s) marked complete.")
    return redirect("tasks:list")
