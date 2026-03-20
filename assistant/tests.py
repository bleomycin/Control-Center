from django.test import TestCase
from django.urls import reverse

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
