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

    # Stale follow-ups: no response, reminder enabled, outreach > 3 days ago
    stale_followups = FollowUp.objects.filter(
        response_received=False,
        reminder_enabled=True,
        outreach_date__lt=now - timedelta(days=3),
    ).exclude(
        task__status="complete",
    ).select_related("task", "stakeholder")

    from cashflow.alerts import get_liquidity_alerts

    # Asset overview counts & values (for asset summary card)
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

    active_loans_qs = Loan.objects.filter(status="active")
    total_liabilities = active_loans_qs.aggregate(
        total=Sum("current_balance"),
    )["total"] or 0
    active_loan_count = active_loans_qs.count()

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
    from healthcare.models import Appointment as HcDeadlineAppt
    for appt in HcDeadlineAppt.objects.filter(
        date__gte=today, date__lte=deadline_horizon,
    ).exclude(status__in=["completed", "cancelled"]).select_related("provider"):
        title = appt.title
        if appt.time:
            title = f"{appt.title} — {appt.time.strftime('%-I:%M %p')}"
        upcoming_deadlines.append({
            "date": appt.date, "type": "appointment", "color": "teal",
            "title": title, "url": appt.get_absolute_url(),
        })
    upcoming_deadlines.sort(key=lambda x: x["date"])

    # Healthcare summary — only show when upcoming appointments exist
    from healthcare.models import Appointment as HcAppt
    upcoming_appointments = HcAppt.objects.filter(
        date__gte=today, date__lte=today + timedelta(days=14),
    ).exclude(status__in=["completed", "cancelled"]).select_related("provider").order_by("date", "time")

    # Asset Risk
    at_risk_properties = RealEstate.objects.filter(
        Q(status="in_dispute") | Q(legal_matters__status__in=["active", "pending"]),
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
        "upcoming_appointments": upcoming_appointments,
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
        from assets.models import Lease
        context["leases"] = Lease.objects.filter(name__icontains=q).select_related("related_property")[:limit]
        from healthcare.models import Provider, Prescription, Appointment
        context["hc_providers"] = Provider.objects.filter(
            Q(name__icontains=q) | Q(specialty__icontains=q) | Q(practice_name__icontains=q)
        )[:limit]
        context["hc_prescriptions"] = Prescription.objects.filter(
            Q(medication_name__icontains=q) | Q(generic_name__icontains=q)
        )[:limit]
        context["hc_appointments"] = Appointment.objects.filter(
            Q(title__icontains=q) | Q(purpose__icontains=q)
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
            context["leases"],
            context["hc_providers"],
            context["hc_prescriptions"],
            context["hc_appointments"],
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
            "title": f"{get_choice_label('contact_method', log.method)} with {log.stakeholder.name if log.stakeholder else 'Unknown'}",
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
            "title": f"Follow-up: {fu.stakeholder.name if fu.stakeholder else 'Unknown'}",
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

    from healthcare.models import Visit, Appointment
    for visit in Visit.objects.select_related("provider").order_by("-created_at")[:limit]:
        items.append({
            "date": visit.created_at,
            "type": "visit",
            "color": "teal",
            "icon": "heart",
            "title": f"Visit: {visit.provider.name if visit.provider else visit.facility or 'Office visit'}",
            "summary": visit.reason[:120] if visit.reason else visit.get_visit_type_display(),
            "url": visit.get_absolute_url(),
        })
    for appt in Appointment.objects.select_related("provider").order_by("-created_at")[:limit]:
        items.append({
            "date": appt.created_at,
            "type": "appointment",
            "color": "teal",
            "icon": "heart",
            "title": appt.title,
            "summary": f"{appt.get_status_display()} — {appt.provider.name if appt.provider else 'No provider'}",
            "url": appt.get_absolute_url(),
        })

    items.sort(key=lambda x: x["date"], reverse=True)
    return items[:limit]


def activity_timeline(request):
    """Full timeline page with filtering, date grouping, pagination, and stats."""
    from itertools import groupby

    PAGE_SIZE = 50

    # --- Parse filter params ---
    selected_types = [t for t in request.GET.getlist("type") if t]
    date_from_str = request.GET.get("date_from", "")
    date_to_str = request.GET.get("date_to", "")
    stakeholder_id = request.GET.get("stakeholder", "")
    page = int(request.GET.get("page", "1") or 1)

    date_from = None
    date_to = None
    if date_from_str:
        try:
            date_from = timezone.make_aware(
                timezone.datetime.combine(date.fromisoformat(date_from_str), timezone.datetime.min.time())
            )
        except ValueError:
            pass
    if date_to_str:
        try:
            date_to = timezone.make_aware(
                timezone.datetime.combine(date.fromisoformat(date_to_str), timezone.datetime.max.time())
            )
        except ValueError:
            pass

    ALL_TYPES = ["contact", "note", "task", "followup", "cashflow", "evidence"]
    # If the filter form was submitted (has "filtered" param) but no types
    # are checked, show nothing. On initial page load (no "filtered" param),
    # default to showing all types.
    is_filtered = "filtered" in request.GET
    if selected_types:
        active_types = set(selected_types)
    elif is_filtered:
        active_types = set()
    else:
        active_types = set(ALL_TYPES)

    # --- Build items (fetch generously, filter in Python) ---
    FETCH_LIMIT = 500
    items = []

    stakeholder_obj = None
    if stakeholder_id:
        try:
            stakeholder_obj = Stakeholder.objects.get(pk=int(stakeholder_id))
        except (ValueError, Stakeholder.DoesNotExist):
            pass

    if "contact" in active_types:
        qs = ContactLog.objects.select_related("stakeholder").order_by("-date")
        if stakeholder_obj:
            qs = qs.filter(stakeholder=stakeholder_obj)
        for log in qs[:FETCH_LIMIT]:
            items.append({
                "date": log.date,
                "type": "contact",
                "color": "blue",
                "icon": "phone",
                "title": f"{get_choice_label('contact_method', log.method)} with {log.stakeholder.name if log.stakeholder else 'Unknown'}",
                "summary": log.summary[:120],
                "url": log.get_absolute_url(),
                "amount": None,
            })

    if "note" in active_types:
        qs = Note.objects.order_by("-date")
        if stakeholder_obj:
            qs = qs.filter(
                Q(participants=stakeholder_obj) | Q(related_stakeholders=stakeholder_obj)
            ).distinct()
        for note in qs[:FETCH_LIMIT]:
            items.append({
                "date": note.date,
                "type": "note",
                "color": "indigo",
                "icon": "pencil",
                "title": note.title,
                "summary": note.content[:120],
                "url": note.get_absolute_url(),
                "amount": None,
            })

    if "task" in active_types:
        qs = Task.objects.order_by("-created_at")
        if stakeholder_obj:
            qs = qs.filter(related_stakeholders=stakeholder_obj)
        for task in qs[:FETCH_LIMIT]:
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
                "amount": None,
            })

    if "followup" in active_types:
        qs = FollowUp.objects.select_related("task", "stakeholder").order_by("-outreach_date")
        if stakeholder_obj:
            qs = qs.filter(stakeholder=stakeholder_obj)
        for fu in qs[:FETCH_LIMIT]:
            items.append({
                "date": fu.outreach_date,
                "type": "followup",
                "color": "amber",
                "icon": "arrow-path",
                "title": f"Follow-up: {fu.stakeholder.name if fu.stakeholder else 'Unknown'}",
                "summary": fu.notes_text[:120] if fu.notes_text else f"Re: {fu.task.title}",
                "url": fu.get_absolute_url(),
                "amount": None,
            })

    if "cashflow" in active_types:
        qs = CashFlowEntry.objects.order_by("-date")
        if stakeholder_obj:
            qs = qs.filter(related_stakeholder=stakeholder_obj)
        for entry in qs[:FETCH_LIMIT]:
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
                "amount": entry.amount if entry.entry_type == "inflow" else -entry.amount,
            })

    if "evidence" in active_types:
        qs = Evidence.objects.select_related("legal_matter").order_by("-created_at")
        if stakeholder_obj:
            qs = qs.filter(legal_matter__related_stakeholders=stakeholder_obj)
        for ev in qs[:FETCH_LIMIT]:
            items.append({
                "date": ev.created_at,
                "type": "evidence",
                "color": "purple",
                "icon": "document",
                "title": ev.title,
                "summary": f"Added to {ev.legal_matter.title}",
                "url": ev.get_absolute_url(),
                "amount": None,
            })

    # --- Apply date range filter ---
    if date_from:
        items = [i for i in items if i["date"] >= date_from]
    if date_to:
        items = [i for i in items if i["date"] <= date_to]

    # --- Sort and compute stats before pagination ---
    items.sort(key=lambda x: x["date"], reverse=True)

    total_count = len(items)
    type_counts = {}
    for t in ALL_TYPES:
        type_counts[t] = sum(1 for i in items if i["type"] == t)
    cashflow_inflows = sum(i["amount"] for i in items if i["type"] == "cashflow" and i["amount"] and i["amount"] > 0)
    cashflow_outflows = sum(abs(i["amount"]) for i in items if i["type"] == "cashflow" and i["amount"] and i["amount"] < 0)
    cashflow_net = cashflow_inflows - cashflow_outflows

    # --- Paginate ---
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = items[start:end]
    has_next = end < total_count
    has_prev = page > 1

    # --- Group by date ---
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=today.weekday())

    def date_group_key(item):
        d = timezone.localdate(item["date"])
        if d == today:
            return "Today"
        if d > today:
            return "Upcoming"
        if d == yesterday:
            return "Yesterday"
        if d >= week_start:
            return "This Week"
        if d.year == today.year and d.month == today.month:
            return "This Month"
        return d.strftime("%B %Y")

    grouped_items = []
    for group_label, group_iter in groupby(page_items, key=date_group_key):
        grouped_items.append({"label": group_label, "items": list(group_iter)})

    # --- Context ---
    stakeholders = Stakeholder.objects.order_by("name")
    context = {
        "grouped_items": grouped_items,
        "timeline_items": page_items,
        "total_count": total_count,
        "type_counts": type_counts,
        "cashflow_inflows": cashflow_inflows,
        "cashflow_outflows": cashflow_outflows,
        "cashflow_net": cashflow_net,
        "all_types": ALL_TYPES,
        "selected_types": selected_types,
        "date_from": date_from_str,
        "date_to": date_to_str,
        "stakeholder_id": stakeholder_id,
        "stakeholders": stakeholders,
        "page": page,
        "has_next": has_next,
        "has_prev": has_prev,
        "next_page": page + 1,
        "prev_page": page - 1,
    }

    if request.headers.get("HX-Request"):
        return render(request, "dashboard/partials/_timeline_content.html", context)
    return render(request, "dashboard/timeline.html", context)


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


def calendar_feed(request):
    """ICS feed endpoint for subscribing from iPhone/Google Calendar."""
    from datetime import datetime
    from django.http import HttpResponse
    from icalendar import Calendar, Event
    from dashboard.models import CalendarFeedSettings

    settings = CalendarFeedSettings.load()
    if not settings.enabled or not settings.token:
        return HttpResponse("Feed not enabled", status=404)
    if request.GET.get("token") != settings.token:
        return HttpResponse("Invalid token", status=403)

    cal = Calendar()
    cal.add("prodid", "-//Control Center//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "Control Center")

    today = timezone.localdate()
    window_start = today - timedelta(days=30)
    window_end = today + timedelta(days=90)
    types = settings.get_event_types()
    base_url = request.build_absolute_uri("/").rstrip("/")

    def _add_alarms(ev, event_type):
        """Add VALARM reminders for an event type based on settings."""
        from icalendar import Alarm
        for minutes in settings.get_reminders(event_type):
            alarm = Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", "Reminder")
            alarm.add("trigger", timedelta(minutes=-minutes))
            ev.add_component(alarm)

    # Tasks & meetings (separate toggles)
    include_tasks = types.get("tasks", True)
    include_meetings = types.get("meetings", True)
    if include_tasks or include_meetings:
        tasks = Task.objects.exclude(status="complete").filter(
            due_date__isnull=False, due_date__gte=window_start, due_date__lte=window_end,
        )
        direction_prefixes = {"outbound": "\u2197 ", "inbound": "\u2199 "}
        for task in tasks:
            if task.is_meeting and not include_meetings:
                continue
            if not task.is_meeting and not include_tasks:
                continue
            prefix = direction_prefixes.get(task.direction, "")
            ev = Event()
            ev.add("summary", f"{prefix}{task.title}")
            if task.is_meeting and task.due_time:
                start = datetime.combine(task.due_date, task.due_time)
                ev.add("dtstart", start)
                if task.duration_minutes:
                    ev.add("dtend", start + timedelta(minutes=task.duration_minutes))
                _add_alarms(ev, "meetings")
            else:
                ev.add("dtstart", task.due_date)
                _add_alarms(ev, "meetings" if task.is_meeting else "tasks")
            if task.description:
                ev.add("description", task.description)
            ev.add("url", f"{base_url}{task.get_absolute_url()}")
            ev.add("uid", f"task-{task.pk}@controlcenter")
            cal.add_component(ev)

    # Loan payments
    if types.get("payments", True):
        loans = Loan.objects.filter(
            status="active", next_payment_date__isnull=False,
            next_payment_date__gte=window_start, next_payment_date__lte=window_end,
        )
        for loan in loans:
            ev = Event()
            title = f"${loan.monthly_payment:,.0f} — {loan.name}" if loan.monthly_payment else f"Payment: {loan.name}"
            ev.add("summary", title)
            ev.add("dtstart", loan.next_payment_date)
            _add_alarms(ev, "payments")
            ev.add("url", f"{base_url}{loan.get_absolute_url()}")
            ev.add("uid", f"loan-{loan.pk}@controlcenter")
            cal.add_component(ev)

    # Follow-ups
    if types.get("followups", True):
        followups = FollowUp.objects.filter(
            response_received=False,
        ).select_related("stakeholder")
        for fu in followups:
            fu_date = timezone.localdate(fu.outreach_date)
            if fu_date < window_start or fu_date > window_end:
                continue
            ev = Event()
            ev.add("summary", f"Follow-up: {fu.stakeholder.name if fu.stakeholder else 'Unknown'}")
            ev.add("dtstart", fu_date)
            _add_alarms(ev, "followups")
            if fu.notes_text:
                ev.add("description", fu.notes_text)
            ev.add("url", f"{base_url}{fu.get_absolute_url()}")
            ev.add("uid", f"followup-{fu.pk}@controlcenter")
            cal.add_component(ev)

    # Legal matters & hearings
    if types.get("legal", True):
        matters = LegalMatter.objects.exclude(status="resolved")
        for matter in matters:
            if matter.filing_date and window_start <= matter.filing_date <= window_end:
                ev = Event()
                ev.add("summary", f"Legal: {matter.title}")
                ev.add("dtstart", matter.filing_date)
                _add_alarms(ev, "legal")
                if matter.description:
                    ev.add("description", matter.description)
                ev.add("url", f"{base_url}{matter.get_absolute_url()}")
                ev.add("uid", f"legal-{matter.pk}@controlcenter")
                cal.add_component(ev)
            if matter.next_hearing_date and window_start <= matter.next_hearing_date <= window_end:
                ev = Event()
                ev.add("summary", f"Hearing: {matter.title}")
                ev.add("dtstart", matter.next_hearing_date)
                _add_alarms(ev, "legal")
                if matter.description:
                    ev.add("description", matter.description)
                ev.add("url", f"{base_url}{matter.get_absolute_url()}")
                ev.add("uid", f"hearing-{matter.pk}@controlcenter")
                cal.add_component(ev)

    # Contact follow-ups
    if types.get("contacts", True):
        contacts = ContactLog.objects.filter(
            follow_up_needed=True, follow_up_date__isnull=False,
            follow_up_date__gte=window_start, follow_up_date__lte=window_end,
        ).select_related("stakeholder")
        for log in contacts:
            ev = Event()
            ev.add("summary", f"Contact: {log.stakeholder.name if log.stakeholder else 'Unknown'}")
            ev.add("dtstart", log.follow_up_date)
            _add_alarms(ev, "contacts")
            if log.summary:
                ev.add("description", log.summary)
            ev.add("url", f"{base_url}{log.get_absolute_url()}")
            ev.add("uid", f"contact-{log.pk}@controlcenter")
            cal.add_component(ev)

    # Healthcare appointments
    if types.get("appointments", True):
        from healthcare.models import Appointment as HcAppointment
        hc_appts = HcAppointment.objects.exclude(
            status__in=["completed", "cancelled"],
        ).filter(
            date__gte=window_start, date__lte=window_end,
        ).select_related("provider")
        for appt in hc_appts:
            ev = Event()
            ev.add("summary", appt.title)
            if appt.time:
                start = datetime.combine(appt.date, appt.time)
                ev.add("dtstart", start)
                if appt.duration_minutes:
                    ev.add("dtend", start + timedelta(minutes=appt.duration_minutes))
            else:
                ev.add("dtstart", appt.date)
            _add_alarms(ev, "appointments")
            desc_parts = []
            if appt.purpose:
                desc_parts.append(appt.purpose)
            if appt.provider:
                desc_parts.append(f"Provider: {appt.provider.name}")
            if appt.facility:
                desc_parts.append(f"Location: {appt.facility}")
            if appt.address:
                desc_parts.append(f"Address: {appt.address}")
                from urllib.parse import quote
                maps_url = f"https://maps.apple.com/?address={quote(appt.address)}"
                desc_parts.append(f"Map: {maps_url}")
            # Always include Control Center link in description
            desc_parts.append(f"Details: {base_url}{appt.get_absolute_url()}")
            ev.add("description", "\n".join(desc_parts))
            # LOCATION: combine facility + address
            location_parts = []
            if appt.facility:
                location_parts.append(appt.facility)
            if appt.address:
                location_parts.append(appt.address)
            if location_parts:
                ev.add("location", ", ".join(location_parts))
            # URL: prefer user-provided URL, fall back to detail page
            if appt.url:
                ev.add("url", appt.url)
            else:
                ev.add("url", f"{base_url}{appt.get_absolute_url()}")
            ev.add("uid", f"appt-{appt.pk}@controlcenter")
            cal.add_component(ev)

    # Prescription refills
    if types.get("refills", True):
        from healthcare.models import Prescription as HcPrescription
        hc_refills = HcPrescription.objects.filter(
            status="active", next_refill_date__isnull=False,
            next_refill_date__gte=window_start, next_refill_date__lte=window_end,
        )
        for rx in hc_refills:
            ev = Event()
            ev.add("summary", f"Refill: {rx.medication_name}")
            ev.add("dtstart", rx.next_refill_date)
            _add_alarms(ev, "refills")
            desc_parts = [f"Medication: {rx.medication_name}"]
            if rx.dosage:
                desc_parts.append(f"Dosage: {rx.dosage}")
            if rx.pharmacy:
                desc_parts.append(f"Pharmacy: {rx.pharmacy}")
            ev.add("description", "\n".join(desc_parts))
            ev.add("url", f"{base_url}{rx.get_absolute_url()}")
            ev.add("uid", f"refill-{rx.pk}@controlcenter")
            cal.add_component(ev)

    # Lease expiry
    if types.get("leases", True):
        from assets.models import Lease
        lease_qs = Lease.objects.filter(
            status__in=["active", "month_to_month"],
            end_date__isnull=False,
            end_date__gte=window_start, end_date__lte=window_end,
        )
        for lease in lease_qs:
            ev = Event()
            title = f"${lease.monthly_rent:,.0f}/mo — {lease.name}" if lease.monthly_rent else f"Lease expires: {lease.name}"
            ev.add("summary", title)
            ev.add("dtstart", lease.end_date)
            _add_alarms(ev, "leases")
            ev.add("url", f"{base_url}{lease.get_absolute_url()}")
            ev.add("uid", f"lease-{lease.pk}@controlcenter")
            cal.add_component(ev)

    response = HttpResponse(cal.to_ical(), content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'inline; filename="controlcenter.ics"'
    return response


def calendar_feed_settings(request):
    """Settings page for the ICS calendar feed."""
    from dashboard.models import CalendarFeedSettings

    settings = CalendarFeedSettings.load()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "toggle":
            settings.enabled = not settings.enabled
            if settings.enabled and not settings.token:
                settings.regenerate_token()
            settings.save()
        elif action == "regenerate":
            settings.regenerate_token()
        elif action == "update_types":
            new_types = {}
            for key in CalendarFeedSettings.EVENT_TYPE_DEFAULTS:
                new_types[key] = key in request.POST.getlist("event_types")
            settings.event_types = new_types
            settings.save()
        elif action == "update_reminders":
            new_reminders = {}
            for key in CalendarFeedSettings.REMINDER_DEFAULTS:
                vals = []
                for slot in ("1", "2"):
                    raw = request.POST.get(f"reminder_{key}_{slot}", "")
                    if raw:
                        try:
                            vals.append(int(raw))
                        except ValueError:
                            pass
                # Sort descending so longer reminder comes first
                new_reminders[key] = sorted(vals, reverse=True)
            settings.reminders = new_reminders
            settings.save()
        return redirect("dashboard:calendar_feed_settings")

    feed_url = ""
    if settings.enabled and settings.token:
        feed_url = request.build_absolute_uri(
            f"/calendar/feed.ics?token={settings.token}"
        )

    type_labels = {
        "tasks": "Tasks",
        "meetings": "Meetings",
        "payments": "Loan payments",
        "followups": "Follow-ups",
        "legal": "Legal matters & hearings",
        "contacts": "Contact follow-ups",
        "appointments": "Healthcare appointments",
        "refills": "Prescription refills",
        "leases": "Lease expiry dates",
    }
    current_types = settings.get_event_types()
    event_type_choices = [
        {"key": key, "label": type_labels[key], "checked": current_types.get(key, True)}
        for key in CalendarFeedSettings.EVENT_TYPE_DEFAULTS
    ]

    reminder_options = [
        ("", "None"),
        ("5", "5 minutes"),
        ("10", "10 minutes"),
        ("15", "15 minutes"),
        ("30", "30 minutes"),
        ("60", "1 hour"),
        ("120", "2 hours"),
        ("1440", "1 day"),
        ("2880", "2 days"),
    ]
    reminder_config = []
    for key in CalendarFeedSettings.REMINDER_DEFAULTS:
        vals = settings.get_reminders(key)
        reminder_config.append({
            "key": key,
            "label": type_labels[key],
            "val1": str(vals[0]) if len(vals) > 0 else "",
            "val2": str(vals[1]) if len(vals) > 1 else "",
        })

    return render(request, "dashboard/calendar_feed_settings.html", {
        "settings": settings,
        "feed_url": feed_url,
        "event_type_choices": event_type_choices,
        "reminder_config": reminder_config,
        "reminder_options": reminder_options,
    })


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
    direction_prefixes = {"outbound": "\u2197 ", "inbound": "\u2199 "}
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
            if task.due_time:
                event["allDay"] = False
                if task.duration_minutes:
                    from datetime import datetime as dt_cls
                    end_dt = dt_cls.combine(task.due_date, task.due_time) + timedelta(minutes=task.duration_minutes)
                    event["end"] = end_dt.isoformat()
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
        title = f"Payment: {loan.name}"
        if loan.monthly_payment:
            title = f"${loan.monthly_payment:,.0f} — {loan.name}"
        events.append({
            "title": title,
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
            "title": f"Follow-up: {fu.stakeholder.name if fu.stakeholder else 'Unknown'}",
            "start": str(timezone.localdate(fu.outreach_date)),
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

    # Legal communication follow-ups (indigo)
    from legal.models import LegalCommunication
    legal_followups = LegalCommunication.objects.filter(
        follow_up_needed=True, follow_up_completed=False, follow_up_date__isnull=False
    ).select_related("stakeholder", "legal_matter")
    if start:
        legal_followups = legal_followups.filter(follow_up_date__gte=start)
    if end:
        legal_followups = legal_followups.filter(follow_up_date__lte=end)
    for lc in legal_followups:
        label = lc.stakeholder.name if lc.stakeholder else lc.legal_matter.title
        events.append({
            "title": f"Legal Follow-up: {label}",
            "start": str(lc.follow_up_date),
            "url": lc.legal_matter.get_absolute_url(),
            "color": "#6366f1",
            "extendedProps": {"type": "legal_followup"},
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
            "title": f"Contact: {log.stakeholder.name if log.stakeholder else 'Unknown'}",
            "start": str(log.follow_up_date),
            "url": log.get_absolute_url(),
            "color": "#06b6d4",
            "extendedProps": {"type": "contact"},
        })

    # Healthcare appointment events (teal)
    from healthcare.models import Appointment as HcAppointment, Prescription as HcPrescription
    hc_appts = HcAppointment.objects.exclude(status__in=["completed", "cancelled"]).select_related("provider")
    if start:
        hc_appts = hc_appts.filter(date__gte=start)
    if end:
        hc_appts = hc_appts.filter(date__lte=end)
    for appt in hc_appts:
        event = {
            "title": appt.title,
            "start": appt.scheduled_datetime_str,
            "url": appt.get_absolute_url(),
            "color": "#14b8a6",
            "extendedProps": {"type": "appointment"},
        }
        if appt.time:
            event["allDay"] = False
            if appt.duration_minutes:
                from datetime import datetime as dt_cls
                end_dt = dt_cls.combine(appt.date, appt.time) + timedelta(minutes=appt.duration_minutes)
                event["end"] = end_dt.isoformat()
        events.append(event)

    # Prescription refill events (amber)
    hc_refills = HcPrescription.objects.filter(
        status="active", next_refill_date__isnull=False,
    )
    if start:
        hc_refills = hc_refills.filter(next_refill_date__gte=start)
    if end:
        hc_refills = hc_refills.filter(next_refill_date__lte=end)
    for rx in hc_refills:
        events.append({
            "title": f"Refill: {rx.medication_name}",
            "start": str(rx.next_refill_date),
            "url": rx.get_absolute_url(),
            "color": "#f59e0b",
            "extendedProps": {"type": "refill"},
        })

    # Lease expiry events (emerald)
    from assets.models import Lease
    lease_qs = Lease.objects.filter(
        status__in=["active", "month_to_month"],
        end_date__isnull=False,
    )
    if start:
        lease_qs = lease_qs.filter(end_date__gte=start)
    if end:
        lease_qs = lease_qs.filter(end_date__lte=end)
    for lease in lease_qs:
        title = f"Lease expires: {lease.name}"
        if lease.monthly_rent:
            title = f"${lease.monthly_rent:,.0f}/mo — {lease.name}"
        events.append({
            "title": title,
            "start": str(lease.end_date),
            "url": lease.get_absolute_url(),
            "color": "#10b981",
            "extendedProps": {"type": "lease"},
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
    from dashboard.management.commands.load_sample_data import SECTION_ORDER, SECTION_LABELS
    status = SampleDataStatus.load()
    # Build per-section status info
    sections = []
    for key in SECTION_ORDER:
        sec_manifest = status.manifest.get(key, {})
        record_count = sum(len(v) for v in sec_manifest.values()) if sec_manifest else 0
        sections.append({
            "key": key,
            "label": SECTION_LABELS[key],
            "loaded": bool(sec_manifest),
            "record_count": record_count,
        })
    any_loaded = any(s["loaded"] for s in sections)
    return render(request, "dashboard/settings_hub.html", {
        "sample_status": status,
        "sample_sections": sections,
        "any_section_loaded": any_loaded,
    })


@require_POST
def sample_data_load(request):
    """Load all sample data sections."""
    from django.core.management import call_command
    from io import StringIO

    out = StringIO()
    call_command("load_sample_data", stdout=out)
    return _sample_data_card_response(request, out.getvalue().strip())


@require_POST
def sample_data_remove(request):
    """Remove all sample data sections."""
    from dashboard.management.commands.load_sample_data import SECTION_ORDER
    status = SampleDataStatus.load()
    if status.manifest:
        for section in SECTION_ORDER:
            _remove_section_data(status, section)
    status.is_loaded = False
    status.loaded_at = None
    status.save()
    return _sample_data_card_response(request)


@require_POST
def sample_data_load_section(request, section):
    """Load a single sample data section."""
    from django.core.management import call_command
    from io import StringIO
    from dashboard.management.commands.load_sample_data import SECTION_ORDER, SECTION_LABELS

    if section not in SECTION_ORDER:
        return _sample_data_card_response(request, f"Unknown section: {section}")

    out = StringIO()
    call_command("load_sample_data", "--sections", section, stdout=out)
    return _sample_data_card_response(
        request, f"{SECTION_LABELS[section]} loaded successfully."
    )


@require_POST
def sample_data_remove_section(request, section):
    """Remove a single sample data section."""
    from dashboard.management.commands.load_sample_data import SECTION_ORDER, SECTION_LABELS

    if section not in SECTION_ORDER:
        return _sample_data_card_response(request, f"Unknown section: {section}")

    status = SampleDataStatus.load()
    _remove_section_data(status, section)
    status.is_loaded = any(status.manifest.get(s) for s in SECTION_ORDER)
    if not status.is_loaded:
        status.loaded_at = None
    status.save()
    return _sample_data_card_response(
        request, f"{SECTION_LABELS[section]} removed."
    )


def _remove_section_data(status, section):
    """Delete all records for a single section from the DB and manifest."""
    from django.apps import apps
    from dashboard.management.commands.load_sample_data import SECTION_DELETION_ORDER

    sec_manifest = status.manifest.get(section, {})
    if not sec_manifest:
        return

    deletion_order = SECTION_DELETION_ORDER.get(section, [])
    for model_label in deletion_order:
        pks = sec_manifest.get(model_label, [])
        if pks:
            Model = apps.get_model(model_label)
            Model.objects.filter(pk__in=pks).delete()

    # Clean up extra stakeholders created by assets section
    extra_pks = sec_manifest.get("_extra_stakeholder_pks", [])
    if extra_pks:
        from stakeholders.models import Stakeholder
        Stakeholder.objects.filter(pk__in=extra_pks).delete()

    # Also handle old flat-format manifests (backward compat)
    for model_label in deletion_order:
        pks = status.manifest.get(model_label, [])
        if pks:
            Model = apps.get_model(model_label)
            Model.objects.filter(pk__in=pks).delete()
            del status.manifest[model_label]

    if section in status.manifest:
        del status.manifest[section]


def _sample_data_card_response(request, message=None):
    """Render the sample data card partial with current section status."""
    from dashboard.management.commands.load_sample_data import SECTION_ORDER, SECTION_LABELS

    status = SampleDataStatus.load()
    sections = []
    for key in SECTION_ORDER:
        sec_manifest = status.manifest.get(key, {})
        record_count = sum(len(v) for v in sec_manifest.values()) if sec_manifest else 0
        sections.append({
            "key": key,
            "label": SECTION_LABELS[key],
            "loaded": bool(sec_manifest),
            "record_count": record_count,
        })
    any_loaded = any(s["loaded"] for s in sections)
    return render(request, "dashboard/partials/_sample_data_card.html", {
        "sample_status": status,
        "sample_sections": sections,
        "any_section_loaded": any_loaded,
        "message": message,
    })


# ---------------------------------------------------------------------------
# Backup & Restore
# ---------------------------------------------------------------------------

def _get_backup_list():
    """Return list of backup dicts sorted newest-first."""
    from dashboard.management.commands.backup import get_backup_dir
    backup_dir = get_backup_dir()
    if not backup_dir.exists():
        return []
    archives = sorted(
        backup_dir.glob('controlcenter-backup-*.tar.gz'),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    results = []
    for a in archives:
        stat = a.stat()
        size_mb = stat.st_size / (1024 * 1024)
        results.append({
            'name': a.name,
            'size': f'{size_mb:.1f} MB' if size_mb >= 1 else f'{stat.st_size / 1024:.0f} KB',
            'date': dt.fromtimestamp(stat.st_mtime),
        })
    return results


def backup_settings(request):
    from dashboard.forms import BackupSettingsForm
    from dashboard.models import BackupSettings

    config = BackupSettings.load()
    form = BackupSettingsForm(instance=config)
    backups = _get_backup_list()
    return render(request, "dashboard/backup_settings.html", {
        "backups": backups, "config_form": form, "config": config,
    })


@require_POST
def backup_config_update(request):
    """Save backup configuration and sync the live Schedule record."""
    from dashboard.forms import BackupSettingsForm
    from dashboard.models import BackupSettings

    config = BackupSettings.load()
    form = BackupSettingsForm(request.POST, instance=config)
    if form.is_valid():
        form.save()
        # Sync the live django-q2 schedule immediately
        _sync_backup_schedule(config)
        message = "Backup configuration saved."
        msg_type = "success"
    else:
        message = "Please correct the errors below."
        msg_type = "error"
    return render(request, "dashboard/partials/_backup_config.html", {
        "config_form": form, "config": config,
        "message": message, "msg_type": msg_type,
    })


def _sync_backup_schedule(config):
    """Update or remove the django-q2 Schedule record based on BackupSettings."""
    from datetime import timedelta
    from django_q.models import Schedule
    from django.utils import timezone as tz

    schedule_name = "Automated Backup"

    if not config.enabled:
        Schedule.objects.filter(name=schedule_name).delete()
        return

    freq_map = {"D": Schedule.DAILY, "H": Schedule.HOURLY, "W": Schedule.WEEKLY}
    schedule_type = freq_map[config.frequency]

    local_tz = tz.get_current_timezone()
    now = tz.localtime(tz.now(), local_tz)
    next_run = now.replace(
        hour=config.time_hour, minute=config.time_minute,
        second=0, microsecond=0,
    )
    if next_run <= now:
        if config.frequency == "H":
            next_run += timedelta(hours=1)
        elif config.frequency == "W":
            next_run += timedelta(weeks=1)
        else:
            next_run += timedelta(days=1)

    Schedule.objects.update_or_create(
        name=schedule_name,
        defaults={
            "func": "dashboard.backup_task.run_backup",
            "schedule_type": schedule_type,
            "next_run": next_run,
        },
    )


@require_POST
def backup_create(request):
    from dashboard.management.commands.backup import create_backup
    try:
        archive_path = create_backup()
        message = f"Backup created: {archive_path.name}"
        msg_type = "success"
    except Exception as e:
        message = f"Backup failed: {e}"
        msg_type = "error"
    backups = _get_backup_list()
    return render(request, "dashboard/partials/_backup_list.html", {
        "backups": backups, "message": message, "msg_type": msg_type,
    })


def backup_download(request, filename):
    from django.http import FileResponse
    from dashboard.management.commands.backup import get_backup_dir
    import re

    if not re.match(r'^controlcenter-backup-[\d]{8}-[\d]{6}\.tar\.gz$', filename):
        from django.http import Http404
        raise Http404
    backup_dir = get_backup_dir()
    file_path = backup_dir / filename
    if not file_path.exists() or not file_path.resolve().parent == backup_dir.resolve():
        from django.http import Http404
        raise Http404
    return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=filename)


@require_POST
def backup_delete(request, filename):
    from dashboard.management.commands.backup import get_backup_dir
    import re

    if not re.match(r'^controlcenter-backup-[\d]{8}-[\d]{6}\.tar\.gz$', filename):
        from django.http import Http404
        raise Http404
    backup_dir = get_backup_dir()
    file_path = backup_dir / filename
    if file_path.exists() and file_path.resolve().parent == backup_dir.resolve():
        file_path.unlink()
    backups = _get_backup_list()
    return render(request, "dashboard/partials/_backup_list.html", {
        "backups": backups, "message": f"Deleted {filename}", "msg_type": "success",
    })


@require_POST
def backup_restore(request, filename=None):
    """Restore from an existing backup on disk or an uploaded file."""
    from dashboard.management.commands.backup import get_backup_dir
    import re
    import shutil
    import tarfile
    import tempfile
    from pathlib import Path
    from django.conf import settings as django_settings
    from django.core.management import call_command

    # Determine source: uploaded file or existing backup
    uploaded = request.FILES.get('archive')
    if uploaded:
        # Save upload to temp file, then validate & restore
        with tempfile.NamedTemporaryFile(delete=False, suffix='.tar.gz') as tmp:
            for chunk in uploaded.chunks():
                tmp.write(chunk)
            archive_path = Path(tmp.name)
    elif filename:
        if not re.match(r'^controlcenter-backup-[\d]{8}-[\d]{6}\.tar\.gz$', filename):
            from django.http import Http404
            raise Http404
        backup_dir = get_backup_dir()
        archive_path = backup_dir / filename
        if not archive_path.exists() or not archive_path.resolve().parent == backup_dir.resolve():
            from django.http import Http404
            raise Http404
    else:
        backups = _get_backup_list()
        return render(request, "dashboard/partials/_backup_list.html", {
            "backups": backups, "message": "No backup specified.", "msg_type": "error",
        })

    # Validate
    try:
        if not tarfile.is_tarfile(str(archive_path)):
            raise ValueError("Not a valid tar.gz archive")
        with tarfile.open(archive_path, 'r:*') as tar:
            members = tar.getnames()
            if 'db.sqlite3' not in members:
                raise ValueError("Archive missing db.sqlite3")
            if not any(m.startswith('media') for m in members):
                raise ValueError("Archive missing media/ directory")
    except Exception as e:
        if uploaded:
            archive_path.unlink(missing_ok=True)
        backups = _get_backup_list()
        return render(request, "dashboard/partials/_backup_list.html", {
            "backups": backups, "message": f"Invalid archive: {e}", "msg_type": "error",
        })

    # Restore
    try:
        media_root = Path(django_settings.MEDIA_ROOT)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with tarfile.open(archive_path, 'r:*') as tar:
                tar.extractall(path=tmp_path)

            # Replace database (WAL-safe)
            from dashboard.management.commands.backup import safe_restore_db
            src_db = tmp_path / 'db.sqlite3'
            safe_restore_db(src_db)

            # Replace media directory contents (clear then copy;
            # can't rmtree a Docker bind mount)
            src_media = tmp_path / 'media'
            if src_media.exists():
                if media_root.exists():
                    for item in media_root.iterdir():
                        if item.is_dir():
                            shutil.rmtree(item)
                        else:
                            item.unlink()
                else:
                    media_root.mkdir(parents=True)
                for item in src_media.iterdir():
                    dst = media_root / item.name
                    if item.is_dir():
                        shutil.copytree(str(item), str(dst))
                    else:
                        shutil.copy2(str(item), str(dst))

        # Run migrations
        call_command('migrate', verbosity=0)
        source_name = uploaded.name if uploaded else filename
        message = f"Restored from {source_name}. Restart the Docker container to refresh background tasks."
        msg_type = "success"
    except Exception as e:
        message = f"Restore failed: {e}"
        msg_type = "error"
    finally:
        if uploaded:
            archive_path.unlink(missing_ok=True)

    backups = _get_backup_list()
    return render(request, "dashboard/partials/_backup_list.html", {
        "backups": backups, "message": message, "msg_type": msg_type,
    })
