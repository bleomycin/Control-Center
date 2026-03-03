from datetime import date, timedelta
from datetime import datetime as dt

from django.contrib import messages
from django.core.mail import send_mail
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

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
    ).select_related("related_stakeholder")

    # Upcoming tasks: due between today and today+14 days, not complete
    upcoming_tasks = Task.objects.filter(
        due_date__gte=today,
        due_date__lte=today + timedelta(days=14),
    ).exclude(
        status="complete",
    ).select_related("related_stakeholder")

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

    projected_inflows = current_month_entries.filter(
        entry_type="inflow", is_projected=True,
    ).aggregate(total=Sum("amount"))["total"] or 0

    projected_outflows = current_month_entries.filter(
        entry_type="outflow", is_projected=True,
    ).aggregate(total=Sum("amount"))["total"] or 0

    from cashflow.alerts import get_liquidity_alerts

    context = {
        "overdue_tasks": overdue_tasks,
        "upcoming_tasks": upcoming_tasks,
        "active_legal_matters": active_legal_matters,
        "recent_notes": recent_notes,
        "recent_activity": recent_activity,
        "stale_followups": stale_followups,
        "liquidity_alerts": get_liquidity_alerts(),
        "cashflow": {
            "actual_inflows": actual_inflows,
            "actual_outflows": actual_outflows,
            "projected_inflows": projected_inflows,
            "projected_outflows": projected_outflows,
        },
    }

    return render(request, "dashboard/index.html", context)


def global_search(request):
    q = request.GET.get("q", "").strip()
    context = {"query": q}

    if q:
        limit = 10
        context["stakeholders"] = Stakeholder.objects.filter(
            Q(name__icontains=q) | Q(organization__icontains=q)
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
            "title": f"{log.get_method_display()} with {log.stakeholder.name}",
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
        items.append({
            "date": task.created_at,
            "type": "task",
            "color": "yellow",
            "icon": "clipboard",
            "title": task.title,
            "summary": f"{task.get_status_display()} / {task.get_priority_display()}",
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
    for task in tasks.filter(due_date__isnull=False):
        events.append({
            "title": task.title,
            "start": str(task.due_date),
            "url": task.get_absolute_url(),
            "color": priority_colors.get(task.priority, "#9ca3af"),
            "extendedProps": {"type": "task"},
        })

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
            "color": "#3b82f6",
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
