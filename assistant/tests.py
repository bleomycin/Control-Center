import json
import time

from unittest.mock import MagicMock, patch

from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from .client import (
    MAX_TOOL_ITERATIONS,
    _result_summary,
    _stream_message_impl,
    _tool_summary,
    _with_heartbeat,
)
from .models import AssistantSettings, ChatMessage, ChatSession
from .registry import build_registry, get_field_info, get_model, serialize_instance
from .tools import delete_record, get_record, list_models, query, search, summarize


class ChatSessionModelTests(TestCase):
    def test_create_session(self):
        session = ChatSession.objects.create(title="Test Chat")
        self.assertEqual(str(session), "Test Chat")

    def test_default_title(self):
        session = ChatSession.objects.create()
        self.assertEqual(session.title, "New Chat")

    def test_get_absolute_url(self):
        session = ChatSession.objects.create()
        self.assertEqual(
            session.get_absolute_url(),
            reverse("assistant:chat_session", kwargs={"session_id": session.pk}),
        )


class ChatMessageModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.session = ChatSession.objects.create(title="Test")
        cls.message = ChatMessage.objects.create(
            session=cls.session,
            role="user",
            content="Hello",
        )

    def test_create_message(self):
        self.assertEqual(self.message.role, "user")
        self.assertEqual(self.message.content, "Hello")

    def test_str(self):
        self.assertEqual(str(self.message), "user: Hello")

    def test_ordering(self):
        msg2 = ChatMessage.objects.create(
            session=self.session, role="assistant", content="Hi"
        )
        messages = list(self.session.messages.all())
        self.assertEqual(messages[0], self.message)
        self.assertEqual(messages[1], msg2)

    def test_cascade_delete(self):
        session_pk = self.session.pk
        self.session.delete()
        self.assertFalse(ChatMessage.objects.filter(session_id=session_pk).exists())


class RegistryTests(TestCase):
    def test_build_registry(self):
        build_registry()
        from .registry import MODEL_REGISTRY
        self.assertIn("Stakeholder", MODEL_REGISTRY)
        self.assertIn("Task", MODEL_REGISTRY)
        self.assertIn("LegalMatter", MODEL_REGISTRY)

    def test_get_model_valid(self):
        model = get_model("Stakeholder")
        self.assertEqual(model.__name__, "Stakeholder")

    def test_get_model_case_insensitive(self):
        model = get_model("stakeholder")
        self.assertEqual(model.__name__, "Stakeholder")

    def test_get_model_invalid(self):
        with self.assertRaises(ValueError):
            get_model("NonexistentModel")

    def test_serialize_instance(self):
        from stakeholders.models import Stakeholder
        s = Stakeholder.objects.create(name="Test Person", entity_type="contact")
        data = serialize_instance(s)
        self.assertEqual(data["__model__"], "Stakeholder")
        self.assertEqual(data["name"], "Test Person")
        self.assertIn("__str__", data)
        self.assertIn("__url__", data)

    def test_get_field_info(self):
        from stakeholders.models import Stakeholder
        fields = get_field_info(Stakeholder)
        field_names = [f["name"] for f in fields]
        self.assertIn("name", field_names)
        self.assertIn("entity_type", field_names)


class CredentialModelExclusionTests(TestCase):
    """Phase 1 security: credential/settings models must be unreachable
    through the tool registry — an injected instruction in ingested email or
    document content must not be able to read or write them."""

    def test_excluded_models_not_in_registry(self):
        build_registry()
        from .registry import EXCLUDED_MODELS, MODEL_REGISTRY
        for name in EXCLUDED_MODELS:
            self.assertNotIn(name, MODEL_REGISTRY)
            self.assertNotIn(name.lower(), MODEL_REGISTRY)

    def test_get_record_excluded_model_is_unknown(self):
        with self.assertRaisesMessage(ValueError, "Unknown model"):
            get_record("GoogleDriveSettings", 1)

    def test_query_excluded_model_is_unknown(self):
        with self.assertRaisesMessage(ValueError, "Unknown model"):
            query("EmailSettings")

    def test_write_tools_reject_excluded_models(self):
        from .tools import update_record
        with self.assertRaisesMessage(ValueError, "Unknown model"):
            create_record_helper("CalendarFeedSettings", {"token": "x"})
        with self.assertRaisesMessage(ValueError, "Unknown model"):
            update_record("BackupSettings", 1, {"enabled": False})
        with self.assertRaisesMessage(ValueError, "Unknown model"):
            delete_record("GoogleDriveSettings", 1)

    def test_unknown_model_error_does_not_advertise_excluded_models(self):
        # The message echoes the requested name; the "Available models" list
        # it offers must not mention any excluded model.
        from .registry import EXCLUDED_MODELS
        with self.assertRaises(ValueError) as ctx:
            get_model("NonexistentModel")
        available = str(ctx.exception).split("Available models:")[1]
        for name in EXCLUDED_MODELS:
            self.assertNotIn(name, available)

    def test_schema_text_excludes_credential_models(self):
        from .registry import get_schema_text
        schema = get_schema_text()
        self.assertNotIn("GoogleDriveSettings", schema)
        self.assertNotIn("EmailSettings", schema)
        self.assertNotIn("CalendarFeedSettings", schema)
        self.assertNotIn("BackupSettings", schema)

    def test_list_models_excludes_credential_models(self):
        from .registry import EXCLUDED_MODELS
        result = list_models()
        names = {m["name"] for m in result["models"]}
        self.assertFalse(EXCLUDED_MODELS & names)

    def test_serialize_instance_redacts_secret_fields(self):
        # Defense in depth: even if a credential-bearing model reached the
        # serializer, secret-named fields must not survive serialization.
        settings = AssistantSettings(owner_name="X", api_key="sk-ant-secret-value")
        data = serialize_instance(settings, expand_relations=False)
        self.assertEqual(data["api_key"], "[redacted]")
        self.assertNotIn("sk-ant-secret-value", json.dumps(data))

    def test_query_fields_path_redacts_secret_fields(self):
        from .registry import _is_secret_field
        for name in ("password", "token", "client_secret", "api_key",
                     "refresh_token", "access_token", "token_expiry"):
            self.assertTrue(_is_secret_field(name), name)
        for name in ("name", "title", "notes_text", "due_date"):
            self.assertFalse(_is_secret_field(name), name)

    def test_query_fields_path_redacts_end_to_end(self):
        # The fields=[...] path bypasses serialize_instance (raw getattr);
        # a secret-named field must come back redacted, never a value.
        from tasks.models import Task
        Task.objects.create(title="T", status="not_started",
                            priority="high", direction="personal")
        result = query("Task", fields=["title", "api_key"])
        self.assertEqual(result["count"], 1)
        row = result["results"][0]
        self.assertEqual(row["title"], "T")
        self.assertEqual(row["api_key"], "[redacted]")


class MarkdownSanitizationTests(TestCase):
    """Phase 1 security: render_markdown must strip raw HTML (stored XSS
    from assistant-quoted email/document content) while normal markdown
    output survives intact."""

    def _render(self, text):
        from dashboard.templatetags.markdown_filter import render_markdown
        return render_markdown(text)

    def test_script_stripped(self):
        html = self._render("<script>alert(1)</script>safe text")
        self.assertNotIn("<script", html)
        self.assertNotIn("alert(1)", html)
        self.assertIn("safe text", html)

    def test_img_onerror_stripped(self):
        html = self._render("<img src=x onerror=alert(1)>")
        self.assertNotIn("onerror", html)
        self.assertNotIn("<img", html)

    def test_svg_onload_stripped(self):
        html = self._render("<svg onload=alert(1)></svg>")
        self.assertNotIn("onload", html)
        self.assertNotIn("<svg", html)

    def test_iframe_stripped(self):
        html = self._render('<iframe src="https://evil.example/"></iframe>')
        self.assertNotIn("<iframe", html)

    def test_event_handler_on_allowed_tag_stripped(self):
        html = self._render('<p onclick="alert(1)">hi</p>')
        self.assertNotIn("onclick", html)
        self.assertIn("hi", html)

    def test_javascript_href_neutralized(self):
        html = self._render("[click](javascript:alert(1))")
        self.assertNotIn("javascript:", html)

    def test_markdown_table_survives(self):
        html = self._render("| a | b |\n|---|---|\n| 1 | 2 |")
        for fragment in ("<table>", "<thead>", "<tbody>", "<th>a</th>", "<td>1</td>"):
            self.assertIn(fragment, html)

    def test_root_relative_link_survives(self):
        html = self._render("[Thomas](/stakeholders/1/)")
        self.assertIn('href="/stakeholders/1/"', html)

    def test_code_fence_survives(self):
        html = self._render("```python\nprint(1)\n```")
        self.assertIn("<pre><code", html)
        self.assertIn("language-python", html)
        self.assertIn("print(1)", html)

    def test_bold_list_and_heading_survive(self):
        html = self._render("## Title\n\n**bold**\n\n- one\n- two")
        self.assertIn("<h2>Title</h2>", html)
        self.assertIn("<strong>bold</strong>", html)
        self.assertIn("<ul>", html)


class ToolTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from stakeholders.models import Stakeholder
        from tasks.models import Task
        from django.utils import timezone

        cls.stakeholder = Stakeholder.objects.create(
            name="Marcus Reed", entity_type="attorney"
        )
        cls.task = Task.objects.create(
            title="File motion",
            status="not_started",
            priority="high",
            direction="personal",
            due_date=timezone.localdate(),
        )

    def test_search(self):
        result = search("Marcus")
        self.assertGreater(result["count"], 0)
        self.assertEqual(result["results"][0]["model"], "Stakeholder")

    def test_search_with_model_filter(self):
        result = search("Marcus", models=["Stakeholder"])
        self.assertGreater(result["count"], 0)

    def test_query_basic(self):
        result = query("Stakeholder", filters={"name__icontains": "Marcus"})
        self.assertEqual(result["count"], 1)

    def test_query_no_filters(self):
        result = query("Stakeholder")
        self.assertGreaterEqual(result["count"], 1)

    def test_query_invalid_model(self):
        with self.assertRaises(ValueError):
            query("FakeModel")

    def test_get_record(self):
        result = get_record("Stakeholder", self.stakeholder.pk)
        self.assertEqual(result["name"], "Marcus Reed")
        self.assertEqual(result["__model__"], "Stakeholder")

    def test_get_record_not_found(self):
        result = get_record("Stakeholder", 99999)
        self.assertIn("error", result)

    def test_create_record_dry_run(self):
        result = create_record_helper(
            "Stakeholder",
            {"name": "New Person", "entity_type": "contact"},
            dry_run=True,
        )
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["action"], "create")
        # Verify nothing was created
        from stakeholders.models import Stakeholder
        self.assertFalse(Stakeholder.objects.filter(name="New Person").exists())

    def test_create_record_execute(self):
        result = create_record_helper(
            "Stakeholder",
            {"name": "Created Person", "entity_type": "contact"},
            dry_run=False,
        )
        self.assertEqual(result["action"], "created")
        from stakeholders.models import Stakeholder
        self.assertTrue(Stakeholder.objects.filter(name="Created Person").exists())

    def test_delete_record_dry_run(self):
        from stakeholders.models import Stakeholder
        s = Stakeholder.objects.create(name="To Delete", entity_type="contact")
        result = delete_record("Stakeholder", s.pk, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertTrue(Stakeholder.objects.filter(pk=s.pk).exists())

    def test_list_models(self):
        result = list_models()
        self.assertGreater(result["count"], 0)
        model_names = [m["name"] for m in result["models"]]
        self.assertIn("Stakeholder", model_names)
        self.assertIn("Task", model_names)

    def test_summarize(self):
        result = summarize()
        self.assertIn("Stakeholder_count", result)
        self.assertIn("Task_count", result)


class SearchWordSplitTests(TestCase):
    """Tests for word-splitting and primary/secondary field prioritization."""

    @classmethod
    def setUpTestData(cls):
        from stakeholders.models import Stakeholder

        # The actual person — "Stan Gribble" is NOT a contiguous substring
        cls.stanley = Stakeholder.objects.create(
            name="Stanley W. Gribble", entity_type="contact",
        )
        # Entities that merely reference Stan in their notes
        cls.attorney = Stakeholder.objects.create(
            name="Ed Hanley", entity_type="attorney",
            notes_text="Long-term real estate attorney for Stan Gribble",
        )
        cls.accountant = Stakeholder.objects.create(
            name="Bill Buckner", entity_type="advisor",
            notes_text="CPA for Stan Gribble trust accounting",
        )

    def test_multiword_search_matches_noncontiguous(self):
        """'Stan Gribble' must match 'Stanley W. Gribble'."""
        result = search("Stan Gribble", models=["Stakeholder"])
        names = [r["str"] for r in result["results"]]
        self.assertIn("Stanley W. Gribble", names)

    def test_name_match_before_notes_match(self):
        """Name matches must appear before notes_text matches."""
        result = search("Stan Gribble", models=["Stakeholder"])
        self.assertGreaterEqual(result["count"], 1)
        # Stanley (name match) must be first
        self.assertEqual(result["results"][0]["str"], "Stanley W. Gribble")

    def test_single_word_still_works(self):
        """Single-word search should still work as before."""
        result = search("Hanley", models=["Stakeholder"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0]["str"], "Ed Hanley")

    def test_notes_matches_still_returned(self):
        """Notes-text matches should still appear, just after name matches."""
        result = search("Stan Gribble", models=["Stakeholder"])
        names = [r["str"] for r in result["results"]]
        self.assertIn("Ed Hanley", names)
        self.assertIn("Bill Buckner", names)
        # But they come after the name match
        stanley_idx = names.index("Stanley W. Gribble")
        for other in ["Ed Hanley", "Bill Buckner"]:
            self.assertGreater(names.index(other), stanley_idx)

    def test_empty_query(self):
        """Empty query should return no results."""
        result = search("", models=["Stakeholder"])
        self.assertEqual(result["count"], 0)


def create_record_helper(model, data, dry_run=True):
    """Helper to avoid name collision with tools.create_record import."""
    from .tools import create_record
    return create_record(model, data, dry_run=dry_run)


class TitleGenerationTests(TestCase):
    def _mock_response(self, text):
        """Create a mock Anthropic response with the given text."""
        mock_block = MagicMock()
        mock_block.text = text
        mock_resp = MagicMock()
        mock_resp.content = [mock_block]
        return mock_resp

    def test_generate_title_success(self):
        """AI title generation returns a clean title."""
        from .client import _generate_title

        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._mock_response(
            "Henderson Escrow Update"
        )

        title = _generate_title(mock_client, "I spoke with Thomas", "Summary...")
        self.assertEqual(title, "Henderson Escrow Update")

    def test_generate_title_strips_quotes(self):
        """Title with surrounding quotes is cleaned."""
        from .client import _generate_title

        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._mock_response(
            '"Henderson Escrow Update"'
        )

        title = _generate_title(mock_client, "test", "test")
        self.assertEqual(title, "Henderson Escrow Update")

    def test_generate_title_strips_single_quotes(self):
        """Title with single quotes is cleaned."""
        from .client import _generate_title

        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._mock_response(
            "'Task Review Summary'"
        )

        title = _generate_title(mock_client, "test", "test")
        self.assertEqual(title, "Task Review Summary")

    def test_generate_title_fallback_on_error(self):
        """Falls back to truncated user text on API error."""
        from .client import _generate_title

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API error")

        title = _generate_title(mock_client, "Short question", "test")
        self.assertEqual(title, "Short question")

    def test_generate_title_fallback_truncates_long_text(self):
        """Fallback truncates long user text with ellipsis."""
        from .client import _generate_title

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API error")
        long_text = "A" * 100

        title = _generate_title(mock_client, long_text, "test")
        self.assertEqual(len(title), 60)
        self.assertTrue(title.endswith("..."))

    def test_generate_title_truncates_long_ai_title(self):
        """AI-generated titles over 80 chars are truncated."""
        from .client import _generate_title

        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._mock_response("B" * 100)

        title = _generate_title(mock_client, "test", "test")
        self.assertEqual(len(title), 80)

    def test_generate_title_empty_response_falls_back(self):
        """Empty AI response falls back to user text."""
        from .client import _generate_title

        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._mock_response("")

        title = _generate_title(mock_client, "My question here", "test")
        self.assertEqual(title, "My question here")

    def test_generate_title_uses_haiku_model(self):
        """Title generation uses the fast haiku model."""
        from .client import TITLE_MODEL, _generate_title

        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._mock_response("Test Title")

        _generate_title(mock_client, "test", "test")

        call_kwargs = mock_client.messages.create.call_args[1]
        self.assertEqual(call_kwargs["model"], TITLE_MODEL)
        self.assertEqual(call_kwargs["max_tokens"], 20)

    def test_generate_title_truncates_inputs(self):
        """Long user/assistant text is truncated in the prompt."""
        from .client import _generate_title

        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._mock_response("Title")

        long_user = "X" * 500
        long_assistant = "Y" * 500
        _generate_title(mock_client, long_user, long_assistant)

        call_kwargs = mock_client.messages.create.call_args[1]
        prompt = call_kwargs["messages"][0]["content"]
        # Each input should be truncated to 200 chars
        self.assertNotIn("X" * 201, prompt)
        self.assertNotIn("Y" * 201, prompt)


class ViewTests(TestCase):
    def test_chat_page_creates_session(self):
        response = self.client.get(reverse("assistant:chat"))
        self.assertEqual(response.status_code, 302)  # Redirects to new session

    def test_chat_page_with_session(self):
        session = ChatSession.objects.create()
        response = self.client.get(
            reverse("assistant:chat_session", kwargs={"session_id": session.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ask anything")

    def test_new_session(self):
        response = self.client.post(reverse("assistant:new_session"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ChatSession.objects.exists())

    def test_new_session_get_rejected(self):
        """State-changing views must not be reachable by GET (prefetch/CSRF
        bypass) — Phase 5 Defect D."""
        response = self.client.get(reverse("assistant:new_session"))
        self.assertEqual(response.status_code, 405)
        self.assertFalse(ChatSession.objects.exists())

    def test_delete_session(self):
        session = ChatSession.objects.create()
        response = self.client.post(
            reverse("assistant:delete_session", kwargs={"session_id": session.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ChatSession.objects.filter(pk=session.pk).exists())

    def test_rename_session(self):
        session = ChatSession.objects.create(title="Old Title")
        self.client.post(
            reverse("assistant:rename_session", kwargs={"session_id": session.pk}),
            {"title": "New Title"},
        )
        session.refresh_from_db()
        self.assertEqual(session.title, "New Title")

    def test_session_list(self):
        ChatSession.objects.create(title="Chat 1")
        ChatSession.objects.create(title="Chat 2")
        response = self.client.get(reverse("assistant:session_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chat 1")
        self.assertContains(response, "Chat 2")

    def test_send_without_api_key(self):
        """Without API key, an error message is persisted. Calls the client
        function directly — the unguarded /send/ view and its route were
        removed in Phase 5 (Defect D); send_message stays for management
        commands and tests."""
        from .client import send_message

        session = ChatSession.objects.create()
        send_message(session, "Hello")
        self.assertTrue(
            ChatMessage.objects.filter(
                session=session, role="assistant", content__icontains="not configured"
            ).exists()
        )

    def test_send_route_removed(self):
        """The dead unguarded /send/ endpoint is gone (Phase 5 Defect D)."""
        from django.urls import NoReverseMatch

        with self.assertRaises(NoReverseMatch):
            reverse("assistant:send", kwargs={"session_id": 1})

    def test_chat_page_loads_marked_js(self):
        """Chat page includes the marked.js library for markdown rendering."""
        session = ChatSession.objects.create()
        response = self.client.get(
            reverse("assistant:chat_session", kwargs={"session_id": session.pk})
        )
        self.assertEqual(response.status_code, 200)
        # marked.umd.js and assistant-chat.js are loaded globally via base.html
        self.assertContains(response, "marked.umd")
        self.assertContains(response, "assistant-chat")

    def test_prune_history(self):
        session = ChatSession.objects.create()
        for i in range(30):
            ChatMessage.objects.create(
                session=session, role="user", content=f"Message {i}"
            )
        self.client.post(
            reverse("assistant:prune", kwargs={"session_id": session.pk}),
            {"keep": 10},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(session.messages.count(), 10)


class RetryMessageTests(TestCase):
    def setUp(self):
        self.session = ChatSession.objects.create(title="Test")
        self.user_msg1 = ChatMessage.objects.create(
            session=self.session, role="user", content="Hello"
        )
        self.asst_msg1 = ChatMessage.objects.create(
            session=self.session, role="assistant", content="Hi there"
        )
        self.user_msg2 = ChatMessage.objects.create(
            session=self.session, role="user", content="Follow up"
        )
        self.asst_msg2 = ChatMessage.objects.create(
            session=self.session, role="assistant", content="Sure thing"
        )

    def test_retry_deletes_from_assistant_message_onward(self):
        response = self.client.post(
            reverse("assistant:retry_message", kwargs={
                "session_id": self.session.pk,
                "message_id": self.asst_msg1.pk,
            })
        )
        self.assertEqual(response.status_code, 200)
        remaining = list(self.session.messages.values_list("pk", flat=True))
        self.assertEqual(remaining, [self.user_msg1.pk])

    def test_retry_returns_preceding_user_text(self):
        response = self.client.post(
            reverse("assistant:retry_message", kwargs={
                "session_id": self.session.pk,
                "message_id": self.asst_msg1.pk,
            })
        )
        data = response.json()
        self.assertEqual(data["user_text"], "Hello")
        self.assertEqual(data["action"], "retry")

    def test_retry_wrong_session(self):
        other_session = ChatSession.objects.create(title="Other")
        response = self.client.post(
            reverse("assistant:retry_message", kwargs={
                "session_id": other_session.pk,
                "message_id": self.asst_msg1.pk,
            })
        )
        self.assertEqual(response.status_code, 404)

    def test_retry_on_user_message(self):
        response = self.client.post(
            reverse("assistant:retry_message", kwargs={
                "session_id": self.session.pk,
                "message_id": self.user_msg1.pk,
            })
        )
        self.assertEqual(response.status_code, 400)

    def test_retry_get_method(self):
        response = self.client.get(
            reverse("assistant:retry_message", kwargs={
                "session_id": self.session.pk,
                "message_id": self.asst_msg1.pk,
            })
        )
        self.assertEqual(response.status_code, 405)

    def test_retry_tool_turn_finds_real_user_text(self):
        """Regression (found in the Phase 2 bug-check, fixed in Phase 5): for
        a tool-using turn the 'preceding user message' used to match the
        tool_result row (role=user, content="") — Retry then deleted the
        answer and re-asked NOTHING. The lookup must skip tool rows and the
        deletion must remove the whole turn (tool pairs included) so the
        resend regenerates from a clean boundary."""
        user_msg3 = ChatMessage.objects.create(
            session=self.session, role="user", content="Tool question"
        )
        tool_use = ChatMessage.objects.create(
            session=self.session, role="assistant", content="",
            tool_data=[{"type": "tool_use", "id": "tu_1", "name": "query",
                        "input": {}}],
        )
        tool_result = ChatMessage.objects.create(
            session=self.session, role="user", content="",
            tool_data=[{"type": "tool_result", "tool_use_id": "tu_1",
                        "content": "{}"}],
        )
        answer = ChatMessage.objects.create(
            session=self.session, role="assistant", content="Tool answer"
        )

        response = self.client.post(
            reverse("assistant:retry_message", kwargs={
                "session_id": self.session.pk,
                "message_id": answer.pk,
            })
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user_text"], "Tool question")
        remaining = list(self.session.messages.values_list("pk", flat=True))
        # Everything after the real user question is gone — tool pair included.
        self.assertEqual(remaining, [
            self.user_msg1.pk, self.asst_msg1.pk,
            self.user_msg2.pk, self.asst_msg2.pk,
            user_msg3.pk,
        ])


class EditMessageTests(TestCase):
    def setUp(self):
        self.session = ChatSession.objects.create(title="Test")
        self.user_msg1 = ChatMessage.objects.create(
            session=self.session, role="user", content="First question"
        )
        self.asst_msg1 = ChatMessage.objects.create(
            session=self.session, role="assistant", content="First answer"
        )
        self.user_msg2 = ChatMessage.objects.create(
            session=self.session, role="user", content="Second question"
        )
        self.asst_msg2 = ChatMessage.objects.create(
            session=self.session, role="assistant", content="Second answer"
        )

    def test_edit_deletes_from_user_message_onward(self):
        response = self.client.post(
            reverse("assistant:edit_message", kwargs={
                "session_id": self.session.pk,
                "message_id": self.user_msg2.pk,
            })
        )
        self.assertEqual(response.status_code, 200)
        remaining = list(self.session.messages.values_list("pk", flat=True))
        self.assertEqual(remaining, [self.user_msg1.pk, self.asst_msg1.pk])

    def test_edit_returns_message_text(self):
        response = self.client.post(
            reverse("assistant:edit_message", kwargs={
                "session_id": self.session.pk,
                "message_id": self.user_msg2.pk,
            })
        )
        data = response.json()
        self.assertEqual(data["user_text"], "Second question")
        self.assertEqual(data["action"], "edit")

    def test_edit_wrong_session(self):
        other_session = ChatSession.objects.create(title="Other")
        response = self.client.post(
            reverse("assistant:edit_message", kwargs={
                "session_id": other_session.pk,
                "message_id": self.user_msg1.pk,
            })
        )
        self.assertEqual(response.status_code, 404)

    def test_edit_on_assistant_message(self):
        response = self.client.post(
            reverse("assistant:edit_message", kwargs={
                "session_id": self.session.pk,
                "message_id": self.asst_msg1.pk,
            })
        )
        self.assertEqual(response.status_code, 400)

    def test_edit_get_method(self):
        response = self.client.get(
            reverse("assistant:edit_message", kwargs={
                "session_id": self.session.pk,
                "message_id": self.user_msg1.pk,
            })
        )
        self.assertEqual(response.status_code, 405)


class ToolSummaryTests(TestCase):
    def test_search_summary(self):
        self.assertEqual(_tool_summary("search", {"query": "Thomas"}), '"Thomas"')

    def test_search_summary_with_models(self):
        result = _tool_summary("search", {"query": "Thomas", "models": ["Stakeholder"]})
        self.assertIn('"Thomas"', result)
        self.assertIn("models=", result)

    def test_search_summary_truncates_long_query(self):
        result = _tool_summary("search", {"query": "A" * 80})
        # Query truncated to 40 chars
        self.assertNotIn("A" * 41, result)
        self.assertIn("A" * 40, result)

    def test_query_summary(self):
        self.assertEqual(_tool_summary("query", {"model": "Task"}), "Task")

    def test_query_summary_with_filters(self):
        result = _tool_summary("query", {
            "model": "Task",
            "filters": {"status": "active", "priority": "high", "extra": "ignored"},
        })
        self.assertIn("Task", result)
        self.assertIn("status=active", result)
        # Only first 2 filters
        self.assertNotIn("extra=ignored", result)

    def test_get_record_summary(self):
        self.assertEqual(
            _tool_summary("get_record", {"model": "Stakeholder", "id": 42}),
            "Stakeholder #42",
        )

    def test_create_record_summary_dry_run(self):
        result = _tool_summary("create_record", {"model": "Task", "dry_run": True})
        self.assertIn("Task", result)
        self.assertIn("dry_run", result)

    def test_list_models_summary_empty(self):
        self.assertEqual(_tool_summary("list_models", {}), "")

    def test_summarize_summary_empty(self):
        self.assertEqual(_tool_summary("summarize", {}), "")

    def test_update_record_summary(self):
        result = _tool_summary("update_record", {"model": "Task", "id": 5})
        self.assertEqual(result, "Task #5")

    def test_delete_record_summary(self):
        result = _tool_summary("delete_record", {"model": "Note", "id": 10})
        self.assertEqual(result, "Note #10")

    def test_read_email_summary(self):
        result = _tool_summary("read_email", {"id": 7})
        self.assertEqual(result, "EmailLink #7")


class ResultSummaryTests(TestCase):
    def test_search_results(self):
        self.assertEqual(
            _result_summary("search", {}, {"count": 3, "results": []}),
            "3 result(s)",
        )

    def test_query_results(self):
        self.assertEqual(
            _result_summary("query", {}, {"count": 5, "records": []}),
            "5 record(s)",
        )

    def test_get_record_found(self):
        self.assertEqual(
            _result_summary("get_record", {}, {"name": "Thomas"}),
            "found",
        )

    def test_error_result(self):
        self.assertEqual(
            _result_summary("search", {}, {"error": "Model not found"}),
            "Model not found",
        )

    def test_create_dry_run(self):
        self.assertEqual(
            _result_summary("create_record", {}, {"dry_run": True, "action": "create"}),
            "preview ready",
        )

    def test_create_execute(self):
        self.assertEqual(
            _result_summary("create_record", {}, {"action": "created"}),
            "created",
        )

    def test_update_dry_run(self):
        self.assertEqual(
            _result_summary("update_record", {}, {"dry_run": True}),
            "preview ready",
        )

    def test_update_execute(self):
        self.assertEqual(
            _result_summary("update_record", {}, {"action": "updated"}),
            "updated",
        )

    def test_delete_result(self):
        self.assertEqual(
            _result_summary("delete_record", {}, {"action": "deleted"}),
            "deleted",
        )

    def test_list_models_result(self):
        self.assertEqual(
            _result_summary("list_models", {}, {"count": 12, "models": []}),
            "12 models",
        )

    def test_summarize_result(self):
        self.assertEqual(
            _result_summary("summarize", {}, {"Task_count": 5}),
            "done",
        )


class ReminderPolicyTests(TestCase):
    """Tests for the schema fix and server-side reminder policy."""

    def test_schema_datetimefield_reported_as_datetime(self):
        from assistant.registry import build_registry, get_field_info
        from tasks.models import Task
        build_registry()
        info = {f["name"]: f for f in get_field_info(Task)}
        self.assertEqual(info["reminder_date"]["type"], "datetime")
        self.assertNotIn("created_at", info)  # auto_now_add, must be skipped
        self.assertNotIn("updated_at", info)  # auto_now, must be skipped

    def test_create_record_meeting_strips_reminder_date(self):
        result = create_record_helper(
            "Task",
            {"title": "M", "task_type": "meeting", "direction": "personal",
             "due_date": "2026-04-23", "due_time": "15:30",
             "reminder_date": "2026-04-23T00:00:00"},
            dry_run=True,
        )
        self.assertNotIn("reminder_date", result["data"])

    def test_create_record_meeting_strips_reminder_date_execute(self):
        from tasks.models import Task
        result = create_record_helper(
            "Task",
            {"title": "M2", "task_type": "meeting", "direction": "personal",
             "due_date": "2026-04-23", "due_time": "15:30",
             "reminder_date": "2026-04-23T00:00:00"},
            dry_run=False,
        )
        t = Task.objects.get(pk=result["record"]["__pk__"])
        self.assertIsNone(t.reminder_date)

    def test_create_record_non_meeting_autocomputes_reminder_date(self):
        from assistant.models import AssistantSettings
        from tasks.models import Task
        from django.utils import timezone
        from datetime import datetime, timedelta
        s = AssistantSettings.load()
        s.default_reminder_minutes = 1440
        s.save()
        result = create_record_helper(
            "Task",
            {"title": "T", "task_type": "one_time", "direction": "personal",
             "due_date": "2026-04-23", "due_time": "15:30"},
            dry_run=False,
        )
        t = Task.objects.get(pk=result["record"]["__pk__"])
        expected = timezone.make_aware(
            datetime(2026, 4, 23, 15, 30), timezone.get_current_timezone()
        ) - timedelta(minutes=1440)
        self.assertEqual(t.reminder_date, expected)

    def test_create_record_non_meeting_respects_explicit_reminder(self):
        from tasks.models import Task
        from django.utils import timezone
        result = create_record_helper(
            "Task",
            {"title": "T2", "task_type": "one_time", "direction": "personal",
             "due_date": "2026-04-23", "due_time": "15:30",
             "reminder_date": "2026-04-21T09:00:00"},
            dry_run=False,
        )
        t = Task.objects.get(pk=result["record"]["__pk__"])
        # The LLM sends a naive ISO datetime; Django stores it as UTC.
        # Assert on localtime to match user intent (9 AM local, not UTC).
        local = timezone.localtime(t.reminder_date)
        self.assertEqual(local.day, 21)
        self.assertEqual(local.hour, 9)

    def test_update_record_meeting_strips_reminder_date(self):
        from tasks.models import Task
        from assistant.tools import update_record
        task = Task.objects.create(
            title="Existing Meeting", task_type="meeting",
            direction="personal", due_date="2026-04-23",
        )
        result = update_record(
            "Task", task.pk,
            {"due_time": "15:30", "reminder_date": "2026-04-23T14:30:00"},
            dry_run=False,
        )
        task.refresh_from_db()
        self.assertIsNone(task.reminder_date)

    def test_apply_reminder_policy_leaves_data_json_safe(self):
        # Regression for the ChatMessage.tool_data save crash: the mutated dict
        # is aliased into block.input which is stored verbatim in tool_data
        # (JSONField) and re-sent as Anthropic message history. A raw datetime
        # breaks both paths. Input path mirrors create_record/update_record,
        # which is how the streaming loop reaches this function.
        import json
        from assistant.models import AssistantSettings
        from assistant.tools import _apply_reminder_policy
        from tasks.models import Task
        s = AssistantSettings.load()
        s.default_reminder_minutes = 1440
        s.save()
        data = {
            "title": "Import CVS documents",
            "task_type": "one_time",
            "direction": "personal",
            "due_date": "2026-04-21",
            "due_time": "20:00",
        }
        _apply_reminder_policy(Task, data)
        self.assertIn("reminder_date", data)
        json.dumps(data)

    def test_create_record_dry_run_preview_is_json_safe(self):
        # The live bug surface: the dry_run=True branch is what the streaming
        # loop hits first, and assistant_content[N]["input"]["data"] is the
        # very dict mutated by the policy. Exercise that exact flow.
        import json
        from assistant.models import AssistantSettings
        from assistant.tools import create_record
        s = AssistantSettings.load()
        s.default_reminder_minutes = 1440
        s.save()
        tool_input = {
            "model": "Task",
            "data": {
                "title": "Import CVS documents",
                "task_type": "one_time",
                "direction": "personal",
                "due_date": "2026-04-21",
                "due_time": "20:00",
            },
        }
        create_record(**tool_input)  # dry_run defaults to True
        json.dumps(tool_input)

    def test_turn_context_omits_auto_reminder_when_disabled(self):
        # When default_reminder_minutes=0 the server writes no reminder, so
        # the context must not claim "the server sets reminder_date to 0
        # minutes before". The meeting bullet stays — that's unconditional.
        # (Phase 3 moved the reminder policy from the system prompt into the
        # per-turn context block — see _build_turn_context.)
        from assistant.client import _build_turn_context
        from assistant.models import AssistantSettings
        s = AssistantSettings.load()
        s.default_reminder_minutes = 0
        s.save()
        stats_text = _build_turn_context()
        self.assertNotIn("0 minutes before the due datetime", stats_text)
        self.assertNotIn("server sets", stats_text)
        self.assertIn("task_type='meeting'", stats_text)

    def test_turn_context_includes_auto_reminder_when_enabled(self):
        from assistant.client import _build_turn_context
        from assistant.models import AssistantSettings
        s = AssistantSettings.load()
        s.default_reminder_minutes = 1440
        s.save()
        stats_text = _build_turn_context()
        self.assertIn("1440 minutes before the due datetime", stats_text)


class DrawerViewTests(TestCase):
    def test_drawer_session_returns_most_recent(self):
        s1 = ChatSession.objects.create(title="Old")
        s2 = ChatSession.objects.create(title="New")
        response = self.client.post(reverse("assistant:drawer_session"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Most recent by updated_at (s2 was created last)
        self.assertEqual(data["session_id"], s2.pk)
        self.assertEqual(data["title"], "New")

    def test_drawer_session_creates_when_none(self):
        self.assertEqual(ChatSession.objects.count(), 0)
        response = self.client.post(reverse("assistant:drawer_session"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ChatSession.objects.count(), 1)

    def test_drawer_session_get_rejected(self):
        """Both branches can create a session, so the endpoint is POST-only
        (Phase 5 Defect D)."""
        response = self.client.get(reverse("assistant:drawer_session"))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(ChatSession.objects.count(), 0)

    def test_drawer_messages_returns_html(self):
        session = ChatSession.objects.create()
        ChatMessage.objects.create(session=session, role="user", content="Hello")
        ChatMessage.objects.create(session=session, role="assistant", content="Hi")
        response = self.client.get(
            reverse("assistant:drawer_messages", kwargs={"session_id": session.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hello")
        self.assertContains(response, "Hi")

    def test_drawer_messages_excludes_empty(self):
        session = ChatSession.objects.create()
        ChatMessage.objects.create(session=session, role="assistant", content="", tool_data=[{"type": "tool_use"}])
        ChatMessage.objects.create(session=session, role="assistant", content="Real answer")
        response = self.client.get(
            reverse("assistant:drawer_messages", kwargs={"session_id": session.pk})
        )
        self.assertContains(response, "Real answer")
        self.assertNotContains(response, "tool_use")

    def test_drawer_messages_404_bad_session(self):
        response = self.client.get(
            reverse("assistant:drawer_messages", kwargs={"session_id": 999})
        )
        self.assertEqual(response.status_code, 404)


class DisplayContentTests(TestCase):
    def test_strips_context_prefix(self):
        msg = ChatMessage(role="user", content='[Context: viewing Task #1 "Test"]\nWhat is this?')
        self.assertEqual(msg.display_content, "What is this?")

    def test_no_context_unchanged(self):
        msg = ChatMessage(role="user", content="Hello there")
        self.assertEqual(msg.display_content, "Hello there")

    def test_empty_content(self):
        msg = ChatMessage(role="user", content="")
        self.assertEqual(msg.display_content, "")

    def test_context_only_message(self):
        msg = ChatMessage(role="user", content='[Context: viewing Stakeholder #5 "Bob"]')
        self.assertEqual(msg.display_content, "")

    def test_strips_attached_email(self):
        content = (
            '[AttachedEmail:{"thread_id":"abc","subject":"Test"}]\n'
            'Subject: Test\nThread: 1 message(s)\n'
            '[/AttachedEmail]\n'
            'Create a task from this email'
        )
        msg = ChatMessage(role="user", content=content)
        self.assertEqual(msg.display_content, "Create a task from this email")

    def test_attached_email_with_context(self):
        content = (
            '[AttachedEmail:{"thread_id":"abc","subject":"Test"}]\n'
            'Email body here\n'
            '[/AttachedEmail]\n'
            '[Context: viewing Task #1 "Test"]\nWhat about this?'
        )
        msg = ChatMessage(role="user", content=content)
        self.assertEqual(msg.display_content, "What about this?")

    def test_attached_email_no_user_text(self):
        content = (
            '[AttachedEmail:{"thread_id":"abc","subject":"Test"}]\n'
            'Email body\n'
            '[/AttachedEmail]'
        )
        msg = ChatMessage(role="user", content=content)
        self.assertEqual(msg.display_content, "")

    def test_attached_email_missing_end_marker(self):
        content = '[AttachedEmail:{"thread_id":"abc"}]\nSome text without closing marker'
        msg = ChatMessage(role="user", content=content)
        # No end marker found, returns content as-is
        self.assertEqual(msg.display_content, content)


# ============================================================
# Tests for optimization changes (A1-A4, B1-B4, C2)
# ============================================================


class TemperaturePassthroughTests(TestCase):
    """A1: Verify temperature from settings is passed to API calls."""

    def test_send_message_passes_temperature(self):
        """Non-streaming path passes temperature to messages.create()."""
        from .client import send_message
        from .models import AssistantSettings

        settings = AssistantSettings.load()
        settings.api_key = "sk-test-key"
        settings.temperature = 0.3
        settings.save()

        session = ChatSession.objects.create()

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            # Simulate a text-only response (no tool use)
            mock_block = MagicMock()
            mock_block.type = "text"
            mock_block.text = "Hello!"
            mock_response = MagicMock()
            mock_response.content = [mock_block]
            mock_client.messages.create.return_value = mock_response

            send_message(session, "Hi")

            # First call is the main message; second is title generation
            first_call_kwargs = mock_client.messages.create.call_args_list[0][1]
            self.assertEqual(first_call_kwargs["temperature"], 0.3)

    def test_send_message_temperature_zero(self):
        """Default temperature of 0.0 is passed correctly (not omitted)."""
        from .client import send_message
        from .models import AssistantSettings

        settings = AssistantSettings.load()
        settings.api_key = "sk-test-key"
        settings.temperature = 0.0
        settings.save()

        session = ChatSession.objects.create()

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_block = MagicMock()
            mock_block.type = "text"
            mock_block.text = "Hi"
            mock_response = MagicMock()
            mock_response.content = [mock_block]
            mock_client.messages.create.return_value = mock_response

            send_message(session, "Hi")

            first_call_kwargs = mock_client.messages.create.call_args_list[0][1]
            self.assertEqual(first_call_kwargs["temperature"], 0.0)


class _FakeTruncatedStream:
    """Stand-in MessageStream returning a text-only response that stopped at the
    max_tokens output cap (stop_reason == "max_tokens")."""

    request_id = "req_test"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter([])  # text delivered via get_final_message, not deltas

    def get_final_message(self):
        block = MagicMock()
        block.type = "text"
        block.text = "partial answer"
        resp = MagicMock()
        resp.model = "claude-opus-4-8"
        resp.content = [block]
        resp.stop_reason = "max_tokens"
        return resp


class Opus48MigrationTests(TestCase):
    """Safety nets for the Opus 4.6 -> 4.8 'max' mode migration."""

    def test_max_mode_targets_opus_4_8(self):
        """'max' mode is pinned to claude-opus-4-8 with adaptive thinking."""
        from .client import MODE_CONFIGS

        self.assertEqual(MODE_CONFIGS["max"]["model"], "claude-opus-4-8")
        # Adaptive thinking must stay: it is what keeps temperature off the
        # request, and Opus 4.8 rejects the temperature sampling param.
        # display must stay "summarized": Opus 4.7+ default to "omitted",
        # which streams no thinking_delta events — the SSE keepalive (and the
        # client's 90s watchdog) depend on those deltas.
        self.assertEqual(
            MODE_CONFIGS["max"]["thinking"],
            {"type": "adaptive", "display": "summarized"},
        )

    def test_thinking_modes_pin_display(self):
        """Every thinking mode pins display explicitly, so a future model
        swap can never silently inherit a new "omitted" default and starve
        the SSE stream of keepalive-driving thinking_delta events."""
        from .client import MODE_CONFIGS

        for mode_name, config in MODE_CONFIGS.items():
            if "thinking" not in config:
                continue
            with self.subTest(mode=mode_name):
                self.assertEqual(
                    config["thinking"].get("display"), "summarized"
                )

    def test_nonstreaming_max_mode_clamps_max_tokens(self):
        """The non-streaming path clamps max_tokens under the SDK threshold
        (the SDK raises ValueError above 21,333 tokens: "Streaming is
        required for operations that may take longer than 10 minutes")."""
        from .client import send_message, NONSTREAMING_MAX_TOKENS
        from .models import AssistantSettings

        self.assertLessEqual(NONSTREAMING_MAX_TOKENS, 21_333)

        settings = AssistantSettings.load()
        settings.api_key = "sk-test-key"
        settings.save()

        session = ChatSession.objects.create()

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_block = MagicMock()
            mock_block.type = "text"
            mock_block.text = "Hi"
            mock_response = MagicMock()
            mock_response.content = [mock_block]
            mock_response.stop_reason = "end_turn"
            mock_client.messages.create.return_value = mock_response

            send_message(session, "Hi", mode="max")

            first_call_kwargs = mock_client.messages.create.call_args_list[0][1]
            self.assertEqual(
                first_call_kwargs["max_tokens"], NONSTREAMING_MAX_TOKENS
            )

    def test_model_accepts_temperature_allowlist(self):
        """Only allowlisted (temperature-capable) models accept temperature."""
        from .client import _model_accepts_temperature

        # Current-gen temperature-capable models (incl. dated ids via prefix).
        self.assertTrue(_model_accepts_temperature("claude-sonnet-4-6"))
        self.assertTrue(_model_accepts_temperature("claude-haiku-4-5-20251001"))
        self.assertTrue(_model_accepts_temperature("claude-opus-4-6"))
        # Opus 4.7+ removed sampling params -> must fail safe (no temperature).
        self.assertFalse(_model_accepts_temperature("claude-opus-4-8"))
        self.assertFalse(_model_accepts_temperature("claude-opus-4-7"))
        # Unknown / empty -> fail safe.
        self.assertFalse(_model_accepts_temperature("claude-future-9"))
        self.assertFalse(_model_accepts_temperature(""))

    def test_fast_mode_omits_temperature_for_opus_4_8(self):
        """Fast mode on a 4.7+ model must NOT send temperature (would 400)."""
        from .client import send_message
        from .models import AssistantSettings

        settings = AssistantSettings.load()
        settings.api_key = "sk-test-key"
        settings.model = "claude-opus-4-8"
        settings.temperature = 0.3
        settings.save()

        session = ChatSession.objects.create()

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_block = MagicMock()
            mock_block.type = "text"
            mock_block.text = "Hi"
            mock_response = MagicMock()
            mock_response.content = [mock_block]
            mock_response.stop_reason = "end_turn"
            mock_client.messages.create.return_value = mock_response

            send_message(session, "Hi")  # default mode="fast"

            first_call_kwargs = mock_client.messages.create.call_args_list[0][1]
            self.assertNotIn("temperature", first_call_kwargs)

    def test_truncated_response_appends_notice(self):
        """A max_tokens stop_reason appends a visible truncation notice (non-stream)."""
        from .client import send_message, TRUNCATION_NOTICE
        from .models import AssistantSettings

        settings = AssistantSettings.load()
        settings.api_key = "sk-test-key"
        settings.save()

        session = ChatSession.objects.create()

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_block = MagicMock()
            mock_block.type = "text"
            mock_block.text = "A long answer cut off"
            mock_response = MagicMock()
            mock_response.content = [mock_block]
            mock_response.stop_reason = "max_tokens"
            mock_client.messages.create.return_value = mock_response

            new_messages = send_message(session, "Hi")

            final = new_messages[-1]
            self.assertEqual(final.role, "assistant")
            self.assertTrue(final.content.startswith("A long answer cut off"))
            self.assertIn(TRUNCATION_NOTICE.strip(), final.content)

    def test_stream_truncation_emits_notice(self):
        """Streaming 'max' path surfaces truncation live and persists it."""
        from .client import _stream_message_impl, TRUNCATION_NOTICE
        from .models import AssistantSettings, ChatMessage

        settings = AssistantSettings.load()
        settings.api_key = "sk-test-key"
        settings.save()

        # Non-default title so the loop skips AI title generation.
        session = ChatSession.objects.create(title="Existing chat")

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = _FakeTruncatedStream()

            frames = list(_stream_message_impl(session, "hello", mode="max"))

        joined = "".join(frames)
        self.assertIn("truncated", joined.lower())
        self.assertTrue(frames[-1].startswith("event: done\ndata: "))
        saved = (
            ChatMessage.objects.filter(session=session, role="assistant")
            .exclude(content="")
            .last()
        )
        self.assertIsNotNone(saved)
        self.assertIn(TRUNCATION_NOTICE.strip(), saved.content)


class ToolDefinitionCacheTests(TestCase):
    """Tools carry NO cache_control of their own: the system prompt is
    frozen, so the entry written at the system breakpoint covers the
    tools+system prefix as one unit. The freed slot funds the
    previous-turn anchor marker (budget: system + anchor + [-2] +
    top-level tail = 4)."""

    def test_no_tool_has_cache_control(self):
        from .tools import TOOL_DEFINITIONS
        for tool in TOOL_DEFINITIONS:
            self.assertNotIn(
                "cache_control", tool,
                f"Tool '{tool['name']}' must not carry cache_control — it"
                " would overspend the 4-breakpoint budget and 400 every"
                " request (see _apply_message_cache_marker)."
            )


class GetClientAndModelTests(TestCase):
    """A3: Verify _get_client_and_model helper works correctly."""

    def test_returns_client_and_model(self):
        from .client import _get_client_and_model
        from .models import AssistantSettings

        settings = AssistantSettings.load()
        settings.api_key = "sk-test-key-12345"
        settings.model = "claude-opus-4-6"
        settings.save()

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            MockClient.return_value = MagicMock()
            client, model_name = _get_client_and_model()
            self.assertEqual(model_name, "claude-opus-4-6")
            MockClient.assert_called_once_with(api_key="sk-test-key-12345", max_retries=5)

    def test_raises_without_api_key(self):
        from .client import _get_client_and_model
        from .models import AssistantSettings

        settings = AssistantSettings.load()
        settings.api_key = ""
        settings.save()

        # Also clear env var
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError):
                _get_client_and_model()

    def test_uses_default_model_when_blank(self):
        from .client import DEFAULT_MODEL, _get_client_and_model
        from .models import AssistantSettings

        settings = AssistantSettings.load()
        settings.api_key = "sk-test-key"
        settings.model = ""
        settings.save()

        with patch("assistant.client.anthropic.Anthropic"):
            _, model_name = _get_client_and_model()
            self.assertEqual(model_name, DEFAULT_MODEL)


class WarmCacheEndpointTests(TestCase):
    """A3: Verify warm_cache view works (previously crashed with ImportError)."""

    def test_warm_cache_import_succeeds(self):
        """The import in warm_cache should not crash."""
        from .client import _get_client_and_model  # noqa: F401
        # If we get here, the import works

    def test_warm_cache_endpoint_returns_ok(self):
        from .models import AssistantSettings

        settings = AssistantSettings.load()
        settings.api_key = "sk-test-key"
        settings.save()

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_block = MagicMock()
            mock_block.type = "text"
            mock_block.text = ""
            mock_resp = MagicMock()
            mock_resp.content = [mock_block]
            mock_client.messages.create.return_value = mock_resp

            response = self.client.post(reverse("assistant:warm_cache"))
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["ok"])

    def test_warm_cache_swallows_errors(self):
        """Even if API call fails, endpoint returns ok."""
        from .models import AssistantSettings
        settings = AssistantSettings.load()
        settings.api_key = ""
        settings.save()

        response = self.client.post(reverse("assistant:warm_cache"))
        self.assertEqual(response.status_code, 200)


class CacheBreakpointTests(TestCase):
    """Phase 3 defect A + hardening: message-level cache markers.

    The tail breakpoint is the top-level ``cache_control`` kwarg every API
    call passes (asserted in Phase3RequestConstructionTests). On top of
    that, _apply_message_cache_marker places at most TWO message-level
    markers: one on the second-to-last message (tool-loop lookback bridge /
    next-turn anchor writer), one on the PREVIOUS turn's user message (the
    distance-zero read of the anchor entry — after a tool-heavy turn the
    anchor sits beyond the 20-block lookback of the [-2] marker).
    """

    @staticmethod
    def _count_markers(result):
        markers = []
        for idx, msg in enumerate(result):
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "cache_control" in block:
                        markers.append(idx)
        return markers

    def test_penultimate_tool_message_gets_marker(self):
        from .client import _build_api_messages
        from .models import ChatMessage

        session = ChatSession.objects.create()
        ChatMessage.objects.create(session=session, role="user", content="Start")
        for i in range(19):
            role = "assistant" if i % 2 == 0 else "user"
            if role == "assistant":
                tool_data = [{"type": "tool_use", "id": f"tu_{i}", "name": "search", "input": {}}]
            else:
                tool_data = [{"type": "tool_result", "tool_use_id": f"tu_{i-1}", "content": "ok"}]
            ChatMessage.objects.create(session=session, role=role, content="", tool_data=tool_data)

        result = _build_api_messages(session.messages.all())

        markers = self._count_markers(result)
        self.assertEqual(markers, [len(result) - 2])
        marked_block = result[-2]["content"][-1]
        self.assertIn(marked_block.get("type"), ("tool_use", "tool_result"))

    def test_text_conversation_marks_penultimate_as_wrapped_block(self):
        """String messages carry the marker as an equivalent single text
        block — the API hashes both forms identically (verified live), so
        the wrap can't invalidate the prefix when the marker moves."""
        from .client import _build_api_messages
        from .models import ChatMessage

        session = ChatSession.objects.create()
        for i in range(20):
            role = "user" if i % 2 == 0 else "assistant"
            ChatMessage.objects.create(session=session, role=role, content=f"Msg {i}")

        result = _build_api_messages(session.messages.all())

        # Two markers: the previous-turn user anchor (Msg 16) + [-2] (Msg 18).
        self.assertEqual(self._count_markers(result), [16, len(result) - 2])
        wrapped = result[-2]["content"]
        self.assertEqual(wrapped[0]["type"], "text")
        self.assertEqual(wrapped[0]["text"], "Msg 18")
        anchor = result[16]["content"]
        self.assertEqual(anchor[0]["type"], "text")
        self.assertEqual(anchor[0]["text"], "Msg 16")
        # Every unmarked message keeps its plain-string shape.
        self.assertTrue(all(
            isinstance(m["content"], str)
            for i, m in enumerate(result)
            if i not in (16, len(result) - 2)
        ))

    def test_stale_markers_stripped_on_reapplication(self):
        """Only one user text in this history → no anchor marker, and
        re-application after the list grows must move (not accumulate)
        the [-2] marker."""
        from .client import _apply_message_cache_marker

        msgs = [{"role": "user", "content": "hi"}]
        for i in range(24):
            msgs.append({
                "role": "assistant",
                "content": [{"type": "tool_use", "id": f"tu_{i}", "name": "search", "input": {}}],
            })
            msgs.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": f"tu_{i}", "content": "ok"}],
            })

        # Apply twice (simulating consecutive loop iterations after appends)
        first = _apply_message_cache_marker(msgs)
        first.append({"role": "assistant", "content": [
            {"type": "tool_use", "id": "tu_x", "name": "search", "input": {}}]})
        first.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "tu_x", "content": "ok"}]})
        second = _apply_message_cache_marker(first)

        markers = self._count_markers(second)
        self.assertEqual(markers, [len(second) - 2],
                         "stale markers must be stripped on re-application")

    def test_marker_application_does_not_mutate_input(self):
        from .client import _apply_message_cache_marker

        blocks = [{"type": "tool_result", "tool_use_id": "tu_1", "content": "ok"}]
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "user", "content": blocks},
            {"role": "assistant", "content": "answer"},
        ]
        _apply_message_cache_marker(msgs)
        self.assertNotIn("cache_control", blocks[-1])

    @staticmethod
    def _tool_heavy_turn(msgs, turn_idx, n_calls=12):
        """Append one tool-heavy turn (user text, one batched tool_use/
        tool_result pair with n_calls calls each — >20 content blocks —
        and a final answer)."""
        msgs.append({"role": "user", "content": f"question {turn_idx}"})
        msgs.append({"role": "assistant", "content": [
            {"type": "tool_use", "id": f"tu_{turn_idx}_{j}", "name": "search",
             "input": {"q": str(j)}}
            for j in range(n_calls)
        ]})
        msgs.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": f"tu_{turn_idx}_{j}",
             "content": "ok"}
            for j in range(n_calls)
        ]})
        msgs.append({"role": "assistant", "content": f"answer {turn_idx}"})

    def test_previous_turn_user_message_gets_anchor_marker(self):
        """The cross-turn read anchor: with a tool-heavy previous turn, the
        previous user message must carry its own marker — the [-2]
        marker's 20-block lookback cannot reach it."""
        from .client import (
            _apply_message_cache_marker,
            _build_turn_context,
            _inject_turn_context,
        )

        msgs = []
        self._tool_heavy_turn(msgs, 1)
        msgs.append({"role": "user", "content": "question 2"})
        injected = _inject_turn_context(msgs, _build_turn_context())

        result = _apply_message_cache_marker(injected)

        # Anchor on "question 1" (index 0), [-2] on "question 2".
        self.assertEqual(self._count_markers(result), [0, len(result) - 2])
        self.assertEqual(result[0]["content"][0]["text"], "question 1")
        self.assertEqual(
            result[len(result) - 2]["content"][0]["text"], "question 2"
        )

    def test_turn_context_is_never_the_anchor(self):
        """The injected [System context] message is a plain-string user
        message too — it must be excluded from anchor selection, or the
        anchor would land on volatile per-turn bytes."""
        from .client import (
            _apply_message_cache_marker,
            _build_turn_context,
            _inject_turn_context,
        )

        msgs = []
        self._tool_heavy_turn(msgs, 1)
        self._tool_heavy_turn(msgs, 2)
        msgs.append({"role": "user", "content": "question 3"})
        injected = _inject_turn_context(msgs, _build_turn_context())
        # Mid-loop shape: pairs appended AFTER the context message.
        injected.append({"role": "assistant", "content": [
            {"type": "tool_use", "id": "tu_now", "name": "search", "input": {}}
        ]})
        injected.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "tu_now", "content": "ok"}
        ]})

        result = _apply_message_cache_marker(injected)

        marked = self._count_markers(result)
        marked_texts = [
            result[i]["content"][0].get("text", "")
            for i in marked
            if result[i]["content"][0].get("type") == "text"
        ]
        self.assertNotIn(
            "[System context", "".join(marked_texts)[:1000],
            "anchor must never land on the injected turn context",
        )
        # Anchor = "question 2" (previous turn), [-2] = the tool_use msg.
        anchor_idx = marked[0]
        self.assertEqual(result[anchor_idx]["content"][0]["text"], "question 2")
        self.assertEqual(marked[1], len(result) - 2)

    def test_anchor_stable_across_loop_reapplication(self):
        """Re-applying after the loop appends a pair keeps the anchor on the
        same message (now in wrapped block form) — the scan must recognize
        both string and single-text-block shapes."""
        from .client import _apply_message_cache_marker

        msgs = []
        self._tool_heavy_turn(msgs, 1)
        msgs.append({"role": "user", "content": "question 2"})

        first = _apply_message_cache_marker(msgs)
        first.append({"role": "assistant", "content": [
            {"type": "tool_use", "id": "tu_x", "name": "search", "input": {}}
        ]})
        first.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "tu_x", "content": "ok"}
        ]})
        second = _apply_message_cache_marker(first)

        marked = self._count_markers(second)
        # Anchor stays on "question 1"; [-2] moved to the tool_use message.
        self.assertEqual(marked, [0, len(second) - 2])
        self.assertEqual(second[0]["content"][0]["text"], "question 1")

    def test_thinking_block_is_never_marked(self):
        """cache_control on thinking/redacted_thinking blocks is rejected
        by the API — a [-2] message ending in one is left unmarked."""
        from .client import _apply_message_cache_marker

        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": [
                {"type": "redacted_thinking", "data": "opaque"},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu_1", "content": "ok"}
            ]},
        ]
        result = _apply_message_cache_marker(msgs)
        self.assertEqual(self._count_markers(result), [])


class SummarizeBatchTests(TestCase):
    """B1: Verify summarize() returns correct results with batched SQL."""

    @classmethod
    def setUpTestData(cls):
        from stakeholders.models import Stakeholder
        from tasks.models import Task
        from django.utils import timezone

        Stakeholder.objects.create(name="Alice", entity_type="contact")
        Stakeholder.objects.create(name="Bob", entity_type="attorney")
        Task.objects.create(
            title="Overdue task", status="not_started", priority="high",
            direction="personal", due_date=timezone.localdate() - timezone.timedelta(days=5),
        )
        Task.objects.create(
            title="Current task", status="not_started", priority="medium",
            direction="personal", due_date=timezone.localdate() + timezone.timedelta(days=2),
        )
        Task.objects.create(
            title="Done task", status="complete", priority="low",
            direction="personal", due_date=timezone.localdate() - timezone.timedelta(days=1),
        )

    def test_model_counts_correct(self):
        result = summarize()
        self.assertEqual(result["Stakeholder_count"], 2)
        self.assertEqual(result["Task_count"], 3)

    def test_overdue_tasks_excludes_complete(self):
        result = summarize()
        self.assertEqual(result["overdue_tasks"], 1)

    def test_tasks_due_this_week(self):
        result = summarize()
        self.assertEqual(result["tasks_due_this_week"], 1)

    def test_returns_all_expected_keys(self):
        """Summarize should return counts for all major models."""
        result = summarize()
        expected_models = [
            "Stakeholder", "LegalMatter", "RealEstate", "Investment", "Loan",
            "Task", "Note",
        ]
        for model in expected_models:
            self.assertIn(f"{model}_count", result, f"Missing {model}_count")

    def test_zero_counts_included(self):
        """Models with zero records should still appear with count 0."""
        result = summarize()
        self.assertEqual(result.get("LegalMatter_count", -1), 0)


class GetRecordSelectRelatedTests(TestCase):
    """B2: Verify get_record uses select_related/prefetch_related."""

    @classmethod
    def setUpTestData(cls):
        from stakeholders.models import Stakeholder
        from tasks.models import Task

        cls.stakeholder = Stakeholder.objects.create(name="Test Person", entity_type="contact")
        cls.task = Task.objects.create(
            title="Linked task", status="not_started", priority="high",
            direction="personal",
        )
        cls.task.related_stakeholders.add(cls.stakeholder)

    def test_get_record_returns_correct_data(self):
        """Functional correctness: get_record still returns full data."""
        result = get_record("Task", self.task.pk)
        self.assertEqual(result["title"], "Linked task")
        self.assertEqual(result["__model__"], "Task")
        self.assertIn("__url__", result)

    def test_get_record_expands_m2m(self):
        """M2M fields are still expanded."""
        result = get_record("Task", self.task.pk)
        self.assertIn("related_stakeholders", result)
        stakeholders = result["related_stakeholders"]
        self.assertEqual(len(stakeholders), 1)
        self.assertEqual(stakeholders[0]["str"], "Test Person")

    def test_get_record_not_found_still_works(self):
        result = get_record("Task", 99999)
        self.assertIn("error", result)

    def test_get_record_with_fk(self):
        """FK fields are still expanded correctly."""
        from tasks.models import Task

        task = Task.objects.create(
            title="Assigned task", status="not_started", priority="high",
            direction="outbound", assigned_to=self.stakeholder,
        )
        result = get_record("Task", task.pk)
        self.assertIn("assigned_to", result)
        self.assertEqual(result["assigned_to"]["id"], self.stakeholder.pk)
        self.assertEqual(result["assigned_to"]["str"], "Test Person")

    def test_get_record_reduces_queries(self):
        """Verify select_related actually reduces query count."""
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as ctx:
            get_record("Task", self.task.pk)

        # With select_related, all FK data comes in 1-2 queries + 1 prefetch per M2M
        # Without it, each FK would be a separate query. Should be well under 10.
        self.assertLess(
            len(ctx), 10,
            f"get_record made {len(ctx)} queries — N+1 may not be fixed"
        )


class ChoiceCacheTests(TestCase):
    """B3: Verify _normalize_choice_fields uses cached choices."""

    def test_normalize_exact_value(self):
        """Exact value match should pass through unchanged."""
        from .tools import _normalize_choice_fields
        from stakeholders.models import Stakeholder

        data = {"entity_type": "contact"}
        _normalize_choice_fields(Stakeholder, data)
        self.assertEqual(data["entity_type"], "contact")

    def test_normalize_case_insensitive_value(self):
        """Case-insensitive value match should normalize."""
        from .tools import _normalize_choice_fields
        from stakeholders.models import Stakeholder

        data = {"entity_type": "Contact"}
        _normalize_choice_fields(Stakeholder, data)
        self.assertEqual(data["entity_type"], "contact")

    def test_normalize_label_to_value(self):
        """Label like 'Attorney' should map to value 'attorney'."""
        from .tools import _normalize_choice_fields
        from dashboard.models import ChoiceOption
        from stakeholders.models import Stakeholder

        # Ensure the choice exists (seeded by migration)
        if not ChoiceOption.objects.filter(category="entity_type", value="attorney").exists():
            ChoiceOption.objects.create(
                category="entity_type", value="attorney", label="Attorney"
            )

        data = {"entity_type": "Attorney"}
        _normalize_choice_fields(Stakeholder, data)
        self.assertEqual(data["entity_type"], "attorney")

    def test_normalize_ignores_non_choice_fields(self):
        """Fields not in CHOICE_CATEGORIES should be untouched."""
        from .tools import _normalize_choice_fields
        from stakeholders.models import Stakeholder

        data = {"name": "Test", "entity_type": "contact"}
        _normalize_choice_fields(Stakeholder, data)
        self.assertEqual(data["name"], "Test")

    def test_normalize_ignores_non_string_values(self):
        """Non-string values (e.g., integers) should be skipped."""
        from .tools import _normalize_choice_fields
        from stakeholders.models import Stakeholder

        data = {"entity_type": 123}
        _normalize_choice_fields(Stakeholder, data)
        self.assertEqual(data["entity_type"], 123)


class SearchEarlyTerminationTests(TestCase):
    """B4: Verify search() stops early at max_total results."""

    @classmethod
    def setUpTestData(cls):
        from stakeholders.models import Stakeholder
        # Create enough records to potentially hit the cap
        for i in range(15):
            Stakeholder.objects.create(name=f"TestMatch {i}", entity_type="contact")

    def test_search_returns_results(self):
        result = search("TestMatch")
        self.assertGreater(result["count"], 0)

    def test_search_respects_per_model_limit(self):
        """Per-model limit of 10 should cap results from one model."""
        result = search("TestMatch", models=["Stakeholder"])
        self.assertLessEqual(result["count"], 10)

    def test_search_with_model_filter_still_works(self):
        result = search("TestMatch", models=["Stakeholder"])
        for r in result["results"]:
            self.assertEqual(r["model"], "Stakeholder")

    def test_search_result_structure(self):
        """Each result should have model, id, str, url."""
        result = search("TestMatch", models=["Stakeholder"])
        self.assertGreater(result["count"], 0)
        first = result["results"][0]
        self.assertIn("model", first)
        self.assertIn("id", first)
        self.assertIn("str", first)
        self.assertIn("url", first)


class M2MTruncationIndicatorTests(TestCase):
    """C2: Verify M2M truncation flag appears when >10 items."""

    @classmethod
    def setUpTestData(cls):
        from stakeholders.models import Stakeholder
        from tasks.models import Task

        cls.stakeholder = Stakeholder.objects.create(name="Busy Person", entity_type="contact")
        # Create 12 tasks linked to the stakeholder
        for i in range(12):
            task = Task.objects.create(
                title=f"Task {i}", status="not_started",
                priority="medium", direction="personal",
            )
            task.related_stakeholders.add(cls.stakeholder)

    def test_truncated_flag_set_when_over_10(self):
        """When >10 related items, _truncated flag should appear."""
        result = serialize_instance(self.stakeholder, expand_relations=True)
        # Tasks are accessed via reverse relation 'tasks'
        self.assertIn("tasks", result)
        self.assertEqual(len(result["tasks"]), 10)
        self.assertTrue(result.get("tasks_truncated", False))

    def test_no_truncated_flag_when_under_limit(self):
        """When <=10 related items, no _truncated flag."""
        from stakeholders.models import Stakeholder
        from tasks.models import Task

        s = Stakeholder.objects.create(name="Light Person", entity_type="contact")
        for i in range(3):
            task = Task.objects.create(
                title=f"Small task {i}", status="not_started",
                priority="low", direction="personal",
            )
            task.related_stakeholders.add(s)

        result = serialize_instance(s, expand_relations=True)
        self.assertIn("tasks", result)
        self.assertEqual(len(result["tasks"]), 3)
        self.assertNotIn("tasks_truncated", result)

    def test_exactly_10_items_no_truncation(self):
        """Exactly 10 items should NOT trigger truncation."""
        from stakeholders.models import Stakeholder
        from tasks.models import Task

        s = Stakeholder.objects.create(name="Exact Person", entity_type="contact")
        for i in range(10):
            task = Task.objects.create(
                title=f"Exact task {i}", status="not_started",
                priority="low", direction="personal",
            )
            task.related_stakeholders.add(s)

        result = serialize_instance(s, expand_relations=True)
        self.assertIn("tasks", result)
        self.assertEqual(len(result["tasks"]), 10)
        self.assertNotIn("tasks_truncated", result)

    def test_expand_relations_false_skips_m2m(self):
        """With expand_relations=False, M2M fields are not included."""
        result = serialize_instance(self.stakeholder, expand_relations=False)
        self.assertNotIn("tasks", result)
        self.assertNotIn("tasks_truncated", result)


class DateTimeHandlingTests(TestCase):
    """Regression tests for assistant datetime handling.

    Prevents future-dated records when the LLM emits datetimes parsed from
    UTC-offset email headers.
    """

    def test_registry_schema_note_date_is_datetime(self):
        from notes.models import Note
        info = {f["name"]: f for f in get_field_info(Note)}
        self.assertEqual(info["date"]["type"], "datetime")

    def test_registry_schema_task_reminder_date_is_datetime(self):
        from tasks.models import Task
        info = {f["name"]: f for f in get_field_info(Task)}
        self.assertEqual(info["reminder_date"]["type"], "datetime")

    def test_note_stored_correctly_with_offset_tagged_iso_datetime(self):
        from django.utils import timezone
        from notes.models import Note
        from .tools import create_record

        with timezone.override("America/Los_Angeles"):
            result = create_record("Note", {
                "title": "Email note",
                "content": "Body",
                "date": "2026-04-20T19:27:00-07:00",
                "note_type": "email",
            }, dry_run=False)
            note = Note.objects.get(pk=result["record"]["__pk__"])
            local = timezone.localtime(note.date)

        self.assertEqual(local.year, 2026)
        self.assertEqual(local.month, 4)
        self.assertEqual(local.day, 20)
        self.assertEqual(local.hour, 19)
        self.assertEqual(local.minute, 27)

    def test_turn_context_declares_timezone(self):
        # Phase 3 moved the timezone declaration from the (now frozen)
        # system prompt into the per-turn context block.
        from .client import _build_turn_context

        stats_text = _build_turn_context()
        self.assertIn("Timezone:", stats_text)
        self.assertIn("America/Los_Angeles", stats_text)
        self.assertIn("ISO format", stats_text)


# ===========================================================================
# read_document tool
# ===========================================================================


class ReadDocumentToolTests(TestCase):
    def setUp(self):
        from documents.models import Document
        self.doc_drive = Document.objects.create(
            title="Oak Ave Lease",
            category="lease",
            description="Lease for 1200 Oak Ave.",
            gdrive_file_id="drive_id_abc",
            gdrive_url="https://drive.google.com/file/d/drive_id_abc/view",
            gdrive_mime_type="application/pdf",
            gdrive_file_name="oak_ave_lease.pdf",
        )
        self.doc_no_content = Document.objects.create(
            title="Metadata Only Document",
            category="note",
        )

    def test_404(self):
        from .tools import read_document
        result = read_document(id=99999)
        self.assertIn("error", result)
        self.assertIn("not found", result["error"])

    def test_no_file_or_drive(self):
        from .tools import read_document
        result = read_document(id=self.doc_no_content.pk)
        self.assertIn("error", result)
        self.assertIn("no file content", result["error"].lower())

    def test_drive_disconnected(self):
        from .tools import read_document
        with patch("documents.gdrive.is_connected", return_value=False):
            result = read_document(id=self.doc_drive.pk)
        self.assertIn("error", result)
        self.assertIn("not connected", result["error"].lower())

    def test_drive_happy_path(self):
        from .tools import read_document
        from documents.tests import _build_pdf_bytes
        pdf_bytes = _build_pdf_bytes([
            "Tenant: Tom Driscoll",
            "Monthly rent: $4,250",
        ])
        with patch("documents.gdrive.is_connected", return_value=True), \
             patch("documents.gdrive.download_file_bytes", return_value=pdf_bytes):
            result = read_document(id=self.doc_drive.pk)
        self.assertNotIn("error", result)
        self.assertIn("Title: Oak Ave Lease", result["content"])
        self.assertIn("Filename: oak_ave_lease.pdf", result["content"])
        self.assertIn("Category: lease", result["content"])
        self.assertIn("Tom Driscoll", result["content"])
        self.assertIn("$4,250", result["content"])
        self.assertFalse(result["truncated"])

    def test_drive_happy_path_with_warning_for_empty_pdf(self):
        from .tools import read_document
        from documents.tests import _build_pdf_bytes
        empty_pdf = _build_pdf_bytes([" "])
        with patch("documents.gdrive.is_connected", return_value=True), \
             patch("documents.gdrive.download_file_bytes", return_value=empty_pdf):
            result = read_document(id=self.doc_drive.pk)
        self.assertNotIn("error", result)
        self.assertIn("Warning:", result["content"])
        self.assertIn("scanned", result["content"].lower())

    def test_drive_extract_failure_propagates_error(self):
        from .tools import read_document
        with patch("documents.gdrive.is_connected", return_value=True), \
             patch("documents.gdrive.download_file_bytes", return_value=None):
            result = read_document(id=self.doc_drive.pk)
        self.assertIn("error", result)

    def test_offset_forwarded_to_extract_drive(self):
        from .tools import read_document
        fake_result = {
            "text": "body",
            "truncated": False,
            "warning": None,
            "total_chars": 4,
            "offset": 1000,
            "next_offset": None,
        }
        with patch("documents.gdrive.is_connected", return_value=True), \
             patch("documents.extract.extract_text_from_drive",
                    return_value=fake_result) as mock_extract:
            read_document(id=self.doc_drive.pk, offset=1000)
        mock_extract.assert_called_once_with(
            "drive_id_abc", "application/pdf", offset=1000,
        )

    def test_truncated_envelope_exposes_next_offset(self):
        from .tools import read_document
        fake_result = {
            "text": "slice body",
            "truncated": True,
            "warning": None,
            "total_chars": 500_000,
            "offset": 0,
            "next_offset": 200_000,
        }
        with patch("documents.gdrive.is_connected", return_value=True), \
             patch("documents.extract.extract_text_from_drive",
                    return_value=fake_result):
            result = read_document(id=self.doc_drive.pk)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["total_chars"], 500_000)
        self.assertEqual(result["offset"], 0)
        self.assertEqual(result["next_offset"], 200_000)
        self.assertIn("Notice:", result["content"])
        self.assertIn("200000", result["content"])
        self.assertIn("NOT read", result["content"])

    def test_final_slice_has_no_next_offset(self):
        from .tools import read_document
        fake_result = {
            "text": "final body",
            "truncated": False,
            "warning": None,
            "total_chars": 500_000,
            "offset": 400_000,
            "next_offset": None,
        }
        with patch("documents.gdrive.is_connected", return_value=True), \
             patch("documents.extract.extract_text_from_drive",
                    return_value=fake_result):
            result = read_document(id=self.doc_drive.pk, offset=400_000)
        self.assertFalse(result["truncated"])
        self.assertNotIn("next_offset", result)
        self.assertNotIn("Notice:", result["content"])


class ReadDocumentToolSummaryTests(TestCase):
    def test_describe_input(self):
        result = _tool_summary("read_document", {"id": 7})
        self.assertEqual(result, "Document #7")

    def test_describe_input_with_offset(self):
        result = _tool_summary("read_document", {"id": 7, "offset": 50_000})
        self.assertIn("Document #7", result)
        self.assertIn("50000", result)

    def test_describe_input_offset_zero_omitted(self):
        result = _tool_summary("read_document", {"id": 7, "offset": 0})
        self.assertEqual(result, "Document #7")

    def test_tool_definition_registered(self):
        from .tools import TOOL_DEFINITIONS, TOOL_HANDLERS, read_document
        names = {t["name"] for t in TOOL_DEFINITIONS}
        self.assertIn("read_document", names)
        self.assertIs(TOOL_HANDLERS["read_document"], read_document)

    def test_tool_definition_exposes_offset_param(self):
        from .tools import TOOL_DEFINITIONS
        defn = next(t for t in TOOL_DEFINITIONS if t["name"] == "read_document")
        self.assertIn("offset", defn["input_schema"]["properties"])
        self.assertEqual(
            defn["input_schema"]["properties"]["offset"]["type"], "integer",
        )

    def test_system_prompt_mentions_read_document(self):
        from .client import _build_system_prompt
        blocks = _build_system_prompt()
        prompt_text = " ".join(b["text"] for b in blocks)
        self.assertIn("read_document", prompt_text)
        self.assertIn("Linked documents", prompt_text)

    def test_system_prompt_truncation_guidance(self):
        from .client import _build_system_prompt
        blocks = _build_system_prompt()
        prompt_text = " ".join(b["text"] for b in blocks)
        # Model must know to react to truncated responses, not silently
        # hallucinate past the cutoff.
        self.assertIn("truncated", prompt_text)
        self.assertIn("next_offset", prompt_text)
        self.assertIn("NEVER cite", prompt_text)


# ---------------------------------------------------------------------------
# Plan 01-01: Drive-attach backend tests
# ---------------------------------------------------------------------------

class BulkLinkDriveFilesToolTest(TestCase):
    """Tests for the assistant tool wrapper around the service."""

    def test_tool_registered_in_definitions_and_handlers(self):
        from assistant.tools import TOOL_DEFINITIONS, TOOL_HANDLERS
        names = [t["name"] for t in TOOL_DEFINITIONS]
        self.assertIn("bulk_link_drive_files", names)
        self.assertIn("bulk_link_drive_files", TOOL_HANDLERS)

    def test_tool_definition_has_dry_run_default_true(self):
        from assistant.tools import TOOL_DEFINITIONS
        tool = next(t for t in TOOL_DEFINITIONS if t["name"] == "bulk_link_drive_files")
        self.assertEqual(tool["input_schema"]["properties"]["dry_run"]["default"], True)
        self.assertIn("NEVER skip the preview step", tool["description"])

    def test_tool_definition_lists_all_nine_entity_types(self):
        from assistant.tools import TOOL_DEFINITIONS
        tool = next(t for t in TOOL_DEFINITIONS if t["name"] == "bulk_link_drive_files")
        enum_values = tool["input_schema"]["properties"]["entity_type"]["enum"]
        self.assertEqual(set(enum_values), {
            "realestate", "investment", "loan", "lease", "policy",
            "vehicle", "aircraft", "stakeholder", "legalmatter",
        })

    def test_tool_handler_proxies_to_service(self):
        from assets.models import RealEstate
        from assistant.tools import bulk_link_drive_files
        entity = RealEstate.objects.create(name="Tool Proxy Property")
        result = bulk_link_drive_files(
            entity_type="realestate",
            entity_id=entity.pk,
            files=[{
                "id": "tp1",
                "name": "a.pdf",
                "mimeType": "application/pdf",
                "url": "u",
            }],
            dry_run=True,
        )
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["target"]["entity_id"], entity.pk)


class ConditionalToolRegistrationTest(TestCase):
    """Tests for assistant.client._get_active_tools — gated tool surface area.

    NOTE: The plan documented a baseline of 11 tools, but the actual baseline
    pre-feature is 10 tools (search, query, get_record, create_record,
    update_record, delete_record, list_models, summarize, read_email,
    read_document). After Plan 01-01, the gated tool brings the maximum to 11.
    Tests assert against the actual counts.
    """

    def test_no_marker_excludes_bulk_link(self):
        from assistant.client import _get_active_tools
        msgs = [{"role": "user", "content": "what tasks are overdue?"}]
        names = [t["name"] for t in _get_active_tools(msgs)]
        self.assertNotIn("bulk_link_drive_files", names)
        self.assertEqual(len(names), 10)  # baseline tool count (was 10 pre-feature)

    def test_marker_in_user_message_includes_bulk_link(self):
        from assistant.client import _get_active_tools
        msgs = [{"role": "user", "content": "[AttachedDriveFiles]\n[]\n[/AttachedDriveFiles]\nattach"}]
        names = [t["name"] for t in _get_active_tools(msgs)]
        self.assertIn("bulk_link_drive_files", names)
        self.assertEqual(len(names), 11)

    def test_marker_in_assistant_message_does_not_include_bulk_link(self):
        """Even if the assistant quotes the marker, it should NOT trigger
        registration — only user-authored messages are inspected."""
        from assistant.client import _get_active_tools
        msgs = [
            {"role": "user", "content": "tell me about email markers"},
            {"role": "assistant", "content": "[AttachedDriveFiles] is a marker..."},
        ]
        names = [t["name"] for t in _get_active_tools(msgs)]
        self.assertNotIn("bulk_link_drive_files", names)

    def test_handles_anthropic_content_block_format(self):
        """When the message uses the list-of-blocks format (e.g., during a
        tool-use round-trip), the helper should still extract the user text
        and detect the marker."""
        from assistant.client import _get_active_tools
        msgs = [{"role": "user", "content": [
            {"type": "text", "text": "[AttachedDriveFiles]\n[]\n[/AttachedDriveFiles]\nhi"},
        ]}]
        names = [t["name"] for t in _get_active_tools(msgs)]
        self.assertIn("bulk_link_drive_files", names)

    def test_marker_in_earlier_user_message_keeps_tool_active(self):
        """The dry_run-first workflow needs the gated tool to remain active
        across the user's confirmation turn (which has no marker). The helper
        scans the full user-message history so bulk_link_drive_files stays
        reachable for the dry_run=False execute call."""
        from assistant.client import _get_active_tools
        msgs = [
            {"role": "user", "content": "[AttachedDriveFiles]\n[]\n[/AttachedDriveFiles]\nattach these to the Smith property"},
            {"role": "assistant", "content": "preview: 2 files would be linked"},
            {"role": "user", "content": "yes confirm"},
        ]
        names = [t["name"] for t in _get_active_tools(msgs)]
        self.assertIn("bulk_link_drive_files", names)

    def test_no_marker_tools_array_byte_identical_to_pre_feature(self):
        """Snapshot test: the tools array sent to Anthropic for messages without
        the marker is byte-identical to TOOL_DEFINITIONS minus the gated tool —
        i.e., zero surface area change for non-attachment messages."""
        import json
        from assistant.client import _get_active_tools
        from assistant.tools import TOOL_DEFINITIONS
        expected = [t for t in TOOL_DEFINITIONS if t["name"] != "bulk_link_drive_files"]
        actual = _get_active_tools([{"role": "user", "content": "no marker here"}])
        self.assertEqual(
            json.dumps(expected, sort_keys=True),
            json.dumps(actual, sort_keys=True),
        )

    def test_empty_messages_returns_baseline_tools(self):
        from assistant.client import _get_active_tools
        names = [t["name"] for t in _get_active_tools([])]
        self.assertNotIn("bulk_link_drive_files", names)


class ChatMessageMarkerStrippingTest(TestCase):
    """Tests for ChatMessage.display_content + parser properties."""

    def setUp(self):
        from assistant.models import ChatSession
        self.session = ChatSession.objects.create(title="t")

    def _msg(self, content):
        from assistant.models import ChatMessage
        return ChatMessage(session=self.session, role="user", content=content)

    def test_strips_drive_marker(self):
        m = self._msg(
            '[AttachedDriveFiles]\n'
            '[{"id":"a","name":"x.pdf","mimeType":"application/pdf","url":"u"}]\n'
            '[/AttachedDriveFiles]\nattach this'
        )
        self.assertEqual(m.display_content, "attach this")

    def test_strips_combined_email_and_drive_markers(self):
        m = self._msg(
            '[AttachedEmail:{"subject":"s","message_count":1}]\nbody\n[/AttachedEmail]\n'
            '[AttachedDriveFiles]\n[]\n[/AttachedDriveFiles]\n'
            'do the thing'
        )
        self.assertEqual(m.display_content, "do the thing")

    def test_strips_email_drive_and_context(self):
        """The full prefix chain: email + drive + context + user text."""
        m = self._msg(
            '[AttachedEmail:{"subject":"s","message_count":1}]\nbody\n[/AttachedEmail]\n'
            '[AttachedDriveFiles]\n[]\n[/AttachedDriveFiles]\n'
            '[Context: viewing Stakeholder #1]\n'
            'final question'
        )
        self.assertEqual(m.display_content, "final question")

    def test_strips_plural_emails_drive_and_context(self):
        """The plural email marker supports email batches before Drive/context."""
        emails = [
            {
                "thread_id": "t1",
                "subject": "First email",
                "from_name": "Alice",
                "from_email": "alice@example.com",
                "message_count": 1,
                "thread_text": "Subject: First email\nBody one",
            },
            {
                "thread_id": "t2",
                "subject": "Second email",
                "from_name": "Bob",
                "from_email": "bob@example.com",
                "message_count": 2,
                "thread_text": "Subject: Second email\nBody two",
            },
        ]
        m = self._msg(
            "[AttachedEmails]\n"
            + json.dumps(emails)
            + "\n[/AttachedEmails]\n"
            "[AttachedDriveFiles]\n[]\n[/AttachedDriveFiles]\n"
            "[Context: viewing Stakeholder #1]\n"
            "compare these"
        )
        self.assertEqual(m.display_content, "compare these")

    def test_attached_drive_files_parses_list(self):
        m = self._msg(
            '[AttachedDriveFiles]\n'
            '[{"id":"a","name":"x.pdf","mimeType":"application/pdf","url":"u"}]\n'
            '[/AttachedDriveFiles]\nx'
        )
        files = m.attached_drive_files
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["name"], "x.pdf")

    def test_attached_drive_files_returns_empty_when_no_marker(self):
        self.assertEqual(self._msg("hello").attached_drive_files, [])

    def test_attached_drive_files_returns_empty_on_malformed_json(self):
        self.assertEqual(
            self._msg(
                "[AttachedDriveFiles]\nnot json\n[/AttachedDriveFiles]\nx"
            ).attached_drive_files,
            [],
        )

    def test_attached_drive_files_returns_empty_on_missing_close_marker(self):
        self.assertEqual(
            self._msg("[AttachedDriveFiles]\n[]\nx").attached_drive_files, [],
        )

    def test_attached_drive_files_returns_empty_when_json_is_not_a_list(self):
        self.assertEqual(
            self._msg(
                '[AttachedDriveFiles]\n{"not":"a list"}\n[/AttachedDriveFiles]\nx'
            ).attached_drive_files,
            [],
        )

    def test_attached_email_summary_parses(self):
        m = self._msg(
            '[AttachedEmail:{"subject":"hi","message_count":3}]\nbody\n[/AttachedEmail]\nx'
        )
        s = m.attached_email_summary
        self.assertEqual(s["subject"], "hi")
        self.assertEqual(s["message_count"], 3)

    def test_attached_email_summaries_parses_plural_marker(self):
        emails = [
            {
                "thread_id": "t1",
                "subject": "First email",
                "from_name": "Alice",
                "from_email": "alice@example.com",
                "message_count": 1,
                "thread_text": "Subject: First email\nBody one",
            },
            {
                "thread_id": "t2",
                "subject": "Second email",
                "from_name": "Bob",
                "from_email": "bob@example.com",
                "message_count": 2,
                "thread_text": "Subject: Second email\nBody two",
            },
        ]
        m = self._msg(
            "[AttachedEmails]\n"
            + json.dumps(emails)
            + "\n[/AttachedEmails]\nquestion"
        )
        summaries = m.attached_email_summaries
        self.assertEqual(len(summaries), 2)
        self.assertEqual(summaries[0]["subject"], "First email")
        self.assertEqual(summaries[1]["message_count"], 2)

    def test_attached_email_summaries_wraps_legacy_single_marker(self):
        m = self._msg(
            '[AttachedEmail:{"subject":"legacy","message_count":1}]\nbody\n[/AttachedEmail]\nx'
        )
        self.assertEqual(m.attached_email_summaries, [
            {"subject": "legacy", "message_count": 1},
        ])

    def test_attached_email_summaries_returns_empty_on_malformed_json(self):
        self.assertEqual(
            self._msg(
                "[AttachedEmails]\nnot json\n[/AttachedEmails]\nx"
            ).attached_email_summaries,
            [],
        )

    def test_attached_email_summaries_returns_empty_when_json_is_not_a_list(self):
        self.assertEqual(
            self._msg(
                '[AttachedEmails]\n{"not":"a list"}\n[/AttachedEmails]\nx'
            ).attached_email_summaries,
            [],
        )

    def test_attached_email_summary_returns_none_when_absent(self):
        self.assertIsNone(self._msg("hello").attached_email_summary)

    def test_attached_email_summary_returns_none_on_malformed_json(self):
        self.assertIsNone(
            self._msg(
                "[AttachedEmail:not json]\nbody\n[/AttachedEmail]\nx"
            ).attached_email_summary,
        )


class HeartbeatWrapperTests(TestCase):
    """_with_heartbeat keeps the SSE stream alive during silent windows and
    always reaches a defined terminal state (Defects 1 & the crash path)."""

    def test_passes_frames_through_in_order(self):
        def gen():
            yield "event: a\ndata: {}\n\n"
            yield "event: b\ndata: {}\n\n"

        out = list(_with_heartbeat(gen(), interval=5))
        self.assertEqual(
            out,
            ["event: a\ndata: {}\n\n", "event: b\ndata: {}\n\n"],
        )

    def test_no_keepalive_when_inner_is_fast(self):
        def gen():
            yield "event: done\ndata: {}\n\n"

        out = list(_with_heartbeat(gen(), interval=5))
        self.assertNotIn(": keepalive\n\n", out)

    def test_emits_keepalive_during_silent_window(self):
        def slow():
            time.sleep(0.25)
            yield "event: done\ndata: {}\n\n"

        out = list(_with_heartbeat(slow(), interval=0.05))
        # The blocking window before the first frame must be bridged...
        self.assertIn(": keepalive\n\n", out)
        # ...and the real frame still arrives, last.
        self.assertEqual(out[-1], "event: done\ndata: {}\n\n")

    def test_inner_exception_yields_terminal_error_frame(self):
        def boom():
            yield "event: token\ndata: {}\n\n"
            raise ValueError("kaboom")

        with self.assertLogs("assistant.client", level="ERROR"):
            out = list(_with_heartbeat(boom(), interval=5))
        self.assertEqual(out[0], "event: token\ndata: {}\n\n")
        self.assertTrue(out[-1].startswith("event: error\ndata: "))


class _FakeStream:
    """Minimal stand-in for anthropic's MessageStream context manager that
    always returns a tool_use response (so the loop runs to max iterations)."""

    request_id = "req_test"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter([])  # no content_block_delta events

    def get_final_message(self):
        block = MagicMock()
        block.type = "tool_use"
        block.id = "tool_1"
        block.name = "search"
        block.input = {"query": "x"}
        resp = MagicMock()
        resp.model = "claude-opus-4-6"
        resp.content = [block]
        return resp


class MaxIterationsTerminalEventTests(TestCase):
    """Reaching MAX_TOOL_ITERATIONS must deliver a terminal SSE event so the
    client never stops silently (Defect 3)."""

    def setUp(self):
        self.session = ChatSession.objects.create()
        settings_obj = AssistantSettings.load()
        settings_obj.api_key = "sk-test-key"
        settings_obj.save()

    @patch("assistant.client._execute_tool", return_value='{"ok": true}')
    @patch("assistant.client.anthropic.Anthropic")
    def test_max_iterations_emits_terminal_done(self, mock_anthropic, _mock_exec):
        mock_anthropic.return_value.messages.stream.return_value = _FakeStream()

        frames = list(_stream_message_impl(self.session, "hello", mode="fast"))

        # The loop ran exactly MAX_TOOL_ITERATIONS times before giving up.
        self.assertEqual(
            mock_anthropic.return_value.messages.stream.call_count,
            MAX_TOOL_ITERATIONS,
        )
        # A terminal "done" frame closes the stream...
        self.assertTrue(
            frames[-1].startswith("event: done\ndata: "),
            f"expected terminal done, got: {frames[-1]!r}",
        )
        # ...and the guidance message was persisted for the client to reload.
        self.assertTrue(
            ChatMessage.objects.filter(
                session=self.session,
                role="assistant",
                content__icontains="maximum number of tool calls",
            ).exists()
        )


# A realistic forwarded-email body: a short cover note + signature, then the
# forwarded message introduced by an Outlook "From: .../Sent: ..." header.
# The forwarded substance below the cover note must reach the model intact.
_FORWARDED_BODY = (
    "Everyone:\r\n\r\n"
    "See below. They clearly think they have a better case than they do.\r\n\r\n"
    "Buchalter\r\nJosh H. Escovedo\r\nwww.buchalter.com\r\n\r\n\r\n"
    "From: Brown, Jeffrey N. <JBrown@thompsoncoburn.com>\r\n"
    "Sent: Wednesday, May 20, 2026 3:00 PM\r\n"
    "To: Escovedo, Josh H.\r\n"
    "Subject: Privileged Settlement Communication\r\n\r\n"
    "Josh, our client will accept nothing less than full payment of the loan.\r\n"
)

# The verbatim forwarded message that the cover note in _FORWARDED_BODY quotes.
# In a real reply chain this would be rendered as its own earlier message, so
# the quoted copy is redundant and safe to drop.
_QUOTED_ORIGINAL = (
    "Josh, our client will accept nothing less than full payment of the loan.\r\n\r\n"
    "Jeffrey N. Brown\r\nThompson Coburn LLP\r\n"
)


class EmailBodyCleaningTests(TestCase):
    """Forwarded email content must survive thread-text assembly (regression)."""

    def test_is_forward_subject(self):
        from .views import _is_forward_subject
        self.assertTrue(_is_forward_subject("FW: Privileged Settlement Communication"))
        self.assertTrue(_is_forward_subject("Fwd: hello"))
        self.assertTrue(_is_forward_subject("  fw:  spaced"))
        self.assertFalse(_is_forward_subject("RE: hello"))
        self.assertFalse(_is_forward_subject("Quarterly review"))
        self.assertFalse(_is_forward_subject(""))
        self.assertFalse(_is_forward_subject(None))

    def test_forward_subject_preserves_quoted_content(self):
        """A forwarded email keeps its forwarded body even at message 1."""
        from .views import _clean_email_body
        cleaned = _clean_email_body(
            _FORWARDED_BODY, is_first=True, is_forward=True, earlier_bodies=[]
        )
        self.assertIn("our client will accept nothing less", cleaned)
        self.assertIn("From: Brown, Jeffrey N.", cleaned)

    def test_first_message_preserves_quoted_content(self):
        """The first/only message in a thread is never stripped (no prior copy)."""
        from .views import _clean_email_body
        cleaned = _clean_email_body(
            _FORWARDED_BODY, is_first=True, is_forward=False, earlier_bodies=[]
        )
        self.assertIn("our client will accept nothing less", cleaned)

    def test_embedded_forward_in_reply_thread_is_preserved(self):
        """A forward pasted into a RE: thread (msg 2+) is kept — the quoted text
        does NOT match any earlier sibling, so it is unique content."""
        from .views import _clean_email_body
        unrelated_earlier = "Team, please review the closing statement before Friday."
        cleaned = _clean_email_body(
            _FORWARDED_BODY, is_first=False, is_forward=False,
            earlier_bodies=[unrelated_earlier],
        )
        self.assertIn("our client will accept nothing less", cleaned)
        self.assertIn("From: Brown, Jeffrey N.", cleaned)

    def test_redundant_reply_quote_is_stripped_with_note(self):
        """A quote that reproduces an earlier sibling message is dropped, and a
        visible note replaces it so the removal is not silent. The short
        attribution header is kept (it is novel to this message)."""
        from .views import _clean_email_body, _OMITTED_QUOTE_NOTE
        cleaned = _clean_email_body(
            _FORWARDED_BODY, is_first=False, is_forward=False,
            earlier_bodies=[_QUOTED_ORIGINAL],
        )
        self.assertIn("See below.", cleaned)            # cover note kept
        self.assertNotIn("our client will accept nothing less", cleaned)  # quote dropped
        self.assertIn(_OMITTED_QUOTE_NOTE, cleaned)     # removal is visible

    def test_inline_replies_between_quotes_are_preserved(self):
        """Interleaved (inline) replies survive: only the quoted question lines
        are dropped, the user's answers between them are kept."""
        from .views import _clean_email_body
        original = (
            "Will your client accept a structured payout over twelve months?\r\n\r\n"
            "And will you release the lis pendens at closing?\r\n"
        )
        inline_reply = (
            "Responses inline below, Jeff.\r\n\r\n"
            "From: Brown, Jeffrey N. <JBrown@thompsoncoburn.com>\r\n"
            "Sent: Wednesday, May 20, 2026 3:00 PM\r\n\r\n"
            "Will your client accept a structured payout over twelve months?\r\n"
            "We can consider a payout, but only over six months, not twelve.\r\n"
            "And will you release the lis pendens at closing?\r\n"
            "Yes, the lis pendens will be released at closing.\r\n"
        )
        cleaned = _clean_email_body(
            inline_reply, is_first=False, is_forward=False,
            earlier_bodies=[original],
        )
        # The user's interleaved answers are preserved...
        self.assertIn("only over six months, not twelve", cleaned)
        self.assertIn("lis pendens will be released at closing", cleaned)
        # ...while the quoted questions (verbatim copies of msg 1) are dropped.
        self.assertNotIn("Will your client accept a structured payout", cleaned)

    def test_dedupe_is_marker_independent(self):
        """A plain ">"-quoted block with no attribution line is still deduped —
        the old marker-based stripper missed these entirely."""
        from .views import _clean_email_body, _OMITTED_QUOTE_NOTE
        original = "Please confirm the wire instructions and the closing date by end of day."
        reply = (
            "Confirmed on both counts.\r\n\r\n"
            "> Please confirm the wire instructions and the closing date by end of day.\r\n"
        )
        cleaned = _clean_email_body(
            reply, is_first=False, is_forward=False, earlier_bodies=[original],
        )
        self.assertIn("Confirmed on both counts.", cleaned)
        self.assertNotIn("Please confirm the wire instructions", cleaned)
        self.assertIn(_OMITTED_QUOTE_NOTE, cleaned)

    def test_no_earlier_bodies_never_strips(self):
        """Without sibling context there is nothing to dedupe against — keep all."""
        from .views import _clean_email_body
        cleaned = _clean_email_body(
            _FORWARDED_BODY, is_first=False, is_forward=False, earlier_bodies=[]
        )
        self.assertIn("our client will accept nothing less", cleaned)

    @patch("email_links.gmail.get_thread_messages")
    def test_fetch_view_keeps_forwarded_content(self, mock_fetch):
        """gmail_thread_fetch returns the full forwarded body for a FW: thread."""
        mock_fetch.return_value = [{
            "from_name": "Escovedo, Josh H.",
            "from_email": "jescovedo@buchalter.com",
            "date": "2026-05-20 15:14 PDT",
            "body": _FORWARDED_BODY,
        }]
        resp = self.client.get(
            reverse("assistant:gmail_thread_fetch"),
            {"thread_id": "abc", "subject": "FW: Privileged Settlement Communication"},
        )
        self.assertEqual(resp.status_code, 200)
        text = resp.json()["formatted_text"]
        self.assertIn("our client will accept nothing less", text)

    @patch("email_links.gmail.get_thread_messages")
    def test_fetch_view_dedupes_redundant_reply_chain(self, mock_fetch):
        """A 2-message RE: reply chain drops the redundant quote but keeps the
        unique earlier message (rendered separately) and the new reply text."""
        mock_fetch.return_value = [
            {"from_name": "Brown, Jeffrey N.", "from_email": "jbrown@thompsoncoburn.com",
             "date": "2026-05-20 15:00 PDT", "body": _QUOTED_ORIGINAL},
            {"from_name": "Escovedo, Josh H.", "from_email": "jescovedo@buchalter.com",
             "date": "2026-05-20 15:14 PDT", "body": _FORWARDED_BODY},
        ]
        resp = self.client.get(
            reverse("assistant:gmail_thread_fetch"),
            {"thread_id": "abc", "subject": "RE: Privileged Settlement Communication"},
        )
        self.assertEqual(resp.status_code, 200)
        text = resp.json()["formatted_text"]
        # The unique content still appears exactly once, via message 1.
        self.assertEqual(text.count("our client will accept nothing less"), 1)
        self.assertIn("See below.", text)              # message 2's new text kept
        self.assertIn("[Earlier quoted messages", text)  # dedupe is visible

    @patch("email_links.gmail.get_thread_messages")
    def test_fetch_view_loses_no_unique_content(self, mock_fetch):
        """Completeness invariant: across a deep reply chain, EVERY distinct
        line of raw content survives in the assembled output (dedup only drops
        copies that exist elsewhere). This is the no-data-loss guarantee."""
        from .views import _normalize_line, _strip_boilerplate
        # A 3-deep reply chain: each message adds new text and re-quotes the
        # full prior message (so msg3 contains copies of msg2 and msg1).
        msg1 = (
            "Two questions before we proceed.\r\n\r\n"
            "First, will your client accept a structured payout over twelve months?\r\n"
            "Second, will you release the lis pendens on the property at closing?\r\n"
        )
        msg2 = (
            "Responses inline, Jeff.\r\n\r\n"
            "We can accept a payout, but only over six months rather than twelve.\r\n"
            "The lis pendens will be released at closing as you request.\r\n\r\n"
            "From: Brown, Jeffrey N. <JBrown@thompsoncoburn.com>\r\n"
            "Sent: Monday, May 18, 2026 9:00 AM\r\n\r\n" + msg1
        )
        msg3 = (
            "Six months works. Please send the revised agreement by Friday.\r\n\r\n"
            "From: Escovedo, Josh H. <jescovedo@buchalter.com>\r\n"
            "Sent: Monday, May 18, 2026 2:00 PM\r\n\r\n" + msg2
        )
        mock_fetch.return_value = [
            {"from_name": "Brown", "from_email": "b@x.com", "date": "d1", "body": msg1},
            {"from_name": "Escovedo", "from_email": "e@y.com", "date": "d2", "body": msg2},
            {"from_name": "Brown", "from_email": "b@x.com", "date": "d3", "body": msg3},
        ]
        text = self.client.get(
            reverse("assistant:gmail_thread_fetch"),
            {"thread_id": "abc", "subject": "RE: Settlement"},
        ).json()["formatted_text"]

        def norm_set(s):
            s = _strip_boilerplate(s.replace("\r\n", "\n").replace("\r", "\n"))
            return {ln for ln in (_normalize_line(x) for x in s.split("\n")) if ln}

        raw_set = norm_set(msg1) | norm_set(msg2) | norm_set(msg3)
        out_set = norm_set(text)
        # No raw line is missing from the output — nothing unique was dropped.
        self.assertEqual(raw_set - out_set, set())
        # ...and dedup actually happened: each quoted line appears only once.
        self.assertEqual(text.count("structured payout over twelve months"), 1)
        self.assertEqual(text.count("only over six months rather than twelve"), 1)
        self.assertIn("Six months works.", text)
        self.assertIn("[Earlier quoted messages", text)


class _FakeCompletingStream:
    """Stand-in MessageStream returning a clean text-only final response."""

    request_id = "req_fake_ok"

    def __init__(self, text="The answer.", stop_reason="end_turn"):
        self._text = text
        self._stop_reason = stop_reason

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter([])  # text delivered via get_final_message, not deltas

    def get_final_message(self):
        block = MagicMock()
        block.type = "text"
        block.text = self._text
        resp = MagicMock()
        resp.model = "claude-sonnet-4-6"
        resp.content = [block]
        resp.stop_reason = self._stop_reason
        return resp


class HeartbeatDetachTests(TransactionTestCase):
    """A severed consumer must NOT cancel the in-flight turn (the production
    incident of 2026-06-12): the worker detaches and drains the inner
    generator to completion so everything it persists still lands.

    TransactionTestCase: the stream worker thread uses its own DB connection,
    which cannot see rows created inside a TestCase transaction."""

    def _wait_for(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.05)
        return False

    def test_disconnect_drains_inner_generator_to_completion(self):
        from .models import AssistantTurn, ChatSession

        session = ChatSession.objects.create()
        turn = AssistantTurn.objects.create(session=session)
        events = []

        def inner():
            try:
                yield "frame1"
                yield "frame2"
                events.append("mid")
                yield "frame3"
                events.append("completed")
            finally:
                events.append("closed")

        gen = _with_heartbeat(inner(), turn=turn)
        self.assertEqual(next(gen), "frame1")
        gen.close()  # simulate the browser/proxy disconnect

        self.assertTrue(
            self._wait_for(lambda: "closed" in events),
            f"worker did not finish, events={events}",
        )
        # The inner generator ran to completion instead of being cancelled.
        self.assertIn("completed", events)
        turn.refresh_from_db()
        self.assertTrue(turn.client_disconnected)
        # The wrapper does not finalize a successful turn — the impl does.
        self.assertEqual(turn.state, AssistantTurn.STATE_RUNNING)

    def test_completed_stream_relays_all_frames(self):
        events = []

        def inner():
            try:
                yield "frame1"
                yield "frame2"
                events.append("completed")
            finally:
                events.append("closed")

        frames = list(_with_heartbeat(inner()))
        self.assertEqual(
            [f for f in frames if not f.startswith(":")],
            ["frame1", "frame2"],
        )
        self.assertEqual(events, ["completed", "closed"])

    def test_drain_budget_abandons_wedged_turn(self):
        from unittest import mock

        from .models import AssistantTurn, ChatSession

        session = ChatSession.objects.create()
        turn = AssistantTurn.objects.create(session=session)
        events = []

        def inner():
            # Long enough that at least one frame is always pulled AFTER the
            # detach (the bounded queue lets the worker run a frame or two
            # ahead of the consumer), deterministically hitting the budget
            # check in the detached branch.
            try:
                yield "frame1"
                for i in range(1000):
                    yield f"frame{i + 2}"
                events.append("completed")
            finally:
                events.append("closed")

        with mock.patch("assistant.client.DETACHED_DRAIN_BUDGET_SECONDS", -1):
            gen = _with_heartbeat(inner(), turn=turn)
            self.assertEqual(next(gen), "frame1")
            gen.close()
            self.assertTrue(
                self._wait_for(lambda: "closed" in events),
                f"worker did not exit, events={events}",
            )
        # Budget exhausted -> the inner generator was cancelled, not drained.
        self.assertNotIn("completed", events)
        turn.refresh_from_db()
        self.assertEqual(turn.state, AssistantTurn.STATE_ABANDONED)

    def test_inner_crash_marks_turn_failed(self):
        from .models import AssistantTurn, ChatSession

        session = ChatSession.objects.create()
        turn = AssistantTurn.objects.create(session=session)

        def inner():
            yield "frame1"
            raise RuntimeError("boom")

        frames = list(_with_heartbeat(inner(), turn=turn))
        self.assertTrue(any(f.startswith("event: error") for f in frames))
        turn.refresh_from_db()
        self.assertEqual(turn.state, AssistantTurn.STATE_FAILED)


class TurnLifecycleTests(TransactionTestCase):
    """stream_message records the turn outcome on its AssistantTurn row.

    TransactionTestCase: the whole tool loop runs in the stream worker thread
    on its own DB connection — it must see the settings/session this test
    commits, and the test must see what the worker commits."""

    def setUp(self):
        from .models import AssistantSettings

        settings = AssistantSettings.load()
        settings.api_key = "sk-test-key"
        settings.save()

    def test_successful_turn_completes_with_final_message(self):
        from .client import stream_message
        from .models import AssistantTurn, ChatMessage, ChatSession

        session = ChatSession.objects.create(title="Existing chat")
        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = (
                _FakeCompletingStream()
            )
            frames = list(stream_message(session, "hello"))

        self.assertTrue(
            any(f.startswith("event: done") for f in frames), frames[-3:]
        )
        turn = AssistantTurn.objects.get(session=session)
        self.assertEqual(turn.state, AssistantTurn.STATE_COMPLETED)
        self.assertFalse(turn.client_disconnected)
        self.assertEqual(turn.request_ids, ["req_fake_ok"])
        saved = (
            ChatMessage.objects.filter(session=session, role="assistant")
            .exclude(content="")
            .last()
        )
        self.assertEqual(turn.final_message_id, saved.pk)

    def test_api_error_marks_turn_failed(self):
        import anthropic as anthropic_sdk
        import httpx

        from .client import stream_message
        from .models import AssistantTurn, ChatSession

        session = ChatSession.objects.create(title="Existing chat")
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        response = httpx.Response(400, request=request, json={"error": {}})
        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.side_effect = (
                anthropic_sdk.APIStatusError(
                    "bad request", response=response, body=None
                )
            )
            frames = list(stream_message(session, "hello"))

        self.assertTrue(any(f.startswith("event: error") for f in frames))
        turn = AssistantTurn.objects.get(session=session)
        self.assertEqual(turn.state, AssistantTurn.STATE_FAILED)

    def test_disconnected_turn_still_persists_answer(self):
        """End-to-end regression for the production incident: sever the
        consumer mid-turn, the answer must still be saved and the turn
        completed."""
        from .client import stream_message
        from .models import AssistantTurn, ChatMessage, ChatSession

        session = ChatSession.objects.create(title="Existing chat")
        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = (
                _FakeCompletingStream()
            )
            gen = stream_message(session, "hello")
            next(gen)  # user_message frame
            gen.close()  # disconnect

            # The detached worker finishes in the background. Reads can race
            # the worker's writes on the shared in-memory test DB — treat a
            # transient lock error as "not ready yet".
            from django.db import OperationalError

            deadline = time.monotonic() + 5
            turn = AssistantTurn.objects.get(session=session)
            while time.monotonic() < deadline:
                try:
                    turn.refresh_from_db()
                    if turn.state != AssistantTurn.STATE_RUNNING:
                        break
                except OperationalError:
                    pass
                time.sleep(0.05)

        self.assertEqual(turn.state, AssistantTurn.STATE_COMPLETED)
        self.assertTrue(turn.client_disconnected)
        saved = (
            ChatMessage.objects.filter(session=session, role="assistant")
            .exclude(content="")
            .last()
        )
        self.assertIsNotNone(saved)
        self.assertIn("The answer.", saved.content)


class TurnStatusViewTests(TestCase):
    def test_no_turn(self):
        from .models import ChatSession

        session = ChatSession.objects.create()
        data = self.client.get(
            reverse("assistant:turn_status", args=[session.pk])
        ).json()
        self.assertEqual(data["state"], "none")

    def test_running_fresh(self):
        from .models import AssistantTurn, ChatSession

        session = ChatSession.objects.create()
        AssistantTurn.objects.create(session=session)
        data = self.client.get(
            reverse("assistant:turn_status", args=[session.pk])
        ).json()
        self.assertEqual(data["state"], "running")

    def test_running_stale_reported_as_stale(self):
        from datetime import timedelta

        from django.utils import timezone

        from .models import AssistantTurn, ChatSession

        session = ChatSession.objects.create()
        turn = AssistantTurn.objects.create(session=session)
        AssistantTurn.objects.filter(pk=turn.pk).update(
            updated_at=timezone.now()
            - timedelta(seconds=AssistantTurn.STALE_AFTER_SECONDS + 10)
        )
        data = self.client.get(
            reverse("assistant:turn_status", args=[session.pk])
        ).json()
        self.assertEqual(data["state"], "stale")

    def test_completed_round_trips_confirm_and_message(self):
        from .models import AssistantTurn, ChatMessage, ChatSession

        session = ChatSession.objects.create()
        msg = ChatMessage.objects.create(
            session=session, role="assistant", content="done"
        )
        AssistantTurn.objects.create(
            session=session,
            state=AssistantTurn.STATE_COMPLETED,
            confirm_required=True,
            client_disconnected=True,
            final_message=msg,
        )
        data = self.client.get(
            reverse("assistant:turn_status", args=[session.pk])
        ).json()
        self.assertEqual(data["state"], "completed")
        self.assertTrue(data["confirm_required"])
        self.assertTrue(data["client_disconnected"])
        self.assertEqual(data["final_message_id"], msg.pk)

    def test_latest_turn_wins(self):
        from .models import AssistantTurn, ChatSession

        session = ChatSession.objects.create()
        AssistantTurn.objects.create(
            session=session, state=AssistantTurn.STATE_COMPLETED
        )
        AssistantTurn.objects.create(session=session)  # newer, running
        data = self.client.get(
            reverse("assistant:turn_status", args=[session.pk])
        ).json()
        self.assertEqual(data["state"], "running")


class StreamViewBusyGuardTests(TestCase):
    """A fresh running turn blocks a second concurrent turn for the session
    (it would interleave messages with the detached in-flight one)."""

    def test_running_turn_refuses_new_stream(self):
        from .models import AssistantTurn, ChatMessage, ChatSession

        session = ChatSession.objects.create()
        AssistantTurn.objects.create(session=session)
        before = ChatMessage.objects.filter(session=session).count()

        resp = self.client.post(
            reverse("assistant:stream", args=[session.pk]),
            {"message": "second question"},
        )
        body = b"".join(resp.streaming_content).decode()
        self.assertIn("event: error", body)
        self.assertIn("still working", body)
        # The refused request must not have written anything.
        self.assertEqual(
            ChatMessage.objects.filter(session=session).count(), before
        )

    def test_stale_running_turn_does_not_block(self):
        from datetime import timedelta

        from django.utils import timezone

        from .models import AssistantTurn, ChatSession

        session = ChatSession.objects.create()
        turn = AssistantTurn.objects.create(session=session)
        AssistantTurn.objects.filter(pk=turn.pk).update(
            updated_at=timezone.now()
            - timedelta(seconds=AssistantTurn.STALE_AFTER_SECONDS + 10)
        )

        with patch(
            "assistant.views.assistant_client.stream_message",
            return_value=iter(['event: done\ndata: {"message_id": 1}\n\n']),
        ) as mock_stream:
            resp = self.client.post(
                reverse("assistant:stream", args=[session.pk]),
                {"message": "hello again"},
            )
            body = b"".join(resp.streaming_content).decode()
        self.assertIn("event: done", body)
        mock_stream.assert_called_once()

    def test_completed_turn_does_not_block(self):
        from .models import AssistantTurn, ChatSession

        session = ChatSession.objects.create()
        AssistantTurn.objects.create(
            session=session, state=AssistantTurn.STATE_COMPLETED
        )
        with patch(
            "assistant.views.assistant_client.stream_message",
            return_value=iter(['event: done\ndata: {"message_id": 1}\n\n']),
        ) as mock_stream:
            self.client.post(
                reverse("assistant:stream", args=[session.pk]),
                {"message": "hello"},
            )
        mock_stream.assert_called_once()

    def test_refused_request_creates_no_second_turn(self):
        """The busy refusal is the DB constraint speaking (IntegrityError on
        the second create), not a racy pre-check — the refused request must
        leave exactly the one original running turn."""
        from .models import AssistantTurn, ChatSession

        session = ChatSession.objects.create()
        first = AssistantTurn.objects.create(session=session)
        resp = self.client.post(
            reverse("assistant:stream", args=[session.pk]),
            {"message": "second question"},
        )
        b"".join(resp.streaming_content)
        turns = session.turns.all()
        self.assertEqual(turns.count(), 1)
        self.assertEqual(turns.first().pk, first.pk)

    def test_stale_turn_finalized_as_abandoned_on_admission(self):
        """Admission finalizes a stale running row (worker died) instead of
        letting it block forever — and the new turn is created by the VIEW,
        before streaming begins."""
        from datetime import timedelta

        from django.utils import timezone

        from .models import AssistantTurn, ChatSession

        session = ChatSession.objects.create()
        stale = AssistantTurn.objects.create(session=session)
        AssistantTurn.objects.filter(pk=stale.pk).update(
            updated_at=timezone.now()
            - timedelta(seconds=AssistantTurn.STALE_AFTER_SECONDS + 10)
        )
        with patch(
            "assistant.views.assistant_client.stream_message",
            return_value=iter(['event: done\ndata: {"message_id": 1}\n\n']),
        ) as mock_stream:
            resp = self.client.post(
                reverse("assistant:stream", args=[session.pk]),
                {"message": "hello again"},
            )
            b"".join(resp.streaming_content)
        stale.refresh_from_db()
        self.assertEqual(stale.state, AssistantTurn.STATE_ABANDONED)
        new_turn = mock_stream.call_args.kwargs.get("turn")
        self.assertIsNotNone(new_turn)
        self.assertEqual(new_turn.state, AssistantTurn.STATE_RUNNING)
        self.assertEqual(new_turn.session_id, session.pk)


class SingleRunningTurnConstraintTests(TestCase):
    """Phase 5 Defect A: one_running_turn_per_session is enforced by the DB,
    closing the TOCTOU window two fast POSTs used to slip through."""

    def test_second_running_turn_rejected(self):
        from django.db import IntegrityError, transaction

        from .models import AssistantTurn, ChatSession

        session = ChatSession.objects.create()
        AssistantTurn.objects.create(session=session)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AssistantTurn.objects.create(session=session)

    def test_terminal_states_do_not_block(self):
        from .models import AssistantTurn, ChatSession

        session = ChatSession.objects.create()
        for state in (
            AssistantTurn.STATE_COMPLETED,
            AssistantTurn.STATE_FAILED,
            AssistantTurn.STATE_ABANDONED,
        ):
            AssistantTurn.objects.create(session=session, state=state)
        # Any number of terminal turns coexist with one running turn.
        AssistantTurn.objects.create(session=session)
        self.assertEqual(session.turns.count(), 4)

    def test_sessions_are_independent(self):
        from .models import AssistantTurn, ChatSession

        s1 = ChatSession.objects.create()
        s2 = ChatSession.objects.create()
        AssistantTurn.objects.create(session=s1)
        AssistantTurn.objects.create(session=s2)  # must not raise
        self.assertEqual(s1.turns.count(), 1)
        self.assertEqual(s2.turns.count(), 1)

    def test_finalizing_frees_the_slot(self):
        from .models import AssistantTurn, ChatSession

        session = ChatSession.objects.create()
        first = AssistantTurn.objects.create(session=session)
        first.state = AssistantTurn.STATE_COMPLETED
        first.save(update_fields=["state"])
        AssistantTurn.objects.create(session=session)  # must not raise


class HistoryMutationGuardTests(TestCase):
    """Phase 5 Defect C: history-mutating views refuse (409) while a live
    running turn may still be writing — a detached worker races edit/retry/
    prune deletes into broken pairing (400s) otherwise."""

    def setUp(self):
        from .models import ChatMessage, ChatSession

        self.session = ChatSession.objects.create(title="Guarded")
        self.user_msg = ChatMessage.objects.create(
            session=self.session, role="user", content="Question"
        )
        self.asst_msg = ChatMessage.objects.create(
            session=self.session, role="assistant", content="Answer"
        )

    def _running_turn(self):
        from .models import AssistantTurn

        return AssistantTurn.objects.create(session=self.session)

    def _stale_turn(self):
        from datetime import timedelta

        from django.utils import timezone

        from .models import AssistantTurn

        turn = self._running_turn()
        AssistantTurn.objects.filter(pk=turn.pk).update(
            updated_at=timezone.now()
            - timedelta(seconds=AssistantTurn.STALE_AFTER_SECONDS + 10)
        )
        return turn

    def test_retry_refused_while_running(self):
        self._running_turn()
        resp = self.client.post(
            reverse("assistant:retry_message", kwargs={
                "session_id": self.session.pk,
                "message_id": self.asst_msg.pk,
            })
        )
        self.assertEqual(resp.status_code, 409)
        self.assertIn("still working", resp.json()["error"])
        self.assertEqual(self.session.messages.count(), 2)

    def test_edit_refused_while_running(self):
        self._running_turn()
        resp = self.client.post(
            reverse("assistant:edit_message", kwargs={
                "session_id": self.session.pk,
                "message_id": self.user_msg.pk,
            })
        )
        self.assertEqual(resp.status_code, 409)
        self.assertIn("still working", resp.json()["error"])
        self.assertEqual(self.session.messages.count(), 2)

    def test_prune_refused_while_running(self):
        self._running_turn()
        resp = self.client.post(
            reverse("assistant:prune", kwargs={"session_id": self.session.pk}),
            {"keep": 2},
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(self.session.messages.count(), 2)

    def test_delete_session_refused_while_running(self):
        from .models import ChatSession

        self._running_turn()
        resp = self.client.post(
            reverse("assistant:delete_session", kwargs={
                "session_id": self.session.pk,
            })
        )
        self.assertEqual(resp.status_code, 409)
        self.assertTrue(ChatSession.objects.filter(pk=self.session.pk).exists())

    def test_bulk_delete_refused_while_running(self):
        from .models import ChatSession

        self._running_turn()
        other = ChatSession.objects.create(title="Other")
        resp = self.client.post(
            reverse("assistant:bulk_delete_sessions"),
            {"selected": [self.session.pk, other.pk]},
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(ChatSession.objects.count(), 2)

    def test_stale_turn_does_not_block_mutations(self):
        self._stale_turn()
        resp = self.client.post(
            reverse("assistant:retry_message", kwargs={
                "session_id": self.session.pk,
                "message_id": self.asst_msg.pk,
            })
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["user_text"], "Question")


class MutatingGetRejectionTests(TestCase):
    """Phase 5 Defect D: no state-mutating endpoint is reachable by GET
    (GET bypasses CSRF; link prefetchers can fire it)."""

    def setUp(self):
        from .models import ChatSession

        self.session = ChatSession.objects.create()

    def test_prune_get_rejected(self):
        from .models import ChatMessage

        ChatMessage.objects.create(
            session=self.session, role="user", content="keep me"
        )
        resp = self.client.get(
            reverse("assistant:prune", kwargs={"session_id": self.session.pk})
        )
        self.assertEqual(resp.status_code, 405)
        self.assertEqual(self.session.messages.count(), 1)

    def test_delete_session_get_rejected(self):
        from .models import ChatSession

        resp = self.client.get(
            reverse("assistant:delete_session", kwargs={
                "session_id": self.session.pk,
            })
        )
        self.assertEqual(resp.status_code, 405)
        self.assertTrue(ChatSession.objects.filter(pk=self.session.pk).exists())

    def test_rename_get_rejected(self):
        resp = self.client.get(
            reverse("assistant:rename_session", kwargs={
                "session_id": self.session.pk,
            })
        )
        self.assertEqual(resp.status_code, 405)


class PruneHistoryHardeningTests(TestCase):
    """Phase 5 Defect D (keep validation) + pair-aware cut: prune never 500s
    on bad input and never strands half a tool pair in the DB."""

    def _prune(self, **data):
        return self.client.post(
            reverse("assistant:prune", kwargs={"session_id": self.session.pk}),
            data,
        )

    def setUp(self):
        from .models import ChatSession

        self.session = ChatSession.objects.create()

    def _add_text_turns(self, n):
        from .models import ChatMessage

        for i in range(n):
            ChatMessage.objects.create(
                session=self.session, role="user", content=f"q{i}"
            )
            ChatMessage.objects.create(
                session=self.session, role="assistant", content=f"a{i}"
            )

    def _add_tool_turn(self, i):
        from .models import ChatMessage

        ChatMessage.objects.create(
            session=self.session, role="user", content=f"tool question {i}"
        )
        ChatMessage.objects.create(
            session=self.session, role="assistant", content="",
            tool_data=[{"type": "tool_use", "id": f"tu_{i}", "name": "query",
                        "input": {}}],
        )
        ChatMessage.objects.create(
            session=self.session, role="user", content="",
            tool_data=[{"type": "tool_result", "tool_use_id": f"tu_{i}",
                        "content": "{}"}],
        )
        ChatMessage.objects.create(
            session=self.session, role="assistant", content=f"tool answer {i}"
        )

    def test_non_numeric_keep_defaults_no_500(self):
        self._add_text_turns(15)  # 30 messages
        resp = self._prune(keep="not-a-number")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.session.messages.count(), 20)

    def test_keep_clamped_to_sane_floor(self):
        self._add_text_turns(5)  # 10 messages
        resp = self._prune(keep="-3")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.session.messages.count(), 2)

    def test_cut_never_splits_a_tool_pair(self):
        for i in range(5):
            self._add_tool_turn(i)  # 20 messages, turn boundaries at 0,4,8,...
        # keep=10 → blind cut at index 10 (the middle of turn 3's tool pair).
        # The cut must advance to the next user-text boundary (index 12).
        resp = self._prune(keep=10)
        self.assertEqual(resp.status_code, 200)
        remaining = list(self.session.messages.order_by("created_at", "pk"))
        self.assertEqual(len(remaining), 8)
        first = remaining[0]
        self.assertEqual(first.role, "user")
        self.assertEqual(first.content, "tool question 3")
        self.assertIsNone(first.tool_data)
        # No orphaned tool_result: every tool_result's tool_use is present.
        use_ids = set()
        for m in remaining:
            for b in m.tool_data or []:
                if b.get("type") == "tool_use":
                    use_ids.add(b["id"])
        for m in remaining:
            for b in m.tool_data or []:
                if b.get("type") == "tool_result":
                    self.assertIn(b["tool_use_id"], use_ids)

    def test_no_clean_boundary_prunes_nothing(self):
        from .models import ChatMessage

        # Pathological: one leading user text, then only tool rows.
        ChatMessage.objects.create(
            session=self.session, role="user", content="only question"
        )
        for i in range(10):
            ChatMessage.objects.create(
                session=self.session, role="assistant", content="",
                tool_data=[{"type": "tool_use", "id": f"tu_{i}",
                            "name": "query", "input": {}}],
            )
            ChatMessage.objects.create(
                session=self.session, role="user", content="",
                tool_data=[{"type": "tool_result", "tool_use_id": f"tu_{i}",
                            "content": "{}"}],
            )
        before = self.session.messages.count()
        resp = self._prune(keep=5)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.session.messages.count(), before)


class TurnToucherTests(TransactionTestCase):
    """Phase 5 Defect E: the turn stays fresh on a time basis, independent of
    produced frames — a long silent inner step (slow tool call, wedged
    upstream) must not make a LIVE turn read as stale and admit a second
    interleaving turn.

    TransactionTestCase: the toucher runs in its own thread on its own DB
    connection — it must see the turn this test commits, and the test must
    see the toucher's committed updates."""

    def _make_turn(self):
        from datetime import timedelta

        from django.utils import timezone

        from .models import AssistantTurn, ChatSession

        session = ChatSession.objects.create()
        turn = AssistantTurn.objects.create(session=session)
        # Backdate past the stale threshold: only an ongoing time-based touch
        # can bring it back.
        AssistantTurn.objects.filter(pk=turn.pk).update(
            updated_at=timezone.now()
            - timedelta(seconds=AssistantTurn.STALE_AFTER_SECONDS + 10)
        )
        turn.refresh_from_db()
        return turn

    def test_silent_inner_step_keeps_turn_fresh(self):
        import threading as _threading
        import time as _time

        from .client import _with_heartbeat

        turn = self._make_turn()
        self.assertTrue(turn.is_stale)
        release = _threading.Event()

        def inner():
            # A "silent inner step": no frames until released.
            release.wait(10)
            yield 'event: done\ndata: {}\n\n'

        with patch("assistant.client.TURN_TOUCH_INTERVAL_SECONDS", 0.05):
            gen = _with_heartbeat(inner(), interval=0.05, turn=turn)
            consumer = _threading.Thread(
                target=lambda: [None for _ in gen], daemon=True
            )
            consumer.start()
            try:
                from django.db import OperationalError

                deadline = _time.monotonic() + 5
                fresh = False
                while _time.monotonic() < deadline:
                    # Reads can race the toucher's writes on the shared
                    # in-memory test DB — treat a transient lock error as
                    # "not ready yet".
                    try:
                        turn.refresh_from_db()
                    except OperationalError:
                        _time.sleep(0.02)
                        continue
                    if not turn.is_stale:
                        fresh = True
                        break
                    _time.sleep(0.02)
                # Refreshed while the inner generator had produced NOTHING.
                self.assertTrue(
                    fresh, "turn stayed stale during a silent inner step"
                )
            finally:
                release.set()
                consumer.join(timeout=5)

    def test_touch_only_refreshes_running_turns(self):
        from datetime import timedelta

        from django.utils import timezone

        from .client import _touch_turn
        from .models import AssistantTurn

        turn = self._make_turn()
        AssistantTurn.objects.filter(pk=turn.pk).update(
            state=AssistantTurn.STATE_COMPLETED,
            updated_at=timezone.now() - timedelta(seconds=500),
        )
        turn.refresh_from_db()
        before = turn.updated_at
        _touch_turn(turn)
        turn.refresh_from_db()
        # A finalized turn keeps its terminal timestamp.
        self.assertEqual(turn.updated_at, before)


class StopReasonNoticeTests(TestCase):
    """4.7+ terminal stop_reasons must never let a stopped response look
    complete (refusal / model_context_window_exceeded, mirroring max_tokens)."""

    def setUp(self):
        from .models import AssistantSettings

        settings = AssistantSettings.load()
        settings.api_key = "sk-test-key"
        settings.save()

    def _stream_with_stop_reason(self, stop_reason):
        from .models import ChatMessage, ChatSession

        session = ChatSession.objects.create(title="Existing chat")
        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = (
                _FakeCompletingStream(text="partial", stop_reason=stop_reason)
            )
            list(_stream_message_impl(session, "hello"))
        return (
            ChatMessage.objects.filter(session=session, role="assistant")
            .exclude(content="")
            .last()
        )

    def test_refusal_notice(self):
        from .client import REFUSAL_NOTICE

        saved = self._stream_with_stop_reason("refusal")
        self.assertIn(REFUSAL_NOTICE.strip(), saved.content)

    def test_context_window_notice(self):
        from .client import CONTEXT_WINDOW_NOTICE

        saved = self._stream_with_stop_reason("model_context_window_exceeded")
        self.assertIn(CONTEXT_WINDOW_NOTICE.strip(), saved.content)

    def test_end_turn_no_notice(self):
        saved = self._stream_with_stop_reason("end_turn")
        self.assertEqual(saved.content, "partial")


def _tool_use_block(block_id="tu_1", name="nonexistent_tool", tool_input=None):
    block = MagicMock()
    block.type = "tool_use"
    block.id = block_id
    block.name = name
    block.input = tool_input or {}
    return block


def _text_block(text):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _api_response(blocks, stop_reason="end_turn"):
    resp = MagicMock()
    resp.content = blocks
    resp.stop_reason = stop_reason
    resp.model = "claude-sonnet-4-6"
    return resp


class _FakePhase2Stream:
    """Stand-in MessageStream returning a canned final response."""

    request_id = "req_fake"

    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter([])

    def get_final_message(self):
        return self._response


class ToolPairValidationTests(TestCase):
    """Phase 2 defect A2/B: _validate_tool_pairs must repair orphans anywhere
    in the list and guarantee the window starts on a genuine user message —
    an unpaired tool message 400s every future request for the session."""

    def _assert_api_valid(self, msgs):
        """Assert the message list satisfies the Anthropic history rules."""
        from .client import _tool_result_ids, _tool_use_ids

        if msgs:
            self.assertEqual(msgs[0].get("role"), "user")
            self.assertEqual(_tool_result_ids(msgs[0]), set())
        for i, msg in enumerate(msgs):
            use_ids = _tool_use_ids(msg) if msg.get("role") == "assistant" else set()
            if use_ids:
                self.assertLess(i + 1, len(msgs), f"tool_use at tail (index {i})")
                nxt = msgs[i + 1]
                self.assertEqual(nxt.get("role"), "user")
                from .client import _tool_result_ids as _res
                self.assertEqual(use_ids, _res(nxt), f"unmatched pair at index {i}")
            res_ids = _tool_result_ids(msg) if msg.get("role") == "user" else set()
            if res_ids:
                prev = msgs[i - 1] if i > 0 else None
                self.assertEqual(
                    res_ids,
                    _tool_use_ids(prev) if prev else set(),
                    f"orphaned tool_result at index {i}",
                )

    @staticmethod
    def _tool_use_msg(block_id="tu_1"):
        return {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": block_id, "name": "search", "input": {}},
            ],
        }

    @staticmethod
    def _tool_result_msg(block_id="tu_1"):
        return {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": block_id, "content": "ok"},
            ],
        }

    def test_mid_list_orphaned_tool_use_dropped(self):
        """The crash signature: tool_use saved, process died before the
        tool_result — the orphan sits in the MIDDLE of later history."""
        from .client import _validate_tool_pairs

        msgs = [
            {"role": "user", "content": "hi"},
            self._tool_use_msg("tu_dead"),  # orphan — no tool_result follows
            {"role": "assistant", "content": "recovered answer"},
            {"role": "user", "content": "next question"},
        ]
        result = _validate_tool_pairs(msgs)
        self._assert_api_valid(result)
        self.assertEqual(len(result), 3)
        self.assertNotIn(
            "tu_dead", json.dumps(result), "orphaned tool_use survived repair"
        )

    def test_mid_list_orphaned_tool_result_dropped(self):
        from .client import _validate_tool_pairs

        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "plain answer"},
            self._tool_result_msg("tu_ghost"),  # no preceding tool_use
            {"role": "user", "content": "next question"},
        ]
        result = _validate_tool_pairs(msgs)
        self._assert_api_valid(result)
        self.assertNotIn("tu_ghost", json.dumps(result))

    def test_mismatched_pair_ids_dropped_together(self):
        """A tool_result answering the WRONG ids is as fatal as a missing one."""
        from .client import _validate_tool_pairs

        msgs = [
            {"role": "user", "content": "hi"},
            self._tool_use_msg("tu_a"),
            self._tool_result_msg("tu_b"),  # answers an id that doesn't exist
            {"role": "user", "content": "next"},
        ]
        result = _validate_tool_pairs(msgs)
        self._assert_api_valid(result)
        self.assertNotIn("tu_a", json.dumps(result))
        self.assertNotIn("tu_b", json.dumps(result))

    def test_valid_pairs_preserved(self):
        from .client import _validate_tool_pairs

        msgs = [
            {"role": "user", "content": "hi"},
            self._tool_use_msg("tu_1"),
            self._tool_result_msg("tu_1"),
            self._tool_use_msg("tu_2"),
            self._tool_result_msg("tu_2"),
            {"role": "assistant", "content": "final answer"},
        ]
        result = _validate_tool_pairs(msgs)
        self.assertEqual(result, msgs)

    def test_existing_end_trim_still_works(self):
        from .client import _validate_tool_pairs

        msgs = [
            {"role": "user", "content": "hi"},
            self._tool_use_msg("tu_tail"),  # orphan at the very end
        ]
        result = _validate_tool_pairs(msgs)
        self._assert_api_valid(result)
        self.assertEqual(result, [{"role": "user", "content": "hi"}])

    def test_existing_start_trim_still_works(self):
        from .client import _validate_tool_pairs

        msgs = [
            self._tool_result_msg("tu_cut"),  # truncation cut its tool_use
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "next"},
        ]
        result = _validate_tool_pairs(msgs)
        self._assert_api_valid(result)
        self.assertEqual(result[0], {"role": "user", "content": "next"})

    def test_leading_assistant_message_dropped(self):
        """Defect B: truncation can slice the window to start on an
        assistant message — the API requires messages[0] to be role user."""
        from .client import _validate_tool_pairs

        msgs = [
            {"role": "assistant", "content": "answer to a sliced-off question"},
            {"role": "user", "content": "next question"},
            {"role": "assistant", "content": "next answer"},
        ]
        result = _validate_tool_pairs(msgs)
        self._assert_api_valid(result)
        self.assertEqual(result[0], {"role": "user", "content": "next question"})

    def test_leading_assistant_tool_pair_dropped_together(self):
        """Dropping a leading assistant tool_use must also drop its (kept)
        tool_result — otherwise the repair itself creates a new orphan."""
        from .client import _validate_tool_pairs

        msgs = [
            self._tool_use_msg("tu_head"),
            self._tool_result_msg("tu_head"),
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "next"},
        ]
        result = _validate_tool_pairs(msgs)
        self._assert_api_valid(result)
        self.assertEqual(result, [{"role": "user", "content": "next"}])

    def test_build_api_messages_repairs_bricked_session(self):
        """End-to-end (spec test A): a session with a mid-history orphaned
        tool_use row self-heals through _build_api_messages."""
        from .client import _build_api_messages

        session = ChatSession.objects.create()
        ChatMessage.objects.create(session=session, role="user", content="hi")
        ChatMessage.objects.create(
            session=session, role="assistant", content="",
            tool_data=[{"type": "tool_use", "id": "tu_orphan",
                        "name": "search", "input": {}}],
        )  # crash happened here — no tool_result row was ever saved
        ChatMessage.objects.create(session=session, role="user", content="are you ok?")
        ChatMessage.objects.create(session=session, role="assistant", content="yes")
        ChatMessage.objects.create(session=session, role="user", content="good")

        result = _build_api_messages(session.messages.all())
        self._assert_api_valid(result)
        self.assertNotIn("tu_orphan", json.dumps(result))

    def test_empty_content_messages_dropped(self):
        """Bug-check fix: empty content ("", [], None) 400s on replay —
        the repair must drop it, not pass it through."""
        from .client import _validate_tool_pairs

        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": ""},
            {"role": "assistant", "content": []},
            {"role": "user", "content": None},
            {"role": "assistant", "content": "real answer"},
        ]
        result = _validate_tool_pairs(msgs)
        self._assert_api_valid(result)
        self.assertEqual(
            result,
            [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "real answer"},
            ],
        )

    def test_build_api_messages_does_not_mutate_tool_data(self):
        """Bug-check fix: cache-breakpoint injection must not write
        cache_control into the ChatMessage instances' tool_data lists
        (request-scoped marker leaking into DB-bound state)."""
        from .client import _build_api_messages

        session = ChatSession.objects.create()
        ChatMessage.objects.create(session=session, role="user", content="Start")
        for i in range(19):
            role = "assistant" if i % 2 == 0 else "user"
            if role == "assistant":
                tool_data = [{"type": "tool_use", "id": f"tu_{i}",
                              "name": "search", "input": {}}]
            else:
                tool_data = [{"type": "tool_result", "tool_use_id": f"tu_{i-1}",
                              "content": "ok"}]
            ChatMessage.objects.create(
                session=session, role=role, content="", tool_data=tool_data
            )

        instances = list(session.messages.all())
        result = _build_api_messages(instances)

        # The breakpoint DID fire on a tool_data message in the output...
        self.assertTrue(any(
            isinstance(m.get("content"), list)
            and any("cache_control" in b for b in m["content"]
                    if isinstance(b, dict))
            for m in result
        ))
        # ...but no model instance's tool_data was touched.
        for inst in instances:
            for block in inst.tool_data or []:
                self.assertNotIn(
                    "cache_control", block,
                    f"cache_control leaked into ChatMessage {inst.pk} tool_data",
                )

    def test_truncated_window_starts_with_user(self):
        """Defect B spec test: 55-message session whose 50-message tail
        begins on an assistant message."""
        from .client import MAX_MESSAGES_TO_SEND, _build_api_messages

        session = ChatSession.objects.create()
        for i in range(MAX_MESSAGES_TO_SEND + 5):
            role = "user" if i % 2 == 0 else "assistant"
            ChatMessage.objects.create(session=session, role=role, content=f"m{i}")
        # Sanity: the raw tail really does start on an assistant message.
        raw_tail_first = list(session.messages.all())[-MAX_MESSAGES_TO_SEND]
        self.assertEqual(raw_tail_first.role, "assistant")

        result = _build_api_messages(session.messages.all())
        self.assertEqual(result[0]["role"], "user")


class AtomicToolSaveTests(TestCase):
    """Phase 2 defect A1: the assistant tool_use message and its user
    tool_result message must persist together or not at all."""

    def setUp(self):
        settings = AssistantSettings.load()
        settings.api_key = "sk-test-key"
        settings.save()
        self.session = ChatSession.objects.create(title="Existing chat")

    def _failing_create(self):
        """A ChatMessage.objects.create stand-in that fails on the
        tool_result save (the second create of the pair)."""
        real_create = ChatMessage.objects.create

        def failing(**kwargs):
            tool_data = kwargs.get("tool_data")
            if kwargs.get("role") == "user" and tool_data:
                raise RuntimeError("simulated crash between the two creates")
            return real_create(**kwargs)

        return failing

    def test_send_message_rolls_back_orphaned_tool_use(self):
        from .client import send_message

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.create.return_value = _api_response(
                [_tool_use_block("tu_1")], stop_reason="tool_use"
            )
            with patch.object(
                ChatMessage.objects, "create", side_effect=self._failing_create()
            ):
                with self.assertRaises(RuntimeError):
                    send_message(self.session, "hi")

        self.assertFalse(
            ChatMessage.objects.filter(
                session=self.session, tool_data__isnull=False
            ).exists(),
            "a tool message persisted without its pair",
        )

    def test_stream_rolls_back_orphaned_tool_use(self):
        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = _FakePhase2Stream(
                _api_response([_tool_use_block("tu_1")], stop_reason="tool_use")
            )
            with patch.object(
                ChatMessage.objects, "create", side_effect=self._failing_create()
            ):
                frames = list(_stream_message_impl(self.session, "hi"))

        self.assertTrue(any(f.startswith("event: error") for f in frames))
        self.assertFalse(
            ChatMessage.objects.filter(
                session=self.session, tool_data__isnull=False
            ).exists(),
            "a tool message persisted without its pair",
        )

    def test_send_message_saves_pair_after_tools_execute(self):
        """Reorder check: tools run BEFORE the pair is saved, so a mocked
        clean run persists both rows and the loop completes."""
        from .client import send_message

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.create.side_effect = [
                _api_response([_tool_use_block("tu_1")], stop_reason="tool_use"),
                _api_response([_text_block("done")], stop_reason="end_turn"),
            ]
            send_message(self.session, "hi")

        tool_msgs = list(
            ChatMessage.objects.filter(
                session=self.session, tool_data__isnull=False
            ).order_by("pk")
        )
        self.assertEqual(len(tool_msgs), 2)
        self.assertEqual(tool_msgs[0].role, "assistant")
        self.assertEqual(tool_msgs[1].role, "user")
        self.assertEqual(
            tool_msgs[1].tool_data[0]["tool_use_id"],
            tool_msgs[0].tool_data[0]["id"],
        )


class RedactedThinkingRoundTripTests(TestCase):
    """Phase 2 defect C: redacted_thinking blocks must be copied into the
    saved assistant content verbatim — dropping them modifies the replayed
    assistant turn and 400s the session."""

    def setUp(self):
        settings = AssistantSettings.load()
        settings.api_key = "sk-test-key"
        settings.save()
        self.session = ChatSession.objects.create(title="Existing chat")

    def _redacted_block(self, data="opaque-redacted-payload"):
        block = MagicMock()
        block.type = "redacted_thinking"
        block.data = data
        return block

    def test_send_message_round_trips_redacted_thinking(self):
        from .client import send_message

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.create.side_effect = [
                _api_response(
                    [self._redacted_block(), _tool_use_block("tu_1")],
                    stop_reason="tool_use",
                ),
                _api_response([_text_block("done")], stop_reason="end_turn"),
            ]
            send_message(self.session, "hi", mode="max")

            # Saved assistant content includes the block verbatim...
            saved = ChatMessage.objects.filter(
                session=self.session, role="assistant", tool_data__isnull=False
            ).first()
            self.assertIn(
                {"type": "redacted_thinking", "data": "opaque-redacted-payload"},
                saved.tool_data,
            )
            # ...and the next API call replays it unmodified.
            second_call_messages = (
                mock_client.messages.create.call_args_list[1][1]["messages"]
            )
            assistant_turns = [
                m for m in second_call_messages
                if m["role"] == "assistant" and isinstance(m["content"], list)
            ]
            self.assertIn(
                {"type": "redacted_thinking", "data": "opaque-redacted-payload"},
                assistant_turns[-1]["content"],
            )

    def test_stream_round_trips_redacted_thinking(self):
        streams = [
            _FakePhase2Stream(_api_response(
                [self._redacted_block(), _tool_use_block("tu_1")],
                stop_reason="tool_use",
            )),
            _FakePhase2Stream(_api_response([_text_block("done")])),
        ]
        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.side_effect = streams
            list(_stream_message_impl(self.session, "hi", mode="max"))

        saved = ChatMessage.objects.filter(
            session=self.session, role="assistant", tool_data__isnull=False
        ).first()
        self.assertIn(
            {"type": "redacted_thinking", "data": "opaque-redacted-payload"},
            saved.tool_data,
        )


class MaxTokensToolSkipTests(TestCase):
    """Phase 2 defect D: a response ending on a terminal stop_reason
    (max_tokens / model_context_window_exceeded / refusal) while carrying
    tool_use blocks must NOT execute them — truncation means incomplete
    input JSON, and a refused response must not act."""

    def setUp(self):
        settings = AssistantSettings.load()
        settings.api_key = "sk-test-key"
        settings.save()
        self.session = ChatSession.objects.create(title="Existing chat")

    def test_send_message_skips_truncated_tool_call(self):
        from .client import TRUNCATION_NOTICE, send_message

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.create.return_value = _api_response(
                [_text_block("partial"), _tool_use_block("tu_cut")],
                stop_reason="max_tokens",
            )
            with patch("assistant.client._execute_tool") as mock_exec:
                new_messages = send_message(self.session, "hi")

        mock_exec.assert_not_called()
        # Single API call — the turn ended instead of looping on tools.
        self.assertEqual(mock_client.messages.create.call_count, 1)
        final = new_messages[-1]
        self.assertTrue(final.content.startswith("partial"))
        self.assertIn(TRUNCATION_NOTICE.strip(), final.content)
        # No tool messages were saved — nothing to orphan.
        self.assertFalse(
            ChatMessage.objects.filter(
                session=self.session, tool_data__isnull=False
            ).exists()
        )

    def test_stream_skips_truncated_tool_call(self):
        from .client import TRUNCATION_NOTICE

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = _FakePhase2Stream(
                _api_response(
                    [_text_block("partial"), _tool_use_block("tu_cut")],
                    stop_reason="max_tokens",
                )
            )
            with patch("assistant.client._execute_tool") as mock_exec:
                frames = list(_stream_message_impl(self.session, "hi"))

        mock_exec.assert_not_called()
        self.assertTrue(frames[-1].startswith("event: done\ndata: "))
        saved = (
            ChatMessage.objects.filter(session=self.session, role="assistant")
            .exclude(content="")
            .last()
        )
        self.assertIn(TRUNCATION_NOTICE.strip(), saved.content)
        self.assertFalse(
            ChatMessage.objects.filter(
                session=self.session, tool_data__isnull=False
            ).exists()
        )

    def _send_with_stop_reason(self, stop_reason):
        """Run send_message against a tool_use response ending on
        ``stop_reason``; return (mock_exec, final ChatMessage)."""
        from .client import send_message

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.create.return_value = _api_response(
                [_text_block("partial"), _tool_use_block("tu_cut")],
                stop_reason=stop_reason,
            )
            with patch("assistant.client._execute_tool") as mock_exec:
                new_messages = send_message(self.session, "hi")
        return mock_exec, new_messages[-1]

    def test_context_window_truncated_tool_call_skipped(self):
        """Bug-check fix: model_context_window_exceeded is the same
        cut-off-mid-generation shape as max_tokens."""
        from .client import CONTEXT_WINDOW_NOTICE

        mock_exec, final = self._send_with_stop_reason(
            "model_context_window_exceeded"
        )
        mock_exec.assert_not_called()
        self.assertIn(CONTEXT_WINDOW_NOTICE.strip(), final.content)

    def test_refusal_with_tool_use_skipped(self):
        """Bug-check fix: a refused response must not act on its tools."""
        from .client import REFUSAL_NOTICE

        mock_exec, final = self._send_with_stop_reason("refusal")
        mock_exec.assert_not_called()
        self.assertIn(REFUSAL_NOTICE.strip(), final.content)

    def test_stream_context_window_truncated_tool_call_skipped(self):
        """Streaming path uses the same widened guard."""
        from .client import CONTEXT_WINDOW_NOTICE

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = _FakePhase2Stream(
                _api_response(
                    [_text_block("partial"), _tool_use_block("tu_cut")],
                    stop_reason="model_context_window_exceeded",
                )
            )
            with patch("assistant.client._execute_tool") as mock_exec:
                frames = list(_stream_message_impl(self.session, "hi"))

        mock_exec.assert_not_called()
        self.assertTrue(frames[-1].startswith("event: done\ndata: "))
        saved = (
            ChatMessage.objects.filter(session=self.session, role="assistant")
            .exclude(content="")
            .last()
        )
        self.assertIn(CONTEXT_WINDOW_NOTICE.strip(), saved.content)

    def test_normal_tool_use_stop_reason_still_executes(self):
        """Guard must not trip on the ordinary tool_use stop_reason."""
        from .client import send_message

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.create.side_effect = [
                _api_response([_tool_use_block("tu_1")], stop_reason="tool_use"),
                _api_response([_text_block("done")], stop_reason="end_turn"),
            ]
            with patch(
                "assistant.client._execute_tool", return_value="{}"
            ) as mock_exec:
                send_message(self.session, "hi")

        mock_exec.assert_called_once()


class FrozenSystemPromptTests(TestCase):
    """Phase 3 defect B: the system prompt must be byte-identical across
    requests — system renders before messages in the cache prefix, so any
    volatile byte there invalidates every message-level cache entry."""

    def test_single_static_block_with_1h_ttl(self):
        from .client import _build_system_prompt

        blocks = _build_system_prompt()
        self.assertEqual(len(blocks), 1)
        self.assertEqual(
            blocks[0]["cache_control"], {"type": "ephemeral", "ttl": "1h"}
        )

    def test_byte_identical_across_stat_and_settings_changes(self):
        """The spec test: two calls with different counts/settings produce a
        byte-identical cached block."""
        from django.utils import timezone
        from tasks.models import Task
        from .client import _build_system_prompt

        first = _build_system_prompt()[0]["text"]

        # Change record counts (what the assistant's own writes do)...
        Task.objects.create(title="cache invalidator?", direction="personal")
        # ...and settings-derived prompt inputs.
        s = AssistantSettings.load()
        s.default_reminder_minutes = 999
        s.owner_name = "Changed Owner"
        s.save()

        second = _build_system_prompt()[0]["text"]
        self.assertEqual(first, second)
        # No date in the frozen prompt — the date lives in the turn context.
        self.assertNotIn(timezone.localdate().isoformat(), first)

    def test_schema_text_stable_across_calls(self):
        """Phase 1 excluded models from the registry — confirm the schema
        text is still deterministic between two calls in one process."""
        from . import registry

        self.assertEqual(registry.get_schema_text(), registry.get_schema_text())


class TurnContextTests(TestCase):
    """Phase 3 defect B: the volatile content moved out of `system` must
    arrive appended to the newest user message, and only at request time."""

    def setUp(self):
        settings = AssistantSettings.load()
        settings.api_key = "sk-test-key"
        settings.save()
        self.session = ChatSession.objects.create(title="Existing chat")

    def test_context_contains_dynamic_content(self):
        from django.utils import timezone
        from .client import _build_turn_context

        s = AssistantSettings.load()
        s.default_reminder_minutes = 1440
        s.owner_name = "Test Owner"
        s.save()

        text = _build_turn_context()
        self.assertIn(f"Today: {timezone.localdate().isoformat()}", text)
        self.assertIn("Timezone:", text)
        self.assertIn("Reminder policy:", text)
        self.assertIn("Test Owner", text)
        self.assertIn("## Current system state", text)

    def test_send_message_injects_context_without_persisting_it(self):
        from .client import send_message

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_block = MagicMock()
            mock_block.type = "text"
            mock_block.text = "Hi"
            mock_response = MagicMock()
            mock_response.content = [mock_block]
            mock_response.stop_reason = "end_turn"
            mock_client.messages.create.return_value = mock_response

            send_message(self.session, "what tasks are overdue?")

            sent = mock_client.messages.create.call_args_list[0][1]["messages"]
        # The context rides as its own trailing user message...
        self.assertEqual(sent[-1]["role"], "user")
        self.assertTrue(sent[-1]["content"].startswith("[System context"))
        # ...after the user's message, which keeps its own text (wrapped
        # into a marked text block — the cache anchor the next turn reads).
        user_block = sent[-2]["content"][0]
        self.assertEqual(user_block["text"], "what tasks are overdue?")
        # The persisted row carries neither context nor wrapping.
        saved = ChatMessage.objects.filter(
            session=self.session, role="user"
        ).latest("created_at")
        self.assertEqual(saved.content, "what tasks are overdue?")

    def test_stream_injects_context_into_newest_user_message_only(self):
        from .client import _stream_message_impl

        # Prior history — must NOT receive the context.
        ChatMessage.objects.create(
            session=self.session, role="user", content="old question"
        )
        ChatMessage.objects.create(
            session=self.session, role="assistant", content="old answer"
        )

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            block = MagicMock()
            block.type = "text"
            block.text = "done"
            resp = MagicMock()
            resp.content = [block]
            resp.stop_reason = "end_turn"
            resp.model = "claude-sonnet-4-6"
            MockClient.return_value.messages.stream.return_value = (
                _FakePhase2Stream(resp)
            )
            list(_stream_message_impl(self.session, "new question"))

            sent = MockClient.return_value.messages.stream.call_args[1]["messages"]
        # History bytes untouched (the old question is the cross-turn
        # anchor, so it travels in wrapped block form — hash-equivalent),
        # context trailing, exactly one context message.
        self.assertEqual(sent[0]["content"][0]["text"], "old question")
        self.assertTrue(sent[-1]["content"].startswith("[System context"))
        self.assertEqual(sent[-2]["content"][0]["text"], "new question")
        self.assertEqual(
            sum("[System context" in m["content"] for m in sent
                if isinstance(m["content"], str)),
            1,
        )

    def test_inject_appends_trailing_message_without_mutating_input(self):
        from .client import _inject_turn_context

        msgs = [
            {"role": "user", "content": "real question"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "tu_1", "name": "search", "input": {}}]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu_1", "content": "ok"}]},
        ]
        result = _inject_turn_context(msgs, "CTX")
        self.assertEqual(len(result), 4)
        self.assertEqual(result[-1], {"role": "user", "content": "CTX"})
        # Every persisted message is byte-identical — that is what lets the
        # history prefix cache-chain across turns.
        self.assertEqual(result[:3], msgs)
        self.assertEqual(len(msgs), 3)


class Phase3RequestConstructionTests(TestCase):
    """Phase 3 defect A: a tail cache breakpoint on EVERY request — the
    top-level cache_control kwarg — including each tool-loop iteration,
    plus the [-2] marker (mid-loop lookback bridge / anchor writer) and
    the previous-turn user-message anchor marker."""

    def setUp(self):
        settings = AssistantSettings.load()
        settings.api_key = "sk-test-key"
        settings.save()
        self.session = ChatSession.objects.create(title="Existing chat")

    def _text_response(self, text="Hi"):
        block = MagicMock()
        block.type = "text"
        block.text = text
        resp = MagicMock()
        resp.content = [block]
        resp.stop_reason = "end_turn"
        return resp

    def _tool_response(self, block_id="tu_1"):
        block = MagicMock()
        block.type = "tool_use"
        block.id = block_id
        block.name = "nonexistent_tool"
        block.input = {}
        resp = MagicMock()
        resp.content = [block]
        resp.stop_reason = "tool_use"
        return resp

    def test_send_message_passes_tail_breakpoint_every_iteration(self):
        from .client import CACHE_CONTROL, send_message

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.create.side_effect = [
                self._tool_response("tu_1"),
                self._text_response("done"),
            ]
            send_message(self.session, "hi")

            calls = mock_client.messages.create.call_args_list
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertEqual(call[1]["cache_control"], CACHE_CONTROL)

        # Iteration 2: the second-to-last message (the assistant tool_use
        # turn) carries the single message-level marker.
        second_messages = calls[1][1]["messages"]
        self.assertIn("cache_control", second_messages[-2]["content"][-1])
        marker_count = sum(
            1 for m in second_messages
            if isinstance(m.get("content"), list)
            for b in m["content"]
            if isinstance(b, dict) and "cache_control" in b
        )
        self.assertEqual(marker_count, 1)

    def test_short_and_long_conversations_get_tail_breakpoint(self):
        from .client import CACHE_CONTROL, send_message

        # Long history (>30 messages)
        for i in range(34):
            role = "user" if i % 2 == 0 else "assistant"
            ChatMessage.objects.create(
                session=self.session, role=role, content=f"m{i}"
            )

        short_session = ChatSession.objects.create(title="Short chat")

        for session in (short_session, self.session):
            with patch("assistant.client.anthropic.Anthropic") as MockClient:
                mock_client = MockClient.return_value
                mock_client.messages.create.return_value = self._text_response()
                send_message(session, "hi")
                kwargs = mock_client.messages.create.call_args_list[0][1]
            self.assertEqual(kwargs["cache_control"], CACHE_CONTROL)

    def test_stream_passes_tail_breakpoint(self):
        from .client import CACHE_CONTROL, _stream_message_impl

        resp = self._text_response("done")
        resp.model = "claude-sonnet-4-6"
        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = (
                _FakePhase2Stream(resp)
            )
            list(_stream_message_impl(self.session, "hi"))
            kwargs = MockClient.return_value.messages.stream.call_args[1]
        self.assertEqual(kwargs["cache_control"], CACHE_CONTROL)

    def test_follow_up_turn_marks_previous_user_message(self):
        """Cross-turn anchor: on a session with prior turns, the request
        must carry a marker on the PREVIOUS turn's user message (distance-
        zero read of the anchor entry) in addition to the [-2] marker."""
        from .client import send_message

        ChatMessage.objects.create(
            session=self.session, role="user", content="old question"
        )
        ChatMessage.objects.create(
            session=self.session, role="assistant", content="old answer"
        )

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.create.return_value = self._text_response()
            send_message(self.session, "new question")
            messages = mock_client.messages.create.call_args_list[0][1]["messages"]

        marked = [
            (i, m["content"][-1])
            for i, m in enumerate(messages)
            if isinstance(m.get("content"), list)
            and isinstance(m["content"][-1], dict)
            and "cache_control" in m["content"][-1]
        ]
        self.assertEqual(len(marked), 2)
        self.assertEqual(marked[0][1]["text"], "old question")
        self.assertEqual(marked[1][0], len(messages) - 2)
        self.assertEqual(marked[1][1]["text"], "new question")


class AnchoredTruncationTests(TestCase):
    """Phase 3 defect D + the Phase 2 head-trim cascade: the truncation
    window start must be stable across turns and land on a turn boundary."""

    def _text_history(self, count):
        return [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}
            for i in range(count)
        ]

    def test_no_trim_below_high_water(self):
        from .client import TRUNCATION_HIGH_WATER, _anchored_window_start

        msgs = self._text_history(TRUNCATION_HIGH_WATER)
        self.assertEqual(_anchored_window_start(msgs), 0)

    def test_trim_lands_on_user_text_anchor(self):
        from .client import (
            MAX_MESSAGES_TO_SEND,
            TRUNCATION_HIGH_WATER,
            _anchored_window_start,
        )

        msgs = self._text_history(TRUNCATION_HIGH_WATER + 10)  # 90
        start = _anchored_window_start(msgs)
        self.assertGreater(start, 0)
        anchored = msgs[start]
        self.assertEqual(anchored["role"], "user")
        self.assertIsInstance(anchored["content"], str)
        # Window is cut back to ~the low-water mark, not the high-water mark.
        self.assertLessEqual(len(msgs) - start, TRUNCATION_HIGH_WATER)
        self.assertGreaterEqual(
            len(msgs) - start, MAX_MESSAGES_TO_SEND - 2
        )

    def test_window_start_stable_as_history_grows(self):
        """The fix itself: the same trim decision replays identically as the
        conversation grows, so the retained prefix is byte-stable between
        turns (the sliding window changed it EVERY turn)."""
        from .client import TRUNCATION_HIGH_WATER, _anchored_window_start

        msgs = self._text_history(TRUNCATION_HIGH_WATER + 5)
        start_now = _anchored_window_start(msgs)
        for extra in (2, 10, 24):
            grown = msgs + self._text_history(extra)
            self.assertEqual(
                _anchored_window_start(grown), start_now,
                f"window start moved after {extra} appended messages",
            )

    def test_second_trim_fires_after_another_thirty_messages(self):
        from .client import TRUNCATION_HIGH_WATER, _anchored_window_start

        msgs = self._text_history(2 * TRUNCATION_HIGH_WATER)
        start = _anchored_window_start(msgs)
        # Two trims replayed; window within bounds and anchored on user text.
        self.assertLessEqual(len(msgs) - start, TRUNCATION_HIGH_WATER)
        self.assertEqual(msgs[start]["role"], "user")

    def test_tool_heavy_turn_does_not_shred_window(self):
        """Head-trim cascade regression (Phase 2 bug-check finding): after a
        25-pair tool turn, a raw positional cut opened the window mid-pair
        with no leading user-text message, and the pairing repair trimmed
        most of the window away. The anchor must skip to the turn boundary
        BEFORE the tool block so every in-window pair survives."""
        from .client import _build_api_messages

        session = ChatSession.objects.create()
        # 40 plain messages (20 old turns)
        for i in range(40):
            role = "user" if i % 2 == 0 else "assistant"
            ChatMessage.objects.create(session=session, role=role, content=f"m{i}")
        # One tool-heavy turn: user question + 25 tool pairs + final answer
        ChatMessage.objects.create(
            session=session, role="user", content="process this email"
        )
        for i in range(25):
            ChatMessage.objects.create(
                session=session, role="assistant", content="",
                tool_data=[{"type": "tool_use", "id": f"tu_{i}",
                            "name": "search", "input": {}}],
            )
            ChatMessage.objects.create(
                session=session, role="user", content="",
                tool_data=[{"type": "tool_result", "tool_use_id": f"tu_{i}",
                            "content": "ok"}],
            )
        ChatMessage.objects.create(
            session=session, role="assistant", content="done processing"
        )
        ChatMessage.objects.create(
            session=session, role="user", content="thanks — next question"
        )
        # 94 messages total; the old [-50:] slice landed inside the tool block.

        result = _build_api_messages(session.messages.all())

        # Window head is a genuine user-text turn boundary...
        self.assertEqual(result[0]["role"], "user")
        self.assertIsInstance(result[0]["content"], str)
        # ...and the repair dropped nothing: all 25 pairs survived.
        blob = json.dumps(result)
        for i in range(25):
            self.assertIn(f"tu_{i}", blob, f"pair tu_{i} was trimmed away")
        self.assertGreaterEqual(len(result), 60)


class WarmCacheToolMatchTests(TestCase):
    """Phase 3 defect C: warm_cache must warm the SAME prefix real requests
    read — the active tool array, not raw TOOL_DEFINITIONS — and must use
    the max_tokens=0 pre-warm form (no output tokens billed)."""

    def test_warm_uses_active_tools_and_zero_max_tokens(self):
        from .client import _get_active_tools

        settings = AssistantSettings.load()
        settings.api_key = "sk-test-key"
        settings.save()

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.create.return_value = MagicMock()

            response = self.client.post(reverse("assistant:warm_cache"))
            self.assertEqual(response.status_code, 200)

            kwargs = mock_client.messages.create.call_args[1]
        self.assertEqual(kwargs["max_tokens"], 0)
        self.assertEqual(kwargs["tools"], _get_active_tools([]))
        tool_names = [t["name"] for t in kwargs["tools"]]
        self.assertNotIn("bulk_link_drive_files", tool_names)
        # System prompt is the frozen static block real requests send.
        self.assertEqual(len(kwargs["system"]), 1)


class SharedClientTests(TestCase):
    """Phase 3 defect E: one Anthropic client per process (per key/retries),
    not one per turn; the streaming path stops stacking SDK retries on the
    manual retry loop."""

    def setUp(self):
        settings = AssistantSettings.load()
        settings.api_key = "sk-test-key"
        settings.save()
        self.session = ChatSession.objects.create(title="Existing chat")

    def _text_response(self):
        block = MagicMock()
        block.type = "text"
        block.text = "Hi"
        resp = MagicMock()
        resp.content = [block]
        resp.stop_reason = "end_turn"
        return resp

    def test_client_reused_across_turns(self):
        from .client import send_message

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = (
                self._text_response()
            )
            send_message(self.session, "first turn")
            send_message(self.session, "second turn")
            MockClient.assert_called_once_with(
                api_key="sk-test-key", max_retries=5
            )

    def test_key_change_rebuilds_client(self):
        from .client import _get_shared_client

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            a = _get_shared_client("key-one", max_retries=5)
            b = _get_shared_client("key-one", max_retries=5)
            self.assertIs(a, b)
            _get_shared_client("key-two", max_retries=5)
            self.assertEqual(MockClient.call_count, 2)

    def test_stream_path_uses_single_sdk_retry(self):
        """The manual 5-attempt loop owns status-code retries; SDK retries
        drop from 5 to 1 so an outage can't pin a thread for ~25 attempts."""
        from .client import _stream_message_impl

        resp = self._text_response()
        resp.model = "claude-sonnet-4-6"
        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = (
                _FakePhase2Stream(resp)
            )
            list(_stream_message_impl(self.session, "hi"))
            MockClient.assert_called_once_with(
                api_key="sk-test-key", max_retries=1
            )

    def test_nonstreaming_path_keeps_sdk_retries(self):
        """send_message has no manual retry loop — SDK retries stay at 5."""
        from .client import send_message

        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = (
                self._text_response()
            )
            send_message(self.session, "hi")
            MockClient.assert_called_once_with(
                api_key="sk-test-key", max_retries=5
            )


# ---------------------------------------------------------------------------
# Phase 4 — streaming transport reliability
# ---------------------------------------------------------------------------


class _FakePhase4FailingStream:
    """Stand-in MessageStream that streams one text token, then dies with a
    retryable 529 mid-iteration — the mid-stream retry shape (Defects C/D)."""

    request_id = "req_fail_529"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        import anthropic as anthropic_sdk
        import httpx

        delta = MagicMock()
        delta.type = "text_delta"
        delta.text = "partial answer that must be cleared"
        event = MagicMock()
        event.type = "content_block_delta"
        event.delta = delta
        yield event
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        response = httpx.Response(
            529, request=request, json={"error": {"type": "overloaded_error"}}
        )
        raise anthropic_sdk.APIStatusError(
            "overloaded", response=response, body=None
        )

    def get_final_message(self):  # pragma: no cover — never reached
        raise AssertionError("get_final_message called on a failing stream")


class SentinelDeliveryTests(TestCase):
    """Phase 4 Defect A: the outer stream must reach a defined end state even
    when the end sentinel would previously have been dropped (slow consumer)
    or lost entirely (worker died before delivering it)."""

    def _drain(self, gen, deadline_seconds=5):
        """Consume until StopIteration or the deadline; returns (frames, done)."""
        frames = []
        deadline = time.monotonic() + deadline_seconds
        while time.monotonic() < deadline:
            try:
                frames.append(next(gen))
            except StopIteration:
                return frames, True
        gen.close()
        return frames, False

    def test_slow_consumer_still_terminates(self):
        """Consumer blocked past the old 1s sentinel-put timeout while the
        queue is full: the sentinel put used to give up (queue.Full) and the
        outer loop then yielded keepalives forever."""

        def inner():
            yield "frame1"
            yield "frame2"

        gen = _with_heartbeat(inner(), interval=0.2)
        first = next(gen)
        self.assertEqual(first, "frame1")
        # Worker now fills the queue with frame2 and finishes; pre-fix the
        # sentinel put timed out at 1s and was dropped.
        time.sleep(2.5)
        frames, terminated = self._drain(gen)
        self.assertTrue(terminated, f"stream never terminated: {frames[-5:]}")
        self.assertIn("frame2", frames)

    def test_dead_worker_without_sentinel_terminates(self):
        """Liveness fallback: if the sentinel is lost entirely, a dead worker
        with an empty queue must break the keepalive loop."""

        def inner():
            yield "frame1"

        with patch("assistant.client._queue_final_frame", return_value=False):
            gen = _with_heartbeat(inner(), interval=0.05)
            frames, terminated = self._drain(gen)
        self.assertTrue(terminated, f"stream never terminated: {frames[-5:]}")
        self.assertIn("frame1", frames)


class WorkerCleanupTests(TestCase):
    """Phase 4 addendum: a raising inner_gen.close() in the worker's finally
    must not skip the DB-connection release or the end sentinel."""

    def test_raising_close_still_delivers_sentinel(self):
        class ExplodingClose:
            """Iterator whose close() raises — the shape of a generator whose
            own finally blows up when resumed with GeneratorExit."""

            def __init__(self):
                self._frames = iter(["frame1"])

            def __iter__(self):
                return self

            def __next__(self):
                return next(self._frames)

            def close(self):
                raise RuntimeError("boom on close")

        with self.assertLogs("assistant.client", level="ERROR") as captured:
            gen = _with_heartbeat(ExplodingClose(), interval=5)
            start = time.monotonic()
            frames = list(gen)
            elapsed = time.monotonic() - start
        self.assertIn("frame1", frames)
        # Sentinel-based termination is immediate. Pre-fix the raise killed
        # the worker before the sentinel put, so the consumer's only escape
        # was the liveness fallback after a full 5s queue timeout.
        self.assertLess(
            elapsed, 2,
            "stream terminated via the liveness fallback, not the sentinel",
        )
        self.assertTrue(
            any("close failed" in line for line in captured.output),
            f"close failure was not caught and logged: {captured.output}",
        )


class MidStreamRetryTests(TestCase):
    """Phase 4 Defects C/D: a retryable failure after tokens already streamed
    must reset the client bubble, and the retry-wait keepalive loop must
    tolerate a consumer that blocks past the backoff deadline."""

    def setUp(self):
        self.session = ChatSession.objects.create()
        settings_obj = AssistantSettings.load()
        settings_obj.api_key = "sk-test-key"
        settings_obj.save()

    @patch("assistant.client.anthropic.Anthropic")
    def test_clear_frame_precedes_second_attempt(self, MockClient):
        MockClient.return_value.messages.stream.side_effect = [
            _FakePhase4FailingStream(),
            _FakeCompletingStream(text="clean full answer"),
        ]
        frames = list(_stream_message_impl(self.session, "hello", mode="fast"))

        token_idx = [
            i for i, f in enumerate(frames) if f.startswith("event: token")
        ]
        clear_idx = [
            i for i, f in enumerate(frames) if f.startswith("event: clear")
        ]
        self.assertTrue(token_idx, frames)
        self.assertTrue(clear_idx, f"no clear frame before retry: {frames}")
        # The clear arrives after the partial token and before the stream ends.
        self.assertGreater(clear_idx[0], token_idx[0])
        self.assertTrue(any(f.startswith("event: done") for f in frames))
        self.assertEqual(MockClient.return_value.messages.stream.call_count, 2)

    @patch("assistant.client.anthropic.Anthropic")
    def test_retry_wait_tolerates_consumer_blocking_past_deadline(self, MockClient):
        """The keepalive yield inside the retry wait can block on a slow
        client until the backoff deadline has passed; sleep() must never
        receive a negative value (used to ValueError and fail the turn)."""
        MockClient.return_value.messages.stream.side_effect = [
            _FakePhase4FailingStream(),
            _FakeCompletingStream(text="recovered"),
        ]
        gen = _stream_message_impl(self.session, "hello", mode="fast")
        frames = []
        slept = False
        for frame in gen:
            frames.append(frame)
            if not slept and frame == ": keepalive\n\n":
                slept = True
                time.sleep(1.5)  # longer than the 1s attempt-0 backoff
        self.assertTrue(slept, f"no keepalive during retry wait: {frames}")
        self.assertTrue(
            any(f.startswith("event: done") for f in frames), frames[-3:]
        )


class TurnIdInStreamTests(TransactionTestCase):
    """Phase 4 Defect B (server half): the first SSE frame carries the
    AssistantTurn pk so the client can correlate turn-status polls with THIS
    turn instead of matching a previous completed one (silent message loss).

    TransactionTestCase: stream_message runs the loop in a worker thread on
    its own DB connection."""

    def setUp(self):
        settings_obj = AssistantSettings.load()
        settings_obj.api_key = "sk-test-key"
        settings_obj.save()

    def test_user_message_frame_carries_turn_id(self):
        from .client import stream_message
        from .models import AssistantTurn

        session = ChatSession.objects.create(title="Existing chat")
        with patch("assistant.client.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = (
                _FakeCompletingStream()
            )
            frames = list(stream_message(session, "hello"))

        user_frames = [f for f in frames if f.startswith("event: user_message")]
        self.assertEqual(len(user_frames), 1, frames[:3])
        payload = json.loads(user_frames[0].split("data: ", 1)[1])
        turn = AssistantTurn.objects.get(session=session)
        self.assertEqual(payload["turn_id"], turn.pk)
