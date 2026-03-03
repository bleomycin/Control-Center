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
| **assets** | RealEstate, PropertyOwnership, Investment, InvestmentParticipant, Loan, LoanParty | Unified `/assets/` page with HTMX tab switching (Properties/Investments/Loans); M2M through models for multi-stakeholder ownership with percentages and roles; inline status editing on properties and loans |
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
- **Currency**: `django.contrib.humanize` `intcomma` filter everywhere

### Editable Choices (DB-backed dropdowns)
- `ChoiceOption` model in `dashboard/models.py` — 4 categories: `entity_type`, `contact_method`, `matter_type`, `note_type`
- `dashboard/choices.py`: `get_choices(category)` (cached), `get_choice_label(category, value)`, `invalidate_choice_cache()`
- Template: `{% load choice_labels %}` then `{{ value|choice_label:"category" }}`
- Status/workflow fields (task status, priority, etc.) are NOT DB-backed — their values are in business logic

### Unified Assets Page
- `asset_list` function view at `/assets/` — 3 HTMX tabs (Properties/Investments/Loans) with tab counts
- `switchAssetTab()` JS updates active styling; hidden `#current-tab` input preserves tab in filter form
- Tab content partial `_asset_tab_content.html` dispatches by `current_tab`; each tab has its own table headers, bulk bar, and sort controls
- Inline status editing: `_realestate_row.html` and `_loan_row.html` with `<select>` → `htmx.ajax()` POST to `inline_update_*_status` views
- Old CBV list views (`/assets/real-estate/`, etc.) remain for backwards compatibility

### Multi-Stakeholder Ownership
- Through models: `PropertyOwnership`, `InvestmentParticipant`, `LoanParty` in `assets/models.py` — each stores percentage and role
- HTMX inline add/delete on asset detail pages AND stakeholder detail page (mirror pattern)
- Create forms include optional "Initial Owner/Participant" fields, hidden on edit via `get_form()` field deletion

### Firm/Employee Hierarchy
- `Stakeholder.parent_organization` self-FK (SET_NULL); firms have `entity_type="firm"`
- HTMX inline add/remove employees on firm detail page and Firms & Teams cards; per-firm target IDs (`#employee-list-{{ firm.pk }}`)
- Entity type and firm assignment are orthogonal — employees appear in their entity-type tabs

### Task System
- `Task.direction`: `personal`/`outbound`/`inbound` — NOT a DB-backed ChoiceOption
- `Task.related_stakeholders` M2M (plain, no through model); `_grouped_stakeholder_choices()` in `tasks/forms.py` builds `<optgroup>` widget
- `FollowUp`: `reminder_enabled` (default=False) opt-in + `follow_up_days` (default=3); `response_notes` TextField; "Create Note" link pre-fills via query params
- `SubTask`: HTMX add/toggle/delete; progress bar on detail, `N/M` annotations on list/kanban
- Recurring: `is_recurring` + `recurrence_rule`; `create_next_recurrence()` called in all 4 completion paths
- Meeting: `task_type="meeting"` + optional `due_time` TimeField; blue styling; "+ Add Meeting Notes" pre-fills note creation
- Kanban: SortableJS drag-and-drop, `kanban_update` endpoint, no pagination on board view
- Inline edit: clickable status/priority badges cycle values; `_task_row.html` partial for single-row re-render
- Grouped view: `_build_grouped_tasks()` with 4 modes (status/priority/due_date/stakeholder)

### Stakeholder Tabs
- `StakeholderTab` model — `key`, `label`, `entity_types` (JSONField), `sort_order`, `is_builtin`
- Built-in: "All" and "Firms & Teams" (non-editable). Dynamic "Other" tab for unclaimed entity types.
- `switchStakeholderTab()` JS updates active styling (tab bar is outside HTMX swap target)
- Inline entity type editing: `<select>` in row → `inline_update_type` POST → re-renders `_stakeholder_row.html`

### Notes System
- 3 view modes: cards (`_note_cards.html`), list (`_note_table_view.html`), timeline (`_note_timeline_view.html`) — `get_template_names()` routes by `view` param
- `Tag` (name, slug, color) + `Folder` (name, color, sort_order); `notes/templatetags/tag_colors.py` maps color names → CSS class string literals (for Tailwind scanning)
- Pinned-first sorting via `-is_pinned` prepended to `order_by`; timeline uses `OrderedDict` with pre-seeded group order
- Folder tab bar with inline "Manage Folders" panel; `HX-Trigger: foldersChanged` auto-refreshes tabs
- Bulk tag: Add/Remove mode toggle with `toggleTagPill()` JS; bulk folder: select dropdown with Unfiled option
- External links: `Link` model with HTMX inline add/edit/delete mirroring attachment pattern
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
- Tag slug collision: uniqueness loop generates `base-slug-1`, `-2`, etc.
- `bulk-actions.js` looks up `#select-all` dynamically and uses fully delegated change events (works after HTMX swaps)
- `switchView()` uses `source: form` (not `values: getFilterValues()`) for proper multi-select serialization
- Django test runner uses in-memory SQLite — WAL mode returns 'memory', not 'wal'
- Backup/restore tests must use temp file-based DBs, not the in-memory test DB

## Next Steps
- User authentication (currently no login required — fine for single-user VPN access)
