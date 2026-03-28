# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## CRITICAL RULES — Follow These Every Session

1. **Docker**: ALWAYS use OrbStack Docker on port 8000. NEVER use `python manage.py runserver`. NEVER kill port 8000 with `lsof`. Use `docker compose down` / `docker compose up --build -d`. ALWAYS leave Docker running when done. Rebuild after code changes.
2. **Git identity**: ALL commits MUST use `bleomycin <bleomycin@users.noreply.github.com>`. Verify with `git config user.name && git config user.email` before first commit.
3. **Definition of Done** — ALL of these before reporting ANY work complete:
   - (a) `make test-unit` (in Docker) + `make test-e2e` (local) — all pass. NEVER run bare `python manage.py test` inside Docker.
   - (b) Interactive verification against Docker on :8000 — click every new/changed button, link, HTMX action, form, toggle. After HTMX swaps, verify elements OUTSIDE the swap target (counters, progress bars, styling) are intact.
   - (c) Desktop screenshots via Playwright at both profiles — verify layout, empty states, edge cases:
     - **Desktop** (MacBook Pro): `{ width: 1512, height: 982 }`, `deviceScaleFactor: 2`
     - **Desktop Split** (4K half-screen): `{ width: 960, height: 1080 }`, `deviceScaleFactor: 2`
   - (d) **Desktop headed pass**: Playwright with `headless=False` — verify hover states, keyboard shortcuts (Cmd+K), hover-revealed buttons, clipboard, animations.
   - (e) **Mobile: iOS Simulator (real Safari)** via safaridriver on BOTH devices:
     - **iPhone 16e** (user's iPhone Air)
     - **iPhone 16 Pro Max** (user's iPhone 17 Pro Max)
     Navigate to every changed page. Scroll through changed sections. Screenshot. Verify layout, no overflow, touch behavior.
   - (f) `make tailwind-build` if any CSS classes changed.
   - **NO EXCEPTIONS. Every step a–f must be completed. Do NOT report done with any step skipped.**
4. **Timezone**: ALWAYS use `timezone.localdate()`, NEVER `date.today()`. ALWAYS use `timezone.localdate(dt)`, NEVER `dt.date()`.
5. **Sample data**: After implementing any new feature/model, ALWAYS update `load_sample_data.py` to exercise it.
6. **iOS Safari**: Prefer standard CSS solutions over JS hacks for iOS quirks (e.g., `font-size: 16px` to prevent auto-zoom is fine; fighting native date pickers is not). If a first approach fails, stop and discuss. Always verify mobile changes on the iOS Simulator before shipping.
7. **Plan-first**: For any feature touching 3+ files, read the most similar existing feature and present a plan BEFORE writing code. Match the dynamic, DB-backed, editable pattern — not a simplified static version.

## Project Overview

**Control Center** is a self-hosted personal management system designed as a single-user command center for managing complex personal affairs. Accessed via VPN on a private server.

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
| Mobile Testing | iOS Simulator (Xcode 16.4) + safaridriver + Selenium |
| Deployment | Docker (Gunicorn + WhiteNoise) |

## Build & Run Commands

The dev server runs in **OrbStack Docker** on port 8000. For local development commands, see `.claude/docs/ARCHITECTURE.md`.

```bash
cp .env.example .env    # edit SECRET_KEY for production
docker compose up --build -d

# Run tests inside container
docker compose exec web python manage.py test

# Backup / restore
docker compose exec web python manage.py backup
docker compose exec web python manage.py restore /app/backups/<archive>.tar.gz

# Shell into container
docker compose exec web bash
```

## Apps & Architecture

Eight Django apps + one e2e test package, all relationally linked:

| App | Purpose |
|-----|---------|
| **dashboard** | Homepage, global search, timeline, calendar, notifications, settings hub, backup config |
| **stakeholders** | CRM — entity profiles, trust/risk ratings, relationships, contact logs; DB-backed tabs |
| **assets** | Unified `/assets/` page with DB-backed tabs; properties, investments, loans, insurance, vehicles, aircraft, leases |
| **legal** | Case status, attorneys (M2M), evidence, related stakeholders/assets |
| **tasks** | Deadlines, priorities, follow-ups, subtasks, kanban, recurring tasks, meetings |
| **cashflow** | Actual + projected inflows/outflows with category filtering and charts |
| **notes** | Searchable records linked to entities via M2M; tags, folders, 3 view modes |
| **healthcare** | Providers, medications, conditions, procedures, allergies, immunizations, insurance, vitals, appointments |
| **e2e** | Playwright browser tests — `StaticLiveServerTestCase` base |

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
- HTMX inline add/delete on asset detail pages AND stakeholder detail page (mirror pattern for all through models)
- Create forms include optional "Initial Owner/Participant" fields, hidden on edit via `get_form()` field deletion

### Important Gotchas
- **Local Python**: Use `source venv/bin/activate && python3` — no system-level Django installed
- **Config dir history**: `blaine/` was renamed to `config/` (settings, urls, wsgi, asgi, forms, export helpers)
- **Task test data**: Task form POST data requires `"direction": "personal"` or tests fail silently
- **Data migrations**: Use `apps.get_model()` for model access — direct imports crash in migrations
- **New templatetag dirs**: Must create `__init__.py` or Django silently fails to find tags
- **`dashboard/views.py`** needs `get_object_or_404` imported (not available by default)
- **Mobile modals**: Never use `flex-1 min-h-0` on modal form content — use `space-y-*` + `overflow-y-auto`
- **datetime-local on mobile**: Use `grid-cols-1 sm:grid-cols-2` + `w-fit` wrapper
- Dashboard views use lazy imports inside functions
- Forms use `__init__` override for dynamic widget/choices setup
- `Relationship`/`ContactLog`/`FollowUp` FKs use SET_NULL (not CASCADE) to prevent data loss on stakeholder deletion
- Tag/AssetTab slug collision: uniqueness loop generates `base-slug-1`, `-2`, etc.
- `bulk-actions.js` looks up `#select-all` dynamically and uses fully delegated change events (works after HTMX swaps)
- `switchView()` uses `source: form` (not `values: getFilterValues()`) for proper multi-select serialization
- Django test runner uses in-memory SQLite — WAL mode returns 'memory', not 'wal'
- Backup/restore tests must use temp file-based DBs, not the in-memory test DB
- E2E tests need `DJANGO_ALLOW_ASYNC_UNSAFE=true` (set in `e2e/base.py` setUp) for Playwright + LiveServerTestCase
- EasyMDE textarea hiding: in e2e tests, use mobile viewport or target `.EasyMDEContainer` instead of the hidden `<textarea>`
- `render_pdf()` signature: `render_pdf(request, filename, title, subtitle="", sections=None)`
- Investment model has no `status` field (unlike RealEstate, Loan, Vehicle, Aircraft)
- `Django 6.0.2 ManyRelatedManager not iterable`: Must call `.all()` before passing to template `{% for %}` loops

## Repository
- **Primary repo**: `https://github.com/bleomycin/Control-Center.git` (remote name: `origin`)
- The old `Nexus` repo is retired — do NOT push or sync to it
- There is only one remote (`origin`). If you see a `nexus` remote, remove it.

## Deployment
- After implementing features, always rebuild Docker and push GitHub release when the user asks. Standard deployment flow: run all tests → git push → docker build → push alpha release tag.
- **Production upgrade**: `upgrade.sh` in project root automates safe upgrades (backup → git pull → docker build → restart → health check → rollback on failure).

## Feature Implementation
- **Bundle deployment into feature completion**: A feature is not "done" until all tests pass, changes are committed and pushed to GitHub, Docker is rebuilt and verified running, and a new alpha release tag is created. Use `/deploy` skill when ready.
- **Test-driven iteration**: After each major component, write tests and run them before moving on.
- **Always work in parallel**: Maximize parallel tool calls and background agents. Run independent operations concurrently (tests + Docker rebuild, multiple file reads, research agents). Ask: "How many workers can I usefully run right now?"
- For detailed feature-specific patterns (Insurance, Loans, Calendar, Tasks, Notes, etc.), see `.claude/docs/ARCHITECTURE.md`.

## cmux Browser (Quick Dev Checks)

Use cmux for fast desktop-width visual checks during development. NOT for mobile testing (use iOS Simulator) or automated testing (use Playwright/e2e).

### Usage
```bash
cmux ping                                          # Check availability
cmux browser open http://localhost:8000             # Open in split pane
cmux browser --surface surface:N screenshot --out /tmp/shot.png  # Screenshot
cmux browser --surface surface:N snapshot --compact # DOM tree
cmux browser --surface surface:N click "ref"        # Click element
cmux browser --surface surface:N fill "sel" "text"  # Fill input
cmux browser --surface surface:N scroll --dy 500    # Scroll
cmux set-progress 0.75 --label "Testing 3/4"        # Sidebar progress
cmux notify --title "Done" --body "All tests passed" # Notification
```

If cmux is unavailable (`cmux ping` fails), fall back to Playwright for desktop visual checks. Surface IDs persist within a session — use `cmux tree` to list them.

## iOS Simulator (Mobile Verification)

Real Safari on real iOS via Xcode's simulator. Use for ALL mobile layout and behavior verification — replaces Playwright mobile emulation and WebKit pass.

### Devices
- **iPhone 16e** — matches user's iPhone Air (375pt width)
- **iPhone 16 Pro Max** — matches user's iPhone 17 Pro Max (440pt width)

### Quick commands
```bash
xcrun simctl boot "iPhone 16e"                      # Boot device
xcrun simctl ui booted appearance dark               # Dark mode
xcrun simctl openurl booted http://localhost:8000    # Open URL
xcrun simctl io booted screenshot /tmp/ios.png       # Screenshot
xcrun simctl shutdown all                            # Shutdown all
```

### Automated testing via safaridriver (scrolling, clicking, screenshotting)
```python
from selenium import webdriver
from selenium.webdriver.safari.options import Options

opts = Options()
opts.set_capability("platformName", "iOS")
opts.set_capability("browserName", "Safari")
opts.set_capability("safari:useSimulator", True)
opts.set_capability("safari:deviceName", "iPhone 16e")  # or "iPhone 16 Pro Max"

driver = webdriver.Safari(options=opts)
driver.get("http://localhost:8000")
driver.execute_script("window.scrollBy(0, 600)")
driver.save_screenshot("/tmp/ios.png")
scale = driver.execute_script("return window.visualViewport.scale")  # check zoom
driver.quit()
```

### Key notes
- `simctl` has NO touch/scroll input — use safaridriver + Selenium for interaction
- Leave simulators booted during dev sessions to avoid boot overhead
- Xcode 16.4 at `/Applications/Xcode.app` — iOS 18 runtime, iPhone 16 devices
