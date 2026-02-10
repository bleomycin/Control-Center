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
| **dashboard** | ChoiceOption, EmailSettings, Notification | Master homepage, global search, activity timeline, calendar view, email/SMTP settings, notification center, editable choice management |
| **stakeholders** | Stakeholder, Relationship, ContactLog | CRM — entity profiles, trust/risk ratings, relationship mapping, contact logs; firm/employee hierarchy via self-FK `parent_organization` |
| **assets** | RealEstate, PropertyOwnership, Investment, InvestmentParticipant, Loan, LoanParty | Asset & liability tracker — properties, investments, loans with payment schedules; M2M through models for multi-stakeholder ownership with percentages and roles |
| **legal** | LegalMatter, Evidence | Legal matter management — case status, attorneys (M2M), evidence, related stakeholders/properties |
| **tasks** | Task, FollowUp | Task system — deadlines, priorities, status tracking, follow-up/stale outreach workflows; bidirectional direction (personal/outbound/inbound); multi-stakeholder M2M with grouped dropdown |
| **cashflow** | CashFlowEntry | Cash flow — actual + projected inflows/outflows with category filtering |
| **notes** | Note, Attachment | Notes/activity database — discrete searchable records linked to entities via M2M relations |

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
- **Liquidity Alerts**: `cashflow/alerts.py` — `get_liquidity_alerts()` returns alert dicts with 3 triggers: net negative monthly flow, large upcoming loan payments (>$5k/30 days), projected shortfall. Displayed via `partials/_alerts.html` on dashboard and cash flow page (context-aware: hides "View Cash Flow" link when already on that page).
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
- **Notes List Cards**: Card-based layout replaces table on `/notes/`. Each card shows: color-coded type badge with icon, date, attachment count (paperclip), content preview (`truncatewords:40` + `line-clamp-2`), and linked entity chips (indigo=participants, blue=stakeholders, green=properties, amber=legal, yellow=tasks). `NoteListView` uses `prefetch_related` for all 5 M2M fields + `annotate(attachment_count=Count("attachments"))`. Search matches `title` and `content`. Stakeholder filter dropdown filters by `participants` OR `related_stakeholders`. Sort toolbar above cards (date/title/type). `_note_cards.html` partial swapped into `#note-card-list` div. `bulk-actions.js` handles card-based afterSwap reset.

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
- Unit/integration tests (330 tests across all modules)
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

### Next Steps
- User authentication (currently no login required — fine for single-user VPN access)
