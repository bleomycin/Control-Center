import datetime
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone

from .models import Document, GoogleDriveSettings
from .forms import DocumentForm, DocumentLinkForm, GoogleDriveSetupForm


class DocumentModelTest(TestCase):
    def setUp(self):
        self.doc = Document.objects.create(
            title="Test Document",
            category="deed",
            date=timezone.localdate(),
            description="A test document.",
        )

    def test_str(self):
        self.assertEqual(str(self.doc), "Test Document")

    def test_get_absolute_url(self):
        self.assertEqual(self.doc.get_absolute_url(), f"/documents/{self.doc.pk}/")

    def test_has_drive_link_false(self):
        self.assertFalse(self.doc.has_drive_link)

    def test_has_drive_link_true(self):
        self.doc.gdrive_url = "https://drive.google.com/file/d/abc/view"
        self.assertTrue(self.doc.has_drive_link)

    def test_has_file_false(self):
        self.assertFalse(self.doc.has_file)

    def test_file_url_drive(self):
        self.doc.gdrive_url = "https://drive.google.com/file/d/abc/view"
        self.assertEqual(self.doc.file_url, "https://drive.google.com/file/d/abc/view")

    def test_file_url_empty(self):
        self.assertEqual(self.doc.file_url, "")

    def test_linked_entities_empty(self):
        self.assertEqual(self.doc.linked_entities, [])

    def test_is_expired_false_no_date(self):
        self.assertFalse(self.doc.is_expired)

    def test_is_expired_true(self):
        self.doc.expiration_date = timezone.localdate() - datetime.timedelta(days=1)
        self.assertTrue(self.doc.is_expired)

    def test_is_expired_false_future(self):
        self.doc.expiration_date = timezone.localdate() + datetime.timedelta(days=30)
        self.assertFalse(self.doc.is_expired)

    def test_is_expiring_soon_true(self):
        self.doc.expiration_date = timezone.localdate() + datetime.timedelta(days=30)
        self.assertTrue(self.doc.is_expiring_soon)

    def test_is_expiring_soon_false_far(self):
        self.doc.expiration_date = timezone.localdate() + datetime.timedelta(days=120)
        self.assertFalse(self.doc.is_expiring_soon)

    def test_ordering(self):
        doc2 = Document.objects.create(
            title="Older Doc",
            date=timezone.localdate() - datetime.timedelta(days=30),
        )
        docs = list(Document.objects.all())
        self.assertEqual(docs[0], self.doc)  # newer first
        self.assertEqual(docs[1], doc2)


class GoogleDriveSettingsTest(TestCase):
    def test_load_creates_singleton(self):
        settings = GoogleDriveSettings.load()
        self.assertEqual(settings.pk, 1)
        self.assertFalse(settings.is_connected)

    def test_load_returns_existing(self):
        GoogleDriveSettings.objects.create(pk=1, is_connected=True, connected_email="test@example.com")
        settings = GoogleDriveSettings.load()
        self.assertTrue(settings.is_connected)

    def test_str_not_connected(self):
        settings = GoogleDriveSettings.load()
        self.assertIn("not connected", str(settings))

    def test_str_connected(self):
        settings = GoogleDriveSettings(is_connected=True, connected_email="user@example.com")
        self.assertIn("user@example.com", str(settings))


class DocumentFormTest(TestCase):
    def test_form_valid_minimal(self):
        form = DocumentForm(data={"title": "My Doc"})
        self.assertTrue(form.is_valid())

    def test_form_valid_full(self):
        form = DocumentForm(data={
            "title": "Full Doc",
            "category": "deed",
            "description": "Desc",
            "date": "2025-01-15",
            "expiration_date": "2026-01-15",
            "gdrive_url": "https://drive.google.com/file/d/abc/view",
            "notes_text": "Some notes",
        })
        self.assertTrue(form.is_valid())

    def test_form_invalid_no_title(self):
        form = DocumentForm(data={"category": "deed"})
        self.assertFalse(form.is_valid())
        self.assertIn("title", form.errors)


class DocumentListViewTest(TestCase):
    def setUp(self):
        self.url = reverse("documents:list")
        for i in range(3):
            Document.objects.create(title=f"Doc {i}", category="deed")

    def test_list_page(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Documents")
        self.assertContains(resp, "Doc 0")

    def test_htmx_returns_partial(self):
        resp = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "<html")  # partial, not full page

    def test_search_filter(self):
        Document.objects.create(title="Unique Search Target")
        resp = self.client.get(self.url, {"q": "Unique Search"})
        self.assertContains(resp, "Unique Search Target")

    def test_category_filter(self):
        Document.objects.create(title="Tax Return", category="tax_return")
        resp = self.client.get(self.url, {"category": "tax_return"})
        self.assertContains(resp, "Tax Return")
        self.assertNotContains(resp, "Doc 0")

    def test_expiring_soon_filter(self):
        Document.objects.create(
            title="Expiring Doc",
            expiration_date=timezone.localdate() + datetime.timedelta(days=30),
        )
        resp = self.client.get(self.url, {"expiring": "soon"})
        self.assertContains(resp, "Expiring Doc")
        self.assertNotContains(resp, "Doc 0")

    def test_expired_filter(self):
        Document.objects.create(
            title="Expired Doc",
            expiration_date=timezone.localdate() - datetime.timedelta(days=1),
        )
        resp = self.client.get(self.url, {"expiring": "expired"})
        self.assertContains(resp, "Expired Doc")

    def test_sort_by_title(self):
        resp = self.client.get(self.url, {"sort": "title", "dir": "asc"})
        self.assertEqual(resp.status_code, 200)

    def test_date_range_filter(self):
        today = timezone.localdate()
        Document.objects.create(title="Dated Doc", date=today)
        resp = self.client.get(self.url, {
            "date_from": str(today),
            "date_to": str(today),
        })
        self.assertContains(resp, "Dated Doc")

    def test_entity_type_unlinked(self):
        resp = self.client.get(self.url, {"entity_type": "unlinked"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Doc 0")


class DocumentDetailViewTest(TestCase):
    def setUp(self):
        self.doc = Document.objects.create(
            title="Detail Test",
            category="deed",
            description="Testing detail view.",
            date=timezone.localdate(),
        )

    def test_detail_page(self):
        resp = self.client.get(reverse("documents:detail", args=[self.doc.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Detail Test")
        self.assertContains(resp, "Testing detail view.")

    def test_detail_with_drive_link(self):
        self.doc.gdrive_url = "https://drive.google.com/file/d/abc/view"
        self.doc.gdrive_file_name = "test.pdf"
        self.doc.save()
        resp = self.client.get(reverse("documents:detail", args=[self.doc.pk]))
        self.assertContains(resp, "test.pdf")
        self.assertContains(resp, "Google Drive")

    def test_detail_no_file(self):
        resp = self.client.get(reverse("documents:detail", args=[self.doc.pk]))
        self.assertContains(resp, "No file attached")


class DocumentCreateViewTest(TestCase):
    def test_create_form_get(self):
        resp = self.client.get(reverse("documents:create"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "New Document")

    def test_create_post(self):
        resp = self.client.post(reverse("documents:create"), {
            "title": "New Created Doc",
            "category": "deed",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Document.objects.filter(title="New Created Doc").exists())

    def test_create_with_query_param(self):
        resp = self.client.get(reverse("documents:create") + "?property=1")
        self.assertEqual(resp.status_code, 200)


class DocumentUpdateViewTest(TestCase):
    def setUp(self):
        self.doc = Document.objects.create(title="Edit Me", category="deed")

    def test_edit_form_get(self):
        resp = self.client.get(reverse("documents:edit", args=[self.doc.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Edit Document")

    def test_edit_post(self):
        resp = self.client.post(reverse("documents:edit", args=[self.doc.pk]), {
            "title": "Edited Title",
        })
        self.assertEqual(resp.status_code, 302)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.title, "Edited Title")


class DocumentDeleteViewTest(TestCase):
    def setUp(self):
        self.doc = Document.objects.create(title="Delete Me")

    def test_delete_confirm(self):
        resp = self.client.get(reverse("documents:delete", args=[self.doc.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_delete_post(self):
        resp = self.client.post(reverse("documents:delete", args=[self.doc.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Document.objects.filter(pk=self.doc.pk).exists())


class BulkActionsTest(TestCase):
    def setUp(self):
        self.docs = [Document.objects.create(title=f"Bulk {i}") for i in range(3)]

    def test_bulk_delete(self):
        pks = [str(d.pk) for d in self.docs[:2]]
        resp = self.client.post(reverse("documents:bulk_delete"), {"selected": pks})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Document.objects.count(), 1)

    def test_bulk_export_csv(self):
        pks = [str(d.pk) for d in self.docs]
        resp = self.client.post(reverse("documents:bulk_export_csv"), {"selected": pks})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")


class ExportTest(TestCase):
    def setUp(self):
        Document.objects.create(title="Export Doc", category="deed")

    def test_export_csv(self):
        resp = self.client.get(reverse("documents:export_csv"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn(b"Export Doc", resp.content)

    def test_export_pdf(self):
        doc = Document.objects.first()
        resp = self.client.get(reverse("documents:export_pdf", args=[doc.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")


class DocumentLinkFormTest(TestCase):
    def test_form_valid(self):
        doc = Document.objects.create(title="Linkable Doc")
        form = DocumentLinkForm(data={"document": doc.pk})
        self.assertTrue(form.is_valid())

    def test_form_invalid_empty(self):
        form = DocumentLinkForm(data={})
        self.assertFalse(form.is_valid())


class DocumentEntityLinkTest(TestCase):
    """Test link/unlink views for all 9 entity types."""

    def setUp(self):
        self.doc = Document.objects.create(title="Link Test Doc", category="deed")

    def _create_entity(self, entity_type):
        """Create a test entity and return (entity, entity_type_key)."""
        if entity_type == "property":
            from assets.models import RealEstate
            return RealEstate.objects.create(name="Test Property")
        elif entity_type == "investment":
            from assets.models import Investment
            return Investment.objects.create(name="Test Investment")
        elif entity_type == "loan":
            from assets.models import Loan
            return Loan.objects.create(name="Test Loan")
        elif entity_type == "lease":
            from assets.models import Lease, RealEstate
            prop = RealEstate.objects.create(name="Lease Property")
            return Lease.objects.create(name="Test Lease", related_property=prop)
        elif entity_type == "policy":
            from assets.models import InsurancePolicy
            return InsurancePolicy.objects.create(name="Test Policy")
        elif entity_type == "vehicle":
            from assets.models import Vehicle
            return Vehicle.objects.create(name="Test Vehicle")
        elif entity_type == "aircraft":
            from assets.models import Aircraft
            return Aircraft.objects.create(name="Test Aircraft")
        elif entity_type == "stakeholder":
            from stakeholders.models import Stakeholder
            return Stakeholder.objects.create(name="Test Stakeholder")
        elif entity_type == "legal_matter":
            from legal.models import LegalMatter
            return LegalMatter.objects.create(title="Test Legal Matter")

    def _test_link_unlink(self, entity_type):
        entity = self._create_entity(entity_type)
        link_url = reverse(f"documents:{entity_type}_document_link", args=[entity.pk])
        unlink_url = reverse(f"documents:{entity_type}_document_unlink", args=[entity.pk, self.doc.pk])

        # GET link form
        resp = self.client.get(link_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Link")

        # POST link
        resp = self.client.post(link_url, {"document": self.doc.pk})
        self.assertEqual(resp.status_code, 200)
        self.doc.refresh_from_db()
        fk_field = f"related_{entity_type}"
        self.assertEqual(getattr(self.doc, fk_field), entity)

        # POST unlink
        resp = self.client.post(unlink_url)
        self.assertEqual(resp.status_code, 200)
        self.doc.refresh_from_db()
        self.assertIsNone(getattr(self.doc, fk_field))

    def test_property_link_unlink(self):
        self._test_link_unlink("property")

    def test_investment_link_unlink(self):
        self._test_link_unlink("investment")

    def test_loan_link_unlink(self):
        self._test_link_unlink("loan")

    def test_lease_link_unlink(self):
        self._test_link_unlink("lease")

    def test_policy_link_unlink(self):
        self._test_link_unlink("policy")

    def test_vehicle_link_unlink(self):
        self._test_link_unlink("vehicle")

    def test_aircraft_link_unlink(self):
        self._test_link_unlink("aircraft")

    def test_stakeholder_link_unlink(self):
        self._test_link_unlink("stakeholder")

    def test_legal_matter_link_unlink(self):
        self._test_link_unlink("legal_matter")


class EntityDetailDocumentSectionTest(TestCase):
    """Test that entity detail pages include the Documents section."""

    def setUp(self):
        self.doc = Document.objects.create(title="Visible Doc", category="deed")

    def test_property_detail_shows_documents(self):
        from assets.models import RealEstate
        prop = RealEstate.objects.create(name="Doc Property")
        self.doc.related_property = prop
        self.doc.save()
        resp = self.client.get(reverse("assets:realestate_detail", args=[prop.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Visible Doc")
        self.assertContains(resp, "Documents")

    def test_investment_detail_shows_documents(self):
        from assets.models import Investment
        inv = Investment.objects.create(name="Doc Investment")
        self.doc.related_investment = inv
        self.doc.save()
        resp = self.client.get(reverse("assets:investment_detail", args=[inv.pk]))
        self.assertContains(resp, "Visible Doc")

    def test_stakeholder_detail_shows_documents(self):
        from stakeholders.models import Stakeholder
        sh = Stakeholder.objects.create(name="Doc Stakeholder")
        self.doc.related_stakeholder = sh
        self.doc.save()
        resp = self.client.get(reverse("stakeholders:detail", args=[sh.pk]))
        self.assertContains(resp, "Visible Doc")

    def test_legal_detail_shows_documents(self):
        from legal.models import LegalMatter
        matter = LegalMatter.objects.create(title="Doc Legal")
        self.doc.related_legal_matter = matter
        self.doc.save()
        resp = self.client.get(reverse("legal:detail", args=[matter.pk]))
        self.assertContains(resp, "Visible Doc")


# ---- Google Drive Setup Form ----


class GoogleDriveSetupFormTest(TestCase):
    def test_form_valid_full(self):
        form = GoogleDriveSetupForm(data={
            "client_id": "test-client-id.apps.googleusercontent.com",
            "client_secret": "test-secret-123",
            "api_key": "AIzaSyTest123",
        })
        self.assertTrue(form.is_valid())

    def test_form_valid_no_api_key(self):
        form = GoogleDriveSetupForm(data={
            "client_id": "test-client-id.apps.googleusercontent.com",
            "client_secret": "test-secret-123",
        })
        self.assertTrue(form.is_valid())

    def test_preserves_existing_secret(self):
        """Leaving client_secret blank preserves the stored value."""
        settings = GoogleDriveSettings.objects.create(
            pk=1, client_id="existing-id", client_secret="existing-secret",
        )
        form = GoogleDriveSetupForm(
            data={"client_id": "new-id", "client_secret": "", "api_key": ""},
            instance=settings,
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["client_secret"], "existing-secret")

    def test_preserves_existing_api_key(self):
        settings = GoogleDriveSettings.objects.create(
            pk=1, client_id="id", api_key="existing-key",
        )
        form = GoogleDriveSetupForm(
            data={"client_id": "id", "client_secret": "", "api_key": ""},
            instance=settings,
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["api_key"], "existing-key")


# ---- Google Drive Settings View ----


class GDriveSettingsViewTest(TestCase):
    def test_settings_page_loads(self):
        resp = self.client.get(reverse("documents:gdrive_settings"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Google Drive Settings")
        self.assertContains(resp, "Not connected")

    def test_settings_page_shows_connected(self):
        GoogleDriveSettings.objects.create(
            pk=1, is_connected=True, refresh_token="tok",
            connected_email="user@example.com",
        )
        resp = self.client.get(reverse("documents:gdrive_settings"))
        self.assertContains(resp, "Connected to Google Drive")
        self.assertContains(resp, "user@example.com")

    def test_save_credentials(self):
        resp = self.client.post(reverse("documents:gdrive_settings"), {
            "client_id": "my-client-id",
            "client_secret": "my-secret",
            "api_key": "my-api-key",
        })
        self.assertEqual(resp.status_code, 302)
        s = GoogleDriveSettings.load()
        self.assertEqual(s.client_id, "my-client-id")
        self.assertEqual(s.client_secret, "my-secret")
        self.assertEqual(s.api_key, "my-api-key")

    def test_settings_shows_connect_button_when_configured(self):
        GoogleDriveSettings.objects.create(
            pk=1, client_id="cid", client_secret="csec",
        )
        resp = self.client.get(reverse("documents:gdrive_settings"))
        self.assertContains(resp, "Connect Google Drive")

    def test_settings_hides_connect_button_when_already_connected(self):
        GoogleDriveSettings.objects.create(
            pk=1, client_id="cid", client_secret="csec",
            is_connected=True, refresh_token="tok",
        )
        resp = self.client.get(reverse("documents:gdrive_settings"))
        # The authorize URL should not appear as a link when already connected
        self.assertNotContains(resp, "/documents/gdrive/authorize/")

    def test_setup_instructions_shows_callback_url(self):
        resp = self.client.get(reverse("documents:gdrive_settings"))
        self.assertContains(resp, "/documents/gdrive/callback/")


# ---- Google Drive Authorize View ----


class GDriveAuthorizeViewTest(TestCase):
    def test_authorize_without_creds_redirects(self):
        """Should redirect to settings with error if not configured."""
        resp = self.client.get(reverse("documents:gdrive_authorize"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("gdrive/settings", resp.url)

    @patch("documents.gdrive.get_authorization_url")
    def test_authorize_redirects_to_google(self, mock_auth):
        GoogleDriveSettings.objects.create(
            pk=1, client_id="cid", client_secret="csec",
        )
        mock_auth.return_value = ("https://accounts.google.com/o/oauth2/auth?foo=bar", "test-state", "verifier123")
        resp = self.client.get(reverse("documents:gdrive_authorize"))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith("https://accounts.google.com/"))

    @patch("documents.gdrive.get_authorization_url")
    def test_authorize_stores_state_in_session(self, mock_auth):
        GoogleDriveSettings.objects.create(
            pk=1, client_id="cid", client_secret="csec",
        )
        mock_auth.return_value = ("https://accounts.google.com/auth", "my-state", "verifier456")
        self.client.get(reverse("documents:gdrive_authorize"))
        self.assertEqual(self.client.session.get("gdrive_oauth_state"), "my-state")


# ---- Google Drive Callback View ----


class GDriveCallbackViewTest(TestCase):
    def test_callback_with_error_param(self):
        resp = self.client.get(reverse("documents:gdrive_callback"), {"error": "access_denied"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("gdrive/settings", resp.url)

    def test_callback_without_code(self):
        resp = self.client.get(reverse("documents:gdrive_callback"))
        self.assertEqual(resp.status_code, 302)

    @patch("documents.gdrive.exchange_code")
    def test_callback_success(self, mock_exchange):
        mock_exchange.return_value = "user@example.com"
        resp = self.client.get(reverse("documents:gdrive_callback"), {"code": "auth-code-123"})
        self.assertEqual(resp.status_code, 302)
        mock_exchange.assert_called_once()

    @patch("documents.gdrive.exchange_code")
    def test_callback_exchange_failure(self, mock_exchange):
        mock_exchange.side_effect = Exception("Token exchange failed")
        resp = self.client.get(reverse("documents:gdrive_callback"), {"code": "bad-code"})
        self.assertEqual(resp.status_code, 302)


# ---- Google Drive Disconnect View ----


class GDriveDisconnectViewTest(TestCase):
    def test_disconnect_requires_post(self):
        resp = self.client.get(reverse("documents:gdrive_disconnect"))
        self.assertEqual(resp.status_code, 405)

    @patch("documents.gdrive.revoke_credentials")
    def test_disconnect_clears_connection(self, mock_revoke):
        mock_revoke.return_value = True
        resp = self.client.post(reverse("documents:gdrive_disconnect"))
        self.assertEqual(resp.status_code, 302)
        mock_revoke.assert_called_once()


# ---- Google Drive Verify View ----


class GDriveVerifyViewTest(TestCase):
    @patch("documents.gdrive.verify_connection")
    def test_verify_success(self, mock_verify):
        mock_verify.return_value = (True, "user@example.com")
        resp = self.client.get(reverse("documents:gdrive_verify"))
        self.assertEqual(resp.status_code, 302)

    @patch("documents.gdrive.verify_connection")
    def test_verify_failure(self, mock_verify):
        mock_verify.return_value = (False, "Token expired")
        resp = self.client.get(reverse("documents:gdrive_verify"))
        self.assertEqual(resp.status_code, 302)


# ---- gdrive.py module tests ----


class GDriveModuleTest(TestCase):
    def test_is_configured_false(self):
        from documents import gdrive
        self.assertFalse(gdrive.is_configured())

    def test_is_configured_true(self):
        from documents import gdrive
        GoogleDriveSettings.objects.create(pk=1, client_id="cid", client_secret="csec")
        self.assertTrue(gdrive.is_configured())

    def test_is_connected_false(self):
        from documents import gdrive
        self.assertFalse(gdrive.is_connected())

    def test_is_connected_true(self):
        from documents import gdrive
        GoogleDriveSettings.objects.create(
            pk=1, is_connected=True, refresh_token="tok",
            client_id="cid", client_secret="csec",
        )
        self.assertTrue(gdrive.is_connected())

    def test_get_authorization_url_raises_without_creds(self):
        from documents import gdrive
        with self.assertRaises(ValueError):
            gdrive.get_authorization_url("http://localhost/callback")

    @patch("documents.gdrive._build_flow")
    def test_get_authorization_url_success(self, mock_flow_builder):
        from documents import gdrive
        GoogleDriveSettings.objects.create(pk=1, client_id="cid", client_secret="csec")
        mock_flow = MagicMock()
        mock_flow.authorization_url.return_value = ("https://google.com/auth", "state123")
        mock_flow.code_verifier = "cv789"
        mock_flow_builder.return_value = mock_flow
        url, state, code_verifier = gdrive.get_authorization_url("http://localhost/callback")
        self.assertEqual(url, "https://google.com/auth")
        self.assertEqual(state, "state123")
        self.assertEqual(code_verifier, "cv789")

    def test_get_credentials_returns_none_when_not_connected(self):
        from documents import gdrive
        self.assertIsNone(gdrive.get_credentials())

    def test_get_service_returns_none_when_not_connected(self):
        from documents import gdrive
        self.assertIsNone(gdrive.get_service())

    def test_get_file_metadata_returns_none_when_not_connected(self):
        from documents import gdrive
        self.assertIsNone(gdrive.get_file_metadata("abc123"))

    def test_verify_connection_not_connected(self):
        from documents import gdrive
        ok, msg = gdrive.verify_connection()
        self.assertFalse(ok)
        self.assertEqual(msg, "Not connected")

    def test_get_picker_access_token_returns_none(self):
        from documents import gdrive
        self.assertIsNone(gdrive.get_picker_access_token())

    def test_revoke_credentials_clears_fields(self):
        from documents import gdrive
        GoogleDriveSettings.objects.create(
            pk=1, is_connected=True, access_token="at",
            refresh_token="rt", connected_email="e@x.com",
        )
        gdrive.revoke_credentials()
        s = GoogleDriveSettings.load()
        self.assertFalse(s.is_connected)
        self.assertEqual(s.access_token, "")
        self.assertEqual(s.refresh_token, "")
        self.assertEqual(s.connected_email, "")

    @patch("documents.gdrive.get_credentials")
    @patch("documents.gdrive.get_service")
    def test_verify_connection_success(self, mock_service, mock_creds):
        from documents import gdrive
        GoogleDriveSettings.objects.create(
            pk=1, is_connected=True, refresh_token="tok",
            connected_email="user@x.com",
        )
        mock_svc = MagicMock()
        mock_svc.files.return_value.list.return_value.execute.return_value = {"files": []}
        mock_service.return_value = mock_svc
        ok, detail = gdrive.verify_connection()
        self.assertTrue(ok)
        self.assertEqual(detail, "user@x.com")


# ---- Settings Hub shows Google Drive card ----


class SettingsHubGDriveCardTest(TestCase):
    def test_settings_hub_has_gdrive_link(self):
        resp = self.client.get(reverse("dashboard:settings_hub"))
        self.assertContains(resp, "Google Drive")
        self.assertContains(resp, "/documents/gdrive/settings/")


# ---- Milestone 3: Picker Token Endpoint ----


class PickerTokenEndpointTest(TestCase):
    def test_not_connected_returns_403(self):
        resp = self.client.get(reverse("documents:picker_token"))
        self.assertEqual(resp.status_code, 403)
        data = resp.json()
        self.assertIn("error", data)

    @patch("documents.gdrive.is_connected", return_value=True)
    @patch("documents.gdrive.get_credentials")
    def test_success(self, mock_creds, mock_connected):
        creds = mock_creds.return_value
        creds.token = "mock-token-123"
        creds.scopes = {"openid", "https://www.googleapis.com/auth/drive.readonly"}
        creds.expired = False
        creds.expiry = None
        GoogleDriveSettings.objects.create(
            pk=1, is_connected=True, refresh_token="tok",
            client_id="123-abc.apps.googleusercontent.com",
            client_secret="sec", project_number="123",
        )
        resp = self.client.get(reverse("documents:picker_token"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["access_token"], "mock-token-123")

    @patch("documents.gdrive.is_connected", return_value=True)
    @patch("documents.gdrive.get_credentials", return_value=None)
    def test_token_refresh_failure(self, mock_creds, mock_connected):
        resp = self.client.get(reverse("documents:picker_token"))
        self.assertEqual(resp.status_code, 500)
        data = resp.json()
        self.assertIn("error", data)


# ---- Milestone 3: Picker Context in Create/Edit Views ----


class PickerFormContextTest(TestCase):
    def test_create_form_no_drive(self):
        """Picker button should not appear when Drive is not connected."""
        resp = self.client.get(reverse("documents:create"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "gdrive-picker-btn")
        self.assertNotContains(resp, "apis.google.com")

    def test_create_form_drive_connected_no_api_key(self):
        """Picker hidden when API key is missing even if connected."""
        GoogleDriveSettings.objects.create(
            pk=1, is_connected=True, refresh_token="tok",
            client_id="cid", client_secret="csec", api_key="",
        )
        resp = self.client.get(reverse("documents:create"))
        self.assertNotContains(resp, "gdrive-picker-btn")

    def test_create_form_drive_connected_with_api_key(self):
        """Picker button appears when fully connected."""
        GoogleDriveSettings.objects.create(
            pk=1, is_connected=True, refresh_token="tok",
            client_id="cid", client_secret="csec", api_key="akey",
        )
        resp = self.client.get(reverse("documents:create"))
        self.assertContains(resp, "gdrive-picker-btn")
        self.assertContains(resp, "apis.google.com")
        self.assertContains(resp, "gdrive-picker.")
        self.assertContains(resp, "gdrive-config")

    def test_edit_form_drive_connected(self):
        doc = Document.objects.create(title="Test")
        GoogleDriveSettings.objects.create(
            pk=1, is_connected=True, refresh_token="tok",
            client_id="cid", client_secret="csec", api_key="akey",
        )
        resp = self.client.get(reverse("documents:edit", args=[doc.pk]))
        self.assertContains(resp, "gdrive-picker-btn")

    def test_edit_form_shows_existing_drive_data(self):
        """Hidden fields should contain existing Drive metadata on edit."""
        doc = Document.objects.create(
            title="Picker Doc",
            gdrive_file_id="abc123",
            gdrive_mime_type="application/pdf",
            gdrive_file_name="contract.pdf",
        )
        resp = self.client.get(reverse("documents:edit", args=[doc.pk]))
        self.assertContains(resp, 'value="abc123"')
        self.assertContains(resp, 'value="application/pdf"')
        self.assertContains(resp, 'value="contract.pdf"')

    def test_url_help_text_changes_with_drive(self):
        """URL help text should change when Drive is connected."""
        GoogleDriveSettings.objects.create(
            pk=1, is_connected=True, refresh_token="tok",
            client_id="cid", client_secret="csec", api_key="akey",
        )
        resp = self.client.get(reverse("documents:create"))
        self.assertContains(resp, "Auto-filled by Picker, or paste manually")

    def test_url_help_text_without_drive(self):
        resp = self.client.get(reverse("documents:create"))
        self.assertContains(resp, "Paste a Google Drive sharing link")


# ---- Milestone 3: Form accepts Picker metadata ----


class DocumentFormPickerFieldsTest(TestCase):
    def test_form_accepts_gdrive_metadata(self):
        form = DocumentForm(data={
            "title": "Picker Doc",
            "gdrive_url": "https://drive.google.com/file/d/abc123/view",
            "gdrive_file_id": "abc123",
            "gdrive_mime_type": "application/pdf",
            "gdrive_file_name": "contract.pdf",
        })
        self.assertTrue(form.is_valid())
        doc = form.save()
        self.assertEqual(doc.gdrive_file_id, "abc123")
        self.assertEqual(doc.gdrive_mime_type, "application/pdf")
        self.assertEqual(doc.gdrive_file_name, "contract.pdf")

    def test_form_renders_hidden_inputs(self):
        form = DocumentForm()
        html = str(form)
        self.assertIn('type="hidden"', html)
        self.assertIn('id_gdrive_file_id', html)
        self.assertIn('id_gdrive_mime_type', html)
        self.assertIn('id_gdrive_file_name', html)

    def test_form_valid_without_gdrive_fields(self):
        """Form remains valid when no Drive metadata is provided."""
        form = DocumentForm(data={"title": "No Drive Doc"})
        self.assertTrue(form.is_valid())


# ===========================================================================
# Text extraction (extract.py)
# ===========================================================================


def _build_pdf_bytes(paragraphs):
    """Build a tiny PDF with reportlab for use in tests."""
    from io import BytesIO
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    buf = BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    pdf.build([Paragraph(p, styles["Normal"]) for p in paragraphs])
    return buf.getvalue()


def _build_docx_bytes(paragraphs):
    from io import BytesIO
    import docx
    document = docx.Document()
    for p in paragraphs:
        document.add_paragraph(p)
    buf = BytesIO()
    document.save(buf)
    return buf.getvalue()


def _build_xlsx_bytes(sheets):
    """sheets is dict of {sheet_name: [[cell, cell], [cell, cell]]}."""
    from io import BytesIO
    from openpyxl import Workbook
    wb = Workbook()
    # Workbook ships with one default sheet; replace it
    default = wb.active
    wb.remove(default)
    for name, rows in sheets.items():
        ws = wb.create_sheet(title=name)
        for row in rows:
            ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


class ExtractPdfTests(TestCase):
    def test_extract_pdf_returns_paragraph_text(self):
        from documents import extract
        pdf_bytes = _build_pdf_bytes([
            "Tenant: Tom Driscoll",
            "Monthly rent: $4,250",
            "Pet policy: dogs under 30 lbs allowed",
        ])
        result = extract._extract_by_mime(pdf_bytes, "application/pdf")
        self.assertNotIn("error", result)
        self.assertIn("Tom Driscoll", result["text"])
        self.assertIn("$4,250", result["text"])
        self.assertFalse(result["truncated"])
        self.assertIsNone(result["warning"])

    def test_extract_pdf_empty_returns_warning(self):
        from documents import extract
        # Bytes that pypdf can open but with no text content
        empty_pdf = _build_pdf_bytes([" "])
        result = extract._extract_by_mime(empty_pdf, "application/pdf")
        self.assertNotIn("error", result)
        self.assertEqual(result["text"].strip(), "")
        self.assertIsNotNone(result["warning"])
        self.assertIn("scanned", result["warning"].lower())

    def test_extract_pdf_malformed_does_not_crash(self):
        from documents import extract
        result = extract._extract_by_mime(b"not a pdf", "application/pdf")
        self.assertNotIn("error", result)
        self.assertEqual(result["text"].strip(), "")
        self.assertIsNotNone(result["warning"])


class ExtractDocxTests(TestCase):
    def test_extract_docx_returns_paragraph_text(self):
        from documents import extract
        data = _build_docx_bytes([
            "Engagement letter for Helen Park",
            "Hourly rate: $650",
            "Retainer: $5,000",
        ])
        result = extract._extract_by_mime(data, extract.DOCX_MIME)
        self.assertNotIn("error", result)
        self.assertIn("Helen Park", result["text"])
        self.assertIn("$650", result["text"])


class ExtractXlsxTests(TestCase):
    def test_extract_xlsx_emits_sheet_headers_and_rows(self):
        from documents import extract
        data = _build_xlsx_bytes({
            "Capital Calls": [
                ["Date", "Amount", "Fund"],
                ["2026-01-15", 50000, "Redwood II"],
                ["2026-04-15", 75000, "Redwood II"],
            ],
            "Distributions": [
                ["Date", "Amount"],
                ["2026-03-01", 12000],
            ],
        })
        result = extract._extract_by_mime(data, extract.XLSX_MIME)
        self.assertNotIn("error", result)
        self.assertIn("=== Sheet: Capital Calls ===", result["text"])
        self.assertIn("Redwood II", result["text"])
        self.assertIn("=== Sheet: Distributions ===", result["text"])
        self.assertIn("12000", result["text"])

    def test_extract_xlsx_truncates_at_row_cap(self):
        from documents import extract
        rows = [["row", i] for i in range(extract.MAX_XLSX_ROWS_PER_SHEET + 50)]
        data = _build_xlsx_bytes({"Big": rows})
        result = extract._extract_by_mime(data, extract.XLSX_MIME)
        self.assertIn("truncated after", result["text"])


class ExtractPlaintextTests(TestCase):
    def test_extract_plaintext(self):
        from documents import extract
        result = extract._extract_by_mime(
            b"line one\nline two\n", "text/plain",
        )
        self.assertNotIn("error", result)
        self.assertIn("line one", result["text"])

    def test_extract_csv(self):
        from documents import extract
        result = extract._extract_by_mime(
            b"name,amount\nTom,4250\n", "text/csv",
        )
        self.assertNotIn("error", result)
        self.assertIn("Tom", result["text"])

    def test_extract_unknown_mime_returns_error(self):
        from documents import extract
        result = extract._extract_by_mime(
            b"\x00\x01\x02", "application/octet-stream",
        )
        self.assertIn("error", result)
        self.assertIn("Unsupported mime type", result["error"])


class ExtractTruncationTests(TestCase):
    def test_long_text_is_truncated_to_max_chars(self):
        from documents import extract
        big = ("hello " * 20_000).encode()  # 120k chars
        result = extract._extract_by_mime(big, "text/plain")
        self.assertTrue(result["truncated"])
        self.assertLessEqual(len(result["text"]), extract.MAX_CHARS + 100)
        self.assertIn("[truncated", result["text"])

    def test_short_text_not_truncated(self):
        from documents import extract
        result = extract._extract_by_mime(b"hello", "text/plain")
        self.assertFalse(result["truncated"])
        self.assertNotIn("[truncated", result["text"])


class ExtractDriveDispatchTests(TestCase):
    """Verify extract_text_from_drive routes Google-native vs binary correctly."""

    def test_google_doc_routes_to_export(self):
        from documents import extract
        with patch("documents.gdrive.export_file_bytes", return_value=b"hello world") as mock_export, \
             patch("documents.gdrive.download_file_bytes") as mock_download:
            result = extract.extract_text_from_drive(
                "fake_id", "application/vnd.google-apps.document",
            )
            mock_export.assert_called_once_with("fake_id", "text/plain")
            mock_download.assert_not_called()
            self.assertIn("hello world", result["text"])

    def test_google_sheet_exports_as_csv(self):
        from documents import extract
        with patch("documents.gdrive.export_file_bytes", return_value=b"a,b\n1,2\n") as mock_export:
            extract.extract_text_from_drive(
                "fake_id", "application/vnd.google-apps.spreadsheet",
            )
            mock_export.assert_called_once_with("fake_id", "text/csv")

    def test_pdf_routes_to_download(self):
        from documents import extract
        pdf_bytes = _build_pdf_bytes(["readable pdf body"])
        with patch("documents.gdrive.download_file_bytes", return_value=pdf_bytes) as mock_download:
            result = extract.extract_text_from_drive(
                "fake_id", "application/pdf",
            )
            mock_download.assert_called_once_with("fake_id")
            self.assertIn("readable pdf body", result["text"])

    def test_export_failure_returns_error(self):
        from documents import extract
        with patch("documents.gdrive.export_file_bytes", return_value=None):
            result = extract.extract_text_from_drive(
                "fake_id", "application/vnd.google-apps.document",
            )
            self.assertIn("error", result)

    def test_download_failure_returns_error(self):
        from documents import extract
        with patch("documents.gdrive.download_file_bytes", return_value=None):
            result = extract.extract_text_from_drive(
                "fake_id", "application/pdf",
            )
            self.assertIn("error", result)

    def test_missing_mime_type_returns_error(self):
        from documents import extract
        result = extract.extract_text_from_drive("fake_id", "")
        self.assertIn("error", result)


class ExtractLocalFileTests(TestCase):
    def test_local_pdf(self):
        import os
        import tempfile
        from documents import extract
        pdf_bytes = _build_pdf_bytes(["local file body"])
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            path = f.name
        try:
            result = extract.extract_text_from_local(path)
            self.assertNotIn("error", result)
            self.assertIn("local file body", result["text"])
        finally:
            os.unlink(path)

    def test_local_missing_file(self):
        from documents import extract
        result = extract.extract_text_from_local("/nonexistent/path.pdf")
        self.assertIn("error", result)

    def test_local_unsupported_extension(self):
        import tempfile
        from documents import extract
        with tempfile.NamedTemporaryFile(suffix=".doc", delete=False) as f:
            f.write(b"old word format")
            path = f.name
        try:
            result = extract.extract_text_from_local(path)
            self.assertIn("error", result)
            self.assertIn("Unsupported file extension", result["error"])
        finally:
            import os
            os.unlink(path)
