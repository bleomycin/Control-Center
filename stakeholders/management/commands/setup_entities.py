"""
One-time setup command to configure Entity type, tab, and parent hierarchy.

Safe to run multiple times — all operations are idempotent.

Usage:
    python manage.py setup_entities
    python manage.py setup_entities --dry-run
"""
from django.core.management.base import BaseCommand

from dashboard.choices import invalidate_choice_cache
from dashboard.models import ChoiceOption
from stakeholders.models import Stakeholder, StakeholderTab

OWNER_NAME = "314SG, LLC"

CHILD_ENTITY_NAMES = [
    "100% Owned (Managed)",
    "CAP 2, LLC / Equitas Investments, LLC",
    "CAP Baseline, LLC",
    "CAP Cincy, LLC",
    "CAP Eagle, LLC",
    "CAP Ellsworth, LLC",
    "CAP Witchduck, LLC",
    "SGAS Holdings, LLC",
    "TIC - Acq. %: 63.44 / 36.56",
]


class Command(BaseCommand):
    help = "Set up Entity type, Entities tab, and 314SG parent hierarchy"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Preview changes without saving")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY RUN ===\n"))

        # 1. Create "Entity" ChoiceOption
        exists = ChoiceOption.objects.filter(category="entity_type", value="entity").exists()
        if exists:
            self.stdout.write("  ChoiceOption 'entity' already exists")
        elif dry_run:
            self.stdout.write(self.style.NOTICE("  WOULD CREATE ChoiceOption: entity -> Entity"))
        else:
            ChoiceOption.objects.create(
                category="entity_type", value="entity", label="Entity", sort_order=9,
            )
            self.stdout.write(self.style.SUCCESS("  Created ChoiceOption: entity -> Entity"))

        # 2. Create "Entities" StakeholderTab
        tab = StakeholderTab.objects.filter(key="entities").first()
        if tab:
            self.stdout.write(f"  Entities tab already exists (pk={tab.pk})")
        elif dry_run:
            self.stdout.write(self.style.NOTICE("  WOULD CREATE StakeholderTab: Entities"))
        else:
            last = StakeholderTab.objects.order_by("-sort_order").first()
            sort = (last.sort_order + 1) if last else 0
            tab = StakeholderTab.objects.create(
                key="entities", label="Entities",
                entity_types=["entity"], sort_order=sort,
            )
            self.stdout.write(self.style.SUCCESS(f"  Created StakeholderTab: Entities (pk={tab.pk})"))

        # 3. Remove "entity" from Business Partners tab if present
        bp_tab = StakeholderTab.objects.filter(key="business-partners").first()
        if bp_tab and "entity" in bp_tab.entity_types:
            if dry_run:
                self.stdout.write(self.style.NOTICE(
                    "  WOULD REMOVE 'entity' from Business Partners tab"))
            else:
                bp_tab.entity_types.remove("entity")
                bp_tab.save()
                self.stdout.write(self.style.SUCCESS(
                    "  Removed 'entity' from Business Partners tab"))
        else:
            self.stdout.write("  Business Partners tab already clean")

        # 4. Reclassify 314SG + children to "entity" type
        all_names = [OWNER_NAME] + CHILD_ENTITY_NAMES
        to_reclassify = Stakeholder.objects.filter(
            name__in=all_names,
        ).exclude(entity_type="entity")
        count = to_reclassify.count()
        if count:
            if dry_run:
                self.stdout.write(self.style.NOTICE(
                    f"  WOULD RECLASSIFY {count} stakeholders to 'entity':"))
                for s in to_reclassify:
                    self.stdout.write(f"    {s.name} ({s.entity_type} -> entity)")
            else:
                to_reclassify.update(entity_type="entity")
                self.stdout.write(self.style.SUCCESS(
                    f"  Reclassified {count} stakeholders to 'entity'"))
        else:
            self.stdout.write("  All target stakeholders already typed as 'entity'")

        # 5. Set parent_organization on child entities -> 314SG
        owner = Stakeholder.objects.filter(name=OWNER_NAME).first()
        if not owner:
            self.stdout.write(self.style.WARNING(
                f"  {OWNER_NAME} not found — skipping parent assignment"))
        else:
            children = Stakeholder.objects.filter(
                name__in=CHILD_ENTITY_NAMES, parent_organization__isnull=True,
            )
            count = children.count()
            if count:
                if dry_run:
                    self.stdout.write(self.style.NOTICE(
                        f"  WOULD SET parent_organization on {count} children:"))
                    for s in children:
                        self.stdout.write(f"    {s.name} -> {OWNER_NAME}")
                else:
                    children.update(parent_organization=owner)
                    self.stdout.write(self.style.SUCCESS(
                        f"  Set parent_organization on {count} children -> {OWNER_NAME}"))
            else:
                self.stdout.write("  All children already have parent_organization set")

        # 6. Invalidate choice cache
        if not dry_run:
            invalidate_choice_cache()

        self.stdout.write(self.style.SUCCESS("\nDone."))
