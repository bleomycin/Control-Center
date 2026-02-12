# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Control Center** is a self-hosted personal management system designed as a single-user command center for managing complex personal affairs. Built for Legacy. Accessed via VPN on a private server (currently demoed via ngrok). No team collaboration features needed.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| Framework | Django 6.0.2 |
| Database | SQLite (WAL mode) |
| Frontend | Django Templates + HTMX 2.0.4 |
| CSS | Tailwind CSS 3.4 (standalone CLI) |
| Charts | Chart.js 4.x (CDN) |
| Markdown | EasyMDE 2.20 (CDN) + Python markdown 3.10 |
| PDF Export | reportlab 4.4.9 (platypus engine) |
| Background Jobs | Django-Q2 (ORM broker) |
| Static Files | WhiteNoise 6.9.0 |
| Deployment | Docker (Gunicorn + WhiteNoise) |

## Build & Run Commands

### Docker (recommended)

```bash
cp .env.example .env    # edit SECRET_KEY for production
docker compose up --build

# Run tests inside container
docker compose exec web python manage.py test

# Backup / restore
docker compose exec web python manage.py backup
docker compose exec web python manage.py restore /app/backups/<archive>.tar.gz

# Shell into container
docker compose exec web bash
```

### Local Development

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser (for admin panel access)
python manage.py createsuperuser

# Run development server
python manage.py runserver

# Run on LAN / for ngrok
python manage.py runserver 0.0.0.0:8000

# Load sample data (comprehensive demo dataset)
python manage.py load_sample_data

# Register notification schedules (django-q2)
python manage.py setup_schedules

# Start background task worker (django-q2)
python manage.py qcluster

# Run tests
python manage.py test

# Run a single test module
python manage.py test <app_name>.tests.<TestClass>

# Make migrations after model changes
python manage.py makemigrations

# Backup / restore (local)
python manage.py backup                    # → backups/controlcenter-backup-*.tar.gz
python manage.py backup --keep 7           # keep only 7 most recent
python manage.py restore backups/<file>.tar.gz

# Tailwind CSS (standalone CLI — no Node.js required)
make tailwind-install   # download binary to ./bin/tailwindcss
make tailwind-build     # one-shot minified build → static/css/tailwind.css
make tailwind-watch     # watch mode for development
```

## Apps & Architecture

Seven Django apps, all relationally linked:

| App | Models | Purpose |
|-----|--------|---------|
| **dashboard** | ChoiceOption, EmailSettings, Notification, SampleDataStatus | Homepage, global search, timeline, calendar, email/SMTP, notifications, choice management, settings hub, sample data toggle |
| **stakeholders** | Stakeholder, StakeholderTab, Relationship, ContactLog | CRM — entity profiles, trust/risk ratings, relationships, contact logs; firm/employee hierarchy via `parent_organization` self-FK; dynamic DB-backed list tabs |
| **assets** | AssetTab, RealEstate, PropertyOwnership, Investment, InvestmentParticipant, Loan, LoanParty, InsurancePolicy, PolicyHolder, Vehicle, VehicleOwner, Aircraft, AircraftOwner | Unified `/assets/` page with dynamic DB-backed tabs; M2M through models for multi-stakeholder ownership with percentages and roles; inline status editing; insurance policy tracking; vehicle tracking (VIN, make/model, mileage); aircraft tracking (tail number, total hours, base airport) |
| **legal** | LegalMatter, Evidence | Case status, attorneys (M2M), evidence, related stakeholders/properties |
| **tasks** | Task, FollowUp, SubTask | Deadlines, priorities, follow-ups, subtask checklists; bidirectional direction; multi-stakeholder M2M; meetings with time; kanban board; recurring tasks; grouped views |
| **cashflow** | CashFlowEntry | Actual + projected inflows/outflows with category filtering and charts |
| **notes** | Note, Attachment, Link, Tag, Folder | Searchable records linked to entities via M2M; external links; pinned notes, tags, folders, 3 view modes (cards/table/timeline) |

## Key Patterns

### General Conventions
- **Views**: CBVs for CRUD, function views for HTMX partials
- **Forms**: `TailwindFormMixin` in `legacy/forms.py` auto-applies dark-mode classes; forms load choices dynamically in `__init__`
- **HTMX**: `hx-get` with `delay:300ms` for search/filter; inline add/delete for child records; partials in `partials/` subdirs; CSRF via `hx-headers` on `<body>`
- **Templates**: `base.html` with sidebar + modal container; shared `partials/_confirm_delete.html` for all DeleteViews
- **FKs**: `SET_NULL` for optional, `CASCADE` for required; string references for cross-app FKs
- **Filtering**: All list pages use `<form id="filter-form">`. Sortable column headers with `sort`/`dir` params. Priority/status sort use `Case/When` for logical order.
- **Bulk ops**: Select-all + per-row checkboxes + sticky bulk bar. `static/js/bulk-actions.js` uses delegated events (works after HTMX swaps).
- **Exports**: CSV via `legacy/export.py`; PDF via `legacy/pdf_export.py` (reportlab platypus) with section types: "info", "table", "text"
- **Button colours**: Detail pages: purple (PDF), blue (Edit), green (Complete), red (Delete). List pages: purple (export), blue (+ New).
- **Dropdown menus**: Multi-type asset tabs use `[data-dropdown]` toggle pattern (`toggleDropdown()`/`closeAllDropdowns()` in `asset_list.html`); single-type tabs render flat buttons instead.
- **Currency**: `django.contrib.humanize` `intcomma` filter everywhere

### Editable Choices (DB-backed dropdowns)
- `ChoiceOption` model in `dashboard/models.py` — 7 categories: `entity_type`, `contact_method`, `matter_type`, `note_type`, `policy_type`, `vehicle_type`, `aircraft_type`
- `dashboard/choices.py`: `get_choices(category)` (cached), `get_choice_label(category, value)`, `invalidate_choice_cache()`
- Template: `{% load choice_labels %}` then `{{ value|choice_label:"category" }}`
- Status/workflow fields (task status, priority, direction) are NOT DB-backed — their values are in business logic

### DB-Backed Tabs (shared pattern: stakeholders + assets)
- Model: `StakeholderTab` / `AssetTab` — `key` (slug, unique), `label`, `entity_types`/`asset_types` (JSONField), `sort_order`, `is_builtin`
- `_get_tab_config()` / `_get_asset_tab_config()` builds tab list with counts + dynamic "Other" tab for unclaimed types
- Tab CRUD at `/stakeholders/tabs/` and `/assets/tabs/` — HTMX settings pages with add/edit/delete; gear icon in tab bar
- `AssetTabForm` / `StakeholderTabForm`: plain `forms.Form` (not ModelForm) with TailwindFormMixin — label + type checkboxes
- Built-in tabs are non-editable/deletable (403 on attempt)
- Multi-type asset tabs render stacked sections with `<h3>` headers; single-type tabs get sort controls and bulk actions

### Multi-Stakeholder Ownership
- Through models: `PropertyOwnership`, `InvestmentParticipant`, `LoanParty`, `VehicleOwner`, `AircraftOwner` — each stores percentage and role
- HTMX inline add/delete on asset detail pages AND stakeholder detail page (mirror pattern)
- Create forms include optional "Initial Owner/Participant" fields, hidden on edit via `get_form()` field deletion

### Insurance Policy Tracking
- `InsurancePolicy`: `policy_type` (DB-backed ChoiceOption), `status` (hardcoded: active/expired/cancelled/pending), carrier/agent FKs → Stakeholder
- `PolicyHolder` through model (role, notes — no percentage); `covered_properties` M2M → RealEstate, `covered_vehicles` M2M → Vehicle, `covered_aircraft` M2M → Aircraft
- Integrated into unified `/assets/` page as "policies" asset type; "Insurance" seed tab
- HTMX inline policyholder add/delete on detail page; inline status editing on list
- Asset detail pages: HTMX inline policy link/unlink (`AssetPolicyLinkForm`); shared partials `_asset_policy_form.html`/`_asset_policy_list.html`; "+ New Policy" pre-selects asset via query param
- Graph shows octagon nodes (prefix `ins-`) for carrier, agent, and policyholder edges
- Notes link via `related_policies` M2M

### Vehicle & Aircraft Tracking
- `Vehicle`: `vehicle_type` (DB-backed ChoiceOption), `status` (hardcoded: active/stored/sold/in_dispute); fields for VIN, make/model, mileage, license plate, registration state
- `Aircraft`: `aircraft_type` (DB-backed ChoiceOption), `status` (adds in_maintenance); fields for tail number, serial number, total hours, base airport, registration country, num_engines
- `VehicleOwner`/`AircraftOwner` through models with ownership percentage and role
- Integrated into unified `/assets/` page as "vehicles"/"aircraft" asset types; seed tabs for each
- Graph shows pentagon nodes (`v-` prefix) for vehicles, vee nodes (`ac-` prefix) for aircraft
- Notes link via `related_vehicles`/`related_aircraft` M2M

### Task System
- `Task.direction`: `personal`/`outbound`/`inbound` — NOT a DB-backed ChoiceOption
- `Task.related_stakeholders` M2M (plain, no through model); `_grouped_stakeholder_choices()` builds `<optgroup>` widget
- `SubTask`: HTMX add/toggle/delete; progress bar on detail, `N/M` annotations on list/kanban
- Recurring: `is_recurring` + `recurrence_rule`; `create_next_recurrence()` called in all 4 completion paths
- Meeting: `task_type="meeting"` + optional `due_time` TimeField
- Kanban: SortableJS drag-and-drop, `kanban_update` endpoint
- Inline edit: clickable status/priority badges cycle values; `_task_row.html` partial for single-row re-render

### Notes System
- 3 view modes: cards, list, timeline — `get_template_names()` routes by `view` param
- `Tag` (name, slug, color) + `Folder` (name, color, sort_order); `notes/templatetags/tag_colors.py` maps color names → CSS class string literals (for Tailwind scanning)
- Folder tab bar with inline "Manage Folders" panel; `HX-Trigger: foldersChanged` auto-refreshes tabs
- Markdown: `render_markdown` template filter with `nl2br` + blank-line preprocessor; `prose-markdown` CSS in `input.css`

### Notifications & Email
- `tasks/notifications.py` — 3 django-q2 scheduled functions: overdue tasks, upcoming reminders, stale follow-ups
- `EmailSettings` singleton (pk=1) stores SMTP config; `dashboard/email.py` provides connection helpers
- `Notification` model with levels (info/warning/critical); sidebar bell with HTMX badge polling (60s)

### Infrastructure
- **SQLite**: WAL mode + pragmas via `connection_created` signal in `dashboard/apps.py` (weak=False). Indexes on frequently-filtered fields.
- **Backup**: `sqlite3.backup()` API + media → `.tar.gz`; django-q2 daily auto-backup (keeps 7)
- **Docker**: Single container — Gunicorn (2 workers, 30s timeout) foreground + qcluster background. `entrypoint.sh` handles migrate/collectstatic/createsuperuser.
- **Tailwind**: Standalone CLI v3.4.17; config in `tailwind.config.js`, output at `static/css/tailwind.css`. Rebuild after adding/changing classes: `make tailwind-build`
- **Environment**: `settings.py` uses `os.environ.get()` with dev-friendly fallbacks; production security headers gated behind `not DEBUG`
- **Sample data**: `SampleDataStatus` singleton tracks loaded PKs in `manifest` JSONField; remove deletes only manifested PKs in reverse-dependency order

### Important Gotchas
- Dashboard views use lazy imports inside functions
- Forms use `__init__` override for dynamic widget/choices setup
- `Relationship`/`ContactLog`/`FollowUp` FKs use SET_NULL (not CASCADE) to prevent data loss on stakeholder deletion
- Tag/AssetTab slug collision: uniqueness loop generates `base-slug-1`, `-2`, etc.
- `bulk-actions.js` looks up `#select-all` dynamically and uses fully delegated change events (works after HTMX swaps)
- `switchView()` uses `source: form` (not `values: getFilterValues()`) for proper multi-select serialization
- Django test runner uses in-memory SQLite — WAL mode returns 'memory', not 'wal'
- Backup/restore tests must use temp file-based DBs, not the in-memory test DB

## Next Steps
- User authentication (currently no login required — fine for single-user VPN access)
