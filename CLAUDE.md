# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Control Center** is a self-hosted personal management system designed as a single-user command center for managing complex personal affairs. Built for Legacy. Accessed via VPN on a private server (currently demoed via ngrok). No team collaboration features needed.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| Framework | Django 6.0.2 |
| Database | SQLite |
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
| **stakeholders** | Stakeholder, Relationship, ContactLog | CRM — entity profiles, trust/risk ratings, relationship mapping, contact logs |
| **assets** | RealEstate, PropertyOwnership, Investment, InvestmentParticipant, Loan, LoanParty | Asset & liability tracker — properties, investments, loans with payment schedules; M2M through models for multi-stakeholder ownership with percentages and roles |
| **legal** | LegalMatter, Evidence | Legal matter management — case status, attorneys (M2M), evidence, related stakeholders/properties |
| **tasks** | Task, FollowUp | Task system — deadlines, priorities, status tracking, follow-up/stale outreach workflows |
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
- **Editable Choices**: `dashboard/models.py` — `ChoiceOption` model stores dropdown options in DB (replaces hardcoded `choices=` on model fields). 4 categories: `entity_type` (Stakeholder), `contact_method` (ContactLog/FollowUp), `matter_type` (LegalMatter), `note_type` (Note). `dashboard/choices.py` provides `get_choices(category)` (cached DB lookup returning Django choice tuples), `get_choice_label(category, value)` (display label with raw-value fallback), `invalidate_choice_cache()`. Template filter: `{% load choice_labels %}` then `{{ value|choice_label:"category" }}`. Forms load choices dynamically in `__init__`. Settings UI at `/settings/choices/` with HTMX add/edit/toggle-active/reorder per category. Seed data in migration `0004_seed_choice_options.py`. Status/workflow fields (task status, priority, loan status, etc.) are NOT included — their values are referenced in business logic.
- **Multi-Stakeholder Ownership**: Properties, investments, and loans support multiple stakeholders via M2M through models (`PropertyOwnership`, `InvestmentParticipant`, `LoanParty`). Each link stores ownership percentage and role. Detail pages show all stakeholders with color-coded percentages (green for properties, purple for investments, orange for loans). Admin has inline editors for through model records. Note: create/edit forms don't include inline formsets yet — use admin for complex multi-stakeholder management.
- **Stakeholder Detail Tabs**: Tabbed "All Connections" interface replaces individual preview cards on stakeholder detail page. 8 tabs with count badges showing all related entities (no 5-item limits). Cash flow entries included. Zero information redundancy with the relationship graph.
- **Docker**: Single container runs Gunicorn (foreground) + qcluster (background). `entrypoint.sh` handles migrate, collectstatic, createsuperuser, sample data loading. Named volumes for SQLite (`legacy-data`) and media (`legacy-media`)

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
- Unit/integration tests (234 tests across all modules)
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

### Next Steps
- User authentication (currently no login required — fine for single-user VPN access)
- Inline formsets for multi-stakeholder management on create/edit forms (currently admin-only)
