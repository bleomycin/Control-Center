# Control Center

A self-hosted personal management system built with Django. Designed as a single-user command center for managing stakeholders, assets, legal matters, tasks, cash flow, and notes — all from one dark-themed dashboard.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Tech Stack](#tech-stack)
- [Environment Variables](#environment-variables)
- [Modules](#modules)
- [Dashboard](#dashboard)
- [Stakeholder Management](#stakeholder-management)
- [Asset Tracking](#asset-tracking)
- [Legal Matter Management](#legal-matter-management)
- [Task Management](#task-management)
- [Cash Flow Tracking](#cash-flow-tracking)
- [Notes & Attachments](#notes--attachments)
- [Backup & Restore](#backup--restore)
- [Background Jobs & Notifications](#background-jobs--notifications)
- [Email Configuration](#email-configuration)
- [Editable Choice Fields](#editable-choice-fields)
- [CSV & PDF Export](#csv--pdf-export)
- [Search & Filtering](#search--filtering)
- [Calendar](#calendar)
- [Database Configuration](#database-configuration)
- [Docker Deployment](#docker-deployment)
- [Local Development](#local-development)
- [Management Commands](#management-commands)
- [Running Tests](#running-tests)
- [Project Structure](#project-structure)

---

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/trialskid/control-center.git
cd control-center
cp .env.example .env          # edit SECRET_KEY for production
docker compose up --build
```

App at **http://localhost:8000** — admin panel login: `admin` / `admin`

Sample data loads automatically on first run. Set `LOAD_SAMPLE_DATA=false` in `.env` to disable.

### Local Development

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py load_sample_data    # optional demo data
python manage.py runserver
```

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Language | Python | 3.12 |
| Framework | Django | 6.0.2 |
| Database | SQLite | WAL mode |
| Frontend | Django Templates + HTMX | 2.0.4 |
| CSS | Tailwind CSS (standalone CLI) | 3.4.17 |
| Charts | Chart.js (CDN) | 4.x |
| PDF Export | ReportLab (platypus engine) | 4.4.9 |
| Background Jobs | Django-Q2 (ORM broker) | 1.9.0 |
| Static Files | WhiteNoise | 6.9.0 |
| WSGI Server | Gunicorn | 23.0.0 |
| Deployment | Docker | Single container |

### Dependencies

```
Django==6.0.2
django-q2==1.9.0
reportlab==4.4.9
pillow>=12.0
gunicorn==23.0.0
whitenoise==6.9.0
```

---

## Environment Variables

Configure via `.env` file (copy from `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | *(required in production)* | Django secret key. Raises `ValueError` if unset when `DEBUG=False` |
| `DEBUG` | `true` | Debug mode. Set to `false` for production |
| `ALLOWED_HOSTS` | `*` | Comma-separated list of allowed hostnames |
| `DATABASE_PATH` | `db.sqlite3` | Path to SQLite database file |
| `DJANGO_SUPERUSER_USERNAME` | — | Initial admin username (Docker auto-creation) |
| `DJANGO_SUPERUSER_PASSWORD` | — | Initial admin password (Docker auto-creation) |
| `DJANGO_SUPERUSER_EMAIL` | — | Initial admin email (Docker auto-creation) |
| `LOAD_SAMPLE_DATA` | `true` | Auto-load demo dataset on first Docker run |
| `EMAIL_BACKEND` | `console` | Django email backend class |
| `ENABLE_SSL` | `false` | Enable HTTPS redirect, HSTS, secure cookies |
| `BACKUP_DIR` | `BASE_DIR/backups` | Backup archive storage directory |

Production security headers (SSL redirect, HSTS, secure cookies) activate when `DEBUG=False` and `ENABLE_SSL=true`.

---

## Modules

Seven Django apps, all relationally cross-linked:

| Module | Models | Purpose |
|--------|--------|---------|
| **Dashboard** | ChoiceOption, EmailSettings, Notification | Homepage, global search, timeline, calendar, notifications, settings |
| **Stakeholders** | Stakeholder, Relationship, ContactLog | CRM with firm/employee hierarchy, trust/risk ratings, network graph |
| **Assets** | RealEstate, PropertyOwnership, Investment, InvestmentParticipant, Loan, LoanParty | Properties, investments, loans with multi-stakeholder ownership |
| **Legal** | LegalMatter, Evidence | Case tracking with hearings, settlements, evidence, linked entities |
| **Tasks** | Task, FollowUp | Deadlines, priorities, bidirectional direction, follow-up reminders |
| **Cash Flow** | CashFlowEntry | Income/expense tracking with charts, projections, liquidity alerts |
| **Notes** | Note, Attachment | Searchable notes with file uploads, linked to any entity |

---

## Dashboard

**URL:** `/`

The main homepage displays:

- **Net Worth Cards** — total assets (owned properties + investments) vs total liabilities (active loans), with computed net worth
- **Cash Flow Summary** — actual inflows/outflows and projected inflows/outflows for the current month
- **Upcoming Deadlines** — unified panel combining task due dates, loan payment dates, and legal hearing dates sorted chronologically
- **Overdue Tasks** — tasks past their due date that aren't complete
- **Stale Follow-ups** — follow-ups awaiting response past their reminder window
- **Asset Risk Alerts** — properties in dispute, defaulted loans
- **Liquidity Alerts** — net negative monthly flow, large upcoming loan payments (>$5,000 in 30 days), projected cash shortfalls
- **Recent Activity Feed** — mixed chronological feed from contact logs, notes, and tasks

### Global Search

**URL:** `/search/?q=<query>`

Searches across all modules simultaneously: stakeholders (name, email, organization, parent organization), tasks (title, description), notes (title, content), legal matters (title, case number), properties (name, address), investments (name), loans (name), and cash flow entries (description). Results grouped by module with links. HTMX live results with 300ms debounce.

### Activity Timeline

**URL:** `/timeline/`

Unified reverse-chronological feed of contact logs, notes, tasks, and cash flow entries. Each item shows date, type badge, title, summary, and link to source record.

---

## Stakeholder Management

**URLs:**

| Action | URL | Method |
|--------|-----|--------|
| List all | `/stakeholders/` | GET |
| Create | `/stakeholders/create/` | GET/POST |
| Detail | `/stakeholders/<id>/` | GET |
| Edit | `/stakeholders/<id>/edit/` | GET/POST |
| Delete | `/stakeholders/<id>/delete/` | GET/POST |
| PDF export | `/stakeholders/<id>/pdf/` | GET |
| CSV export | `/stakeholders/export/` | GET |
| Relationship graph (JSON) | `/stakeholders/<id>/graph-data/` | GET |
| Add contact log | `/stakeholders/<id>/contact-log/add/` | POST (HTMX) |
| Delete contact log | `/stakeholders/contact-log/<id>/delete/` | POST (HTMX) |
| Bulk delete | `/stakeholders/bulk/delete/` | POST |
| Bulk export | `/stakeholders/bulk/export/` | POST |

### Entity Types

DB-backed via `ChoiceOption` (editable at `/settings/choices/`): Advisor, Business Partner, Lender, Contact, Professional, Attorney, Firm, Other.

### Tabbed List Navigation

The stakeholder list page has 7 tabs:

| Tab | Filter | Layout |
|-----|--------|--------|
| **All** | Excludes employees (shows top-level only) | Table |
| **Firms & Teams** | `entity_type="firm"` | Card layout with nested employees |
| **Attorneys** | `entity_type="attorney"` | Table |
| **Lenders** | `entity_type="lender"` | Table |
| **Business Partners** | `entity_type="business_partner"` | Table |
| **Advisors** | `entity_type="advisor"` | Table |
| **Other** | All other types | Table |

Each tab shows a count badge. The Firms tab displays firm cards with nested employee rows and an "+ Add Employee" link. Search on the Firms tab matches firm name OR employee names.

### Firm/Employee Hierarchy

Stakeholders can be organized into firms via the `parent_organization` self-referencing foreign key:

- Firms have `entity_type="firm"` and display a "Team Members" section on their detail page
- Employees link back to their parent firm
- The relationship graph shows firm-to-employee edges and sibling employee connections
- The stakeholder form filters the "Organization" dropdown to firms only

### Relationship Graph

Cytoscape.js network visualization on each stakeholder's detail page showing 1st and 2nd degree connections:

| Entity Type | Shape | Color |
|-------------|-------|-------|
| Stakeholders | Circle | Blue |
| Properties | Rectangle | Green |
| Investments | Diamond | Purple |
| Loans | Triangle | Orange |
| Legal Matters | Hexagon | Red |
| Tasks | Star | Yellow |

Edges display relationship role and ownership percentage (e.g., "Co-owner (50%)"). Nodes are clickable and link to detail pages. Node IDs are prefixed by type: `s-`, `p-`, `i-`, `l-`, `m-`, `t-`.

### Contact Logs

Inline HTMX add/delete on the stakeholder detail page. Each log records date, contact method, summary, and optional follow-up date. Contact methods are DB-backed via `ChoiceOption`.

---

## Asset Tracking

### Real Estate

**URLs:**

| Action | URL |
|--------|-----|
| List | `/assets/real-estate/` |
| Create | `/assets/real-estate/create/` |
| Detail | `/assets/real-estate/<id>/` |
| Edit | `/assets/real-estate/<id>/edit/` |
| Delete | `/assets/real-estate/<id>/delete/` |
| PDF export | `/assets/real-estate/<id>/pdf/` |
| CSV export | `/assets/real-estate/export/` |
| Add owner | `/assets/real-estate/<id>/ownership/add/` (HTMX) |
| Remove owner | `/assets/ownership/<id>/delete/` (HTMX) |
| Bulk delete | `/assets/real-estate/bulk/delete/` |
| Bulk export | `/assets/real-estate/bulk/export/` |

**Statuses:** Owned, Under Contract, Sold, In Dispute

**Multi-Stakeholder Ownership:** Properties support multiple stakeholders via the `PropertyOwnership` through model. Each ownership record stores stakeholder, percentage, role (Owner, Co-owner, Partner, etc.), and notes. HTMX inline add/delete on the detail page. Color-coded green percentage badges.

### Investments

**URLs:**

| Action | URL |
|--------|-----|
| List | `/assets/investments/` |
| Create | `/assets/investments/create/` |
| Detail | `/assets/investments/<id>/` |
| Edit | `/assets/investments/<id>/edit/` |
| Delete | `/assets/investments/<id>/delete/` |
| PDF export | `/assets/investments/<id>/pdf/` |
| CSV export | `/assets/investments/export/` |
| Add participant | `/assets/investments/<id>/participant/add/` (HTMX) |
| Remove participant | `/assets/participant/<id>/delete/` (HTMX) |
| Bulk delete | `/assets/investments/bulk/delete/` |
| Bulk export | `/assets/investments/bulk/export/` |

**Multi-Stakeholder Participation:** Investments support multiple participants via `InvestmentParticipant` (stakeholder, percentage, role). Color-coded purple percentage badges.

### Loans

**URLs:**

| Action | URL |
|--------|-----|
| List | `/assets/loans/` |
| Create | `/assets/loans/create/` |
| Detail | `/assets/loans/<id>/` |
| Edit | `/assets/loans/<id>/edit/` |
| Delete | `/assets/loans/<id>/delete/` |
| PDF export | `/assets/loans/<id>/pdf/` |
| CSV export | `/assets/loans/export/` |
| Add party | `/assets/loans/<id>/party/add/` (HTMX) |
| Remove party | `/assets/party/<id>/delete/` (HTMX) |
| Bulk delete | `/assets/loans/bulk/delete/` |
| Bulk export | `/assets/loans/bulk/export/` |

**Statuses:** Active, Paid Off, Defaulted, In Dispute

**Fields:** Original amount, current balance, interest rate, monthly payment, next payment date, maturity date, collateral description.

**Multi-Stakeholder Parties:** Loans support multiple parties via `LoanParty` (stakeholder, percentage, role: Lender, Borrower, Co-borrower, Guarantor). Color-coded orange percentage badges.

---

## Legal Matter Management

**URLs:**

| Action | URL |
|--------|-----|
| List | `/legal/` |
| Create | `/legal/create/` |
| Detail | `/legal/<id>/` |
| Edit | `/legal/<id>/edit/` |
| Delete | `/legal/<id>/delete/` |
| PDF export | `/legal/<id>/pdf/` |
| CSV export | `/legal/export/` |
| Add evidence | `/legal/<id>/evidence/add/` (HTMX) |
| Delete evidence | `/legal/evidence/<id>/delete/` (HTMX) |
| Bulk delete | `/legal/bulk/delete/` |
| Bulk export | `/legal/bulk/export/` |

**Statuses:** Active, Pending, Resolved, On Hold

**Matter Types** (DB-backed): Litigation, Compliance, Investigation, Transaction, Other

**Fields:** Title, case number, matter type, status, jurisdiction, court, filing date, next hearing date, settlement amount, judgment amount, outcome, description.

**Relationships:** M2M to attorneys (stakeholders), related stakeholders, and related properties.

**Evidence:** File uploads with title, description, type, and date obtained. HTMX inline add/delete on the detail page. Files stored in `media/evidence/`.

**Calendar Integration:** Hearing dates appear as events on the calendar view.

---

## Task Management

**URLs:**

| Action | URL |
|--------|-----|
| List | `/tasks/` |
| Create | `/tasks/create/` |
| Quick create (modal) | `/tasks/quick-create/` (HTMX) |
| Detail | `/tasks/<id>/` |
| Edit | `/tasks/<id>/edit/` |
| Delete | `/tasks/<id>/delete/` |
| PDF export | `/tasks/<id>/pdf/` |
| CSV export | `/tasks/export/` |
| Toggle complete | `/tasks/<id>/toggle/` (HTMX) |
| Add follow-up | `/tasks/<id>/followup/add/` (HTMX) |
| Delete follow-up | `/tasks/followup/<id>/delete/` (HTMX) |
| Mark responded | `/tasks/followup/<id>/respond/` (HTMX) |
| Bulk delete | `/tasks/bulk/delete/` |
| Bulk export | `/tasks/bulk/export/` |
| Bulk complete | `/tasks/bulk/complete/` |

**Statuses:** Not Started, In Progress, Waiting, Complete

**Priorities:** Critical, High, Medium, Low

**Task Types:** One-Time, Reference

### Bidirectional Task Direction

Each task has a `direction` field:

| Direction | Meaning | Badge | Arrow | Calendar Prefix |
|-----------|---------|-------|-------|-----------------|
| **Personal** | For yourself | — | — | — |
| **Outbound** | "I asked them" | Cyan | ↗ | `[OUT]` |
| **Inbound** | "They asked me" | Amber | ↙ | `[IN]` |

- The stakeholder label on the detail page changes based on direction: "Requested From" (outbound) or "Requested By" (inbound)
- Follow-up section is hidden for inbound tasks
- Notification messages are prefixed with `[OUTBOUND]` or `[INBOUND]`
- Stakeholder detail page has convenience action links: "+ Request from them" and "+ They requested"

### Follow-Up Tracking

Follow-ups track outreach attempts on tasks:

- **Fields:** Stakeholder, outreach date, method, notes
- **Reminder System:** Opt-in per follow-up via `reminder_enabled` toggle. `follow_up_days` (default: 3) sets the reminder window
- **Status Indicators:**
  - Green — response received
  - Red "Overdue" — stale + reminder enabled
  - Yellow "Awaiting" — pending + reminder enabled
  - Gray "No reminder" — pending + reminder disabled
- **Mark Responded:** HTMX button to record a response with timestamp
- **Stale Detection:** `is_stale` property fires only when `reminder_enabled=True` and current time exceeds `outreach_date + follow_up_days`

### Task Create Form

The task creation form includes an optional inline follow-up section:
- Toggle to add initial follow-up with stakeholder, method, and date
- Separate "Enable reminder" checkbox with configurable follow-up days

---

## Cash Flow Tracking

**URLs:**

| Action | URL |
|--------|-----|
| List | `/cashflow/` |
| Create | `/cashflow/create/` |
| Edit | `/cashflow/<id>/edit/` |
| Delete | `/cashflow/<id>/delete/` |
| CSV export | `/cashflow/export/` |
| Chart data (JSON) | `/cashflow/charts/data/` |
| Bulk delete | `/cashflow/bulk/delete/` |
| Bulk export | `/cashflow/bulk/export/` |

**Entry Types:** Inflow, Outflow

**Fields:** Description, amount, type, category, date, is_projected flag, related stakeholder/property/loan, notes.

### Charts

Chart.js 4.x visualizations on the cash flow page:

- **Monthly Trend Bar Chart** — inflows vs outflows by month using `TruncMonth` + `Sum` aggregation
- **Category Breakdown Doughnut** — spending distribution by category

JSON endpoint at `/cashflow/charts/data/` serves aggregated data.

### Liquidity Alerts

Automated alerts displayed on both the dashboard and cash flow page:

| Alert | Trigger |
|-------|---------|
| Net negative flow | Monthly outflows exceed inflows |
| Large upcoming payment | Loan payment > $5,000 due within 30 days |
| Projected shortfall | Projected outflows exceed projected inflows |

---

## Notes & Attachments

**URLs:**

| Action | URL |
|--------|-----|
| List (cards) | `/notes/` |
| Create | `/notes/create/` |
| Quick capture (modal) | `/notes/quick-capture/` (HTMX) |
| Detail | `/notes/<id>/` |
| Edit | `/notes/<id>/edit/` |
| Delete | `/notes/<id>/delete/` |
| PDF export | `/notes/<id>/pdf/` |
| CSV export | `/notes/export/` |
| Add attachment | `/notes/<id>/attachment/add/` (HTMX) |
| Delete attachment | `/notes/attachment/<id>/delete/` (HTMX) |
| Bulk delete | `/notes/bulk/delete/` |
| Bulk export | `/notes/bulk/export/` |

### Card Layout

The notes list uses a card-based layout showing:

- Color-coded type badge with icon
- Date and attachment count (paperclip icon)
- Content preview (truncated to 40 words)
- Linked entity chips: indigo (participants), blue (stakeholders), green (properties), amber (legal matters), yellow (tasks)

### Note Types

DB-backed via `ChoiceOption`: Call (green), Email (blue), Meeting (purple), Research (cyan), Legal Update (amber), General (gray).

### Relationships

Each note supports M2M links to:
- Participants (stakeholders present)
- Related stakeholders
- Related legal matters
- Related properties
- Related tasks

### Attachments

File uploads via HTMX inline add/delete. Files stored in `media/attachments/`. Each attachment has an optional description.

---

## Backup & Restore

The backup system uses Python's `sqlite3.backup()` API for safe, consistent snapshots of a live database (correctly handles WAL mode).

### Creating a Backup

```bash
# Local development
python manage.py backup

# Docker
docker compose exec web python manage.py backup
```

**Output:**
```
Creating backup...
  Database backed up (524,288 bytes)
  Media backed up (153 files)

Backup created: /app/backups/controlcenter-backup-20260209-120000.tar.gz (25,578 bytes)
```

Each backup produces a timestamped `.tar.gz` archive containing:
- `db.sqlite3` — consistent database snapshot
- `media/` — all uploaded files (evidence, attachments)

### Backup Options

```bash
# Keep only the 7 most recent backups (delete older ones)
python manage.py backup --keep 7

# Store backups in a custom directory
python manage.py backup --dir /path/to/backups

# Combine both
python manage.py backup --keep 7 --dir /mnt/external/backups
```

### Restoring from Backup

```bash
# Local development
python manage.py restore backups/controlcenter-backup-20260209-120000.tar.gz

# Docker
docker compose exec web python manage.py restore /app/backups/controlcenter-backup-20260209-120000.tar.gz
```

**Output:**
```
Restoring from: /app/backups/controlcenter-backup-20260209-120000.tar.gz
  Database restored (524,288 bytes)
  Media restored (153 files)
  Running migrations...

Restore complete.
```

The restore command:
1. Validates the archive contains `db.sqlite3` and `media/`
2. Replaces the current database file
3. Replaces the `media/` directory
4. Runs `migrate` to apply any schema differences

### Automated Daily Backups

When `python manage.py setup_schedules` is run (automatically on Docker startup), a daily backup schedule is registered with django-q2:

- **Schedule:** Daily at midnight
- **Retention:** Keeps the 7 most recent backups, prunes older ones
- **Function:** `dashboard.backup_task.run_backup`

The background worker (`qcluster`) must be running for automated backups to execute.

### Backup Storage

| Environment | Default Location | Override |
|-------------|-----------------|----------|
| Local | `<project-root>/backups/` | `BACKUP_DIR` env var |
| Docker | `/app/backups/` (bind mount `./persist/backups/`) | `BACKUP_DIR` env var |

### Docker Bind Mounts

Docker Compose uses bind mounts under `./persist/` for all persistent data. Files are directly accessible on the host.

```bash
# List backups directly on host
ls -la persist/backups/

# Or inside the container
docker compose exec web ls -la /app/backups/
```

### Disaster Recovery Example

```bash
# 1. Stop the running container
docker compose down

# 2. Start fresh container (persist/ directory still intact)
docker compose up --build -d

# 3. Restore from backup
docker compose exec web python manage.py restore /app/backups/controlcenter-backup-20260209-120000.tar.gz

# 4. Verify
docker compose exec web python manage.py shell -c "
from stakeholders.models import Stakeholder
print(f'Stakeholders: {Stakeholder.objects.count()}')
"
```

---

## Background Jobs & Notifications

### Django-Q2 Configuration

```python
Q_CLUSTER = {
    'name': 'ControlCenter',
    'workers': 2,           # Background worker processes
    'timeout': 60,          # Task timeout (seconds)
    'retry': 120,           # Retry delay on failure (seconds)
    'queue_limit': 50,      # Max queued tasks
    'orm': 'default',       # Uses Django ORM as broker (no Redis needed)
}
```

### Scheduled Tasks

Register all schedules:

```bash
python manage.py setup_schedules
```

| Schedule | Function | Frequency |
|----------|----------|-----------|
| Check Overdue Tasks | `tasks.notifications.check_overdue_tasks` | Daily |
| Check Upcoming Reminders | `tasks.notifications.check_upcoming_reminders` | Hourly |
| Check Stale Follow-ups | `tasks.notifications.check_stale_followups` | Daily |
| Daily Backup | `dashboard.backup_task.run_backup` | Daily |

### Starting the Worker

```bash
# Local development
python manage.py qcluster

# Docker (started automatically by entrypoint.sh)
docker compose exec web python manage.py qcluster
```

### In-App Notifications

The `Notification` model stores alerts with levels: info, warning, critical.

- **Sidebar bell icon** with unread count badge (HTMX polling every 60 seconds)
- **Full notification list** at `/notifications/`
- **Mark all read** button at `/notifications/mark-read/`
- Auto-created by scheduled task functions alongside email notifications

### Notification Triggers

| Trigger | Level | Example Message |
|---------|-------|----------------|
| Overdue task | warning | "Overdue: Review lease agreement (due 2026-01-15)" |
| Upcoming reminder | info | "Reminder: Follow up with attorney (due tomorrow)" |
| Stale follow-up | warning | "[OUTBOUND] Stale follow-up: Email to Marcus Reed (3 days)" |

---

## Email Configuration

### SMTP Settings UI

**URL:** `/settings/email/`

DB-backed SMTP configuration (singleton `EmailSettings` model):

| Setting | Default |
|---------|---------|
| SMTP Host | *(blank)* |
| SMTP Port | 587 |
| Use TLS | Yes |
| Use SSL | No |
| Username | *(blank)* |
| Password | *(blank)* |
| From Email | `noreply@controlcenter.local` |
| Admin Email (recipient) | `admin@controlcenter.local` |
| Enable Notifications | No |

A **Test Email** button (HTMX) sends a test message to verify the configuration works.

The master `notifications_enabled` switch controls whether scheduled tasks send emails. When disabled, tasks still create in-app `Notification` records.

---

## Editable Choice Fields

**URL:** `/settings/choices/`

Four categories of dropdown options are stored in the database via the `ChoiceOption` model, replacing hardcoded `choices=` on model fields:

| Category | Used By |
|----------|---------|
| Stakeholder Type | `Stakeholder.entity_type` |
| Contact Method | `ContactLog.method`, `FollowUp.method` |
| Legal Matter Type | `LegalMatter.matter_type` |
| Note Type | `Note.note_type` |

### Settings UI Features

- **Add** new options with auto-generated slug values
- **Edit** labels and values inline
- **Toggle** active/inactive (inactive options hidden from forms but still display for existing records)
- **Reorder** with up/down buttons

### Template Usage

```django
{% load choice_labels %}
{{ stakeholder.entity_type|choice_label:"entity_type" }}
```

### API

```python
from dashboard.choices import get_choices, get_choice_label, invalidate_choice_cache

# Get Django choice tuples for forms
choices = get_choices("entity_type")  # [("advisor", "Advisor"), ...]

# Get display label (with raw-value fallback)
label = get_choice_label("entity_type", "advisor")  # "Advisor"

# Clear cache after programmatic changes
invalidate_choice_cache()
```

> **Note:** Status/workflow fields (task status, priority, loan status, etc.) are NOT DB-backed — their values are referenced in business logic.

---

## CSV & PDF Export

### CSV Export

Every list page has a CSV export button (purple). Available at:

```
/stakeholders/export/
/tasks/export/
/cashflow/export/
/notes/export/
/legal/export/
/assets/real-estate/export/
/assets/investments/export/
/assets/loans/export/
```

Bulk export (selected rows only) available via the bulk action bar on each list page.

### PDF Export

Every detail page has a PDF export button (purple). Uses ReportLab's platypus engine. Available at:

```
/stakeholders/<id>/pdf/
/tasks/<id>/pdf/
/notes/<id>/pdf/
/legal/<id>/pdf/
/assets/real-estate/<id>/pdf/
/assets/investments/<id>/pdf/
/assets/loans/<id>/pdf/
```

PDF sections include key-value info tables, related entity tables, and text blocks. Generic utility at `config/pdf_export.py`.

---

## Search & Filtering

### Advanced Filtering

All list pages share a consistent filtering pattern:

- **Search box** with HTMX live search (`hx-get` with `delay:300ms`)
- **Sortable column headers** — click to toggle ascending/descending with arrow indicators (`sort` and `dir` query params)
- **Date range filters** — `<input type="date">` for start/end dates
- **Multi-select status/type** — checkbox groups with `getlist()` for multi-value filtering
- **Loading indicators** — spinners during HTMX filter/search requests

### Bulk Operations

All list pages support:

- **Select all** checkbox in table header
- **Per-row checkboxes** for individual selection
- **Sticky bulk action bar** (appears when items selected) with:
  - Bulk delete (with confirmation modal)
  - Bulk export CSV
  - Bulk mark complete (tasks only)

Managed by `static/js/bulk-actions.js`.

---

## Calendar

**URL:** `/calendar/`

FullCalendar 6.x with color-coded events:

| Event Type | Color | Source |
|------------|-------|--------|
| Tasks | Blue | `Task.due_date` |
| Loan Payments | Green | `Loan.next_payment_date` |
| Hearings | Red | `LegalMatter.next_hearing_date` |

- Defaults to list view on mobile
- Task events prefixed with `[OUT]`/`[IN]` for directional tasks
- JSON endpoint at `/calendar/events/` with `start`/`end` date filtering
- Clickable events link to detail pages

---

## Database Configuration

### SQLite with WAL Mode

The application uses SQLite with Write-Ahead Logging (WAL) mode and tuned pragmas for reliable concurrent access from Gunicorn workers and the background task worker.

Pragmas are set automatically via a `connection_created` signal handler in `dashboard/apps.py`:

| Pragma | Value | Purpose |
|--------|-------|---------|
| `journal_mode` | WAL | Readers don't block writers |
| `synchronous` | NORMAL | Safe with WAL, much faster than FULL |
| `busy_timeout` | 5000 | Wait 5 seconds on lock instead of failing |
| `cache_size` | -20000 | 20MB page cache (default is 2MB) |
| `foreign_keys` | ON | Enforce foreign key constraints |

### Indexed Fields

The following fields have database indexes for query performance:

| Model | Field | Usage |
|-------|-------|-------|
| `Stakeholder` | `entity_type` | Tab filtering on list page |
| `Stakeholder` | `name` | Global search, list search |
| `Task` | `status` | Active/complete filtering |
| `Task` | `due_date` | Calendar, dashboard deadlines |
| `CashFlowEntry` | `date` | Monthly aggregations, sorting |
| `CashFlowEntry` | `entry_type` | Inflow/outflow filtering |
| `LegalMatter` | `status` | Active/resolved filtering |
| `Note` | `date` | Sort/filter on list page |

---

## Docker Deployment

### Container Architecture

Single container running:
- **Gunicorn** (foreground, PID 1) — 2 workers, 30-second timeout
- **qcluster** (background) — 2 worker processes for scheduled tasks

### Persistent Data (Bind Mounts)

| Host Path | Mount Point | Contents |
|-----------|------------|----------|
| `./persist/data/` | `/app/data/` | SQLite database |
| `./persist/media/` | `/app/media/` | Uploaded files |
| `./persist/backups/` | `/app/backups/` | Backup archives |

### Startup Sequence

The `entrypoint.sh` runs on every container start:

1. `migrate --noinput` — apply pending migrations
2. `collectstatic --noinput` — gather static files for WhiteNoise
3. `createsuperuser --noinput` — create admin user (idempotent)
4. `setup_schedules` — register django-q2 scheduled tasks
5. Check `LOAD_SAMPLE_DATA` — load demo data if DB is empty
6. `qcluster &` — start background worker
7. `mkdir -p /app/backups` — ensure backup directory exists
8. `gunicorn` — start WSGI server

### Common Docker Commands

```bash
# Build and start
docker compose up --build -d

# View logs
docker compose logs -f

# Run tests
docker compose exec web python manage.py test

# Open Django shell
docker compose exec web python manage.py shell

# Create backup
docker compose exec web python manage.py backup

# Restore from backup
docker compose exec web python manage.py restore /app/backups/<archive>.tar.gz

# List backups
docker compose exec web ls -lh /app/backups/

# Access backups directly on host
ls persist/backups/

# Run a one-off management command
docker compose exec web python manage.py <command>

# Stop
docker compose down

# Stop and remove all persistent data (DESTROYS ALL DATA)
docker compose down && rm -rf persist/
```

---

## Local Development

### Initial Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
```

### Running the Server

```bash
# Local only
python manage.py runserver

# LAN / ngrok access
python manage.py runserver 0.0.0.0:8000
```

### Tailwind CSS

The project uses the Tailwind CSS standalone CLI (no Node.js required):

```bash
# Download the binary (platform auto-detected)
make tailwind-install

# One-shot minified build
make tailwind-build

# Watch mode for development (auto-rebuilds on file changes)
make tailwind-watch
```

After adding or changing Tailwind classes in templates, rebuild with `make tailwind-build`.

### Background Worker

```bash
# Register scheduled tasks
python manage.py setup_schedules

# Start the background worker (runs in foreground)
python manage.py qcluster
```

---

## Management Commands

| Command | Description |
|---------|-------------|
| `python manage.py runserver` | Start development server |
| `python manage.py migrate` | Apply database migrations |
| `python manage.py createsuperuser` | Create admin user |
| `python manage.py load_sample_data` | Load comprehensive demo dataset (16 stakeholders, 5 properties, 5 investments, 4 loans, 5 legal matters, 21 tasks, 21 cash flow entries, 9 notes) |
| `python manage.py setup_schedules` | Register django-q2 schedules (3 notification tasks + daily backup) |
| `python manage.py qcluster` | Start background task worker |
| `python manage.py backup` | Create timestamped backup archive |
| `python manage.py backup --keep N` | Create backup and prune, keeping only N most recent |
| `python manage.py backup --dir PATH` | Create backup in a custom directory |
| `python manage.py restore <path>` | Restore database and media from backup archive |
| `python manage.py test` | Run all tests (300 tests) |
| `python manage.py test <app>.tests.<Class>` | Run specific test class |
| `python manage.py makemigrations` | Generate new migrations after model changes |
| `python manage.py collectstatic` | Gather static files for production |
| `python manage.py shell` | Open Django interactive shell |

---

## Running Tests

```bash
# Run all 300 tests
python manage.py test

# Run tests for a specific app
python manage.py test dashboard
python manage.py test stakeholders
python manage.py test tasks

# Run a specific test class
python manage.py test dashboard.tests.BackupCommandTests
python manage.py test dashboard.tests.SQLitePragmaTests

# Run with verbosity
python manage.py test -v2

# Docker
docker compose exec web python manage.py test
```

### Test Coverage

| Area | Tests |
|------|-------|
| Dashboard views & context | 12 |
| Global search | 6 |
| Activity timeline | 6 |
| Calendar & events | 9 |
| Net worth & deadlines | 5 |
| Notifications | 5 |
| Choice system (model, utils, views, template) | 19 |
| SQLite pragmas | 5 |
| Backup & restore | 9 |
| Stakeholders (CRUD, tabs, firm hierarchy) | 30+ |
| Assets (properties, investments, loans, ownership) | 30+ |
| Legal matters & evidence | 20+ |
| Tasks (direction, follow-ups, reminders) | 40+ |
| Cash flow (entries, charts, alerts) | 20+ |
| Notes (cards, attachments, search) | 20+ |

---

## Project Structure

```
control-center/
├── config/                    # Django project config
│   ├── settings.py            # Main settings (env var config)
│   ├── urls.py                # Root URL configuration
│   ├── wsgi.py                # WSGI entry point
│   ├── forms.py               # TailwindFormMixin
│   ├── export.py              # Generic CSV export utility
│   └── pdf_export.py          # Generic PDF export utility (ReportLab)
├── dashboard/                 # Dashboard app
│   ├── apps.py                # SQLite pragma signal handler
│   ├── models.py              # EmailSettings, Notification, ChoiceOption
│   ├── views.py               # Dashboard, search, timeline, calendar, settings
│   ├── choices.py             # get_choices(), get_choice_label(), cache
│   ├── choice_seed_data.py    # Seed data for ChoiceOption
│   ├── email.py               # SMTP helpers (get_smtp_connection, etc.)
│   ├── backup_task.py         # Django-Q2 callable for automated backups
│   ├── management/commands/
│   │   ├── backup.py          # Backup management command
│   │   ├── restore.py         # Restore management command
│   │   ├── setup_schedules.py # Register django-q2 schedules
│   │   └── load_sample_data.py # Demo data loader
│   ├── templatetags/
│   │   └── choice_labels.py   # |choice_label template filter
│   └── tests.py
├── stakeholders/              # Stakeholder CRM app
│   ├── models.py              # Stakeholder, Relationship, ContactLog
│   ├── views.py               # CRUD + graph + tabs + inline contact logs
│   ├── forms.py
│   └── tests.py
├── assets/                    # Asset tracking app
│   ├── models.py              # RealEstate, Investment, Loan + through models
│   ├── views.py               # CRUD + inline ownership management
│   ├── forms.py
│   └── tests.py
├── legal/                     # Legal matter app
│   ├── models.py              # LegalMatter, Evidence
│   ├── views.py               # CRUD + inline evidence
│   ├── forms.py
│   └── tests.py
├── tasks/                     # Task management app
│   ├── models.py              # Task, FollowUp
│   ├── views.py               # CRUD + toggle + inline follow-ups
│   ├── notifications.py       # Scheduled notification functions
│   ├── forms.py
│   └── tests.py
├── cashflow/                  # Cash flow app
│   ├── models.py              # CashFlowEntry
│   ├── views.py               # CRUD + chart data endpoint
│   ├── alerts.py              # Liquidity alert logic
│   ├── forms.py
│   └── tests.py
├── notes/                     # Notes app
│   ├── models.py              # Note, Attachment
│   ├── views.py               # CRUD + inline attachments + quick capture
│   ├── forms.py
│   └── tests.py
├── templates/                 # Global templates
│   ├── base.html              # Main layout (sidebar, nav, modals)
│   └── */                     # Per-app template directories
├── static/
│   ├── css/input.css           # Tailwind source
│   └── js/bulk-actions.js      # Bulk operation JavaScript
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
├── Makefile                   # Tailwind CLI targets
├── tailwind.config.js
├── requirements.txt
├── .env.example
└── CLAUDE.md                  # AI assistant instructions
```

---

## License

Private project.
