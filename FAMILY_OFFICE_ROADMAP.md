# Family Office Platform Roadmap

## Workflow Paradigm

**This is a principal-level family office tool, not a property management system.**

The family office does not manage properties, tenants, or investments directly on a day-to-day basis. Third-party property management companies, investment managers, syndicators, and business partners handle daily operations. The family office's role is:

1. **Receive and organize** — Monthly operating statements, quarterly investor reports, annual K-1s, appraisals, insurance certificates, and other paperwork flow in from managers and partners. The primary daily workflow is ingesting, filing, and tracking this incoming data.
2. **Monitor and evaluate** — Review manager reports for anomalies, compare performance across properties and managers, track key metrics over time to spot underperformance.
3. **Administer entities and compliance** — Manage the legal entity structure, track filing deadlines, handle tax planning (1031 exchanges, depreciation, basis tracking), maintain insurance coverage.
4. **Make strategic decisions** — Acquisitions, dispositions, refinancing, capital allocation across the portfolio. Evaluate new investment opportunities against portfolio concentration and return targets.
5. **Track obligations and deadlines** — Loan maturities, lease expirations, option dates, tax deadlines, entity filings, insurance renewals.

**Data flows IN from managers** — the system records summary-level financial data from PM operating statements and investor reports, not individual rent collections or maintenance invoices. Cashflow entries often represent aggregated figures from monthly reports, not granular transactions.

---

## Current State

Control Center currently excels at **task-centric personal management** — tracking tasks, stakeholders, legal matters, notes, and cashflow entries linked together. It has a solid foundation for a family office platform but significant gaps exist in financial reporting, entity structure, document management, and manager oversight workflows.

### What Exists Today
- Stakeholder CRM with trust/risk ratings, org hierarchy, relationship graphs, DB-backed tabs, firm_type classification
- Property tracking with 10 financial fields: estimated_value, equity, monthly_income, monthly_accrued_income, unreturned_capital, total_unreturned_capital, total_accrued_pref_return, deferred_gain, loan_balance_snapshot, income_source
- Syndication-aware fields already present: `unreturned_capital` (user's position), `total_unreturned_capital` (all investors), `total_accrued_pref_return`, `income_source` with values like "D" (distributions), "Above Pref", "Vacant"
- Investments (sparse: name, type, institution, current_value — no status, no cost basis, no dates)
- Loans with comprehensive debt terms: original_amount, current_balance, interest_rate, default_interest_rate, monthly_payment, maturity_date, is_hard_money, collateral
- Insurance policies with carrier/agent FKs, M2M to properties/vehicles/aircraft, coverage limits, deductibles, premium tracking
- Leases with monthly_rent, escalation_rate, renewal_type, status, security_deposit, rent_due_day
- Vehicles and aircraft with detailed specs, estimated values, multi-owner through models
- Legal matter management with attorney communications, evidence tracking, M2M to all 7 asset types
- Transaction-level cashflow (inflow/outflow, projected, recurring, DB-backed categories via `cashflow_category` ChoiceOption)
- Task management with follow-ups, subtasks, recurring tasks, kanban, meetings
- Cross-linked notes system touching every entity type (tags, folders, 3 view modes)
- Calendar with 7 event types (tasks, loan payments, follow-ups, legal hearings, appointments, rx refills, lease expiry) + ICS feed for iPhone/Google Calendar
- Dashboard aggregations: property count/value, investment count/value, active loan count/balance, 30-day unified deadlines
- Chart.js cashflow charts: 6-month inflow/outflow trend, top-8 category breakdown
- CSV + PDF exports (reportlab platypus) for individual records
- Multi-stakeholder ownership via 7 through models (PropertyOwnership, InvestmentParticipant, LoanParty, PolicyHolder, VehicleOwner, AircraftOwner, LeaseParty) — all with ownership_percentage + role + notes
- Liquidity alerts (negative net flow, large upcoming payments, projected shortfalls)

### What's Missing
The system tracks **individual transactions and tasks** but can't answer portfolio-level questions that a family office asks daily: *What's my net worth? What's my total debt exposure? Which properties are underperforming? When do my loans mature? What's my NOI by property? What entities own what? What's my total personal guarantee exposure? What's my adjusted tax basis? Which manager reports are overdue? How does PM Company A's expense ratio compare to PM Company B's?*

Critically, there's no structured workflow for the family office's **primary daily activity**: receiving, organizing, and extracting data from periodic reports sent by property managers, investment managers, and partners.

### Known Model Gaps (Pre-Requisites)
These field additions are needed by multiple roadmap features and should be addressed early:

- [ ] **RealEstate physical fields**: `purchase_price`, `square_footage`, `lot_size`, `year_built`, `units`, `zoning` — needed by 1.4, 1.5, 2.1, 2.4
- [ ] **RealEstate `property_type` as DB-backed choice**: Currently a free-text CharField. Add `property_type` to ChoiceOption categories (retail, office, industrial, multifamily, land, mixed_use) for consistent filtering and reporting
- [ ] **Investment model enrichment**: Add `status` (active, closed, pending), `cost_basis`, `acquisition_date`, `account_number`, `maturity_date` — currently only 4 fields
- [ ] **CashFlowEntry missing asset links**: Only links to Stakeholder, Property, Loan, Investment. Add FKs: `related_vehicle`, `related_aircraft`, `related_policy` — needed for vehicle maintenance costs, aircraft operating costs, insurance premium tracking
- [ ] **Cashflow category hierarchy**: Current `cashflow_category` is flat DB-backed choices. Need `category_group` field or `CashflowCategory` model to distinguish Income / Operating Expense / CapEx / Debt Service / Non-Operating — prerequisite for NOI calculation (see Architectural Considerations)

---

## Tier 1 — Foundation (Must-Have for Family Office)

### 1.1 Entity Structure Management
- [ ] **Not started** | Size: XL

**Problem:** CRE investors hold assets through LLCs, trusts, series LLCs, and holding companies. The system only has stakeholders (people and firms) — no concept of legal entities as asset-holding vehicles, and no ownership chain modeling.

**What exists:** Stakeholder model has `entity_type` (person, company, trust, etc.) and `parent_organization` FK for org hierarchy. `firm_type` classification exists. But these represent contacts/counterparties, not the user's own legal entities.

**What's needed:**
- [ ] New `Entity` model (or enhance Stakeholder) representing LLCs, trusts, S-corps, partnerships, sole proprietorships
- [ ] Fields: entity name, entity type, EIN/tax ID, formation date, formation state, registered agent, tax election (disregarded, partnership, S-corp)
- [ ] Operating agreement tracking: status (draft, executed, amended), key terms (distribution provisions, voting rights, capital call provisions), amendment history with dates
- [ ] Parent-child entity relationships (Holding LLC -> Property LLC -> Property)
- [ ] Ownership waterfall: Person -> 60% of Holding LLC -> 100% of Property LLC -> Property
- [ ] Annual filing deadline tracking per entity (state annual reports, franchise taxes) — integrate with existing calendar events system
- [ ] Registered agent renewal tracking
- [ ] Link to existing stakeholders as members/managers/officers (through model with role)
- [ ] Entity-level asset assignment: which entity holds which properties, investments, bank accounts
- [ ] Entity org chart visualization (tree/hierarchy view)

**Impact:** This is the structural backbone. Without entity modeling, you can't properly track who owns what through which structure — fundamental to CRE tax planning and liability protection.

### 1.2 Portfolio Financial Dashboard
- [ ] **Not started** | Size: L

**Problem:** The dashboard shows task counts and basic asset value totals. No consolidated financial picture beyond simple Sum aggregations.

**What exists:** Dashboard already computes: total property value (excluding sold), total investment value, total active loan balance, property/investment/loan counts. Cashflow charts show 6-month inflow/outflow trend and category breakdown. 30-day unified deadline widget combines tasks, loan payments, legal hearings, appointments.

**What's needed:**
- [ ] **Net worth summary**: Total asset values - total loan balances = net equity (combine existing aggregations into a single net worth card)
- [ ] **Portfolio breakdown**: By asset type (CRE, investments, vehicles, etc.) with Chart.js pie/bar charts
- [ ] **Debt summary**: Total debt, weighted average interest rate, upcoming maturities (next 6/12 months)
- [ ] **Income summary**: Monthly/annual rental income across all properties (aggregate `monthly_income` field + lease `monthly_rent`)
- [ ] **Key CRE metrics per property** (see 1.4)
- [ ] **Historical snapshots**: New `NetWorthSnapshot` model — monthly/quarterly snapshots of total assets, total liabilities, net equity. Automated via Django-Q2 scheduled task.
- [ ] **Concentration analysis**: Exposure by geography, property type, tenant, lender — pie charts with alert thresholds
- [ ] **Personal guarantee exposure**: Aggregate view of all loans where LoanParty role = "Guarantor" — total guarantee amount, by property, by lender

**Implementation notes:** Most data already exists — this is primarily aggregation expansion and Chart.js visualization. The dashboard view in `dashboard/views.py` (lines 63-80) already does basic `Sum` queries. Extend with computed metrics and chart endpoints similar to `cashflow/views.py` chart_data pattern.

### 1.3 Document Management & Report Intake
- [ ] **In progress — 5 of 6 milestones complete (M6: calendar alerts remaining)** | Size: XL

**Problem:** Evidence model handles legal documents only. No general-purpose document storage for leases, deeds, surveys, appraisals, tax returns, entity formation docs, insurance certificates, closing packages. More critically, there's no structured way to track the **inflow of periodic reports** from property managers, investment managers, and partners — the primary daily workflow of the family office.

**Storage strategy: Google Drive as file store, Control Center as metadata/intelligence layer** (see Architectural Considerations: Google Drive Integration for full analysis). Google Drive handles what it's good at — storage, sharing, collaboration, Google Workspace editing, mobile access. Control Center handles what Drive can't — categorization by entity, expiration alerts, report schedules, deadline tracking, and cross-entity search. Files live in Google Drive; the app stores references (Drive file IDs/URLs) plus rich metadata.

**Detailed implementation plan:** See `GDRIVE_INTEGRATION_PLAN.md` for milestone-by-milestone checklist, architecture diagram, failure mode matrix, and **Usage Guide** with step-by-step instructions.

#### How to Use (Quick Reference)

- **Documents page** → Sidebar → **Documents** (`/documents/`)
  - Search, filter by category/entity/expiration/date, sort columns, bulk select, CSV/PDF export
  - Click `+ New Document` to create, or click any row to view detail
- **Google Drive Setup** → Settings → **Google Drive** (`/documents/gdrive/settings/`)
  - Enter OAuth2 credentials → Connect → Picker becomes available on document forms
- **Google Picker** → On document create/edit form, click green **Pick from Google Drive** button
  - Selects a file → auto-fills URL, title, and metadata; manual URL paste always works as fallback
- **Entity linking** → On any entity detail page (Property, Investment, etc.), scroll to **Documents** section
  - `+ Add` links an existing document; `New Document` creates one pre-linked to that entity
- **Drive URLs on evidence/attachments** → Legal evidence, communications, note attachments, and healthcare test results all have optional "Google Drive URL" fields alongside their file uploads

#### Completed Milestones

**Milestone 1 — Documents app foundation (no Google):** ✅ **COMPLETE** (2026-03-09)
- [x] `Document` model with 20+ fields: title, category (DB-backed, 15 values), description, date, expiration_date, Drive metadata (`gdrive_file_id`, `gdrive_url`, `gdrive_mime_type`, `gdrive_file_name`), local `file` (FileField fallback), notes_text, 9 nullable entity FKs, timestamps
- [x] Computed properties: `has_drive_link`, `has_file`, `file_url`, `linked_entities`, `is_expired`, `is_expiring_soon`
- [x] Full CRUD: list (HTMX search/filter/sort), detail (Drive link, entity links, notes), create/edit (entity linking, Drive URL), delete
- [x] Filters: search (title/description/filename), category, entity type (9 types + "unlinked"), expiration (soon/expired), date range, sortable columns
- [x] Bulk actions: select-all + per-row checkboxes, bulk delete, bulk CSV export
- [x] Exports: CSV (all + bulk, includes Drive columns), PDF (single doc reportlab)
- [x] Expiration color coding: red=expired, amber=≤90 days. Mobile responsive layout.
- [x] 10 sample documents, 15 document categories, sidebar nav link, 44 unit tests
- [x] **Files:** 16 created, 7 modified

**Milestone 2 — Google Drive Settings + OAuth2:** ✅ **COMPLETE** (2026-03-09)
- [x] `documents/gdrive.py` — single abstraction layer for ALL Google API calls (10 public functions)
- [x] Settings page (`/documents/gdrive/settings/`) with credential form, setup instructions, callback URL
- [x] OAuth2 flow: Connect → Google consent screen → callback → store tokens + connected email
- [x] Connection status banner (green=connected with email, gray=not connected)
- [x] Disconnect (revokes tokens), Test Connection (verify endpoint), auto token refresh
- [x] Settings hub card (emerald theme) linking to Drive settings
- [x] Password masking: client_secret and api_key show "Leave blank to keep current" on re-visit
- [x] 26 new unit tests
- [x] **Files:** 2 created, 7 modified

**Milestone 3 — Google Picker integration:** ✅ **COMPLETE** (2026-03-09)
- [x] `static/js/gdrive-picker.js` — self-contained Picker wrapper (~180 lines, vanilla JS)
- [x] Reusable `_gdrive_picker.html` partial: Picker button + selected file feedback + error display
- [x] Picker token endpoint (`GET /documents/api/picker-token/`) — returns fresh access token JSON (403 when disconnected)
- [x] `GDriveContextMixin` on Create/Update views — injects `drive_connected`, `drive_api_key`, `drive_client_id`
- [x] Auto-populate: title (filename minus extension), URL, hidden metadata fields (file_id, mime_type, file_name)
- [x] Conditional rendering: Picker visible only when Drive connected AND api_key set; manual URL always available
- [x] Edit mode: existing Drive data auto-shows selected file feedback on page load
- [x] Error handling: loading spinner → error message → button re-enabled with original text
- [x] 13 new tests
- [x] **Files:** 1 created, 6 modified

**Milestone 4 — Existing model migration (gdrive_url on 4 models):** ✅ **COMPLETE** (2026-03-09)
- [x] `gdrive_url` (URLField) + `has_drive_link` property added to: Evidence, LegalCommunication, Attachment, TestResult
- [x] Notes Attachment `file` changed to `blank=True` — allows Drive-only attachments (form validates: file OR gdrive_url required)
- [x] All 4 forms updated with gdrive_url field; 7 templates updated: green Drive links (cloud icon) alongside blue file links
- [x] 3 migrations (`legal/0008`, `notes/0010`, `healthcare/0005`), 12 new unit tests
- [x] Sample data: 5/9 evidence items + 3/5 communications have example Drive URLs
- [x] **Files:** 3 created, 14 modified

**Milestone 5 — Entity detail page integration:** ✅ **COMPLETE** (2026-03-09)
- [x] "Documents (N)" section on all 9 entity detail pages: Property, Investment, Loan, Lease, Policy, Vehicle, Aircraft, Stakeholder, Legal Matter
- [x] HTMX link/unlink: `+ Add` dropdown to link existing, `New Document` creates pre-linked, `×` to unlink (inline, no page reload)
- [x] 2 reusable partials (`_document_link_form.html`, `_document_list_section.html`) + generic view helpers (`ENTITY_CONFIG` dict)
- [x] 18 link/unlink URL patterns, 15 new unit tests
- [x] **Files:** 2 created, 12 modified

**Milestone 5b — Global search + UX polish:** ✅ **COMPLETE** (2026-03-09)
- [x] Documents appear in global search (`/search/`) — matches title, description, category
- [x] Search results: category label, date, Drive indicator (cloud icon), expiration badges
- [x] Mobile unlink button: always visible on touch devices (was hover-only)
- [x] 2 expiration sample docs, 2 new categories (15 total), 2 new unit tests

#### Remaining

**Milestone 6 — Expiration alerts + calendar:** ⬜ Not started
- [ ] Document expiration events in calendar (`calendar_events()`)
- [ ] Expiring documents in 30-day dashboard deadline widget
- [ ] CalendarFeedSettings: add `documents` event type
- [ ] ICS feed includes document expirations

#### Pages Touched (Summary)

New pages: Document list, detail, create/edit, delete confirm, CSV/PDF export, Drive settings, OAuth flow (4 endpoints), Picker token API, 18 link/unlink endpoints.

Modified pages: Sidebar, Settings hub, Global search results, 9 entity detail pages (Property, Investment, Loan, Lease, Policy, Vehicle, Aircraft, Stakeholder, Legal Matter), 4 evidence/attachment form templates, 4 evidence/attachment list templates, 1 test result detail template.

See `GDRIVE_INTEGRATION_PLAN.md` → "Pages & URLs Affected" for the complete URL table.

#### Test Coverage
- **1199 unit tests** + **140 e2e tests** — all passing (as of latest verification)
- Documents app: ~100 unit tests covering model, views, forms, filters, exports, Drive settings, OAuth, Picker, entity linking

**What's needed — periodic report tracking (future, post-Milestone 6):**
- [ ] New `ReportSchedule` model: manager (FK to Stakeholder), report_type (operating_statement, investor_report, k1, capital_account_statement, rent_roll, budget, tax_return), frequency (monthly, quarterly, annually), expected_day (day of month/quarter typically received), related assets (M2M to properties/investments)
- [ ] New `ReportReceipt` model (or extend Document): schedule FK, period_covered (date range), date_received, status (expected, received, overdue, reviewed), document FK (link to received file in Drive), key_figures (JSONField — store extracted numbers like NOI, occupancy, distributions for trend tracking)
- [ ] **Overdue report alerts**: Flag when expected reports haven't been received by their due date + grace period. Calendar integration.
- [ ] **Report dashboard**: Which reports are expected this month, which have been received, which are overdue. By manager, by property.
- [ ] **Trend extraction**: When recording key figures from received reports (NOI, occupancy rate, cash distributions), store them for period-over-period comparison and anomaly flagging.

**Impact:** Every CRE transaction generates dozens of documents, and every managed property generates monthly/quarterly reports. The report intake workflow is the family office's primary daily interaction with its investments — currently completely untracked. Google Drive integration means professionals and partners can contribute directly to shared folders without needing app access.

### 1.4 Enhanced Property Financial Metrics
- [ ] **Not started** | Size: L

**Problem:** Properties have 10 financial fields but no computed metrics. The system stores snapshots but doesn't calculate the ratios CRE professionals use daily.

**What exists:** RealEstate has estimated_value, equity, monthly_income, monthly_accrued_income, loan_balance_snapshot plus syndication fields. CashFlowEntry links to properties. Loans link to properties via `related_property` FK.

**Pre-requisite:** Cashflow category hierarchy (see Known Model Gaps) — must distinguish operating expenses from debt service and capex for NOI calculation.

**What's needed — new RealEstate fields:**
- [ ] `purchase_price` (DecimalField) — original acquisition cost, distinct from estimated_value which changes
- [ ] `total_cash_invested` (DecimalField) — down payment + closing costs + improvements
- [ ] `square_footage` (IntegerField) — total building SF
- [ ] `lot_size` (DecimalField) — acres or SF
- [ ] `year_built` (PositiveIntegerField)
- [ ] `units` (PositiveIntegerField) — number of units/suites (1 for single-tenant NNN, N for multifamily/multi-tenant)
- [ ] `zoning` (CharField) — zoning designation
- [ ] `parking_spaces` (PositiveIntegerField)

**What's needed — computed metrics (property detail page + comparison view):**
- [ ] **NOI (Net Operating Income)**: Sum of rental income cashflows - sum of operating expense cashflows for a property over a period. Requires cashflow category hierarchy.
- [ ] **Cap Rate**: NOI / estimated_value
- [ ] **Cash-on-Cash Return**: Annual pre-tax cash flow / total_cash_invested
- [ ] **DSCR (Debt Service Coverage Ratio)**: NOI / Annual Debt Service (sum of monthly_payment on linked loans * 12)
- [ ] **LTV (Loan-to-Value)**: Sum of linked loan current_balance / estimated_value
- [ ] **Equity Multiple**: Total distributions received / total_cash_invested
- [ ] **Gross Rent Multiplier**: purchase_price / gross annual rental income
- [ ] **Price per SF**: purchase_price / square_footage
- [ ] **Price per Unit**: purchase_price / units
- [ ] **Occupancy Rate**: Occupied units (active leases) / total units
- [ ] Property financial summary partial on detail page showing all computed metrics
- [ ] Comparison table view across all properties (sortable by any metric)

**Implementation notes:** Some metrics (LTV, price/SF, price/unit) are purely computed from stored fields. Others like NOI and cap rate may come from two sources: (1) computed from cashflow entries if granular data is entered, or (2) recorded directly from PM operating statements via the report intake workflow (1.3). The system should support both — manual metric entry from a received report AND auto-computation from cashflow data, with manual entry taking precedence when available. Consider a `@property` or utility function approach for computed metrics rather than stored fields, with optional override fields for PM-reported values.

### 1.5 Rent Roll View
- [ ] **Not started** | Size: M

**Problem:** Leases exist but there's no consolidated "rent roll" — the single most important document in CRE.

**What exists:** Lease model with monthly_rent, escalation_rate, renewal_type, status, security_deposit, start_date, end_date, rent_due_day. LeaseParty through model for tenant/landlord roles. `is_expiring_soon` computed property (60 days). Leases link to properties via `related_property` FK.

**Workflow note:** Rent roll data originates from PM companies. The family office receives updated rent rolls and maintains them in the system for lender requests, refinancing packages, and strategic analysis (lease expiration exposure, tenant concentration). Lease details are entered/updated when new leases are signed or when PM reports show changes.

**What's needed — new Lease model fields:**
- [ ] `unit_number` or `suite` (CharField) — which unit in a multi-tenant property
- [ ] `square_footage` (IntegerField) — leased area for this unit
- [ ] `lease_structure` (CharField) — gross, modified gross, NNN, absolute NNN (DB-backed choice)
- [ ] `cam_charges` (DecimalField) — monthly CAM/NNN charges
- [ ] `base_rent` (DecimalField) — vs monthly_rent which may include extras; or rename existing `monthly_rent` to `base_rent` and add `effective_rent`
- [ ] `tenant_improvement_allowance` (DecimalField) — TI dollars
- [ ] `free_rent_months` (IntegerField) — concession tracking
- [ ] `option_rent` (DecimalField) — rent during renewal option period
- [ ] `option_notice_date` (DateField) — deadline to exercise renewal option
- [ ] `early_termination_date` (DateField) — earliest tenant can terminate
- [ ] `early_termination_fee` (DecimalField)

**What's needed — rent roll views:**
- [ ] Portfolio-wide rent roll page: all active leases across all properties in one table
- [ ] Columns: property, tenant (via LeaseParty), unit/suite, lease start, lease end, monthly rent, annual rent, rent/SF, escalation rate, renewal type, status
- [ ] Sortable/filterable by property, expiration date, rent amount
- [ ] Lease expiration schedule: visual timeline or table of upcoming expirations (30/60/90/180/365 days)
- [ ] Vacancy tracking: units/properties without active leases (requires property `units` field from 1.4)
- [ ] Rent roll PDF export (lender/appraiser format)

**Impact:** The rent roll is what you provide to lenders, appraisers, and potential buyers. It's the family office's consolidated view of tenant obligations across the portfolio — critical for refinancing packages and disposition marketing.

### 1.6 Debt Maturity & Capital Stack
- [ ] **Not started** | Size: M

**Problem:** Loans have maturity dates but there's no visual timeline or per-property capital stack view.

**What exists:** Loan model has maturity_date, current_balance, interest_rate, original_amount, monthly_payment, is_hard_money, collateral, status. LoanParty through model captures Lender, Borrower, Guarantor roles with ownership_percentage. Loans link to properties/investments/vehicles/aircraft.

**What's needed — new Loan model fields:**
- [ ] `loan_type` (CharField, DB-backed choice) — permanent, bridge, construction, line of credit, mezzanine, SBA
- [ ] `rate_type` (CharField) — fixed, variable, ARM
- [ ] `arm_index` (CharField) — SOFR, Prime, Treasury (only if rate_type = ARM/variable)
- [ ] `arm_margin` (DecimalField) — spread over index
- [ ] `rate_floor` (DecimalField) — minimum rate
- [ ] `rate_cap` (DecimalField) — maximum rate
- [ ] `prepayment_terms` (TextField) — penalty structure (yield maintenance, defeasance, step-down, open)
- [ ] `ltv_at_origination` (DecimalField) — original LTV for comparison to current
- [ ] `covenants` (TextField) — DSCR minimums, LTV maximums, reserve requirements
- [ ] `refinance_status` (CharField) — not_started, shopping, term_sheet, in_process, closed
- [ ] `io_period_end` (DateField) — end of interest-only period (common in CRE)
- [ ] `personal_guarantee` (BooleanField) — whether personally guaranteed (currently only tracked as LoanParty role text)
- [ ] `guarantee_amount` (DecimalField) — dollar amount of personal guarantee (may differ from loan balance)

**What's needed — views:**
- [ ] **Debt maturity timeline**: Chart.js bar chart showing all loan maturities across portfolio, grouped by year. Color-code by loan type. Highlight concentration risk.
- [ ] **Per-property capital stack visualization**: Stacked bar showing equity vs senior debt vs mezzanine vs preferred equity.
- [ ] **Refinance planning dashboard**: Flag loans maturing within 6/12/18 months, track refinance_status. Table with countdown timers.
- [ ] **Personal guarantee exposure summary**: Total guarantee amount across all loans, broken out by property/lender. Alert if total exposure exceeds threshold.
- [ ] **Interest rate exposure**: Split between fixed vs variable rate debt. Impact analysis if rates change +1%/+2%.

### 1.7 Tax & Compliance Tracking
- [ ] **Not started** | Size: XL

**Problem:** Tax planning is the #1 reason CRE investors use family offices. The system has no tax-specific features.

**What's needed:**
- [ ] **1031 Exchange tracker** (new `Exchange1031` model):
  - [ ] Relinquished property (FK to RealEstate), sale_date, sale_price
  - [ ] 45-day identification deadline (auto-calculated from sale_date)
  - [ ] 180-day close deadline (auto-calculated from sale_date)
  - [ ] Identified replacement properties (M2M or child model, up to 3 per three-property rule or 200% rule)
  - [ ] Exchange accommodator (FK to Stakeholder)
  - [ ] Status: identification_period, acquisition_period, completed, failed, boot_recognized
  - [ ] Boot amount (if partial exchange)
  - [ ] Calendar integration for deadlines (add to existing calendar_events system)
  - [ ] Replacement property acquired (FK to RealEstate, set on completion)

- [ ] **Tax basis tracking per property** (new fields on RealEstate or new `PropertyTaxBasis` model):
  - [ ] `purchase_price` (shared with 1.4)
  - [ ] `land_value` (non-depreciable portion)
  - [ ] `building_value` (depreciable portion = purchase_price - land_value)
  - [ ] `total_improvements` (accumulated capital improvements)
  - [ ] `accumulated_depreciation`
  - [ ] `adjusted_basis` = purchase_price + improvements - accumulated_depreciation
  - [ ] Depreciation method: straight-line 27.5yr (residential) / 39yr (commercial)
  - [ ] Annual depreciation amount (auto-calculated)
  - [ ] Remaining depreciable life
  - [ ] Optional: cost segregation study results with accelerated components (5yr, 7yr, 15yr personal property, 15yr land improvements)

- [ ] **Tax deadline tracking**:
  - [ ] Estimated tax payments (quarterly) — calendar events
  - [ ] Entity-level filing deadlines (K-1s due Mar 15, 1065/1120S due Mar 15, extensions to Sep 15)
  - [ ] Property tax payment dates per jurisdiction (semi-annual in most states)
  - [ ] Calendar integration for all deadlines

- [ ] **Tax document collection** (new `TaxDocumentChecklist` model):
  - [ ] Track which K-1s, 1099s, W-2s, and statements have been received per tax year per entity
  - [ ] Status: not_received, received, sent_to_cpa, filed
  - [ ] Dashboard showing completion percentage per tax year

**Impact:** Missing a 1031 exchange deadline means hundreds of thousands in unnecessary taxes. Missing an entity filing means penalties or dissolution. These are high-stakes, non-negotiable deadlines.

### 1.8 Syndication & Fund Tracking
- [ ] **Not started** | Size: L

**Problem:** The existing RealEstate fields (`unreturned_capital`, `total_accrued_pref_return`, `income_source` with values "D", "Above Pref", "Vacant") clearly show syndication/LP participation. But there's no structured way to track capital accounts, distributions, waterfall positions, or fund-level reporting across syndication investments.

**Workflow note:** As an LP/passive investor in syndications, the family office receives quarterly investor statements and annual K-1s from sponsors/GPs. The primary workflow is recording data from these received statements — capital account balances, distributions received, accrued preferred returns, and K-1 tax allocations. The family office does not manage the waterfall — it tracks its position within it based on what sponsors report.

**What exists:** RealEstate has syndication-aware fields. InvestmentParticipant tracks ownership_percentage and role. But no capital call/distribution tracking, no waterfall position monitoring, no K-1 income allocation.

**What's needed:**
- [ ] **Capital account tracking** (new `CapitalAccount` model or fields on through models):
  - [ ] Initial capital contribution
  - [ ] Additional capital calls (with dates, amounts, status: called, funded, past_due)
  - [ ] Distributions received (with dates, amounts, type: return_of_capital, preferred_return, profit_share)
  - [ ] Current capital account balance
  - [ ] Unreturned capital (auto-calculated: contributions - return_of_capital distributions)

- [ ] **Waterfall position tracking** (record from sponsor statements, not modeled):
  - [ ] Preferred return rate and accrued amount
  - [ ] Current position in waterfall (returning capital, paying pref, above pref) — maps to existing `income_source` values ("D", "Above Pref")
  - [ ] Promote/carried interest structure notes (text — terms of the deal)

- [ ] **Fund/syndication summary view**:
  - [ ] All syndication investments in one view
  - [ ] IRR calculation (if distribution dates are tracked)
  - [ ] Equity multiple: total distributions / total contributions
  - [ ] K-1 income allocation tracking per year (ordinary income, capital gains, depreciation, Sec 199A)

**Impact:** Without this, syndication investments are black boxes — you can see a current value but not how you got there or what your actual returns are.

---

## Tier 2 — High Value (Major Quality-of-Life Improvements)

### 2.1 Transaction Pipeline (Acquisitions & Dispositions)
- [ ] **Not started** | Size: L

**Problem:** No structured way to track deals from identification through closing.

**Workflow note:** The family office evaluates deals and makes go/no-go decisions, but brokers, attorneys, title companies, and lenders handle the transaction mechanics. This pipeline tracks the family office's decision points and deadlines, not the execution details. Due diligence items are delegated to professionals — the family office tracks completion status, not the work itself.

**What's needed:**
- [ ] New `Deal` model: title, deal_type (acquisition, disposition, refinance), status (identified, LOI, due_diligence, under_contract, closing, closed, dead), target property or new property details
- [ ] Financial underwriting fields: asking_price, offer_price, projected_noi, target_cap_rate, projected_cash_on_cash, projected_irr
- [ ] Due diligence checklist (subtask-like via existing Task system): environmental, title, survey, inspection, zoning, financials review, estoppels
- [ ] Key dates: loi_date, contract_date, inspection_deadline, financing_contingency_deadline, closing_date — all feed into calendar events
- [ ] Related stakeholders via through model: seller/buyer, broker, attorney, lender, inspector, title company
- [ ] Pipeline view (kanban-style) showing deals by stage — similar to existing task kanban
- [ ] Conversion to property record on close (auto-populate RealEstate from deal data including purchase_price)
- [ ] For dispositions: link to existing property, track listing price, offers received, buyer info, 1031 exchange trigger

### 2.2 Budget vs Actuals Monitoring
- [ ] **Not started** | Size: M

**Problem:** PM companies create annual operating budgets and send monthly/quarterly variance reports. The family office has no way to record, track, or compare these budgets against actual results across the portfolio.

**Workflow note:** The family office does NOT create operating budgets — PM companies do. The family office receives the approved budget, records the key line items, then monitors PM variance reports throughout the year to evaluate manager performance and flag anomalies. This is an oversight tool, not a budgeting tool.

**Pre-requisite:** Cashflow category hierarchy (see Known Model Gaps).

**What's needed:**
- [ ] New `PropertyBudget` model: property FK, year, budget_type (operating, capex), source/manager (FK to Stakeholder — which PM prepared this budget), approved_date
- [ ] `BudgetLineItem` model: budget FK, category (matching cashflow category hierarchy), monthly amounts (Jan-Dec fields or 12 child records), annual total
- [ ] Dashboard showing: budgeted vs actual by category, variance analysis ($ and %), YTD tracking
- [ ] Traffic light indicators: green (under budget), yellow (within 10%), red (over budget)
- [ ] Year-over-year comparison — spot trends in expense growth
- [ ] Cross-manager comparison — compare expense ratios and NOI margins across PM companies managing different properties

### 2.3 Enhanced Insurance & Claims
- [ ] **Not started** | Size: M

**Problem:** Insurance policies tracked but no claims management, COI tracking, or coverage gap analysis.

**What exists:** InsurancePolicy with carrier/agent FKs, coverage_limit, deductible, premium, M2M to properties/vehicles/aircraft, PolicyHolder through model, status, expiration_date.

**What's needed:**
- [ ] New `InsuranceClaim` model: policy FK, claim_number, date_of_loss, date_filed, description, claimed_amount, settled_amount, status (filed, under_review, approved, denied, settled, closed), adjuster (FK to Stakeholder), related_property (optional FK)
- [ ] COI tracking: which tenants/contractors have provided certificates, expiration dates, required limits vs actual limits (could be a `COICertificate` model linked to Stakeholder + InsurancePolicy)
- [ ] Coverage analysis view: by property, show all applicable policies, identify gaps (property without liability coverage, vehicle without collision, etc.)
- [ ] Renewal pipeline: policies expiring in 30/60/90 days — leverage existing `expiration_date` field
- [ ] Premium cost summary: total annual premiums across all policies, broken out by type

### 2.4 Property Valuation History
- [ ] **Not started** | Size: S

**Problem:** Properties have a single `estimated_value` field. No way to track value changes over time.

**What's needed:**
- [ ] New `PropertyValuation` model: property FK, date, value, valuation_method (appraisal, broker_opinion, tax_assessment, internal_estimate, purchase_price), source/appraiser (FK to Stakeholder), notes, document (optional FK to Document — links to appraisal PDF in Google Drive)
- [ ] Auto-create initial valuation record when `purchase_price` is set (1.4)
- [ ] Auto-update `estimated_value` on RealEstate when new valuation is added (latest valuation becomes current value)
- [ ] Value trend chart on property detail page (Chart.js line chart)
- [ ] Portfolio value trend on dashboard
- [ ] Unrealized gain/loss calculation: current estimated_value - adjusted_basis (from 1.7)

### 2.5 Reporting Engine
- [ ] **Not started** | Size: L

**Problem:** CSV and PDF exports exist for individual records but no portfolio-level financial reports.

**What exists:** `config/pdf_export.py` with `render_pdf()` supporting info/table/text section types. CSV export via `config/export.py`. Individual record PDF/CSV exports on detail pages.

**What's needed:**
- [ ] **Property P&L Report**: Income - expenses = NOI for a date range, per property or portfolio-wide. Generated from cashflow entries + category hierarchy.
- [ ] **Portfolio Summary Report**: All properties with key metrics in a table (value, debt, equity, NOI, cap rate, occupancy)
- [ ] **Debt Schedule Report**: All loans with terms, balances, payments, maturities, rate type
- [ ] **Rent Roll Report**: Exportable rent roll (PDF and CSV) — lender-ready format
- [ ] **Cash Flow Projection Report**: Forward-looking projected cashflows by month (use existing `is_projected` and `is_recurring` fields to extrapolate)
- [ ] **Net Worth Statement**: Assets - liabilities snapshot, comparable to prior periods (uses 1.2 snapshot data)
- [ ] **Personal Guarantee Summary**: All guaranteed loans with amounts, properties, lenders
- [ ] **Entity Structure Report**: Ownership hierarchy with assets held per entity (requires 1.1)
- [ ] Scheduled report generation (monthly/quarterly) via Django-Q2
- [ ] Report archive — store generated reports for historical comparison

### 2.6 Bank Account Tracking
- [ ] **Not started** | Size: M

**Problem:** Cashflow tracks transactions but not account balances. No way to see "how much cash do I have?"

**What's needed:**
- [ ] New `BankAccount` model: name, institution (FK to Stakeholder or CharField), account_type (operating, reserve, escrow, investment, personal, tax_escrow), account_number_last4 (CharField, 4 digits only — never store full account numbers), current_balance, related_property (optional FK), related_entity (optional FK if 1.1 is built)
- [ ] `BankAccountBalance` model for historical tracking: account FK, date, balance — monthly snapshots
- [ ] Manual balance updates or reconciliation workflow
- [ ] Account-level cashflow linking: add `related_account` FK to CashFlowEntry (which account did this come from/go to?)
- [ ] Cash position summary on dashboard: total cash across all accounts, broken out by type
- [ ] Escrow/reserve account tracking: track escrow balances for tax, insurance, capex reserves per property

---

## Tier 3 — Enhancement (Nice-to-Have)

### 3.1 Manager & Partner Performance Monitoring
- [ ] **Not started** | Size: M

**Problem:** The family office delegates daily management to PM companies, investment managers, and business partners, but has no structured way to evaluate their performance or compare managers against each other.

- [ ] **Manager assignment tracking**: Which PM company manages which properties, which investment manager oversees which funds (extend Stakeholder or use through model linking managers to assets)
- [ ] **Fee structure tracking**: Management fee percentage or flat fee per manager per property, incentive fee structures
- [ ] **Performance scorecard**: Per manager — average occupancy rate, expense ratio, NOI margin, tenant retention, report timeliness (from 1.3 report tracking). Compare same metrics across different managers.
- [ ] **Fee analysis**: Total management fees paid per year per manager, fees as percentage of gross revenue
- [ ] **Contract tracking**: Management agreement terms, expiration dates, renewal/termination notice periods

### 3.2 CapEx Approval & Tracking
- [ ] **Not started** | Size: S

**Problem:** PM companies request approval for capital expenditures above a threshold. The family office needs to track these requests, approvals, and actual spend.

- [ ] `CapExRequest` model: property FK, requested_by (FK to Stakeholder/PM), description, category (roof, HVAC, parking, TI, etc.), estimated_cost, status (requested, approved, denied, completed), actual_cost, date_requested, date_approved, date_completed
- [ ] Link to CashFlowEntry on completion
- [ ] Budget vs actual for approved capex projects
- [ ] Annual capex summary per property (feeds into budget monitoring in 2.2)

### 3.3 Communication Templates
- [ ] **Not started** | Size: S

**Workflow note:** Tenant-facing communications (rent increases, lease renewals) are handled by PM companies. Family office communications are to lenders, attorneys, CPAs, exchange intermediaries, and occasionally direct to managers/partners.

- [ ] Template library for family office level letters: 1031 exchange identification letter, estoppel request (for acquisitions/dispositions), demand letter (via attorney), lender correspondence, investor correspondence
- [ ] Variable substitution (entity name, property address, dates, amounts, EIN)
- [ ] PDF generation from templates (extend existing reportlab infrastructure)

### 3.4 Market Data & Comps
- [ ] **Not started** | Size: M
- [ ] `Comparable` model: address, sale/lease date, price/rent, cap rate, price per SF, property type, source, notes
- [ ] Linked to properties for valuation support (M2M)
- [ ] Market rent tracking for lease renewal negotiations
- [ ] Submarket/area tracking

### 3.5 Consolidated Critical Deadlines
- [ ] **Not started** | Size: S
- [ ] Beyond the existing 30-day dashboard widget: a dedicated deadlines page with configurable horizons (30/60/90/180/365 days)
- [ ] Combines: loan maturities, lease expirations, insurance renewals, entity filing deadlines, 1031 exchange deadlines, option exercise dates, tax payment dates
- [ ] Color-coded by urgency and category
- [ ] Export to PDF for team meetings

### 3.6 Forward-Looking Cash Projection
- [ ] **Not started** | Size: M
- [ ] 12-month forward cash flow projection based on:
  - [ ] Known recurring cashflow entries (existing `is_recurring` + `recurrence_rule`)
  - [ ] Scheduled loan payments (existing `monthly_payment` + `next_payment_date`)
  - [ ] Expected rental income (from active leases `monthly_rent`)
  - [ ] Projected entries (existing `is_projected` flag)
- [ ] Month-by-month waterfall showing beginning balance -> inflows -> outflows -> ending balance
- [ ] Highlight months with negative projected cash flow
- [ ] Scenario modeling: what-if a property goes vacant, what-if rates increase

---

## Implementation Priority & Dependencies

```
Phase 1 (Foundation — field additions + views from existing data)
├── Known Model Gaps (pre-requisites)     ← field additions, migrations
├── 1.2 Portfolio Financial Dashboard [L] ← aggregation + Chart.js, mostly existing data
├── 1.4 Enhanced Property Metrics [L]     ← new fields on RealEstate + computed metrics
├── 1.5 Rent Roll View [M]               ← new fields on Lease + new view/template
└── 1.6 Debt Maturity Timeline [M]       ← new fields on Loan + Chart.js visualization

Phase 2 (Structure — new models)
├── 1.1 Entity Structure [XL]            ← new Entity model, touches stakeholders + assets
├── 1.3 Document Mgmt & Report Intake [XL] ← new app, core daily workflow
├── 1.7 Tax & Compliance [XL]            ← new models, calendar integration
└── 1.8 Syndication & Fund Tracking [L]  ← new models, extends existing syndication fields

Phase 3 (Operations — oversight depth)
├── 2.1 Transaction Pipeline [L]         ← new Deal model, kanban view
├── 2.2 Budget vs Actuals Monitoring [M] ← record PM budgets, track variance reports
├── 2.4 Property Valuation History [S]   ← simple new model, Chart.js
└── 2.6 Bank Account Tracking [M]        ← new model, ties to cashflow

Phase 4 (Reporting & Polish)
├── 2.5 Reporting Engine [L]             ← aggregates all prior phases
├── 2.3 Enhanced Insurance [M]           ← extends existing insurance model
├── 3.1 Manager Performance [M]          ← evaluate PM companies + investment managers
├── 3.5 Consolidated Deadlines [S]       ← aggregates calendar events
├── 3.6 Cash Projection [M]             ← extends existing cashflow data
└── Tier 3 remaining items as needed
```

**Phase 1 adds fields to existing models** (RealEstate, Lease, Loan, CashFlowEntry) plus new views and Chart.js visualizations. No new Django apps. Migrations required for field additions. This is where to start for immediate value.

**Phase 2 introduces new models** that restructure how ownership and documents are tracked. Entity structure touches many existing models (stakeholders relate to entities, entities own assets). Document management with report intake tracking is the backbone of the daily oversight workflow. Tax compliance adds calendar deadline integrations.

**Phase 3 adds oversight depth** — deal tracking, PM budget monitoring, valuations, bank accounts. Each is relatively standalone.

**Phase 4 ties it all together** with comprehensive reporting that pulls from all prior phases.

---

## Architectural Considerations

### Google Drive Integration

**Decision: Use Google Drive as the file store. Control Center is the metadata and intelligence layer. This is the right approach.**

**Why not local-only storage (current state):**
- Files trapped inside Docker volume, only accessible through the app via VPN
- No sharing with business partners, attorneys, CPAs, or PM companies — they'd need app access
- No Google Workspace tools (Docs, Sheets) for viewing/editing/commenting
- No mobile access without VPN
- Inferior versioning compared to Drive's built-in history
- Backup is another thing to manage (Drive handles it natively)

**Why not rclone:**
rclone solves a different problem (backup/sync). It fails this use case because:
- FUSE mounts inside Docker containers are unreliable and add operational complexity
- No access to Google Drive file IDs or shareable links from the app
- Can't manage sharing permissions programmatically
- Can't embed Google Picker for file selection in the UI
- Bidirectional sync conflicts are a real risk when files are modified on both sides
- Latency on large directories makes it feel sluggish
- rclone IS useful as a backup tool (sync Drive to local), but not as the primary integration

**Why not keep them completely separate:**
- Defeats the entire document management feature — can't have expiration alerts, report tracking, or entity linking without the app knowing about the files
- Double data entry (manually tracking in Drive AND in the app)
- No way to answer "show me all documents for 1200 Oak Avenue" without manually searching Drive
- No overdue report detection

**Recommended architecture — Google Drive API (phased):**

The app stores **references** to Google Drive files (file ID + URL) plus metadata that Drive can't provide (entity links, categories, expiration dates, report periods). Google Drive handles storage, sharing, collaboration, and mobile access.

**Phase A — Link-based (no API dependency):**
- `Document` model stores `gdrive_url` (URLField) — user pastes Google Drive sharing links
- App stores metadata: category, dates, entity FKs, expiration alerts
- Existing FileField models (Evidence, LegalCommunication, Attachment, TestResult) get optional `gdrive_url` field
- Template shows Drive link as clickable button alongside any local file
- User manually organizes folders in Google Drive
- Zero API dependency, zero OAuth complexity, immediate value

**Phase B — Google Picker + API:**
- Add `google-api-python-client` and `google-auth-oauthlib` to requirements
- OAuth2 flow: user authorizes Control Center to access their Drive (one-time setup in Settings)
- Store OAuth refresh token encrypted in DB (or use service account with domain-wide delegation for Workspace)
- Embed [Google Picker API](https://developers.google.com/drive/picker) (JavaScript widget) in document forms — user browses Drive, selects file, app auto-captures file ID + name + MIME type + URL
- App can read file metadata (size, modified date, sharing status) from API
- Generate shareable links programmatically when needed

**Phase C — Managed folder structure:**
- App creates and maintains a canonical folder hierarchy in Google Drive:
```
Family Office/
├── Properties/
│   ├── 1200 Oak Avenue/
│   │   ├── Acquisition & Closing/
│   │   ├── Leases/
│   │   ├── Operating Statements/
│   │   │   ├── 2024/
│   │   │   └── 2025/
│   │   ├── Insurance/
│   │   ├── Appraisals & Valuations/
│   │   ├── Tax Records/
│   │   └── Correspondence/
│   └── 450 Elm Street/
│       └── ...
├── Entities/
│   ├── Holding LLC/
│   │   ├── Formation/
│   │   ├── Operating Agreements/
│   │   ├── Tax Returns/
│   │   └── Annual Filings/
│   └── ...
├── Investments/
│   ├── Fund A/
│   │   ├── Subscription Docs/
│   │   ├── Investor Reports/
│   │   ├── K-1s/
│   │   └── Capital Calls & Distributions/
│   └── ...
├── Loans/
│   ├── First National - 1200 Oak/
│   │   ├── Loan Documents/
│   │   └── Statements/
│   └── ...
├── Legal/
│   └── [Matter Name]/
├── Insurance/
│   └── [Policy Name]/
├── Tax/
│   ├── 2024/
│   ├── 2025/
│   └── 1031 Exchanges/
└── Shared With/
    ├── CPA - Armanino/
    └── Attorney - Smith & Jones/
```
- When a new property/entity/investment is created in the app, auto-create the corresponding Drive folder
- When a document is uploaded through the app, push it to the correct Drive folder based on entity links and category
- Poll designated folders (or use Drive push notifications) to detect files added directly in Drive by partners/PMs — prompt user to categorize and link them in the app
- Folder names stay in sync with entity names in the app

**Existing local FileField migration path:**
Currently 4 models store files locally:
- `legal.Evidence.file` → `evidence/`
- `legal.LegalCommunication.file` → `communications/`
- `notes.Attachment.file` → `attachments/`
- `healthcare.TestResult.file` → `test_results/`

Migration approach: Add `gdrive_url` field to each model alongside existing `file` field. Templates show whichever is populated (Drive link preferred over local file). Over time, move existing local files to Drive and update records. Never break existing local file access — the `file` field remains for backwards compatibility and as a fallback.

**API rate limits:** Google Drive API allows 20,000 queries/100 seconds per user. A single-user family office will never approach this. Not a concern.

**Security note:** OAuth2 refresh tokens must be stored encrypted. Consider `django-encrypted-model-fields` or similar. Service account approach (for Google Workspace) avoids per-user OAuth entirely.

### Cashflow Category Structure
The current `cashflow_category` is a flat DB-backed choice field (ChoiceOption category). For proper financial reporting, categories need hierarchy:
- **Income**: Rental Income, CAM Reimbursements, Late Fees, Percentage Rent, Other Income
- **Operating Expenses**: Property Tax, Insurance, Utilities, Repairs & Maintenance, Management Fees, Landscaping, Legal, Accounting, Advertising, HOA/CAM
- **Capital Expenditures**: Roof, HVAC, Parking Lot, Tenant Improvements, Building Systems
- **Debt Service**: Principal, Interest (ideally auto-split from loan monthly_payment)
- **Non-Operating**: Acquisition Costs, Disposition Costs, Owner Distributions, Capital Contributions

This categorization is what enables NOI calculation (Income - OpEx, excluding debt service and capex). **Recommended approach:** Add a `category_group` CharField to CashFlowEntry with choices (income, opex, capex, debt_service, non_operating). Each cashflow_category value maps to exactly one group. This is simpler than a hierarchical CashflowCategory model and preserves the existing DB-backed choice pattern.

**Workflow note on cashflow data entry:** Many cashflow entries will be summary-level figures from PM operating statements and investment manager reports, not individual tenant payments or vendor invoices. Example: a PM sends a monthly operating statement showing $45,000 gross rent collected and $12,000 in operating expenses — the family office records two cashflow entries, not 30 individual transactions. The category hierarchy must work at this summary level.

### Property Type Specialization
Commercial real estate subtypes have different metrics:
- **Retail/NNN**: Tenant name (already exists as `tenant` field), lease structure, CAM charges, percentage rent
- **Multifamily**: Unit count, unit mix, vacancy rate, rent per unit
- **Office**: Rentable SF, usable SF, load factor, parking ratio
- **Industrial**: Clear height, dock doors, power capacity, yard space
- **Land**: Acreage, zoning, entitlements, development potential

The current `property_type` field is a free-text CharField (max_length=100). **Recommended:** Make it a DB-backed ChoiceOption category for consistent filtering. Type-specific fields can be handled by making most fields nullable — a retail property won't use `units` and a multifamily won't use `tenant`, but both fields can coexist on the model.

### Existing Syndication Fields Reference
The RealEstate model already has syndication-aware fields that should be preserved and extended:
- `equity` — "314SG equity position" (user's equity in the deal)
- `unreturned_capital` — "314SG unreturned capital" (user's unreturned capital)
- `total_unreturned_capital` — all-investors unreturned capital
- `total_accrued_pref_return` — accrued preferred return across all investors
- `income_source` — values include "D" (distributing), "Above Pref" (above preferred return in waterfall), "Vacant"
- `deferred_gain` — future tax liability (likely from 1031 exchange)
- `loan_balance_snapshot` — outstanding loan at time of import

These fields suggest a portfolio imported from a spreadsheet or fund admin/sponsor report — consistent with the LP/passive investor workflow where the family office records data received from sponsors and managers. Section 1.8 should formalize this into proper models rather than flat fields, while preserving the workflow of "record from received report" rather than "compute from scratch."

### Audit Trail
Family offices need accountability. Consider adding:
- `created_by` / `updated_by` fields on financial records
- Change history for critical fields (property value, loan balance, entity ownership changes)
- Currently single-user so low urgency, but important if access is ever shared with accountants/attorneys
- Django's `django-simple-history` package could provide this with minimal effort

### Model Naming Conventions
When adding new models, follow existing patterns:
- Through models: `{Asset}+{Role}` (e.g., PropertyOwnership, LoanParty, LeaseParty)
- Asset FKs on CashFlowEntry: `related_{asset_type}` with SET_NULL
- Status fields: CharField with STATUS_CHOICES tuple on the model class
- Financial amounts: DecimalField(max_digits=14, decimal_places=2) for dollar amounts
- Percentages: DecimalField(max_digits=5, decimal_places=2) or max_digits=6, decimal_places=3 for rates
