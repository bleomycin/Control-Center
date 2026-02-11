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
| **dashboard** | ChoiceOption, EmailSettings, Notification, SampleDataStatus | Master homepage, global search, activity timeline, calendar view, email/SMTP settings, notification center, editable choice management, settings hub, sample data toggle |
| **stakeholders** | Stakeholder, Relationship, ContactLog | CRM — entity profiles, trust/risk ratings, relationship mapping, contact logs; firm/employee hierarchy via self-FK `parent_organization` |
| **assets** | RealEstate, PropertyOwnership, Investment, InvestmentParticipant, Loan, LoanParty | Asset & liability tracker — properties, investments, loans with payment schedules; M2M through models for multi-stakeholder ownership with percentages and roles |
| **legal** | LegalMatter, Evidence | Legal matter management — case status, attorneys (M2M), evidence, related stakeholders/properties |
| **tasks** | Task, FollowUp, SubTask | Task system — deadlines, priorities, status tracking, follow-up/stale outreach workflows; bidirectional direction (personal/outbound/inbound); multi-stakeholder M2M with grouped dropdown; meeting task type with optional time and meeting-to-notes workflow; kanban board view with drag-and-drop; quick inline status/priority/date editing; follow-up timeline visualization; recurring tasks with auto-creation on completion; subtask checklists with progress tracking; stakeholder filter dropdown; grouped table view (by status/priority/due date/stakeholder); stale follow-up indicators |
| **cashflow** | CashFlowEntry | Cash flow — actual + projected inflows/outflows with category filtering |
| **notes** | Note, Attachment, Link | Notes/activity database — discrete searchable records linked to entities via M2M relations; external URL links with descriptions |

## Key Patterns

- **Views**: CBVs for CRUD, function views for HTMX partials (contact logs, follow-ups, evidence, attachments, quick capture)
- **Forms**: `TailwindFormMixin` in `legacy/forms.py` auto-applies dark-mode Tailwind classes to all widget types
- **HTMX**: Live search/filter on list pages (`hx-get` with `delay:300ms`), inline add/delete for child records, modal quick capture, global search with live results
- **Templates**: `base.html` includes sidebar + modal container; apps use `partials/` subdirectories for HTMX fragments
- **Cross-linking**: Detail pages show related records from all other modules; all models have `get_absolute_url()`
- **Delete confirmation**: Shared `partials/_confirm_delete.html` template used by all DeleteViews
- **CSRF for HTMX**: Set via `hx-headers` on `<body>` element
- **FKs**: `SET_NULL` for optional, `CASCADE` for required; string references for cross-app FKs
- **Admin**: Inlines for child records, `filter_horizontal` for M2M fields
- **CSV Export**: Generic `legacy/export.py` utility; export views on all list pages (stakeholders, tasks, cashflow, notes, legal, real estate, investments, loans)
- **PDF Export**: Generic `legacy/pdf_export.py` using reportlab platypus; `render_pdf(request, filename, title, subtitle, sections)` with section types: "info" (key-value rows), "table" (headers + rows), "text" (paragraphs). PDF views on all detail pages.
- **Charts**: Chart.js 4.x on cash flow page — monthly trend bar chart + category breakdown doughnut chart. JSON endpoint at `cashflow/charts/data/` using `TruncMonth` + `Sum` aggregation.
- **Liquidity Alerts**: `cashflow/alerts.py` — `get_liquidity_alerts()` returns alert dicts with 3 triggers: net negative monthly flow, large upcoming loan payments (>$5k/30 days), projected shortfall. Displayed via `partials/_alerts.html` on dashboard and cash flow page (context-aware: hides "View Cash Flow" link when already on that page). Dismissable via `static/js/dismiss-alerts.js` — stores dismissed alert keys in `sessionStorage` (resets on new browser session).
- **Currency formatting**: `django.contrib.humanize` `intcomma` filter for comma-separated dollar values across all templates
- **Email Notifications**: `tasks/notifications.py` — 3 scheduled functions via django-q2 (overdue tasks, upcoming reminders, stale follow-ups). SMTP config read from DB at runtime via `dashboard/email.py` helpers; master on/off switch via `EmailSettings.notifications_enabled`. Also creates in-app `Notification` records.
- **Email Settings**: `dashboard/models.py` — `EmailSettings` singleton (pk=1) stores SMTP config in DB. UI at `/settings/email/` with HTMX test-email button. `dashboard/email.py` provides `get_smtp_connection()`, `get_notification_addresses()`, `notifications_are_enabled()`. Admin registered with singleton enforcement (no add if exists, no delete)
- **Breadcrumbs**: All detail/form pages have `Home / Module / Record` breadcrumb navigation
- **Notifications**: `dashboard/models.py` — `Notification` model with levels (info/warning/critical). Sidebar bell icon with HTMX badge polling (every 60s). Full list page at `/notifications/`. Auto-created by scheduled task functions alongside emails.
- **Relationship Graph**: Cytoscape.js network visualization on stakeholder detail page (500px). Shows ALL entity types: stakeholders (circles), properties (rectangles), investments (diamonds), loans (triangles), legal matters (hexagons), tasks (stars) — all color-coded. Edges display role and ownership percentage (e.g., "Co-owner (50%)"). JSON endpoint returns 1st + 2nd degree relationship data. `cose` layout, dark theme, clickable nodes. Node IDs prefixed by type (s-, p-, i-, l-, m-, t-).
- **Advanced Filtering**: All list pages use `<form id="filter-form">` wrapping all inputs. Sortable column headers with `sort`/`dir` query params and arrow indicators. Date range `<input type="date">` filters. Multi-select status/type via checkbox groups with `getlist()`.
- **Bulk Operations**: All list pages have select-all checkbox, per-row checkboxes, and a sticky bulk action bar (hidden until items selected). `static/js/bulk-actions.js` handles select-all toggle, count tracking, and bar visibility. Bulk delete (with confirmation modal), bulk export CSV, and bulk mark-complete (tasks only) views per app.
- **Button colour scheme**: Detail pages use purple (PDF/export), blue (Edit), green (Complete), red (Delete). List pages use purple for export buttons, blue for "+ New".
- **Environment config**: `settings.py` uses `os.environ.get()` with dev-friendly fallbacks for SECRET_KEY, DEBUG, ALLOWED_HOSTS, DATABASE_PATH, EMAIL_BACKEND — local dev works without `.env`. SECRET_KEY raises `ValueError` if unset when `DEBUG=False`. Production security headers (SSL redirect, HSTS, secure cookies) gated behind `not DEBUG`.
- **Tailwind CSS**: Standalone CLI binary (v3.4.17, no Node.js). Config in `tailwind.config.js`, source in `static/css/input.css`, output at `static/css/tailwind.css`. Local dev: `make tailwind-install && make tailwind-watch`. Docker builds CSS during image build and discards the binary. After adding/changing Tailwind classes, rebuild with `make tailwind-build`.
- **Static files**: WhiteNoise serves static files in production (`CompressedManifestStaticFilesStorage` when `DEBUG=False`); standard Django staticfiles in dev
- **Media serving**: Unconditional `re_path` in `urls.py` (no Nginx needed for single-user app)
- **Editable Choices**: `dashboard/models.py` — `ChoiceOption` model stores dropdown options in DB (replaces hardcoded `choices=` on model fields). 4 categories: `entity_type` (Stakeholder), `contact_method` (ContactLog/FollowUp), `matter_type` (LegalMatter), `note_type` (Note). `dashboard/choices.py` provides `get_choices(category)` (cached DB lookup returning Django choice tuples), `get_choice_label(category, value)` (display label with raw-value fallback), `invalidate_choice_cache()`. Template filter: `{% load choice_labels %}` then `{{ value|choice_label:"category" }}`. Forms load choices dynamically in `__init__`. Settings UI at `/settings/choices/` with HTMX add/edit/toggle-active/reorder per category. Seed data in squashed `0001_initial.py` migration. Status/workflow fields (task status, priority, loan status, etc.) are NOT included — their values are referenced in business logic.
- **Multi-Stakeholder Ownership**: Properties, investments, and loans support multiple stakeholders via M2M through models (`PropertyOwnership`, `InvestmentParticipant`, `LoanParty`). Each link stores ownership percentage and role. Detail pages show all stakeholders with color-coded percentages (green for properties, purple for investments, orange for loans). HTMX inline add/delete on all 3 asset detail pages (same pattern as contact logs) AND on stakeholder detail page (mirror pattern: stakeholder fixed, asset dropdown). Admin also has inline editors. Create forms include optional "Initial Owner/Participant" fields (stakeholder, role, %) so first relationship can be set during creation — hidden on edit views via `get_form()` field deletion.
- **Loan-Asset Linking**: `Loan.related_property` (FK→RealEstate, SET_NULL) and `Loan.related_investment` (FK→Investment, SET_NULL) link loans to the assets they finance. Property and investment detail pages show "Loans" section with lender names, balance, rate, and monthly payment. Loan detail shows linked property/investment with clickable links. Loan create form includes Property and Investment dropdowns; query param pre-fill (`?property=<pk>`, `?investment=<pk>`) supported from asset detail "+ Add Loan" links.
- **Stakeholder Detail Tabs**: Tabbed "All Connections" interface replaces individual preview cards on stakeholder detail page. 8 tabs with count badges showing all related entities (no 5-item limits). Cash flow entries included. Zero information redundancy with the relationship graph. Properties/Investments/Loans tabs use through-model querysets to display role, percentage, and inline HTMX add/delete (forms in `stakeholders/forms.py`: `StakeholderPropertyForm`, `StakeholderInvestmentForm`, `StakeholderLoanForm`; partials prefixed `_sh_`).
- **Follow-Up Reminders**: `FollowUp` model has `reminder_enabled` (default=False) opt-in toggle and `follow_up_days` (default=3) for per-follow-up configurable reminder windows. `is_stale` property only fires when `reminder_enabled=True`. UI shows: green (responded), red "Overdue" (stale + reminder on), yellow "Awaiting" (pending + reminder on), gray "no reminder" (pending + reminder off). HTMX "Mark Responded" button on pending follow-ups. Inline HTMX edit on each follow-up (loads form into `#followup-form-container`, same pattern as add). Task create form has optional inline follow-up section with separate "Enable reminder" checkbox. `check_stale_followups()` filters on `reminder_enabled=True` and excludes completed tasks.
- **Follow-Up Response Notes**: `FollowUp.response_notes` TextField captures what the person said when marking responded. "Mark Responded" button uses `hx-get` to load inline form (`_followup_respond_form.html`) into `#followup-form-container` with optional notes textarea. Undo preserves `response_notes`. Responded follow-ups with notes show "Create Note" link that pre-fills `NoteCreateView` via query params (`title`, `content`, `date`, `task`, `stakeholder`). PDF export appends response notes to Notes column. `NoteCreateView.get_initial()` reads query params for pre-fill.
- **Multi-Stakeholder Tasks**: `Task.related_stakeholders` M2M field (plain, no through model — direction field handles semantics). `_grouped_stakeholder_choices()` in `tasks/forms.py` builds `<optgroup>`-grouped `SelectMultiple` widget (size=5) ordered by entity type label. 3-step migration (0003 add M2M, 0004 data migrate FK→M2M, 0005 remove FK). `related_name="tasks"` preserved for reverse lookups. Follow-up auto-create uses `task.related_stakeholders.first()`. CSV export joins M2M names via custom `_stakeholder_names` attr. Table rows show first stakeholder + "+N" count badge for multiple. Detail page shows comma-separated linked names. Notifications join all stakeholder names.
- **SQLite Hardening**: `DashboardConfig.ready()` in `dashboard/apps.py` sets pragmas via `connection_created` signal — WAL mode, `synchronous=NORMAL`, `busy_timeout=5000`, `cache_size=-20000` (20MB), `foreign_keys=ON`. WAL mode eliminates reader/writer blocking between Gunicorn workers and qcluster.
- **Database Indexes**: `db_index=True` on frequently-filtered fields: `Stakeholder.entity_type`/`name`, `Task.status`/`due_date`, `CashFlowEntry.date`/`entry_type`, `LegalMatter.status`, `Note.date`.
- **Backup/Restore**: `python manage.py backup` uses Python's `sqlite3.backup()` API for safe live-DB snapshots (handles WAL mode), copies `media/`, packages into timestamped `.tar.gz`. `--keep N` prunes old backups. `python manage.py restore <archive>` validates, replaces DB + media, runs `migrate`. `dashboard/backup_task.py` provides django-q2 callable (`run_backup`) for automated daily backups (keeps 7). Backup dir: `BACKUP_DIR` env var or `BASE_DIR/backups`.
- **Docker**: Single container runs Gunicorn (foreground, 2 workers, 30s timeout) + qcluster (background). `entrypoint.sh` handles migrate, collectstatic, createsuperuser, sample data loading. Named volumes for SQLite (`legacy-data`), media (`legacy-media`), and backups (`legacy-backups`)
- **Firm/Employee Hierarchy**: `Stakeholder.parent_organization` self-FK (SET_NULL). Firms have `entity_type="firm"`. Detail page shows Team Members section with count and "Add Employee" link. Employee detail links back to firm. Graph shows firm→employee + sibling edges. Form filters `parent_organization` queryset to firms. CSV/PDF exports include firm. Global search includes `parent_organization__name`. Stakeholder table rows link Organization column to firm. "firm" entity type seeded via squashed `dashboard/0001_initial.py` and `choice_seed_data.py`.
- **Bidirectional Task Direction**: `Task.direction` CharField with choices: `personal` (default), `outbound` ("I asked them"), `inbound` ("they asked me"). NOT a DB-backed ChoiceOption (values in business logic). Cyan badges/arrows for outbound, amber for inbound. Direction-aware stakeholder label on detail ("Requested From"/"Requested By"). Follow-up section hidden for inbound tasks. Direction filter checkboxes on list page. Calendar event titles prefixed `[OUT]`/`[IN]`. Notification messages prefixed `[OUTBOUND]`/`[INBOUND]`. Stakeholder detail Tasks tab has convenience links: "+ Request from them" (outbound) and "+ They requested" (inbound) with prefilled direction + stakeholder.
- **Stakeholder List Tabs**: 7-tab navigation on stakeholder list page: All (default, excludes employees), Firms & Teams (card layout with nested employees), Attorneys, Lenders, Business Partners, Advisors, Other. `TAB_DEFINITIONS` dict in `stakeholders/views.py` defines tab keys, labels, and entity type filters. `tab` query param drives filtering; HTMX swaps `#stakeholder-content` div. Firms tab uses `_firm_cards.html` partial (card per firm with employee rows, "+ Add Employee" link). Table tabs reuse `_stakeholder_table_rows.html` inside `_tab_content.html` wrapper. Tab counts shown as badges. Search on Firms tab matches firm name OR employee name via `Q` objects. Type filter dropdown only shown on All tab.
- **Notes List Cards**: Card-based layout replaces table on `/notes/`. Each card shows: color-coded type badge with icon, date, combined attachment+link count (paperclip), content preview (`truncatewords:40` + `line-clamp-2`), and linked entity chips (indigo=participants, blue=stakeholders, green=properties, amber=legal, yellow=tasks). `NoteListView` uses `prefetch_related` for all 5 M2M fields + `annotate(attachment_count=Count("attachments", distinct=True), link_count=Count("links", distinct=True))`. Search matches `title` and `content`. Stakeholder filter dropdown filters by `participants` OR `related_stakeholders`. Sort toolbar above cards (date/title/type). `_note_cards.html` partial swapped into `#note-card-list` div. `bulk-actions.js` handles card-based afterSwap reset.
- **External Links on Notes**: `Link` model in `notes/models.py` — `note` FK (CASCADE, `related_name="links"`), `url` URLField(max_length=2000), `description` CharField(255, required), `created_at`. HTMX inline add/edit/delete mirrors attachment pattern (`link_add`/`link_edit`/`link_delete` views, `_link_form.html`/`_link_list.html` partials). `_link_form.html` reused for add and edit via parameterized `form_url` + `edit_mode` flag (button text switches "Add Link"/"Save"). Edit button on each link row loads pre-populated form into `#link-form-container`. Note detail page shows combined "Attachments & Links" section with separate "+ Add Link" and "+ Add File" buttons, "Links" sub-header. Links display external-link icon + clickable description (`target="_blank"`). `LinkForm` in `notes/forms.py` with URL/description placeholders. `LinkInline` in admin. PDF export includes Links table section. Note cards badge shows combined `attachment_count + link_count`.
- **Markdown Editor**: EasyMDE 2.20 (CDN, loaded only on note form pages) with dark theme CSS overrides. Toolbar: bold, italic, strikethrough, H1-H3, bullet/numbered/check lists, links, blockquotes, code, preview, side-by-side. Content stored as plain markdown in existing `TextField` — no model/migration changes. `dashboard/templatetags/markdown_filter.py` provides `render_markdown` filter using Python `markdown` package with extensions: `nl2br` (backwards compat — existing plain-text notes render correctly), `fenced_code`, `tables`, `sane_lists`. Preprocessor inserts blank lines before block-level elements (lists, headings, blockquotes) so `nl2br` doesn't prevent parsing. Detail page renders via `{{ note.content|render_markdown }}` inside `prose-markdown` div. Custom `prose-markdown` CSS in `static/css/input.css` styles all markdown elements (disc/decimal list markers, headings, blockquotes with left border, code blocks, tables, links) with dark theme colors — needed because Tailwind standalone CLI has no `@tailwindcss/typography` plugin. PDF export strips markdown syntax via `_strip_markdown()` helper in `notes/views.py`. Search/CSV export unaffected (markdown is plain text). Quick capture modal keeps plain textarea for speed.
- **Settings Hub**: Consolidated settings page at `/settings/` with 4 cards: Sample Data, Manage Choices, Email Settings, Django Admin. Sidebar reduced from 4 bottom links to 2 (Notifications + Settings). `settings_hub` view in `dashboard/views.py`.
- **Sample Data Toggle**: `SampleDataStatus` singleton model (pk=1) in `dashboard/models.py` with `is_loaded` BooleanField, `manifest` JSONField (stores PKs of all sample objects by model label), `loaded_at` DateTimeField. `load_sample_data` command saves manifest after creating objects; idempotency guard skips if already loaded. HTMX load/remove buttons on settings hub. `sample_data_remove` view reads manifest and bulk-deletes by PK in reverse-dependency order (children before parents) — user-created data is never touched. Admin registered with singleton enforcement (same pattern as `EmailSettings`).
- **Kanban Board View**: Table/Board toggle on task list page. Board shows 4 columns (Not Started, In Progress, Waiting, Complete) with draggable task cards. SortableJS (CDN) enables drag-and-drop between columns — each drop POSTs to `kanban-update` endpoint. `TaskListView` disables pagination for board view (`get_paginate_by` returns `None`). `get_context_data` builds `kanban_columns` list by grouping tasks by status. HTMX filter form works for both views — `hx-target="#task-content"` wrapper div. View mode stored in hidden `<input name="view">`. `switchView()` JS function toggles buttons, loads SortableJS dynamically, fires HTMX request, updates URL. `static/js/kanban.js` initializes Sortable on `.kanban-column` elements with `group: "kanban"`, manages empty placeholders and count badges. New templates: `_kanban_board.html` (4-column grid), `_kanban_card.html` (card with priority bar, badges, stakeholder).
- **Quick Inline Edit**: Clickable status/priority badges in task table rows cycle through values via HTMX POST to `inline_update` endpoint. Status cycles: not_started→in_progress→waiting→complete→not_started. Priority cycles: low→medium→high→critical→low. Due date cell shows native date picker on click (`.showPicker()`). `inline_update` view validates field name against allowlist and value against model choices. `_task_row.html` extracted from `_task_table_rows.html` for single-row rendering — used by `inline_update`, `toggle_complete` (table context), and the table rows loop. `toggle_complete` returns full row for table context, badge-only for detail context (via `context=detail` POST param). Each `<tr>` has `id="task-row-{{ task.pk }}"` for targeted HTMX swaps.
- **Follow-up Timeline**: Vertical timeline replaces flat list on task detail page. Left-aligned with `pl-8` indent, vertical line via `absolute left-[15px]` div, and colored status dots positioned on the line. Dot colors: green+checkmark (responded), red (overdue/stale), yellow (awaiting with reminder), gray (no reminder). Each follow-up in a bordered card with `bg-gray-800/50`. Pure template/CSS restyle of `_followup_list.html` — all HTMX interactions (add/edit/respond/undo/delete) unchanged.
- **Stakeholder Filter on Tasks**: `<select name="stakeholder">` dropdown on task list page. `TaskListView.get_queryset()` filters by `related_stakeholders__pk` with `.distinct()`. Context provides `stakeholders` queryset + `selected_stakeholder` for re-selection. Follows same pattern as notes list stakeholder filter.
- **Stale Follow-up Indicator**: `Task.has_stale_followups` property checks for overdue follow-ups (optimized: uses prefetch cache when available, else queries only `reminder_enabled=True, response_received=False`). Red dot (`bg-red-500`) displayed in `_task_row.html` and `_kanban_card.html` title area. `TaskListView` prefetches `follow_ups` alongside `related_stakeholders`.
- **Grouped Table View**: `_build_grouped_tasks(tasks, group_by)` helper in `tasks/views.py` supports 4 modes: `status` (4 fixed groups), `priority` (4 fixed groups), `due_date` (5 buckets: Overdue/Today/This Week/Later/No Date — empty omitted), `stakeholder` (dynamic groups + "No Stakeholder"). Group dropdown `<select name="group">` in filter form. `_grouped_table_view.html` partial uses collapsible `<details open>` per group with count badge. Pagination disabled for grouped view. HTMX returns grouped partial when `group` param present.
- **Subtasks/Checklists**: `SubTask` model in `tasks/models.py` — `task` FK (CASCADE), `title`, `is_completed` (default=False), `sort_order`, `created_at`. Ordering by `sort_order, created_at`. `SubTaskForm` with title-only field. 3 HTMX views: `subtask_add` (POST creates, returns list), `subtask_toggle` (POST flips `is_completed`), `subtask_delete` (POST removes). `_subtask_list.html` partial: green checkbox toggles, `line-through` on completed, hover-reveal delete button, always-visible inline add form at bottom. Detail page: "Checklist" section with progress bar (`{% widthratio %}`) and `N/M` count. List rows: `subtask_done/subtask_count` text after title (via `Count` annotations on queryset). Kanban cards: thin green progress bar. `SubTaskInline` in admin. PDF export: "Checklist" table section (Item + Status). CSV: `_subtask_progress` field ("3/5" format).
- **Recurring Tasks**: `Task.is_recurring` BooleanField (default=False) + `Task.recurrence_rule` CharField (choices: daily/weekly/biweekly/monthly/quarterly/yearly). `RECURRENCE_CHOICES` on model (NOT DB-backed ChoiceOption — values in business logic). `compute_next_due_date()` method: daily/weekly/biweekly via `timedelta`; monthly/quarterly via month arithmetic with `calendar.monthrange` end-of-month clamping; yearly with Feb 29→28 fallback. `create_next_recurrence()` copies title, description, due_date (computed), due_time, priority, task_type, direction, related_legal_matter, related_property, is_recurring, recurrence_rule + M2M stakeholders; does NOT copy follow-ups, subtasks, reminder_date, completed_at. `_handle_recurring_completion(task)` helper called in 4 completion paths: `toggle_complete`, `kanban_update`, `inline_update`, `bulk_complete` (changed from `queryset.update()` to per-object loop). Form: `is_recurring` checkbox + `recurrence_rule` dropdown with JS toggle (hidden until checked). Validation: recurring requires both rule and due_date. Template indicators: indigo &#x21bb; icon in rows/cards/detail badge area. PDF/CSV: recurrence info column. Migration: `0007_task_recurrence_subtask`.
- **Meeting Tasks**: `"meeting"` added to `TASK_TYPE_CHOICES`. `due_time` optional TimeField (null/blank) on Task — separate from `due_date` DateField (zero blast radius on existing code). `is_meeting` property returns `self.task_type == "meeting"`. `scheduled_datetime_str` property returns ISO datetime string when time set, date-only string otherwise. Form: `task_type` rendered before `due_date`; `due_date` and `due_time` side-by-side in flex row (time hidden until "meeting" selected). JS changes date label to "Meeting date" for meetings. `clean()` rejects time without date. Detail page: "Meeting Time" label with blue time display, blue-bordered "Meeting Notes" section with prominent "+ Add Meeting Notes" button (pre-fills note creation with title, note_type=meeting, task, first stakeholder, full datetime). Table rows: styled `MTG` pill badge (bg-blue-900/50), time in due column. Task type filter checkboxes (One-Time/Reference/Meeting). Sortable "Created" column (hidden xl, `created_at` in `ALLOWED_SORTS`). Calendar: meetings get distinct blue color (`#3b82f6`, contacts use cyan `#06b6d4`), `display: "block"` for colored bar rendering, `extendedProps.type = "meeting"`. Interactive toggle buttons per event type (All, Tasks, Meetings, Payments, Follow-ups, Legal, Hearings, Contacts) with "All" toggle for quick isolation. Timeline: time appended to meeting task summaries. Dashboard deadlines: blue color/badge for meetings. CSV/PDF: "Time" column/row. Notifications: `[MEETING]` prefix. Admin: `due_time` in `list_display`. `NoteCreateView.get_initial()` parses date strings via `fromisoformat()` for robust datetime-local pre-fill.

## Current Status

### Completed
- All models and migrations
- Admin interfaces for all models
- Full frontend: dark sidebar command-center layout with Tailwind CSS + HTMX
- All CRUD pages for all 7 modules (~70 templates)
- Dashboard with 4 panels + cash flow summary cards + mixed activity feed
- HTMX-powered search/filter on all list pages with loading spinners
- Inline child record management (contact logs, follow-ups, evidence, attachments)
- Quick capture modals from sidebar (Quick Note + Quick Task)
- Cross-linked detail pages showing related records from other modules
- Responsive mobile layout (hamburger sidebar)
- Comprehensive sample data (management command: `load_sample_data`)
- ngrok tunnel for remote demo access
- Global search across all modules (sidebar search form + `/search/` page with HTMX live results)
- Activity timeline — unified chronological feed from all modules (`/timeline/`)
- Calendar view — FullCalendar 6.x with color-coded events by type (`/calendar/`); defaults to list view on mobile
- File uploads working — evidence on legal matters + attachments on notes (HTMX inline add/delete)
- CSV export on all list pages (stakeholders, tasks, cash flow, notes, legal, real estate, investments, loans)
- PDF export on all detail pages (stakeholders, tasks, notes, legal, real estate, investments, loans, cash flow summary) via reportlab
- Cash flow charts — monthly trend bar chart + category breakdown doughnut (Chart.js 4.x)
- Liquidity alerts — net negative flow, large upcoming payments, projected shortfall (dashboard + cash flow page)
- Currency values formatted with comma separators across all templates
- Mobile-responsive button layout, summary cards, and calendar on all pages
- Push notifications via django-q2 — overdue tasks, upcoming reminders, stale follow-ups
- Notification schedule management command (`setup_schedules`)
- Email settings UI — DB-backed SMTP configuration at `/settings/email/` with test email button, sidebar link, admin singleton enforcement
- Friendly empty states with icons + CTA buttons on all list pages
- HTMX loading indicators on all list page filters/searches
- Colour-coded action buttons (purple exports, blue edit, green complete, red delete)
- Docker deployment — single container with Gunicorn + WhiteNoise, env var config, named volumes
- Unit/integration tests (424 tests across all modules)
- Tailwind CSS switched from CDN to standalone CLI (v3.4.17) — compiled at build time, no Node.js required
- GitHub repo: `trialskid/control-center`
- Security hardening — conditional SECRET_KEY, production SSL/HSTS/cookie security headers (gated behind `not DEBUG`)
- Breadcrumb navigation on all detail and form pages (Home / Module / Record)
- Legal matter enhancements — hearing dates, settlement/judgment amounts, outcome field; hearing events on calendar
- Dashboard enhancements — net worth cards (assets vs liabilities), unified upcoming deadlines panel (tasks + loans + hearings), asset risk alerts
- In-app notification center — Notification model, sidebar bell icon with HTMX badge polling, full notification list page, auto-created from scheduled task emails
- Relationship visualization — Cytoscape.js network graph on stakeholder detail page (1st + 2nd degree relationships)
- Advanced filtering on all list pages — sortable column headers (click to toggle asc/desc with arrow indicators), date range inputs, multi-select status/type checkbox groups, unified `<form id="filter-form">` with `hx-include`
- Bulk operations on all list pages — select-all checkbox, per-row checkboxes, bulk action bar (delete selected, export selected CSV), tasks also have bulk mark-complete; confirmation modal for bulk delete
- Editable choice fields — DB-backed `ChoiceOption` model replacing hardcoded `choices=` on 5 model fields across 4 categories (entity type, contact method, matter type, note type). Settings UI at `/settings/choices/` with HTMX inline add/edit/toggle-active/reorder. Template filter `|choice_label` for display. Cached choice lookups. Seed data migration. Forms load choices dynamically. PDF exports and notifications updated. 19 new tests.
- Enhanced stakeholder detail page — comprehensive relationship view with tabbed "All Connections" interface (8 tabs with count badges), expanded Cytoscape.js graph showing all entity types (stakeholders, properties, investments, loans, legal matters, tasks) with color-coded shapes, cash flow entries added to detail view
- Multi-stakeholder support — M2M through models (`PropertyOwnership`, `InvestmentParticipant`, `LoanParty`) replacing single FKs on properties, investments, and loans. Each link stores ownership percentage and role. Graph edges display "Role (X%)" labels. Admin inline editors. Sample data updated with co-owners and co-borrowers.
- Inline stakeholder management on asset detail pages — HTMX add/delete for owners (properties), participants (investments), and parties (loans) directly from detail pages. 6 new views, 6 URL patterns, 6 template partials following the contact log inline pattern.
- Per-follow-up configurable reminders — `reminder_enabled` (default=off) opt-in toggle + `follow_up_days` field (default=3). Reminders only fire when explicitly enabled. Task create form has optional inline follow-up creation with separate reminder toggle. "Mark Responded" HTMX button on pending follow-ups. Stale notification excludes completed tasks. 16 new tests.
- Firm/employee hierarchy — `parent_organization` self-FK on Stakeholder. Firms (`entity_type="firm"`) have Team Members section on detail page with "Add Employee" link. Employees link back to firm. Graph shows firm→employee edges with sibling employees. "firm" entity type seeded via data migration. Form filters dropdown to firms only. CSV/PDF exports include firm. Global search includes `parent_organization__name`. Table rows link Organization column to firm. 6 new tests.
- Bidirectional task tracking — `direction` field on Task (personal/outbound/inbound). Outbound = "I asked them", inbound = "they asked me". Cyan badges for outbound, amber for inbound. Arrow indicators (↗/↙) in task table rows. Direction-aware stakeholder label on detail page ("Requested From"/"Requested By"). Follow-up section hidden for inbound tasks. Direction filter checkboxes on list page. Calendar prefixes [OUT]/[IN]. Notification prefixes [OUTBOUND]/[INBOUND]. CSV/PDF exports include direction. Stakeholder detail Tasks tab has "+ Request from them" and "+ They requested" action links. Sample data includes Armanino LLP firm with 3 employees, 3 outbound tasks, 3 inbound tasks, and 2 follow-ups with reminders. 7 new tests.

- Stakeholder list category tabs — 7-tab navigation (All, Firms & Teams, Attorneys, Lenders, Business Partners, Advisors, Other). "All" tab excludes employees (they appear under their firm). "Firms & Teams" uses card layout with firm cards containing nested employee rows and "+ Add Employee" links. Tab counts as badges. HTMX tab switching with `hx-push-url`. Search works per-tab (Firms tab matches firm OR employee name). Type filter dropdown only on All tab. Bulk actions/sorting/pagination on table tabs. `_tab_content.html` and `_firm_cards.html` partials. 5 new tests.

- Notes list rich cards — table replaced with card layout showing content previews (`truncatewords:40` + `line-clamp-2`), color-coded type badges with icons (call/email/meeting/research/legal_update/general), attachment count with paperclip icon, and linked entity chips (indigo participants, blue stakeholders, green properties, amber legal matters, yellow tasks). Stakeholder filter dropdown (participants OR related_stakeholders). Search expanded to match note content. Prefetch + annotation eliminates N+1 queries. Sort toolbar (date/title/type). Bulk actions work with card layout via `bulk-actions.js` afterSwap fix. 4 new tests.

- Sustainability hardening (Phase 1) — SQLite WAL mode + pragmas via `connection_created` signal (`dashboard/apps.py`). Gunicorn tuned from 4 workers/5s timeout to 2 workers/30s timeout. Database indexes on 8 frequently-filtered fields across 5 apps. Backup system: `python manage.py backup` (sqlite3 backup API + media → timestamped .tar.gz), `python manage.py restore <archive>` (validates, replaces DB + media, runs migrate), automated daily backup via django-q2 (keeps 7). Docker backup volume (`legacy-backups`). All 21 migrations squashed to 7 (one `0001_initial.py` per app). `.gitignore` updated for WAL files and backups dir. 14 new tests.

- Comprehensive README.md — full feature documentation with URL reference tables for all 7 modules, complete management command reference (runserver, migrate, backup, restore, load_sample_data, setup_schedules, qcluster), backup/restore procedures with command examples, disaster recovery walkthrough, Docker deployment guide, environment variable reference, project directory structure, test coverage breakdown by module, and development workflow instructions.

- Follow-up inline edit — HTMX edit button on each follow-up row loads pre-populated form into `#followup-form-container`. Reuses `_followup_form.html` with parameterized `form_url` and `edit_mode` flag. URL: `followup/<pk>/edit/`. 2 new tests.

- Follow-up response notes — `response_notes` TextField on FollowUp captures what the person said when marking as responded. "Mark Responded" button changed from instant toggle to inline form (`_followup_respond_form.html`) with optional notes textarea. Undo preserves response notes. Responded follow-ups with notes display italic text and "Create Note" link that pre-fills NoteCreateView via query params (title, content, date, task, stakeholder). PDF export includes response notes in Notes column. NoteCreateView extended with query param pre-fill support. 4 new tests.

- Multi-stakeholder tasks — `related_stakeholder` FK converted to `related_stakeholders` M2M (plain, no through model). 3-step migration (add M2M, data migrate, remove FK). Form uses `SelectMultiple` with `<optgroup>` elements grouped by entity type label via `_grouped_stakeholder_choices()`. Follow-up auto-create uses first stakeholder. CSV export joins all stakeholder names. Table rows show first stakeholder + "+N" count badge. Detail page shows comma-separated linked names. Notifications join all names. Dashboard queries updated from `select_related` to `prefetch_related`. `related_name="tasks"` preserved so all reverse lookups (stakeholder detail tabs, graph) continue unchanged. 5 new tests (311 total).

- Stakeholder-side inline asset management — Properties/Investments/Loans tabs on stakeholder detail page reworked from plain lists to rich through-model displays with role badges, color-coded percentages (green/purple/orange), and HTMX inline add/delete. 3 new forms in `stakeholders/forms.py` (`StakeholderPropertyForm`, `StakeholderInvestmentForm`, `StakeholderLoanForm`) with asset dropdowns (stakeholder set server-side). 6 new views, 6 URL patterns, 6 template partials (`_sh_ownership_*`, `_sh_participant_*`, `_sh_party_*`). Detail view context updated from plain asset querysets to through-model querysets with `select_related`. 8 new tests (319 total).

- Loan-asset linking and enriched create forms — `Loan.related_property` and `Loan.related_investment` optional FKs (SET_NULL) link loans to the assets they finance. Property and investment detail pages now show "Loans" section with lender names, balance, rate, and monthly payment; "+ Add Loan" links pre-fill the loan create form via query params. Loan detail page shows linked property/investment as clickable links. Property and investment create forms now include optional "Initial Owner/Participant" section (stakeholder dropdown, role, ownership %) so the first relationship can be set during creation without doubling back. Edit forms hide these fields. 11 new tests (330 total).

- Dashboard rework — asset/task/legal focus replacing cashflow-heavy layout. Liquidity alerts now dismissable via sessionStorage (`static/js/dismiss-alerts.js`). Net worth + cashflow consolidated from 7 cards (2 rows) to 4 cards (1 row): Net Worth, Total Assets, Total Liabilities, Monthly Net Flow. New Asset Overview panel (`_asset_summary.html`) shows property/investment/loan counts and totals with color-coded links. Prominent "Upcoming Meetings" panel (`_upcoming_meetings.html`) between summary cards and primary row — blue-bordered, shows next 14 days of meetings with date/time, "Today" highlight, stakeholder, and quick "+ Notes" link; hidden when no meetings. Primary 3-column row (Overdue Tasks | Active Legal | Asset Overview) above secondary 2-column row (Stale Follow-ups | Recent Activity). Removed 4-card cashflow detail row and projected inflow/outflow queries — that granularity lives on `/cashflow/`. View context adds `upcoming_meetings`, `today`, `monthly_net_flow`, `property_count`/`property_value`, `investment_count`/`investment_value`, `active_loan_count`/`loan_balance`.

- External links on notes — `Link` model (`url` URLField max_length=2000, `description` CharField 255 required, `created_at`) with FK→Note. HTMX inline add/edit/delete mirroring attachment pattern. Note detail "Attachments & Links" section with "+ Add Link" / "+ Add File" buttons, Links sub-header. Clickable descriptions open in new tab with external-link icon. Inline edit via hover "edit" button loads pre-populated form (reuses `_link_form.html` with `form_url`/`edit_mode` params). `LinkForm` with Google Docs placeholder. Admin `LinkInline`. PDF export includes Links table. Note list cards show combined attachment+link count badge. 12 new tests (341 total).

- Markdown editor for notes — EasyMDE 2.20 toolbar (bold, italic, strikethrough, headings, lists, checklists, links, blockquotes, code, preview, side-by-side) on note create/edit forms via CDN. Dark theme CSS overrides. Content stored as plain markdown in existing TextField — no model changes. `render_markdown` template filter with `nl2br` extension + blank-line preprocessor for backwards compat. Custom `prose-markdown` CSS in `input.css` for rendered markdown styling (Tailwind standalone CLI lacks typography plugin). PDF export strips markdown syntax. Quick capture stays plain textarea. 6 new tests (347 total).

- Settings hub + sample data toggle — consolidated settings page at `/settings/` with 4 cards (Sample Data, Manage Choices, Email Settings, Django Admin). Sidebar reduced from 4 bottom links to 2 (Notifications + Settings). `SampleDataStatus` singleton model tracks loaded state + manifest of created PKs. `load_sample_data` command saves manifest and has idempotency guard. HTMX load/remove buttons with confirmation dialog. Remove deletes only manifested PKs in reverse-dependency order — user data untouched. Admin singleton enforcement. 12 new tests (359 total).

- Meeting task support — `"meeting"` task type with optional `due_time` TimeField (separate from `due_date` for zero blast radius). `is_meeting` and `scheduled_datetime_str` properties. Form renders date+time side-by-side in flex row; JS shows/hides time input and changes label to "Meeting date" when task_type is "meeting"; `clean()` validates time requires date. Detail page: "Meeting Time" label, blue time display, blue-bordered "Meeting Notes" section with "+ Add Meeting Notes" button pre-filling note creation (title, type, task, stakeholder, datetime). Table rows: styled blue `MTG` pill badge + time in due column + sortable Created column. Task type filter checkboxes on list page. Calendar: meetings get distinct blue `#3b82f6` with `display: "block"` for bar rendering; contacts use cyan `#06b6d4`. Interactive calendar toggle buttons for all 7 event types + "All" toggle (turns all on if any off, all off if all on). Timeline/deadlines: time in summaries, blue meeting badges. CSV "Time" column (both full and bulk export), PDF time in due date. Notifications: `[MEETING]` prefix. `NoteCreateView.get_initial()` parses date query params via `fromisoformat()` for robust datetime pre-fill. 12 new tests (371 total).

- Task page enhancements — Kanban board view (Table/Board toggle, 4-column drag-and-drop via SortableJS, `kanban_update` endpoint, cards with priority bars and badges, no pagination on board, dynamic SortableJS loading), follow-up timeline (vertical timeline with colored status dots replacing flat list, green/red/yellow/gray indicators, all HTMX preserved), and quick inline edit (clickable status/priority badges that cycle values, clickable due date with native picker, extracted `_task_row.html` partial, `inline_update` endpoint with field validation, `toggle_complete` returns row or badge based on context). 22 new tests (393 total).

- Dashboard upcoming meetings panel — dedicated blue-bordered "Upcoming Meetings" panel (`_upcoming_meetings.html`) positioned between summary cards and primary 3-column row for maximum visibility. Queries next 14 days of non-complete meeting tasks, ordered by date+time, with prefetched stakeholders. Each row shows: date block with green "Today" label for same-day meetings (otherwise "Feb 14" format), blue time, meeting title, first stakeholder name, and "+ Notes" quick link (pre-fills note creation with title, note_type=meeting, task, stakeholder, datetime). Count badge in header + "View Calendar" link. Panel hidden when no upcoming meetings. Meetings continue to appear in Upcoming Deadlines for completeness. EasyMDE sync fix: codemirror `change` event calls `save()` so hidden textarea stays in sync for form validation.

- Task page enhancements batch 2 — Five features: (1) Stakeholder filter dropdown on task list (follows notes list pattern, `<select name="stakeholder">` with `.distinct()` filtering). (2) Stale follow-up indicator — red dot on task rows/kanban cards via `has_stale_followups` property, `follow_ups` prefetched in list view. (3) Grouped table view — `_build_grouped_tasks()` helper with 4 modes (status/priority/due_date/stakeholder), collapsible `<details>` sections, group dropdown in filter form, no pagination. (4) Subtasks/checklists — `SubTask` model, 3 HTMX views (add/toggle/delete), `_subtask_list.html` with green checkboxes and inline add, progress bar on detail page, `N/M` annotations on list/kanban, admin inline, PDF/CSV export. (5) Recurring tasks — `is_recurring`/`recurrence_rule` fields, `compute_next_due_date()` with end-of-month clamping, `create_next_recurrence()` copies task + M2M, completion hooks in all 4 paths (toggle/kanban/inline/bulk), form toggle + validation, indigo &#x21bb; indicators. Migration: `0007_task_recurrence_subtask`. 31 new tests (424 total).

### Next Steps
- User authentication (currently no login required — fine for single-user VPN access)
