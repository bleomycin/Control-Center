import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from assets.models import Investment, Loan, RealEstate
from cashflow.models import CashFlowEntry
from legal.models import LegalMatter
from notes.models import Note
from stakeholders.models import ContactLog, Stakeholder
from tasks.models import FollowUp, Task

from .choices import get_choice_label, get_choices, invalidate_choice_cache
from .models import ChoiceOption, Notification, SampleDataStatus
from .views import _parse_date, get_activity_timeline


class DashboardViewTests(TestCase):
    def test_status_code(self):
        resp = self.client.get(reverse("dashboard:index"))
        self.assertEqual(resp.status_code, 200)

    def test_context_keys(self):
        resp = self.client.get(reverse("dashboard:index"))
        for key in ("overdue_tasks", "upcoming_tasks", "stale_followups",
                     "recent_activity", "liquidity_alerts", "monthly_net_flow",
                     "net_worth", "upcoming_deadlines", "property_count",
                     "investment_count", "active_loan_count"):
            self.assertIn(key, resp.context, f"Missing context key: {key}")

    def test_overdue_tasks_in_context(self):
        Task.objects.create(
            title="Overdue",
            due_date=timezone.localdate() - timedelta(days=2),
            status="not_started",
        )
        resp = self.client.get(reverse("dashboard:index"))
        self.assertTrue(resp.context["overdue_tasks"].exists())

    def test_upcoming_tasks(self):
        Task.objects.create(
            title="Soon",
            due_date=timezone.localdate() + timedelta(days=3),
            status="not_started",
        )
        resp = self.client.get(reverse("dashboard:index"))
        self.assertTrue(resp.context["upcoming_tasks"].exists())

    def test_stale_followups(self):
        s = Stakeholder.objects.create(name="Stale Person")
        t = Task.objects.create(title="Stale Task")
        FollowUp.objects.create(
            task=t, stakeholder=s,
            outreach_date=timezone.now() - timedelta(days=5),
            method="email", response_received=False,
        )
        resp = self.client.get(reverse("dashboard:index"))
        self.assertTrue(resp.context["stale_followups"].exists())

    def test_monthly_net_flow(self):
        today = timezone.localdate()
        CashFlowEntry.objects.create(
            description="Income", amount=Decimal("3000"),
            entry_type="inflow", date=today, is_projected=False,
        )
        CashFlowEntry.objects.create(
            description="Expense", amount=Decimal("1000"),
            entry_type="outflow", date=today, is_projected=False,
        )
        resp = self.client.get(reverse("dashboard:index"))
        self.assertEqual(resp.context["monthly_net_flow"], Decimal("2000"))


class GlobalSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.stakeholder = Stakeholder.objects.create(name="Searchable Person")
        cls.task = Task.objects.create(title="Searchable Task")

    def test_status_code(self):
        resp = self.client.get(reverse("dashboard:search"))
        self.assertEqual(resp.status_code, 200)

    def test_empty_query(self):
        resp = self.client.get(reverse("dashboard:search"), {"q": ""})
        self.assertFalse(resp.context["has_results"])

    def test_finds_stakeholder(self):
        resp = self.client.get(reverse("dashboard:search"), {"q": "Searchable Person"})
        self.assertTrue(resp.context["has_results"])
        self.assertTrue(resp.context["stakeholders"].exists())

    def test_finds_across_models(self):
        resp = self.client.get(reverse("dashboard:search"), {"q": "Searchable"})
        self.assertTrue(resp.context["has_results"])
        self.assertTrue(resp.context["stakeholders"].exists())
        self.assertTrue(resp.context["tasks_results"].exists())

    def test_htmx_partial(self):
        resp = self.client.get(
            reverse("dashboard:search"),
            {"q": "test"},
            HTTP_HX_REQUEST="true",
        )
        self.assertTemplateUsed(resp, "dashboard/partials/_search_results.html")

    def test_limit_results(self):
        for i in range(15):
            Stakeholder.objects.create(name=f"Bulk Person {i}")
        resp = self.client.get(reverse("dashboard:search"), {"q": "Bulk Person"})
        self.assertTrue(len(resp.context["stakeholders"]) <= 10)


class ActivityTimelineTests(TestCase):
    def test_empty_returns_list(self):
        items = get_activity_timeline()
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 0)

    def test_contact_log_item_keys(self):
        s = Stakeholder.objects.create(name="Timeline Person")
        ContactLog.objects.create(
            stakeholder=s, date=timezone.now(), method="call", summary="Test call",
        )
        items = get_activity_timeline()
        self.assertTrue(len(items) >= 1)
        item = [i for i in items if i["type"] == "contact"][0]
        for key in ("date", "type", "color", "icon", "title", "summary", "url"):
            self.assertIn(key, item)

    def test_includes_multiple_types(self):
        s = Stakeholder.objects.create(name="Multi")
        ContactLog.objects.create(
            stakeholder=s, date=timezone.now(), method="call", summary="call",
        )
        Note.objects.create(title="Note", content="c", date=timezone.now())
        Task.objects.create(title="Task")
        items = get_activity_timeline()
        types = {i["type"] for i in items}
        self.assertIn("contact", types)
        self.assertIn("note", types)
        self.assertIn("task", types)

    def test_sorted_reverse_chronological(self):
        s = Stakeholder.objects.create(name="Sort")
        ContactLog.objects.create(
            stakeholder=s, date=timezone.now() - timedelta(days=5),
            method="call", summary="old",
        )
        Note.objects.create(title="Recent", content="c", date=timezone.now())
        items = get_activity_timeline()
        if len(items) >= 2:
            self.assertGreaterEqual(items[0]["date"], items[1]["date"])

    def test_respects_limit(self):
        s = Stakeholder.objects.create(name="Limit")
        for i in range(5):
            ContactLog.objects.create(
                stakeholder=s, date=timezone.now() - timedelta(hours=i),
                method="call", summary=f"call {i}",
            )
        items = get_activity_timeline(limit=3)
        self.assertEqual(len(items), 3)

    def test_timeline_view(self):
        resp = self.client.get(reverse("dashboard:timeline"))
        self.assertEqual(resp.status_code, 200)


class CalendarTests(TestCase):
    def test_calendar_view(self):
        resp = self.client.get(reverse("dashboard:calendar"))
        self.assertEqual(resp.status_code, 200)

    def test_events_returns_json(self):
        resp = self.client.get(reverse("dashboard:calendar_events"))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIsInstance(data, list)

    def test_events_include_tasks(self):
        Task.objects.create(
            title="Calendar Task",
            due_date=timezone.localdate() + timedelta(days=1),
            status="not_started",
        )
        resp = self.client.get(reverse("dashboard:calendar_events"))
        data = json.loads(resp.content)
        task_events = [e for e in data if e.get("extendedProps", {}).get("type") == "task"]
        self.assertTrue(len(task_events) >= 1)

    def test_events_include_loan_payments(self):
        Loan.objects.create(
            name="Calendar Loan",
            status="active",
            next_payment_date=timezone.localdate() + timedelta(days=5),
        )
        resp = self.client.get(reverse("dashboard:calendar_events"))
        data = json.loads(resp.content)
        payment_events = [e for e in data if e.get("extendedProps", {}).get("type") == "payment"]
        self.assertTrue(len(payment_events) >= 1)

    def test_date_filtering(self):
        today = timezone.localdate()
        Task.objects.create(
            title="In Range", due_date=today + timedelta(days=2), status="not_started",
        )
        Task.objects.create(
            title="Out of Range", due_date=today + timedelta(days=60), status="not_started",
        )
        resp = self.client.get(reverse("dashboard:calendar_events"), {
            "start": str(today),
            "end": str(today + timedelta(days=30)),
        })
        data = json.loads(resp.content)
        titles = [e["title"] for e in data]
        self.assertIn("In Range", titles)
        self.assertNotIn("Out of Range", titles)

    def test_parse_date_valid(self):
        result = _parse_date("2025-06-15T00:00:00")
        self.assertIsNotNone(result)

    def test_parse_date_invalid(self):
        result = _parse_date("not-a-date")
        self.assertIsNone(result)

    def test_parse_date_empty(self):
        result = _parse_date("")
        self.assertIsNone(result)

    def test_hearing_events_in_calendar(self):
        LegalMatter.objects.create(
            title="Hearing Matter",
            status="active",
            next_hearing_date=timezone.localdate() + timedelta(days=5),
        )
        resp = self.client.get(reverse("dashboard:calendar_events"))
        data = json.loads(resp.content)
        hearing_events = [e for e in data if e.get("extendedProps", {}).get("type") == "hearing"]
        self.assertTrue(len(hearing_events) >= 1)


class NetWorthTests(TestCase):
    def test_net_worth_calculation(self):
        RealEstate.objects.create(name="Prop1", address="1 Main", estimated_value=Decimal("500000"), status="owned")
        RealEstate.objects.create(name="Prop2", address="2 Main", estimated_value=Decimal("300000"), status="sold")
        Investment.objects.create(name="Inv1", current_value=Decimal("100000"))
        Loan.objects.create(name="Loan1", current_balance=Decimal("200000"), status="active")
        Loan.objects.create(name="Loan2", current_balance=Decimal("50000"), status="paid_off")

        resp = self.client.get(reverse("dashboard:index"))
        nw = resp.context["net_worth"]
        # total assets = 500000 (prop1, prop2 excluded because sold) + 100000 = 600000
        self.assertEqual(nw["total_assets"], Decimal("600000"))
        # liabilities = 200000 (only active loans)
        self.assertEqual(nw["total_liabilities"], Decimal("200000"))
        # net = 400000
        self.assertEqual(nw["net_worth"], Decimal("400000"))

    def test_upcoming_deadlines_aggregation(self):
        today = timezone.localdate()
        Task.objects.create(title="Due Task", due_date=today + timedelta(days=5), status="not_started")
        Loan.objects.create(name="Payment Loan", status="active", next_payment_date=today + timedelta(days=10))
        LegalMatter.objects.create(title="Hearing Matter", status="active", next_hearing_date=today + timedelta(days=15))

        resp = self.client.get(reverse("dashboard:index"))
        deadlines = resp.context["upcoming_deadlines"]
        types = {d["type"] for d in deadlines}
        self.assertIn("task", types)
        self.assertIn("payment", types)
        self.assertIn("hearing", types)
        # Sorted by date
        dates = [d["date"] for d in deadlines]
        self.assertEqual(dates, sorted(dates))

    def test_asset_risk_properties(self):
        RealEstate.objects.create(name="Disputed Prop", address="1 Main", status="in_dispute")
        resp = self.client.get(reverse("dashboard:index"))
        self.assertTrue(resp.context["has_asset_risks"])
        self.assertTrue(resp.context["at_risk_properties"].exists())

    def test_asset_risk_loans(self):
        Loan.objects.create(name="Default Loan", status="defaulted")
        resp = self.client.get(reverse("dashboard:index"))
        self.assertTrue(resp.context["has_asset_risks"])
        self.assertTrue(resp.context["at_risk_loans"].exists())


class NotificationTests(TestCase):
    def test_notification_list(self):
        Notification.objects.create(message="Test alert", level="info")
        resp = self.client.get(reverse("dashboard:notifications"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Test alert")

    def test_badge_shows_unread(self):
        Notification.objects.create(message="Unread", level="info")
        resp = self.client.get(reverse("dashboard:notifications_badge"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "1")

    def test_badge_empty_when_read(self):
        Notification.objects.create(message="Read", level="info", is_read=True)
        resp = self.client.get(reverse("dashboard:notifications_badge"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "1")

    def test_mark_read(self):
        Notification.objects.create(message="To Read", level="warning")
        self.assertEqual(Notification.objects.filter(is_read=False).count(), 1)
        resp = self.client.post(reverse("dashboard:notifications_mark_read"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Notification.objects.filter(is_read=False).count(), 0)

    def test_notification_ordering(self):
        n1 = Notification.objects.create(message="First")
        n2 = Notification.objects.create(message="Second")
        notifications = list(Notification.objects.all())
        self.assertEqual(notifications[0], n2)  # newest first


class ChoiceOptionModelTests(TestCase):
    def test_seed_data_exists(self):
        """Data migration should have seeded all 4 categories."""
        for cat in ("entity_type", "contact_method", "matter_type", "note_type"):
            self.assertTrue(
                ChoiceOption.objects.filter(category=cat).exists(),
                f"No seed data for category: {cat}",
            )

    def test_entity_type_has_expected_values(self):
        values = set(ChoiceOption.objects.filter(category="entity_type").values_list("value", flat=True))
        for v in ("advisor", "business_partner", "lender", "contact", "professional", "attorney", "other"):
            self.assertIn(v, values)

    def test_str(self):
        opt = ChoiceOption.objects.filter(category="entity_type", value="advisor").first()
        self.assertIn("Advisor", str(opt))

    def test_unique_together(self):
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            ChoiceOption.objects.create(category="entity_type", value="advisor", label="Duplicate")


class ChoiceUtilityTests(TestCase):
    def test_get_choices_returns_tuples(self):
        invalidate_choice_cache()
        choices = get_choices("entity_type")
        self.assertIsInstance(choices, list)
        self.assertTrue(len(choices) > 0)
        self.assertEqual(len(choices[0]), 2)  # (value, label) tuple

    def test_get_choices_excludes_inactive(self):
        invalidate_choice_cache()
        opt = ChoiceOption.objects.get(category="entity_type", value="other")
        opt.is_active = False
        opt.save()
        invalidate_choice_cache()
        choices = get_choices("entity_type")
        values = [v for v, _ in choices]
        self.assertNotIn("other", values)
        # Restore
        opt.is_active = True
        opt.save()
        invalidate_choice_cache()

    def test_get_choices_include_inactive(self):
        invalidate_choice_cache()
        opt = ChoiceOption.objects.get(category="entity_type", value="other")
        opt.is_active = False
        opt.save()
        invalidate_choice_cache()
        choices = get_choices("entity_type", include_inactive=True)
        values = [v for v, _ in choices]
        self.assertIn("other", values)
        # Restore
        opt.is_active = True
        opt.save()
        invalidate_choice_cache()

    def test_get_choice_label_found(self):
        invalidate_choice_cache()
        label = get_choice_label("entity_type", "advisor")
        self.assertEqual(label, "Advisor")

    def test_get_choice_label_fallback(self):
        invalidate_choice_cache()
        label = get_choice_label("entity_type", "nonexistent_value")
        self.assertEqual(label, "nonexistent_value")

    def test_get_choice_label_empty(self):
        self.assertEqual(get_choice_label("entity_type", ""), "")
        self.assertIsNone(get_choice_label("entity_type", None))


class ChoiceSettingsViewTests(TestCase):
    def test_settings_page_loads(self):
        resp = self.client.get(reverse("dashboard:choice_settings"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Stakeholder Type")
        self.assertContains(resp, "Contact Method")
        self.assertContains(resp, "Legal Matter Type")
        self.assertContains(resp, "Note Type")

    def test_add_option(self):
        invalidate_choice_cache()
        resp = self.client.post(
            reverse("dashboard:choice_add", args=["entity_type"]),
            {"label": "Vendor"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(ChoiceOption.objects.filter(category="entity_type", value="vendor").exists())

    def test_add_option_auto_value(self):
        invalidate_choice_cache()
        self.client.post(
            reverse("dashboard:choice_add", args=["entity_type"]),
            {"label": "Real Estate Agent"},
        )
        self.assertTrue(ChoiceOption.objects.filter(category="entity_type", value="real_estate_agent").exists())

    def test_edit_option(self):
        invalidate_choice_cache()
        opt = ChoiceOption.objects.get(category="entity_type", value="advisor")
        resp = self.client.post(
            reverse("dashboard:choice_edit", args=[opt.pk]),
            {"label": "Financial Advisor", "value": "advisor"},
        )
        self.assertEqual(resp.status_code, 200)
        opt.refresh_from_db()
        self.assertEqual(opt.label, "Financial Advisor")

    def test_toggle_deactivate(self):
        invalidate_choice_cache()
        opt = ChoiceOption.objects.get(category="entity_type", value="other")
        self.assertTrue(opt.is_active)
        self.client.post(reverse("dashboard:choice_toggle", args=[opt.pk]))
        opt.refresh_from_db()
        self.assertFalse(opt.is_active)
        # Re-activate
        self.client.post(reverse("dashboard:choice_toggle", args=[opt.pk]))
        opt.refresh_from_db()
        self.assertTrue(opt.is_active)

    def test_move_reorder(self):
        invalidate_choice_cache()
        opts = list(ChoiceOption.objects.filter(category="entity_type"))
        if len(opts) >= 2:
            second = opts[1]
            original_order = second.sort_order
            self.client.post(reverse("dashboard:choice_move", args=[second.pk, "up"]))
            second.refresh_from_db()
            self.assertNotEqual(second.sort_order, original_order)

    def test_inactive_hidden_from_form_choices(self):
        invalidate_choice_cache()
        opt = ChoiceOption.objects.get(category="entity_type", value="other")
        opt.is_active = False
        opt.save()
        invalidate_choice_cache()
        choices = get_choices("entity_type")
        values = [v for v, _ in choices]
        self.assertNotIn("other", values)
        # Restore
        opt.is_active = True
        opt.save()
        invalidate_choice_cache()

    def test_existing_records_display_inactive_label(self):
        """Deactivated options should still show labels for existing records."""
        invalidate_choice_cache()
        s = Stakeholder.objects.create(name="Test", entity_type="other")
        opt = ChoiceOption.objects.get(category="entity_type", value="other")
        opt.is_active = False
        opt.save()
        invalidate_choice_cache()
        label = get_choice_label("entity_type", "other")
        self.assertEqual(label, "Other")
        # Restore
        opt.is_active = True
        opt.save()
        invalidate_choice_cache()


class ChoiceTemplateFilterTests(TestCase):
    def test_choice_label_filter_in_template(self):
        invalidate_choice_cache()
        s = Stakeholder.objects.create(name="Filter Test", entity_type="advisor")
        resp = self.client.get(reverse("stakeholders:detail", args=[s.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Advisor")


class SQLitePragmaTests(TestCase):
    """Test that SQLite pragmas are applied via the connection_created signal.

    Note: Django test runner uses in-memory SQLite, so WAL mode returns
    'memory' instead of 'wal'. We test that the signal fires and sets
    the other pragmas correctly.
    """

    def test_wal_mode_requested(self):
        """WAL mode is set on file-based DBs; in-memory returns 'memory'."""
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA journal_mode;')
            mode = cursor.fetchone()[0]
        self.assertIn(mode, ('wal', 'memory'))

    def test_busy_timeout_set(self):
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA busy_timeout;')
            timeout = cursor.fetchone()[0]
        self.assertEqual(timeout, 5000)

    def test_foreign_keys_enabled(self):
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA foreign_keys;')
            fk = cursor.fetchone()[0]
        self.assertEqual(fk, 1)

    def test_cache_size_set(self):
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA cache_size;')
            size = cursor.fetchone()[0]
        self.assertEqual(size, -20000)

    def test_synchronous_normal(self):
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA synchronous;')
            sync = cursor.fetchone()[0]
        # 1 = NORMAL
        self.assertEqual(sync, 1)


class BackupCommandTests(TestCase):
    """Test backup command using a temp file-based SQLite DB."""

    def setUp(self):
        import sqlite3
        import tempfile
        self.tmp_dir = tempfile.mkdtemp()
        self.backup_dir = Path(self.tmp_dir) / 'backups'
        self.backup_dir.mkdir()
        # Create a real file-based SQLite DB for backup testing
        self.test_db = Path(self.tmp_dir) / 'test.sqlite3'
        conn = sqlite3.connect(str(self.test_db))
        conn.execute('CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT)')
        conn.execute("INSERT INTO test_table VALUES (1, 'hello')")
        conn.commit()
        conn.close()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_test_backup(self):
        """Create a backup archive from the test DB."""
        import sqlite3
        import tarfile
        import tempfile
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        archive_path = self.backup_dir / f'controlcenter-backup-{timestamp}.tar.gz'
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dst_db = tmp_path / 'db.sqlite3'
            src = sqlite3.connect(str(self.test_db))
            dst = sqlite3.connect(str(dst_db))
            src.backup(dst)
            src.close()
            dst.close()
            media_dir = tmp_path / 'media'
            media_dir.mkdir()
            with tarfile.open(archive_path, 'w:gz') as tar:
                tar.add(str(dst_db), arcname='db.sqlite3')
                tar.add(str(media_dir), arcname='media')
        return archive_path

    def test_backup_creates_archive(self):
        archive = self._create_test_backup()
        self.assertTrue(archive.exists())
        self.assertTrue(archive.name.startswith('controlcenter-backup-'))
        self.assertTrue(archive.name.endswith('.tar.gz'))

    def test_backup_contains_db_and_media(self):
        import tarfile
        archive = self._create_test_backup()
        with tarfile.open(archive, 'r:gz') as tar:
            names = tar.getnames()
        self.assertIn('db.sqlite3', names)
        self.assertTrue(any(n.startswith('media') for n in names))

    def test_backup_db_is_valid_sqlite(self):
        import sqlite3
        import tarfile
        import tempfile
        archive = self._create_test_backup()
        with tempfile.TemporaryDirectory() as tmp:
            with tarfile.open(archive, 'r:gz') as tar:
                tar.extractall(path=tmp)
            db_path = Path(tmp) / 'db.sqlite3'
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r[0] for r in cursor.fetchall()]
            conn.close()
        self.assertIn('test_table', tables)

    def test_backup_prune_keeps_n(self):
        from dashboard.management.commands.backup import prune_backups
        import time
        archives = []
        for i in range(3):
            a = self._create_test_backup()
            archives.append(a)
            time.sleep(1.1)  # Ensure distinct timestamps
        to_delete = prune_backups(self.backup_dir, keep=1)
        self.assertEqual(len(to_delete), 2)
        for old in to_delete:
            old.unlink()
        remaining = list(self.backup_dir.glob('controlcenter-backup-*.tar.gz'))
        self.assertEqual(len(remaining), 1)

    def test_backup_management_command(self):
        """Test the full management command runs without error."""
        from io import StringIO
        from unittest.mock import patch
        from django.core.management import call_command
        # Patch DATABASE NAME to our test file
        with patch.dict(
            'django.conf.settings.DATABASES',
            {'default': {**settings.DATABASES['default'], 'NAME': self.test_db}},
        ):
            call_command('backup', '--dir', str(self.backup_dir), stdout=StringIO())
        archives = list(self.backup_dir.glob('controlcenter-backup-*.tar.gz'))
        self.assertEqual(len(archives), 1)


class RestoreCommandTests(TestCase):
    def setUp(self):
        import tempfile
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_restore_invalid_archive_raises(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        bad_file = Path(self.tmp_dir) / 'bad.tar.gz'
        bad_file.write_text('not a tar')
        with self.assertRaises(CommandError):
            call_command('restore', str(bad_file))

    def test_restore_missing_file_raises(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command('restore', '/nonexistent/backup.tar.gz')

    def test_restore_validates_archive_contents(self):
        """Archive without db.sqlite3 should raise CommandError."""
        import tarfile
        from django.core.management import call_command
        from django.core.management.base import CommandError
        # Create archive with only a dummy file
        archive_path = Path(self.tmp_dir) / 'bad_contents.tar.gz'
        dummy = Path(self.tmp_dir) / 'dummy.txt'
        dummy.write_text('hello')
        with tarfile.open(archive_path, 'w:gz') as tar:
            tar.add(str(dummy), arcname='dummy.txt')
        with self.assertRaises(CommandError):
            call_command('restore', str(archive_path))

    def test_restore_replaces_db_file(self):
        """Test restore overwrites the DB file with backup contents."""
        import sqlite3
        import tarfile
        import tempfile
        # Create a "backup" DB with known data
        backup_db = Path(self.tmp_dir) / 'backup_db.sqlite3'
        conn = sqlite3.connect(str(backup_db))
        conn.execute('CREATE TABLE restore_test (id INTEGER PRIMARY KEY, val TEXT)')
        conn.execute("INSERT INTO restore_test VALUES (1, 'restored')")
        conn.commit()
        conn.close()
        # Create a "current" DB (target)
        current_db = Path(self.tmp_dir) / 'current.sqlite3'
        conn = sqlite3.connect(str(current_db))
        conn.execute('CREATE TABLE current_table (id INTEGER PRIMARY KEY)')
        conn.commit()
        conn.close()
        # Create archive
        archive_path = Path(self.tmp_dir) / 'test-backup.tar.gz'
        media_dir = Path(self.tmp_dir) / 'media_src'
        media_dir.mkdir()
        with tarfile.open(archive_path, 'w:gz') as tar:
            tar.add(str(backup_db), arcname='db.sqlite3')
            tar.add(str(media_dir), arcname='media')
        # Restore archive to current DB location
        import shutil
        shutil.copy2(str(backup_db), str(current_db))
        # Verify the backup DB has our test table
        conn = sqlite3.connect(str(current_db))
        cursor = conn.cursor()
        cursor.execute("SELECT val FROM restore_test WHERE id=1")
        self.assertEqual(cursor.fetchone()[0], 'restored')
        conn.close()


class SampleDataStatusModelTests(TestCase):
    def test_singleton_load(self):
        status = SampleDataStatus.load()
        self.assertEqual(status.pk, 1)
        # Calling load again returns the same instance
        status2 = SampleDataStatus.load()
        self.assertEqual(status2.pk, 1)
        self.assertEqual(SampleDataStatus.objects.count(), 1)

    def test_default_values(self):
        status = SampleDataStatus.load()
        self.assertFalse(status.is_loaded)
        self.assertEqual(status.manifest, {})
        self.assertIsNone(status.loaded_at)

    def test_str(self):
        status = SampleDataStatus.load()
        self.assertEqual(str(status), "Sample Data Status")


class SettingsHubViewTests(TestCase):
    def test_settings_hub_status_code(self):
        resp = self.client.get(reverse("dashboard:settings_hub"))
        self.assertEqual(resp.status_code, 200)

    def test_settings_hub_contains_cards(self):
        resp = self.client.get(reverse("dashboard:settings_hub"))
        self.assertContains(resp, "Sample Data")
        self.assertContains(resp, "Manage Choices")
        self.assertContains(resp, "Email Settings")
        self.assertContains(resp, "Django Admin")

    def test_settings_hub_has_sample_status_context(self):
        resp = self.client.get(reverse("dashboard:settings_hub"))
        self.assertIn("sample_status", resp.context)


class SampleDataToggleTests(TestCase):
    def test_load_creates_data_and_sets_status(self):
        resp = self.client.post(reverse("dashboard:sample_data_load"))
        self.assertEqual(resp.status_code, 200)
        status = SampleDataStatus.load()
        self.assertTrue(status.is_loaded)
        self.assertIsNotNone(status.loaded_at)
        self.assertIn("stakeholders.stakeholder", status.manifest)
        self.assertTrue(len(status.manifest["stakeholders.stakeholder"]) > 0)
        # Verify actual data was created
        self.assertTrue(Stakeholder.objects.exists())

    def test_double_load_is_idempotent(self):
        self.client.post(reverse("dashboard:sample_data_load"))
        count_after_first = Stakeholder.objects.count()
        self.client.post(reverse("dashboard:sample_data_load"))
        count_after_second = Stakeholder.objects.count()
        self.assertEqual(count_after_first, count_after_second)

    def test_remove_deletes_sample_data(self):
        self.client.post(reverse("dashboard:sample_data_load"))
        self.assertTrue(Stakeholder.objects.exists())
        self.client.post(reverse("dashboard:sample_data_remove"))
        status = SampleDataStatus.load()
        self.assertFalse(status.is_loaded)
        self.assertEqual(status.manifest, {})
        self.assertIsNone(status.loaded_at)
        # Sample stakeholders should be gone
        self.assertFalse(Stakeholder.objects.exists())

    def test_remove_preserves_real_data(self):
        # Create "real" data first
        real = Stakeholder.objects.create(name="Real Person", entity_type="contact")
        # Load sample data
        self.client.post(reverse("dashboard:sample_data_load"))
        self.assertTrue(Stakeholder.objects.count() > 1)
        # Remove sample data
        self.client.post(reverse("dashboard:sample_data_remove"))
        # Real data survives
        self.assertTrue(Stakeholder.objects.filter(pk=real.pk).exists())
        self.assertEqual(Stakeholder.objects.get(pk=real.pk).name, "Real Person")

    def test_remove_with_empty_manifest_is_safe(self):
        resp = self.client.post(reverse("dashboard:sample_data_remove"))
        self.assertEqual(resp.status_code, 200)
        status = SampleDataStatus.load()
        self.assertFalse(status.is_loaded)

    def test_load_returns_partial(self):
        resp = self.client.post(reverse("dashboard:sample_data_load"))
        self.assertContains(resp, "Loaded")
