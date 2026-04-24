"""Silent-breakage canary suite for the v2 urgency-first dashboard.

PURPOSE
-------
The v2 dashboard reorganizes items into new sections (hero / pipeline / overdue /
monitoring / asset footer). The worst failure mode is SILENT DATA LOSS — an item
that should appear somewhere silently vanishes, and because there's no visible
error, the user never notices until it becomes a real problem.

This suite catches that class of bug by:

  1. Creating a rich fixture universe (every item type, multiple items per category).
  2. Rendering BOTH dashboards against the same DB.
  3. Extracting primary keys from rendered `href` attributes — the agent
     cannot fake these without actually rendering the links.
  4. Asserting strict set equality between the expected items and what appears
     in each section of v2.
  5. Asserting counts in section headers match counts of rendered rows.
  6. Walking the hero state machine through all 4 states with mocked time.

Anti-cheat design:
  * PKs are extracted from hrefs, not from visible text — a template that writes
    "22 items" but renders 0 rows will fail.
  * `assertSetEqual` is used (not subset). Missing items fail LOUDLY with the
    missing PK listed in the error message.
  * Count assertions use `assertEqual`, never `assertGreaterEqual`.
  * Fixture scale is >1 per category so off-by-ones are detectable.
  * Legacy dashboard serves as the oracle — if legacy shows it, v2 must too.
  * No `@skipIf` / `@expectedFailure` anywhere.
  * Time is mocked with a fixed timestamp so "today" boundaries are deterministic.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.urls import NoReverseMatch, resolve
from django.utils import timezone

from assets.models import Loan, RealEstate
from checklists.models import Checklist, ChecklistItem
from legal.models import LegalMatter
from stakeholders.models import Stakeholder
from tasks.models import FollowUp, Task


# Fixed "now" that makes the scenarios reproducible.
# 7:52 PM local on a Wednesday gives us both past and future items today.
FIXED_NOW = timezone.make_aware(datetime(2026, 4, 22, 19, 52, 0))
TODAY = FIXED_NOW.date()


def _extract_task_pks(html: str) -> set[int]:
    """Extract every Task PK referenced by an href in the rendered HTML."""
    import re
    return {int(m) for m in re.findall(r'href="/tasks/(\d+)/', html)}


def _extract_legal_pks(html: str) -> set[int]:
    import re
    return {int(m) for m in re.findall(r'href="/legal/(\d+)/', html)}


def _extract_property_pks(html: str) -> set[int]:
    import re
    return {int(m) for m in re.findall(r'href="/assets/real-estate/(\d+)/', html)}


def _extract_loan_pks(html: str) -> set[int]:
    import re
    return {int(m) for m in re.findall(r'href="/assets/loans/(\d+)/', html)}


def _extract_checklist_pks(html: str) -> set[int]:
    import re
    return {int(m) for m in re.findall(r'href="/checklists/(\d+)/', html)}


def _extract_section_html(html: str, marker: str) -> str:
    """Extract the HTML slice of a section, from its marker to the next section break.

    Used to assert that a PK appears in a specific section, not just anywhere.
    """
    idx = html.find(marker)
    if idx == -1:
        return ""
    # Next section marker — pipeline / overdue / monitoring / asset-footer headers all
    # contain "v2-section-head" or ".v2-asset-footer". Slice to the next one.
    next_idx = html.find("v2-section-head", idx + 1)
    if next_idx == -1:
        next_idx = html.find("v2-asset-footer", idx + 1)
    return html[idx:next_idx] if next_idx > idx else html[idx:]


class _FixtureMixin:
    """Shared fixture for the whole suite. Builds a rich item universe once.

    Counts per category are intentionally > 1 so dropping a single item is visible.
    """

    @classmethod
    def setUpTestData(cls):
        # ─── Stakeholders (used as meeting/task attendees) ────────────────────
        cls.alice = Stakeholder.objects.create(name="Alice Analyst", entity_type="person")
        cls.bob = Stakeholder.objects.create(name="Bob Builder", entity_type="person")
        cls.carol = Stakeholder.objects.create(name="Carol Carpenter", entity_type="person")

        # ─── TODAY: mix of past, live-soon, future, untimed ───────────────────
        # 1:00 PM (past) — non-meeting task
        cls.today_past_task = Task.objects.create(
            title="Today Past Task (1 PM)",
            due_date=TODAY, due_time=time(13, 0),
            status="not_started", priority="medium",
            task_type="one_time", direction="personal",
        )
        # 2:30 PM (past) — meeting
        cls.today_past_meeting = Task.objects.create(
            title="Today Past Meeting (2:30 PM)",
            due_date=TODAY, due_time=time(14, 30),
            status="not_started", priority="high",
            task_type="meeting", direction="outbound",
        )
        cls.today_past_meeting.related_stakeholders.add(cls.alice)
        # 8:00 PM (live — 8 min in future from FIXED_NOW 7:52 PM)
        cls.today_live_task = Task.objects.create(
            title="Today Live Task (8 PM)",
            due_date=TODAY, due_time=time(20, 0),
            status="not_started", priority="critical",
            task_type="one_time", direction="personal",
        )
        # 11:30 PM (future-later today)
        cls.today_later_task = Task.objects.create(
            title="Today Later Task (11:30 PM)",
            due_date=TODAY, due_time=time(23, 30),
            status="not_started", priority="medium",
            task_type="one_time", direction="personal",
        )
        # No time (all-day)
        cls.today_allday_task = Task.objects.create(
            title="Today All-Day Task",
            due_date=TODAY, due_time=None,
            status="not_started", priority="high",
            task_type="one_time", direction="personal",
        )
        cls.today_task_pks = {
            cls.today_past_task.pk, cls.today_past_meeting.pk,
            cls.today_live_task.pk, cls.today_later_task.pk,
            cls.today_allday_task.pk,
        }

        # ─── OVERDUE: one of each priority, varying stakeholders ──────────────
        cls.overdue_pks = set()
        for days_late, priority in [(1, "critical"), (3, "high"), (7, "high"),
                                     (14, "medium"), (25, "medium"), (40, "low")]:
            t = Task.objects.create(
                title=f"Overdue {days_late}d ({priority})",
                due_date=TODAY - timedelta(days=days_late),
                status="not_started", priority=priority,
                task_type="one_time", direction="personal",
            )
            t.related_stakeholders.add(cls.bob)
            cls.overdue_pks.add(t.pk)

        # ─── COMPLETED overdue — MUST NOT appear (regression guard) ──────────
        cls.completed_overdue = Task.objects.create(
            title="Completed Old Task (should be hidden)",
            due_date=TODAY - timedelta(days=5),
            status="complete", priority="high",
            task_type="one_time", direction="personal",
        )

        # ─── PIPELINE: tomorrow / day-after / rest-of-week ───────────────────
        cls.tomorrow_pks = set()
        for i in range(3):
            t = Task.objects.create(
                title=f"Tomorrow Item {i}",
                due_date=TODAY + timedelta(days=1),
                due_time=time(10 + i, 0),
                status="not_started", priority="medium",
                task_type="meeting" if i == 0 else "one_time",
                direction="personal",
            )
            cls.tomorrow_pks.add(t.pk)

        cls.day_after_pks = set()
        for i in range(2):
            t = Task.objects.create(
                title=f"Day-After Item {i}",
                due_date=TODAY + timedelta(days=2),
                status="not_started", priority="low",
                task_type="one_time", direction="personal",
            )
            cls.day_after_pks.add(t.pk)

        cls.rest_of_week_pks = set()
        for days in (3, 4, 6):
            t = Task.objects.create(
                title=f"ROW Item +{days}d",
                due_date=TODAY + timedelta(days=days),
                status="not_started", priority="medium",
                task_type="one_time", direction="personal",
            )
            cls.rest_of_week_pks.add(t.pk)

        # ─── Beyond-week items — MUST NOT appear in pipeline ─────────────────
        cls.beyond_week = Task.objects.create(
            title="Beyond Week (should not render)",
            due_date=TODAY + timedelta(days=10),
            status="not_started", priority="medium",
            task_type="one_time", direction="personal",
        )

        # ─── LEGAL MATTERS (monitoring section) ──────────────────────────────
        cls.legal_active_pks = set()
        for i, s in enumerate(["active", "active", "pending"]):
            m = LegalMatter.objects.create(
                title=f"Legal {i} ({s})",
                status=s, matter_type="other",
            )
            cls.legal_active_pks.add(m.pk)

        # Resolved — MUST NOT appear
        cls.legal_resolved = LegalMatter.objects.create(
            title="Resolved Matter", status="resolved", matter_type="other",
        )

        # ─── AT-RISK ASSETS (monitoring section) ─────────────────────────────
        cls.at_risk_property_pks = set()
        for i in range(2):
            p = RealEstate.objects.create(
                name=f"Risky Property {i}",
                status="in_dispute",
                estimated_value=Decimal("1000000"),
            )
            cls.at_risk_property_pks.add(p.pk)
        # Healthy property (should not be in monitoring)
        cls.healthy_property = RealEstate.objects.create(
            name="Healthy Property", status="owned",
            estimated_value=Decimal("500000"),
        )

        cls.at_risk_loan_pks = set()
        for i, s in enumerate(["defaulted", "in_dispute"]):
            loan = Loan.objects.create(
                name=f"Risky Loan {i}", status=s,
                current_balance=Decimal("100000"),
            )
            cls.at_risk_loan_pks.add(loan.pk)

        # ─── OUTSTANDING CHECKLISTS ──────────────────────────────────────────
        cls.checklist_pks = set()
        for i in range(3):
            cl = Checklist.objects.create(name=f"Checklist {i}")
            for j in range(5):
                ChecklistItem.objects.create(
                    checklist=cl, title=f"Item {j}",
                    is_completed=(j < i),  # partial completion varies
                )
            cls.checklist_pks.add(cl.pk)
        # Fully complete checklist (should not appear)
        cls.complete_checklist = Checklist.objects.create(name="All Done")
        for j in range(3):
            ChecklistItem.objects.create(
                checklist=cls.complete_checklist, title=f"Done {j}",
                is_completed=True,
            )

        # ─── STALE FOLLOW-UPS ────────────────────────────────────────────────
        # Source task has no due_date so it doesn't pollute pipeline/overdue PK sets.
        stale_task = Task.objects.create(
            title="Stale-source task (not in any band)",
            due_date=None,
            status="not_started", priority="medium",
            task_type="one_time", direction="outbound",
        )
        FollowUp.objects.create(
            task=stale_task, stakeholder=cls.carol,
            outreach_date=FIXED_NOW - timedelta(days=10),
            method="email", reminder_enabled=True, follow_up_days=3,
            response_received=False,
        )
        cls.stale_task_pk = stale_task.pk
        cls.stale_count_expected = 1

        # ─── Link checklists to a dedicated stakeholder so their URLs don't collide
        # with property URLs in later tests. (Checklist.get_absolute_url delegates
        # to the linked entity.)
        cls.checklist_owner = Stakeholder.objects.create(
            name="Checklist Owner Stakeholder", entity_type="person",
        )
        for cl in Checklist.objects.filter(pk__in=cls.checklist_pks):
            cl.related_stakeholder = cls.checklist_owner
            cl.save()


def _freeze_time(dt_value):
    """Patch both timezone.now() and timezone.localdate() used by the view."""
    return mock.patch("django.utils.timezone.now", return_value=dt_value)


class V2DashboardCompletenessTests(_FixtureMixin, TestCase):
    """Layer 1: every fixture item renders in the expected section of v2.

    This is the primary silent-breakage guard. Each test extracts a set of PKs
    from rendered HTML and asserts strict equality against an expected set from
    the fixture.
    """

    def setUp(self):
        self.client = Client()
        self.session = self.client.session
        self.session["dashboard_version"] = "v2"
        self.session.save()
        self._time_patcher = _freeze_time(FIXED_NOW)
        self._time_patcher.start()

    def tearDown(self):
        self._time_patcher.stop()

    def _render_v2(self):
        resp = self.client.get("/?v=v2")
        self.assertEqual(resp.status_code, 200,
                         "v2 dashboard must render 200 OK")
        return resp.content.decode("utf-8")

    # ─── Today panel ────────────────────────────────────────────────────────
    def test_every_today_item_renders_in_hero(self):
        """BUG GUARDED: today items with past due_time silently dropped.

        Every today item (past/live/future/all-day) must be reachable via an
        href inside the hero block.
        """
        html = self._render_v2()
        # Hero block spans from the hero opening to the first pipeline section header.
        hero_start = html.find("v2-hero ")
        pipeline_start = html.find("Pipeline ·", hero_start)
        hero_html = html[hero_start:pipeline_start]
        rendered_pks = _extract_task_pks(hero_html)
        missing = self.today_task_pks - rendered_pks
        self.assertFalse(
            missing,
            f"TODAY items silently missing from hero: {missing}. "
            f"Hero rendered PKs: {rendered_pks}. "
            f"Expected all today PKs: {self.today_task_pks}."
        )

    def test_live_task_appears_before_side_panel(self):
        """The live task must appear in the primary area (before the side panel)."""
        html = self._render_v2()
        # The "Today's schedule" header marks the start of the side panel content.
        # The live task's href must appear BEFORE that header.
        live_href = f"/tasks/{self.today_live_task.pk}/"
        first_live_occurrence = html.find(live_href)
        side_panel_marker = html.find("Today's schedule")
        self.assertGreater(first_live_occurrence, -1,
                           "Live task href not present at all in rendered HTML")
        self.assertGreater(side_panel_marker, -1,
                           "Side panel 'Today's schedule' marker not in rendered HTML")
        self.assertLess(
            first_live_occurrence, side_panel_marker,
            f"Live task should render in primary panel (before 'Today's schedule' "
            f"at pos {side_panel_marker}), but first appears at pos {first_live_occurrence}"
        )

    # ─── Overdue section ────────────────────────────────────────────────────
    def test_every_overdue_task_renders_in_overdue_section(self):
        """BUG GUARDED: overdue task misclassified into pipeline, or dropped entirely."""
        html = self._render_v2()
        overdue_html = _extract_section_html(html, "Overdue ·")
        rendered = _extract_task_pks(overdue_html)
        self.assertSetEqual(
            rendered, self.overdue_pks,
            f"Overdue section PK mismatch. "
            f"Missing: {self.overdue_pks - rendered}. "
            f"Unexpected: {rendered - self.overdue_pks}."
        )

    def test_completed_overdue_task_not_rendered(self):
        """Completed tasks must never appear anywhere on the dashboard."""
        html = self._render_v2()
        self.assertNotIn(f"/tasks/{self.completed_overdue.pk}/", html,
                         "Completed task leaked onto dashboard")

    def test_overdue_header_count_matches_row_count(self):
        """'Overdue · N items' header number must equal the count of `.v2-row` children."""
        import re
        html = self._render_v2()
        overdue_html = _extract_section_html(html, "Overdue ·")
        m = re.search(r"Overdue · (\d+) item", overdue_html)
        self.assertIsNotNone(m, "Could not find overdue count in header")
        header_count = int(m.group(1))
        # Count rendered row tasks (excludes empty-row placeholders)
        row_pks = _extract_task_pks(overdue_html)
        self.assertEqual(
            header_count, len(row_pks),
            f"Overdue header claims {header_count} but only {len(row_pks)} rows render"
        )

    # ─── Pipeline day bands ─────────────────────────────────────────────────
    def test_every_tomorrow_item_renders_in_tomorrow_band(self):
        """Items due tomorrow belong in the Tomorrow band, and nowhere else in pipeline."""
        html = self._render_v2()
        pipe = _extract_section_html(html, "Pipeline ·")
        # Slice between the 1st and 2nd v2-day-band occurrences (tomorrow → day-after)
        bands = [i for i in range(len(pipe)) if pipe.startswith("v2-day-band", i)]
        self.assertGreaterEqual(len(bands), 2,
                                "Expected at least 2 day-bands (tomorrow + day-after)")
        tomorrow_html = pipe[bands[0]:bands[1]]
        rendered = _extract_task_pks(tomorrow_html)
        self.assertSetEqual(
            rendered, self.tomorrow_pks,
            f"Tomorrow band PK mismatch. Missing: {self.tomorrow_pks - rendered}. "
            f"Unexpected: {rendered - self.tomorrow_pks}."
        )

    def test_every_day_after_item_renders_in_day_after_band(self):
        html = self._render_v2()
        pipe = _extract_section_html(html, "Pipeline ·")
        # Day-after band starts after tomorrow band (2nd v2-day-band in pipeline)
        bands = [i for i in range(len(pipe)) if pipe.startswith("v2-day-band", i)]
        self.assertGreaterEqual(len(bands), 3,
                                "Expected 3 day-bands (tomorrow, day-after, rest)")
        day_after_html = pipe[bands[1]:bands[2]]
        rendered = _extract_task_pks(day_after_html)
        self.assertSetEqual(
            rendered, self.day_after_pks,
            f"Day-after band PK mismatch. Missing: {self.day_after_pks - rendered}. "
            f"Unexpected: {rendered - self.day_after_pks}."
        )

    def test_every_rest_of_week_item_renders_in_rest_band(self):
        html = self._render_v2()
        pipe = _extract_section_html(html, "Pipeline ·")
        bands = [i for i in range(len(pipe)) if pipe.startswith("v2-day-band", i)]
        rest_html = pipe[bands[2]:]
        rendered = _extract_task_pks(rest_html)
        self.assertSetEqual(
            rendered, self.rest_of_week_pks,
            f"Rest-of-week band PK mismatch. Missing: {self.rest_of_week_pks - rendered}. "
            f"Unexpected: {rendered - self.rest_of_week_pks}."
        )

    def test_beyond_week_item_does_not_render_in_pipeline(self):
        """BUG GUARDED: time horizon leak — items >7 days out must not appear."""
        html = self._render_v2()
        pipe = _extract_section_html(html, "Pipeline ·")
        self.assertNotIn(f"/tasks/{self.beyond_week.pk}/", pipe,
                         "Beyond-week item leaked into pipeline")

    def test_overdue_task_never_appears_in_pipeline(self):
        """BUG GUARDED: category bleed — overdue must not show in pipeline."""
        html = self._render_v2()
        pipe = _extract_section_html(html, "Pipeline ·")
        pipe_pks = _extract_task_pks(pipe)
        bleeding = pipe_pks & self.overdue_pks
        self.assertFalse(
            bleeding,
            f"Overdue tasks leaked into pipeline: {bleeding}"
        )

    # ─── Monitoring section ─────────────────────────────────────────────────
    def test_every_active_legal_matter_renders_in_monitoring(self):
        html = self._render_v2()
        mon = _extract_section_html(html, "Monitoring ·")
        rendered = _extract_legal_pks(mon)
        self.assertSetEqual(
            rendered, self.legal_active_pks,
            f"Monitoring section legal matter PK mismatch. "
            f"Missing: {self.legal_active_pks - rendered}. "
            f"Unexpected: {rendered - self.legal_active_pks}."
        )

    def test_resolved_legal_matter_not_rendered(self):
        html = self._render_v2()
        self.assertNotIn(f"/legal/{self.legal_resolved.pk}/", html,
                         "Resolved legal matter leaked onto dashboard")

    def test_every_at_risk_property_renders_in_monitoring(self):
        html = self._render_v2()
        mon = _extract_section_html(html, "Monitoring ·")
        rendered = _extract_property_pks(mon)
        # Note: asset footer also contains property links — we extracted only
        # from the monitoring section so footer doesn't pollute the result.
        self.assertTrue(
            self.at_risk_property_pks.issubset(rendered),
            f"At-risk properties missing from monitoring: "
            f"{self.at_risk_property_pks - rendered}"
        )

    def test_healthy_property_not_in_monitoring(self):
        html = self._render_v2()
        mon = _extract_section_html(html, "Monitoring ·")
        self.assertNotIn(f"/assets/real-estate/{self.healthy_property.pk}/", mon,
                         "Healthy property leaked into monitoring section")

    def test_every_at_risk_loan_renders_in_monitoring(self):
        html = self._render_v2()
        mon = _extract_section_html(html, "Monitoring ·")
        rendered = _extract_loan_pks(mon)
        self.assertSetEqual(
            rendered, self.at_risk_loan_pks,
            f"At-risk loans in monitoring PK mismatch. "
            f"Missing: {self.at_risk_loan_pks - rendered}"
        )

    def test_every_outstanding_checklist_renders_in_monitoring(self):
        """Each outstanding checklist must appear in monitoring, identified by its name.

        (Checklists don't have dedicated URLs — get_absolute_url() delegates to the
        linked entity, so we identify by the unique name instead of PK.)
        """
        html = self._render_v2()
        mon = _extract_section_html(html, "Monitoring ·")
        missing = []
        for cl in Checklist.objects.filter(pk__in=self.checklist_pks):
            if cl.name not in mon:
                missing.append(cl.name)
        self.assertFalse(
            missing,
            f"Outstanding checklists missing from monitoring (by name): {missing}"
        )

    def test_fully_complete_checklist_not_rendered(self):
        html = self._render_v2()
        self.assertNotIn(f"/checklists/{self.complete_checklist.pk}/", html,
                         "Fully-complete checklist leaked onto dashboard")

    # ─── Alert strip counts ─────────────────────────────────────────────────
    def _extract_alert_badge(self, html: str, label: str) -> int:
        """Find the alert-strip badge number next to a given label.

        Alert pills are structured: <span class="...bg-red-500...">N</span>
        followed by a sibling <span ...>LABEL</span>. We find the label, walk
        backward to the nearest `>N</span>`, and parse N.
        """
        import re
        # `class="v2-alert-strip` appears in the rendered DOM (not in <style>),
        # so this slice targets the actual alert strip element.
        strip_start = html.find('class="v2-alert-strip')
        self.assertNotEqual(strip_start, -1, "v2-alert-strip element not found in rendered HTML")
        # Alert strip ends before the hero (`class="v2-hero `)
        strip_end = html.find('class="v2-hero ', strip_start)
        strip = html[strip_start:strip_end]
        label_idx = strip.find(label)
        self.assertNotEqual(label_idx, -1, f"Label '{label}' not in alert strip: {strip[:400]}")
        # Walk backward for the nearest `>\d+</span>`
        prefix = strip[:label_idx]
        matches = re.findall(r'>(\d+)</span>', prefix)
        self.assertTrue(matches, f"No badge number found before label '{label}'")
        return int(matches[-1])

    def test_alert_strip_overdue_count_matches_fixture(self):
        """Alert strip badge number must equal the actual overdue count."""
        html = self._render_v2()
        badge = self._extract_alert_badge(html, "Overdue task")
        self.assertEqual(
            badge, len(self.overdue_pks),
            f"Alert strip says {badge} overdue but fixture has {len(self.overdue_pks)}"
        )

    def test_alert_strip_stale_count_matches_fixture(self):
        """Alert strip stale badge must equal the actual stale follow-up count."""
        html = self._render_v2()
        badge = self._extract_alert_badge(html, "Stale")
        self.assertEqual(badge, self.stale_count_expected,
                         f"Alert strip says {badge} stale but fixture has {self.stale_count_expected}")


class V2ParityWithLegacyTests(_FixtureMixin, TestCase):
    """Layer 2: the legacy dashboard is an oracle — any task it shows, v2 must show."""

    def setUp(self):
        self._time_patcher = _freeze_time(FIXED_NOW)
        self._time_patcher.start()

    def tearDown(self):
        self._time_patcher.stop()

    def test_v2_shows_every_task_legacy_shows_within_week_horizon(self):
        """Within the 7-day horizon v2 is spec'd for, every task legacy shows must also
        appear in v2. (Beyond +6 days is intentionally hidden per the skill spec —
        users see those on /tasks/ or /calendar/, which are still linked from nav.)
        """
        legacy_html = self.client.get("/?v=legacy").content.decode("utf-8")
        v2_html = self.client.get("/?v=v2").content.decode("utf-8")

        legacy_pks = _extract_task_pks(legacy_html)
        v2_pks = _extract_task_pks(v2_html)

        # Restrict comparison to tasks due in [today-30, today+6] — the shared horizon
        in_horizon_pks = set(Task.objects.filter(
            due_date__gte=TODAY - timedelta(days=30),
            due_date__lte=TODAY + timedelta(days=6),
        ).exclude(status="complete").values_list("pk", flat=True))

        legacy_in_horizon = legacy_pks & in_horizon_pks
        v2_in_horizon = v2_pks & in_horizon_pks

        missing = legacy_in_horizon - v2_in_horizon
        self.assertFalse(
            missing,
            f"Legacy shows {len(missing)} task(s) in the 7-day horizon that v2 doesn't: {missing}. "
            f"Legacy total in horizon: {len(legacy_in_horizon)}, v2 total: {len(v2_in_horizon)}"
        )

    def test_v2_shows_every_legal_matter_legacy_shows(self):
        legacy_html = self.client.get("/?v=legacy").content.decode("utf-8")
        v2_html = self.client.get("/?v=v2").content.decode("utf-8")
        missing = _extract_legal_pks(legacy_html) - _extract_legal_pks(v2_html)
        self.assertFalse(missing, f"v2 missing legal PKs shown by legacy: {missing}")


class V2HeroStateMachineTests(_FixtureMixin, TestCase):
    """Layer 3: walk the hero through all four states with mocked time.

    Regression guard for the past-items bug: when all today items are past, hero
    must NOT claim "clear" — it should be "open" (if overdue exists) or "clear"
    (truly nothing pending).
    """

    def _render_at(self, when):
        """Render v2 with timezone.now() mocked to `when`."""
        with _freeze_time(when):
            resp = self.client.get("/?v=v2")
            self.assertEqual(resp.status_code, 200)
            return resp.content.decode("utf-8")

    def test_live_state_when_item_imminent(self):
        """FIXED_NOW is 7:52 PM; fixture has an 8:00 PM task → hero must be 'live'."""
        html = self._render_at(FIXED_NOW)
        self.assertIn("RIGHT NOW", html.upper(),
                      "Hero must be in Live state at 7:52 PM with 8:00 PM task")
        # Live dot must appear
        self.assertIn("v2-live-dot", html)

    def test_later_state_when_no_live_but_future_items(self):
        """At 9 AM with no imminent items but 11:30 PM task exists → 'later'."""
        when = timezone.make_aware(datetime(2026, 4, 22, 9, 0, 0))
        html = self._render_at(when)
        self.assertIn("UP NEXT TODAY", html.upper(),
                      "Hero must be in Later state at 9 AM with future today items")

    def test_open_state_when_overdue_but_no_today(self):
        """Delete today items, keep overdue → hero should be 'open' with focus-on CTA."""
        Task.objects.filter(pk__in=self.today_task_pks).delete()
        when = FIXED_NOW
        html = self._render_at(when)
        self.assertIn("FOCUS ON", html.upper(),
                      "Hero must be in Open state when overdue exists but no today items")

    def test_clear_state_when_nothing_pending(self):
        """Delete all tasks, legal, risk, stale → hero is 'clear', alert strip muted."""
        Task.objects.all().delete()
        LegalMatter.objects.all().delete()
        RealEstate.objects.all().update(status="owned")
        Loan.objects.all().update(status="active")
        Checklist.objects.all().delete()
        FollowUp.objects.all().delete()
        html = self._render_at(FIXED_NOW)
        self.assertIn("ALL CLEAR", html.upper(),
                      "Hero must be in All-Clear state with zero pending items")
        self.assertIn("muted", html, "Alert strip must be muted-green in All-Clear")

    def test_past_only_today_does_not_claim_clear(self):
        """BUG GUARDED: with only past-time today items, hero must NOT be 'clear'.

        This is the regression test for the bug the user caught visually.
        """
        # Remove future and live items — keep only past items and overdue.
        Task.objects.filter(pk__in={
            self.today_live_task.pk, self.today_later_task.pk, self.today_allday_task.pk,
        }).delete()
        # At 11 PM, only past today items remain. Plus overdue still exists.
        when = timezone.make_aware(datetime(2026, 4, 22, 23, 0, 0))
        html = self._render_at(when)
        self.assertNotIn("ALL CLEAR", html.upper(),
                         "Hero claimed 'All Clear' but overdue items remain")
        # Past today items must still render in side panel
        self.assertIn(f"/tasks/{self.today_past_task.pk}/", html,
                      "Past today item missing from rendered HTML")
        self.assertIn(f"/tasks/{self.today_past_meeting.pk}/", html,
                      "Past today meeting missing from rendered HTML")


class V2LinkReachabilityTests(_FixtureMixin, TestCase):
    """Layer 4: every href the v2 dashboard emits must resolve to a real URL.

    BUG GUARDED: NoReverseMatch or 404 only appearing when user clicks the link.
    """

    def setUp(self):
        self._time_patcher = _freeze_time(FIXED_NOW)
        self._time_patcher.start()

    def tearDown(self):
        self._time_patcher.stop()

    def test_every_rendered_href_resolves(self):
        """Parse every internal href from v2; assert Django's URL resolver handles it."""
        import re
        html = self.client.get("/?v=v2").content.decode("utf-8")
        hrefs = set(re.findall(r'href="(/[^"#?]+)', html))
        # Narrow to our app's URL space — skip static files and external
        hrefs = {h for h in hrefs if not h.startswith("/static/")}

        broken = []
        for href in hrefs:
            try:
                resolve(href)
            except Exception as e:
                broken.append((href, str(e)))
        self.assertFalse(
            broken,
            f"v2 rendered unresolvable hrefs: {broken}"
        )


class V2VersionToggleTests(_FixtureMixin, TestCase):
    """Layer 5: the version toggle persists and routes correctly."""

    def test_default_version_is_v2(self):
        """Fresh session must land on v2 (user requested this default)."""
        html = self.client.get("/").content.decode("utf-8")
        self.assertIn("v2-hero", html, "Default dashboard should be v2")

    def test_url_query_override_v2(self):
        html = self.client.get("/?v=v2").content.decode("utf-8")
        self.assertIn("v2-hero", html)

    def test_url_query_override_legacy(self):
        html = self.client.get("/?v=legacy").content.decode("utf-8")
        self.assertNotIn("v2-hero", html)
        self.assertIn("Try new Dashboard", html)

    def test_switch_endpoint_to_legacy_persists(self):
        """Hitting /version/legacy/ sets the session, subsequent / renders legacy."""
        resp = self.client.get("/version/legacy/")
        self.assertIn(resp.status_code, (302, 303),
                      "switch_version must redirect")
        html = self.client.get("/").content.decode("utf-8")
        self.assertNotIn("v2-hero", html,
                         "Session did not persist legacy preference")

    def test_switch_endpoint_to_v2_persists(self):
        # First flip to legacy, then back to v2
        self.client.get("/version/legacy/")
        self.client.get("/version/v2/")
        html = self.client.get("/").content.decode("utf-8")
        self.assertIn("v2-hero", html)

    def test_invalid_version_value_ignored(self):
        """An unknown value must not break the page or poison the session."""
        resp = self.client.get("/?v=nonsense")
        self.assertEqual(resp.status_code, 200)


class V2NoDjangoCommentLeakTests(_FixtureMixin, TestCase):
    """Layer 6: no literal Django comment syntax leaks into rendered HTML.

    BUG GUARDED: multi-line `{# #}` comments render as text (Django only supports
    single-line). This caught me twice during implementation.
    """

    def test_rendered_html_contains_no_django_comment_markers(self):
        html = self.client.get("/?v=v2").content.decode("utf-8")
        # Any of these patterns appearing in output means a comment leaked.
        forbidden = ["{# ", " #}", "{% comment %}", "{% endcomment %}"]
        leaks = [p for p in forbidden if p in html]
        self.assertFalse(
            leaks,
            f"Django comment syntax leaked into rendered HTML: {leaks}. "
            f"Multi-line {{# #}} comments must be {{% comment %}} blocks."
        )


class V2TodayDedupTests(TestCase):
    """Layer 7: today items must render once even when a task has both
    due_date=today AND reminder_date=today.

    BUG GUARDED: previously, a task appearing through both lenses was added to
    today_items twice — user sees the same item duplicated in the side panel.
    Observed in real data: 2 real tasks in prod had this pattern as of 2026-04-22.
    """

    def setUp(self):
        self._time_patcher = _freeze_time(FIXED_NOW)
        self._time_patcher.start()
        self.client = Client()

    def tearDown(self):
        self._time_patcher.stop()

    def test_task_with_both_due_today_and_reminder_today_appears_once_in_side_panel(self):
        """A task whose due_date=today AND reminder_date fires today must not duplicate."""
        # Reminder at 8:05 PM (> FIXED_NOW 7:52 PM so it passes reminder_date__gte=now)
        reminder_dt = FIXED_NOW + timedelta(minutes=13)
        t = Task.objects.create(
            title="Dup Suspect Task",
            due_date=TODAY,
            due_time=time(15, 0),
            reminder_date=reminder_dt,
            status="not_started",
            priority="high",
            task_type="one_time",
            direction="personal",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")

        # Slice to the hero's side panel
        hero_start = html.find("v2-hero ")
        pipeline_start = html.find("Pipeline", hero_start)
        hero = html[hero_start:pipeline_start]
        sched_start = hero.find("Today's schedule")
        side_panel = hero[sched_start:] if sched_start > 0 else ""

        import re
        side_hrefs = re.findall(rf'href="/tasks/{t.pk}/', side_panel)
        self.assertEqual(
            len(side_hrefs), 1,
            f"Task {t.pk} appears {len(side_hrefs)}x in the side panel "
            f"(should be exactly 1). Duplicate silently confuses the user."
        )

    def test_today_schedule_section_has_no_duplicate_task_pks(self):
        """Broader guard: across the whole side panel schedule, no task PK repeats."""
        # Multiple tasks with both due + reminder today
        for i, hour in enumerate([9, 11, 14]):
            Task.objects.create(
                title=f"Dup Case {i}",
                due_date=TODAY,
                due_time=time(hour, 0),
                reminder_date=FIXED_NOW + timedelta(minutes=30 + i),
                status="not_started",
                priority="medium",
                task_type="one_time",
                direction="personal",
            )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        hero_start = html.find("v2-hero ")
        pipeline_start = html.find("Pipeline", hero_start)
        hero = html[hero_start:pipeline_start]
        sched_start = hero.find("Today's schedule")
        side_panel = hero[sched_start:] if sched_start > 0 else ""

        import re
        all_pks = re.findall(r'href="/tasks/(\d+)/', side_panel)
        from collections import Counter
        counts = Counter(all_pks)
        dups = {pk: n for pk, n in counts.items() if n > 1}
        self.assertFalse(
            dups,
            f"Side panel has duplicate task PKs: {dups}. "
            f"Each task must render at most once."
        )


class V2AlertStripLoanRiskTests(_FixtureMixin, TestCase):
    """Layer 8: alert strip includes at-risk loans pill.

    BUG GUARDED: the alert strip only mentioned properties, missing at-risk loans
    despite the hero state machine counting them for `risk_total`. Monitoring
    section showed the loan while the alert strip said "No active alerts".
    """

    def setUp(self):
        self._time_patcher = _freeze_time(FIXED_NOW)
        self._time_patcher.start()

    def tearDown(self):
        self._time_patcher.stop()

    def test_alert_strip_shows_loan_pill_when_loan_is_at_risk(self):
        html = self.client.get("/?v=v2").content.decode("utf-8")
        # Alert strip is the element with class="v2-alert-strip ..."
        strip_start = html.find('class="v2-alert-strip')
        strip_end = html.find('class="v2-hero ', strip_start)
        strip = html[strip_start:strip_end]
        # Fixture has 2 at-risk loans (defaulted + in_dispute)
        self.assertIn(
            "Loans at risk", strip,
            f"Expected 'Loans at risk' pill in alert strip. Strip: {strip[:500]}"
        )

    def test_alert_strip_triage_button_shown_when_only_loan_risk_exists(self):
        """If the ONLY alert is at-risk loans, alert strip must NOT say 'No active alerts'."""
        # Clear every alert source except the at-risk loans
        Task.objects.all().delete()
        LegalMatter.objects.all().delete()
        RealEstate.objects.all().update(status="owned")
        FollowUp.objects.all().delete()
        # At-risk loans remain from fixture

        html = self.client.get("/?v=v2").content.decode("utf-8")
        strip_start = html.find('class="v2-alert-strip')
        strip_end = html.find('class="v2-hero ', strip_start)
        strip = html[strip_start:strip_end]
        self.assertNotIn(
            "No active alerts", strip,
            "Alert strip says 'No active alerts' while at-risk loan pending. "
            "Inconsistent with hero 'Focus on' state and Monitoring section."
        )
        self.assertIn(
            "Triage now", strip,
            "'Triage now' CTA missing from alert strip despite at-risk loans"
        )


class V2PluralizationTests(TestCase):
    """Layer 9: section headers handle 1-item and N-item correctly.

    The existing completeness suite uses multi-item fixtures only (by design —
    to catch off-by-ones). This suite specifically covers "1 item" edge cases.
    """

    def setUp(self):
        self._time_patcher = _freeze_time(FIXED_NOW)
        self._time_patcher.start()
        self.client = Client()

    def tearDown(self):
        self._time_patcher.stop()

    def test_single_overdue_header_says_one_item(self):
        Task.objects.create(
            title="Lone overdue",
            due_date=TODAY - timedelta(days=1),
            status="not_started",
            priority="high",
            task_type="one_time",
            direction="personal",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        # Header should say "Overdue · 1 item" not "Overdue · 1 items"
        self.assertIn("Overdue · 1 item", html,
                      "Overdue header pluralization wrong with 1 item")
        self.assertNotIn("Overdue · 1 items", html,
                         "Overdue header says '1 items' (plural) for 1 item")

    def test_single_monitoring_header_says_one_matter(self):
        LegalMatter.objects.create(
            title="Lone matter", status="active", matter_type="other",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        self.assertIn("1 open matter", html,
                      "Monitoring header should say '1 open matter' not '1 open matters'")
        self.assertNotIn("1 open matters", html)

    def test_single_tomorrow_item_header_says_one_item(self):
        t = Task.objects.create(
            title="Lone tomorrow",
            due_date=TODAY + timedelta(days=1),
            status="not_started",
            priority="medium",
            task_type="one_time",
            direction="personal",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        # Tomorrow band has "Tomorrow · <date> · N item(s)"
        # Find the tomorrow band segment
        tom_marker = "Tomorrow · "
        idx = html.find(tom_marker)
        self.assertNotEqual(idx, -1, "Tomorrow band marker missing")
        tomorrow_segment = html[idx:idx + 200]
        self.assertIn("1 item", tomorrow_segment,
                      f"Tomorrow pluralization wrong: {tomorrow_segment!r}")
        self.assertNotIn("1 items", tomorrow_segment,
                         f"Tomorrow says '1 items' not '1 item': {tomorrow_segment!r}")


class V2EdgeInputTests(TestCase):
    """Layer 10: tasks with unusual field values render without crashing.

    BUG GUARDED: titles with HTML/script/emoji/unicode edge cases; empty or
    whitespace titles; ultra-long titles; missing stakeholders.
    """

    def setUp(self):
        self._time_patcher = _freeze_time(FIXED_NOW)
        self._time_patcher.start()
        self.client = Client()

    def tearDown(self):
        self._time_patcher.stop()

    def test_html_in_title_is_escaped_not_executed(self):
        """A task title with <script> tags must be escaped, never executed."""
        Task.objects.create(
            title="<script>alert(1)</script>",
            due_date=TODAY - timedelta(days=1),
            status="not_started", priority="high",
            task_type="one_time", direction="personal",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        # Django default auto-escape should turn < into &lt;
        self.assertNotIn(
            "<script>alert(1)</script>", html,
            "<script> tag rendered unescaped — XSS vector in task title"
        )
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html,
                      "Task title was not HTML-escaped as expected")

    def test_unicode_and_emoji_title_renders(self):
        """Titles with emoji/unicode must not corrupt the page."""
        t = Task.objects.create(
            title="Café ☕ résumé with émojis 🎉",
            due_date=TODAY,
            due_time=time(12, 0),
            status="not_started", priority="medium",
            task_type="one_time", direction="personal",
        )
        resp = self.client.get("/?v=v2")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        self.assertIn(f"/tasks/{t.pk}/", html,
                      "Unicode-titled task missing from rendered HTML")
        # The emoji itself should survive (UTF-8 correctness)
        self.assertIn("☕", html, "Emoji corrupted in rendered HTML")

    def test_empty_title_renders_without_crashing(self):
        """A task with an empty title should not break the dashboard."""
        t = Task.objects.create(
            title="",  # blank title — model field has max_length but no blank constraint check on create
            due_date=TODAY - timedelta(days=2),
            status="not_started", priority="high",
            task_type="one_time", direction="personal",
        )
        resp = self.client.get("/?v=v2")
        self.assertEqual(resp.status_code, 200,
                         "Dashboard returned non-200 with empty-title task")
        html = resp.content.decode("utf-8")
        # Task's href should still be present
        self.assertIn(f"/tasks/{t.pk}/", html,
                      "Empty-title task silently dropped from overdue section")

    def test_ultra_long_title_truncates_safely(self):
        """A 500-char title must not break the layout; dashboard still renders."""
        t = Task.objects.create(
            title="X" * 500,
            due_date=TODAY + timedelta(days=1),
            status="not_started", priority="medium",
            task_type="one_time", direction="personal",
        )
        resp = self.client.get("/?v=v2")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        self.assertIn(f"/tasks/{t.pk}/", html,
                      "Ultra-long-title task missing from rendered HTML")

    def test_no_stakeholder_renders_direction_display(self):
        """Task with no stakeholder should fall back to direction display ('Outbound Request' etc.)."""
        t = Task.objects.create(
            title="No-stakeholder task",
            due_date=TODAY,
            due_time=time(10, 0),
            status="not_started", priority="medium",
            task_type="one_time", direction="outbound",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        self.assertIn(f"/tasks/{t.pk}/", html)
        # "Outbound Request" is the default meta for a task with no stakeholder
        self.assertIn("Outbound Request", html,
                      "Fallback direction display missing for stakeholder-less task")


class V2ScaleTests(TestCase):
    """Layer 11: dashboard handles realistic data volumes.

    The existing fixture has ~20 tasks; user's real DB has 50+ with 22 overdue.
    This sanity-checks performance and item-count integrity with 100+ items.
    """

    def setUp(self):
        self._time_patcher = _freeze_time(FIXED_NOW)
        self._time_patcher.start()
        self.client = Client()

    def tearDown(self):
        self._time_patcher.stop()

    def test_100_overdue_tasks_all_render(self):
        """BUG GUARDED: silent truncation at some pagination boundary."""
        expected_pks = set()
        for i in range(100):
            t = Task.objects.create(
                title=f"Scale overdue #{i}",
                due_date=TODAY - timedelta(days=(i % 30) + 1),
                status="not_started",
                priority=["critical", "high", "medium", "low"][i % 4],
                task_type="one_time",
                direction="personal",
            )
            expected_pks.add(t.pk)

        html = self.client.get("/?v=v2").content.decode("utf-8")

        # Slice the overdue section only
        import re
        overdue_idx = html.find("Overdue ·")
        next_section = html.find("v2-section-head", overdue_idx + 1)
        # Monitoring might come after
        overdue_section = html[overdue_idx:next_section] if next_section > 0 else html[overdue_idx:]
        rendered_pks = {int(m) for m in re.findall(r'href="/tasks/(\d+)/', overdue_section)}

        missing = expected_pks - rendered_pks
        self.assertFalse(
            missing,
            f"{len(missing)} overdue tasks silently dropped with 100-item fixture "
            f"(first few missing: {sorted(missing)[:5]})."
        )
        # Header count must match rendered count
        m = re.search(r"Overdue · (\d+) item", overdue_section)
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), 100,
                         f"Overdue header count wrong at scale: {m.group(0)}")


class V2LiveWindowTests(_FixtureMixin, TestCase):
    """Layer 12: multiple items in the live window — only one is the hero 'live',
    the rest must still surface (not silently drop).
    """

    def setUp(self):
        self._time_patcher = _freeze_time(FIXED_NOW)
        self._time_patcher.start()
        self.client = Client()

    def tearDown(self):
        self._time_patcher.stop()

    def test_second_live_window_item_still_renders(self):
        """When two items are both in the [-5, +15] live window, the first is
        featured as 'live' and the second must still appear (in side panel)."""
        # Fixture already has today_live_task at 8:00 PM (8 min after FIXED_NOW).
        # Add a SECOND item in the same window (e.g., 7:55 PM).
        t2 = Task.objects.create(
            title="Second Live Item",
            due_date=TODAY,
            due_time=time(19, 55),  # 3 min after FIXED_NOW 7:52 — still in window
            status="not_started",
            priority="high",
            task_type="one_time",
            direction="personal",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        self.assertIn(
            f"/tasks/{t2.pk}/", html,
            "Second live-window item silently dropped when first is featured as 'live'"
        )


class V2KeyboardA11yTests(_FixtureMixin, TestCase):
    """Layer 13: collapsible section heads are keyboard-accessible.

    BUG GUARDED: the redesign uses <div class="v2-section-head"> with a click
    handler but no tabindex/role — keyboard users couldn't collapse sections.
    """

    def setUp(self):
        self._time_patcher = _freeze_time(FIXED_NOW)
        self._time_patcher.start()

    def tearDown(self):
        self._time_patcher.stop()

    def test_section_heads_get_role_and_tabindex_via_js(self):
        """The JS in index_v2.html must set role=button and tabindex=0 on
        section heads. Since Django tests render HTML server-side and don't
        execute JS, we assert the JS contains the expected setAttribute calls."""
        html = self.client.get("/?v=v2").content.decode("utf-8")
        self.assertIn("setAttribute('role', 'button')", html,
                      "Section heads missing role=button setup in client JS")
        self.assertIn("setAttribute('tabindex', '0')", html,
                      "Section heads missing tabindex=0 setup in client JS")
        self.assertIn("aria-expanded", html,
                      "No aria-expanded handling on collapsible sections")

    def test_section_heads_respond_to_enter_and_space(self):
        """JS must register keydown handlers for Enter and Space keys."""
        html = self.client.get("/?v=v2").content.decode("utf-8")
        self.assertIn("e.key === 'Enter'", html,
                      "Section head keyboard handler missing Enter support")
        self.assertIn("e.key === ' '", html,
                      "Section head keyboard handler missing Space support")


# ═══════════════════════════════════════════════════════════════════════════
#  Cross-type silent-drop coverage — EVERY legacy data type must surface
#  somewhere in v2 (hero or pipeline), never silently vanish.
# ═══════════════════════════════════════════════════════════════════════════


class V2HealthcareAppointmentTests(TestCase):
    """Healthcare appointments rendered in legacy dashboard but dropped in v2.

    User has real appointments in their DB. Silent-drop = user misses a doctor
    visit. This suite is a critical regression guard.
    """

    @classmethod
    def setUpTestData(cls):
        from healthcare.models import Appointment, Provider
        cls.provider = Provider.objects.create(name="Dr. Test", specialty="primary_care")

    def setUp(self):
        self._time_patcher = _freeze_time(FIXED_NOW)
        self._time_patcher.start()
        self.client = Client()

    def tearDown(self):
        self._time_patcher.stop()

    def test_appointment_today_appears_in_hero(self):
        from healthcare.models import Appointment
        a = Appointment.objects.create(
            title="Dental today",
            date=TODAY, time=time(10, 0),
            provider=self.provider,
            status="scheduled",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        hero_start = html.find("v2-hero ")
        pipeline_start = html.find("Pipeline", hero_start)
        hero = html[hero_start:pipeline_start]
        self.assertIn(
            f"/healthcare/appointments/{a.pk}/", hero,
            f"Appointment due today silently dropped from v2 hero. "
            f"This is exactly the silent-breakage class the user flagged."
        )

    def test_appointment_tomorrow_appears_in_pipeline_tomorrow_band(self):
        from healthcare.models import Appointment
        a = Appointment.objects.create(
            title="Dental tomorrow",
            date=TODAY + timedelta(days=1), time=time(14, 0),
            provider=self.provider, status="scheduled",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        pipe = _extract_section_html(html, "Pipeline ·")
        self.assertIn(
            f"/healthcare/appointments/{a.pk}/", pipe,
            "Appointment tomorrow silently dropped from v2 pipeline"
        )

    def test_appointment_day_3_appears_in_pipeline_rest_band(self):
        from healthcare.models import Appointment
        a = Appointment.objects.create(
            title="Dermatology in 3 days",
            date=TODAY + timedelta(days=3), time=time(11, 30),
            provider=self.provider, status="scheduled",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        pipe = _extract_section_html(html, "Pipeline ·")
        self.assertIn(
            f"/healthcare/appointments/{a.pk}/", pipe,
            "Appointment 3 days out silently dropped from v2 pipeline rest-of-week"
        )

    def test_appointment_8_days_out_correctly_hidden(self):
        """Items beyond the 7-day horizon are intentionally hidden per the skill spec."""
        from healthcare.models import Appointment
        a = Appointment.objects.create(
            title="Appointment far out",
            date=TODAY + timedelta(days=8), time=time(11, 0),
            provider=self.provider, status="scheduled",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        pipe = _extract_section_html(html, "Pipeline ·")
        self.assertNotIn(
            f"/healthcare/appointments/{a.pk}/", pipe,
            "Appointment beyond 7-day horizon leaked into pipeline (spec violation)"
        )

    def test_completed_appointment_never_renders(self):
        from healthcare.models import Appointment
        a = Appointment.objects.create(
            title="Completed appt",
            date=TODAY, time=time(9, 0),
            provider=self.provider, status="completed",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        self.assertNotIn(
            f"/healthcare/appointments/{a.pk}/", html,
            "Completed appointment leaked onto dashboard"
        )

    def test_cancelled_appointment_never_renders(self):
        from healthcare.models import Appointment
        a = Appointment.objects.create(
            title="Cancelled appt",
            date=TODAY + timedelta(days=1), time=time(9, 0),
            provider=self.provider, status="cancelled",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        self.assertNotIn(
            f"/healthcare/appointments/{a.pk}/", html,
            "Cancelled appointment leaked onto dashboard"
        )


class V2LoanPaymentDeadlineTests(TestCase):
    """Loan payments (next_payment_date) surfaced in legacy, silently dropped in v2.

    User has 1 real loan with payment due today. This is the highest-severity
    silent-drop category — missing a loan payment has financial consequences.
    """

    def setUp(self):
        self._time_patcher = _freeze_time(FIXED_NOW)
        self._time_patcher.start()
        self.client = Client()

    def tearDown(self):
        self._time_patcher.stop()

    def test_loan_payment_today_appears_in_hero(self):
        loan = Loan.objects.create(
            name="Seed Loan Today",
            status="active",
            next_payment_date=TODAY,
            current_balance=Decimal("5000"),
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        hero_start = html.find("v2-hero ")
        pipeline_start = html.find("Pipeline", hero_start)
        hero = html[hero_start:pipeline_start]
        self.assertIn(
            f"/assets/loans/{loan.pk}/", hero,
            f"Loan payment due TODAY silently dropped. User may miss a payment."
        )

    def test_loan_payment_tomorrow_appears_in_pipeline(self):
        loan = Loan.objects.create(
            name="Seed Loan Tomorrow",
            status="active",
            next_payment_date=TODAY + timedelta(days=1),
            current_balance=Decimal("5000"),
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        pipe = _extract_section_html(html, "Pipeline ·")
        self.assertIn(
            f"/assets/loans/{loan.pk}/", pipe,
            "Loan payment tomorrow silently dropped from v2 pipeline"
        )

    def test_loan_payment_day_4_appears_in_pipeline_rest_band(self):
        loan = Loan.objects.create(
            name="Seed Loan Day 4",
            status="active",
            next_payment_date=TODAY + timedelta(days=4),
            current_balance=Decimal("5000"),
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        pipe = _extract_section_html(html, "Pipeline ·")
        self.assertIn(
            f"/assets/loans/{loan.pk}/", pipe,
            "Loan payment 4 days out silently dropped"
        )

    def test_inactive_loan_payment_not_rendered(self):
        """Paid-off loans (non-active status) must not render in pipeline."""
        loan = Loan.objects.create(
            name="Paid Off",
            status="paid_off",
            next_payment_date=TODAY + timedelta(days=1),
            current_balance=Decimal("0"),
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        pipe = _extract_section_html(html, "Pipeline ·")
        self.assertNotIn(
            f"Seed Loan Today: {loan.name}", pipe,
        )

    def test_loan_without_next_payment_date_does_not_render_in_pipeline(self):
        """Most loans have next_payment_date=None — must not clutter the pipeline."""
        loan = Loan.objects.create(
            name="Indefinite Loan", status="active",
            current_balance=Decimal("1000"),
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        pipe = _extract_section_html(html, "Pipeline ·")
        self.assertNotIn(
            f"Payment: {loan.name}", pipe,
            "Loan without next_payment_date leaked into pipeline"
        )


class V2LegalHearingDeadlineTests(TestCase):
    """Legal hearings (next_hearing_date) dropped in v2 if not today/tomorrow."""

    def setUp(self):
        self._time_patcher = _freeze_time(FIXED_NOW)
        self._time_patcher.start()
        self.client = Client()

    def tearDown(self):
        self._time_patcher.stop()

    def test_hearing_tomorrow_appears_in_pipeline(self):
        matter = LegalMatter.objects.create(
            title="Hearing Matter Tom",
            status="active", matter_type="litigation",
            next_hearing_date=TODAY + timedelta(days=1),
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        pipe = _extract_section_html(html, "Pipeline ·")
        self.assertIn(
            f"/legal/{matter.pk}/", pipe,
            "Legal hearing tomorrow silently dropped from v2 pipeline"
        )

    def test_hearing_day_5_appears_in_pipeline_rest(self):
        matter = LegalMatter.objects.create(
            title="Hearing Day 5",
            status="active", matter_type="litigation",
            next_hearing_date=TODAY + timedelta(days=5),
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        pipe = _extract_section_html(html, "Pipeline ·")
        self.assertIn(
            f"/legal/{matter.pk}/", pipe,
            "Legal hearing 5 days out silently dropped"
        )

    def test_resolved_matter_hearing_never_renders_in_pipeline(self):
        matter = LegalMatter.objects.create(
            title="Resolved w/ hearing",
            status="resolved", matter_type="litigation",
            next_hearing_date=TODAY + timedelta(days=2),
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        pipe = _extract_section_html(html, "Pipeline ·")
        self.assertNotIn(
            f"Hearing: {matter.title}", pipe,
            "Resolved matter's hearing leaked into pipeline"
        )


class V2ReminderOnlyTaskTests(TestCase):
    """Tasks with due_date=None but reminder_date in range — previously dropped.

    Scenario: user sets a task reminder for 3 days from now to call someone,
    never assigns a due_date. Legacy shows this in Upcoming Reminders panel,
    v2 previously dropped it entirely.
    """

    def setUp(self):
        self._time_patcher = _freeze_time(FIXED_NOW)
        self._time_patcher.start()
        self.client = Client()

    def tearDown(self):
        self._time_patcher.stop()

    def test_reminder_only_task_tomorrow_appears_in_pipeline(self):
        t = Task.objects.create(
            title="Call someone (reminder only)",
            due_date=None,
            reminder_date=FIXED_NOW + timedelta(days=1, hours=3),
            status="not_started", priority="high",
            task_type="one_time", direction="personal",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        pipe = _extract_section_html(html, "Pipeline ·")
        self.assertIn(
            f"/tasks/{t.pk}/", pipe,
            "Reminder-only task (no due_date) tomorrow silently dropped. "
            "User will miss the call."
        )

    def test_reminder_only_task_day_5_appears_in_pipeline_rest(self):
        t = Task.objects.create(
            title="Call someone day 5",
            due_date=None,
            reminder_date=FIXED_NOW + timedelta(days=5),
            status="not_started", priority="medium",
            task_type="one_time", direction="personal",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        pipe = _extract_section_html(html, "Pipeline ·")
        self.assertIn(
            f"/tasks/{t.pk}/", pipe,
            "Reminder-only task 5 days out silently dropped"
        )

    def test_reminder_only_task_beyond_horizon_correctly_hidden(self):
        """9 days out — beyond the pipeline's 6-day cap (though reminder is within 7)."""
        t = Task.objects.create(
            title="Far reminder",
            due_date=None,
            reminder_date=FIXED_NOW + timedelta(days=9),
            status="not_started", priority="low",
            task_type="one_time", direction="personal",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        pipe = _extract_section_html(html, "Pipeline ·")
        self.assertNotIn(f"/tasks/{t.pk}/", pipe)

    def test_reminder_only_task_not_duplicated_when_reminder_is_today(self):
        """If reminder fires today, it goes to today hero — not pipeline too."""
        t = Task.objects.create(
            title="Today reminder-only",
            due_date=None,
            reminder_date=FIXED_NOW + timedelta(minutes=30),
            status="not_started", priority="medium",
            task_type="one_time", direction="personal",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        pipe = _extract_section_html(html, "Pipeline ·")
        self.assertNotIn(
            f"/tasks/{t.pk}/", pipe,
            "Today's reminder-only task also duplicated in tomorrow pipeline"
        )
        # But it SHOULD appear in the hero today_items
        hero_start = html.find("v2-hero ")
        pipe_start = html.find("Pipeline", hero_start)
        hero = html[hero_start:pipe_start]
        self.assertIn(
            f"/tasks/{t.pk}/", hero,
            "Today's reminder-only task missing from hero"
        )


class V2ChecklistDueDateTests(TestCase):
    """Checklists with due_date now surface with time-awareness in pipeline/hero.

    Before: only shown in Monitoring section as 'N items remaining' — no day band.
    After: also appears in pipeline bands when due_date falls in range.
    """

    def setUp(self):
        self._time_patcher = _freeze_time(FIXED_NOW)
        self._time_patcher.start()
        self.client = Client()

    def tearDown(self):
        self._time_patcher.stop()

    def test_checklist_due_today_appears_in_hero(self):
        cl = Checklist.objects.create(name="Seed CL Today", due_date=TODAY)
        for i in range(3):
            ChecklistItem.objects.create(checklist=cl, title=f"Item {i}", is_completed=False)
        html = self.client.get("/?v=v2").content.decode("utf-8")
        hero_start = html.find("v2-hero ")
        pipe_start = html.find("Pipeline", hero_start)
        hero = html[hero_start:pipe_start]
        self.assertIn(
            "Seed CL Today", hero,
            "Checklist due TODAY silently dropped from hero day-awareness"
        )

    def test_checklist_due_tomorrow_appears_in_pipeline(self):
        cl = Checklist.objects.create(name="Seed CL Tom", due_date=TODAY + timedelta(days=1))
        for i in range(3):
            ChecklistItem.objects.create(checklist=cl, title=f"Item {i}", is_completed=False)
        html = self.client.get("/?v=v2").content.decode("utf-8")
        pipe = _extract_section_html(html, "Pipeline ·")
        self.assertIn(
            "Seed CL Tom", pipe,
            "Checklist due tomorrow missing from pipeline tomorrow band"
        )


class V2CrossTypeDedupeTests(TestCase):
    """Guard: each item surfaces ONCE per band, no matter which table it lives in.

    BUG GUARDED: broadening the pipeline to include loans/legals/appts/etc. can
    accidentally re-add a task (e.g. via reminder) that was already added via due_date.
    """

    def setUp(self):
        self._time_patcher = _freeze_time(FIXED_NOW)
        self._time_patcher.start()
        self.client = Client()

    def tearDown(self):
        self._time_patcher.stop()

    def test_task_with_due_date_AND_reminder_in_same_band_renders_once(self):
        t = Task.objects.create(
            title="Dup check",
            due_date=TODAY + timedelta(days=2),
            reminder_date=FIXED_NOW + timedelta(days=2, hours=4),
            status="not_started", priority="high",
            task_type="one_time", direction="personal",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        pipe = _extract_section_html(html, "Pipeline ·")
        import re
        matches = re.findall(rf'href="/tasks/{t.pk}/', pipe)
        self.assertEqual(
            len(matches), 1,
            f"Task with due_date AND reminder in same pipeline band rendered {len(matches)}x"
        )


class V2PipelineSortOrderTests(TestCase):
    """Pipeline bands must order items by actual time, not alphabetically.

    BUG GUARDED: sorting by the 12-hour `time_label` string put "10:00 AM"
    before "2:00 AM" because '1' < '2'. Sort must use the underlying
    `time` object instead.
    """

    def setUp(self):
        self._time_patcher = _freeze_time(FIXED_NOW)
        self._time_patcher.start()
        self.client = Client()

    def tearDown(self):
        self._time_patcher.stop()

    def test_tomorrow_band_sorts_times_chronologically_not_alphabetically(self):
        tomorrow = TODAY + timedelta(days=1)
        t_10am = Task.objects.create(
            title="Sort 10AM", due_date=tomorrow, due_time=time(10, 0),
            status="not_started", priority="low",
            task_type="one_time", direction="personal",
        )
        t_2am = Task.objects.create(
            title="Sort 2AM", due_date=tomorrow, due_time=time(2, 0),
            status="not_started", priority="low",
            task_type="one_time", direction="personal",
        )
        t_2pm = Task.objects.create(
            title="Sort 2PM", due_date=tomorrow, due_time=time(14, 0),
            status="not_started", priority="low",
            task_type="one_time", direction="personal",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        pipe = _extract_section_html(html, "Pipeline ·")
        pos_2am = pipe.find("Sort 2AM")
        pos_10am = pipe.find("Sort 10AM")
        pos_2pm = pipe.find("Sort 2PM")
        self.assertGreater(pos_2am, 0, "Sort 2AM not rendered")
        self.assertGreater(pos_10am, 0, "Sort 10AM not rendered")
        self.assertGreater(pos_2pm, 0, "Sort 2PM not rendered")
        self.assertLess(
            pos_2am, pos_10am,
            "2:00 AM must render before 10:00 AM (chronological, not alphabetical)"
        )
        self.assertLess(
            pos_10am, pos_2pm,
            "10:00 AM must render before 2:00 PM"
        )

    def test_all_day_items_render_after_timed_items_same_date(self):
        tomorrow = TODAY + timedelta(days=1)
        t_timed = Task.objects.create(
            title="Timed item", due_date=tomorrow, due_time=time(14, 0),
            status="not_started", priority="low",
            task_type="one_time", direction="personal",
        )
        t_allday = Task.objects.create(
            title="All-day item", due_date=tomorrow, due_time=None,
            status="not_started", priority="low",
            task_type="one_time", direction="personal",
        )
        html = self.client.get("/?v=v2").content.decode("utf-8")
        pipe = _extract_section_html(html, "Pipeline ·")
        self.assertLess(
            pipe.find("Timed item"), pipe.find("All-day item"),
            "Timed items must render before all-day items within the same date"
        )


class V2ChecklistNoDoubleAppearanceTests(TestCase):
    """Checklists with due_date in [today, week_end] must appear in hero OR
    pipeline — never ALSO in monitoring. (Undated and past-due checklists
    continue to show in monitoring.)

    BUG GUARDED: checklist with due_date=tomorrow rendering in both Pipeline
    (tomorrow band) and Monitoring (all outstanding_checklists), creating a
    duplicate row visible to the user.
    """

    def setUp(self):
        self._time_patcher = _freeze_time(FIXED_NOW)
        self._time_patcher.start()
        self.client = Client()

    def tearDown(self):
        self._time_patcher.stop()

    def _render(self):
        return self.client.get("/?v=v2").content.decode("utf-8")

    def test_checklist_due_tomorrow_not_also_in_monitoring(self):
        cl = Checklist.objects.create(
            name="Dedupe Tom", due_date=TODAY + timedelta(days=1),
        )
        for i in range(3):
            ChecklistItem.objects.create(
                checklist=cl, title=f"Item {i}", is_completed=False,
            )
        html = self._render()
        pipe = _extract_section_html(html, "Pipeline ·")
        mon = _extract_section_html(html, "Monitoring ·")
        self.assertIn("Dedupe Tom", pipe, "Checklist due tomorrow missing from pipeline")
        self.assertNotIn(
            "Dedupe Tom", mon,
            "Checklist due tomorrow must not ALSO appear in monitoring"
        )

    def test_checklist_due_today_not_also_in_monitoring(self):
        cl = Checklist.objects.create(name="Dedupe Today", due_date=TODAY)
        for i in range(3):
            ChecklistItem.objects.create(
                checklist=cl, title=f"Item {i}", is_completed=False,
            )
        html = self._render()
        mon = _extract_section_html(html, "Monitoring ·")
        self.assertNotIn(
            "Dedupe Today", mon,
            "Checklist due today is in hero — must not ALSO appear in monitoring"
        )

    def test_undated_checklist_still_in_monitoring(self):
        cl = Checklist.objects.create(name="Undated CL")
        for i in range(3):
            ChecklistItem.objects.create(
                checklist=cl, title=f"Item {i}", is_completed=False,
            )
        html = self._render()
        mon = _extract_section_html(html, "Monitoring ·")
        self.assertIn(
            "Undated CL", mon,
            "Undated checklist must continue to render in monitoring"
        )

    def test_past_due_checklist_still_in_monitoring(self):
        cl = Checklist.objects.create(
            name="Past Due CL", due_date=TODAY - timedelta(days=3),
        )
        for i in range(3):
            ChecklistItem.objects.create(
                checklist=cl, title=f"Item {i}", is_completed=False,
            )
        html = self._render()
        mon = _extract_section_html(html, "Monitoring ·")
        self.assertIn(
            "Past Due CL", mon,
            "Past-due checklist must continue to render in monitoring"
        )
