from datetime import date, timedelta
from datetime import datetime as dt

from django.contrib import messages
from django.core.mail import send_mail
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from dashboard.choices import get_choice_label
from dashboard.models import SampleDataStatus
from assets.models import Investment, Loan, RealEstate
from cashflow.models import CashFlowEntry
from legal.models import Evidence, LegalMatter
from notes.models import Note
from stakeholders.models import ContactLog, Stakeholder
from tasks.models import FollowUp, Task


def dashboard(request):
    today = timezone.localdate()
    now = timezone.now()

    # Overdue tasks: due before today and not complete
    overdue_tasks = Task.objects.filter(
        due_date__lt=today,
    ).exclude(
        status="complete",
    ).prefetch_related("related_stakeholders")

    # Upcoming tasks: due between today and today+14 days, not complete
    upcoming_tasks = Task.objects.filter(
        due_date__gte=today,
        due_date__lte=today + timedelta(days=14),
    ).exclude(
        status="complete",
    ).prefetch_related("related_stakeholders")

    # Active legal matters: status is 'active' or 'pending'
    active_legal_matters = LegalMatter.objects.filter(
        Q(status="active") | Q(status="pending"),
    )

    # Recent activity: mixed timeline items for dashboard panel
    recent_activity = get_activity_timeline(limit=10)

    # Recent notes: last 10 ordered by -date
    recent_notes = Note.objects.order_by("-date")[:10]

    # Stale follow-ups: no response received and outreach_date > 3 days ago
    stale_followups = FollowUp.objects.filter(
        response_received=False,
        outreach_date__lt=now - timedelta(days=3),
    ).select_related("task", "stakeholder")

    # Cash flow summary for current month
    current_month_entries = CashFlowEntry.objects.filter(
        date__year=today.year,
        date__month=today.month,
    )

    actual_inflows = current_month_entries.filter(
        entry_type="inflow", is_projected=False,
    ).aggregate(total=Sum("amount"))["total"] or 0

    actual_outflows = current_month_entries.filter(
        entry_type="outflow", is_projected=False,
    ).aggregate(total=Sum("amount"))["total"] or 0

    from cashflow.alerts import get_liquidity_alerts

    # Monthly net flow
    monthly_net_flow = actual_inflows - actual_outflows

    # Net Worth calculation
    properties_qs = RealEstate.objects.exclude(status="sold")
    total_real_estate = properties_qs.aggregate(
        total=Sum("estimated_value"),
    )["total"] or 0
    property_count = properties_qs.count()

    investments_qs = Investment.objects.all()
    total_investments = investments_qs.aggregate(
        total=Sum("current_value"),
    )["total"] or 0
    investment_count = investments_qs.count()

    total_assets = total_real_estate + total_investments

    active_loans_qs = Loan.objects.filter(status="active")
    total_liabilities = active_loans_qs.aggregate(
        total=Sum("current_balance"),
    )["total"] or 0
    active_loan_count = active_loans_qs.count()

    net_worth = total_assets - total_liabilities

    # Upcoming meetings (next 14 days)
    upcoming_meetings = Task.objects.filter(
        task_type="meeting",
        due_date__gte=today,
        due_date__lte=today + timedelta(days=14),
    ).exclude(status="complete").prefetch_related("related_stakeholders").order_by("due_date", "due_time")

    # Upcoming Deadlines (next 30 days, unified)
    deadline_horizon = today + timedelta(days=30)
    upcoming_deadlines = []
    for task in Task.objects.filter(
        due_date__gte=today, due_date__lte=deadline_horizon,
    ).exclude(status="complete").prefetch_related("related_stakeholders"):
        title = task.title
        color = "yellow"
        if task.is_meeting:
            color = "blue"
            if task.due_time:
                title = f"{task.title} — {task.due_time.strftime('%-I:%M %p')}"
        upcoming_deadlines.append({
            "date": task.due_date, "type": "task", "color": color,
            "title": title, "url": task.get_absolute_url(),
        })
    for loan in Loan.objects.filter(
        status="active", next_payment_date__gte=today,
        next_payment_date__lte=deadline_horizon,
    ):
        upcoming_deadlines.append({
            "date": loan.next_payment_date, "type": "payment", "color": "red",
            "title": f"Payment: {loan.name}", "url": loan.get_absolute_url(),
        })
    for matter in LegalMatter.objects.filter(
        next_hearing_date__gte=today, next_hearing_date__lte=deadline_horizon,
    ).exclude(status="resolved"):
        upcoming_deadlines.append({
            "date": matter.next_hearing_date, "type": "hearing", "color": "purple",
            "title": f"Hearing: {matter.title}", "url": matter.get_absolute_url(),
        })
    upcoming_deadlines.sort(key=lambda x: x["date"])

    # Asset Risk
    from django.db.models import Q as DQ
    at_risk_properties = RealEstate.objects.filter(
        DQ(status="in_dispute") | DQ(legal_matters__status__in=["active", "pending"]),
    ).distinct()
    at_risk_loans = Loan.objects.filter(
        status__in=["defaulted", "in_dispute"],
    )
    has_asset_risks = at_risk_properties.exists() or at_risk_loans.exists()

    context = {
        "overdue_tasks": overdue_tasks,
        "upcoming_tasks": upcoming_tasks,
        "active_legal_matters": active_legal_matters,
        "recent_notes": recent_notes,
        "recent_activity": recent_activity,
        "stale_followups": stale_followups,
        "liquidity_alerts": get_liquidity_alerts(),
        "monthly_net_flow": monthly_net_flow,
        "net_worth": {
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "net_worth": net_worth,
        },
        "property_count": property_count,
        "property_value": total_real_estate,
        "investment_count": investment_count,
        "investment_value": total_investments,
        "active_loan_count": active_loan_count,
        "loan_balance": total_liabilities,
        "upcoming_meetings": upcoming_meetings,
        "today": today,
        "upcoming_deadlines": upcoming_deadlines,
        "at_risk_properties": at_risk_properties,
        "at_risk_loans": at_risk_loans,
        "has_asset_risks": has_asset_risks,
    }

    return render(request, "dashboard/index.html", context)


def global_search(request):
    q = request.GET.get("q", "").strip()
    context = {"query": q}

    if q:
        limit = 10
        context["stakeholders"] = Stakeholder.objects.filter(
            Q(name__icontains=q) | Q(organization__icontains=q) | Q(parent_organization__name__icontains=q)
        )[:limit]
        context["tasks_results"] = Task.objects.filter(title__icontains=q)[:limit]
        context["notes"] = Note.objects.filter(
            Q(title__icontains=q) | Q(content__icontains=q)
        )[:limit]
        context["legal_matters"] = LegalMatter.objects.filter(
            Q(title__icontains=q) | Q(case_number__icontains=q)
        )[:limit]
        context["properties"] = RealEstate.objects.filter(
            Q(name__icontains=q) | Q(address__icontains=q)
        )[:limit]
        context["investments"] = Investment.objects.filter(name__icontains=q)[:limit]
        context["loans"] = Loan.objects.filter(name__icontains=q)[:limit]
        context["cashflow_entries"] = CashFlowEntry.objects.filter(
            description__icontains=q
        )[:limit]
        context["has_results"] = any([
            context["stakeholders"],
            context["tasks_results"],
            context["notes"],
            context["legal_matters"],
            context["properties"],
            context["investments"],
            context["loans"],
            context["cashflow_entries"],
        ])
    else:
        context["has_results"] = False

    if request.headers.get("HX-Request"):
        return render(request, "dashboard/partials/_search_results.html", context)
    return render(request, "dashboard/search.html", context)


def get_activity_timeline(limit=50):
    """Aggregate records from multiple models into unified chronological feed."""
    items = []

    for log in ContactLog.objects.select_related("stakeholder").order_by("-date")[:limit]:
        items.append({
            "date": log.date,
            "type": "contact",
            "color": "blue",
            "icon": "phone",
            "title": f"{get_choice_label('contact_method', log.method)} with {log.stakeholder.name}",
            "summary": log.summary[:120],
            "url": log.get_absolute_url(),
        })

    for note in Note.objects.order_by("-date")[:limit]:
        items.append({
            "date": note.date,
            "type": "note",
            "color": "indigo",
            "icon": "pencil",
            "title": note.title,
            "summary": note.content[:120],
            "url": note.get_absolute_url(),
        })

    for task in Task.objects.order_by("-created_at")[:limit]:
        summary = f"{task.get_status_display()} / {task.get_priority_display()}"
        if task.is_meeting and task.due_time:
            summary += f" — {task.due_time.strftime('%-I:%M %p')}"
        items.append({
            "date": task.created_at,
            "type": "task",
            "color": "yellow",
            "icon": "clipboard",
            "title": task.title,
            "summary": summary,
            "url": task.get_absolute_url(),
        })

    for fu in FollowUp.objects.select_related("task", "stakeholder").order_by("-outreach_date")[:limit]:
        items.append({
            "date": fu.outreach_date,
            "type": "followup",
            "color": "amber",
            "icon": "arrow-path",
            "title": f"Follow-up: {fu.stakeholder.name}",
            "summary": fu.notes_text[:120] if fu.notes_text else f"Re: {fu.task.title}",
            "url": fu.get_absolute_url(),
        })

    for entry in CashFlowEntry.objects.order_by("-date")[:limit]:
        color = "green" if entry.entry_type == "inflow" else "red"
        items.append({
            "date": timezone.make_aware(
                timezone.datetime.combine(entry.date, timezone.datetime.min.time())
            ),
            "type": "cashflow",
            "color": color,
            "icon": "currency-dollar",
            "title": entry.description,
            "summary": f"{'+'if entry.entry_type == 'inflow' else '-'}${entry.amount:,.0f}",
            "url": entry.get_absolute_url(),
        })

    for ev in Evidence.objects.select_related("legal_matter").order_by("-created_at")[:limit]:
        items.append({
            "date": ev.created_at,
            "type": "evidence",
            "color": "purple",
            "icon": "document",
            "title": ev.title,
            "summary": f"Added to {ev.legal_matter.title}",
            "url": ev.get_absolute_url(),
        })

    items.sort(key=lambda x: x["date"], reverse=True)
    return items[:limit]


def activity_timeline(request):
    items = get_activity_timeline(limit=100)
    return render(request, "dashboard/timeline.html", {"timeline_items": items})


def calendar_view(request):
    return render(request, "dashboard/calendar.html")


def _parse_date(value):
    """Parse ISO datetime string from FullCalendar into a date object."""
    if not value:
        return None
    try:
        return dt.fromisoformat(value).date()
    except ValueError:
        return None


def calendar_events(request):
    """JSON endpoint for FullCalendar events."""
    start = _parse_date(request.GET.get("start", ""))
    end = _parse_date(request.GET.get("end", ""))
    events = []

    # Task events - color by priority
    priority_colors = {
        "critical": "#ef4444",
        "high": "#f97316",
        "medium": "#eab308",
        "low": "#9ca3af",
    }
    tasks = Task.objects.exclude(status="complete")
    if start:
        tasks = tasks.filter(due_date__gte=start)
    if end:
        tasks = tasks.filter(due_date__lte=end)
    direction_prefixes = {"outbound": "[OUT] ", "inbound": "[IN] "}
    for task in tasks.filter(due_date__isnull=False):
        prefix = direction_prefixes.get(task.direction, "")
        if task.is_meeting:
            event = {
                "title": f"{prefix}{task.title}",
                "start": task.scheduled_datetime_str,
                "url": task.get_absolute_url(),
                "color": "#3b82f6",
                "display": "block",
                "extendedProps": {"type": "meeting"},
            }
        else:
            event = {
                "title": f"{prefix}{task.title}",
                "start": task.scheduled_datetime_str,
                "url": task.get_absolute_url(),
                "color": priority_colors.get(task.priority, "#9ca3af"),
                "extendedProps": {"type": "task"},
            }
        events.append(event)

    # Loan payment events (red)
    loans = Loan.objects.filter(status="active", next_payment_date__isnull=False)
    if start:
        loans = loans.filter(next_payment_date__gte=start)
    if end:
        loans = loans.filter(next_payment_date__lte=end)
    for loan in loans:
        events.append({
            "title": f"Payment: {loan.name}",
            "start": str(loan.next_payment_date),
            "url": loan.get_absolute_url(),
            "color": "#dc2626",
            "extendedProps": {"type": "payment"},
        })

    # Follow-up events (amber)
    followups = FollowUp.objects.filter(response_received=False).select_related("task", "stakeholder")
    if start:
        followups = followups.filter(outreach_date__date__gte=start)
    if end:
        followups = followups.filter(outreach_date__date__lte=end)
    for fu in followups:
        events.append({
            "title": f"Follow-up: {fu.stakeholder.name}",
            "start": str(fu.outreach_date.date()),
            "url": fu.get_absolute_url(),
            "color": "#f59e0b",
            "extendedProps": {"type": "followup"},
        })

    # Legal filing dates (purple)
    matters = LegalMatter.objects.filter(filing_date__isnull=False).exclude(status="resolved")
    if start:
        matters = matters.filter(filing_date__gte=start)
    if end:
        matters = matters.filter(filing_date__lte=end)
    for matter in matters:
        events.append({
            "title": f"Legal: {matter.title}",
            "start": str(matter.filing_date),
            "url": matter.get_absolute_url(),
            "color": "#a855f7",
            "extendedProps": {"type": "legal"},
        })

    # Legal hearing dates (dark purple)
    hearings = LegalMatter.objects.filter(next_hearing_date__isnull=False).exclude(status="resolved")
    if start:
        hearings = hearings.filter(next_hearing_date__gte=start)
    if end:
        hearings = hearings.filter(next_hearing_date__lte=end)
    for matter in hearings:
        events.append({
            "title": f"Hearing: {matter.title}",
            "start": str(matter.next_hearing_date),
            "url": matter.get_absolute_url(),
            "color": "#7c3aed",
            "extendedProps": {"type": "hearing"},
        })

    # Contact follow-up dates (blue)
    contacts = ContactLog.objects.filter(
        follow_up_needed=True, follow_up_date__isnull=False
    ).select_related("stakeholder")
    if start:
        contacts = contacts.filter(follow_up_date__gte=start)
    if end:
        contacts = contacts.filter(follow_up_date__lte=end)
    for log in contacts:
        events.append({
            "title": f"Contact: {log.stakeholder.name}",
            "start": str(log.follow_up_date),
            "url": log.get_absolute_url(),
            "color": "#06b6d4",
            "extendedProps": {"type": "contact"},
        })

    return JsonResponse(events, safe=False)


def email_settings(request):
    from dashboard.forms import EmailSettingsForm
    from dashboard.models import EmailSettings

    instance = EmailSettings.load()
    if request.method == "POST":
        form = EmailSettingsForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, "Email settings saved.")
            return redirect("dashboard:email_settings")
    else:
        form = EmailSettingsForm(instance=instance)
    return render(request, "dashboard/email_settings.html", {"form": form})


@require_POST
def test_email(request):
    from dashboard.email import get_notification_addresses, get_smtp_connection

    try:
        connection = get_smtp_connection()
        from_email, admin_email = get_notification_addresses()
        send_mail(
            subject="[Control Center] Test Email",
            message="This is a test email from Control Center. If you see this, your SMTP settings are working.",
            from_email=from_email,
            recipient_list=[admin_email],
            connection=connection,
        )
        return render(request, "dashboard/partials/_test_email_result.html", {
            "success": True,
            "message": f"Test email sent to {admin_email}.",
        })
    except Exception as e:
        return render(request, "dashboard/partials/_test_email_result.html", {
            "success": False,
            "message": f"Failed to send: {e}",
        })


def notifications_list(request):
    from dashboard.models import Notification
    notifications = Notification.objects.all()[:100]
    return render(request, "dashboard/notifications.html", {"notifications": notifications})


def notifications_badge(request):
    from dashboard.models import Notification
    count = Notification.objects.filter(is_read=False).count()
    return render(request, "dashboard/partials/_notification_badge.html", {"unread_count": count})


@require_POST
def notifications_mark_read(request):
    from dashboard.models import Notification
    Notification.objects.filter(is_read=False).update(is_read=True)
    return render(request, "dashboard/partials/_notification_badge.html", {"unread_count": 0})


def choice_settings(request):
    from dashboard.models import CATEGORY_CHOICES, ChoiceOption
    categories = []
    for cat_value, cat_label in CATEGORY_CHOICES:
        options = ChoiceOption.objects.filter(category=cat_value)
        categories.append({
            "key": cat_value,
            "label": cat_label,
            "options": options,
        })
    return render(request, "dashboard/choice_settings.html", {"categories": categories})


def choice_add(request, category):
    from dashboard.choices import invalidate_choice_cache
    from dashboard.forms import ChoiceOptionForm
    from dashboard.models import CATEGORY_CHOICES, ChoiceOption

    if request.method == "POST":
        form = ChoiceOptionForm(request.POST, category=category)
        if form.is_valid():
            form.save()
            invalidate_choice_cache()
            options = ChoiceOption.objects.filter(category=category)
            cat_label = dict(CATEGORY_CHOICES).get(category, category)
            return render(request, "dashboard/partials/_choice_category.html", {
                "cat": {"key": category, "label": cat_label, "options": options},
            })
    else:
        form = ChoiceOptionForm(category=category)
    return render(request, "dashboard/partials/_choice_add_form.html", {
        "form": form, "category": category,
    })


def choice_edit(request, pk):
    from dashboard.choices import invalidate_choice_cache
    from dashboard.forms import ChoiceOptionForm
    from dashboard.models import CATEGORY_CHOICES, ChoiceOption

    option = get_object_or_404(ChoiceOption, pk=pk)
    if request.method == "POST":
        form = ChoiceOptionForm(request.POST, instance=option, category=option.category)
        if form.is_valid():
            form.save()
            invalidate_choice_cache()
            options = ChoiceOption.objects.filter(category=option.category)
            cat_label = dict(CATEGORY_CHOICES).get(option.category, option.category)
            return render(request, "dashboard/partials/_choice_category.html", {
                "cat": {"key": option.category, "label": cat_label, "options": options},
            })
    else:
        form = ChoiceOptionForm(instance=option, category=option.category)
    return render(request, "dashboard/partials/_choice_edit_form.html", {
        "form": form, "option": option,
    })


@require_POST
def choice_toggle(request, pk):
    from dashboard.choices import invalidate_choice_cache
    from dashboard.models import CATEGORY_CHOICES, ChoiceOption

    option = get_object_or_404(ChoiceOption, pk=pk)
    option.is_active = not option.is_active
    option.save()
    invalidate_choice_cache()
    options = ChoiceOption.objects.filter(category=option.category)
    cat_label = dict(CATEGORY_CHOICES).get(option.category, option.category)
    return render(request, "dashboard/partials/_choice_category.html", {
        "cat": {"key": option.category, "label": cat_label, "options": options},
    })


@require_POST
def choice_move(request, pk, direction):
    from dashboard.choices import invalidate_choice_cache
    from dashboard.models import CATEGORY_CHOICES, ChoiceOption

    option = get_object_or_404(ChoiceOption, pk=pk)
    siblings = list(ChoiceOption.objects.filter(category=option.category))
    idx = next((i for i, o in enumerate(siblings) if o.pk == option.pk), None)
    if idx is not None:
        swap_idx = idx - 1 if direction == "up" else idx + 1
        if 0 <= swap_idx < len(siblings):
            siblings[idx].sort_order, siblings[swap_idx].sort_order = (
                siblings[swap_idx].sort_order, siblings[idx].sort_order,
            )
            siblings[idx].save()
            siblings[swap_idx].save()
            invalidate_choice_cache()
    options = ChoiceOption.objects.filter(category=option.category)
    cat_label = dict(CATEGORY_CHOICES).get(option.category, option.category)
    return render(request, "dashboard/partials/_choice_category.html", {
        "cat": {"key": option.category, "label": cat_label, "options": options},
    })


def settings_hub(request):
    status = SampleDataStatus.load()
    return render(request, "dashboard/settings_hub.html", {"sample_status": status})


@require_POST
def sample_data_load(request):
    from django.core.management import call_command
    from io import StringIO

    out = StringIO()
    call_command("load_sample_data", stdout=out)
    status = SampleDataStatus.load()
    return render(request, "dashboard/partials/_sample_data_card.html", {
        "sample_status": status,
        "message": out.getvalue().strip(),
    })


@require_POST
def sample_data_remove(request):
    from django.apps import apps

    status = SampleDataStatus.load()
    if not status.is_loaded or not status.manifest:
        status.is_loaded = False
        status.manifest = {}
        status.loaded_at = None
        status.save()
        return render(request, "dashboard/partials/_sample_data_card.html", {
            "sample_status": status,
        })

    # Delete in reverse-dependency order (children before parents)
    deletion_order = [
        "notes.note",
        "notes.tag",
        "notes.folder",
        "cashflow.cashflowentry",
        "tasks.followup",
        "tasks.task",
        "legal.evidence",
        "legal.legalmatter",
        "assets.loanparty",
        "assets.investmentparticipant",
        "assets.propertyownership",
        "assets.loan",
        "assets.investment",
        "assets.realestate",
        "stakeholders.contactlog",
        "stakeholders.relationship",
        "stakeholders.stakeholder",
    ]

    for model_label in deletion_order:
        pks = status.manifest.get(model_label, [])
        if pks:
            Model = apps.get_model(model_label)
            Model.objects.filter(pk__in=pks).delete()

    status.is_loaded = False
    status.manifest = {}
    status.loaded_at = None
    status.save()

    return render(request, "dashboard/partials/_sample_data_card.html", {
        "sample_status": status,
    })
