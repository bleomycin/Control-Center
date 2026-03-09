# Google Drive Integration — Implementation Plan

## Overview

**Goal:** Integrate Google Drive as the document storage layer for Control Center. Google Drive handles file storage, sharing, collaboration, and mobile access. Control Center handles metadata, entity linking, expiration alerts, and cross-entity search.

**Approach:** Phase B — Google Picker widget + Drive API for metadata retrieval. Google Workspace account.

**Baseline release:** v0.22.0-alpha (committed before implementation began)

**Rollback:** If anything goes sideways, reset to v0.22.0-alpha.

---

## Milestone Tracker

| # | Milestone | Status | Files Changed | Notes |
|---|-----------|--------|---------------|-------|
| 1 | Documents app foundation (no Google) | Not started | ~15 new, ~6 modified | New app + CRUD + sidebar + sample data |
| 2 | Google Drive Settings + OAuth2 | Not started | ~8 | Settings page + OAuth flow + gdrive.py |
| 3 | Google Picker integration | Not started | ~6 | Picker JS + template partial + token endpoint |
| 4 | Existing model migration | Not started | ~20 | Add gdrive_url to Evidence, Communication, Attachment, TestResult |
| 5 | Entity detail page integration | Not started | ~20 | Documents section on 9 detail pages |
| 6 | Expiration alerts + calendar | Not started | ~5 | Calendar events + dashboard alerts |

---

## Design Principles

1. **Drive is additive, never a dependency.** If Google Drive is not connected, misconfigured, or down, every existing feature works exactly as today.
2. **Single abstraction layer.** Only `documents/gdrive.py` imports `google-api-python-client`. If Google changes their API, fix ONE file.
3. **Follows every existing pattern.** Singleton settings (`load()`), TailwindFormMixin, HTMX partials, DB-backed choices, nullable FKs, link/unlink inline pattern.
4. **Fallback always available.** Manual URL paste works alongside Picker. Local FileField remains. Neither requires the other.

---

## Milestone 1: Documents App Foundation (No Google)

### Scope
New `documents` Django app with full CRUD, entity linking, filtering, exports. No Google API dependency — gdrive fields are just empty CharFields. Users can create document records with manually pasted Drive URLs immediately.

### Checklist

**App structure:**
- [ ] Create `documents/` app directory with __init__.py, apps.py, admin.py
- [ ] `documents/models.py` — Document model + GoogleDriveSettings singleton
- [ ] `documents/forms.py` — DocumentForm + DocumentFilterForm
- [ ] `documents/views.py` — List, Detail, Create, Edit, Delete, CSV export, PDF export
- [ ] `documents/urls.py` — URL patterns (app_name = "documents")
- [ ] `documents/tests.py` — Unit tests

**Model — Document:**
- [ ] title (CharField 255)
- [ ] category (CharField 100, blank) — DB-backed via `document_category` ChoiceOption
- [ ] description (TextField, blank)
- [ ] date (DateField, null/blank)
- [ ] expiration_date (DateField, null/blank)
- [ ] gdrive_file_id (CharField 255, blank, db_index)
- [ ] gdrive_url (URLField 500, blank)
- [ ] gdrive_mime_type (CharField 100, blank)
- [ ] gdrive_file_name (CharField 255, blank)
- [ ] file (FileField upload_to='documents/', blank)
- [ ] 9 nullable FKs: related_property, related_investment, related_loan, related_lease, related_policy, related_vehicle, related_aircraft, related_stakeholder, related_legal_matter
- [ ] notes_text (TextField, blank)
- [ ] created_at, updated_at

**Model — GoogleDriveSettings:**
- [ ] Singleton (pk=1) with load() classmethod
- [ ] is_connected, client_id, client_secret, api_key, refresh_token, access_token, token_expiry, connected_email
- [ ] Shell only for Milestone 1 — no Google logic yet

**Registration:**
- [ ] Add `documents` to INSTALLED_APPS in config/settings.py
- [ ] Add URL include in config/urls.py
- [ ] Add `document_category` to ChoiceOption CATEGORY_CHOICES
- [ ] Data migration for default document categories

**Templates:**
- [ ] `documents/document_list.html` — search, category filter, entity filter, date range, sort
- [ ] `documents/document_detail.html` — metadata, Drive link button, entity links, notes
- [ ] `documents/document_form.html` — create/edit with explicit field layout
- [ ] `documents/partials/_document_table.html` — HTMX table partial for list page

**Sidebar:**
- [ ] Add Documents link to `templates/partials/_sidebar.html`

**Exports:**
- [ ] CSV export (list page)
- [ ] PDF export (detail page)

**Sample data:**
- [ ] Update `load_sample_data.py` — add document section with ~8 sample documents
- [ ] Update `clean_sample_data.py` — add document cleanup
- [ ] Update SAMPLE_NAMES dict

**Tests:**
- [ ] Model tests: creation, str, FKs, defaults
- [ ] View tests: list, detail, create, edit, delete (200/302/404)
- [ ] Form tests: validation, required fields, category choices
- [ ] Filter tests: search, category, date range, sort
- [ ] Export tests: CSV, PDF
- [ ] Empty state tests

**Verification:**
- [ ] `make test-unit` — all pass
- [ ] `make test-e2e` — all pass (including new document e2e tests)
- [ ] Docker rebuild + manual Playwright verification
- [ ] Desktop screenshot (1280x800)
- [ ] Mobile screenshot (375x812)
- [ ] Tailwind build if new classes
- [ ] Verify HTMX swaps don't break surrounding elements

### Completion Log
*(Updated when milestone is complete)*

---

## Milestone 2: Google Drive Settings + OAuth2

### Scope
Settings page for Google Drive credentials. OAuth2 authorization flow with Google Workspace. Token storage and refresh. Connection health check.

### Checklist
- [ ] Add `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib` to requirements.txt
- [ ] `documents/gdrive.py` — abstraction layer: get_credentials(), get_service(), get_file_metadata(), verify_connection(), get_picker_access_token(), revoke_credentials()
- [ ] Settings page: `documents/templates/documents/gdrive_settings.html`
- [ ] GoogleDriveSetupForm: client_id, client_secret, api_key fields
- [ ] Step-by-step guidance text in settings UI
- [ ] "Connect Google Drive" → OAuth2 authorization code flow → callback → store tokens
- [ ] "Disconnect" button → revoke + clear
- [ ] Connection status indicator (connected as email / not connected)
- [ ] Token refresh logic (automatic before API calls)
- [ ] Settings hub card linking to Google Drive settings
- [ ] Unit tests with mocked Google responses
- [ ] Manual OAuth flow test with real Google Workspace account

### Completion Log
*(Updated when milestone is complete)*

---

## Milestone 3: Google Picker Integration

### Scope
Google Picker JavaScript widget embedded in document forms. Reusable template include. Fallback to manual URL entry.

### Checklist
- [ ] `documents/static/js/gdrive-picker.js` — Picker wrapper (load libs, handle auth, create picker, populate form fields, error handling)
- [ ] `documents/templates/documents/partials/_gdrive_picker.html` — reusable include with Picker button + hidden fields + manual URL fallback
- [ ] Picker token endpoint: `GET /documents/api/picker-token/` → returns fresh access token JSON
- [ ] Integrate into Document create/edit forms
- [ ] Auto-populate title from filename when Picker selects a file
- [ ] Conditional rendering: Picker button only shows if Drive is connected
- [ ] Tests for token endpoint, form rendering with/without Drive connection
- [ ] Manual testing: pick real files from Google Drive

### Completion Log
*(Updated when milestone is complete)*

---

## Milestone 4: Existing Model Migration

### Scope
Add `gdrive_url` field to the 4 existing models that have FileField. Update forms and templates to show Picker widget alongside file upload.

### Checklist
- [ ] Add `gdrive_url` (URLField, blank) to legal.Evidence
- [ ] Add `gdrive_url` (URLField, blank) to legal.LegalCommunication
- [ ] Add `gdrive_url` (URLField, blank) to notes.Attachment
- [ ] Add `gdrive_url` (URLField, blank) to healthcare.TestResult
- [ ] 4 data migrations
- [ ] Update EvidenceForm — add Picker widget + gdrive_url field
- [ ] Update LegalCommunicationForm — add Picker widget + gdrive_url field
- [ ] Update AttachmentForm — add Picker widget + gdrive_url field
- [ ] Update TestResultForm — add Picker widget + gdrive_url field
- [ ] Update evidence list/form partials — show Drive link icon
- [ ] Update communication list/form partials — show Drive link icon
- [ ] Update attachment list partial — show Drive link
- [ ] Update TestResult detail — show Drive link
- [ ] Both local file and Drive link always available
- [ ] Tests for each model's new field
- [ ] Update sample data with example gdrive_url values

### Completion Log
*(Updated when milestone is complete)*

---

## Milestone 5: Entity Detail Page Integration

### Scope
Add "Documents" section to all 9 entity detail pages using the existing HTMX link/unlink pattern.

### Checklist
- [ ] DocumentLinkForm — dropdown of existing documents
- [ ] `_document_link_form.html` — reusable HTMX form partial
- [ ] `_document_list.html` — reusable HTMX list partial (title, category, Drive icon, date, unlink)
- [ ] Link/unlink views per entity type (9 pairs)
- [ ] URL patterns for all link/unlink endpoints
- [ ] Documents section on: realestate_detail, investment_detail, loan_detail, lease_detail, policy_detail, vehicle_detail, aircraft_detail, stakeholder_detail, legalmatter_detail
- [ ] "New Document" link pre-populates entity FK
- [ ] Tests for link/unlink per entity type
- [ ] Playwright e2e: attach document to property, verify display

### Completion Log
*(Updated when milestone is complete)*

---

## Milestone 6: Expiration Alerts + Calendar

### Scope
Document expiration dates appear in calendar and dashboard deadline widget.

### Checklist
- [ ] Add document expiration events to `calendar_events()` in dashboard/views.py
- [ ] Add expiring documents to 30-day dashboard deadline widget
- [ ] CalendarFeedSettings: add `documents` event type
- [ ] ICS feed: include document expiration events
- [ ] Tests for calendar events + dashboard alerts

### Completion Log
*(Updated when milestone is complete)*

---

## Failure Mode Matrix

| Failure | User Experience | App Impact |
|---------|----------------|------------|
| Drive not connected | Picker button hidden. Manual URL shown. | Zero |
| Token expired + refresh fails | Banner: "reconnect in Settings". Existing doc links work. | Zero |
| Google API down | Picker shows error. Manual URL fallback. | Zero |
| File moved/deleted in Drive | User clicks link → Google 404. CC record intact. | Zero |
| Picker CDN unreachable | Picker button error state. Manual URL present. | Zero |
| google-api-python-client breaks | Pin version. gdrive.py catches exceptions. App works. | Zero |

---

## Dependencies Added (Milestone 2+)

```
google-api-python-client>=2.100.0,<3.0
google-auth-httplib2>=0.2.0,<1.0
google-auth-oauthlib>=1.2.0,<2.0
```

## Architecture

```
documents/
├── __init__.py
├── apps.py
├── models.py          ← Document + GoogleDriveSettings
├── gdrive.py          ← ALL Google API calls (abstraction layer)
├── views.py           ← CRUD + OAuth2 + Picker token endpoint
├── forms.py           ← DocumentForm + filters + setup form
├── urls.py
├── admin.py
├── tests.py
├── migrations/
├── templates/documents/
│   ├── document_list.html
│   ├── document_detail.html
│   ├── document_form.html
│   ├── gdrive_settings.html
│   └── partials/
│       ├── _document_table.html
│       ├── _document_link_form.html
│       ├── _document_list.html
│       └── _gdrive_picker.html
└── static/js/
    └── gdrive-picker.js
```
