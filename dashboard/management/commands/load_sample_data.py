"""
Management command to populate Control Center with comprehensive sample data.
Usage: python manage.py load_sample_data [--sections stakeholders assets ...]
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from stakeholders.models import Stakeholder, Relationship, ContactLog
from assets.models import (
    Aircraft, AircraftOwner, InsurancePolicy, Investment, Lease, LeaseParty,
    Loan, PolicyHolder, RealEstate, Vehicle, VehicleOwner,
)
from legal.models import LegalChecklistItem, LegalCommunication, LegalMatter, Evidence
from tasks.models import Task, FollowUp
from cashflow.models import CashFlowEntry
from notes.models import Folder, Note, Tag
from healthcare.models import (
    Provider, Condition, Prescription, Supplement, TestResult,
    Visit, Advice, Appointment,
)
from documents.models import Document


# Canonical section order and labels
SECTION_ORDER = [
    "stakeholders", "assets", "legal", "tasks", "cashflow", "notes", "healthcare",
    "documents",
]
SECTION_LABELS = {
    "stakeholders": "Stakeholders",
    "assets": "Assets",
    "legal": "Legal",
    "tasks": "Tasks",
    "cashflow": "Cash Flow",
    "notes": "Notes",
    "healthcare": "Healthcare",
    "documents": "Documents",
}

# Which sections depend on which others (for loading)
SECTION_DEPS = {
    "stakeholders": [],
    "assets": ["stakeholders"],
    "legal": ["stakeholders", "assets"],
    "tasks": ["stakeholders"],
    "cashflow": ["stakeholders"],
    "notes": [],
    "healthcare": [],
    "documents": ["stakeholders", "assets", "legal"],
}

# Deletion order per section (children before parents within each section)
SECTION_DELETION_ORDER = {
    "healthcare": [
        "healthcare.appointment", "healthcare.advice", "healthcare.visit",
        "healthcare.testresult", "healthcare.supplement", "healthcare.prescription",
        "healthcare.condition", "healthcare.provider",
    ],
    "notes": ["notes.note", "notes.tag", "notes.folder"],
    "cashflow": ["cashflow.cashflowentry"],
    "tasks": ["tasks.followup", "tasks.task"],
    "legal": ["legal.legalcommunication", "legal.evidence", "legal.legalmatter"],
    "assets": [
        "assets.leaseparty", "assets.lease", "assets.policyholder",
        "assets.insurancepolicy", "assets.aircraftowner", "assets.vehicleowner",
        "assets.loanparty", "assets.investmentparticipant", "assets.propertyownership",
        "assets.aircraft", "assets.vehicle", "assets.loan", "assets.investment",
        "assets.realestate",
    ],
    "stakeholders": [
        "stakeholders.contactlog", "stakeholders.relationship",
        "stakeholders.stakeholder",
    ],
    "documents": ["documents.document"],
}

# ---------------------------------------------------------------------------
# Known sample data identifiers — used by clean_sample_data for safe removal.
# When adding new sample records, add their names/titles here too.
# ---------------------------------------------------------------------------
SAMPLE_NAMES = {
    "stakeholders": {
        "Marcus Reed", "Sandra Liu", "Tom Driscoll", "Janet Cobb",
        "Derek Vasquez", "Karen Whitfield", "Ray Holston", "Nina Patel",
        "Victor Huang", "Alicia Moreno", "James Calloway", "Dr. Helen Park",
        "Armanino LLP", "Sarah Chen", "Michael Torres", "Lisa Park",
        "National Property Ins",
    },
    "properties": {
        "1200 Oak Avenue", "450 Elm Street", "3300 Magnolia Blvd",
        "890 Cedar Lane", "15 Riverside Dr",
        "7-Eleven - 509 Bates Ave", "7-Eleven - 10710 W Loop",
        "Dollar Tree - 2100 Main St",
    },
    "investments": {
        "Vanguard Total Market Index", "Schwab S&P 500 ETF",
        "Municipal Bond Fund", "NP Investments LP - Fund II",
        "Bitcoin Holdings",
    },
    "loans": {
        "First National - Oak Ave Mortgage", "First National - Elm St Mortgage",
        "Huang Bridge Loan - Magnolia", "Vehicle Loan - F-150",
    },
    "vehicles": {
        "2023 Ford F-150 Lariat", "2021 Toyota Land Cruiser",
        "2019 Harley-Davidson Road King", "2022 Sea Ray 250 SLX",
    },
    "aircraft": {
        "N172SP — Cessna 172 Skyhawk", "N525BL — Cessna Citation CJ3+",
        "N44RH — Robinson R44 Raven II",
    },
    "insurance": {
        "Homeowners - 1200 Oak Ave", "Commercial Property - Magnolia Blvd",
        "Umbrella Policy", "Auto Policy - Fleet",
    },
    "leases": {
        "Oak Ave Residential Lease", "Elm St Unit A Lease",
        "Elm St Unit B Lease", "Magnolia Commercial Lease",
    },
    "legal_matters": {
        "Holston Eviction - 1200 Oak Ave", "Cedar Lane Boundary Dispute",
        "Magnolia Blvd Acquisition - Due Diligence",
        "Riverside Zoning Application", "Estate Plan Update",
    },
    "tasks": {
        "Follow up with Marcus on Holston hearing date",
        "Pay Oak Ave mortgage", "Pay Elm St mortgage",
        "Schedule roof inspection - Elm St",
        "Review Magnolia closing documents",
        "Refinance Huang bridge loan",
        "Prepare zoning hearing materials",
        "Quarterly portfolio review follow-up",
        "Send Holston back rent to collections",
        "Oak Ave bathroom renovation check-in",
        "Update estate plan documents",
        "Review Q4 Elm St expense report",
        "Pay Huang bridge loan interest",
        "File property tax protest - Cedar Lane",
        "Research Bitcoin exit strategy",
        "Request Polaris Risk background report via Armanino",
        "Request 2024 Elm St transaction review",
        "Request Magnolia Blvd tax review",
        "Schedule meeting with Michael Torres",
        "Send Oak Ave receipts to Sarah",
        "Contact Nina about entity formation",
    },
    "notes": {
        "Holston eviction strategy call with Marcus",
        "Magnolia Blvd walkthrough notes",
        "Quarterly portfolio review with Derek",
        "Cedar Lane mediation prep",
        "Elm St roof concerns",
        "Estate planning meeting notes",
        "Huang bridge loan terms review",
        "Riverside development feasibility",
        "Call with Tom about Elm St expenses",
        "Quick note - Bitcoin price alert",
    },
    "cashflow": {
        "Oak Ave rent received", "Elm St Unit A rent", "Elm St Unit B rent",
        "Oak Ave mortgage payment", "Elm St mortgage payment",
        "Huang bridge loan interest", "Vehicle loan payment",
        "Property insurance - Oak Ave", "Property insurance - Elm St",
        "Reed & Associates retainer", "Calloway - Oak Ave renovation",
        "Vanguard monthly investment", "Whitfield appraisal fee",
        "Magnolia closing - down payment", "Magnolia closing - closing costs",
        "Expected Oak Ave rent - March", "Expected Elm St rent - March",
        "Oak Ave mortgage - March", "Elm St mortgage - March",
        "Huang bridge interest - March",
        "NP Investments annual distribution", "Property tax - all properties",
    },
    "tags": {"legal", "finance", "property", "meeting-notes", "action-item", "research"},
    "folders": {"Legal", "Properties", "Investments", "Meetings", "Healthcare"},
    "providers": {
        "Dr. Sarah Mitchell", "Dr. James Wong", "Dr. Emily Chen",
        "Dr. Michael Torres", "Dr. Lisa Pham",
    },
    "conditions": {"Essential Hypertension", "Seasonal Allergies"},
    "prescriptions": {"Lisinopril", "Atorvastatin", "Amoxicillin"},
    "supplements": {"Vitamin D3", "Fish Oil (Omega-3)", "Magnesium Glycinate"},
    "documents": {
        "Oak Ave Property Deed", "Elm St Property Deed",
        "2024 Federal Tax Return", "2024 State Tax Return",
        "Oak Ave Homeowners Insurance Certificate",
        "NP Investments LP - Operating Agreement",
        "Magnolia Blvd Appraisal Report",
        "Q4 2024 Elm St Operating Statement",
        "Elm St Business License",
        "Magnolia Blvd Phase I ESA Report",
    },
}


def _get_sample_stakeholders():
    """Return dict of sample stakeholders by name, or empty dict if none loaded."""
    from dashboard.models import SampleDataStatus
    status = SampleDataStatus.load()
    pks = status.manifest.get("stakeholders", {}).get("stakeholders.stakeholder", [])
    if not pks:
        return {}
    return {s.name: s for s in Stakeholder.objects.filter(pk__in=pks)}


def _get_sample_properties():
    from dashboard.models import SampleDataStatus
    status = SampleDataStatus.load()
    pks = status.manifest.get("assets", {}).get("assets.realestate", [])
    if not pks:
        return {}
    return {p.name: p for p in RealEstate.objects.filter(pk__in=pks)}


def _get_sample_investments():
    from dashboard.models import SampleDataStatus
    status = SampleDataStatus.load()
    pks = status.manifest.get("assets", {}).get("assets.investment", [])
    if not pks:
        return {}
    return {i.name: i for i in Investment.objects.filter(pk__in=pks)}


def _get_sample_loans():
    from dashboard.models import SampleDataStatus
    status = SampleDataStatus.load()
    pks = status.manifest.get("assets", {}).get("assets.loan", [])
    if not pks:
        return {}
    return {ln.name: ln for ln in Loan.objects.filter(pk__in=pks)}


def _get_sample_vehicles():
    from dashboard.models import SampleDataStatus
    status = SampleDataStatus.load()
    pks = status.manifest.get("assets", {}).get("assets.vehicle", [])
    if not pks:
        return {}
    return {v.name: v for v in Vehicle.objects.filter(pk__in=pks)}


def _get_sample_legal_matters():
    from dashboard.models import SampleDataStatus
    status = SampleDataStatus.load()
    pks = status.manifest.get("legal", {}).get("legal.legalmatter", [])
    if not pks:
        return {}
    return {lm.title: lm for lm in LegalMatter.objects.filter(pk__in=pks)}


def _get_sample_tasks():
    from dashboard.models import SampleDataStatus
    status = SampleDataStatus.load()
    pks = status.manifest.get("tasks", {}).get("tasks.task", [])
    if not pks:
        return {}
    return {t.title: t for t in Task.objects.filter(pk__in=pks)}


def _get_sample_leases():
    from dashboard.models import SampleDataStatus
    status = SampleDataStatus.load()
    pks = status.manifest.get("assets", {}).get("assets.lease", [])
    if not pks:
        return {}
    return {l.name: l for l in Lease.objects.filter(pk__in=pks)}


def _get_sample_insurance():
    from dashboard.models import SampleDataStatus
    status = SampleDataStatus.load()
    pks = status.manifest.get("assets", {}).get("assets.insurancepolicy", [])
    if not pks:
        return {}
    return {p.name: p for p in InsurancePolicy.objects.filter(pk__in=pks)}


class Command(BaseCommand):
    help = "Load comprehensive sample data for demo purposes"

    def add_arguments(self, parser):
        parser.add_argument(
            "--sections", nargs="+", choices=SECTION_ORDER,
            help="Sections to load (default: all). Options: " + ", ".join(SECTION_ORDER),
        )
        parser.add_argument(
            "--hard-reset", action="store_true",
            help="Delete ALL data from sample-data models and reset manifest. "
                 "Use when sample data is corrupted or duplicated.",
        )

    def handle(self, *args, **options):
        from dashboard.models import SampleDataStatus

        if options.get("hard_reset"):
            return self._hard_reset()

        sample_status = SampleDataStatus.load()
        sections = options.get("sections") or SECTION_ORDER

        # Check which sections are already loaded
        already_loaded = [s for s in sections if sample_status.manifest.get(s)]
        if already_loaded:
            self.stdout.write(self.style.WARNING(
                f"Already loaded: {', '.join(already_loaded)}. Remove first before reloading."
            ))
            sections = [s for s in sections if s not in already_loaded]
            if not sections:
                return

        today = timezone.localdate()
        now = timezone.now()

        # Seed choices (always, idempotent)
        self.stdout.write("Seeding choice options...")
        from dashboard.models import ChoiceOption
        from dashboard.choice_seed_data import SEED_DATA
        for category, value, label, sort_order in SEED_DATA:
            ChoiceOption.objects.get_or_create(
                category=category, value=value,
                defaults={"label": label, "sort_order": sort_order},
            )

        for section in sections:
            loader = getattr(self, f"_load_{section}")
            manifest = loader(today, now)
            sample_status.manifest[section] = manifest
            # Save after each section so cross-section helpers (e.g.
            # _get_sample_stakeholders) see the latest manifest from DB.
            sample_status.save()
            self.stdout.write(self.style.SUCCESS(f"  Loaded {SECTION_LABELS[section]}"))

        sample_status.is_loaded = any(sample_status.manifest.get(s) for s in SECTION_ORDER)
        sample_status.loaded_at = timezone.now()
        sample_status.save()

        # Print summary
        for section in sections:
            m = sample_status.manifest.get(section, {})
            total = sum(len(v) for v in m.values())
            self.stdout.write(f"  {SECTION_LABELS[section]}: {total} records")

        self.stdout.write(self.style.SUCCESS("Done."))

    def _hard_reset(self):
        """Delete ALL records from every model used by sample data, reset manifest."""
        from django.apps import apps
        from dashboard.models import SampleDataStatus

        self.stdout.write(self.style.WARNING("Hard reset: deleting ALL data from sample-data models..."))

        # Delete in dependency order (children first)
        all_models_ordered = []
        for section in reversed(SECTION_ORDER):
            all_models_ordered.extend(SECTION_DELETION_ORDER.get(section, []))

        for model_label in all_models_ordered:
            Model = apps.get_model(model_label)
            count = Model.objects.count()
            if count:
                Model.objects.all().delete()
                self.stdout.write(f"  Deleted {count} {model_label} records")

        # Reset the manifest
        status = SampleDataStatus.load()
        status.manifest = {}
        status.is_loaded = False
        status.loaded_at = None
        status.save()

        self.stdout.write(self.style.SUCCESS("Hard reset complete. All sample-data models emptied, manifest cleared."))

    # -----------------------------------------------------------------------
    # STAKEHOLDERS
    # -----------------------------------------------------------------------
    def _load_stakeholders(self, today, now):
        from assets.models import PropertyOwnership  # noqa: F811 - needed for manifest

        self.stdout.write("Creating stakeholders...")
        stakeholders = {}
        data = [
            ("Marcus Reed", "attorney", "marcus.reed@reedlaw.com", "555-201-4400", "Reed & Associates", 5, 1,
             "Primary litigation attorney. Very responsive, bills fairly."),
            ("Sandra Liu", "attorney", "sliu@liulegal.com", "555-303-7100", "Liu Legal Group", 4, 1,
             "Real estate transactional attorney. Handles all closings."),
            ("Tom Driscoll", "business_partner", "tom@driscollventures.com", "555-817-2200", "Driscoll Ventures LLC", 3, 3,
             "50/50 partner on Elm St property. Has been slow to respond lately."),
            ("Janet Cobb", "lender", "jcobb@firstnational.com", "555-422-8000", "First National Bank", 4, 2,
             "Loan officer handling the commercial mortgage. Good relationship."),
            ("Derek Vasquez", "advisor", "derek@vfinancial.com", "555-610-3300", "Vasquez Financial Advisory", 5, 1,
             "Financial advisor managing investment portfolio. Quarterly reviews."),
            ("Karen Whitfield", "professional", "kwhitfield@appraisalco.com", "555-774-1500", "Whitfield Appraisals", 4, 1,
             "Licensed appraiser. Used for property valuations."),
            ("Ray Holston", "contact", "ray.holston@email.com", "555-229-6600", "", 2, 4,
             "Former tenant at Oak Ave. Owes back rent. Unresponsive."),
            ("Nina Patel", "business_partner", "nina@npinvestments.com", "555-888-4100", "NP Investments", 4, 2,
             "Co-investor on Magnolia portfolio. Reliable so far."),
            ("Victor Huang", "lender", "vhuang@privatelending.com", "555-316-9200", "Huang Private Lending", 3, 3,
             "Private money lender. High rates but fast closes. Use cautiously."),
            ("Alicia Moreno", "professional", "amoreno@titlefirst.com", "555-502-7700", "Title First Agency", 5, 1,
             "Title agent handling all closings. Extremely thorough."),
            ("James Calloway", "contact", "james.c@email.com", "555-119-3400", "Calloway Construction", 3, 2,
             "General contractor. Good work but missed deadlines on Oak Ave renovation."),
            ("Dr. Helen Park", "advisor", "hpark@estateplanning.com", "555-667-4800", "Park Estate Planning", 5, 1,
             "Estate planning attorney. Handles trust and succession planning."),
        ]
        for name, etype, email, phone, org, trust, risk, notes in data:
            s = Stakeholder.objects.create(
                name=name, entity_type=etype, email=email, phone=phone,
                organization=org, trust_rating=trust, risk_rating=risk, notes_text=notes,
            )
            stakeholders[name] = s

        # Firm: Armanino LLP
        armanino = Stakeholder.objects.create(
            name="Armanino LLP", entity_type="firm", firm_type="accounting",
            email="info@armanino.com", phone="555-700-1000",
            website="https://www.armanino.com",
            organization="", trust_rating=5, risk_rating=1,
            notes_text="Full-service accounting and consulting firm. Handles family office services, "
                       "forensic accounting, tax preparation, and advisory.",
        )
        stakeholders["Armanino LLP"] = armanino

        employee_data = [
            ("Sarah Chen", "professional", "schen@armanino.com", "555-700-1001",
             "Senior account manager. Primary day-to-day contact for all matters."),
            ("Michael Torres", "professional", "mtorres@armanino.com", "555-700-1002",
             "Partner. Oversees the family office engagement. Quarterly strategic reviews."),
            ("Lisa Park", "professional", "lpark@armanino.com", "555-700-1003",
             "Forensic accounting specialist. Handles transaction analysis and due diligence reviews."),
        ]
        for name, etype, email, phone, notes in employee_data:
            emp = Stakeholder.objects.create(
                name=name, entity_type=etype, email=email, phone=phone,
                parent_organization=armanino, trust_rating=5, risk_rating=1,
                notes_text=notes,
            )
            stakeholders[name] = emp

        self.stdout.write("Creating relationships...")
        rels = [
            ("Marcus Reed", "Sandra Liu", "colleague", "Both in legal, refer work to each other"),
            ("Tom Driscoll", "Nina Patel", "business associate", "Have co-invested before"),
            ("Janet Cobb", "Alicia Moreno", "professional contact", "Bank refers title work to her"),
            ("Derek Vasquez", "Dr. Helen Park", "referral partner", "Cross-refer wealth management clients"),
            ("James Calloway", "Tom Driscoll", "contractor", "Calloway does rehab work for Driscoll projects"),
            ("Michael Torres", "Derek Vasquez", "professional contact", "Coordinate on tax and investment strategy"),
            ("Lisa Park", "Marcus Reed", "professional contact", "Collaborate on forensic financial analysis for litigation"),
        ]
        for f, t, rtype, desc in rels:
            Relationship.objects.create(
                from_stakeholder=stakeholders[f], to_stakeholder=stakeholders[t],
                relationship_type=rtype, description=desc,
            )

        self.stdout.write("Creating contact logs...")
        logs = [
            ("Marcus Reed", -2, "call", "Discussed status of Holston eviction. Filing motion next week.", True, 7),
            ("Marcus Reed", -15, "email", "Sent updated retainer agreement. Awaiting signature.", False, None),
            ("Sandra Liu", -5, "meeting", "Reviewed closing docs for Magnolia Blvd. All clear to proceed.", False, None),
            ("Tom Driscoll", -8, "call", "Left voicemail about Elm St maintenance issues. No answer.", True, 3),
            ("Tom Driscoll", -22, "email", "Sent Q4 expense report for Elm St property.", False, None),
            ("Janet Cobb", -3, "call", "Confirmed next mortgage payment dates. No issues.", False, None),
            ("Derek Vasquez", -1, "meeting", "Quarterly portfolio review. Recommended shifting 10% to bonds.", False, None),
            ("Ray Holston", -10, "call", "Attempted contact re: outstanding balance. No answer.", True, 5),
            ("Ray Holston", -30, "email", "Sent formal demand letter for $4,200 in back rent.", True, 14),
            ("Nina Patel", -6, "email", "Discussed potential acquisition of 440 Birch St.", False, None),
            ("James Calloway", -4, "call", "Got updated timeline for bathroom renovation. 2 weeks out.", True, 14),
            ("Karen Whitfield", -12, "email", "Requested appraisal for 1200 Oak Ave. Scheduled for next week.", False, None),
            ("Alicia Moreno", -7, "call", "Title search on Magnolia property is clean. Ready for closing.", False, None),
            ("Dr. Helen Park", -20, "meeting", "Annual trust review. Updated beneficiary designations.", False, None),
        ]
        for name, days_ago, method, summary, followup, fu_days in logs:
            ContactLog.objects.create(
                stakeholder=stakeholders[name],
                date=now + timedelta(days=days_ago),
                method=method, summary=summary,
                follow_up_needed=followup,
                follow_up_date=today + timedelta(days=fu_days) if fu_days else None,
            )

        return {
            "stakeholders.stakeholder": [s.pk for s in stakeholders.values()],
            "stakeholders.relationship": list(
                Relationship.objects.filter(
                    from_stakeholder__in=stakeholders.values()
                ).values_list("pk", flat=True)
            ),
            "stakeholders.contactlog": list(
                ContactLog.objects.filter(
                    stakeholder__in=stakeholders.values()
                ).values_list("pk", flat=True)
            ),
        }

    # -----------------------------------------------------------------------
    # ASSETS
    # -----------------------------------------------------------------------
    def _load_assets(self, today, now):
        from assets.models import PropertyOwnership, InvestmentParticipant, LoanParty

        stakeholders = _get_sample_stakeholders()

        self.stdout.write("Creating real estate...")
        properties = {}
        prop_data = [
            ("1200 Oak Avenue", "", "1200 Oak Ave, Austin, TX 78701", "Travis County, TX", "Single Family",
             Decimal("385000.00"), today - timedelta(days=730), "owned",
             "Rental property. Currently undergoing bathroom renovation. Tenant issues with Ray Holston.",
             []),
            ("450 Elm Street", "", "450 Elm St, Austin, TX 78702", "Travis County, TX", "Duplex",
             Decimal("520000.00"), today - timedelta(days=1095), "owned",
             "Co-owned 50/50 with Tom Driscoll. Both units rented. Needs roof inspection.",
             [("Tom Driscoll", Decimal("50.00"), "Co-owner")]),
            ("3300 Magnolia Blvd", "", "3300 Magnolia Blvd, San Antonio, TX 78205", "Bexar County, TX", "Commercial",
             Decimal("1250000.00"), None, "under_contract",
             "Under contract. Closing scheduled for next month. Co-investing with Nina Patel.",
             [("Nina Patel", Decimal("50.00"), "Co-investor")]),
            ("890 Cedar Lane", "", "890 Cedar Ln, Dallas, TX 75201", "Dallas County, TX", "Single Family",
             Decimal("275000.00"), today - timedelta(days=1460), "in_dispute",
             "Property boundary dispute with neighbor. Marcus Reed handling litigation.",
             []),
            ("15 Riverside Dr", "", "15 Riverside Dr, Houston, TX 77001", "Harris County, TX", "Vacant Land",
             Decimal("180000.00"), today - timedelta(days=365), "owned",
             "Undeveloped lot. Zoning permits under review for residential development.",
             []),
            ("7-Eleven - 509 Bates Ave", "7-Eleven", "509 Bates Ave, San Antonio, TX 78204", "Bexar County, TX", "Commercial",
             Decimal("836000.00"), today - timedelta(days=500), "owned",
             "NNN lease. 15 year term remaining.",
             [], {
                 "equity": Decimal("168396.00"),
                 "monthly_income": Decimal("1098.00"),
                 "loan_balance_snapshot": Decimal("445054.00"),
                 "unreturned_capital": Decimal("991973.00"),
                 "total_unreturned_capital": Decimal("1283000.00"),
                 "total_accrued_pref_return": Decimal("202415.00"),
                 "income_source": "D",
             }),
            ("7-Eleven - 10710 W Loop", "7-Eleven", "10710 W Loop 1604 N, San Antonio, TX 78254", "Bexar County, TX", "Commercial",
             Decimal("2800000.00"), today - timedelta(days=400), "owned",
             "NNN lease. High traffic corner lot.",
             [], {
                 "equity": Decimal("512000.00"),
                 "monthly_income": Decimal("3450.00"),
                 "monthly_accrued_income": Decimal("5515.00"),
                 "loan_balance_snapshot": Decimal("1890000.00"),
                 "unreturned_capital": Decimal("1650000.00"),
                 "total_unreturned_capital": Decimal("2100000.00"),
                 "total_accrued_pref_return": Decimal("98750.00"),
                 "income_source": "D",
             }),
            ("Dollar Tree - 2100 Main St", "Dollar Tree", "2100 Main St, Houston, TX 77002", "Harris County, TX", "Commercial",
             Decimal("650000.00"), today - timedelta(days=300), "owned",
             "NNN lease. 10 year term.",
             [], {
                 "equity": Decimal("95200.00"),
                 "monthly_income": Decimal("875.00"),
                 "loan_balance_snapshot": Decimal("380000.00"),
                 "unreturned_capital": Decimal("540000.00"),
                 "income_source": "D",
             }),
        ]
        for name, tenant, addr, juris, ptype, val, acq, status, notes, owners, *rest in prop_data:
            financials = rest[0] if rest else {}
            p = RealEstate.objects.create(
                name=name, tenant=tenant, address=addr, jurisdiction=juris, property_type=ptype,
                estimated_value=val, acquisition_date=acq, status=status, notes_text=notes,
                **financials,
            )
            properties[name] = p
            for owner_name, percentage, role in owners:
                if owner_name in stakeholders:
                    PropertyOwnership.objects.create(
                        property=p, stakeholder=stakeholders[owner_name],
                        ownership_percentage=percentage, role=role
                    )

        if "Tom Driscoll" in stakeholders and "450 Elm Street" in properties:
            PropertyOwnership.objects.create(
                property=properties["450 Elm Street"],
                stakeholder=stakeholders["Tom Driscoll"],
                role="Contractor",
                notes="Handling renovation project on Unit B",
            )

        self.stdout.write("Creating investments...")
        investments = {}
        inv_data = [
            ("Vanguard Total Market Index", "Index Fund", "Vanguard", Decimal("142500.00"),
             "Core holding. Dollar-cost averaging $2k/month.",
             [("Derek Vasquez", None, "Advisor")]),
            ("Schwab S&P 500 ETF", "ETF", "Charles Schwab", Decimal("87300.00"),
             "Large cap exposure. Rebalance quarterly.",
             [("Derek Vasquez", None, "Advisor")]),
            ("Municipal Bond Fund", "Bond Fund", "Fidelity", Decimal("65000.00"),
             "Tax-advantaged income. Added per advisor recommendation.",
             [("Derek Vasquez", None, "Advisor")]),
            ("NP Investments LP - Fund II", "Private Equity", "NP Investments", Decimal("50000.00"),
             "Committed $50k to Nina's real estate fund. 3-year lockup. Annual distributions.",
             [("Nina Patel", None, "Fund Manager")]),
            ("Bitcoin Holdings", "Cryptocurrency", "Coinbase", Decimal("22400.00"),
             "Speculative position. 0.35 BTC. Consider taking profits if above $70k.",
             []),
        ]
        for name, itype, inst, val, notes, participants in inv_data:
            inv = Investment.objects.create(
                name=name, investment_type=itype, institution=inst, current_value=val, notes_text=notes,
            )
            investments[name] = inv
            for participant_name, percentage, role in participants:
                if participant_name in stakeholders:
                    InvestmentParticipant.objects.create(
                        investment=inv, stakeholder=stakeholders[participant_name],
                        ownership_percentage=percentage, role=role
                    )

        self.stdout.write("Creating loans...")
        loans = {}
        loan_data = [
            ("First National - Oak Ave Mortgage", "Owner (personal)",
             Decimal("320000.00"), Decimal("285400.00"), Decimal("4.750"), None, False,
             Decimal("2100.00"), today + timedelta(days=22), today + timedelta(days=365 * 25),
             "1200 Oak Avenue property", "active",
             "30-year fixed. Good rate locked in 2023.",
             "1200 Oak Avenue",
             [("Janet Cobb", None, "Lender")]),
            ("First National - Elm St Mortgage", "Owner & Tom Driscoll (50/50)",
             Decimal("410000.00"), Decimal("372000.00"), Decimal("5.125"), None, False,
             Decimal("2800.00"), today + timedelta(days=15), today + timedelta(days=365 * 27),
             "450 Elm Street duplex", "active",
             "Joint mortgage with Tom. Both personally guaranteeing.",
             "450 Elm Street",
             [("Janet Cobb", None, "Lender"), ("Tom Driscoll", Decimal("50.00"), "Co-borrower")]),
            ("Huang Bridge Loan - Magnolia", "Owner & Nina Patel",
             Decimal("200000.00"), Decimal("200000.00"), Decimal("9.500"), Decimal("24.000"), True,
             Decimal("1583.33"), today + timedelta(days=8), today + timedelta(days=180),
             "3300 Magnolia Blvd purchase", "active",
             "6-month hard money bridge loan for acquisition. Need to refinance into permanent financing ASAP. Default rate 24%.",
             "3300 Magnolia Blvd",
             [("Victor Huang", None, "Lender"), ("Nina Patel", Decimal("50.00"), "Co-borrower")]),
            ("Vehicle Loan - F-150", "Owner (personal)",
             Decimal("45000.00"), Decimal("28700.00"), Decimal("3.900"), None, False,
             Decimal("750.00"), today + timedelta(days=18), today + timedelta(days=365 * 3),
             "2023 Ford F-150", "active",
             "Auto loan through credit union. On track.",
             None,
             []),
        ]
        for name, borrower, orig, bal, rate, default_rate, is_hm, pmt, npd, mat, collat, status, notes, prop_name, parties in loan_data:
            ln = Loan.objects.create(
                name=name, borrower_description=borrower, original_amount=orig,
                current_balance=bal, interest_rate=rate, default_interest_rate=default_rate,
                is_hard_money=is_hm, monthly_payment=pmt,
                next_payment_date=npd, maturity_date=mat, collateral=collat,
                status=status, notes_text=notes,
                related_property=properties.get(prop_name) if prop_name else None,
            )
            loans[name] = ln
            for party_name, percentage, role in parties:
                if party_name in stakeholders:
                    LoanParty.objects.create(
                        loan=ln, stakeholder=stakeholders[party_name],
                        ownership_percentage=percentage, role=role
                    )

        self.stdout.write("Creating insurance policies...")
        insurance_policies = {}
        policy_data = [
            ("Homeowners - 1200 Oak Ave", "HOI-2024-001", "homeowners", "active",
             "National Property Ins", None, Decimal("2400.00"), "annual",
             Decimal("2500.00"), Decimal("500000.00"),
             date(2024, 3, 1), date(2025, 3, 1), True,
             ["1200 Oak Avenue"], "Standard homeowners policy"),
            ("Commercial Property - Magnolia Blvd", "CP-2024-050", "commercial_property", "active",
             "National Property Ins", None, Decimal("8500.00"), "annual",
             Decimal("5000.00"), Decimal("2000000.00"),
             date(2024, 6, 15), date(2025, 6, 15), True,
             ["3300 Magnolia Blvd"], "Commercial building coverage"),
            ("Umbrella Policy", "UMB-2024-100", "umbrella", "active",
             "National Property Ins", None, Decimal("1200.00"), "annual",
             Decimal("10000.00"), Decimal("5000000.00"),
             date(2024, 1, 1), date(2025, 1, 1), True,
             [], "Excess liability umbrella policy"),
            ("Auto Policy - Fleet", "AUTO-2024-200", "auto", "active",
             "National Property Ins", None, Decimal("3600.00"), "semi_annual",
             Decimal("1000.00"), Decimal("300000.00"),
             date(2024, 7, 1), date(2025, 1, 1), False,
             [], "Blanket auto coverage for all vehicles"),
        ]
        carrier, created = Stakeholder.objects.get_or_create(
            name="National Property Ins",
            defaults={"entity_type": "lender", "email": "claims@natpropins.com",
                      "phone": "555-800-4567", "notes_text": "Insurance carrier for property and auto policies"},
        )
        # Track carrier in stakeholders manifest if we created it and stakeholders are loaded
        extra_stakeholder_pks = [carrier.pk] if created else []

        policy_pks = []
        for (name, policy_num, ptype, status, carrier_name, agent_name,
             premium, freq, deductible, coverage, eff, exp, auto_renew,
             covered_prop_names, notes) in policy_data:
            pol = InsurancePolicy.objects.create(
                name=name, policy_number=policy_num, policy_type=ptype,
                status=status, carrier=carrier, premium_amount=premium,
                premium_frequency=freq, deductible=deductible,
                coverage_limit=coverage, effective_date=eff,
                expiration_date=exp, auto_renew=auto_renew, notes_text=notes,
            )
            for pname in covered_prop_names:
                if pname in properties:
                    pol.covered_properties.add(properties[pname])
            if "Tom Driscoll" in stakeholders:
                PolicyHolder.objects.create(
                    policy=pol, stakeholder=stakeholders["Tom Driscoll"], role="Named Insured",
                )
            insurance_policies[name] = pol
            policy_pks.append(pol.pk)

        self.stdout.write("Creating vehicles...")
        vehicles = {}
        vehicle_data = [
            ("2023 Ford F-150 Lariat", "1FTFW1E85NFA00001", 2023, "Ford", "F-150 Lariat",
             "truck", "White", "ABC-1234", "TX", 12500, Decimal("45000.00"),
             today - timedelta(days=365), "active",
             "Primary truck. Loan through credit union.", []),
            ("2021 Toyota Land Cruiser", "JTDKN3DU5M1000002", 2021, "Toyota", "Land Cruiser",
             "suv", "Black", "XYZ-5678", "TX", 34000, Decimal("72000.00"),
             today - timedelta(days=730), "active",
             "Family SUV. Paid off.", []),
            ("2019 Harley-Davidson Road King", "1HD1FBV19KB000003", 2019, "Harley-Davidson", "Road King",
             "motorcycle", "Black", "", "TX", 8200, Decimal("18500.00"),
             today - timedelta(days=1460), "stored",
             "In storage at home garage. Seasonal use only.", []),
            ("2022 Sea Ray 250 SLX", "SERV2500A222000004", 2022, "Sea Ray", "250 SLX",
             "boat", "", "", "TX", None, Decimal("95000.00"),
             today - timedelta(days=900), "active",
             "Docked at Lake Travis Marina. Co-owned 50/50 with Tom Driscoll.",
             [("Tom Driscoll", Decimal("50.00"), "Co-owner")]),
        ]
        for name, vin, year, make, model_name, vtype, color, plate, state, miles, val, acq, status, notes, owners in vehicle_data:
            v = Vehicle.objects.create(
                name=name, vin=vin, year=year, make=make, model_name=model_name,
                vehicle_type=vtype, color=color, license_plate=plate,
                registration_state=state, mileage=miles, estimated_value=val,
                acquisition_date=acq, status=status, notes_text=notes,
            )
            vehicles[name] = v
            for owner_name, percentage, role in owners:
                if owner_name in stakeholders:
                    VehicleOwner.objects.create(
                        vehicle=v, stakeholder=stakeholders[owner_name],
                        ownership_percentage=percentage, role=role,
                    )

        # Link Vehicle Loan to F-150
        f150_loan = loans.get("Vehicle Loan - F-150")
        f150_vehicle = vehicles.get("2023 Ford F-150 Lariat")
        if f150_loan and f150_vehicle:
            f150_loan.related_vehicle = f150_vehicle
            f150_loan.save()

        # Link auto policy to all vehicles
        auto_policy = insurance_policies.get("Auto Policy - Fleet")
        if auto_policy:
            for v in vehicles.values():
                auto_policy.covered_vehicles.add(v)

        self.stdout.write("Creating aircraft...")
        aircraft_dict = {}
        aircraft_data = [
            ("N172SP — Cessna 172 Skyhawk", "N172SP", "", 1998, "Cessna", "172 Skyhawk",
             "single_engine", 1, "KAUS", Decimal("1245.6"), Decimal("285000.00"),
             today - timedelta(days=1825), "active", "US",
             "Primary trainer/personal aircraft. Based at Austin-Bergstrom.", []),
            ("N525BL — Cessna Citation CJ3+", "N525BL", "525B-0601", 2018, "Cessna", "Citation CJ3+",
             "jet", 2, "KAUS", Decimal("3420.0"), Decimal("6200000.00"),
             today - timedelta(days=1095), "active", "US",
             "Business jet. Co-owned 75/25 with Nina Patel.",
             [("Nina Patel", Decimal("25.00"), "Co-owner")]),
            ("N44RH — Robinson R44 Raven II", "N44RH", "13876", 2015, "Robinson", "R44 Raven II",
             "helicopter", 1, "KAUS", Decimal("2180.3"), Decimal("320000.00"),
             today - timedelta(days=2190), "in_maintenance", "US",
             "In maintenance for 2200-hour overhaul. Expected back in 6 weeks.", []),
        ]
        for name, tail, serial, year, make, model_name, atype, engines, airport, hours, val, acq, status, country, notes, owners in aircraft_data:
            ac = Aircraft.objects.create(
                name=name, tail_number=tail, serial_number=serial, year=year,
                make=make, model_name=model_name, aircraft_type=atype,
                num_engines=engines, base_airport=airport, total_hours=hours,
                estimated_value=val, acquisition_date=acq, status=status,
                registration_country=country, notes_text=notes,
            )
            aircraft_dict[name] = ac
            for owner_name, percentage, role in owners:
                if owner_name in stakeholders:
                    AircraftOwner.objects.create(
                        aircraft=ac, stakeholder=stakeholders[owner_name],
                        ownership_percentage=percentage, role=role,
                    )

        self.stdout.write("Creating leases...")
        leases = {}
        lease_data = [
            ("Oak Ave Residential Lease", "1200 Oak Avenue", "residential", "active",
             today - timedelta(days=300), today + timedelta(days=65),
             Decimal("1800.00"), Decimal("1800.00"), 1, "auto",
             "Standard 1-year residential lease with auto-renewal clause.", Decimal("3.00")),
            ("Elm St Unit A Lease", "450 Elm Street", "residential", "active",
             today - timedelta(days=200), today + timedelta(days=165),
             Decimal("1350.00"), Decimal("1350.00"), 1, "option",
             "1-year residential lease. Tenant has option to renew for another year at same rate.", None),
            ("Elm St Unit B Lease", "450 Elm Street", "residential", "active",
             today - timedelta(days=300), today + timedelta(days=65),
             Decimal("1275.00"), Decimal("1275.00"), 1, "negotiable",
             "Lease expiring soon. Need to discuss renewal terms with tenant.", None),
            ("Magnolia Commercial Lease", "3300 Magnolia Blvd", "commercial", "upcoming",
             today + timedelta(days=30), today + timedelta(days=30 + 365 * 5),
             Decimal("8500.00"), Decimal("12000.00"), 1, "negotiable",
             "5-year NNN commercial lease. Starts after property closing.", Decimal("4.00")),
        ]
        lease_pks = []
        lease_party_pks = []
        for name, prop_name, ltype, status, start, end, rent, deposit, due_day, renewal, notes, escalation in lease_data:
            lease = Lease.objects.create(
                name=name, related_property=properties[prop_name],
                lease_type=ltype, status=status,
                start_date=start, end_date=end,
                monthly_rent=rent, security_deposit=deposit,
                rent_due_day=due_day, renewal_type=renewal,
                notes_text=notes, escalation_rate=escalation,
            )
            leases[name] = lease
            lease_pks.append(lease.pk)

        if "Nina Patel" in stakeholders and "Magnolia Commercial Lease" in leases:
            lp = LeaseParty.objects.create(
                lease=leases["Magnolia Commercial Lease"],
                stakeholder=stakeholders["Nina Patel"],
                role="Co-landlord",
                notes="Co-investor on Magnolia portfolio.",
            )
            lease_party_pks.append(lp.pk)

        manifest = {
            "assets.realestate": [p.pk for p in properties.values()],
            "assets.investment": [i.pk for i in investments.values()],
            "assets.loan": [ln.pk for ln in loans.values()],
            "assets.propertyownership": list(
                PropertyOwnership.objects.filter(property__in=properties.values()).values_list("pk", flat=True)
            ),
            "assets.investmentparticipant": list(
                InvestmentParticipant.objects.filter(investment__in=investments.values()).values_list("pk", flat=True)
            ),
            "assets.loanparty": list(
                LoanParty.objects.filter(loan__in=loans.values()).values_list("pk", flat=True)
            ),
            "assets.insurancepolicy": policy_pks,
            "assets.policyholder": list(
                PolicyHolder.objects.filter(policy__pk__in=policy_pks).values_list("pk", flat=True)
            ),
            "assets.vehicle": [v.pk for v in vehicles.values()],
            "assets.vehicleowner": list(
                VehicleOwner.objects.filter(vehicle__in=vehicles.values()).values_list("pk", flat=True)
            ),
            "assets.aircraft": [ac.pk for ac in aircraft_dict.values()],
            "assets.aircraftowner": list(
                AircraftOwner.objects.filter(aircraft__in=aircraft_dict.values()).values_list("pk", flat=True)
            ),
            "assets.lease": lease_pks,
            "assets.leaseparty": lease_party_pks,
        }
        if extra_stakeholder_pks:
            manifest["_extra_stakeholder_pks"] = extra_stakeholder_pks
        return manifest

    # -----------------------------------------------------------------------
    # LEGAL
    # -----------------------------------------------------------------------
    def _load_legal(self, today, now):
        stakeholders = _get_sample_stakeholders()
        properties = _get_sample_properties()
        investments = _get_sample_investments()
        vehicles = _get_sample_vehicles()
        leases = _get_sample_leases()

        self.stdout.write("Creating legal matters...")
        legal_matters = {}
        lm_data = [
            ("Holston Eviction - 1200 Oak Ave",
             "2024-CV-4821", "litigation", "active", "Travis County, TX",
             "Travis County District Court", today - timedelta(days=45),
             "Eviction proceeding against Ray Holston for non-payment of rent ($4,200 outstanding). "
             "Filed after 30-day demand letter went unanswered. Hearing scheduled.",
             ["Marcus Reed"], ["Ray Holston"], ["1200 Oak Avenue"]),
            ("Cedar Lane Boundary Dispute",
             "2023-CV-11034", "litigation", "active", "Dallas County, TX",
             "Dallas County Civil Court", today - timedelta(days=210),
             "Neighbor claims fence encroaches 3 feet onto their lot. Survey shows otherwise. "
             "Attempting mediation before trial.",
             ["Marcus Reed"], [], ["890 Cedar Lane"]),
            ("Magnolia Blvd Acquisition - Due Diligence",
             "", "transaction", "pending", "Bexar County, TX", "",
             today - timedelta(days=30),
             "Due diligence review for 3300 Magnolia Blvd acquisition. Environmental Phase I complete. "
             "Title search clean. Reviewing seller's disclosures.",
             ["Sandra Liu"], ["Nina Patel"], ["3300 Magnolia Blvd"]),
            ("Riverside Zoning Application",
             "ZN-2025-0188", "compliance", "pending", "Harris County, TX",
             "Harris County Planning Commission", today - timedelta(days=60),
             "Zoning change request from agricultural to residential for 15 Riverside Dr. "
             "Public hearing scheduled. Need community support documentation.",
             [], [], ["15 Riverside Dr"]),
            ("Estate Plan Update",
             "", "other", "active", "", "",
             today - timedelta(days=90),
             "Comprehensive estate plan review and update. Revising trust documents, "
             "updating beneficiary designations, power of attorney refresh.",
             ["Dr. Helen Park"], [], []),
        ]
        lm_extras = {
            "Holston Eviction - 1200 Oak Ave": {
                "next_hearing_date": today + timedelta(days=21),
                "judgment_amount": Decimal("4200.00"),
            },
            "Cedar Lane Boundary Dispute": {"next_hearing_date": today + timedelta(days=45)},
            "Magnolia Blvd Acquisition - Due Diligence": {},
            "Riverside Zoning Application": {"next_hearing_date": today + timedelta(days=14)},
            "Estate Plan Update": {},
        }
        for title, case, mtype, status, juris, court, filed, desc, attys, shs, props in lm_data:
            extras = lm_extras.get(title, {})
            lm = LegalMatter.objects.create(
                title=title, case_number=case, matter_type=mtype, status=status,
                jurisdiction=juris, court=court, filing_date=filed, description=desc,
                **extras,
            )
            for a in attys:
                if a in stakeholders:
                    lm.attorneys.add(stakeholders[a])
            for s in shs:
                if s in stakeholders:
                    lm.related_stakeholders.add(stakeholders[s])
            for p in props:
                if p in properties:
                    lm.related_properties.add(properties[p])
            legal_matters[title] = lm

        # Cross-link to other asset types
        if "Estate Plan Update" in legal_matters and investments:
            for inv_name in list(investments.keys())[:2]:
                legal_matters["Estate Plan Update"].related_investments.add(investments[inv_name])
        if "Cedar Lane Boundary Dispute" in legal_matters and vehicles:
            for v_name in list(vehicles.keys())[:1]:
                legal_matters["Cedar Lane Boundary Dispute"].related_vehicles.add(vehicles[v_name])
        if "Holston Eviction - 1200 Oak Ave" in legal_matters and leases:
            for lease_name in list(leases.keys())[:1]:
                legal_matters["Holston Eviction - 1200 Oak Ave"].related_leases.add(leases[lease_name])

        self.stdout.write("Creating evidence...")
        # (title, description, evidence_type, date_obtained, gdrive_url)
        evidence_data = [
            ("Holston Eviction - 1200 Oak Ave", [
                ("Lease Agreement - Holston", "Original signed lease with Ray Holston", "Document", today - timedelta(days=400), "https://drive.google.com/file/d/ev_lease01/view"),
                ("Demand Letter - 30 Day Notice", "Certified mail demand letter sent to Holston", "Correspondence", today - timedelta(days=60), ""),
                ("Rent Ledger", "Payment history showing 3 months delinquent", "Financial Record", today - timedelta(days=45), "https://drive.google.com/file/d/ev_ledger01/view"),
            ]),
            ("Cedar Lane Boundary Dispute", [
                ("Property Survey - 2024", "Licensed surveyor report showing fence placement", "Survey", today - timedelta(days=180), "https://drive.google.com/file/d/ev_survey01/view"),
                ("Original Deed - 890 Cedar", "Deed with metes and bounds description", "Document", today - timedelta(days=200), ""),
                ("Neighbor Communications", "Email thread with neighbor's initial complaint", "Correspondence", today - timedelta(days=220), ""),
            ]),
            ("Magnolia Blvd Acquisition - Due Diligence", [
                ("Phase I Environmental Report", "Clean environmental assessment", "Report", today - timedelta(days=20), "https://drive.google.com/file/d/ev_env01/view"),
                ("Title Search Results", "Clear title, no liens or encumbrances", "Document", today - timedelta(days=15), "https://drive.google.com/file/d/ev_title01/view"),
                ("Property Inspection Report", "Structural and mechanical inspection findings", "Report", today - timedelta(days=18), ""),
            ]),
        ]
        for lm_title, items in evidence_data:
            if lm_title in legal_matters:
                for title, desc, etype, dt, gdrive in items:
                    Evidence.objects.create(
                        legal_matter=legal_matters[lm_title],
                        title=title, description=desc, evidence_type=etype, date_obtained=dt,
                        gdrive_url=gdrive,
                    )

        self.stdout.write("Creating legal communications...")
        comm_pks = []
        # (lm_title, sh_name, days_ago, direction, method, subject, summary, followup, fu_days, fu_completed, gdrive_url)
        comm_data = [
            ("Holston Eviction - 1200 Oak Ave", "Marcus Reed", -14, "outbound", "email",
             "Case summary and evidence",
             "Sent initial case summary and evidence of missed payments to Marcus for review.",
             False, None, False, "https://drive.google.com/file/d/comm_case01/view"),
            ("Holston Eviction - 1200 Oak Ave", "Marcus Reed", -10, "inbound", "call",
             "Filing timeline confirmation",
             "Marcus confirmed filing timeline. Expects hearing in 3-4 weeks. Discussed strategy — "
             "going for default judgment if Holston doesn't respond.",
             True, 7, False, ""),
            ("Holston Eviction - 1200 Oak Ave", "Marcus Reed", -5, "outbound", "email",
             "Bank statements and property photos",
             "Forwarded bank statements showing bounced checks and 3 months of non-payment. "
             "Also sent photos of property condition from last inspection.",
             False, None, False, "https://drive.google.com/file/d/comm_bank01/view"),
            ("Magnolia Blvd Acquisition - Due Diligence", "Sandra Liu", -12, "outbound", "call",
             "Title search results review",
             "Discussed title search results with Sandra. One old mechanics lien found — "
             "she says it should clear before closing.",
             True, -3, True, ""),
            ("Magnolia Blvd Acquisition - Due Diligence", "Sandra Liu", -7, "inbound", "email",
             "Phase I environmental report",
             "Sandra sent Phase I environmental report summary. Property is clean — "
             "no remediation needed. Recommends proceeding to closing.",
             True, 5, False, "https://drive.google.com/file/d/comm_env01/view"),
        ]
        for lm_title, sh_name, days_ago, direction, method, subject, summary, followup, fu_days, fu_completed, gdrive in comm_data:
            if lm_title in legal_matters and sh_name in stakeholders:
                comm = LegalCommunication.objects.create(
                    legal_matter=legal_matters[lm_title],
                    stakeholder=stakeholders[sh_name],
                    date=now + timedelta(days=days_ago),
                    direction=direction, method=method,
                    subject=subject, summary=summary,
                    follow_up_needed=followup,
                    follow_up_date=today + timedelta(days=fu_days) if fu_days else None,
                    follow_up_completed=fu_completed,
                    follow_up_completed_date=today if fu_completed else None,
                    gdrive_url=gdrive,
                )
                comm_pks.append(comm.pk)

        self.stdout.write("Creating legal checklists...")
        checklist_data = [
            ("Holston Eviction - 1200 Oak Ave", [
                ("Gather rent ledger and bounced check evidence", True),
                ("Obtain certified copy of lease agreement", True),
                ("File unlawful detainer complaint", True),
                ("Serve tenant with court summons", False),
                ("Prepare witness list for hearing", False),
                ("Review default judgment requirements", False),
            ]),
            ("Cedar Lane Boundary Dispute", [
                ("Commission independent boundary survey", True),
                ("Obtain original deed with metes and bounds", True),
                ("Document fence installation date with photos", False),
                ("Research adverse possession requirements", False),
                ("Prepare mediation position statement", False),
            ]),
            ("Magnolia Blvd Acquisition - Due Diligence", [
                ("Order Phase I environmental report", True),
                ("Complete title search", True),
                ("Review zoning compliance", True),
                ("Obtain property inspection report", True),
                ("Verify seller disclosures", False),
                ("Review closing documents", False),
                ("Confirm financing terms", False),
            ]),
            ("Estate Plan Update", [
                ("Review current trust provisions", True),
                ("Update beneficiary designations", False),
                ("Draft power of attorney updates", False),
                ("Schedule signing appointment", False),
            ]),
        ]
        checklist_pks = []
        for lm_title, items in checklist_data:
            if lm_title in legal_matters:
                for i, (title, completed) in enumerate(items):
                    cl = LegalChecklistItem.objects.create(
                        legal_matter=legal_matters[lm_title],
                        title=title, is_completed=completed, sort_order=i,
                    )
                    checklist_pks.append(cl.pk)

        return {
            "legal.legalmatter": [lm.pk for lm in legal_matters.values()],
            "legal.evidence": list(
                Evidence.objects.filter(legal_matter__in=legal_matters.values()).values_list("pk", flat=True)
            ),
            "legal.legalcommunication": comm_pks,
            "legal.legalchecklistitem": checklist_pks,
        }

    # -----------------------------------------------------------------------
    # TASKS
    # -----------------------------------------------------------------------
    def _load_tasks(self, today, now):
        stakeholders = _get_sample_stakeholders()
        legal_matters = _get_sample_legal_matters()
        properties = _get_sample_properties()

        self.stdout.write("Creating tasks...")
        tasks = {}
        task_data = [
            ("Follow up with Marcus on Holston hearing date", "Call Marcus Reed to confirm hearing date and discuss strategy.",
             today + timedelta(days=3), "not_started", "high", "one_time", "outbound",
             "Marcus Reed", "Holston Eviction - 1200 Oak Ave", "1200 Oak Avenue"),
            ("Pay Oak Ave mortgage", "Monthly mortgage payment to First National.",
             today + timedelta(days=22), "not_started", "high", "one_time", "personal",
             None, None, "1200 Oak Avenue"),
            ("Pay Elm St mortgage", "Monthly mortgage payment to First National. Split with Tom.",
             today + timedelta(days=15), "not_started", "high", "one_time", "personal",
             "Tom Driscoll", None, "450 Elm Street"),
            ("Schedule roof inspection - Elm St", "Get 2-3 quotes for roof inspection on the duplex.",
             today + timedelta(days=10), "in_progress", "medium", "one_time", "outbound",
             "James Calloway", None, "450 Elm Street"),
            ("Review Magnolia closing documents", "Final review of all closing docs before signing.",
             today + timedelta(days=5), "waiting", "critical", "one_time", "outbound",
             "Sandra Liu", "Magnolia Blvd Acquisition - Due Diligence", "3300 Magnolia Blvd"),
            ("Refinance Huang bridge loan", "Find permanent financing to replace the 9.5% bridge loan.",
             today + timedelta(days=30), "not_started", "critical", "one_time", "outbound",
             "Janet Cobb", None, None),
            ("Prepare zoning hearing materials", "Compile community support letters and development plan for hearing.",
             today + timedelta(days=14), "in_progress", "high", "one_time", "personal",
             None, "Riverside Zoning Application", "15 Riverside Dr"),
            ("Quarterly portfolio review follow-up", "Review Derek's bond allocation recommendation and make decision.",
             today + timedelta(days=7), "not_started", "medium", "one_time", "personal",
             "Derek Vasquez", None, None),
            ("Send Holston back rent to collections", "If eviction proceeds, send $4,200 balance to collections agency.",
             today + timedelta(days=45), "not_started", "medium", "one_time", "outbound",
             "Ray Holston", "Holston Eviction - 1200 Oak Ave", None),
            ("Oak Ave bathroom renovation check-in", "Verify Calloway is on schedule. Due in 2 weeks.",
             today + timedelta(days=5), "not_started", "medium", "one_time", "outbound",
             "James Calloway", None, "1200 Oak Avenue"),
            ("Update estate plan documents", "Sign updated trust and POA documents at Helen's office.",
             today + timedelta(days=20), "waiting", "medium", "one_time", "personal",
             "Dr. Helen Park", "Estate Plan Update", None),
            ("Review Q4 Elm St expense report", "Tom sent Q4 expenses. Verify amounts and approve.",
             today - timedelta(days=5), "not_started", "medium", "one_time", "inbound",
             "Tom Driscoll", None, "450 Elm Street"),
            ("Pay Huang bridge loan interest", "Monthly interest-only payment due.",
             today + timedelta(days=8), "not_started", "high", "one_time", "personal",
             "Victor Huang", None, None),
            ("File property tax protest - Cedar Lane", "Assessed value seems high given boundary dispute. File protest.",
             today - timedelta(days=10), "not_started", "low", "one_time", "personal",
             None, "Cedar Lane Boundary Dispute", "890 Cedar Lane"),
            ("Research Bitcoin exit strategy", "Price is near target. Set limit orders or hold?",
             today + timedelta(days=2), "not_started", "low", "one_time", "personal",
             None, None, None),
            ("Request Polaris Risk background report via Armanino",
             "Asked Lisa Park to run a background/forensic report on Polaris Risk Group before considering their investment proposal.",
             today + timedelta(days=12), "not_started", "high", "one_time", "outbound",
             "Lisa Park", None, None),
            ("Request 2024 Elm St transaction review",
             "Asked Sarah Chen to pull all 2024 transactions for 450 Elm St and prepare a summary for tax season.",
             today + timedelta(days=18), "not_started", "medium", "one_time", "outbound",
             "Sarah Chen", None, "450 Elm Street"),
            ("Request Magnolia Blvd tax review",
             "Asked Michael Torres to review the tax implications of the Magnolia Blvd acquisition structure.",
             today + timedelta(days=25), "not_started", "medium", "one_time", "outbound",
             "Michael Torres", "Magnolia Blvd Acquisition - Due Diligence", "3300 Magnolia Blvd"),
            ("Schedule meeting with Michael Torres",
             "Michael Torres requested a meeting to discuss Q4 tax planning strategy and year-end adjustments.",
             today + timedelta(days=7), "not_started", "medium", "meeting", "inbound",
             "Michael Torres", None, None),
            ("Send Oak Ave receipts to Sarah",
             "Sarah Chen asked me to send all renovation receipts for 1200 Oak Ave for the capital improvement deduction.",
             today + timedelta(days=5), "not_started", "high", "one_time", "inbound",
             "Sarah Chen", None, "1200 Oak Avenue"),
            ("Contact Nina about entity formation",
             "Lisa Park flagged that Nina Patel needs to provide entity formation docs for the Magnolia closing.",
             today + timedelta(days=10), "not_started", "medium", "one_time", "inbound",
             "Lisa Park", "Magnolia Blvd Acquisition - Due Diligence", None),
        ]
        for title, desc, due, status, priority, ttype, direction, sh_name, lm_title, prop_name in task_data:
            t = Task.objects.create(
                title=title, description=desc, due_date=due,
                status=status, priority=priority, task_type=ttype,
                direction=direction,
                related_legal_matter=legal_matters.get(lm_title) if lm_title else None,
                related_property=properties.get(prop_name) if prop_name else None,
            )
            if sh_name and sh_name in stakeholders:
                t.related_stakeholders.add(stakeholders[sh_name])
            tasks[title] = t

        # Set meeting time/duration
        from datetime import time as t_time
        meeting_task = tasks.get("Schedule meeting with Michael Torres")
        if meeting_task:
            meeting_task.due_time = t_time(14, 0)
            meeting_task.duration_minutes = 60
            meeting_task.save(update_fields=["due_time", "duration_minutes"])

        self.stdout.write("Creating follow-ups...")
        followup_data = [
            ("Follow up with Marcus on Holston hearing date", "Marcus Reed", -2, "call", True, 3, False, None,
             "Left voicemail. Will try again tomorrow."),
            ("Review Q4 Elm St expense report", "Tom Driscoll", -5, "email", True, 5, False, None,
             "Sent email asking for supporting receipts."),
            ("Review Q4 Elm St expense report", "Tom Driscoll", -12, "call", False, 3, False, None,
             "Called to discuss expense report. He said he'd send it over."),
            ("Schedule roof inspection - Elm St", "James Calloway", -4, "call", False, 7, True, now - timedelta(days=2),
             "Called Calloway for a quote. He'll send one by Friday."),
            ("Schedule roof inspection - Elm St", "James Calloway", -1, "email", False, 5, False, None,
             "Following up on the quote. No response yet."),
            ("Review Magnolia closing documents", "Sandra Liu", -5, "email", False, 3, True, now - timedelta(days=3),
             "Sandra confirmed docs are ready for review. Picking up Thursday."),
            ("Send Holston back rent to collections", "Ray Holston", -10, "call", True, 7, False, None,
             "Attempted contact one more time before going to collections. No answer."),
            ("Update estate plan documents", "Dr. Helen Park", -20, "meeting", False, 5, True, now - timedelta(days=18),
             "Met to review draft documents. A few changes needed before signing."),
            ("Request Polaris Risk background report via Armanino", "Lisa Park", -2, "email", True, 5, False, None,
             "Sent request to Lisa with details on Polaris Risk Group. Awaiting initial findings."),
            ("Request 2024 Elm St transaction review", "Sarah Chen", -3, "email", True, 7, False, None,
             "Emailed Sarah with access to the Elm St bank statements. She'll compile the summary."),
        ]
        for task_title, sh_name, days_ago, method, reminder_on, fu_days, responded, resp_date, notes in followup_data:
            if task_title in tasks and sh_name in stakeholders:
                FollowUp.objects.create(
                    task=tasks[task_title], stakeholder=stakeholders[sh_name],
                    outreach_date=now + timedelta(days=days_ago),
                    method=method, reminder_enabled=reminder_on, follow_up_days=fu_days,
                    response_received=responded, response_date=resp_date, notes_text=notes,
                )

        return {
            "tasks.task": [t.pk for t in tasks.values()],
            "tasks.followup": list(
                FollowUp.objects.filter(task__in=tasks.values()).values_list("pk", flat=True)
            ),
        }

    # -----------------------------------------------------------------------
    # CASHFLOW
    # -----------------------------------------------------------------------
    def _load_cashflow(self, today, now):
        stakeholders = _get_sample_stakeholders()
        properties = _get_sample_properties()
        loans = _get_sample_loans()

        self.stdout.write("Creating cash flow entries...")
        cf_data = [
            ("Oak Ave rent received", Decimal("1800.00"), "inflow", "Rental Income", today - timedelta(days=2), False,
             None, "1200 Oak Avenue", None, "February rent from current tenant."),
            ("Elm St Unit A rent", Decimal("1400.00"), "inflow", "Rental Income", today - timedelta(days=5), False,
             "Tom Driscoll", "450 Elm Street", None, "Split 50/50 with Tom."),
            ("Elm St Unit B rent", Decimal("1350.00"), "inflow", "Rental Income", today - timedelta(days=5), False,
             "Tom Driscoll", "450 Elm Street", None, "Split 50/50 with Tom."),
            ("Oak Ave mortgage payment", Decimal("2100.00"), "outflow", "Mortgage", today - timedelta(days=10), False,
             "Janet Cobb", "1200 Oak Avenue", "First National - Oak Ave Mortgage", "Monthly P&I."),
            ("Elm St mortgage payment", Decimal("2800.00"), "outflow", "Mortgage", today - timedelta(days=10), False,
             "Janet Cobb", "450 Elm Street", "First National - Elm St Mortgage", "Monthly P&I."),
            ("Huang bridge loan interest", Decimal("1583.33"), "outflow", "Loan Payment", today - timedelta(days=8), False,
             "Victor Huang", None, "Huang Bridge Loan - Magnolia", "Monthly interest only."),
            ("Vehicle loan payment", Decimal("750.00"), "outflow", "Loan Payment", today - timedelta(days=12), False,
             None, None, "Vehicle Loan - F-150", ""),
            ("Property insurance - Oak Ave", Decimal("245.00"), "outflow", "Insurance", today - timedelta(days=15), False,
             None, "1200 Oak Avenue", None, "Monthly premium."),
            ("Property insurance - Elm St", Decimal("310.00"), "outflow", "Insurance", today - timedelta(days=15), False,
             None, "450 Elm Street", None, "Monthly premium."),
            ("Reed & Associates retainer", Decimal("3500.00"), "outflow", "Legal Fees", today - timedelta(days=20), False,
             "Marcus Reed", None, None, "Monthly retainer for Holston eviction + Cedar Lane."),
            ("Calloway - Oak Ave renovation", Decimal("4800.00"), "outflow", "Renovation", today - timedelta(days=7), False,
             "James Calloway", "1200 Oak Avenue", None, "Progress payment for bathroom renovation."),
            ("Vanguard monthly investment", Decimal("2000.00"), "outflow", "Investment", today - timedelta(days=1), False,
             "Derek Vasquez", None, None, "Monthly dollar-cost average into index fund."),
            ("Whitfield appraisal fee", Decimal("450.00"), "outflow", "Professional Services", today - timedelta(days=12), False,
             "Karen Whitfield", "1200 Oak Avenue", None, "Appraisal for refinance consideration."),
            ("Magnolia closing - down payment", Decimal("250000.00"), "outflow", "Acquisition", today + timedelta(days=25), True,
             "Nina Patel", "3300 Magnolia Blvd", None, "Due at closing. Split with Nina."),
            ("Magnolia closing - closing costs", Decimal("18500.00"), "outflow", "Acquisition", today + timedelta(days=25), True,
             None, "3300 Magnolia Blvd", None, "Estimated title, recording, legal fees."),
            ("Expected Oak Ave rent - March", Decimal("1800.00"), "inflow", "Rental Income", today + timedelta(days=28), True,
             None, "1200 Oak Avenue", None, ""),
            ("Expected Elm St rent - March", Decimal("2750.00"), "inflow", "Rental Income", today + timedelta(days=28), True,
             "Tom Driscoll", "450 Elm Street", None, "Both units combined."),
            ("Oak Ave mortgage - March", Decimal("2100.00"), "outflow", "Mortgage", today + timedelta(days=22), True,
             "Janet Cobb", "1200 Oak Avenue", "First National - Oak Ave Mortgage", ""),
            ("Elm St mortgage - March", Decimal("2800.00"), "outflow", "Mortgage", today + timedelta(days=15), True,
             "Janet Cobb", "450 Elm Street", "First National - Elm St Mortgage", ""),
            ("Huang bridge interest - March", Decimal("1583.33"), "outflow", "Loan Payment", today + timedelta(days=8), True,
             "Victor Huang", None, "Huang Bridge Loan - Magnolia", ""),
            ("NP Investments annual distribution", Decimal("4500.00"), "inflow", "Investment Income", today + timedelta(days=60), True,
             "Nina Patel", None, None, "Estimated annual distribution from Fund II."),
            ("Property tax - all properties", Decimal("8200.00"), "outflow", "Taxes", today + timedelta(days=45), True,
             None, None, None, "Quarterly property tax bill across all holdings."),
        ]
        cashflow_pks = []
        for desc, amt, etype, cat, dt, proj, sh_name, prop_name, loan_name, notes in cf_data:
            cf = CashFlowEntry.objects.create(
                description=desc, amount=amt, entry_type=etype, category=cat,
                date=dt, is_projected=proj,
                related_stakeholder=stakeholders.get(sh_name),
                related_property=properties.get(prop_name) if prop_name else None,
                related_loan=loans.get(loan_name) if loan_name else None,
                notes_text=notes,
            )
            cashflow_pks.append(cf.pk)

        return {"cashflow.cashflowentry": cashflow_pks}

    # -----------------------------------------------------------------------
    # NOTES
    # -----------------------------------------------------------------------
    def _load_notes(self, today, now):
        stakeholders = _get_sample_stakeholders()
        legal_matters = _get_sample_legal_matters()
        properties = _get_sample_properties()
        tasks = _get_sample_tasks()

        self.stdout.write("Creating tags and folders...")
        tag_data = [
            ("legal", "Legal", "red"),
            ("finance", "Finance", "green"),
            ("property", "Property", "blue"),
            ("meeting-notes", "Meeting Notes", "purple"),
            ("action-item", "Action Item", "orange"),
            ("research", "Research", "cyan"),
        ]
        tags = {}
        for slug, name, color in tag_data:
            tag, _ = Tag.objects.get_or_create(slug=slug, defaults={"name": name, "color": color})
            tags[slug] = tag

        folder_data = [
            ("Legal", "red", 1),
            ("Properties", "blue", 2),
            ("Investments", "green", 3),
            ("Meetings", "purple", 4),
            ("Healthcare", "cyan", 5),
        ]
        folders = {}
        for name, color, order in folder_data:
            folder, _ = Folder.objects.get_or_create(name=name, defaults={"color": color, "sort_order": order})
            folders[name] = folder

        self.stdout.write("Creating notes...")
        note_data = [
            ("Holston eviction strategy call with Marcus", "call", now - timedelta(days=2),
             "Called Marcus to discuss eviction strategy.\n\nKey points:\n- Hearing likely in 3-4 weeks\n- Judge typically rules in landlord's favor with proper documentation\n- We have strong case: signed lease, payment history, demand letter\n- Marcus recommends also pursuing judgment for back rent\n- Total exposure: $4,200 back rent + ~$3,500 legal fees\n\nAction items:\n- Gather last 12 months bank statements showing no payments\n- Get written statement from property manager about condition of unit",
             ["Marcus Reed"], ["Marcus Reed", "Ray Holston"], ["Holston Eviction - 1200 Oak Ave"],
             ["1200 Oak Avenue"], ["Follow up with Marcus on Holston hearing date"]),
            ("Magnolia Blvd walkthrough notes", "meeting", now - timedelta(days=10),
             "Walked the property with Nina and Sandra.\n\nObservations:\n- Building is in good condition overall\n- HVAC systems (3 units) are 8 years old - budget for replacement in 3-5 years\n- Parking lot needs resealing - est $12k\n- Current tenants are month-to-month, rents below market by ~15%\n- Clear upside: raise rents gradually after closing\n\nNina's take: strong buy at asking price. I agree.\n\nNext steps: finalize financing, review seller's disclosures, schedule closing.",
             ["Nina Patel", "Sandra Liu"], ["Nina Patel", "Sandra Liu"],
             ["Magnolia Blvd Acquisition - Due Diligence"], ["3300 Magnolia Blvd"],
             ["Review Magnolia closing documents"]),
            ("Quarterly portfolio review with Derek", "meeting", now - timedelta(days=1),
             "Met with Derek for Q4 review.\n\nPortfolio summary:\n- Total liquid investments: ~$367k\n- YTD return: 11.2% (vs S&P 10.8%)\n- Vanguard Total Market: strong performance, continue DCA\n- Municipal bonds: providing steady 3.8% tax-free yield\n- Bitcoin: up 45% since purchase, consider trimming\n\nDerek's recommendations:\n1. Shift 10% from equities to bonds (rising rate environment)\n2. Take partial profits on Bitcoin above $70k\n3. Max out IRA contribution before April deadline\n4. Consider tax-loss harvesting in taxable account",
             ["Derek Vasquez"], ["Derek Vasquez"], [], [], ["Quarterly portfolio review follow-up"]),
            ("Cedar Lane mediation prep", "research", now - timedelta(days=15),
             "Research for upcoming mediation on boundary dispute.\n\nOur position:\n- 2024 survey clearly shows fence is 100% on our property\n- Original deed metes and bounds support our survey\n- Fence has been in place since 2019 (5 years)\n- Neighbor's survey (done by a less reputable firm) shows 3ft encroachment\n\nLegal strategy:\n- Lead with our survey + deed\n- Offer to split cost of a third independent survey\n- If mediation fails, file for declaratory judgment\n- Marcus estimates trial would cost $15-20k\n\nIdeal outcome: neighbor accepts our survey, we avoid court costs.",
             [], [], ["Cedar Lane Boundary Dispute"], ["890 Cedar Lane"],
             ["File property tax protest - Cedar Lane"]),
            ("Elm St roof concerns", "general", now - timedelta(days=6),
             "Tom mentioned during our last call that Unit B tenant reported a small leak in the back bedroom during the last heavy rain.\n\nNeed to:\n1. Get Calloway or another contractor to inspect\n2. Check if this is covered under existing homeowner's insurance\n3. Get 2-3 quotes for repair/replacement\n4. Discuss cost split with Tom (50/50 per our agreement)\n\nRoof is ~18 years old. May be time for full replacement rather than patching.",
             [], ["Tom Driscoll", "James Calloway"], [], ["450 Elm Street"],
             ["Schedule roof inspection - Elm St"]),
            ("Estate planning meeting notes", "meeting", now - timedelta(days=20),
             "Annual review with Dr. Helen Park.\n\nUpdates made:\n- Revocable living trust updated with new property acquisitions\n- Added 3300 Magnolia Blvd (pending closing) to trust schedule\n- Updated beneficiary designations on all investment accounts\n- Renewed power of attorney documents\n- Healthcare directive remains current\n\nOutstanding items:\n- Need to sign final documents at Helen's office\n- Consider forming LLC for Magnolia Blvd (discuss with Sandra)\n- Review life insurance coverage given increased asset base",
             ["Dr. Helen Park"], ["Dr. Helen Park"], ["Estate Plan Update"], [],
             ["Update estate plan documents"]),
            ("Huang bridge loan terms review", "research", now - timedelta(days=25),
             "Reviewed the terms on Victor Huang's bridge loan.\n\nTerms:\n- Principal: $200,000\n- Rate: 9.5% (interest only)\n- Term: 6 months\n- Monthly payment: $1,583.33\n- Maturity: ~5 months from now\n- Prepayment penalty: None after 90 days\n\nTotal interest cost if held to maturity: ~$9,500\nNeed to refinance ASAP. Talk to Janet about rolling into a conventional loan once Magnolia closes and we have rental income to show.",
             [], ["Victor Huang", "Janet Cobb"], [], [],
             ["Refinance Huang bridge loan"]),
            ("Riverside development feasibility", "research", now - timedelta(days=40),
             "Researched development options for 15 Riverside Dr.\n\nZoning: Currently agricultural, requesting residential\nLot size: 0.8 acres\nEstimated build cost: $280-350k for single family\nComparable sales in area: $450-520k\nTimeline: 6-8 months for permitting + 10-12 months construction\n\nPros: Good margins, growing area, no HOA restrictions\nCons: Long timeline, capital intensive, zoning not guaranteed\n\nDecision: Proceed with zoning application, then reassess based on approval and available capital after Magnolia closing.",
             [], [], ["Riverside Zoning Application"], ["15 Riverside Dr"],
             ["Prepare zoning hearing materials"]),
            ("Call with Tom about Elm St expenses", "call", now - timedelta(days=22),
             "Quick call with Tom about Q4 expenses.\n\nHe reported:\n- Plumbing repair Unit A: $380\n- Landscaping Q4: $600\n- Pest control: $150\n- General maintenance: $425\n- Total: $1,555 (my half: $777.50)\n\nAsked him to send receipts for everything. He said he'd email them over. Still waiting as of today.",
             ["Tom Driscoll"], ["Tom Driscoll"], [], ["450 Elm Street"],
             ["Review Q4 Elm St expense report"]),
            ("Quick note - Bitcoin price alert", "general", now - timedelta(hours=6),
             "Bitcoin hit $68,500 today. Getting close to my $70k target for trimming. Set a limit sell for 0.1 BTC at $71,000 on Coinbase. Will reassess remaining position after.",
             [], [], [], [], ["Research Bitcoin exit strategy"]),
        ]
        note_folders = {
            "Holston eviction strategy call with Marcus": "Legal",
            "Magnolia Blvd walkthrough notes": "Properties",
            "Quarterly portfolio review with Derek": "Investments",
            "Cedar Lane mediation prep": "Legal",
            "Estate planning meeting notes": "Meetings",
        }
        note_tags = {
            "Holston eviction strategy call with Marcus": ["legal", "action-item"],
            "Magnolia Blvd walkthrough notes": ["property", "meeting-notes"],
            "Quarterly portfolio review with Derek": ["finance", "meeting-notes"],
            "Cedar Lane mediation prep": ["legal", "research", "property"],
            "Elm St roof concerns": ["property", "action-item"],
            "Estate planning meeting notes": ["legal", "meeting-notes"],
        }
        pinned_notes = {
            "Holston eviction strategy call with Marcus",
            "Quarterly portfolio review with Derek",
        }

        note_pks = []
        for title, ntype, dt, content, participants, rel_sh, rel_lm, rel_props, rel_tasks in note_data:
            note = Note.objects.create(
                title=title, note_type=ntype, date=dt, content=content,
                is_pinned=title in pinned_notes,
                folder=folders.get(note_folders.get(title)),
            )
            note_pks.append(note.pk)
            for name in participants:
                if name in stakeholders:
                    note.participants.add(stakeholders[name])
            for name in rel_sh:
                if name in stakeholders:
                    note.related_stakeholders.add(stakeholders[name])
            for t in rel_lm:
                if t in legal_matters:
                    note.related_legal_matters.add(legal_matters[t])
            for p in rel_props:
                if p in properties:
                    note.related_properties.add(properties[p])
            for t in rel_tasks:
                if t in tasks:
                    note.related_tasks.add(tasks[t])
            for tag_slug in note_tags.get(title, []):
                if tag_slug in tags:
                    note.tags.add(tags[tag_slug])

        return {
            "notes.tag": [t.pk for t in tags.values()],
            "notes.folder": [f.pk for f in folders.values()],
            "notes.note": note_pks,
        }

    # -----------------------------------------------------------------------
    # HEALTHCARE
    # -----------------------------------------------------------------------
    def _load_healthcare(self, today, now):
        stakeholders = _get_sample_stakeholders()

        self.stdout.write("Creating healthcare data...")
        providers = {}
        provider_data = [
            ("Dr. Sarah Mitchell", "primary_care", "Internal Medicine", "Pacific Primary Care",
             "1234567890", "CA-MD-45678", "415-555-0101", "415-555-0102",
             "smitchell@pacificprimary.com", "2200 Pacific Ave, San Francisco, CA 94115",
             "active", "Dr. Helen Park", None),
            ("Dr. James Wong", "specialist", "Cardiology", "Bay Area Heart Group",
             "2345678901", "CA-MD-56789", "415-555-0201", "",
             "jwong@bayareaheart.com", "1800 Post St, San Francisco, CA 94115",
             "active", None, None),
            ("Dr. Emily Chen", "dentist", "General Dentistry", "Sunset Dental",
             "3456789012", "CA-DDS-67890", "415-555-0301", "",
             "echen@sunsetdental.com", "3456 Sunset Blvd, San Francisco, CA 94122",
             "active", None, None),
            ("Dr. Michael Torres", "specialist", "Orthopedics", "Sports Medicine Associates",
             "4567890123", "CA-MD-78901", "415-555-0401", "",
             "mtorres@sportsmedicine.com", "500 Parnassus Ave, San Francisco, CA 94143",
             "past", None, None),
            ("Dr. Lisa Pham", "specialist", "Dermatology", "Pham Dermatology",
             "5678901234", "CA-MD-89012", "415-555-0501", "",
             "lpham@phamderm.com", "1600 Divisadero St, San Francisco, CA 94115",
             "active", None, None),
        ]
        hc_pks = {"providers": [], "conditions": [], "prescriptions": [],
                   "supplements": [], "testresults": [], "visits": [],
                   "advice": [], "appointments": []}
        for (name, ptype, spec, practice, npi, lic, phone, fax, email, addr,
             status, sh_name, policy_name) in provider_data:
            prov = Provider.objects.create(
                name=name, provider_type=ptype, specialty=spec,
                practice_name=practice, npi=npi, license_number=lic,
                phone=phone, fax=fax, email=email, address=addr,
                status=status,
                stakeholder=stakeholders.get(sh_name),
                notes_text="",
            )
            providers[name] = prov
            hc_pks["providers"].append(prov.pk)

        conditions = {}
        condition_data = [
            ("Essential Hypertension", "I10", today - timedelta(days=730),
             "active", "moderate", "Dr. Sarah Mitchell",
             "Blood pressure consistently elevated. Well-controlled with medication.",
             "Lisinopril 10mg daily. Monitor BP at home. Low sodium diet."),
            ("Seasonal Allergies", "J30.1", today - timedelta(days=1825),
             "managed", "mild", "Dr. Sarah Mitchell",
             "Spring/fall seasonal allergic rhinitis.",
             "Cetirizine as needed. Nasal spray during peak season."),
        ]
        for name, icd, diag_date, status, severity, prov_name, desc, plan in condition_data:
            cond = Condition.objects.create(
                name=name, icd_code=icd, diagnosed_date=diag_date,
                status=status, severity=severity,
                diagnosed_by=providers.get(prov_name),
                description=desc, treatment_plan=plan,
            )
            conditions[name] = cond
            hc_pks["conditions"].append(cond.pk)

        rx_data = [
            ("Lisinopril", "Lisinopril", "10mg", "once_daily", "oral",
             "CVS Pharmacy", "415-555-0901", "RX-2024-001",
             today - timedelta(days=365), None, 6, 3,
             today + timedelta(days=15), False,
             "Blood pressure control", "Dry cough (rare), dizziness",
             "active", "Dr. Sarah Mitchell", "Essential Hypertension"),
            ("Atorvastatin", "Atorvastatin Calcium", "20mg", "once_daily", "oral",
             "CVS Pharmacy", "415-555-0901", "RX-2024-002",
             today - timedelta(days=180), None, 6, 5,
             today + timedelta(days=45), False,
             "Cholesterol management", "Muscle aches, liver enzyme changes",
             "active", "Dr. Sarah Mitchell", "Essential Hypertension"),
            ("Amoxicillin", "Amoxicillin", "500mg", "three_times_daily", "oral",
             "Walgreens", "415-555-0902", "RX-2025-010",
             today - timedelta(days=14), today - timedelta(days=4), 0, 0,
             None, False,
             "Sinus infection", "Nausea, diarrhea",
             "completed", "Dr. Sarah Mitchell", None),
        ]
        for (med, generic, dose, freq, route, pharmacy, ph_phone, rx_num,
             start, end, ref_total, ref_remain, next_refill, controlled,
             purpose, side_effects, status, prov_name, cond_name) in rx_data:
            rx = Prescription.objects.create(
                medication_name=med, generic_name=generic, dosage=dose,
                frequency=freq, route=route, pharmacy=pharmacy,
                pharmacy_phone=ph_phone, rx_number=rx_num,
                start_date=start, end_date=end,
                refills_total=ref_total, refills_remaining=ref_remain,
                next_refill_date=next_refill, is_controlled=controlled,
                purpose=purpose, side_effects=side_effects, status=status,
                prescribing_provider=providers.get(prov_name),
                related_condition=conditions.get(cond_name),
            )
            hc_pks["prescriptions"].append(rx.pk)

        supplement_data = [
            ("Vitamin D3", "Nature Made", "5000 IU", "once_daily",
             "Bone health and immune support", today - timedelta(days=365), None,
             "active", "Dr. Sarah Mitchell", None),
            ("Fish Oil (Omega-3)", "Nordic Naturals", "1000mg", "twice_daily",
             "Heart health and inflammation", today - timedelta(days=200), None,
             "active", "Dr. Sarah Mitchell", "Essential Hypertension"),
            ("Magnesium Glycinate", "NOW Foods", "400mg", "once_daily",
             "Sleep quality and muscle relaxation", today - timedelta(days=90), None,
             "active", None, None),
        ]
        for name, brand, dose, freq, purpose, start, end, status, prov_name, cond_name in supplement_data:
            s = Supplement.objects.create(
                name=name, brand=brand, dosage=dose, frequency=freq,
                purpose=purpose, start_date=start, end_date=end, status=status,
                recommended_by=providers.get(prov_name),
                related_condition=conditions.get(cond_name),
            )
            hc_pks["supplements"].append(s.pk)

        test_data = [
            ("Comprehensive Metabolic Panel", "lab", today - timedelta(days=30),
             "UCSF Medical Center", "All within range", "See reference ranges",
             "", "normal", "Annual lab work. All values normal.",
             "Dr. Sarah Mitchell", None),
            ("Lipid Panel", "lab", today - timedelta(days=30),
             "UCSF Medical Center", "Total: 195, LDL: 118, HDL: 55, Trig: 110",
             "Total <200, LDL <130, HDL >40, Trig <150", "mg/dL",
             "normal", "Cholesterol well-controlled with statin therapy.",
             "Dr. Sarah Mitchell", "Essential Hypertension"),
            ("Chest X-Ray", "imaging", today - timedelta(days=90),
             "Bay Area Heart Group", "Normal cardiac silhouette",
             "Normal", "", "normal",
             "Annual cardiac screening. No abnormalities detected.",
             "Dr. James Wong", None),
        ]
        for (name, ttype, dt, facility, result, ref_range, unit,
             status, summary, prov_name, cond_name) in test_data:
            tr = TestResult.objects.create(
                test_name=name, test_type=ttype, date=dt,
                facility=facility, result_value=result,
                reference_range=ref_range, unit=unit, status=status,
                result_summary=summary,
                ordering_provider=providers.get(prov_name),
                related_condition=conditions.get(cond_name),
            )
            hc_pks["testresults"].append(tr.pk)

        from datetime import time as time_type
        visit_data = [
            (today - timedelta(days=30), "10:00", "Dr. Sarah Mitchell",
             "Pacific Primary Care", "routine",
             "Annual physical exam", "Good overall health. Continue current medications.",
             "Comprehensive exam performed. All vitals within normal range.",
             "BP: 128/82, HR: 72, Temp: 98.6F, Weight: 180lbs",
             "Continue medications. Return in 6 months for BP check.",
             today + timedelta(days=150), Decimal("40.00"), "Essential Hypertension"),
            (today - timedelta(days=90), "14:30", "Dr. James Wong",
             "Bay Area Heart Group", "specialist",
             "Annual cardiac evaluation", "No cardiac concerns.",
             "EKG normal sinus rhythm. Heart sounds normal. Exercise tolerance good.",
             "BP: 130/80, HR: 68",
             "Continue statin. Annual follow-up.",
             today + timedelta(days=275), Decimal("60.00"), None),
            (today - timedelta(days=14), "09:00", "Dr. Sarah Mitchell",
             "Pacific Primary Care", "follow_up",
             "Sinus infection", "Bacterial sinusitis diagnosed.",
             "Patient presented with 10 days of congestion, facial pain, purulent discharge.",
             "BP: 126/80, HR: 74, Temp: 99.1F",
             "10-day course of amoxicillin. Follow up if not improved.",
             None, Decimal("40.00"), None),
        ]
        for (dt, time_str, prov_name, facility, vtype, reason, diagnosis,
             summary, vitals, followup, next_visit, copay, cond_name) in visit_data:
            h, m = map(int, time_str.split(":"))
            v = Visit.objects.create(
                date=dt, time=time_type(h, m),
                provider=providers.get(prov_name),
                facility=facility, visit_type=vtype,
                reason=reason, diagnosis=diagnosis, summary=summary,
                vitals=vitals, follow_up_instructions=followup,
                next_visit_date=next_visit, copay=copay,
                related_condition=conditions.get(cond_name),
            )
            hc_pks["visits"].append(v.pk)

        advice_data = [
            ("Reduce sodium intake", "Limit daily sodium to under 2,300mg.\n\nTips:\n- Read nutrition labels\n- Cook at home more\n- Use herbs/spices instead of salt\n- Avoid processed foods\n- Choose low-sodium options when eating out",
             "diet", today - timedelta(days=30), "active",
             "Dr. Sarah Mitchell", None, "Essential Hypertension"),
            ("Regular cardiovascular exercise",
             "30 minutes of moderate cardio exercise, 5 days per week.\n\nRecommended activities:\n- Brisk walking\n- Swimming\n- Cycling\n- Elliptical\n\nAvoid: Heavy weightlifting without proper warm-up. Monitor heart rate during exercise.",
             "exercise", today - timedelta(days=90), "active",
             "Dr. James Wong", None, "Essential Hypertension"),
        ]
        for title, text, category, dt, status, prov_name, visit_pk, cond_name in advice_data:
            adv = Advice.objects.create(
                title=title, advice_text=text, category=category,
                date=dt, status=status,
                given_by=providers.get(prov_name),
                related_condition=conditions.get(cond_name),
            )
            hc_pks["advice"].append(adv.pk)

        appt_data = [
            ("Annual Physical Exam", today + timedelta(days=60), "09:30", 60,
             "Pacific Primary Care", "1234 Market St, Suite 200, San Francisco, CA 94102",
             "https://www.pacificprimarycare.com/patient-portal", "routine",
             "Annual comprehensive physical exam",
             "Fast for 12 hours before appointment for lab work.",
             "scheduled", "Dr. Sarah Mitchell", "Essential Hypertension"),
            ("Dental Cleaning", today + timedelta(days=14), "10:00", 60,
             "Sunset Dental", "5678 Sunset Blvd, San Francisco, CA 94122",
             "", "routine",
             "Biannual dental cleaning and exam", "",
             "confirmed", "Dr. Emily Chen", None),
            ("Dermatology Annual Skin Check", today + timedelta(days=45), "14:00", 30,
             "Pham Dermatology", "900 Hyde St, Floor 3, San Francisco, CA 94109",
             "https://www.phamdermatology.com", "specialist",
             "Annual full-body skin exam",
             "Avoid applying any lotions on the day of the appointment.",
             "scheduled", "Dr. Lisa Pham", None),
        ]
        for (title, dt, time_str, duration, facility, address, url,
             vtype, purpose, prep, status, prov_name, cond_name) in appt_data:
            h, m = map(int, time_str.split(":"))
            appt = Appointment.objects.create(
                title=title, date=dt, time=time_type(h, m),
                duration_minutes=duration, facility=facility,
                address=address, url=url,
                visit_type=vtype, purpose=purpose,
                preparation=prep, status=status,
                provider=providers.get(prov_name),
                related_condition=conditions.get(cond_name),
            )
            hc_pks["appointments"].append(appt.pk)

        return {
            "healthcare.provider": hc_pks["providers"],
            "healthcare.condition": hc_pks["conditions"],
            "healthcare.prescription": hc_pks["prescriptions"],
            "healthcare.supplement": hc_pks["supplements"],
            "healthcare.testresult": hc_pks["testresults"],
            "healthcare.visit": hc_pks["visits"],
            "healthcare.advice": hc_pks["advice"],
            "healthcare.appointment": hc_pks["appointments"],
        }

    # -----------------------------------------------------------------------
    # DOCUMENTS
    # -----------------------------------------------------------------------
    def _load_documents(self, today, now):
        properties = _get_sample_properties()
        investments = _get_sample_investments()
        insurance = _get_sample_insurance()
        legal_matters = _get_sample_legal_matters()
        stakeholders = _get_sample_stakeholders()

        self.stdout.write("Creating documents...")
        doc_pks = []

        doc_data = [
            # (title, category, date, expiration_date, description, gdrive_url,
            #  property_name, investment_name, policy_name, legal_name, stakeholder_name, notes)
            ("Oak Ave Property Deed", "deed",
             today - timedelta(days=1825), None,
             "Warranty deed for 1200 Oak Avenue residential property.",
             "https://drive.google.com/file/d/1abc123/view",
             "1200 Oak Avenue", None, None, None, None,
             "Recorded at county recorder's office."),
            ("Elm St Property Deed", "deed",
             today - timedelta(days=1460), None,
             "Warranty deed for 450 Elm Street duplex property.",
             "",
             "450 Elm Street", None, None, None, None, ""),
            ("2024 Federal Tax Return", "tax_return",
             today - timedelta(days=60), None,
             "2024 Federal income tax return (Form 1040) and all schedules.",
             "https://drive.google.com/file/d/2def456/view",
             None, None, None, None, None,
             "Filed electronically via CPA."),
            ("2024 State Tax Return", "tax_return",
             today - timedelta(days=55), None,
             "2024 California state income tax return (Form 540).",
             "https://drive.google.com/file/d/3ghi789/view",
             None, None, None, None, None, ""),
            ("Oak Ave Homeowners Insurance Certificate", "insurance_cert",
             today - timedelta(days=90), today + timedelta(days=275),
             "Certificate of insurance for 1200 Oak Avenue homeowners policy.",
             "",
             "1200 Oak Avenue", None, "Homeowners - 1200 Oak Ave", None, None, ""),
            ("NP Investments LP - Operating Agreement", "operating_agreement",
             today - timedelta(days=365), None,
             "Limited partnership operating agreement for NP Investments LP Fund II.",
             "https://drive.google.com/file/d/4jkl012/view",
             None, "NP Investments LP - Fund II", None, None, None,
             "Executed copy. Amendment 1 pending review."),
            ("Magnolia Blvd Appraisal Report", "appraisal",
             today - timedelta(days=120), None,
             "Full appraisal report for 3300 Magnolia Blvd commercial property.",
             "https://drive.google.com/file/d/5mno345/view",
             "3300 Magnolia Blvd", None, None,
             "Magnolia Blvd Acquisition - Due Diligence", "Karen Whitfield",
             "MAI appraisal by Karen Whitfield. Value: $2.8M"),
            ("Q4 2024 Elm St Operating Statement", "operating_statement",
             today - timedelta(days=45), None,
             "Q4 2024 operating statement from property manager for 450 Elm Street.",
             "https://drive.google.com/file/d/6pqr678/view",
             "450 Elm Street", None, None, None, "Tom Driscoll",
             "Shows $12,500 gross income, $4,200 expenses."),
            ("Elm St Business License", "license",
             today - timedelta(days=180), today + timedelta(days=45),
             "City of LA business license for 450 Elm Street rental operation.",
             "",
             "450 Elm Street", None, None, None, None,
             "Renewal application submitted. Awaiting approval."),
            ("Magnolia Blvd Phase I ESA Report", "environmental",
             today - timedelta(days=400), today - timedelta(days=35),
             "Phase I Environmental Site Assessment for 3300 Magnolia Blvd.",
             "https://drive.google.com/file/d/7stu901/view",
             "3300 Magnolia Blvd", None, None,
             "Magnolia Blvd Acquisition - Due Diligence", None,
             "Clean report. No RECs identified. Expired — new assessment needed."),
        ]

        for (title, category, dt, exp_date, desc, gdrive_url,
             prop_name, inv_name, pol_name, legal_name, sh_name, notes) in doc_data:
            doc = Document.objects.create(
                title=title,
                category=category,
                date=dt,
                expiration_date=exp_date,
                description=desc,
                gdrive_url=gdrive_url,
                gdrive_file_name=title if gdrive_url else "",
                related_property=properties.get(prop_name),
                related_investment=investments.get(inv_name),
                related_policy=insurance.get(pol_name),
                related_legal_matter=legal_matters.get(legal_name),
                related_stakeholder=stakeholders.get(sh_name),
                notes_text=notes,
            )
            doc_pks.append(doc.pk)

        return {
            "documents.document": doc_pks,
        }
