import datetime

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from django.http import JsonResponse

from dashboard.choices import get_choices, get_choice_label
from .forms import DocumentForm, DocumentLinkForm, GoogleDriveSetupForm
from .models import Document, GoogleDriveFolderBookmark, GoogleDriveSettings


class GDriveContextMixin:
    """Inject Google Drive connection state into template context."""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from . import gdrive
        settings = GoogleDriveSettings.load()
        connected = gdrive.is_connected() and bool(settings.api_key)
        ctx["drive_connected"] = connected
        ctx["drive_api_key"] = settings.api_key if connected else ""
        ctx["drive_client_id"] = settings.client_id if connected else ""
        ctx["drive_project_number"] = settings.project_number if connected else ""
        ctx["picker_debug"] = settings.picker_debug if connected else False
        return ctx


class DocumentListView(ListView):
    model = Document
    template_name = "documents/document_list.html"
    context_object_name = "documents"
    paginate_by = 50

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "related_property", "related_investment", "related_loan",
            "related_lease", "related_policy", "related_vehicle",
            "related_aircraft", "related_stakeholder", "related_legal_matter",
        )

        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(description__icontains=q)
                | Q(gdrive_file_name__icontains=q)
            )

        category = self.request.GET.get("category", "").strip()
        if category:
            qs = qs.filter(category=category)

        entity_type = self.request.GET.get("entity_type", "").strip()
        if entity_type == "property":
            qs = qs.filter(related_property__isnull=False)
        elif entity_type == "investment":
            qs = qs.filter(related_investment__isnull=False)
        elif entity_type == "loan":
            qs = qs.filter(related_loan__isnull=False)
        elif entity_type == "lease":
            qs = qs.filter(related_lease__isnull=False)
        elif entity_type == "policy":
            qs = qs.filter(related_policy__isnull=False)
        elif entity_type == "vehicle":
            qs = qs.filter(related_vehicle__isnull=False)
        elif entity_type == "aircraft":
            qs = qs.filter(related_aircraft__isnull=False)
        elif entity_type == "stakeholder":
            qs = qs.filter(related_stakeholder__isnull=False)
        elif entity_type == "legal":
            qs = qs.filter(related_legal_matter__isnull=False)
        elif entity_type == "unlinked":
            qs = qs.filter(
                related_property__isnull=True,
                related_investment__isnull=True,
                related_loan__isnull=True,
                related_lease__isnull=True,
                related_policy__isnull=True,
                related_vehicle__isnull=True,
                related_aircraft__isnull=True,
                related_stakeholder__isnull=True,
                related_legal_matter__isnull=True,
            )

        has_expiration = self.request.GET.get("expiring", "").strip()
        if has_expiration == "soon":
            today = timezone.localdate()
            qs = qs.filter(
                expiration_date__isnull=False,
                expiration_date__lte=today + datetime.timedelta(days=90),
                expiration_date__gte=today,
            )
        elif has_expiration == "expired":
            qs = qs.filter(
                expiration_date__isnull=False,
                expiration_date__lt=timezone.localdate(),
            )

        date_from = self.request.GET.get("date_from")
        if date_from:
            qs = qs.filter(date__gte=date_from)
        date_to = self.request.GET.get("date_to")
        if date_to:
            qs = qs.filter(date__lte=date_to)

        ALLOWED_SORTS = {"title", "category", "date", "expiration_date", "created_at"}
        sort = self.request.GET.get("sort", "")
        if sort in ALLOWED_SORTS:
            direction = "" if self.request.GET.get("dir") == "asc" else "-"
            qs = qs.order_by(f"{direction}{sort}")

        return qs

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["documents/partials/_document_table.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search_query"] = self.request.GET.get("q", "")
        ctx["selected_category"] = self.request.GET.get("category", "")
        ctx["selected_entity_type"] = self.request.GET.get("entity_type", "")
        ctx["selected_expiring"] = self.request.GET.get("expiring", "")
        ctx["date_from"] = self.request.GET.get("date_from", "")
        ctx["date_to"] = self.request.GET.get("date_to", "")
        ctx["current_sort"] = self.request.GET.get("sort", "")
        ctx["current_dir"] = self.request.GET.get("dir", "")
        ctx["category_choices"] = get_choices("document_category")
        ctx["total_count"] = Document.objects.count()
        today = timezone.localdate()
        ctx["expiring_count"] = Document.objects.filter(
            expiration_date__isnull=False,
            expiration_date__lte=today + datetime.timedelta(days=90),
            expiration_date__gte=today,
        ).count()
        ctx["unlinked_count"] = Document.objects.filter(
            related_property__isnull=True,
            related_investment__isnull=True,
            related_loan__isnull=True,
            related_lease__isnull=True,
            related_policy__isnull=True,
            related_vehicle__isnull=True,
            related_aircraft__isnull=True,
            related_stakeholder__isnull=True,
            related_legal_matter__isnull=True,
        ).count()
        return ctx


class DocumentDetailView(DetailView):
    model = Document
    template_name = "documents/document_detail.html"
    context_object_name = "document"


class DocumentCreateView(GDriveContextMixin, CreateView):
    model = Document
    form_class = DocumentForm
    template_name = "documents/document_form.html"

    def get_initial(self):
        initial = super().get_initial()
        # Pre-populate entity FK from query params
        for param, field in [
            ("property", "related_property"),
            ("investment", "related_investment"),
            ("loan", "related_loan"),
            ("lease", "related_lease"),
            ("policy", "related_policy"),
            ("vehicle", "related_vehicle"),
            ("aircraft", "related_aircraft"),
            ("stakeholder", "related_stakeholder"),
            ("legal_matter", "related_legal_matter"),
        ]:
            val = self.request.GET.get(param)
            if val:
                initial[field] = val
        return initial

    def get_success_url(self):
        return self.object.get_absolute_url()


class DocumentUpdateView(GDriveContextMixin, UpdateView):
    model = Document
    form_class = DocumentForm
    template_name = "documents/document_form.html"

    def get_success_url(self):
        return self.object.get_absolute_url()


class DocumentDeleteView(DeleteView):
    model = Document
    template_name = "partials/_confirm_delete.html"
    success_url = reverse_lazy("documents:list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["cancel_url"] = self.object.get_absolute_url()
        return ctx


def export_csv(request):
    """Export documents list as CSV."""
    from config.export import export_csv as do_export
    qs = Document.objects.all()
    fields = [
        ("title", "Title"),
        ("category", "Category"),
        ("date", "Date"),
        ("expiration_date", "Expiration Date"),
        ("gdrive_url", "Google Drive URL"),
        ("gdrive_file_name", "Drive Filename"),
        ("description", "Description"),
    ]
    return do_export(qs, fields, "documents")


def export_pdf_detail(request, pk):
    """Export single document record as PDF."""
    from config.pdf_export import render_pdf
    doc = get_object_or_404(Document, pk=pk)
    sections = [
        {
            "type": "info",
            "items": [
                ("Title", doc.title),
                ("Category", get_choice_label("document_category", doc.category) if doc.category else ""),
                ("Date", str(doc.date) if doc.date else ""),
                ("Expiration Date", str(doc.expiration_date) if doc.expiration_date else ""),
                ("Google Drive URL", doc.gdrive_url or ""),
                ("Drive Filename", doc.gdrive_file_name or ""),
                ("Description", doc.description or ""),
            ],
        },
    ]
    entities = doc.linked_entities
    if entities:
        sections.append({
            "type": "info",
            "title": "Linked Entities",
            "items": [(label, str(obj)) for label, obj in entities],
        })
    if doc.notes_text:
        sections.append({"type": "text", "title": "Notes", "text": doc.notes_text})
    return render_pdf(request, f"document_{doc.pk}.pdf", "Document Record",
                      subtitle=doc.title, sections=sections)


@require_POST
def bulk_delete(request):
    pks = request.POST.getlist("selected")
    if pks:
        deleted = Document.objects.filter(pk__in=pks).delete()[0]
        messages.success(request, f"Deleted {deleted} document(s).")
    return redirect("documents:list")


def bulk_export_csv(request):
    from config.export import export_csv as do_export
    pks = request.POST.getlist("selected")
    qs = Document.objects.filter(pk__in=pks) if pks else Document.objects.none()
    fields = [
        ("title", "Title"),
        ("category", "Category"),
        ("date", "Date"),
        ("expiration_date", "Expiration Date"),
        ("gdrive_url", "Google Drive URL"),
        ("gdrive_file_name", "Drive Filename"),
        ("description", "Description"),
    ]
    return do_export(qs, fields, "documents_selected")


# ---- Entity document link/unlink ----

ENTITY_CONFIG = {
    "property": ("assets.RealEstate", "related_property"),
    "investment": ("assets.Investment", "related_investment"),
    "loan": ("assets.Loan", "related_loan"),
    "lease": ("assets.Lease", "related_lease"),
    "policy": ("assets.InsurancePolicy", "related_policy"),
    "vehicle": ("assets.Vehicle", "related_vehicle"),
    "aircraft": ("assets.Aircraft", "related_aircraft"),
    "stakeholder": ("stakeholders.Stakeholder", "related_stakeholder"),
    "legal_matter": ("legal.LegalMatter", "related_legal_matter"),
}


def _doc_list_ctx(entity, fk_field, unlink_url_name, entity_pk):
    return {
        "documents": Document.objects.filter(**{fk_field: entity}),
        "unlink_url_name": unlink_url_name,
        "entity_pk": entity_pk,
    }


def _document_link(request, entity_type, pk):
    from django.apps import apps
    app_model, fk_field = ENTITY_CONFIG[entity_type]
    Model = apps.get_model(app_model)
    entity = get_object_or_404(Model, pk=pk)
    link_url_name = f"documents:{entity_type}_document_link"
    unlink_url_name = f"documents:{entity_type}_document_unlink"

    if request.method == "POST":
        form = DocumentLinkForm(request.POST)
        if form.is_valid():
            doc = form.cleaned_data["document"]
            setattr(doc, fk_field, entity)
            doc.save()
            return render(request, "documents/partials/_document_list_section.html",
                          _doc_list_ctx(entity, fk_field, unlink_url_name, pk))
    else:
        form = DocumentLinkForm()
    return render(request, "documents/partials/_document_link_form.html", {
        "form": form,
        "link_url": reverse(link_url_name, args=[pk]),
    })


def _document_unlink(request, entity_type, pk, doc_pk):
    from django.apps import apps
    app_model, fk_field = ENTITY_CONFIG[entity_type]
    Model = apps.get_model(app_model)
    entity = get_object_or_404(Model, pk=pk)
    doc = get_object_or_404(Document, pk=doc_pk)
    unlink_url_name = f"documents:{entity_type}_document_unlink"

    if request.method == "POST":
        setattr(doc, fk_field, None)
        doc.save()
    return render(request, "documents/partials/_document_list_section.html",
                  _doc_list_ctx(entity, fk_field, unlink_url_name, pk))


# Thin wrappers — one pair per entity type

def property_document_link(request, pk):
    return _document_link(request, "property", pk)


def property_document_unlink(request, pk, doc_pk):
    return _document_unlink(request, "property", pk, doc_pk)


def investment_document_link(request, pk):
    return _document_link(request, "investment", pk)


def investment_document_unlink(request, pk, doc_pk):
    return _document_unlink(request, "investment", pk, doc_pk)


def loan_document_link(request, pk):
    return _document_link(request, "loan", pk)


def loan_document_unlink(request, pk, doc_pk):
    return _document_unlink(request, "loan", pk, doc_pk)


def lease_document_link(request, pk):
    return _document_link(request, "lease", pk)


def lease_document_unlink(request, pk, doc_pk):
    return _document_unlink(request, "lease", pk, doc_pk)


def policy_document_link(request, pk):
    return _document_link(request, "policy", pk)


def policy_document_unlink(request, pk, doc_pk):
    return _document_unlink(request, "policy", pk, doc_pk)


def vehicle_document_link(request, pk):
    return _document_link(request, "vehicle", pk)


def vehicle_document_unlink(request, pk, doc_pk):
    return _document_unlink(request, "vehicle", pk, doc_pk)


def aircraft_document_link(request, pk):
    return _document_link(request, "aircraft", pk)


def aircraft_document_unlink(request, pk, doc_pk):
    return _document_unlink(request, "aircraft", pk, doc_pk)


def stakeholder_document_link(request, pk):
    return _document_link(request, "stakeholder", pk)


def stakeholder_document_unlink(request, pk, doc_pk):
    return _document_unlink(request, "stakeholder", pk, doc_pk)


def legal_matter_document_link(request, pk):
    return _document_link(request, "legal_matter", pk)


def legal_matter_document_unlink(request, pk, doc_pk):
    return _document_unlink(request, "legal_matter", pk, doc_pk)


# ---- Bulk create + link from Google Drive Picker (multi-select) ----

@require_POST
def bulk_create_and_link(request, entity_type, pk):
    """Create one Document per picked Drive file and link all to the entity.

    POST body (JSON): {"files": [{"id": "...", "name": "...", "mimeType": "...", "url": "..."}, ...]}
    Returns the rendered _document_list_section.html partial (HTMX swap target).
    Dedupes against existing Documents already linked to this entity by gdrive_file_id.
    """
    import json
    from django.apps import apps

    if entity_type not in ENTITY_CONFIG:
        return JsonResponse({"error": "Unknown entity_type"}, status=400)

    app_model, fk_field = ENTITY_CONFIG[entity_type]
    Model = apps.get_model(app_model)
    entity = get_object_or_404(Model, pk=pk)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    files = payload.get("files") or []
    if not isinstance(files, list):
        return JsonResponse({"error": "files must be a list"}, status=400)

    existing_ids = set(
        Document.objects
        .filter(**{fk_field: entity})
        .exclude(gdrive_file_id="")
        .values_list("gdrive_file_id", flat=True)
    )

    created = 0
    for f in files:
        if not isinstance(f, dict):
            continue
        file_id = (f.get("id") or "").strip()
        if not file_id or file_id in existing_ids:
            continue
        name = (f.get("name") or "").strip()
        title = name.rsplit(".", 1)[0] if "." in name else name
        url = (f.get("url") or "").strip()
        if not url and file_id:
            url = f"https://drive.google.com/file/d/{file_id}/view"
        Document.objects.create(
            title=title or "Untitled",
            gdrive_file_id=file_id,
            gdrive_url=url,
            gdrive_file_name=name,
            gdrive_mime_type=(f.get("mimeType") or "").strip(),
            **{fk_field: entity},
        )
        existing_ids.add(file_id)
        created += 1

    unlink_url_name = f"documents:{entity_type}_document_unlink"
    return render(
        request,
        "documents/partials/_document_list_section.html",
        _doc_list_ctx(entity, fk_field, unlink_url_name, pk),
    )


# ---- Google Drive settings & OAuth2 ----

def gdrive_settings(request):
    """Display and update Google Drive OAuth2 credentials."""
    instance = GoogleDriveSettings.load()

    if request.method == "POST":
        form = GoogleDriveSetupForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, "Google Drive credentials saved.")
            return redirect("documents:gdrive_settings")
    else:
        form = GoogleDriveSetupForm(instance=instance)

    # Connection status
    connected = instance.is_connected and bool(instance.refresh_token)
    connected_email = instance.connected_email if connected else ""

    from . import gdrive
    gmail_available = connected and gdrive.has_gmail_scope()

    return render(request, "documents/gdrive_settings.html", {
        "form": form,
        "settings_obj": instance,
        "connected": connected,
        "connected_email": connected_email,
        "gmail_available": gmail_available,
    })


def gdrive_authorize(request):
    """Redirect user to Google's OAuth2 consent screen."""
    from . import gdrive

    if not gdrive.is_configured():
        messages.error(request, "Please save your Client ID and Client Secret first.")
        return redirect("documents:gdrive_settings")

    callback_url = request.build_absolute_uri(reverse("documents:gdrive_callback"))
    try:
        auth_url, state, code_verifier = gdrive.get_authorization_url(callback_url)
    except Exception as exc:
        messages.error(request, f"Failed to start authorization: {exc}")
        return redirect("documents:gdrive_settings")

    # Store state + PKCE code_verifier in session
    request.session["gdrive_oauth_state"] = state
    request.session["gdrive_code_verifier"] = code_verifier or ""
    return redirect(auth_url)


def gdrive_callback(request):
    """Handle the OAuth2 callback from Google."""
    from . import gdrive

    error = request.GET.get("error")
    if error:
        messages.error(request, f"Google authorization failed: {error}")
        return redirect("documents:gdrive_settings")

    code = request.GET.get("code")
    if not code:
        messages.error(request, "No authorization code received from Google.")
        return redirect("documents:gdrive_settings")

    callback_url = request.build_absolute_uri(reverse("documents:gdrive_callback"))
    code_verifier = request.session.pop("gdrive_code_verifier", None)
    try:
        email = gdrive.exchange_code(code, callback_url, code_verifier=code_verifier)
        messages.success(request, f"Connected to Google Drive as {email}")
    except Exception as exc:
        messages.error(request, f"Failed to complete authorization: {exc}")

    return redirect("documents:gdrive_settings")


@require_POST
def gdrive_disconnect(request):
    """Revoke tokens and disconnect Google Drive."""
    from . import gdrive
    gdrive.revoke_credentials()
    messages.success(request, "Google Drive disconnected.")
    return redirect("documents:gdrive_settings")


def gdrive_verify(request):
    """Test the current Google Drive connection."""
    from . import gdrive
    success, detail = gdrive.verify_connection()
    if success:
        messages.success(request, f"Connection verified — connected as {detail}")
    else:
        messages.error(request, f"Connection check failed: {detail}")
    return redirect("documents:gdrive_settings")


def picker_token(request):
    """Return a fresh access token for the Google Picker widget (JSON)."""
    from . import gdrive
    if not gdrive.is_connected():
        return JsonResponse({"error": "Not connected"}, status=403)
    creds = gdrive.get_credentials()
    if not creds or not creds.token:
        return JsonResponse({"error": "Failed to get access token"}, status=500)
    # Force refresh to guarantee a fresh token for the Picker
    try:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        settings = GoogleDriveSettings.load()
        settings.access_token = creds.token
        if creds.expiry:
            settings.token_expiry = creds.expiry
        settings.save()
    except Exception:
        # If refresh fails, return whatever token we have
        settings = GoogleDriveSettings.load()
    return JsonResponse({
        "access_token": creds.token,
        "scopes": list(creds.scopes) if creds.scopes else [],
        "expired": creds.expired if hasattr(creds, 'expired') else None,
        "expiry": str(creds.expiry) if creds.expiry else None,
        "project_number": settings.project_number,
        "client_id_prefix": settings.client_id.split("-")[0] if settings.client_id else "",
    })


def gdrive_search(request):
    """Return Drive file search results as JSON for the custom file browser."""
    from . import gdrive
    if not gdrive.is_connected():
        return JsonResponse({"error": "Not connected"}, status=403)
    query = request.GET.get("q", "").strip()
    files = gdrive.search_files(query=query, page_size=20)
    if files is None:
        return JsonResponse({"error": "Failed to search Drive"}, status=500)
    return JsonResponse({"files": files})


def gdrive_folder_contents(request):
    """Return the contents of a Google Drive folder as JSON."""
    from . import gdrive
    if not gdrive.is_connected():
        return JsonResponse({"error": "Not connected"}, status=403)
    folder_id = request.GET.get("folder_id", "")
    if not folder_id:
        return JsonResponse({"error": "Missing folder_id"}, status=400)
    files = gdrive.list_folder_contents(folder_id)
    if files is None:
        return JsonResponse({"error": "Failed to list folder"}, status=500)

    folder_meta = None
    if folder_id == "root":
        folder_meta = {"id": "root", "name": "My Drive", "parents": []}
    else:
        meta = gdrive.get_folder_metadata(folder_id)
        if meta:
            folder_meta = {
                "id": meta.get("id"),
                "name": meta.get("name") or "(unnamed)",
                "parents": meta.get("parents") or [],
            }
    return JsonResponse({"files": files, "folder": folder_meta})


def gdrive_resolve_folder_path(request):
    """Return the breadcrumb path for a folder as JSON: [{id, name}, …] root → target."""
    from . import gdrive
    if not gdrive.is_connected():
        return JsonResponse({"error": "Not connected"}, status=403)
    folder_id = request.GET.get("folder_id", "")
    if not folder_id:
        return JsonResponse({"error": "Missing folder_id"}, status=400)
    chain = gdrive.resolve_folder_path(folder_id)
    if chain is None:
        return JsonResponse({"error": "Folder not found"}, status=404)
    return JsonResponse({"path": chain})


# ---- Folder Bookmarks ----

def _bookmark_to_dict(bm):
    return {
        "id": bm.pk,
        "label": bm.label,
        "folder_id": bm.folder_id,
        "sort_order": bm.sort_order,
    }


def gdrive_bookmarks_list(request):
    """List all folder bookmarks as JSON, ordered by sort_order then created_at."""
    qs = GoogleDriveFolderBookmark.objects.all()
    return JsonResponse({"bookmarks": [_bookmark_to_dict(b) for b in qs]})


@require_POST
def gdrive_bookmark_create(request):
    """Create a folder bookmark from POST {label, folder_id}."""
    label = (request.POST.get("label") or "").strip()
    folder_id = (request.POST.get("folder_id") or "").strip()
    if not label:
        return JsonResponse({"error": "Label is required"}, status=400)
    if not folder_id:
        return JsonResponse({"error": "folder_id is required"}, status=400)
    bm = GoogleDriveFolderBookmark.objects.create(
        label=label[:100],
        folder_id=folder_id[:255],
    )
    return JsonResponse({"bookmark": _bookmark_to_dict(bm)}, status=201)


@require_POST
def gdrive_bookmark_rename(request, pk):
    """Rename a folder bookmark from POST {label}."""
    bm = get_object_or_404(GoogleDriveFolderBookmark, pk=pk)
    label = (request.POST.get("label") or "").strip()
    if not label:
        return JsonResponse({"error": "Label is required"}, status=400)
    bm.label = label[:100]
    bm.save()
    return JsonResponse({"bookmark": _bookmark_to_dict(bm)})


@require_POST
def gdrive_bookmark_delete(request, pk):
    """Delete a folder bookmark."""
    bm = get_object_or_404(GoogleDriveFolderBookmark, pk=pk)
    bm.delete()
    return JsonResponse({"ok": True})
