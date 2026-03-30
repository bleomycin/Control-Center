from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.urls import reverse

from .client import _result_summary, _tool_summary
from .models import ChatMessage, ChatSession
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
        response = self.client.get(reverse("assistant:new_session"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ChatSession.objects.exists())

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
        """Without API key, should return error message."""
        session = ChatSession.objects.create()
        response = self.client.post(
            reverse("assistant:send", kwargs={"session_id": session.pk}),
            {"message": "Hello"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            ChatMessage.objects.filter(
                session=session, role="assistant", content__icontains="not configured"
            ).exists()
        )

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
        self.assertEqual(_tool_summary("query", {"model_name": "Task"}), "Task")

    def test_query_summary_with_filters(self):
        result = _tool_summary("query", {
            "model_name": "Task",
            "filters": {"status": "active", "priority": "high", "extra": "ignored"},
        })
        self.assertIn("Task", result)
        self.assertIn("status=active", result)
        # Only first 2 filters
        self.assertNotIn("extra=ignored", result)

    def test_get_record_summary(self):
        self.assertEqual(
            _tool_summary("get_record", {"model_name": "Stakeholder", "record_id": 42}),
            "Stakeholder #42",
        )

    def test_create_record_summary_dry_run(self):
        result = _tool_summary("create_record", {"model_name": "Task", "dry_run": True})
        self.assertIn("Task", result)
        self.assertIn("dry_run", result)

    def test_list_models_summary_empty(self):
        self.assertEqual(_tool_summary("list_models", {}), "")

    def test_summarize_summary_empty(self):
        self.assertEqual(_tool_summary("summarize", {}), "")

    def test_update_record_summary(self):
        result = _tool_summary("update_record", {"model_name": "Task", "record_id": 5})
        self.assertEqual(result, "Task #5")

    def test_delete_record_summary(self):
        result = _tool_summary("delete_record", {"model_name": "Note", "record_id": 10})
        self.assertEqual(result, "Note #10")


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


class DrawerViewTests(TestCase):
    def test_drawer_session_returns_most_recent(self):
        s1 = ChatSession.objects.create(title="Old")
        s2 = ChatSession.objects.create(title="New")
        response = self.client.get(reverse("assistant:drawer_session"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Most recent by updated_at (s2 was created last)
        self.assertEqual(data["session_id"], s2.pk)
        self.assertEqual(data["title"], "New")

    def test_drawer_session_creates_when_none(self):
        self.assertEqual(ChatSession.objects.count(), 0)
        response = self.client.get(reverse("assistant:drawer_session"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ChatSession.objects.count(), 1)

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


class ToolDefinitionCacheTests(TestCase):
    """A2: Verify cache_control is on the last tool definition."""

    def test_last_tool_has_cache_control(self):
        from .tools import TOOL_DEFINITIONS
        last_tool = TOOL_DEFINITIONS[-1]
        self.assertIn("cache_control", last_tool)
        self.assertEqual(last_tool["cache_control"]["type"], "ephemeral")
        # TTL must match system prompt (1h) — tools are processed first in hierarchy
        self.assertEqual(last_tool["cache_control"]["ttl"], "1h")

    def test_last_tool_is_read_email(self):
        from .tools import TOOL_DEFINITIONS
        last_tool = TOOL_DEFINITIONS[-1]
        self.assertEqual(last_tool["name"], "read_email")

    def test_other_tools_no_cache_control(self):
        """Only the last tool should have cache_control."""
        from .tools import TOOL_DEFINITIONS
        for tool in TOOL_DEFINITIONS[:-1]:
            self.assertNotIn(
                "cache_control", tool,
                f"Tool '{tool['name']}' should not have cache_control"
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
    """A4: Verify cache breakpoints work on both text and tool_data messages."""

    def _make_messages(self, count, tool_data=False):
        """Create a list of alternating user/assistant API messages."""
        msgs = []
        for i in range(count):
            role = "user" if i % 2 == 0 else "assistant"
            if tool_data:
                msgs.append({
                    "role": role,
                    "content": [{"type": "tool_result" if role == "user" else "tool_use",
                                 "id": f"tool_{i}"}],
                })
            else:
                msgs.append({"role": role, "content": f"Message {i}"})
        return msgs

    def test_text_messages_get_breakpoints(self):
        """Original behavior: plain text messages get cache breakpoints."""
        from .client import CACHE_BREAKPOINT_INTERVAL, _build_api_messages
        from .models import ChatMessage

        session = ChatSession.objects.create()
        # Create enough messages to trigger breakpoints
        for i in range(20):
            role = "user" if i % 2 == 0 else "assistant"
            ChatMessage.objects.create(session=session, role=role, content=f"Msg {i}")

        result = _build_api_messages(session.messages.all())

        # Check that at least one breakpoint was added
        has_breakpoint = False
        for msg in result:
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "cache_control" in block:
                        has_breakpoint = True
                        break
        self.assertTrue(has_breakpoint)

    def test_tool_data_messages_get_breakpoints(self):
        """New behavior: tool_data (list) messages also get cache breakpoints."""
        from .client import CACHE_BREAKPOINT_INTERVAL, _build_api_messages
        from .models import ChatMessage

        session = ChatSession.objects.create()
        # Create a mix: first a text msg, then lots of tool messages
        ChatMessage.objects.create(session=session, role="user", content="Start")
        for i in range(19):
            role = "assistant" if i % 2 == 0 else "user"
            if role == "assistant":
                tool_data = [{"type": "tool_use", "id": f"tu_{i}", "name": "search", "input": {}}]
            else:
                tool_data = [{"type": "tool_result", "tool_use_id": f"tu_{i-1}", "content": "ok"}]
            ChatMessage.objects.create(session=session, role=role, content="", tool_data=tool_data)

        result = _build_api_messages(session.messages.all())

        # Find breakpoints on tool_data messages
        tool_breakpoints = 0
        for msg in result:
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "cache_control" in block:
                        # It's a breakpoint on a list-type message
                        if block.get("type") in ("tool_use", "tool_result"):
                            tool_breakpoints += 1
        self.assertGreater(tool_breakpoints, 0, "No breakpoints found on tool_data messages")

    def test_max_two_breakpoints_in_messages(self):
        """Cache breakpoints are capped at 2 (+ 1 tool + 1 system = 4 total)."""
        from .client import _build_api_messages
        from .models import ChatMessage

        session = ChatSession.objects.create()
        for i in range(50):
            role = "user" if i % 2 == 0 else "assistant"
            ChatMessage.objects.create(session=session, role=role, content=f"Msg {i}")

        result = _build_api_messages(session.messages.all())

        breakpoint_count = 0
        for msg in result:
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "cache_control" in block:
                        breakpoint_count += 1
        self.assertLessEqual(breakpoint_count, 2)


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
