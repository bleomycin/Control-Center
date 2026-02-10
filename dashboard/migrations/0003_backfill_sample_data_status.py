"""
Data migration: detect pre-existing sample data loaded before SampleDataStatus
existed and populate the manifest so it can be cleanly removed.
"""
from django.db import migrations

# Known sample stakeholder names (the command creates exactly these)
SAMPLE_STAKEHOLDER_NAMES = [
    "Marcus Reed", "Sandra Liu", "Tom Driscoll", "Janet Cobb",
    "Derek Vasquez", "Karen Whitfield", "Ray Holston", "Nina Patel",
    "Victor Huang", "Alicia Moreno", "James Calloway", "Dr. Helen Park",
    "Armanino LLP", "Sarah Chen", "Michael Torres", "Lisa Park",
]

SAMPLE_PROPERTY_NAMES = [
    "1200 Oak Avenue", "450 Elm Street", "3300 Magnolia Blvd",
    "890 Cedar Lane", "15 Riverside Dr",
]

SAMPLE_INVESTMENT_NAMES = [
    "Vanguard Total Market Index", "Schwab S&P 500 ETF",
    "Municipal Bond Fund", "NP Investments LP - Fund II", "Bitcoin Holdings",
]

SAMPLE_LOAN_NAMES = [
    "First National - Oak Ave Mortgage", "First National - Elm St Mortgage",
    "Huang Bridge Loan - Magnolia", "Vehicle Loan - F-150",
]

SAMPLE_LEGAL_TITLES = [
    "Holston Eviction - 1200 Oak Ave", "Cedar Lane Boundary Dispute",
    "Magnolia Blvd Acquisition - Due Diligence", "Riverside Zoning Application",
    "Estate Plan Update",
]

SAMPLE_TASK_TITLES = [
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
]

SAMPLE_NOTE_TITLES = [
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
]


def backfill_sample_status(apps, schema_editor):
    SampleDataStatus = apps.get_model("dashboard", "SampleDataStatus")
    Stakeholder = apps.get_model("stakeholders", "Stakeholder")

    # Check if sample data exists by looking for a known stakeholder
    if not Stakeholder.objects.filter(name="Marcus Reed").exists():
        return  # No sample data present

    Relationship = apps.get_model("stakeholders", "Relationship")
    ContactLog = apps.get_model("stakeholders", "ContactLog")
    RealEstate = apps.get_model("assets", "RealEstate")
    Investment = apps.get_model("assets", "Investment")
    Loan = apps.get_model("assets", "Loan")
    PropertyOwnership = apps.get_model("assets", "PropertyOwnership")
    InvestmentParticipant = apps.get_model("assets", "InvestmentParticipant")
    LoanParty = apps.get_model("assets", "LoanParty")
    LegalMatter = apps.get_model("legal", "LegalMatter")
    Evidence = apps.get_model("legal", "Evidence")
    Task = apps.get_model("tasks", "Task")
    FollowUp = apps.get_model("tasks", "FollowUp")
    CashFlowEntry = apps.get_model("cashflow", "CashFlowEntry")
    Note = apps.get_model("notes", "Note")

    # Gather PKs by known names/titles
    stakeholder_pks = list(
        Stakeholder.objects.filter(name__in=SAMPLE_STAKEHOLDER_NAMES)
        .values_list("pk", flat=True)
    )
    property_pks = list(
        RealEstate.objects.filter(name__in=SAMPLE_PROPERTY_NAMES)
        .values_list("pk", flat=True)
    )
    investment_pks = list(
        Investment.objects.filter(name__in=SAMPLE_INVESTMENT_NAMES)
        .values_list("pk", flat=True)
    )
    loan_pks = list(
        Loan.objects.filter(name__in=SAMPLE_LOAN_NAMES)
        .values_list("pk", flat=True)
    )
    legal_pks = list(
        LegalMatter.objects.filter(title__in=SAMPLE_LEGAL_TITLES)
        .values_list("pk", flat=True)
    )
    task_pks = list(
        Task.objects.filter(title__in=SAMPLE_TASK_TITLES)
        .values_list("pk", flat=True)
    )
    note_pks = list(
        Note.objects.filter(title__in=SAMPLE_NOTE_TITLES)
        .values_list("pk", flat=True)
    )

    # Derived records (children of the above)
    relationship_pks = list(
        Relationship.objects.filter(
            from_stakeholder_id__in=stakeholder_pks
        ).values_list("pk", flat=True)
    )
    contactlog_pks = list(
        ContactLog.objects.filter(
            stakeholder_id__in=stakeholder_pks
        ).values_list("pk", flat=True)
    )
    ownership_pks = list(
        PropertyOwnership.objects.filter(
            property_id__in=property_pks
        ).values_list("pk", flat=True)
    )
    participant_pks = list(
        InvestmentParticipant.objects.filter(
            investment_id__in=investment_pks
        ).values_list("pk", flat=True)
    )
    party_pks = list(
        LoanParty.objects.filter(
            loan_id__in=loan_pks
        ).values_list("pk", flat=True)
    )
    evidence_pks = list(
        Evidence.objects.filter(
            legal_matter_id__in=legal_pks
        ).values_list("pk", flat=True)
    )
    followup_pks = list(
        FollowUp.objects.filter(
            task_id__in=task_pks
        ).values_list("pk", flat=True)
    )
    # Cash flow entries linked to sample stakeholders or sample properties/loans
    cashflow_pks = list(
        CashFlowEntry.objects.filter(
            related_stakeholder_id__in=stakeholder_pks
        ).values_list("pk", flat=True)
    )
    # Also get entries with no stakeholder but linked to sample properties/loans
    cashflow_pks += list(
        CashFlowEntry.objects.filter(
            related_stakeholder__isnull=True,
        ).filter(
            related_property_id__in=property_pks,
        ).values_list("pk", flat=True)
    )
    cashflow_pks += list(
        CashFlowEntry.objects.filter(
            related_stakeholder__isnull=True,
            related_property__isnull=True,
        ).filter(
            related_loan_id__in=loan_pks,
        ).values_list("pk", flat=True)
    )
    # Remaining unlinked entries (like "Property tax - all properties")
    cashflow_pks += list(
        CashFlowEntry.objects.filter(
            related_stakeholder__isnull=True,
            related_property__isnull=True,
            related_loan__isnull=True,
            description__in=[
                "Property tax - all properties",
                "Magnolia closing - closing costs",
            ],
        ).values_list("pk", flat=True)
    )
    cashflow_pks = list(set(cashflow_pks))  # dedupe

    manifest = {
        "stakeholders.stakeholder": stakeholder_pks,
        "stakeholders.relationship": relationship_pks,
        "stakeholders.contactlog": contactlog_pks,
        "assets.realestate": property_pks,
        "assets.investment": investment_pks,
        "assets.loan": loan_pks,
        "assets.propertyownership": ownership_pks,
        "assets.investmentparticipant": participant_pks,
        "assets.loanparty": party_pks,
        "legal.legalmatter": legal_pks,
        "legal.evidence": evidence_pks,
        "tasks.task": task_pks,
        "tasks.followup": followup_pks,
        "cashflow.cashflowentry": cashflow_pks,
        "notes.note": note_pks,
    }

    from django.utils import timezone
    obj, _ = SampleDataStatus.objects.get_or_create(pk=1)
    obj.is_loaded = True
    obj.manifest = manifest
    obj.loaded_at = timezone.now()
    obj.save()


class Migration(migrations.Migration):
    dependencies = [
        ("dashboard", "0002_sampledatastatus"),
        ("stakeholders", "0001_initial"),
        ("assets", "0002_loan_related_asset_fks"),
        ("legal", "0001_initial"),
        ("tasks", "0005_remove_fk_rename_m2m"),
        ("cashflow", "0001_initial"),
        ("notes", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill_sample_status, migrations.RunPython.noop),
    ]
