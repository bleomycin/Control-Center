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
        # Script src has a hash suffix from WhiteNoise, so check for the base name
        self.assertContains(response, "marked.umd")
        self.assertContains(response, "marked.setOptions")

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
