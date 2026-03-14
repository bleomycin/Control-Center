from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from dashboard.choices import get_choice_label, get_choices
from stakeholders.models import Stakeholder
from .forms import CaseLogForm, EvidenceForm, FirmEngagementForm, LegalChecklistForm, LegalCommunicationForm, LegalMatterForm
from .models import CaseLog, Evidence, FirmEngagement, LegalChecklistItem, LegalCommunication, LegalMatter


ACTIVITY_PAGE_SIZE = 20


def _activity_list_context(matter, request=None, page=1):
    """Build filtered, paginated unified activity list (comms + case logs)."""
    act_type = ""
    q = ""
    stakeholder_pk = ""
    direction = ""
    method = ""
    date_from = ""
    date_to = ""
    has_file = False
    follow_up = False

    if request:
        q = request.GET.get("act_q", "").strip()
        act_type = request.GET.get("act_type", "")
        stakeholder_pk = request.GET.get("act_stakeholder", "")
        direction = request.GET.get("act_direction", "")
        method = request.GET.get("act_method", "")
        date_from = request.GET.get("act_date_from", "")
        date_to = request.GET.get("act_date_to", "")
        has_file = bool(request.GET.get("act_has_file"))
        follow_up = bool(request.GET.get("act_follow_up"))
        page_param = request.GET.get("act_page")
        if page_param:
            try:
                page = int(page_param)
            except (ValueError, TypeError):
                page = 1

    limit = page * ACTIVITY_PAGE_SIZE

    # --- Communications queryset ---
    comm_qs = matter.communications.select_related("stakeholder").all()
    if act_type != "log":
        if q:
            comm_qs = comm_qs.filter(Q(subject__icontains=q) | Q(summary__icontains=q))
        if stakeholder_pk:
            comm_qs = comm_qs.filter(stakeholder_id=stakeholder_pk)
        if direction in ("outbound", "inbound"):
            comm_qs = comm_qs.filter(direction=direction)
        if method:
            comm_qs = comm_qs.filter(method=method)
        if date_from:
            comm_qs = comm_qs.filter(date__date__gte=date_from)
        if date_to:
            comm_qs = comm_qs.filter(date__date__lte=date_to)
        if has_file:
            comm_qs = comm_qs.exclude(file="")
        if follow_up:
            comm_qs = comm_qs.filter(follow_up_needed=True)
    else:
        comm_qs = comm_qs.none()

    # --- Case log queryset ---
    log_qs = matter.case_logs.select_related("stakeholder").all()
    if act_type != "comm":
        if q:
            log_qs = log_qs.filter(
                Q(text__icontains=q)
                | Q(source_name__icontains=q)
                | Q(stakeholder__name__icontains=q)
            )
        if stakeholder_pk:
            log_qs = log_qs.filter(stakeholder_id=stakeholder_pk)
        if date_from:
            log_qs = log_qs.filter(created_at__date__gte=date_from)
        if date_to:
            log_qs = log_qs.filter(created_at__date__lte=date_to)
    else:
        log_qs = log_qs.none()

    # Counts (from filtered querysets, before pagination)
    act_comm_count = comm_qs.count()
    act_log_count = log_qs.count()
    act_total_count = act_comm_count + act_log_count

    # Merge: fetch `limit` from each, wrap, sort, slice
    comm_items = [
        {"type": "comm", "sort_date": c.date, "obj": c}
        for c in comm_qs[:limit]
    ]
    log_items = [
        {"type": "log", "sort_date": l.created_at, "obj": l}
        for l in log_qs[:limit]
    ]
    merged = sorted(comm_items + log_items, key=lambda x: x["sort_date"], reverse=True)[:limit]

    return {
        "activity_list": merged,
        "act_total_count": act_total_count,
        "act_comm_count": act_comm_count,
        "act_log_count": act_log_count,
        "act_has_more": act_total_count > limit,
        "act_next_page": page + 1,
        "matter": matter,
        "today": timezone.localdate(),
    }


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
        statuses = [s for s in self.request.GET.getlist("status") if s]
        if statuses:
            qs = qs.filter(status__in=statuses)
        matter_type = self.request.GET.get("type")
        if matter_type:
            qs = qs.filter(matter_type=matter_type)
        date_from = self.request.GET.get("date_from")
        if date_from:
            qs = qs.filter(filing_date__gte=date_from)
        date_to = self.request.GET.get("date_to")
        if date_to:
            qs = qs.filter(filing_date__lte=date_to)
        hearing_date_from = self.request.GET.get("hearing_date_from")
        if hearing_date_from:
            qs = qs.filter(next_hearing_date__gte=hearing_date_from)
        hearing_date_to = self.request.GET.get("hearing_date_to")
        if hearing_date_to:
            qs = qs.filter(next_hearing_date__lte=hearing_date_to)
        ALLOWED_SORTS = {"title", "status", "matter_type", "filing_date", "next_hearing_date", "created_at"}
        sort = self.request.GET.get("sort", "")
        if sort in ALLOWED_SORTS:
            direction = "" if self.request.GET.get("dir") == "asc" else "-"
            qs = qs.order_by(f"{direction}{sort}")
        return qs

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["legal/partials/_legal_table.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search_query"] = self.request.GET.get("q", "")
        ctx["status_choices"] = LegalMatter.STATUS_CHOICES
        ctx["type_choices"] = get_choices("matter_type")
        ctx["selected_status"] = self.request.GET.get("status", "")
        ctx["selected_type"] = self.request.GET.get("type", "")
        ctx["date_from"] = self.request.GET.get("date_from", "")
        ctx["date_to"] = self.request.GET.get("date_to", "")
        ctx["hearing_date_from"] = self.request.GET.get("hearing_date_from", "")
        ctx["hearing_date_to"] = self.request.GET.get("hearing_date_to", "")
        ctx["selected_statuses"] = self.request.GET.getlist("status")
        ctx["current_sort"] = self.request.GET.get("sort", "")
        ctx["current_dir"] = self.request.GET.get("dir", "")
        return ctx


class LegalMatterCreateView(CreateView):
    model = LegalMatter
    form_class = LegalMatterForm
    template_name = "legal/legal_form.html"

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("property"):
            initial["related_properties"] = [self.request.GET["property"]]
        if self.request.GET.get("investment"):
            initial["related_investments"] = [self.request.GET["investment"]]
        if self.request.GET.get("loan"):
            initial["related_loans"] = [self.request.GET["loan"]]
        if self.request.GET.get("vehicle"):
            initial["related_vehicles"] = [self.request.GET["vehicle"]]
        if self.request.GET.get("aircraft"):
            initial["related_aircraft"] = [self.request.GET["aircraft"]]
        if self.request.GET.get("policy"):
            initial["related_policies"] = [self.request.GET["policy"]]
        if self.request.GET.get("lease"):
            initial["related_leases"] = [self.request.GET["lease"]]
        return initial

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
        ctx.update(_activity_list_context(obj))
        ctx["communication_form"] = LegalCommunicationForm()
        ctx["case_log_form"] = CaseLogForm()
        ctx["activity_stakeholders"] = Stakeholder.objects.filter(
            Q(legal_communications__legal_matter=obj) | Q(case_logs__legal_matter=obj)
        ).distinct().order_by("name")
        ctx["comm_method_choices"] = get_choices("contact_method")
        ctx["evidence_list"] = obj.evidence.all()
        ctx["evidence_form"] = EvidenceForm()
        checklist_items = obj.checklist_items.all()
        ctx["checklist_items"] = checklist_items
        ctx["checklist_form"] = LegalChecklistForm()
        ctx["checklist_count"] = checklist_items.count()
        ctx["checklist_done"] = checklist_items.filter(is_completed=True).count()
        ctx["tasks"] = obj.tasks.exclude(status="complete")[:5]
        ctx["notes"] = obj.notes.all()[:5]
        # Activity summary stats
        today = timezone.localdate()
        ctx["pending_followups"] = obj.communications.filter(
            follow_up_needed=True, follow_up_completed=False
        ).count()
        ctx["overdue_followups"] = obj.communications.filter(
            follow_up_needed=True, follow_up_completed=False,
            follow_up_date__lt=today,
        ).count()
        ctx["active_task_count"] = obj.tasks.exclude(status="complete").count()
        nearest_due = obj.tasks.exclude(status="complete").exclude(
            due_date__isnull=True
        ).order_by("due_date").values_list("due_date", flat=True).first()
        ctx["nearest_due_date"] = nearest_due
        thirty_days_ago = today - timezone.timedelta(days=30)
        ctx["recent_comm_count"] = obj.communications.filter(
            date__date__gte=thirty_days_ago
        ).count()
        ctx.update(_firm_engagement_context(obj))
        ctx["related_entities"] = _build_entity_list(obj)
        ctx["entity_documents"] = obj.documents.all()
        ctx["entity_email_links"] = obj.email_links.all()
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
    from config.export import export_csv as do_export
    qs = LegalMatter.objects.all()
    fields = [
        ("title", "Title"),
        ("case_number", "Case Number"),
        ("matter_type", "Type"),
        ("status", "Status"),
        ("jurisdiction", "Jurisdiction"),
        ("court", "Court"),
        ("filing_date", "Filing Date"),
        ("next_hearing_date", "Next Hearing"),
        ("settlement_amount", "Settlement Amount"),
        ("judgment_amount", "Judgment Amount"),
    ]
    return do_export(qs, fields, "legal_matters")


def export_pdf_detail(request, pk):
    from config.pdf_export import render_pdf
    m = get_object_or_404(LegalMatter, pk=pk)
    sections = [
        {"heading": "Case Information", "type": "info", "rows": [
            ("Case Number", m.case_number or "N/A"),
            ("Jurisdiction", m.jurisdiction or "N/A"),
            ("Court", m.court or "N/A"),
            ("Filing Date", m.filing_date.strftime("%b %d, %Y") if m.filing_date else "N/A"),
            ("Next Hearing", m.next_hearing_date.strftime("%b %d, %Y") if m.next_hearing_date else "N/A"),
            ("Settlement Amount", f"${m.settlement_amount:,.2f}" if m.settlement_amount else "N/A"),
            ("Judgment Amount", f"${m.judgment_amount:,.2f}" if m.judgment_amount else "N/A"),
        ]},
    ]
    if m.outcome:
        sections.append({"heading": "Outcome", "type": "text", "content": m.outcome})
    if m.description:
        sections.append({"heading": "Description", "type": "text", "content": m.description})
    attorneys = m.attorneys.all()
    if attorneys:
        sections.append({"heading": "Attorneys", "type": "table",
                         "headers": ["Name", "Organization", "Email", "Phone"],
                         "rows": [[a.name, a.organization or "-", a.email or "-", a.phone or "-"] for a in attorneys]})
    engagements = m.firm_engagements.select_related("firm", "referred_by__firm").all()
    if engagements:
        sections.append({"heading": "Counsel Search", "type": "table",
                         "headers": ["Firm", "Status", "Scope", "Contact Date", "Referred By"],
                         "rows": [
                             [e.firm.name if e.firm else "-",
                              e.get_status_display(),
                              e.scope or "-",
                              e.initial_contact_date.strftime("%b %d, %Y") if e.initial_contact_date else "-",
                              e.referred_by.firm.name if e.referred_by and e.referred_by.firm else "-"]
                             for e in engagements
                         ]})
    stakeholders = m.related_stakeholders.all()
    if stakeholders:
        sections.append({"heading": "Related Stakeholders", "type": "table",
                         "headers": ["Name", "Type", "Organization"],
                         "rows": [[s.name, get_choice_label("entity_type", s.entity_type), s.organization or "-"] for s in stakeholders]})
    comms = m.communications.select_related("stakeholder").all()
    if comms:
        sections.append({"heading": "Communications", "type": "table",
                         "headers": ["Date", "Direction", "Subject", "Method", "Contact", "Summary", "Follow-up", "Attachment"],
                         "rows": [[c.date.strftime("%b %d, %Y %I:%M %p"),
                                   c.get_direction_display(),
                                   c.subject or "-",
                                   get_choice_label("contact_method", c.method),
                                   c.stakeholder.name if c.stakeholder else "-",
                                   c.summary,
                                   c.follow_up_date.strftime("%b %d, %Y") if c.follow_up_date else "-",
                                   c.file.name.split("/")[-1] if c.file else "-"]
                                  for c in comms]})
    checklist = m.checklist_items.all()
    if checklist:
        sections.append({"heading": "Checklist", "type": "table",
                         "headers": ["Item", "Status"],
                         "rows": [[c.title, "Done" if c.is_completed else "Pending"] for c in checklist]})
    case_logs = m.case_logs.select_related("stakeholder").all()
    if case_logs:
        sections.append({"heading": "Case Log", "type": "table",
                         "headers": ["Date", "Source", "Entry"],
                         "rows": [[cl.created_at.strftime("%b %d, %Y %I:%M %p"),
                                   cl.display_source or "-",
                                   cl.text] for cl in case_logs]})
    evidence = m.evidence.all()
    if evidence:
        sections.append({"heading": "Evidence", "type": "table",
                         "headers": ["Title", "Type", "Date Obtained", "URL"],
                         "rows": [[e.title, e.evidence_type or "-",
                                   e.date_obtained.strftime("%b %d, %Y") if e.date_obtained else "-",
                                   e.url or "-"] for e in evidence]})
    tasks = m.tasks.exclude(status="complete")
    if tasks:
        sections.append({"heading": "Related Tasks", "type": "table",
                         "headers": ["Title", "Status", "Priority", "Due Date"],
                         "rows": [[t.title, t.get_status_display(), t.get_priority_display(),
                                   t.due_date.strftime("%b %d, %Y") if t.due_date else "-"] for t in tasks]})
    return render_pdf(request, f"legal-matter-{m.pk}", m.title,
                      f"{get_choice_label('matter_type', m.matter_type)} — {m.get_status_display()}", sections)


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


def evidence_edit(request, pk):
    ev = get_object_or_404(Evidence, pk=pk)
    matter = ev.legal_matter
    if request.method == "POST":
        form = EvidenceForm(request.POST, request.FILES, instance=ev)
        if form.is_valid():
            obj = form.save(commit=False)
            if request.POST.get("clear_file"):
                obj.file = ""
            obj.save()
            return render(request, "legal/partials/_evidence_list.html",
                          {"evidence_list": matter.evidence.all(), "matter": matter})
    else:
        form = EvidenceForm(instance=ev)
    return render(request, "legal/partials/_evidence_form.html",
                  {"form": form, "matter": matter, "editing": ev})


def evidence_delete(request, pk):
    ev = get_object_or_404(Evidence, pk=pk)
    matter = ev.legal_matter
    if request.method == "POST":
        ev.delete()
    return render(request, "legal/partials/_evidence_list.html",
                  {"evidence_list": matter.evidence.all(), "matter": matter})


def activity_list(request, pk):
    """HTMX endpoint: filtered, paginated unified activity list."""
    matter = get_object_or_404(LegalMatter, pk=pk)
    ctx = _activity_list_context(matter, request)
    return render(request, "legal/partials/_activity_list.html", ctx)


def communication_add(request, pk):
    matter = get_object_or_404(LegalMatter, pk=pk)
    if request.method == "POST":
        form = LegalCommunicationForm(request.POST, request.FILES)
        if form.is_valid():
            comm = form.save(commit=False)
            comm.legal_matter = matter
            comm.save()
            ctx = _activity_list_context(matter)
            return render(request, "legal/partials/_activity_list.html", ctx)
    else:
        form = LegalCommunicationForm()
    return render(request, "legal/partials/_communication_form.html",
                  {"form": form, "matter": matter})


def communication_edit(request, pk):
    comm = get_object_or_404(LegalCommunication, pk=pk)
    matter = comm.legal_matter
    if request.method == "POST":
        form = LegalCommunicationForm(request.POST, request.FILES, instance=comm)
        if form.is_valid():
            obj = form.save(commit=False)
            if request.POST.get("clear_file"):
                obj.file = ""
            obj.save()
            ctx = _activity_list_context(matter)
            return render(request, "legal/partials/_activity_list.html", ctx)
    else:
        form = LegalCommunicationForm(instance=comm)
    return render(request, "legal/partials/_communication_form.html",
                  {"form": form, "matter": matter, "editing": comm})


def communication_delete(request, pk):
    comm = get_object_or_404(LegalCommunication, pk=pk)
    matter = comm.legal_matter
    if request.method == "POST":
        comm.delete()
    ctx = _activity_list_context(matter)
    return render(request, "legal/partials/_activity_list.html", ctx)


@require_POST
def communication_toggle_followup(request, pk):
    """Toggle follow_up_completed on a single communication, return row partial."""
    comm = get_object_or_404(LegalCommunication.objects.select_related("stakeholder", "legal_matter"), pk=pk)
    if comm.follow_up_completed:
        comm.follow_up_completed = False
        comm.follow_up_completed_date = None
    else:
        comm.follow_up_completed = True
        comm.follow_up_completed_date = timezone.localdate()
    comm.save(update_fields=["follow_up_completed", "follow_up_completed_date"])
    return render(request, "legal/partials/_communication_row.html", {
        "comm": comm, "matter": comm.legal_matter, "today": timezone.localdate(),
    })


def bulk_delete(request):
    if request.method == "POST":
        pks = request.POST.getlist("selected")
        count = LegalMatter.objects.filter(pk__in=pks).count()
        if "confirm" not in request.POST:
            from django.urls import reverse
            return render(request, "partials/_bulk_confirm_delete.html", {
                "count": count, "selected_pks": pks,
                "action_url": reverse("legal:bulk_delete"),
            })
        LegalMatter.objects.filter(pk__in=pks).delete()
        messages.success(request, f"{count} legal matter(s) deleted.")
    return redirect("legal:list")


def bulk_export_csv(request):
    from config.export import export_csv as do_export
    pks = request.GET.getlist("selected")
    qs = LegalMatter.objects.filter(pk__in=pks) if pks else LegalMatter.objects.none()
    fields = [
        ("title", "Title"),
        ("case_number", "Case Number"),
        ("matter_type", "Type"),
        ("status", "Status"),
        ("jurisdiction", "Jurisdiction"),
        ("court", "Court"),
        ("filing_date", "Filing Date"),
        ("next_hearing_date", "Next Hearing"),
        ("settlement_amount", "Settlement Amount"),
        ("judgment_amount", "Judgment Amount"),
    ]
    return do_export(qs, fields, "legal_matters_selected")


# ---------------------------------------------------------------------------
# Firm Engagements (Counsel Search)
# ---------------------------------------------------------------------------


def _firm_engagement_context(matter):
    """Build context for the counsel search section."""
    engagements = matter.firm_engagements.select_related("firm", "referred_by__firm").all()

    engagement_data = []
    for eng in engagements:
        if eng.firm_id:
            comm_count = matter.communications.filter(stakeholder_id=eng.firm_id).count()
            log_count = matter.case_logs.filter(stakeholder_id=eng.firm_id).count()
            email_count = matter.email_links.filter(related_stakeholder_id=eng.firm_id).count()
        else:
            comm_count = log_count = email_count = 0
        engagement_data.append({
            "engagement": eng,
            "comm_count": comm_count,
            "log_count": log_count,
            "email_count": email_count,
            "activity_total": comm_count + log_count + email_count,
        })

    total = len(engagement_data)
    engaged_count = sum(1 for d in engagement_data if d["engagement"].status == "engaged")
    reviewing_count = sum(1 for d in engagement_data if d["engagement"].status == "in_review")
    declined_count = sum(1 for d in engagement_data if d["engagement"].status == "declined")

    return {
        "engagement_data": engagement_data,
        "engagement_total": total,
        "engagement_engaged": engaged_count,
        "engagement_reviewing": reviewing_count,
        "engagement_declined": declined_count,
        "matter": matter,
    }


def firm_engagement_add(request, pk):
    matter = get_object_or_404(LegalMatter, pk=pk)
    if request.method == "POST":
        form = FirmEngagementForm(request.POST, legal_matter=matter)
        if form.is_valid():
            eng = form.save(commit=False)
            eng.legal_matter = matter
            eng.save()
            return render(request, "legal/partials/_firm_engagement_list.html",
                          _firm_engagement_context(matter))
    else:
        initial = {"initial_contact_date": timezone.localdate()}
        referred_by_pk = request.GET.get("referred_by")
        if referred_by_pk:
            initial["referred_by"] = referred_by_pk
        form = FirmEngagementForm(initial=initial, legal_matter=matter)
    create_new_mode = request.POST.get("create_new") == "on" if request.method == "POST" else False
    return render(request, "legal/partials/_firm_engagement_form.html",
                  {"form": form, "matter": matter, "create_new_mode": create_new_mode})


def firm_engagement_edit(request, pk):
    eng = get_object_or_404(FirmEngagement, pk=pk)
    matter = eng.legal_matter
    if request.method == "POST":
        form = FirmEngagementForm(request.POST, instance=eng, legal_matter=matter)
        if form.is_valid():
            form.save()
            return render(request, "legal/partials/_firm_engagement_list.html",
                          _firm_engagement_context(matter))
    else:
        form = FirmEngagementForm(instance=eng, legal_matter=matter)
    return render(request, "legal/partials/_firm_engagement_form.html",
                  {"form": form, "matter": matter, "editing": eng})


def firm_engagement_delete(request, pk):
    eng = get_object_or_404(FirmEngagement, pk=pk)
    matter = eng.legal_matter
    if request.method == "POST":
        eng.delete()
    return render(request, "legal/partials/_firm_engagement_list.html",
                  _firm_engagement_context(matter))


@require_POST
def firm_engagement_promote(request, pk):
    eng = get_object_or_404(FirmEngagement.objects.select_related("firm", "legal_matter"), pk=pk)
    matter = eng.legal_matter
    if eng.firm:
        matter.attorneys.add(eng.firm)
        eng.status = "engaged"
        eng.decision_date = timezone.localdate()
        eng.save(update_fields=["status", "decision_date"])
        CaseLog.objects.create(
            legal_matter=matter,
            stakeholder=eng.firm,
            text=f"Promoted {eng.firm.name} to attorney. Scope: {eng.scope or 'General counsel'}",
        )
    return render(request, "legal/partials/_firm_engagement_list.html",
                  _firm_engagement_context(matter))


# ---------------------------------------------------------------------------
# Related Entity Link / Unlink (HTMX)
# ---------------------------------------------------------------------------

# Mapping of entity type key -> (m2m_field_name, model_path, label, extra_detail_field)
ENTITY_TYPE_MAP = {
    "attorney":    ("attorneys", "stakeholders.Stakeholder", "Attorney", "organization"),
    "stakeholder": ("related_stakeholders", "stakeholders.Stakeholder", "Stakeholder", "organization"),
    "property":    ("related_properties", "assets.RealEstate", "Property", None),
    "investment":  ("related_investments", "assets.Investment", "Investment", None),
    "loan":        ("related_loans", "assets.Loan", "Loan", None),
    "vehicle":     ("related_vehicles", "assets.Vehicle", "Vehicle", None),
    "aircraft":    ("related_aircraft", "assets.Aircraft", "Aircraft", None),
    "policy":      ("related_policies", "assets.InsurancePolicy", "Policy", None),
    "lease":       ("related_leases", "assets.Lease", "Lease", None),
}


def _build_entity_list(matter):
    """Build a flat list of all related entities for template rendering."""
    entities = []
    for type_key, (field_name, _model_path, label, detail_field) in ENTITY_TYPE_MAP.items():
        for obj in getattr(matter, field_name).all():
            entities.append({
                "type_key": type_key,
                "type_label": label,
                "pk": obj.pk,
                "name": str(obj),
                "url": obj.get_absolute_url(),
                "detail": getattr(obj, detail_field, "") if detail_field else "",
            })
    return entities


def _related_entities_response(request, matter):
    """Render the related entities list partial."""
    return render(request, "legal/partials/_related_entities_list.html", {
        "matter": matter,
        "entities": _build_entity_list(matter),
    })


def related_entity_link(request, pk):
    """GET = show link form, POST = add entity to M2M."""
    from django.apps import apps

    matter = get_object_or_404(LegalMatter, pk=pk)

    if request.method == "POST":
        entity_type = request.POST.get("entity_type", "")
        entity_pk = request.POST.get("entity_pk", "")
        if entity_type in ENTITY_TYPE_MAP and entity_pk:
            field_name, model_path, _label, _detail = ENTITY_TYPE_MAP[entity_type]
            Model = apps.get_model(model_path)
            try:
                obj = Model.objects.get(pk=entity_pk)
                getattr(matter, field_name).add(obj)
            except Model.DoesNotExist:
                pass
        return _related_entities_response(request, matter)

    # GET: show form
    type_choices = [(k, v[2]) for k, v in ENTITY_TYPE_MAP.items()]
    return render(request, "legal/partials/_related_entity_form.html", {
        "matter": matter,
        "type_choices": type_choices,
    })


@require_POST
def related_entity_unlink(request, pk):
    """Remove an entity from the matter's M2M field."""
    from django.apps import apps

    matter = get_object_or_404(LegalMatter, pk=pk)
    entity_type = request.GET.get("type", "")
    entity_pk = request.GET.get("entity_pk", "")
    if entity_type in ENTITY_TYPE_MAP and entity_pk:
        field_name, model_path, _label, _detail = ENTITY_TYPE_MAP[entity_type]
        Model = apps.get_model(model_path)
        try:
            obj = Model.objects.get(pk=entity_pk)
            getattr(matter, field_name).remove(obj)
        except Model.DoesNotExist:
            pass
    return _related_entities_response(request, matter)


# ---------------------------------------------------------------------------
# Checklists (exact copy of tasks subtask pattern)
# ---------------------------------------------------------------------------

def _checklist_context(matter):
    items = matter.checklist_items.all()
    return {
        "checklist_items": items,
        "matter": matter,
        "checklist_form": LegalChecklistForm(),
        "checklist_count": items.count(),
        "checklist_done": items.filter(is_completed=True).count(),
    }


def checklist_add(request, pk):
    matter = get_object_or_404(LegalMatter, pk=pk)
    if request.method == "POST":
        form = LegalChecklistForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.legal_matter = matter
            item.sort_order = matter.checklist_items.count()
            item.save()
    return render(request, "legal/partials/_checklist_list.html", _checklist_context(matter))


@require_POST
def checklist_toggle(request, pk):
    item = get_object_or_404(LegalChecklistItem, pk=pk)
    item.is_completed = not item.is_completed
    item.save()
    return render(request, "legal/partials/_checklist_list.html", _checklist_context(item.legal_matter))


def checklist_edit(request, pk):
    item = get_object_or_404(LegalChecklistItem, pk=pk)
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        if title:
            item.title = title
            item.save()
        return render(request, "legal/partials/_checklist_list.html", _checklist_context(item.legal_matter))
    if request.GET.get("cancel"):
        return render(request, "legal/partials/_checklist_list.html", _checklist_context(item.legal_matter))
    return render(request, "legal/partials/_checklist_edit_form.html", {"item": item})


@require_POST
def checklist_delete(request, pk):
    item = get_object_or_404(LegalChecklistItem, pk=pk)
    matter = item.legal_matter
    item.delete()
    return render(request, "legal/partials/_checklist_list.html", _checklist_context(matter))


# ---------------------------------------------------------------------------
# Case Log
# ---------------------------------------------------------------------------

def case_log_add(request, pk):
    matter = get_object_or_404(LegalMatter, pk=pk)
    if request.method == "POST":
        form = CaseLogForm(request.POST)
        if form.is_valid():
            log = form.save(commit=False)
            log.legal_matter = matter
            log.save()
            ctx = _activity_list_context(matter)
            return render(request, "legal/partials/_activity_list.html", ctx)
    else:
        form = CaseLogForm()
    return render(request, "legal/partials/_case_log_form.html",
                  {"form": form, "matter": matter})


def case_log_edit(request, pk):
    log = get_object_or_404(CaseLog, pk=pk)
    matter = log.legal_matter
    if request.method == "POST":
        form = CaseLogForm(request.POST, instance=log)
        if form.is_valid():
            form.save()
            ctx = _activity_list_context(matter)
            return render(request, "legal/partials/_activity_list.html", ctx)
    else:
        form = CaseLogForm(instance=log)
    return render(request, "legal/partials/_case_log_form.html",
                  {"form": form, "matter": matter, "editing": log})


@require_POST
def case_log_delete(request, pk):
    log = get_object_or_404(CaseLog, pk=pk)
    matter = log.legal_matter
    log.delete()
    ctx = _activity_list_context(matter)
    return render(request, "legal/partials/_activity_list.html", ctx)


def related_entity_options(request, pk):
    """HTMX: return <select> options for the chosen entity type."""
    from django.apps import apps

    matter = get_object_or_404(LegalMatter, pk=pk)
    entity_type = request.GET.get("entity_type", "")
    options = []
    if entity_type in ENTITY_TYPE_MAP:
        field_name, model_path, _label, _detail = ENTITY_TYPE_MAP[entity_type]
        Model = apps.get_model(model_path)
        # Exclude already-linked entities
        existing_pks = set(getattr(matter, field_name).values_list("pk", flat=True))
        for obj in Model.objects.order_by("name"):
            if obj.pk not in existing_pks:
                options.append((obj.pk, str(obj)))
    return render(request, "legal/partials/_related_entity_options.html", {
        "options": options,
    })
