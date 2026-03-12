from django.shortcuts import get_object_or_404, render
from . import gmail
from .models import EmailLink


# ---- Entity email link/unlink ----

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


def _parse_email_date(date_str):
    """Parse an RFC 2822 date (from Gmail) into a datetime, or None."""
    if not date_str:
        return None
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(date_str)
    except (ValueError, TypeError):
        return None


def _email_list_ctx(entity, fk_field, unlink_url_name, entity_pk):
    return {
        "email_links": EmailLink.objects.filter(**{fk_field: entity}),
        "unlink_url_name": unlink_url_name,
        "entity_pk": entity_pk,
        "gmail_available": gmail.is_available(),
    }


def _email_link(request, entity_type, pk):
    """Handle POST to link a Gmail message to an entity."""
    from django.apps import apps
    app_model, fk_field = ENTITY_CONFIG[entity_type]
    Model = apps.get_model(app_model)
    entity = get_object_or_404(Model, pk=pk)
    unlink_url_name = f"email_links:{entity_type}_email_unlink"

    if request.method == "POST":
        message_id = request.POST.get("message_id", "").strip()
        if message_id:
            email_link, _created = EmailLink.objects.get_or_create(
                message_id=message_id,
                defaults={
                    "subject": request.POST.get("subject", ""),
                    "from_name": request.POST.get("from_name", ""),
                    "from_email": request.POST.get("from_email", ""),
                    "date": _parse_email_date(request.POST.get("date", "")),
                    "provider": "gmail",
                },
            )
            setattr(email_link, fk_field, entity)
            email_link.save()
            return render(request, "email_links/partials/_email_list_section.html",
                          _email_list_ctx(entity, fk_field, unlink_url_name, pk))

    # GET: show search/link form
    link_url_name = f"email_links:{entity_type}_email_link"
    from django.urls import reverse
    gmail_available = gmail.is_available()
    return render(request, "email_links/partials/_email_link_form.html", {
        "link_url": reverse(link_url_name, args=[pk]),
        "gmail_available": gmail_available,
        "labels": gmail.get_labels() if gmail_available else [],
    })


def _email_unlink(request, entity_type, pk, email_pk):
    from django.apps import apps
    app_model, fk_field = ENTITY_CONFIG[entity_type]
    Model = apps.get_model(app_model)
    entity = get_object_or_404(Model, pk=pk)
    email_link = get_object_or_404(EmailLink, pk=email_pk)
    unlink_url_name = f"email_links:{entity_type}_email_unlink"

    if request.method == "POST":
        setattr(email_link, fk_field, None)
        email_link.save()
    return render(request, "email_links/partials/_email_list_section.html",
                  _email_list_ctx(entity, fk_field, unlink_url_name, pk))


# Thin wrappers — one pair per entity type

def property_email_link(request, pk):
    return _email_link(request, "property", pk)


def property_email_unlink(request, pk, email_pk):
    return _email_unlink(request, "property", pk, email_pk)


def investment_email_link(request, pk):
    return _email_link(request, "investment", pk)


def investment_email_unlink(request, pk, email_pk):
    return _email_unlink(request, "investment", pk, email_pk)


def loan_email_link(request, pk):
    return _email_link(request, "loan", pk)


def loan_email_unlink(request, pk, email_pk):
    return _email_unlink(request, "loan", pk, email_pk)


def lease_email_link(request, pk):
    return _email_link(request, "lease", pk)


def lease_email_unlink(request, pk, email_pk):
    return _email_unlink(request, "lease", pk, email_pk)


def policy_email_link(request, pk):
    return _email_link(request, "policy", pk)


def policy_email_unlink(request, pk, email_pk):
    return _email_unlink(request, "policy", pk, email_pk)


def vehicle_email_link(request, pk):
    return _email_link(request, "vehicle", pk)


def vehicle_email_unlink(request, pk, email_pk):
    return _email_unlink(request, "vehicle", pk, email_pk)


def aircraft_email_link(request, pk):
    return _email_link(request, "aircraft", pk)


def aircraft_email_unlink(request, pk, email_pk):
    return _email_unlink(request, "aircraft", pk, email_pk)


def stakeholder_email_link(request, pk):
    return _email_link(request, "stakeholder", pk)


def stakeholder_email_unlink(request, pk, email_pk):
    return _email_unlink(request, "stakeholder", pk, email_pk)


def legal_matter_email_link(request, pk):
    return _email_link(request, "legal_matter", pk)


def legal_matter_email_unlink(request, pk, email_pk):
    return _email_unlink(request, "legal_matter", pk, email_pk)


# ---- Gmail search API ----

def gmail_search_html(request):
    """Return Gmail search/browse results as HTML partial for the HTMX picker."""
    link_url = request.GET.get("link_url", "")
    if not gmail.is_available():
        return render(request, "email_links/partials/_email_search_results.html", {
            "error": "Gmail is not connected. Please reconnect Google Drive with Gmail permissions.",
        })
    query = request.GET.get("q", "").strip()
    page_token = request.GET.get("page_token", "").strip() or None
    label = request.GET.get("label", "").strip() or None
    label_ids = [label] if label else None

    data = gmail.search_threads(
        query=query, max_results=15, page_token=page_token, label_ids=label_ids,
    )
    if data is None:
        return render(request, "email_links/partials/_email_search_results.html", {
            "error": "Failed to search Gmail. Please try again.",
        })
    return render(request, "email_links/partials/_email_search_results.html", {
        "results": data["threads"],
        "next_page_token": data["next_page_token"],
        "link_url": link_url,
        "browsing": not query and not label,
        "query": query,
        "label": label or "",
        "is_page_load": bool(page_token),
    })


# ---- Email body expansion ----

def email_body(request, pk):
    """Fetch and return the thread messages for a linked email."""
    email_link = get_object_or_404(EmailLink, pk=pk)
    thread_messages = gmail.get_thread_messages(email_link.message_id)
    return render(request, "email_links/partials/_email_body.html", {
        "thread_messages": thread_messages,
        "email_link": email_link,
    })
