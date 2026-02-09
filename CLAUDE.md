# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Control Center** is a self-hosted personal management system designed as a single-user command center for managing complex personal affairs. Built for Blaine. Accessed via VPN on a private server (currently demoed via ngrok). No team collaboration features needed.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| Framework | Django 6.0.2 |
| Database | SQLite |
| Frontend | Django Templates + HTMX 2.0.4 |
| CSS | Tailwind CSS (CDN) |
| Charts | Chart.js 4.x (CDN) |
| PDF Export | reportlab 4.4.9 (platypus engine) |
| Background Jobs | Django-Q2 (ORM broker) |
| Deployment | Gunicorn + Nginx on Linux |

## Build & Run Commands

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
```

## Apps & Architecture

Seven Django apps, all relationally linked:

| App | Models | Purpose |
|-----|--------|---------|
| **dashboard** | (none) | Master homepage, global search, activity timeline, calendar view |
| **stakeholders** | Stakeholder, Relationship, ContactLog | CRM — entity profiles, trust/risk ratings, relationship mapping, contact logs |
| **assets** | RealEstate, Investment, Loan | Asset & liability tracker — properties, investments, loans with payment schedules |
| **legal** | LegalMatter, Evidence | Legal matter management — case status, attorneys (M2M), evidence, related stakeholders/properties |
| **tasks** | Task, FollowUp | Task system — deadlines, priorities, status tracking, follow-up/stale outreach workflows |
| **cashflow** | CashFlowEntry | Cash flow — actual + projected inflows/outflows with category filtering |
| **notes** | Note, Attachment | Notes/activity database — discrete searchable records linked to entities via M2M relations |

## Key Patterns

- **Views**: CBVs for CRUD, function views for HTMX partials (contact logs, follow-ups, evidence, attachments, quick capture)
- **Forms**: `TailwindFormMixin` in `blaine/forms.py` auto-applies dark-mode Tailwind classes to all widget types
- **HTMX**: Live search/filter on list pages (`hx-get` with `delay:300ms`), inline add/delete for child records, modal quick capture, global search with live results
- **Templates**: `base.html` includes sidebar + modal container; apps use `partials/` subdirectories for HTMX fragments
- **Cross-linking**: Detail pages show related records from all other modules; all models have `get_absolute_url()`
- **Delete confirmation**: Shared `partials/_confirm_delete.html` template used by all DeleteViews
- **CSRF for HTMX**: Set via `hx-headers` on `<body>` element
- **FKs**: `SET_NULL` for optional, `CASCADE` for required; string references for cross-app FKs
- **Admin**: Inlines for child records, `filter_horizontal` for M2M fields
- **CSV Export**: Generic `blaine/export.py` utility; export views on all list pages (stakeholders, tasks, cashflow, notes, legal, real estate, investments, loans)
- **PDF Export**: Generic `blaine/pdf_export.py` using reportlab platypus; `render_pdf(request, filename, title, subtitle, sections)` with section types: "info" (key-value rows), "table" (headers + rows), "text" (paragraphs). PDF views on all detail pages.
- **Charts**: Chart.js 4.x on cash flow page — monthly trend bar chart + category breakdown doughnut chart. JSON endpoint at `cashflow/charts/data/` using `TruncMonth` + `Sum` aggregation.
- **Liquidity Alerts**: `cashflow/alerts.py` — `get_liquidity_alerts()` returns alert dicts with 3 triggers: net negative monthly flow, large upcoming loan payments (>$5k/30 days), projected shortfall. Displayed via `partials/_alerts.html` on dashboard and cash flow page (context-aware: hides "View Cash Flow" link when already on that page).
- **Currency formatting**: `django.contrib.humanize` `intcomma` filter for comma-separated dollar values across all templates
- **Notifications**: `tasks/notifications.py` — 3 scheduled functions via django-q2 (overdue tasks, upcoming reminders, stale follow-ups)
- **Button colour scheme**: Detail pages use purple (PDF/export), blue (Edit), green (Complete), red (Delete). List pages use purple for export buttons, blue for "+ New".
- **ALLOWED_HOSTS**: Set to `["*"]` for development (lock down for production)

## Current Status

### Completed
- All models and migrations
- Admin interfaces for all models
- Full frontend: dark sidebar command-center layout with Tailwind CSS + HTMX
- All CRUD pages for all 6 modules (58+ templates, 80+ files total)
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
- Push notifications via django-q2 — overdue tasks, upcoming reminders, stale follow-ups (console email for dev)
- Notification schedule management command (`setup_schedules`)
- Friendly empty states with icons + CTA buttons on all list pages
- HTMX loading indicators on all list page filters/searches
- Colour-coded action buttons (purple exports, blue edit, green complete, red delete)

### Next Steps
- Production deployment (Gunicorn + Nginx, proper ALLOWED_HOSTS, static file collection)
- Switch Tailwind from CDN to standalone CLI for production
- User authentication (currently no login required — fine for single-user VPN access)
- SMTP email configuration for production notifications
- Unit/integration tests
