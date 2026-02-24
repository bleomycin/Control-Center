# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Control Center** is a self-hosted personal management system designed as a single-user command center for managing complex personal affairs. Accessed via VPN on a private server. No team collaboration features needed.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| Framework | Django 6.0.2 |
| Database | SQLite (WAL mode) |
| Frontend | Django Templates + HTMX 2.0.4 |
| CSS | Tailwind CSS 3.4 (standalone CLI) |
| Charts | Chart.js 4.x (self-hosted) |
| Markdown | EasyMDE 2.20 (self-hosted) + Python markdown 3.10 |
| PDF Export | reportlab 4.4.9 (platypus engine) |
| Background Jobs | Django-Q2 (ORM broker) |
| Static Files | WhiteNoise 6.9.0 |
| E2E Testing | Playwright (dev-only, in `requirements-dev.txt`) |
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

# Run all tests (unit + e2e)
python manage.py test

# Run only unit tests (exclude e2e)
python manage.py test assets cashflow config dashboard legal notes stakeholders tasks

# Run only e2e browser tests
python manage.py test e2e

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

Seven Django apps + one e2e test package, all relationally linked:

| App | Models | Purpose |
|-----|--------|---------|
| **dashboard** | ChoiceOption, EmailSettings, BackupSettings, Notification, SampleDataStatus | Homepage, global search, timeline, calendar, email/SMTP, notifications, choice management, settings hub, backup config, sample data toggle |
| **stakeholders** | Stakeholder, StakeholderTab, Relationship, ContactLog | CRM — entity profiles, trust/risk ratings, relationships, contact logs; firm/employee hierarchy via `parent_organization` self-FK; dynamic DB-backed list tabs |
| **assets** | AssetTab, RealEstate, PropertyOwnership, Investment, InvestmentParticipant, Loan, LoanParty, InsurancePolicy, PolicyHolder, Vehicle, VehicleOwner, Aircraft, AircraftOwner | Unified `/assets/` page with dynamic DB-backed tabs; M2M through models for multi-stakeholder ownership with percentages and roles; inline status editing; insurance policy tracking; loan-to-asset linking (property/investment/vehicle/aircraft); hard money loan tracking; vehicle tracking (VIN, make/model, mileage); aircraft tracking (tail number, total hours, base airport) |
| **legal** | LegalMatter, Evidence | Case status, attorneys (M2M), evidence, related stakeholders/properties |
| **tasks** | Task, FollowUp, SubTask | Deadlines, priorities, follow-ups, subtask checklists; bidirectional direction; multi-stakeholder M2M; meetings with time; kanban board; recurring tasks; grouped views |
| **cashflow** | CashFlowEntry | Actual + projected inflows/outflows with category filtering and charts |
| **notes** | Note, Attachment, Link, Tag, Folder | Searchable records linked to entities via M2M; external links; pinned notes, tags, folders, 3 view modes (cards/table/timeline) |
| **e2e** | *(no models)* | Playwright browser tests — `StaticLiveServerTestCase` base class in `e2e/base.py`; 78 tests covering inline editing, HTMX swaps, form interactivity, calendar |

## Key Patterns

### General Conventions
- **Views**: CBVs for CRUD, function views for HTMX partials
- **Forms**: `TailwindFormMixin` in `config/forms.py` auto-applies dark-mode classes; forms load choices dynamically in `__init__`
- **HTMX**: `hx-get` with `delay:300ms` for search/filter; inline add/delete for child records; partials in `partials/` subdirs; CSRF via `hx-headers` on `<body>`
- **Templates**: `base.html` with sidebar + modal container; shared `partials/_confirm_delete.html` for all DeleteViews
- **FKs**: `SET_NULL` for optional, `CASCADE` for required; string references for cross-app FKs
- **Filtering**: All list pages use `<form id="filter-form">`. Sortable column headers with `sort`/`dir` params. Priority/status sort use `Case/When` for logical order.
- **Bulk ops**: Select-all + per-row checkboxes + sticky bulk bar. `static/js/bulk-actions.js` uses delegated events (works after HTMX swaps).
- **Exports**: CSV via `config/export.py`; PDF via `config/pdf_export.py` (reportlab platypus) with section types: "info", "table", "text"
- **Button colours**: Detail pages: purple (PDF), blue (Edit), green (Complete), red (Delete). List pages: purple (export), blue (+ New).
- **Dropdown menus**: Multi-type asset tabs use `[data-dropdown]` toggle pattern (`toggleDropdown()`/`closeAllDropdowns()` in `asset_list.html`); single-type tabs render flat buttons instead.
- **Currency**: `django.contrib.humanize` `intcomma` filter everywhere
- **Mobile responsive**: All list pages mobile-optimized. Pattern: view toggle in header (icon-only on mobile via `hidden sm:inline`), Export CSV hidden on mobile (`hidden sm:inline-block`), 2-col grid for dropdowns (`grid grid-cols-2 sm:flex`), collapsible Filters panel with badge count, table rows hide columns on mobile and show `sm:hidden` metadata line in title cell, tabs collapse to `<select>` dropdown on mobile (`sm:hidden` / `hidden sm:flex`)
- **Inline editing on detail pages**: Tasks and notes use HTMX display/editor partial swaps. Pattern: `_detail_title_display.html` + `_detail_title_editor.html` (pencil icon → input + Save/Cancel). Description uses click-to-edit with textarea. Metadata uses badge row → dropdown row swap. Breadcrumb updates via `HX-Trigger` event.
- **Form layout**: Explicit field rendering (not `{% for field in form %}` loops) for precise layout control. Short fields (dropdowns, dates) in responsive 2-col grids (`grid grid-cols-1 sm:grid-cols-2 gap-4`); title/description full-width. Note form uses 3-col grid for Date/Type/Folder.
- **Colored pill toggles**: Used for tag selection (forms + filters), note type filters, and task list filters (status/direction/type). Pattern: hidden `<input type="checkbox">` + styled `<span>` with `data-active-bg`/`data-active-text`/`data-active-border` attributes; JS `onchange` handler toggles CSS classes.

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
- Through models: `PropertyOwnership`, `InvestmentParticipant`, `LoanParty`, `VehicleOwner`, `AircraftOwner` — each stores percentage, role, and notes; all have `unique_together` on (asset FK, stakeholder FK); `PolicyHolder` also has `unique_together`
- HTMX inline add/delete on asset detail pages AND stakeholder detail page (mirror pattern for all 5 through models + PolicyHolder)
- Inline notes: `_inline_notes.html`/`_inline_notes_form.html` shared partials; click-to-edit, save/cancel/clear; `get_notes_url()`/`get_notes_id()` on each through model
- Stakeholder detail "All Connections" tabs: Stakeholders, Properties, Investments, Loans, Vehicles, Aircraft, Insurance, Legal, Tasks, Notes, Cash Flow
- `StakeholderVehicleForm`, `StakeholderAircraftForm`, `StakeholderPolicyForm` in `stakeholders/forms.py`
- Create forms include optional "Initial Owner/Participant" fields, hidden on edit via `get_form()` field deletion

### Insurance Policy Tracking
- `InsurancePolicy`: `policy_type` (DB-backed ChoiceOption), `status` (hardcoded: active/expired/cancelled/pending), carrier/agent FKs → Stakeholder
- `PolicyHolder` through model (role, notes — no percentage); `covered_properties` M2M → RealEstate, `covered_vehicles` M2M → Vehicle, `covered_aircraft` M2M → Aircraft
- Integrated into unified `/assets/` page as "policies" asset type; "Insurance" seed tab
- HTMX inline policyholder add/delete on detail page; inline status editing on list
- Asset detail pages: HTMX inline policy link/unlink (`AssetPolicyLinkForm`); shared partials `_asset_policy_form.html`/`_asset_policy_list.html`; "+ New Policy" pre-selects asset via query param
- Graph shows octagon nodes (prefix `ins-`) for carrier, agent, and policyholder edges
- Notes link via `related_policies` M2M

### Loan Tracking
- `Loan` has FKs to all 4 asset types: `related_property`, `related_investment`, `related_vehicle`, `related_aircraft` (all SET_NULL, nullable)
- `is_hard_money` BooleanField + `default_interest_rate` DecimalField for hard money loans; orange "HM" badge on list/detail
- Asset detail pages: HTMX inline loan link/unlink (`AssetLoanLinkForm`); shared partials `_asset_loan_form.html`/`_asset_loan_list.html`; "+ New Loan" pre-selects asset via query param
- Same pattern as policy link/unlink but uses FK (set `loan.related_X = asset` / `= None`) instead of M2M `.add()`/`.remove()`
- Unlink views verify FK ownership before clearing (prevents unlinking a loan that belongs to a different asset)
- Asset list rows show orange loan count/balance subtitle via `Count`/`Sum` annotations

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
- `SubTask`: HTMX add/toggle/delete; progress bar on detail, `N/M` annotations on list/kanban; clickable counter on list expands inline toggle-only panel (`_inline_subtask_panel.html`) with OOB counter swap
- Recurring: `is_recurring` + `recurrence_rule`; `create_next_recurrence()` called in all 4 completion paths
- Meeting: `task_type="meeting"` + optional `due_time` TimeField; `QuickTaskForm` also supports meetings (type select + conditional time field)
- Kanban: SortableJS drag-and-drop, `kanban_update` endpoint
- Inline list edit: clickable status/priority badges cycle values; inline date picker; `_task_row.html` partial for single-row re-render
- Inline detail edit: title (pencil → input), description (click → textarea), metadata (badges → dropdowns) — partials in `tasks/partials/_detail_*_display.html` / `_detail_*_editor.html`; breadcrumb synced via `HX-Trigger: updateTaskBreadcrumb`
- Note indicator: `note_count` annotation on list queryset; icon + count link on list rows (links to `#notes-section` on detail); count badge in detail Notes section header

### Calendar
- FullCalendar v6.1.11, dark theme CSS overrides in `calendar.html`; JSON events from `calendar_events()` in `dashboard/views.py`
- Event types: task (priority-colored), meeting (blue), payment (red), followup (amber), legal (purple), hearing (violet), contact (cyan)
- Client-side filter toggles: `cal-toggle` buttons with `hiddenTypes` object; mobile collapsible filter panel
- `dayMaxEvents: isMobile ? 3 : 4` — desktop shows "+N more" overflow link
- Meetings with `due_time` rendered as timed events (`allDay: false`); week view shows them in time slots
- Week view: `slotMinTime: '07:00:00'`, `slotMaxTime: '22:00:00'`, `expandRows: true` (hides dead hours)
- Direction arrows: `↗` (outbound) / `↙` (inbound) replace old `[OUT]`/`[IN]` text prefixes
- Payment amounts: `$2,500 — Loan Name` when `monthly_payment` exists; falls back to `Payment: Loan Name`
- Hover tooltips: `info.el.title = info.event.title` in `eventDidMount`
- Click-to-create: desktop `dateClick` → `/tasks/create/?due_date=YYYY-MM-DD`; week view also passes `due_time` + `task_type=meeting`
- `TaskCreateView.get_initial()` accepts `due_date`, `due_time`, `task_type` query params

### Quick Capture (mobile-first)
- Sidebar "Quick Note" button → HTMX modal (`notes:quick_capture`); `QuickNoteForm` in `notes/forms.py`
- Content-first layout: content textarea above title; title optional (auto-generated from first ~50 chars of content)
- Auto-expanding textarea: JS `oninput` resize up to 40% viewport height; auto-focus on open
- Date + Type stacked on mobile (`grid-cols-1 sm:grid-cols-2`); date wrapped in `w-fit` to prevent stretching
- "More options" collapsible: folder, tag pills (colored `toggleTypePill` pattern), multi-select stakeholder, task
- Stakeholder field is `ModelMultipleChoiceField` (multi-select, adds to `note.participants`)
- No flex layout on form — simple `space-y-3` to prevent content collapsing when "More options" opens
- Auto-title: view does `commit=False`, generates title from `content.split("\n", 1)[0][:50]`, then `save()` + `save_m2m()`

### Notes System
- 3 view modes: cards, list, timeline — `get_template_names()` routes by `view` param
- `Tag` (name, slug, color) + `Folder` (name, color, sort_order); `notes/templatetags/tag_colors.py` maps color names → CSS class string literals (for Tailwind scanning)
- Template tags: `tag_classes(color)`, `folder_classes(color)`, `note_type_classes(note_type)` — all return `{bg, text, border}` dict for colored pill rendering
- Note type filter pills on list page: colored pill toggles (not plain checkboxes); `toggleTypePill` JS; `NOTE_TYPE_COLOR_MAP` for 7 types including `text_message`
- Folder tab bar with inline "Manage Folders" panel; `HX-Trigger: foldersChanged` auto-refreshes tabs
- Inline detail edit: title (pencil → input), content (click → EasyMDE textarea), metadata (badges → dropdowns + tag pills) — partials in `notes/partials/_detail_*_display.html` / `_detail_*_editor.html`
- Note form: explicit field layout with 3-col grid (Date/Type/Folder); tags rendered as horizontal colored pills (not CheckboxSelectMultiple); `selected_tag_pks` property on form
- Markdown: `render_markdown` template filter with `nl2br` + blank-line preprocessor; `prose-markdown` CSS in `input.css`

### Notifications & Email
- `tasks/notifications.py` — 3 django-q2 scheduled functions: overdue tasks, upcoming reminders, stale follow-ups; overdue/reminder notifications include subtask progress (`checklist N/M`) when incomplete
- `EmailSettings` singleton (pk=1) stores SMTP config; `dashboard/email.py` provides connection helpers
- `Notification` model with levels (info/warning/critical); sidebar bell with HTMX badge polling (60s)

### Scheduled Tasks (Django-Q2)
All registered via `python manage.py setup_schedules`; executed by `python manage.py qcluster`:

| Task | Frequency | Function |
|------|-----------|----------|
| Check Overdue Tasks | Daily | `tasks.notifications.check_overdue_tasks` |
| Check Upcoming Reminders | Hourly | `tasks.notifications.check_upcoming_reminders` |
| Check Stale Follow-ups | Daily | `tasks.notifications.check_stale_followups` |
| Automated Backup | Configurable (Settings UI) | `dashboard.backup_task.run_backup` |

- Backup schedule is configurable via `/settings/backups/` — `BackupSettings` singleton (frequency, time, retention count, enabled/disabled)
- Saving backup config from the UI immediately syncs the live `Schedule` record (no restart needed)
- The 3 notification schedules are hardcoded (not user-configurable)

### Infrastructure
- **SQLite**: WAL mode + pragmas via `connection_created` signal in `dashboard/apps.py` (weak=False). Indexes on frequently-filtered fields.
- **Backup**: `sqlite3.backup()` API + media → `.tar.gz`; configurable automated backup via `BackupSettings` singleton; web UI at `/settings/backups/` for schedule config + manual create/download/restore/upload
- **Docker**: Single container — Gunicorn (2 workers, 30s timeout) foreground + qcluster background. `entrypoint.sh` handles migrate/collectstatic/createsuperuser.
- **Tailwind**: Standalone CLI v3.4.17; config in `tailwind.config.js`, output at `static/css/tailwind.css`. Rebuild after adding/changing classes: `make tailwind-build`
- **Environment**: `settings.py` uses `os.environ.get()` with dev-friendly fallbacks; production security headers gated behind `not DEBUG`
- **Sample data**: `SampleDataStatus` singleton tracks loaded PKs in `manifest` JSONField; remove deletes only manifested PKs in reverse-dependency order

### E2E Browser Testing (Playwright)
- `e2e/base.py`: `PlaywrightTestCase` extends `StaticLiveServerTestCase` — spins up real HTTP server on random port, serves static files
- Browser shared per class (expensive to launch), fresh page per test for isolation; `url()` helper constructs full URL
- `requirements-dev.txt` for dev-only dependencies (playwright); install browsers via `playwright install chromium`
- Tests verify actual DOM state after HTMX swaps, JS toggle functions, and responsive behavior
- Test files: `test_task_inline.py` (detail editing), `test_task_list.py` (list + form), `test_note_inline.py` (detail editing), `test_note_list.py` (list + form), `test_subtasks.py` (checklist interactions), `test_calendar.py` (calendar events, filters, click-to-create)
- `setUp()` calls `invalidate_choice_cache()` to avoid stale ChoiceOption cache across test classes
- EasyMDE hides `<textarea>` — tests use `page.set_viewport_size({"width": 375, ...})` for mobile to skip EasyMDE

### Important Gotchas
- Dashboard views use lazy imports inside functions
- Forms use `__init__` override for dynamic widget/choices setup
- `Relationship`/`ContactLog`/`FollowUp` FKs use SET_NULL (not CASCADE) to prevent data loss on stakeholder deletion
- Tag/AssetTab slug collision: uniqueness loop generates `base-slug-1`, `-2`, etc.
- `bulk-actions.js` looks up `#select-all` dynamically and uses fully delegated change events (works after HTMX swaps)
- `switchView()` uses `source: form` (not `values: getFilterValues()`) for proper multi-select serialization
- **Timezone**: `TIME_ZONE = 'America/Los_Angeles'` with `USE_TZ = True`. Always use `timezone.localdate()` (not `date.today()`) and `timezone.localdate(dt)` (not `dt.date()`) when comparing dates from DateTimeFields — UTC vs local mismatch causes wrong results
- Django test runner uses in-memory SQLite — WAL mode returns 'memory', not 'wal'
- Backup/restore tests must use temp file-based DBs, not the in-memory test DB
- E2E tests need `DJANGO_ALLOW_ASYNC_UNSAFE=true` (set in `e2e/base.py` setUp) for Playwright + LiveServerTestCase
- EasyMDE textarea hiding: in e2e tests, use mobile viewport or target `.EasyMDEContainer` instead of the hidden `<textarea>`

## Next Steps
- User authentication (currently no login required — fine for single-user VPN access)
