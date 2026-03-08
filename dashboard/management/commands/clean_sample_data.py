"""
Management command to safely remove sample data by matching known names/identifiers.
Unlike --hard-reset, this preserves any user-created production data.

Usage: python manage.py clean_sample_data [--dry-run]
"""
from django.core.management.base import BaseCommand
from django.db.models import Q


# Known sample data identifiers — these are the exact names/titles used by load_sample_data.py

SAMPLE_STAKEHOLDER_NAMES = {
    "Marcus Reed", "Sandra Liu", "Tom Driscoll", "Janet Cobb",
    "Derek Vasquez", "Karen Whitfield", "Ray Holston", "Nina Patel",
    "Victor Huang", "Alicia Moreno", "James Calloway", "Dr. Helen Park",
    "Armanino LLP", "Sarah Chen", "Michael Torres", "Lisa Park",
    "National Property Ins",
}

SAMPLE_PROPERTY_NAMES = {
    "1200 Oak Avenue", "450 Elm Street", "3300 Magnolia Blvd",
    "890 Cedar Lane", "15 Riverside Dr",
    "7-Eleven - 509 Bates Ave", "7-Eleven - 10710 W Loop",
    "Dollar Tree - 2100 Main St",
}

SAMPLE_INVESTMENT_NAMES = {
    "Vanguard Total Market Index", "Schwab S&P 500 ETF",
    "Municipal Bond Fund", "NP Investments LP - Fund II",
    "Bitcoin Holdings",
}

SAMPLE_LOAN_NAMES = {
    "First National - Oak Ave Mortgage", "First National - Elm St Mortgage",
    "Huang Bridge Loan - Magnolia", "Vehicle Loan - F-150",
}

SAMPLE_VEHICLE_NAMES = {
    "2023 Ford F-150 Lariat", "2021 Toyota Land Cruiser",
    "2019 Harley-Davidson Road King", "2022 Sea Ray 250 SLX",
}

SAMPLE_AIRCRAFT_NAMES = {
    "N172SP — Cessna 172 Skyhawk", "N525BL — Cessna Citation CJ3+",
    "N44RH — Robinson R44 Raven II",
}

SAMPLE_INSURANCE_NAMES = {
    "Homeowners - 1200 Oak Ave", "Commercial Property - Magnolia Blvd",
    "Umbrella Policy", "Auto Policy - Fleet",
}

SAMPLE_LEASE_NAMES = {
    "Oak Ave Residential Lease", "Elm St Unit A Lease",
    "Elm St Unit B Lease", "Magnolia Commercial Lease",
}

SAMPLE_LEGAL_TITLES = {
    "Holston Eviction - 1200 Oak Ave", "Cedar Lane Boundary Dispute",
    "Magnolia Blvd Acquisition - Due Diligence",
    "Riverside Zoning Application", "Estate Plan Update",
}

SAMPLE_TASK_TITLES = {
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
}

SAMPLE_NOTE_TITLES = {
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
}

SAMPLE_CASHFLOW_DESCRIPTIONS = {
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
}

SAMPLE_TAG_SLUGS = {
    "legal", "finance", "property", "meeting-notes", "action-item", "research",
}

SAMPLE_FOLDER_NAMES = {
    "Legal", "Properties", "Investments", "Meetings", "Healthcare",
}

SAMPLE_PROVIDER_NAMES = {
    "Dr. Sarah Mitchell", "Dr. James Wong", "Dr. Emily Chen",
    "Dr. Michael Torres", "Dr. Lisa Pham",
}

SAMPLE_CONDITION_NAMES = {
    "Essential Hypertension", "Seasonal Allergies",
}

SAMPLE_PRESCRIPTION_NAMES = {
    "Lisinopril", "Atorvastatin", "Amoxicillin",
}

SAMPLE_SUPPLEMENT_NAMES = {
    "Vitamin D3", "Fish Oil (Omega-3)", "Magnesium Glycinate",
}


class Command(BaseCommand):
    help = (
        "Safely remove sample data by matching known names/identifiers. "
        "Preserves user-created production data. Use --dry-run to preview."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Show what would be deleted without actually deleting.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — nothing will be deleted\n"))

        total_deleted = 0

        # Delete in reverse dependency order (children before parents)
        total_deleted += self._clean_healthcare(dry_run)
        total_deleted += self._clean_notes(dry_run)
        total_deleted += self._clean_cashflow(dry_run)
        total_deleted += self._clean_tasks(dry_run)
        total_deleted += self._clean_legal(dry_run)
        total_deleted += self._clean_assets(dry_run)
        total_deleted += self._clean_stakeholders(dry_run)

        # Reset manifest
        if not dry_run:
            from dashboard.models import SampleDataStatus
            status = SampleDataStatus.load()
            status.manifest = {}
            status.is_loaded = False
            status.loaded_at = None
            status.save()
            self.stdout.write(self.style.SUCCESS(f"\nDone. Removed {total_deleted} sample records. Manifest reset."))
        else:
            self.stdout.write(self.style.WARNING(f"\nDRY RUN complete. Would remove {total_deleted} records."))

    def _delete(self, qs, label, dry_run):
        count = qs.count()
        if count:
            if not dry_run:
                qs.delete()
            action = "Would delete" if dry_run else "Deleted"
            self.stdout.write(f"  {action} {count} {label}")
        return count

    def _clean_stakeholders(self, dry_run):
        from stakeholders.models import Stakeholder, Relationship, ContactLog
        self.stdout.write("Stakeholders:")
        total = 0
        sample = Stakeholder.objects.filter(name__in=SAMPLE_STAKEHOLDER_NAMES)
        # Delete child records first
        total += self._delete(
            ContactLog.objects.filter(stakeholder__in=sample),
            "contact logs", dry_run)
        total += self._delete(
            Relationship.objects.filter(
                Q(from_stakeholder__in=sample) | Q(to_stakeholder__in=sample)),
            "relationships", dry_run)
        total += self._delete(sample, "stakeholders", dry_run)
        return total

    def _clean_assets(self, dry_run):
        from assets.models import (
            RealEstate, Investment, Loan, Vehicle, Aircraft,
            InsurancePolicy, Lease, PropertyOwnership, InvestmentParticipant,
            LoanParty, VehicleOwner, AircraftOwner, PolicyHolder, LeaseParty,
        )
        self.stdout.write("Assets:")
        total = 0

        # Through models first (cascade would handle these, but be explicit)
        props = RealEstate.objects.filter(name__in=SAMPLE_PROPERTY_NAMES)
        invs = Investment.objects.filter(name__in=SAMPLE_INVESTMENT_NAMES)
        lns = Loan.objects.filter(name__in=SAMPLE_LOAN_NAMES)
        vehs = Vehicle.objects.filter(name__in=SAMPLE_VEHICLE_NAMES)
        acs = Aircraft.objects.filter(name__in=SAMPLE_AIRCRAFT_NAMES)
        pols = InsurancePolicy.objects.filter(name__in=SAMPLE_INSURANCE_NAMES)
        lses = Lease.objects.filter(name__in=SAMPLE_LEASE_NAMES)

        total += self._delete(LeaseParty.objects.filter(lease__in=lses), "lease parties", dry_run)
        total += self._delete(lses, "leases", dry_run)
        total += self._delete(PolicyHolder.objects.filter(policy__in=pols), "policy holders", dry_run)
        total += self._delete(pols, "insurance policies", dry_run)
        total += self._delete(AircraftOwner.objects.filter(aircraft__in=acs), "aircraft owners", dry_run)
        total += self._delete(acs, "aircraft", dry_run)
        total += self._delete(VehicleOwner.objects.filter(vehicle__in=vehs), "vehicle owners", dry_run)
        total += self._delete(vehs, "vehicles", dry_run)
        total += self._delete(LoanParty.objects.filter(loan__in=lns), "loan parties", dry_run)
        total += self._delete(lns, "loans", dry_run)
        total += self._delete(InvestmentParticipant.objects.filter(investment__in=invs), "investment participants", dry_run)
        total += self._delete(invs, "investments", dry_run)
        total += self._delete(PropertyOwnership.objects.filter(property__in=props), "property ownerships", dry_run)
        total += self._delete(props, "properties", dry_run)
        return total

    def _clean_legal(self, dry_run):
        from legal.models import LegalMatter, Evidence, LegalCommunication
        self.stdout.write("Legal:")
        total = 0
        matters = LegalMatter.objects.filter(title__in=SAMPLE_LEGAL_TITLES)
        total += self._delete(LegalCommunication.objects.filter(legal_matter__in=matters), "communications", dry_run)
        total += self._delete(Evidence.objects.filter(legal_matter__in=matters), "evidence", dry_run)
        total += self._delete(matters, "legal matters", dry_run)
        return total

    def _clean_tasks(self, dry_run):
        from tasks.models import Task, FollowUp
        self.stdout.write("Tasks:")
        total = 0
        tasks = Task.objects.filter(title__in=SAMPLE_TASK_TITLES)
        total += self._delete(FollowUp.objects.filter(task__in=tasks), "follow-ups", dry_run)
        total += self._delete(tasks, "tasks", dry_run)
        return total

    def _clean_cashflow(self, dry_run):
        from cashflow.models import CashFlowEntry
        self.stdout.write("Cash Flow:")
        total = 0
        total += self._delete(
            CashFlowEntry.objects.filter(description__in=SAMPLE_CASHFLOW_DESCRIPTIONS),
            "cash flow entries", dry_run)
        return total

    def _clean_notes(self, dry_run):
        from notes.models import Note, Tag, Folder
        self.stdout.write("Notes:")
        total = 0
        total += self._delete(Note.objects.filter(title__in=SAMPLE_NOTE_TITLES), "notes", dry_run)
        # Only delete tags/folders if no user notes reference them
        for slug in SAMPLE_TAG_SLUGS:
            tag = Tag.objects.filter(slug=slug).first()
            if tag and not tag.notes.exclude(title__in=SAMPLE_NOTE_TITLES).exists():
                total += self._delete(Tag.objects.filter(pk=tag.pk), f"tag '{slug}'", dry_run)
        for name in SAMPLE_FOLDER_NAMES:
            folder = Folder.objects.filter(name=name).first()
            if folder and not folder.notes.exclude(title__in=SAMPLE_NOTE_TITLES).exists():
                total += self._delete(Folder.objects.filter(pk=folder.pk), f"folder '{name}'", dry_run)
        return total

    def _clean_healthcare(self, dry_run):
        from healthcare.models import (
            Provider, Condition, Prescription, Supplement,
            TestResult, Visit, Advice, Appointment,
        )
        self.stdout.write("Healthcare:")
        total = 0
        providers = Provider.objects.filter(name__in=SAMPLE_PROVIDER_NAMES)
        conditions = Condition.objects.filter(name__in=SAMPLE_CONDITION_NAMES)

        # Delete children first
        total += self._delete(Appointment.objects.filter(provider__in=providers), "appointments", dry_run)
        total += self._delete(Advice.objects.filter(given_by__in=providers), "advice", dry_run)
        total += self._delete(Visit.objects.filter(provider__in=providers), "visits", dry_run)
        total += self._delete(
            TestResult.objects.filter(ordering_provider__in=providers),
            "test results", dry_run)
        total += self._delete(
            Supplement.objects.filter(name__in=SAMPLE_SUPPLEMENT_NAMES),
            "supplements", dry_run)
        total += self._delete(
            Prescription.objects.filter(medication_name__in=SAMPLE_PRESCRIPTION_NAMES),
            "prescriptions", dry_run)
        total += self._delete(conditions, "conditions", dry_run)
        total += self._delete(providers, "providers", dry_run)
        return total
