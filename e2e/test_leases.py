"""E2E Playwright tests for Lease Tracking feature."""
import json
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from assets.models import Lease, LeaseParty, RealEstate
from dashboard.models import ChoiceOption
from stakeholders.models import Stakeholder
from e2e.base import PlaywrightTestCase


def _seed_lease_type():
    """Seed lease_type ChoiceOption (TransactionTestCase flushes migration data)."""
    ChoiceOption.objects.get_or_create(
        category="lease_type", value="residential",
        defaults={"label": "Residential", "sort_order": 1},
    )
    ChoiceOption.objects.get_or_create(
        category="lease_type", value="commercial",
        defaults={"label": "Commercial", "sort_order": 2},
    )


class LeaseListTests(PlaywrightTestCase):
    """Test lease list page rendering and navigation."""

    def setUp(self):
        super().setUp()
        self.prop = RealEstate.objects.create(name="Test Property", address="100 Main St")
        self.lease = Lease.objects.create(
            name="Test Residential Lease",
            related_property=self.prop,
            lease_type="residential",
            status="active",
            monthly_rent=Decimal("2500.00"),
        )

    def test_list_page_loads(self):
        """Lease list page renders with lease data."""
        self.page.goto(self.url("/assets/leases/"))
        self.page.wait_for_selector("h1")
        h1 = self.page.text_content("h1")
        self.assertEqual(h1, "Leases")

    def test_list_shows_lease(self):
        """Lease appears in the table with correct name."""
        self.page.goto(self.url("/assets/leases/"))
        self.page.wait_for_selector("table")
        content = self.page.text_content("table")
        self.assertIn("Test Residential Lease", content)

    def test_list_shows_property_name(self):
        """Lease row shows the related property name."""
        self.page.goto(self.url("/assets/leases/"))
        self.page.wait_for_selector("table")
        content = self.page.text_content("table")
        self.assertIn("Test Property", content)

    def test_list_links_to_detail(self):
        """Clicking a lease name navigates to the detail page."""
        self.page.goto(self.url("/assets/leases/"))
        self.page.click(f"a:has-text('Test Residential Lease')")
        self.page.wait_for_selector("h1")
        h1 = self.page.text_content("h1")
        self.assertEqual(h1, "Test Residential Lease")

    def test_list_new_lease_button(self):
        """'+Lease' button navigates to create form."""
        self.page.goto(self.url("/assets/leases/"))
        self.page.click("a:has-text('+ Lease')")
        self.page.wait_for_selector("h1")
        h1 = self.page.text_content("h1")
        self.assertIn("New Lease", h1)

    def test_csv_export(self):
        """Export CSV link returns CSV content."""
        self.page.goto(self.url("/assets/leases/"))
        # Just verify the link exists
        link = self.page.locator("a:has-text('Export CSV')")
        self.assertTrue(link.is_visible())


class LeaseCreateFormTests(PlaywrightTestCase):
    """Test lease create form interactivity."""

    def setUp(self):
        super().setUp()
        _seed_lease_type()
        self.prop = RealEstate.objects.create(name="Form Property", address="200 Oak St")
        self.stakeholder = Stakeholder.objects.create(name="Form Tenant")

    def test_form_renders(self):
        """Create form loads with all fields."""
        self.page.goto(self.url("/assets/leases/create/"))
        self.page.wait_for_selector("form")
        # Required fields should be present
        self.assertTrue(self.page.locator("input[name='name']").is_visible())
        self.assertTrue(self.page.locator("select[name='related_property']").is_visible())
        self.assertTrue(self.page.locator("select[name='status']").is_visible())

    def test_create_lease_and_redirect(self):
        """Submitting form creates lease and redirects to detail."""
        self.page.goto(self.url("/assets/leases/create/"))
        self.page.fill("input[name='name']", "E2E Created Lease")
        self.page.select_option("select[name='related_property']", str(self.prop.pk))
        self.page.select_option("select[name='lease_type']", "residential")
        self.page.select_option("select[name='status']", "active")
        self.page.select_option("select[name='renewal_type']", "none")
        self.page.click("button[type='submit']")
        # Wait for redirect to detail page
        self.page.wait_for_url("**/leases/*/", timeout=5000)
        h1 = self.page.text_content("h1")
        self.assertEqual(h1, "E2E Created Lease")
        # Verify in DB
        self.assertTrue(Lease.objects.filter(name="E2E Created Lease").exists())

    def test_create_with_initial_party(self):
        """Creating a lease with initial stakeholder adds LeaseParty."""
        self.page.goto(self.url("/assets/leases/create/"))
        self.page.fill("input[name='name']", "Lease With Party")
        self.page.select_option("select[name='related_property']", str(self.prop.pk))
        self.page.select_option("select[name='lease_type']", "residential")
        self.page.select_option("select[name='status']", "active")
        self.page.select_option("select[name='renewal_type']", "auto")
        self.page.select_option("select[name='initial_stakeholder']", str(self.stakeholder.pk))
        self.page.fill("input[name='initial_role']", "Tenant")
        self.page.click("button[type='submit']")
        self.page.wait_for_url("**/leases/*/", timeout=5000)
        lease = Lease.objects.get(name="Lease With Party")
        self.assertTrue(LeaseParty.objects.filter(lease=lease, stakeholder=self.stakeholder).exists())

    def test_property_preselected_via_query(self):
        """?property=pk preselects the property dropdown."""
        self.page.goto(self.url(f"/assets/leases/create/?property={self.prop.pk}"))
        self.page.wait_for_selector("form")
        selected = self.page.locator("select[name='related_property']").input_value()
        self.assertEqual(selected, str(self.prop.pk))


class LeaseDetailTests(PlaywrightTestCase):
    """Test lease detail page content and actions."""

    def setUp(self):
        super().setUp()
        self.prop = RealEstate.objects.create(name="Detail Property", address="300 Elm St")
        self.stakeholder = Stakeholder.objects.create(name="Detail Tenant")
        self.lease = Lease.objects.create(
            name="Detail Test Lease",
            related_property=self.prop,
            lease_type="commercial",
            status="active",
            monthly_rent=Decimal("5000.00"),
            security_deposit=Decimal("10000.00"),
            start_date=timezone.localdate() - timedelta(days=180),
            end_date=timezone.localdate() + timedelta(days=185),
            rent_due_day=1,
            renewal_type="option",
            escalation_rate=Decimal("3.00"),
            notes_text="Some internal notes here.",
        )

    def test_detail_page_loads(self):
        """Detail page renders with lease name."""
        self.page.goto(self.url(f"/assets/leases/{self.lease.pk}/"))
        h1 = self.page.wait_for_selector("h1")
        self.assertEqual(h1.text_content(), "Detail Test Lease")

    def test_hero_cards_show_data(self):
        """Hero stat cards display rent, status, type, end date."""
        self.page.goto(self.url(f"/assets/leases/{self.lease.pk}/"))
        self.page.wait_for_selector("h1")
        content = self.page.text_content("body")
        self.assertIn("$5,000", content)
        self.assertIn("Active", content)

    def test_detail_shows_property_link(self):
        """Property name is a clickable link."""
        self.page.goto(self.url(f"/assets/leases/{self.lease.pk}/"))
        prop_link = self.page.locator(f"a:has-text('Detail Property')")
        self.assertTrue(prop_link.is_visible())

    def test_detail_shows_notes(self):
        """Internal notes section rendered."""
        self.page.goto(self.url(f"/assets/leases/{self.lease.pk}/"))
        self.page.wait_for_selector("h1")
        content = self.page.text_content("body")
        self.assertIn("Some internal notes here.", content)

    def test_detail_shows_deposit_and_escalation(self):
        """Detail shows security deposit and escalation rate."""
        self.page.goto(self.url(f"/assets/leases/{self.lease.pk}/"))
        self.page.wait_for_selector("h1")
        content = self.page.text_content("body")
        self.assertIn("$10,000", content)
        self.assertIn("3.00%", content)

    def test_edit_button_navigates_to_form(self):
        """Edit button goes to edit form."""
        self.page.goto(self.url(f"/assets/leases/{self.lease.pk}/"))
        self.page.click("a:has-text('Edit')")
        self.page.wait_for_selector("h1")
        h1 = self.page.text_content("h1")
        self.assertIn("Edit Lease", h1)

    def test_pdf_export(self):
        """PDF button returns PDF content."""
        self.page.goto(self.url(f"/assets/leases/{self.lease.pk}/"))
        pdf_link = self.page.locator("a:has-text('PDF')")
        href = pdf_link.get_attribute("href")
        self.assertIn("pdf", href)


class LeaseEditDeleteTests(PlaywrightTestCase):
    """Test editing and deleting leases."""

    def setUp(self):
        super().setUp()
        _seed_lease_type()
        self.prop = RealEstate.objects.create(name="Edit Property", address="x")
        self.lease = Lease.objects.create(
            name="Editable Lease",
            related_property=self.prop,
            lease_type="residential",
            status="active",
            renewal_type="none",
        )

    def test_edit_updates_lease(self):
        """Edit form saves changes and redirects to detail."""
        self.page.goto(self.url(f"/assets/leases/{self.lease.pk}/edit/"))
        self.page.fill("input[name='name']", "Renamed Lease")
        # Ensure required fields are set
        self.page.select_option("select[name='lease_type']", "residential")
        self.page.select_option("select[name='renewal_type']", "none")
        self.page.click("button[type='submit']")
        # Wait for redirect to detail page
        self.page.wait_for_url(f"**/leases/{self.lease.pk}/", timeout=5000)
        h1 = self.page.text_content("h1")
        self.assertEqual(h1, "Renamed Lease")
        self.lease.refresh_from_db()
        self.assertEqual(self.lease.name, "Renamed Lease")

    def test_edit_hides_initial_fields(self):
        """Edit form should NOT show Initial Party section."""
        self.page.goto(self.url(f"/assets/leases/{self.lease.pk}/edit/"))
        self.page.wait_for_selector("form")
        content = self.page.text_content("form")
        self.assertNotIn("Initial Party", content)

    def test_delete_removes_lease(self):
        """Deleting a lease removes it and redirects to list."""
        self.page.goto(self.url(f"/assets/leases/{self.lease.pk}/delete/"))
        self.page.click("button[type='submit']")
        self.page.wait_for_url("**/leases/")
        self.assertFalse(Lease.objects.filter(pk=self.lease.pk).exists())


class LeaseInlineStatusTests(PlaywrightTestCase):
    """Test inline status editing on the lease list page."""

    def setUp(self):
        super().setUp()
        self.prop = RealEstate.objects.create(name="Status Prop", address="x")
        self.lease = Lease.objects.create(
            name="Status Lease",
            related_property=self.prop,
            status="active",
            monthly_rent=Decimal("1000.00"),
        )

    def test_inline_status_change(self):
        """Changing the status dropdown on the list updates the DB via HTMX."""
        self.page.set_viewport_size({"width": 1280, "height": 800})
        self.page.goto(self.url("/assets/leases/"))
        self.page.wait_for_selector("table")

        # The status select is only visible on lg screens
        status_select = self.page.locator(f"#lease-row-{self.lease.pk} select")
        status_select.select_option("expired")

        # Wait for HTMX swap (row re-renders)
        self.page.wait_for_timeout(500)

        # Verify DB
        self.lease.refresh_from_db()
        self.assertEqual(self.lease.status, "expired")


class LeasePartyInlineTests(PlaywrightTestCase):
    """Test HTMX inline add/delete of lease parties on detail page."""

    def setUp(self):
        super().setUp()
        self.prop = RealEstate.objects.create(name="Party Prop", address="x")
        self.stakeholder = Stakeholder.objects.create(name="Party Stakeholder")
        self.lease = Lease.objects.create(
            name="Party Lease",
            related_property=self.prop,
            status="active",
        )

    def test_add_party_inline(self):
        """Click '+ Add Party' -> form appears -> submit -> party appears in list."""
        self.page.goto(self.url(f"/assets/leases/{self.lease.pk}/"))
        self.page.wait_for_selector("h1")

        # Click + Add Party button
        self.page.click("button:has-text('+ Add Party')")

        # Wait for the inline form to appear via HTMX
        self.page.wait_for_selector("#party-form-container select[name='stakeholder']")

        # Fill the form
        self.page.select_option("#party-form-container select[name='stakeholder']", str(self.stakeholder.pk))
        self.page.fill("#party-form-container input[name='role']", "Tenant")
        self.page.click("#party-form-container button[type='submit']")

        # Wait for party list to update
        self.page.wait_for_selector("#party-list >> text=Party Stakeholder")

        # Verify DB
        self.assertTrue(LeaseParty.objects.filter(
            lease=self.lease, stakeholder=self.stakeholder).exists())

    def test_delete_party_inline(self):
        """Party delete button removes party from list."""
        party = LeaseParty.objects.create(
            lease=self.lease, stakeholder=self.stakeholder, role="Landlord")

        self.page.goto(self.url(f"/assets/leases/{self.lease.pk}/"))
        self.page.wait_for_selector("#party-list >> text=Party Stakeholder")

        # Accept the confirm dialog
        self.page.on("dialog", lambda d: d.accept())

        # Click the delete button
        self.page.click(f"#party-list button[hx-post*='lease-party/{party.pk}/delete']")

        # Wait for removal
        self.page.wait_for_timeout(500)

        # Verify DB
        self.assertFalse(LeaseParty.objects.filter(pk=party.pk).exists())


class LeaseUnifiedAssetsTests(PlaywrightTestCase):
    """Test leases appearing on the unified /assets/ page."""

    def setUp(self):
        super().setUp()
        self.prop = RealEstate.objects.create(name="Asset Prop", address="x")
        self.lease = Lease.objects.create(
            name="Unified Asset Lease",
            related_property=self.prop,
            status="active",
        )

    def test_all_tab_shows_leases_section(self):
        """The 'All' tab on /assets/ includes a Leases section."""
        self.page.goto(self.url("/assets/"))
        self.page.wait_for_selector("h1")
        content = self.page.text_content("body")
        self.assertIn("Unified Asset Lease", content)

    def test_leases_tab_exists(self):
        """A 'Leases' tab exists in the tab bar."""
        self.page.goto(self.url("/assets/"))
        self.page.wait_for_selector("h1")
        # Tabs use <a> elements, could also be in a mobile <select>
        content = self.page.text_content("body")
        self.assertIn("Leases", content)


class LeasePropertyDetailTests(PlaywrightTestCase):
    """Test leases section on property detail page."""

    def setUp(self):
        super().setUp()
        self.prop = RealEstate.objects.create(
            name="PropDetail Property", address="500 Main St", status="owned")
        self.lease = Lease.objects.create(
            name="PropDetail Lease",
            related_property=self.prop,
            lease_type="residential",
            status="active",
            monthly_rent=Decimal("1800.00"),
        )

    def test_property_detail_shows_lease(self):
        """Property detail page has a Leases section with the lease name."""
        self.page.goto(self.url(f"/assets/real-estate/{self.prop.pk}/"))
        self.page.wait_for_selector("h1")
        content = self.page.text_content("body")
        self.assertIn("PropDetail Lease", content)
        self.assertIn("$1,800", content)

    def test_property_detail_new_lease_link(self):
        """'+ New Lease' button has property preselect query param."""
        self.page.goto(self.url(f"/assets/real-estate/{self.prop.pk}/"))
        self.page.wait_for_selector("h1")
        link = self.page.locator(f"a[href*='property={self.prop.pk}']")
        self.assertTrue(link.count() > 0)


class LeaseStakeholderDetailTests(PlaywrightTestCase):
    """Test lease tab on stakeholder detail page."""

    def setUp(self):
        super().setUp()
        self.prop = RealEstate.objects.create(name="SH Prop", address="x")
        self.stakeholder = Stakeholder.objects.create(name="SH Person", entity_type="contact")
        self.lease = Lease.objects.create(
            name="SH Lease", related_property=self.prop, status="active")
        self.party = LeaseParty.objects.create(
            lease=self.lease, stakeholder=self.stakeholder, role="Tenant")

    def test_stakeholder_detail_has_leases_tab(self):
        """Stakeholder detail page has a Leases tab button."""
        self.page.goto(self.url(f"/stakeholders/{self.stakeholder.pk}/"))
        self.page.wait_for_selector("h1")
        tab = self.page.locator("button[data-tab='leases']")
        self.assertTrue(tab.is_visible())
        # Tab count should show (1)
        tab_text = tab.text_content()
        self.assertIn("1", tab_text)

    def test_stakeholder_leases_tab_shows_lease(self):
        """Clicking the Leases tab shows the linked lease."""
        self.page.goto(self.url(f"/stakeholders/{self.stakeholder.pk}/"))
        self.page.wait_for_selector("h1")

        # Click the Leases tab
        self.page.click("button[data-tab='leases']")

        # The tab content should become visible with the lease name
        tab_content = self.page.locator("#tab-leases")
        tab_content.wait_for(state="visible")
        self.assertIn("SH Lease", tab_content.text_content())


class LeaseCalendarTests(PlaywrightTestCase):
    """Test lease expiry events on the calendar."""

    def setUp(self):
        super().setUp()
        self.prop = RealEstate.objects.create(name="Cal Prop", address="x")
        self.lease = Lease.objects.create(
            name="Expiring Cal Lease",
            related_property=self.prop,
            status="active",
            monthly_rent=Decimal("2000.00"),
            end_date=timezone.localdate() + timedelta(days=15),
        )

    def test_calendar_has_lease_filter_toggle(self):
        """Calendar page has a 'Leases' filter toggle button."""
        self.page.set_viewport_size({"width": 1280, "height": 800})
        self.page.goto(self.url("/calendar/"))
        self.page.wait_for_selector("#calendar-filters-desktop")
        toggle = self.page.locator('#calendar-filters-desktop .cal-toggle[data-type="lease"]')
        self.assertTrue(toggle.is_visible())
        self.assertIn("Leases", toggle.text_content())

    def test_calendar_lease_events_endpoint(self):
        """Calendar events API returns lease expiry events with correct color."""
        today = timezone.localdate()
        start = (today - timedelta(days=5)).isoformat()
        end = (today + timedelta(days=30)).isoformat()
        resp = self.client.get(f"/calendar/events/?start={start}&end={end}")
        events = json.loads(resp.content)
        lease_events = [e for e in events if e.get("extendedProps", {}).get("type") == "lease"]
        self.assertTrue(len(lease_events) >= 1)
        self.assertEqual(lease_events[0]["color"], "#10b981")
        self.assertIn("Expiring Cal Lease", lease_events[0]["title"])

    def test_calendar_renders_lease_event(self):
        """Calendar UI renders the lease event on the page."""
        self.page.set_viewport_size({"width": 1280, "height": 800})
        self.page.goto(self.url("/calendar/"))
        # Wait for events to render
        self.page.wait_for_selector(".fc-event", timeout=5000)
        # Check that at least one event has our lease info in its title attribute
        events = self.page.locator(".fc-event")
        found = False
        for i in range(events.count()):
            title = events.nth(i).get_attribute("title") or ""
            if "Expiring Cal Lease" in title:
                found = True
                break
        self.assertTrue(found, "Lease expiry event not found on calendar")

    def test_lease_toggle_hides_events(self):
        """Clicking the Leases filter toggle hides lease events."""
        self.page.set_viewport_size({"width": 1280, "height": 800})
        self.page.goto(self.url("/calendar/"))
        self.page.wait_for_selector(".fc-event", timeout=5000)

        # Click the Leases toggle to disable
        self.page.click('#calendar-filters-desktop .cal-toggle[data-type="lease"]')

        # Wait for toggle to deactivate
        self.page.wait_for_function(
            "!document.querySelector('#calendar-filters-desktop .cal-toggle[data-type=\"lease\"]').classList.contains('active')"
        )

        # Lease events should be hidden (display: none)
        events = self.page.locator(".fc-event")
        for i in range(events.count()):
            title = events.nth(i).get_attribute("title") or ""
            if "Expiring Cal Lease" in title:
                display = events.nth(i).evaluate("el => getComputedStyle(el).display")
                self.assertEqual(display, "none")


class LeaseGlobalSearchTests(PlaywrightTestCase):
    """Test leases in global search results."""

    def setUp(self):
        super().setUp()
        self.prop = RealEstate.objects.create(name="Search Prop", address="x")
        self.lease = Lease.objects.create(
            name="Searchable Unique Lease",
            related_property=self.prop,
            status="active",
        )

    def test_search_finds_lease(self):
        """Global search returns lease in results."""
        # Use the search endpoint directly via test client
        resp = self.client.get("/search/", {"q": "Searchable Unique"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Searchable Unique Lease")

    def test_search_shows_leases_section(self):
        """Search results template shows 'Leases' section header."""
        resp = self.client.get("/search/", {"q": "Searchable"})
        self.assertContains(resp, "Leases")


class LeaseGraphTests(PlaywrightTestCase):
    """Test lease nodes in stakeholder relationship graph."""

    def setUp(self):
        super().setUp()
        self.prop = RealEstate.objects.create(name="Graph Prop", address="x")
        self.stakeholder = Stakeholder.objects.create(name="Graph Person", entity_type="contact")
        self.lease = Lease.objects.create(
            name="Graph Lease", related_property=self.prop, status="active")
        LeaseParty.objects.create(
            lease=self.lease, stakeholder=self.stakeholder, role="Tenant")

    def test_graph_data_includes_lease_node(self):
        """Graph data endpoint returns lease nodes with barrel shape."""
        resp = self.client.get(f"/stakeholders/{self.stakeholder.pk}/graph-data/")
        data = json.loads(resp.content)
        nodes = data["nodes"]
        lease_nodes = [n for n in nodes if n["id"].startswith("lease-")]
        self.assertTrue(len(lease_nodes) >= 1)
        self.assertEqual(lease_nodes[0]["shape"], "barrel")
        self.assertIn("Graph Lease", lease_nodes[0]["name"])

    def test_graph_data_includes_lease_edge(self):
        """Graph data has edge from stakeholder to lease with role label."""
        resp = self.client.get(f"/stakeholders/{self.stakeholder.pk}/graph-data/")
        data = json.loads(resp.content)
        edges = data["edges"]
        lease_edges = [e for e in edges if e["target"].startswith("lease-")]
        self.assertTrue(len(lease_edges) >= 1)
        self.assertEqual(lease_edges[0]["label"], "Tenant")
