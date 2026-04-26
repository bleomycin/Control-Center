"""
Management command to safely remove sample data by matching known names/identifiers.
Unlike --hard-reset, this preserves any user-created production data.

Names are imported from load_sample_data.SAMPLE_NAMES (single source of truth).

Usage: python manage.py clean_sample_data [--dry-run]
"""
from django.core.management.base import BaseCommand
from django.db.models import Q

from dashboard.management.commands.load_sample_data import SAMPLE_NAMES


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
        total_deleted += self._clean_assistant(dry_run)
        total_deleted += self._clean_documents(dry_run)
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
        names = SAMPLE_NAMES["stakeholders"]
        sample = Stakeholder.objects.filter(name__in=names)
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

        props = RealEstate.objects.filter(name__in=SAMPLE_NAMES["properties"])
        invs = Investment.objects.filter(name__in=SAMPLE_NAMES["investments"])
        lns = Loan.objects.filter(name__in=SAMPLE_NAMES["loans"])
        vehs = Vehicle.objects.filter(name__in=SAMPLE_NAMES["vehicles"])
        acs = Aircraft.objects.filter(name__in=SAMPLE_NAMES["aircraft"])
        pols = InsurancePolicy.objects.filter(name__in=SAMPLE_NAMES["insurance"])
        lses = Lease.objects.filter(name__in=SAMPLE_NAMES["leases"])

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
        matters = LegalMatter.objects.filter(title__in=SAMPLE_NAMES["legal_matters"])
        total += self._delete(LegalCommunication.objects.filter(legal_matter__in=matters), "communications", dry_run)
        total += self._delete(Evidence.objects.filter(legal_matter__in=matters), "evidence", dry_run)
        total += self._delete(matters, "legal matters", dry_run)
        return total

    def _clean_tasks(self, dry_run):
        from tasks.models import Task, FollowUp
        self.stdout.write("Tasks:")
        total = 0
        tasks = Task.objects.filter(title__in=SAMPLE_NAMES["tasks"])
        total += self._delete(FollowUp.objects.filter(task__in=tasks), "follow-ups", dry_run)
        total += self._delete(tasks, "tasks", dry_run)
        return total

    def _clean_cashflow(self, dry_run):
        from cashflow.models import CashFlowEntry
        self.stdout.write("Cash Flow:")
        total = 0
        total += self._delete(
            CashFlowEntry.objects.filter(description__in=SAMPLE_NAMES["cashflow"]),
            "cash flow entries", dry_run)
        return total

    def _clean_notes(self, dry_run):
        from notes.models import Note, Tag, Folder
        self.stdout.write("Notes:")
        total = 0
        note_names = SAMPLE_NAMES["notes"]
        total += self._delete(Note.objects.filter(title__in=note_names), "notes", dry_run)
        # Only delete tags/folders if no user notes reference them
        for slug in SAMPLE_NAMES["tags"]:
            tag = Tag.objects.filter(slug=slug).first()
            if tag and not tag.notes.exclude(title__in=note_names).exists():
                total += self._delete(Tag.objects.filter(pk=tag.pk), f"tag '{slug}'", dry_run)
        for name in SAMPLE_NAMES["folders"]:
            folder = Folder.objects.filter(name=name).first()
            if folder and not folder.notes.exclude(title__in=note_names).exists():
                total += self._delete(Folder.objects.filter(pk=folder.pk), f"folder '{name}'", dry_run)
        return total

    def _clean_documents(self, dry_run):
        from documents.models import Document
        self.stdout.write("Documents:")
        total = 0
        total += self._delete(
            Document.objects.filter(title__in=SAMPLE_NAMES["documents"]),
            "documents", dry_run)
        return total

    def _clean_assistant(self, dry_run):
        from assistant.models import ChatSession, ChatMessage
        self.stdout.write("Assistant:")
        total = 0
        sample = ChatSession.objects.filter(
            title__in=SAMPLE_NAMES["chat_sessions"]
        )
        # Cascade on ChatSession would remove messages, but we count them
        # explicitly so the dry-run report is accurate.
        total += self._delete(
            ChatMessage.objects.filter(session__in=sample),
            "chat messages", dry_run)
        total += self._delete(sample, "chat sessions", dry_run)
        return total

    def _clean_healthcare(self, dry_run):
        from healthcare.models import (
            Provider, Condition, Prescription, Supplement,
            TestResult, Visit, Advice, Appointment,
        )
        self.stdout.write("Healthcare:")
        total = 0
        providers = Provider.objects.filter(name__in=SAMPLE_NAMES["providers"])
        conditions = Condition.objects.filter(name__in=SAMPLE_NAMES["conditions"])

        total += self._delete(Appointment.objects.filter(provider__in=providers), "appointments", dry_run)
        total += self._delete(Advice.objects.filter(given_by__in=providers), "advice", dry_run)
        total += self._delete(Visit.objects.filter(provider__in=providers), "visits", dry_run)
        total += self._delete(
            TestResult.objects.filter(ordering_provider__in=providers),
            "test results", dry_run)
        total += self._delete(
            Supplement.objects.filter(name__in=SAMPLE_NAMES["supplements"]),
            "supplements", dry_run)
        total += self._delete(
            Prescription.objects.filter(medication_name__in=SAMPLE_NAMES["prescriptions"]),
            "prescriptions", dry_run)
        total += self._delete(conditions, "conditions", dry_run)
        total += self._delete(providers, "providers", dry_run)
        return total
