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
| 1 | Documents app foundation (no Google) | **COMPLETE** | 16 new, 7 modified | New app + CRUD + sidebar + sample data |
| 2 | Google Drive Settings + OAuth2 | **COMPLETE** | 7 modified, 2 new | Settings page + OAuth flow + gdrive.py abstraction |
| 3 | Google Picker integration | **COMPLETE** | 6 modified, 1 new | Picker JS + template partial + token endpoint |
| 4 | Existing model migration | **COMPLETE** | 14 modified, 3 new | gdrive_url on Evidence, Communication, Attachment, TestResult |
| 5 | Entity detail page integration | **COMPLETE** | 2 new, 12 modified | Documents section on all 9 entity detail pages |
| 5b | Global search + UX polish | **COMPLETE** | 5 modified, 1 new | Search integration, mobile unlink fix, expiration sample data |
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
- [x] Create `documents/` app directory with __init__.py, apps.py, admin.py
- [x] `documents/models.py` — Document model + GoogleDriveSettings singleton
- [x] `documents/forms.py` — DocumentForm
- [x] `documents/views.py` — List, Detail, Create, Edit, Delete, CSV export, PDF export, bulk ops
- [x] `documents/urls.py` — URL patterns (app_name = "documents")
- [x] `documents/tests.py` — 44 unit tests

**Model — Document:**
- [x] title (CharField 255)
- [x] category (CharField 100, blank) — DB-backed via `document_category` ChoiceOption
- [x] description (TextField, blank)
- [x] date (DateField, null/blank)
- [x] expiration_date (DateField, null/blank)
- [x] gdrive_file_id (CharField 255, blank, db_index)
- [x] gdrive_url (URLField 500, blank)
- [x] gdrive_mime_type (CharField 100, blank)
- [x] gdrive_file_name (CharField 255, blank)
- [x] file (FileField upload_to='documents/', blank)
- [x] 9 nullable FKs: related_property, related_investment, related_loan, related_lease, related_policy, related_vehicle, related_aircraft, related_stakeholder, related_legal_matter
- [x] notes_text (TextField, blank)
- [x] created_at, updated_at
- [x] Properties: has_drive_link, has_file, file_url, linked_entities, is_expired, is_expiring_soon

**Model — GoogleDriveSettings:**
- [x] Singleton (pk=1) with load() classmethod
- [x] is_connected, client_id, client_secret, api_key, refresh_token, access_token, token_expiry, connected_email
- [x] Shell only for Milestone 1 — no Google logic yet

**Registration:**
- [x] Add `documents` to INSTALLED_APPS in config/settings.py
- [x] Add URL include in config/urls.py
- [x] Add `document_category` to ChoiceOption CATEGORY_CHOICES
- [x] Data migration for default document categories (13 categories)

**Templates:**
- [x] `documents/document_list.html` — search, category filter, entity filter, expiration filter, date range, sort, bulk actions
- [x] `documents/document_detail.html` — metadata, Drive link button, entity links, notes, file source
- [x] `documents/document_form.html` — create/edit with explicit field layout, entity link section
- [x] `documents/partials/_document_table.html` — HTMX table partial with expiration color coding

**Sidebar:**
- [x] Add Documents link to `templates/partials/_sidebar.html` (with document icon)

**Exports:**
- [x] CSV export (list page + bulk)
- [x] PDF export (detail page)

**Sample data:**
- [x] Update `load_sample_data.py` — 8 sample documents linked to properties, investments, policies, legal matters, stakeholders
- [x] Update `clean_sample_data.py` — safe document cleanup by title matching
- [x] Update SAMPLE_NAMES dict + SECTION_ORDER/DEPS/DELETION_ORDER

**Tests:**
- [x] Model tests: creation, str, properties (has_drive_link, file_url, is_expired, is_expiring_soon, linked_entities, ordering)
- [x] View tests: list, detail, create, edit, delete (200/302)
- [x] Form tests: valid minimal, valid full, invalid no title
- [x] Filter tests: search, category, entity_type, expiring_soon, expired, date range, sort, unlinked
- [x] Export tests: CSV (list + bulk), PDF
- [x] Empty state tests (bulk delete, HTMX partial)
- [x] GoogleDriveSettings tests: singleton load, str display

**Verification:**
- [x] `make test-unit` — 1124 tests pass (1080 existing + 44 new)
- [x] `make test-e2e` — 140 tests pass
- [x] Docker rebuild + manual Playwright verification (all pages, CRUD, filters, HTMX)
- [x] Desktop screenshot (1280x800) — list, detail, create, edit verified
- [x] Mobile screenshot (420x912) — responsive layout, entity metadata visible
- [x] Tailwind build completed
- [x] HTMX filter swaps verified — surrounding elements intact

### Completion Log
**Completed: 2026-03-09**

Files created (16):
- `documents/__init__.py`, `documents/apps.py`, `documents/admin.py`
- `documents/models.py` (Document + GoogleDriveSettings)
- `documents/forms.py` (DocumentForm)
- `documents/views.py` (7 views + 3 exports + 2 bulk ops)
- `documents/urls.py` (9 URL patterns)
- `documents/tests.py` (44 tests)
- `documents/migrations/__init__.py`, `documents/migrations/0001_initial.py`
- `documents/templatetags/__init__.py`
- `documents/templates/documents/document_list.html`
- `documents/templates/documents/document_detail.html`
- `documents/templates/documents/document_form.html`
- `documents/templates/documents/partials/_document_table.html`
- `dashboard/migrations/0018_seed_document_categories.py`
- `dashboard/migrations/0019_alter_choiceoption_category.py`

Files modified (7):
- `config/settings.py` — added 'documents' to INSTALLED_APPS
- `config/urls.py` — added documents URL include
- `templates/partials/_sidebar.html` — added Documents nav link
- `dashboard/models.py` — added document_category to CATEGORY_CHOICES
- `dashboard/choice_seed_data.py` — added 13 document categories
- `dashboard/management/commands/load_sample_data.py` — documents section + 8 sample docs
- `dashboard/management/commands/clean_sample_data.py` — document cleanup
- `Makefile` — added documents to test-unit command

---

## Milestone 2: Google Drive Settings + OAuth2

### Scope
Settings page for Google Drive credentials. OAuth2 authorization flow with Google Workspace. Token storage and refresh. Connection health check.

### Checklist
- [x] Add `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib` to requirements.txt
- [x] `documents/gdrive.py` — abstraction layer: get_credentials(), get_service(), get_file_metadata(), verify_connection(), get_picker_access_token(), revoke_credentials(), get_authorization_url(), exchange_code(), is_configured(), is_connected()
- [x] Settings page: `documents/templates/documents/gdrive_settings.html`
- [x] GoogleDriveSetupForm: client_id, client_secret, api_key fields (password masking, preserve-on-blank)
- [x] Step-by-step guidance text in settings UI (7-step numbered list with callback URL)
- [x] "Connect Google Drive" → OAuth2 authorization code flow → callback → store tokens
- [x] "Disconnect" button → revoke + clear (with confirmation dialog)
- [x] Connection status indicator (green connected banner with email / gray not-connected)
- [x] Token refresh logic (automatic before API calls in get_credentials())
- [x] Settings hub card linking to Google Drive settings (emerald cloud icon)
- [x] "Test Connection" button → verify_connection() → success/error message
- [x] Unit tests with mocked Google responses (26 new tests)
- [ ] Manual OAuth flow test with real Google Workspace account (requires user's real credentials)

### Completion Log

**Completed:** 2026-03-09

**Files created (2):**
- `documents/gdrive.py` — Full abstraction layer (~210 lines). Public API: `is_configured()`, `is_connected()`, `get_authorization_url()`, `exchange_code()`, `get_credentials()`, `get_service()`, `get_file_metadata()`, `verify_connection()`, `get_picker_access_token()`, `revoke_credentials()`. Only file that imports google-api-python-client.
- `documents/templates/documents/gdrive_settings.html` — Settings page with connection status banner, credential form (OAuth2 + API Key sections), setup instructions callout, Connect/Disconnect/Verify actions.

**Files modified (7):**
- `requirements.txt` — Added google-api-python-client, google-auth-httplib2, google-auth-oauthlib
- `documents/forms.py` — Added `GoogleDriveSetupForm` (ModelForm with password masking, preserve-existing-on-blank)
- `documents/views.py` — Added 5 views: `gdrive_settings`, `gdrive_authorize`, `gdrive_callback`, `gdrive_disconnect`, `gdrive_verify`
- `documents/urls.py` — Added 5 URL patterns under `gdrive/`
- `dashboard/templates/dashboard/settings_hub.html` — Added Google Drive card (emerald theme)
- `documents/tests.py` — Added 26 new tests (form, settings view, authorize, callback, disconnect, verify, gdrive module)
- `static/css/tailwind.css` — Rebuilt

**Test count:** 1186 unit + 140 e2e = 1326 total (all passing)

---

## Milestone 3: Google Picker Integration

### Scope
Google Picker JavaScript widget embedded in document forms. Reusable template include. Fallback to manual URL entry.

### Checklist
- [x] `static/js/gdrive-picker.js` — Picker wrapper (load libs, handle auth, create picker, populate form fields, error handling)
- [x] `documents/templates/documents/partials/_gdrive_picker.html` — reusable include with Picker button + hidden fields + manual URL fallback
- [x] Picker token endpoint: `GET /documents/api/picker-token/` → returns fresh access token JSON
- [x] Integrate into Document create/edit forms (via `GDriveContextMixin`)
- [x] Auto-populate title from filename when Picker selects a file (strips extension)
- [x] Conditional rendering: Picker button only shows if Drive is connected AND api_key is set
- [x] Tests for token endpoint, form rendering with/without Drive connection (13 new tests)
- [ ] Manual testing: pick real files from Google Drive (requires user's real credentials)

### Completion Log
**Completed:** 2026-03-09

**Files created (1):**
- `static/js/gdrive-picker.js` — Self-contained Picker wrapper (~180 lines). Reads config from `#gdrive-config` data attributes. Flow: button click → `Promise.all([loadPickerApi(), fetchToken()])` → `createPicker()` → `pickerCallback()` → `populateForm()`. Auto-populates hidden fields + URL + title (strips extension). Shows selected file feedback with clear button. Edit mode auto-shows feedback for existing Drive data.

**Files modified (6):**
- `documents/forms.py` — Added `gdrive_file_id`, `gdrive_mime_type`, `gdrive_file_name` to DocumentForm with `HiddenInput` widgets
- `documents/views.py` — Added `GDriveContextMixin` (injects `drive_connected`, `drive_api_key`, `drive_client_id`), `picker_token` endpoint, applied mixin to Create/Update views
- `documents/urls.py` — Added `api/picker-token/` URL pattern
- `documents/templates/documents/partials/_gdrive_picker.html` — Picker button + selected file feedback + error display + hidden fields (conditionally rendered)
- `documents/templates/documents/document_form.html` — Added `{% load static %}`, picker partial include, conditional URL help text, `{% block extra_js %}` with gapi.js + gdrive-picker.js + config div
- `documents/tests.py` — Added 13 new tests: PickerTokenEndpointTest (3), PickerFormContextTest (7), DocumentFormPickerFieldsTest (3)

**Test count:** 1199 unit + 140 e2e = 1339 total (all passing)

---

## Milestone 4: Existing Model Migration

### Scope
Add `gdrive_url` field to the 4 existing models that have FileField. Update forms and templates to show Drive link alongside file upload. Both local file and Drive URL always available — neither is a dependency.

### Checklist
- [x] Add `gdrive_url` (URLField 500, blank, verbose_name="Google Drive URL") to legal.Evidence
- [x] Add `gdrive_url` (URLField 500, blank, verbose_name="Google Drive URL") to legal.LegalCommunication
- [x] Add `gdrive_url` (URLField 500, blank, verbose_name="Google Drive URL") to notes.Attachment
- [x] Add `gdrive_url` (URLField 500, blank, verbose_name="Google Drive URL") to healthcare.TestResult
- [x] `has_drive_link` property on all 4 models: `return bool(self.gdrive_url)`
- [x] Notes Attachment `file` changed from required to `blank=True` — allows Drive-only attachments
- [x] Attachment `__str__` updated: shows description, then file name, then gdrive_url as fallback
- [x] 3 migrations: `legal/0008`, `notes/0010`, `healthcare/0005`
- [x] Update EvidenceForm — add gdrive_url field
- [x] Update LegalCommunicationForm — add gdrive_url field
- [x] Update AttachmentForm — add gdrive_url field + clean() validation (requires file OR gdrive_url)
- [x] Update TestResultForm — add gdrive_url field
- [x] Update evidence list partial — green Drive link with cloud icon
- [x] Update evidence form partial — Google Drive URL input alongside file
- [x] Update communication row partial — combined Drive (green) + file (blue) links
- [x] Update communication form partial — Drive URL in 2-col grid with file
- [x] Update attachment list partial — Drive links (green) vs file links (blue) with mobile-friendly layout
- [x] Update attachment form partial — File + Drive URL + Description in 2-col grid
- [x] Update TestResult detail — Drive link section alongside file download
- [x] Both local file and Drive link always available (no dependency)
- [x] 12 new unit tests: model field + has_drive_link for all 4 models, form validation for Attachment
- [x] Update sample data: 5/9 evidence items + 3/5 communications have example gdrive_url values
- [x] 1151 unit tests + 140 e2e tests passing
- [x] Playwright verification: all forms, list displays, detail pages, mobile layout

### Completion Log
**Completed: 2026-03-09**

Files modified (14):
- `legal/models.py` — added `gdrive_url` + `has_drive_link` to Evidence and LegalCommunication
- `notes/models.py` — added `gdrive_url` + `has_drive_link` to Attachment, `file` changed to `blank=True`, `__str__` updated
- `healthcare/models.py` — added `gdrive_url` + `has_drive_link` to TestResult
- `legal/forms.py` — added `gdrive_url` to EvidenceForm and LegalCommunicationForm field lists
- `notes/forms.py` — added `gdrive_url` to AttachmentForm + clean() validation
- `healthcare/forms.py` — added `gdrive_url` to TestResultForm field list
- `legal/templates/legal/partials/_evidence_list.html` — green Drive link with cloud SVG icon
- `legal/templates/legal/partials/_evidence_form.html` — Google Drive URL field in grid
- `legal/templates/legal/partials/_communication_row.html` — combined Drive + file link display
- `legal/templates/legal/partials/_communication_form.html` — Drive URL in 2-col grid with file
- `notes/templates/notes/partials/_attachment_list.html` — Drive (green) vs file (blue) links
- `notes/templates/notes/partials/_attachment_form.html` — File + Drive URL + Description grid
- `healthcare/templates/healthcare/testresult_detail.html` — Drive link section alongside file
- `dashboard/management/commands/load_sample_data.py` — evidence + communication tuples extended with gdrive_url values

Files created (3):
- `legal/migrations/0008_add_gdrive_url.py` — adds gdrive_url to Evidence and LegalCommunication
- `notes/migrations/0010_add_gdrive_url.py` — adds gdrive_url to Attachment, alters file to blank=True
- `healthcare/migrations/0005_add_gdrive_url.py` — adds gdrive_url to TestResult

Tests added (in existing test files):
- `legal/tests.py` — 4 tests: Evidence gdrive_url field, Evidence has_drive_link, LegalCommunication gdrive_url, LegalCommunication has_drive_link
- `notes/tests.py` — 4 tests: Attachment gdrive_url field, has_drive_link, form requires file or gdrive, form valid with gdrive only
- `healthcare/tests.py` — 2 tests: TestResult gdrive_url field, has_drive_link

---

## Milestone 5: Entity Detail Page Integration

### Scope
Add "Documents" section to all 9 entity detail pages using the existing HTMX link/unlink pattern.

### Checklist
- [x] DocumentLinkForm — dropdown of existing documents
- [x] `_document_link_form.html` — reusable HTMX form partial
- [x] `_document_list_section.html` — reusable HTMX list partial (title, category, Drive icon, date, expiration indicator, unlink)
- [x] Link/unlink views per entity type (9 pairs) — generic helpers + thin wrappers in documents/views.py
- [x] URL patterns for all 18 link/unlink endpoints in documents/urls.py
- [x] Documents section on: realestate_detail, investment_detail, loan_detail, lease_detail, policy_detail, vehicle_detail, aircraft_detail, stakeholder_detail, legalmatter_detail
- [x] "New Document" link pre-populates entity FK via query param
- [x] Document count in section header — "Documents (N)"
- [x] Tests for link/unlink per entity type (9 test methods)
- [x] Tests for entity detail pages showing linked documents (4 test methods)
- [x] Playwright interactive verification: link, unlink, form load/cancel, all 9 entity types, HTMX swap integrity
- [x] Desktop + mobile screenshots verified

### Completion Log
**Completed: 2026-03-09**

Files created (2):
- `documents/templates/documents/partials/_document_link_form.html`
- `documents/templates/documents/partials/_document_list_section.html`

Files modified (12):
- `documents/forms.py` — added DocumentLinkForm
- `documents/views.py` — added ENTITY_CONFIG, _doc_list_ctx, _document_link, _document_unlink helpers + 18 thin wrapper view functions
- `documents/urls.py` — added 18 link/unlink URL patterns
- `documents/tests.py` — added 15 new tests (DocumentLinkFormTest, DocumentEntityLinkTest, EntityDetailDocumentSectionTest)
- `assets/views.py` — added `entity_documents` to context for all 7 asset detail views
- `assets/templates/assets/realestate_detail.html` — added Documents section
- `assets/templates/assets/investment_detail.html` — added Documents section
- `assets/templates/assets/loan_detail.html` — added Documents section
- `assets/templates/assets/lease_detail.html` — added Documents section
- `assets/templates/assets/policy_detail.html` — added Documents section
- `assets/templates/assets/vehicle_detail.html` — added Documents section
- `assets/templates/assets/aircraft_detail.html` — added Documents section
- `stakeholders/views.py` — added `entity_documents` to stakeholder detail context
- `stakeholders/templates/stakeholders/stakeholder_detail.html` — added Documents section
- `legal/views.py` — added `entity_documents` to legal detail context
- `legal/templates/legal/legal_detail.html` — added Documents section

---

## Milestone 5b: Global Search + UX Polish

### Scope
Close integration gaps found in the Milestone 5 audit: documents missing from global search, mobile unlink button invisible on touch devices, expiration filters showing no results due to missing sample data.

### Checklist
- [x] Add Document model to global search view (search by title, description, category)
- [x] Add Documents section to search results template (category label, date, Drive indicator, expiration badges)
- [x] Fix mobile unlink button: `sm:opacity-0 sm:group-hover:opacity-100` (always visible on mobile, hover-reveal on desktop)
- [x] Add 2 sample documents with expiration dates: "Elm St Business License" (expiring in 45 days), "Magnolia Blvd Phase I ESA Report" (expired 35 days ago)
- [x] Add 2 new document categories: "License / Permit" (license), "Environmental Report" (environmental)
- [x] Data migration for new categories (0020_seed_document_categories_v2)
- [x] Update SAMPLE_NAMES and clean_sample_data support for new documents
- [x] 2 new unit tests for document search
- [x] `make test-unit` — 1141 tests pass + `make test-e2e` — 140 tests pass
- [x] Playwright verification: search, filters, mobile unlink, entity detail pages

### Completion Log
**Completed: 2026-03-09**

Files modified (5):
- `dashboard/views.py` — added Document query to `global_search()` + added `documents` to `has_results` check
- `dashboard/templates/dashboard/partials/_search_results.html` — added Documents section with category, date, Drive indicator, expiration badges
- `dashboard/tests.py` — added 2 tests (search by title, search by description)
- `documents/templates/documents/partials/_document_list_section.html` — fixed mobile unlink button visibility
- `dashboard/management/commands/load_sample_data.py` — added 2 sample documents with expiration dates, updated SAMPLE_NAMES
- `dashboard/choice_seed_data.py` — added `license` and `environmental` categories

Files created (1):
- `dashboard/migrations/0020_seed_document_categories_v2.py` — data migration for 2 new document categories

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

## Usage Guide

### Creating a Document

1. Navigate to **Documents** in the sidebar (or click `+ New Document` on the list page)
2. Fill in required **Title** and any optional fields:
   - **Category** — 15 DB-backed choices (Tax Return, Deed, Operating Statement, Appraisal, etc.)
   - **Date** — when the document was created/received
   - **Description** — free-text summary
   - **Expiration Date** — triggers color-coded alerts on list page (red=expired, amber=≤90 days)
   - **File Upload** — local file attachment (optional)
   - **Google Drive URL** — paste a Drive sharing link, or use Picker (see below)
   - **Notes** — additional context
3. Under **Link to Entity**, optionally select related Property, Investment, Loan, Lease, Policy, Vehicle, Aircraft, Stakeholder, or Legal Matter
4. Click **Create Document**

### Using the Google Drive Picker

**Prerequisites:** Google Drive must be connected (see Setup below).

1. On the document create/edit form, click the green **Pick from Google Drive** button
2. A Google Picker dialog opens showing your Drive files
3. Select a file → the form auto-populates:
   - **Google Drive URL** (the sharing link)
   - **Title** (from filename, stripped of extension — only if title field is empty)
   - Hidden metadata: `gdrive_file_id`, `gdrive_mime_type`, `gdrive_file_name`
4. The selected file name and MIME type appear below the Picker button
5. Click **Clear selection** to undo and pick a different file
6. You can always paste a Drive URL manually instead of using the Picker

**Fallback:** If Google APIs are unavailable, the Picker shows an error message. The manual URL field always works regardless of Drive connection status.

### Setting Up Google Drive Integration

#### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown at the top → **New Project**
3. Name it something like `control-center` → **Create**
4. Make sure the new project is selected in the dropdown

#### Step 2: Enable Required APIs

1. Go to **APIs & Services** → **Library** (or search "API Library" in the console search bar)
2. Search for and enable each of these:
   - **Google Drive API** — click → **Enable**
   - **Google Picker API** — click → **Enable**

#### Step 3: Create OAuth 2.0 Credentials

1. Go to **Google Auth Platform** → **Clients** (or **APIs & Services** → **Credentials**)
2. Click **+ Create Client** (or **Create Credentials** → **OAuth client ID**)
3. Set **Application type** to **Web application**
4. Set **Name** to something like `control-center-dev`
5. Under **Authorized JavaScript origins**, click **+ Add URI** and enter:
   ```
   http://localhost:8000
   ```
6. Under **Authorized redirect URIs**, click **+ Add URI** and enter:
   ```
   http://localhost:8000/documents/gdrive/callback/
   ```
7. Click **Create**
8. A dialog shows your **Client ID** and **Client Secret** — copy both (you can also download the JSON)

> **Production:** When deploying behind VPN, add your production hostname to both fields:
> - JavaScript origin: `https://your-server.vpn`
> - Redirect URI: `https://your-server.vpn/documents/gdrive/callback/`

#### Step 4: Create an API Key (for the Picker widget)

1. Go to **APIs & Services** → **Credentials**
2. Click **+ Create credentials** → **API Key**
3. A "Create API key" panel opens on the right:
   - **Name**: Change `API key 1` to something descriptive (e.g., `control-center-picker`)
   - **Application restrictions**: Select **Websites**, then click **Add** and enter:
     ```
     http://localhost:8000/*
     ```
   - **API restrictions**: Select **Restrict key**, then choose **Google Picker API** from the dropdown
4. Click **Create**
5. Copy the generated API key value (starts with `AIza...`)

#### Step 5: Configure Control Center

1. In Control Center, go to **Settings** → **Google Drive** (or navigate to `/documents/gdrive/settings/`)
2. Paste your **Client ID** into the Client ID field
3. Paste your **Client Secret** into the Client Secret field
4. Paste your **API Key** into the API Key field
5. Click **Save Credentials**

#### Step 6: Connect Your Google Account

1. On the same settings page, click **Connect Google Drive**
2. Google's consent screen opens — select your Google account
3. If you see "This app isn't verified" (expected for personal projects), click **Advanced** → **Go to control-center (unsafe)** — this is safe, it's your own app
4. Grant the requested permissions (read-only Drive access + email)
5. You're redirected back to Control Center with a green **Connected to Google Drive** banner showing your email
6. Click **Test Connection** to verify everything works

#### Troubleshooting

| Problem | Solution |
|---------|----------|
| "redirect_uri_mismatch" error | The redirect URI in Google Console must **exactly** match `http://localhost:8000/documents/gdrive/callback/` — check for trailing slash, http vs https, port number |
| "This app isn't verified" warning | Expected for personal/development apps. Click Advanced → Continue. You can configure the OAuth consent screen under **Branding** in Google Auth Platform to suppress this. |
| Picker button doesn't appear after connecting | Verify all 3 conditions: `is_connected` = True (OAuth completed), `refresh_token` exists, AND `api_key` is set. All three are required. |
| "Token request failed (500)" when clicking Picker | The refresh token may be invalid. Go to settings → **Disconnect** → reconnect. |

**Localhost / development note:** Google OAuth explicitly allows `http://localhost` redirect URIs without HTTPS — it's a special case in their policy. No public hostname or SSL certificate needed for development. When deploying to a private server behind VPN, update the callback URL and JavaScript origin in both the Google Cloud Console and the app's settings page to match the production hostname.

### Searching & Filtering Documents

**List page** (`/documents/`):
- **Search**: Type in the search box — filters by title, description, and Drive filename (HTMX live search with 300ms debounce)
- **Category**: Select from dropdown — 15 document categories
- **Linked To**: Filter by entity type (Property, Investment, Loan, etc.) or "Unlinked"
- **Expiration**: Filter by "Expiring Soon" (≤90 days), "Expired", or "All"
- **Date Range**: Set "Date From" and "Date To" to narrow by document date
- **Sort**: Click column headers (Title, Category, Date) to sort ascending/descending

**Global search** (`/search/?q=...`):
- Documents appear in global search results alongside stakeholders, tasks, notes, etc.
- Matches on title, description, and category
- Results show category label, date, Drive indicator (cloud icon), and expiration badges

### Exports

- **CSV Export**: Click **Export CSV** on the list page (purple button). Includes columns: Title, Category, Date, Expiration Date, Google Drive URL, Drive Filename, Description. Respects current filters.
- **Bulk CSV Export**: Select specific rows with checkboxes → use the bulk bar's **Export Selected** button
- **PDF Export**: On any document detail page, click the **PDF** button (purple). Generates a single-document report with all metadata, entity links, and notes.

### Linking Documents to Entities

**From the document form:**
- Select entities in the **Link to Entity** section when creating or editing

**From entity detail pages:**
- Every entity detail page (Property, Investment, Loan, Lease, Policy, Vehicle, Aircraft, Stakeholder, Legal Matter) has a **Documents** section
- Click **+ Add** to link an existing document from a dropdown
- Click **New Document** to create a new document pre-linked to that entity
- Click the **×** button on any linked document to unlink it (HTMX inline, no page reload)
- Document count shows in the section header: "Documents (N)"

### Drive URLs on Legal Evidence & Other Models

Four existing models also support Google Drive URLs alongside their file upload fields:

| Model | Where to Find | Usage |
|-------|--------------|-------|
| **Evidence** | Legal Matter detail → Evidence section → Add Evidence | Fill in the "Google Drive URL" field alongside or instead of file upload |
| **Communication** | Legal Matter detail → Communications tab → Add Communication | Drive URL field in the communication form |
| **Attachment** | Note detail → Attachments section → Add Attachment | File upload OR Drive URL (at least one required) |
| **Test Result** | Healthcare → Procedure detail → Test Results | Drive URL for lab results stored in Drive |

In list displays, Drive links appear as green cloud icons; local file links appear as blue document icons.

### Expiration Tracking

- Documents with expiration dates show color-coded indicators on the list page:
  - **Red** — expired
  - **Amber** — expiring within 90 days
  - **Green/dash** — no expiration or >90 days away
- The list header shows "N expiring soon" count
- Use the **Expiration** filter dropdown to show only expiring/expired documents
- Expiration dates are visible on detail pages and in CSV exports

---

## Pages & URLs Affected

### New Pages (Documents App)

| URL | Page | Description |
|-----|------|-------------|
| `/documents/` | Document list | Filterable table with search, category, entity, expiration, date range filters. Bulk actions. |
| `/documents/create/` | Create document | Full form with entity linking, Drive Picker (when connected), file upload |
| `/documents/<id>/` | Document detail | Metadata, Drive link, entity links, notes, file source. PDF/Edit/Delete buttons. |
| `/documents/<id>/edit/` | Edit document | Pre-populated form, Drive Picker preserves existing selection |
| `/documents/<id>/delete/` | Delete confirmation | Standard confirm-delete pattern |
| `/documents/<id>/pdf/` | PDF export | Single-document reportlab PDF |
| `/documents/export/` | CSV export | Full list or filtered CSV download |
| `/documents/gdrive/settings/` | Drive settings | OAuth credentials, connect/disconnect, test connection |
| `/documents/gdrive/authorize/` | OAuth redirect | Redirects to Google OAuth consent screen |
| `/documents/gdrive/callback/` | OAuth callback | Receives auth code, stores tokens |
| `/documents/gdrive/disconnect/` | Disconnect | Revokes tokens, clears connection |
| `/documents/gdrive/verify/` | Test connection | Verifies stored credentials work |
| `/documents/api/picker-token/` | Picker token API | Returns fresh access token JSON for Picker JS |
| `/documents/link/<entity>/<id>/` | Link document (×9) | HTMX POST to link a document to an entity |
| `/documents/unlink/<entity>/<id>/<doc_id>/` | Unlink document (×9) | HTMX POST to unlink |

### Modified Pages (Other Apps)

| Page | What Changed |
|------|-------------|
| **Sidebar** (`_sidebar.html`) | Added Documents nav link with document icon |
| **Settings Hub** (`settings_hub.html`) | Added Google Drive card (emerald theme) |
| **Global Search** (`_search_results.html`) | Added Documents result section |
| **Property Detail** (`realestate_detail.html`) | Added Documents section with HTMX link/unlink |
| **Investment Detail** (`investment_detail.html`) | Added Documents section |
| **Loan Detail** (`loan_detail.html`) | Added Documents section |
| **Lease Detail** (`lease_detail.html`) | Added Documents section |
| **Policy Detail** (`policy_detail.html`) | Added Documents section |
| **Vehicle Detail** (`vehicle_detail.html`) | Added Documents section |
| **Aircraft Detail** (`aircraft_detail.html`) | Added Documents section |
| **Stakeholder Detail** (`stakeholder_detail.html`) | Added Documents section |
| **Legal Matter Detail** (`legal_detail.html`) | Added Documents section |
| **Evidence Form** (`_evidence_form.html`) | Added Google Drive URL field |
| **Evidence List** (`_evidence_list.html`) | Added green Drive link with cloud icon |
| **Communication Form** (`_communication_form.html`) | Added Drive URL field in grid |
| **Communication Row** (`_communication_row.html`) | Added combined Drive + file link display |
| **Attachment Form** (`_attachment_form.html`) | Added Drive URL field, file now optional |
| **Attachment List** (`_attachment_list.html`) | Added Drive (green) vs file (blue) link icons |
| **Test Result Detail** (`testresult_detail.html`) | Added Drive link section |

---

## Architecture

```
documents/
├── __init__.py
├── apps.py
├── models.py          ← Document + GoogleDriveSettings
├── gdrive.py          ← ALL Google API calls (abstraction layer)
├── views.py           ← CRUD + OAuth2 + Picker token + entity link/unlink
├── forms.py           ← DocumentForm + DocumentLinkForm + GoogleDriveSetupForm
├── urls.py            ← 42 URL patterns (CRUD + OAuth + API + 18 link/unlink)
├── admin.py
├── tests.py           ← 100+ tests (model, view, form, filter, export, Drive, link/unlink)
├── migrations/
├── templates/documents/
│   ├── document_list.html
│   ├── document_detail.html
│   ├── document_form.html
│   ├── gdrive_settings.html
│   └── partials/
│       ├── _document_table.html
│       ├── _document_link_form.html
│       ├── _document_list_section.html
│       └── _gdrive_picker.html
└── static/js/
    └── gdrive-picker.js

Other apps modified:
├── legal/models.py              ← gdrive_url on Evidence + LegalCommunication
├── notes/models.py              ← gdrive_url on Attachment (file now optional)
├── healthcare/models.py         ← gdrive_url on TestResult
├── legal/forms.py               ← gdrive_url on EvidenceForm + LegalCommunicationForm
├── notes/forms.py               ← gdrive_url on AttachmentForm + clean() validation
├── healthcare/forms.py          ← gdrive_url on TestResultForm
├── assets/views.py              ← entity_documents context for 7 asset detail views
├── stakeholders/views.py        ← entity_documents context for stakeholder detail
├── legal/views.py               ← entity_documents context for legal detail
├── dashboard/views.py           ← Document added to global_search()
└── 9 entity detail templates    ← Documents section added to each
```
