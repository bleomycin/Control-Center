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
- **Frontend:** Django Templates, HTMX 2.0.4, Tailwind CSS (CDN)
- **Charts:** Chart.js 4.x
- **PDF Export:** ReportLab
- **Background Jobs:** Django-Q2

## Modules

| Module | Description |
|--------|-------------|
| **Dashboard** | Homepage with summary panels, global search, activity timeline, calendar view |
| **Stakeholders** | CRM with contact logs, trust/risk ratings, relationship mapping |
| **Assets** | Real estate, investments, and loans with payment schedules |
| **Legal** | Case tracking with evidence uploads, linked stakeholders and properties |
| **Tasks** | Deadlines, priorities, follow-ups, stale outreach tracking |
| **Cash Flow** | Income/expense tracking with charts, liquidity alerts, projections |
| **Notes** | Searchable notes with file attachments, linked to any entity |

## Features

- HTMX-powered live search and filtering on all list pages
- Inline child record management (contact logs, follow-ups, evidence, attachments)
- Quick capture modals for notes and tasks from the sidebar
- Cross-linked detail pages across all modules
- CSV export on all list pages
- PDF export on all detail pages
- Cash flow charts (monthly trend + category breakdown)
- Liquidity alerts (negative flow, large payments, projected shortfalls)
- Push notifications for overdue tasks, upcoming reminders, stale follow-ups
- Calendar view with color-coded events (FullCalendar 6.x)
- Responsive mobile layout

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
```

## License

Private project.
