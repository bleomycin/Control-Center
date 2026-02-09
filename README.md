# Control Center

A self-hosted personal management system built with Django. Designed as a single-user command center for managing stakeholders, assets, legal matters, tasks, cash flow, and notes — all from one dark-themed dashboard.

## Quick Start (Docker)

```bash
git clone <repo-url>
cd blaine
cp .env.example .env    # edit SECRET_KEY for production
docker compose up --build
```

App at **http://localhost:8000** — login: `admin` / `admin`

Sample data loads automatically on first run. To disable, set `LOAD_SAMPLE_DATA=false` in `.env`.

## Tech Stack

- **Backend:** Python 3.12, Django 6.0.2, SQLite
- **Frontend:** Django Templates, HTMX 2.0.4, Tailwind CSS 3.4 (standalone CLI)
- **Charts:** Chart.js 4.x
- **PDF Export:** ReportLab
- **Background Jobs:** Django-Q2

## Modules

| Module | Description |
|--------|-------------|
| **Dashboard** | Homepage with net worth cards, upcoming deadlines, asset risk alerts, global search, activity timeline, calendar, notification center |
| **Stakeholders** | CRM with contact logs, trust/risk ratings, relationship mapping, network graph visualization |
| **Assets** | Real estate, investments, and loans with payment schedules |
| **Legal** | Case tracking with hearing dates, settlement/judgment amounts, evidence uploads, linked stakeholders and properties |
| **Tasks** | Deadlines, priorities, follow-ups, stale outreach tracking, bulk mark-complete |
| **Cash Flow** | Income/expense tracking with charts, liquidity alerts, projections |
| **Notes** | Searchable notes with file attachments, linked to any entity |

## Features

- HTMX-powered live search and filtering on all list pages
- Advanced filtering — sortable column headers, date range pickers, multi-select status/type checkboxes
- Bulk operations — select-all, bulk delete (with confirmation), bulk CSV export, bulk mark-complete (tasks)
- Inline child record management (contact logs, follow-ups, evidence, attachments)
- Quick capture modals for notes and tasks from the sidebar
- Cross-linked detail pages across all modules with breadcrumb navigation
- CSV export on all list pages, PDF export on all detail pages
- Cash flow charts (monthly trend + category breakdown)
- Liquidity alerts (negative flow, large payments, projected shortfalls)
- Dashboard net worth cards, unified upcoming deadlines, asset risk alerts
- In-app notification center with sidebar bell icon (HTMX badge polling)
- Email notifications via django-q2 — overdue tasks, upcoming reminders, stale follow-ups
- DB-backed email/SMTP settings with test email button
- Relationship network graph on stakeholder detail (Cytoscape.js)
- Calendar view with color-coded events (FullCalendar 6.x)
- Security hardening — conditional SECRET_KEY, production SSL/HSTS/cookie headers
- Responsive mobile layout
- 228 unit/integration tests

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### Optional

```bash
# Load sample data
python manage.py load_sample_data

# Set up notification schedules
python manage.py setup_schedules

# Start background worker
python manage.py qcluster

# Tailwind CSS (standalone CLI — no Node.js required)
make tailwind-install   # download binary
make tailwind-build     # one-shot minified build
make tailwind-watch     # watch mode for development
```

## License

Private project.
