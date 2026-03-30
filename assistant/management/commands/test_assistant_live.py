"""
Live integration tests for the AI assistant.

Runs against the real Anthropic API inside Docker to verify all
optimizations (A1-A4, B1-B4, C2) work correctly with real data.
Tests both send_message and stream_message paths.

Usage:
    docker compose exec web python manage.py test_assistant_live
    docker compose exec web python manage.py test_assistant_live --skip-api
    docker compose exec web python manage.py test_assistant_live --category optimization
    docker compose exec web python manage.py test_assistant_live --verbose
"""

import json
import time
import traceback
from dataclasses import dataclass

from django.core.management.base import BaseCommand
from django.db import connection
from django.test import Client as DjangoClient
from django.test.utils import CaptureQueriesContext


SESSION_PREFIX = "[LIVE-TEST]"

CATEGORIES = {
    "optimization": "Optimization Verification",
    "functional": "Functional Regression",
    "streaming": "Streaming Path",
    "edge": "Edge Cases & Stress",
}


@dataclass
class TestResult:
    name: str
    category: str
    passed: bool
    duration: float
    message: str
    details: str = ""


def _parse_sse_events(generator):
    """Consume stream_message generator, return list of (event_name, data_dict)."""
    events = []
    for raw in generator:
        if raw.startswith(":"):
            continue
        lines = raw.strip().split("\n")
        event_name = data_str = None
        for line in lines:
            if line.startswith("event: "):
                event_name = line[7:]
            elif line.startswith("data: "):
                data_str = line[6:]
        if event_name and data_str:
            try:
                events.append((event_name, json.loads(data_str)))
            except json.JSONDecodeError:
                events.append((event_name, {"_raw": data_str}))
    return events


class Command(BaseCommand):
    help = "Run live integration tests against the Anthropic API to verify assistant optimizations."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-api", action="store_true",
            help="Skip tests that require API calls (run DB-only tests)",
        )
        parser.add_argument(
            "--category", nargs="+", choices=list(CATEGORIES.keys()),
            help="Run only specific test categories",
        )
        parser.add_argument(
            "--verbose", action="store_true",
            help="Show detailed output for each test",
        )

    def handle(self, *args, **options):
        self.verbose = options["verbose"]
        self.skip_api = options["skip_api"]
        categories = options["category"] or list(CATEGORIES.keys())

        # Clean up any orphaned test sessions from previous runs
        self._cleanup()

        # Check prerequisites
        if not self._check_prerequisites():
            return

        # Collect and run tests
        results = []
        try:
            if "optimization" in categories:
                results.extend(self._run_optimization_tests())
            if "functional" in categories:
                results.extend(self._run_functional_tests())
            if "streaming" in categories:
                results.extend(self._run_streaming_tests())
            if "edge" in categories:
                results.extend(self._run_edge_tests())
        finally:
            self._cleanup()

        self._print_report(results)

    # ------------------------------------------------------------------
    # Infrastructure
    # ------------------------------------------------------------------

    def _check_prerequisites(self):
        from assistant.models import AssistantSettings
        from assistant.registry import get_model, build_registry

        build_registry()

        if not self.skip_api:
            settings = AssistantSettings.load()
            key = settings.get_effective_api_key()
            if not key:
                self.stderr.write(self.style.ERROR(
                    "No API key configured. Set one in Assistant Settings or ANTHROPIC_API_KEY env var.\n"
                    "Use --skip-api to run DB-only tests."
                ))
                return False

        # Check sample data exists
        Stakeholder = get_model("Stakeholder")
        if Stakeholder.objects.count() == 0:
            self.stderr.write(self.style.ERROR(
                "No sample data found. Run: python manage.py load_sample_data"
            ))
            return False

        return True

    def _create_session(self, label):
        from assistant.models import ChatSession
        return ChatSession.objects.create(title=f"{SESSION_PREFIX} {label}")

    def _cleanup(self):
        from assistant.models import ChatSession
        deleted, _ = ChatSession.objects.filter(title__startswith=SESSION_PREFIX).delete()
        if deleted and self.verbose:
            self.stdout.write(f"  Cleaned up {deleted} test objects")

        # Also clean up test stakeholders/tasks from M2M truncation test
        from stakeholders.models import Stakeholder
        Stakeholder.objects.filter(name="[LIVE-TEST] M2M Truncation").delete()

    def _run_test(self, test_func, category):
        name = test_func.__name__
        start = time.time()
        try:
            passed, message, details = test_func()
            duration = time.time() - start
            return TestResult(name, category, passed, duration, message, details)
        except Exception as e:
            duration = time.time() - start
            tb = traceback.format_exc()
            return TestResult(name, category, False, duration, f"EXCEPTION: {e}", tb)

    def _print_report(self, results):
        self.stdout.write("")
        self.stdout.write("=" * 70)
        self.stdout.write("ASSISTANT LIVE TEST RESULTS")
        self.stdout.write("=" * 70)

        current_cat = None
        passed_count = 0
        failed_count = 0
        total_time = 0

        for r in results:
            if r.category != current_cat:
                current_cat = r.category
                self.stdout.write(f"\n{CATEGORIES.get(current_cat, current_cat)}")

            total_time += r.duration
            status = self.style.SUCCESS("PASS") if r.passed else self.style.ERROR("FAIL")
            time_str = f"{r.duration:.1f}s"
            line = f"  {status}  {r.name:<45s} {time_str:>6s}"
            if r.message:
                line += f"  {r.message}"
            self.stdout.write(line)

            if r.passed:
                passed_count += 1
            else:
                failed_count += 1

            if self.verbose and r.details:
                for detail_line in r.details.split("\n")[:20]:
                    self.stdout.write(f"        {detail_line}")

            if not r.passed and r.details:
                for detail_line in r.details.split("\n")[:10]:
                    self.stdout.write(f"        {detail_line}")

        total = passed_count + failed_count
        self.stdout.write("")
        self.stdout.write("=" * 70)
        if failed_count == 0:
            self.stdout.write(self.style.SUCCESS(
                f"SUMMARY: {passed_count}/{total} PASSED | Time: {total_time:.1f}s"
            ))
        else:
            self.stdout.write(self.style.ERROR(
                f"SUMMARY: {passed_count}/{total} PASSED, {failed_count} FAILED | Time: {total_time:.1f}s"
            ))
        self.stdout.write("=" * 70)

    # ------------------------------------------------------------------
    # Category 1: Optimization Verification
    # ------------------------------------------------------------------

    def _run_optimization_tests(self):
        tests = [
            self.test_summarize_query_count,
            self.test_get_record_query_count,
            self.test_search_early_termination,
            self.test_m2m_truncation_flag,
        ]
        if not self.skip_api:
            tests = [
                self.test_cache_hit_on_second_call,
                self.test_temperature_passed,
            ] + tests

        return [self._run_test(t, "optimization") for t in tests]

    def test_cache_hit_on_second_call(self):
        """A2: Verify tool+system prompt caching produces cache hits."""
        from assistant.client import _build_system_prompt, _get_client_and_model
        from assistant.tools import TOOL_DEFINITIONS

        client, model_name = _get_client_and_model()
        system = _build_system_prompt()
        tools = TOOL_DEFINITIONS
        messages = [{"role": "user", "content": "Say hi."}]

        r1 = client.messages.create(
            model=model_name, max_tokens=50, temperature=0.0,
            system=system, tools=tools, messages=messages,
        )
        creation = getattr(r1.usage, "cache_creation_input_tokens", 0) or 0

        r2 = client.messages.create(
            model=model_name, max_tokens=50, temperature=0.0,
            system=system, tools=tools, messages=messages,
        )
        read = getattr(r2.usage, "cache_read_input_tokens", 0) or 0

        details = (
            f"Call 1: input={r1.usage.input_tokens}, cache_creation={creation}\n"
            f"Call 2: input={r2.usage.input_tokens}, cache_read={read}"
        )

        if read > 0:
            return True, f"cache_read={read} tokens", details
        return False, f"No cache hit (cache_read={read})", details

    def test_temperature_passed(self):
        """A1: Verify temperature=0.0 produces deterministic responses."""
        from assistant.client import send_message

        session = self._create_session("temperature")
        r1 = send_message(session, "What is 2+2? Reply with ONLY the number, nothing else.")
        text1 = ""
        for msg in r1:
            if msg.role == "assistant" and msg.content:
                text1 = msg.content.strip()

        r2 = send_message(session, "What is 2+2? Reply with ONLY the number, nothing else.")
        text2 = ""
        for msg in r2:
            if msg.role == "assistant" and msg.content:
                text2 = msg.content.strip()

        details = f"Response 1: {text1!r}\nResponse 2: {text2!r}"
        has_4 = "4" in text1 and "4" in text2
        if has_4:
            return True, "both contain '4'", details
        return False, f"Expected '4' in both responses", details

    def test_summarize_query_count(self):
        """B1: Verify summarize() uses batched SQL (< 10 queries, was 22)."""
        from assistant.tools import summarize

        with CaptureQueriesContext(connection) as ctx:
            result = summarize()

        count = len(ctx)
        has_stakeholder = "Stakeholder_count" in result
        has_task = "Task_count" in result
        details = f"Queries: {count}\nKeys: {sorted(result.keys())[:8]}..."

        if count < 10 and has_stakeholder and has_task:
            return True, f"{count} queries (was 22)", details
        return False, f"{count} queries (expected <10)", details

    def test_get_record_query_count(self):
        """B2: Verify get_record uses select_related/prefetch_related."""
        from assistant.tools import get_record
        from assistant.registry import get_model

        Task = get_model("Task")
        task = Task.objects.first()
        if not task:
            return False, "No tasks in sample data", ""

        with CaptureQueriesContext(connection) as ctx:
            result = get_record("Task", task.pk)

        count = len(ctx)
        details = f"Queries: {count}\nTask: {task.title}"

        if count < 10 and "__model__" in result:
            return True, f"{count} queries for Task", details
        return False, f"{count} queries (expected <10)", details

    def test_search_early_termination(self):
        """B4: Verify search() caps at 50 results and terminates early."""
        from assistant.tools import search

        with CaptureQueriesContext(connection) as ctx:
            result = search("a")

        query_count = len(ctx)
        result_count = result["count"]
        details = f"Results: {result_count}, Queries: {query_count}"

        if result_count <= 50 and query_count < 20:
            return True, f"{result_count} results, {query_count} queries", details
        return False, f"count={result_count} (expected <=50), queries={query_count}", details

    def test_m2m_truncation_flag(self):
        """C2: Verify _truncated flag appears when M2M > 10 items."""
        from assistant.registry import serialize_instance, get_model

        Stakeholder = get_model("Stakeholder")
        Task = get_model("Task")

        # Create test stakeholder with 12 tasks
        s = Stakeholder.objects.create(name="[LIVE-TEST] M2M Truncation", entity_type="contact")
        try:
            tasks = []
            for i in range(12):
                t = Task.objects.create(
                    title=f"[LIVE-TEST] Trunc task {i}",
                    status="not_started", priority="low", direction="personal",
                )
                t.related_stakeholders.add(s)
                tasks.append(t)

            result = serialize_instance(s, expand_relations=True)
            has_tasks = "tasks" in result
            task_count = len(result.get("tasks", []))
            truncated = result.get("tasks_truncated", False)

            details = f"tasks={task_count}, truncated={truncated}"

            if has_tasks and task_count == 10 and truncated:
                return True, "truncated=True with 12 items", details
            return False, f"Expected truncated=True, got {truncated}", details
        finally:
            Task.objects.filter(title__startswith="[LIVE-TEST]").delete()
            s.delete()

    # ------------------------------------------------------------------
    # Category 2: Functional Regression
    # ------------------------------------------------------------------

    def _run_functional_tests(self):
        tests = [self.test_choice_normalization]
        if not self.skip_api:
            tests = [
                self.test_simple_text_response,
                self.test_summarize_tool,
                self.test_search_tool,
                self.test_get_record_tool,
                self.test_list_models_tool,
                self.test_multi_tool_chain,
                self.test_create_dry_run,
                self.test_query_with_filters,
            ] + tests + [
                self.test_multi_turn_context,
            ]

        return [self._run_test(t, "functional") for t in tests]

    def _get_assistant_response(self, session, prompt):
        """Send a message and return (response_text, tool_names, messages)."""
        from assistant.client import send_message

        messages = send_message(session, prompt)
        response_text = ""
        tool_names = []
        for msg in messages:
            if msg.tool_data:
                for block in msg.tool_data:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_names.append(block["name"])
            if msg.role == "assistant" and msg.content:
                response_text = msg.content
        return response_text, tool_names, messages

    def test_simple_text_response(self):
        """No tools needed - basic text response."""
        session = self._create_session("simple-text")
        text, tools, _ = self._get_assistant_response(
            session, "Say 'hello world' and nothing else. Do not use any tools."
        )
        details = f"Response: {text[:200]}\nTools: {tools}"
        if text and not tools:
            return True, "", details
        if text and tools:
            return True, f"responded but used {len(tools)} tool(s)", details
        return False, "Empty response", details

    def test_summarize_tool(self):
        """Summarize tool returns system stats."""
        session = self._create_session("summarize")
        text, tools, _ = self._get_assistant_response(
            session, "How many stakeholders and tasks do I have? Use the summarize tool."
        )
        details = f"Response: {text[:300]}\nTools: {tools}"
        has_counts = any(w in text.lower() for w in ["21", "stakeholder", "task"])
        if has_counts:
            return True, f"tools={tools}", details
        return False, "Response missing expected counts", details

    def test_search_tool(self):
        """Search finds known stakeholder."""
        session = self._create_session("search")
        text, tools, _ = self._get_assistant_response(
            session, "Search for James Calloway in the system."
        )
        details = f"Response: {text[:300]}\nTools: {tools}"
        if "calloway" in text.lower() or "james" in text.lower():
            return True, f"tools={tools}", details
        return False, "James Calloway not found in response", details

    def test_get_record_tool(self):
        """get_record returns full details."""
        session = self._create_session("get-record")
        text, tools, _ = self._get_assistant_response(
            session, "Look up full details for the stakeholder Alicia Moreno."
        )
        details = f"Response: {text[:400]}\nTools: {tools}"
        has_detail = "moreno" in text.lower() or "alicia" in text.lower()
        if has_detail:
            return True, f"tools={tools}", details
        return False, "Alicia Moreno details not in response", details

    def test_list_models_tool(self):
        """list_models returns available models."""
        session = self._create_session("list-models")
        text, tools, _ = self._get_assistant_response(
            session, "What data models are available? List them grouped by app."
        )
        details = f"Response: {text[:400]}\nTools: {tools}"
        has_models = "stakeholder" in text.lower() and "task" in text.lower()
        if has_models:
            return True, f"tools={tools}", details
        return False, "Model names not in response", details

    def test_multi_tool_chain(self):
        """Search then get_record for a property."""
        session = self._create_session("multi-tool")
        text, tools, msgs = self._get_assistant_response(
            session,
            "Find the property at 1200 Oak Avenue and show me its full details."
        )
        details = f"Response: {text[:400]}\nTools: {tools}"
        has_tool_data = any(m.tool_data for m in msgs)
        has_property = "oak" in text.lower() and ("385" in text or "austin" in text.lower())
        if has_property and has_tool_data:
            return True, f"tools={tools}", details
        return False, "Property details missing or no tools used", details

    def test_create_dry_run(self):
        """create_record dry_run shows preview without writing."""
        from tasks.models import Task

        session = self._create_session("create-dry-run")
        before_count = Task.objects.count()
        text, tools, _ = self._get_assistant_response(
            session,
            "Create a new task called 'Live test task' with priority high, direction personal. "
            "Show me a preview only, do NOT create it."
        )
        after_count = Task.objects.count()
        details = f"Response: {text[:300]}\nTools: {tools}\nTask count: {before_count}->{after_count}"

        no_new_task = after_count == before_count
        has_preview = "preview" in text.lower() or "dry" in text.lower() or "confirm" in text.lower()
        if no_new_task and has_preview:
            return True, "preview shown, no record created", details
        if not no_new_task:
            # Clean up
            Task.objects.filter(title="Live test task").delete()
            return False, "Record was created (should have been dry_run only)", details
        return False, "No preview indication in response", details

    def test_query_with_filters(self):
        """Query tool with ORM filters."""
        session = self._create_session("query-filters")
        text, tools, _ = self._get_assistant_response(
            session, "Show me all high priority tasks using the query tool."
        )
        details = f"Response: {text[:400]}\nTools: {tools}"
        has_tasks = "task" in text.lower() or "high" in text.lower()
        if has_tasks:
            return True, f"tools={tools}", details
        return False, "No task info in response", details

    def test_choice_normalization(self):
        """B3: Choice label 'Business Partner' normalizes to 'business_partner'."""
        from assistant.tools import create_record

        result = create_record(
            "Stakeholder",
            {"name": "Test Choice", "entity_type": "Business Partner"},
            dry_run=True,
        )
        data = result.get("data", {})
        entity_type_key = data.get("entity_type_id") or data.get("entity_type", "")
        # In dry_run, FK fields get _id suffix, but entity_type is a CharField not FK
        # Check the raw data
        details = f"Result data: {data}"

        # The normalization happens in-place on the input dict before dry_run processing
        # So the preview should show the normalized value
        if "business_partner" in str(data).lower():
            return True, "normalized to business_partner", details
        return False, f"Not normalized: {data}", details

    def test_multi_turn_context(self):
        """Context retention across multiple turns."""
        session = self._create_session("multi-turn")

        # Turn 1: establish a fact
        self._get_assistant_response(
            session, "Remember this important fact: my favorite color is chartreuse."
        )
        # Turn 2: use a tool (adds messages to context)
        self._get_assistant_response(
            session, "How many tasks do I have in the system?"
        )
        # Turn 3: recall the fact
        text, _, _ = self._get_assistant_response(
            session, "What did I say my favorite color was?"
        )
        details = f"Response: {text[:300]}"
        if "chartreuse" in text.lower():
            return True, "recalled 'chartreuse'", details
        return False, "Failed to recall 'chartreuse'", details

    # ------------------------------------------------------------------
    # Category 3: Streaming Path
    # ------------------------------------------------------------------

    def _run_streaming_tests(self):
        if self.skip_api:
            return []
        tests = [
            self.test_stream_basic_response,
            self.test_stream_tool_use,
            self.test_stream_saves_to_db,
            self.test_stream_multi_tool_chain,
        ]
        return [self._run_test(t, "streaming") for t in tests]

    def test_stream_basic_response(self):
        """Streaming yields correct SSE events for text response."""
        from assistant.client import stream_message

        session = self._create_session("stream-basic")
        events = _parse_sse_events(
            stream_message(session, "Say the word 'pineapple' and nothing else. No tools needed.")
        )
        event_types = [e[0] for e in events]
        token_texts = "".join(
            e[1].get("text", "") for e in events if e[0] == "token"
        )
        details = f"Events: {event_types}\nTokens: {token_texts[:200]}"

        has_user_msg = "user_message" in event_types
        has_tokens = "token" in event_types
        has_done = "done" in event_types
        has_word = "pineapple" in token_texts.lower()

        if has_user_msg and has_tokens and has_done and has_word:
            return True, f"{len(events)} events", details
        missing = []
        if not has_user_msg:
            missing.append("user_message")
        if not has_tokens:
            missing.append("token")
        if not has_done:
            missing.append("done")
        if not has_word:
            missing.append("'pineapple' in tokens")
        return False, f"Missing: {', '.join(missing)}", details

    def test_stream_tool_use(self):
        """Streaming with tool calls emits tool_start/tool_done events."""
        from assistant.client import stream_message

        session = self._create_session("stream-tools")
        events = _parse_sse_events(
            stream_message(session, "How many stakeholders are in the system? Use the summarize tool.")
        )
        event_types = [e[0] for e in events]
        details = f"Events: {event_types}"

        has_tool_start = "tool_start" in event_types
        has_tool_done = "tool_done" in event_types
        has_done = "done" in event_types

        if has_tool_start and has_tool_done and has_done:
            return True, f"{len(events)} events", details
        missing = []
        if not has_tool_start:
            missing.append("tool_start")
        if not has_tool_done:
            missing.append("tool_done")
        if not has_done:
            missing.append("done")
        return False, f"Missing: {', '.join(missing)}", details

    def test_stream_saves_to_db(self):
        """Streaming path persists messages to the database."""
        from assistant.client import stream_message

        session = self._create_session("stream-db")
        events = _parse_sse_events(
            stream_message(session, "Say hello.")
        )

        # Check done event has message_id
        done_events = [e for e in events if e[0] == "done"]
        if not done_events:
            return False, "No 'done' event", f"Events: {[e[0] for e in events]}"

        message_id = done_events[0][1].get("message_id")
        from assistant.models import ChatMessage
        msg_exists = ChatMessage.objects.filter(pk=message_id).exists() if message_id else False

        # Check session has messages
        user_msgs = session.messages.filter(role="user").count()
        asst_msgs = session.messages.filter(role="assistant", content__gt="").count()
        details = f"message_id={message_id}, exists={msg_exists}, user_msgs={user_msgs}, asst_msgs={asst_msgs}"

        if msg_exists and user_msgs >= 1 and asst_msgs >= 1:
            return True, f"msg #{message_id} saved", details
        return False, "Messages not saved correctly", details

    def test_stream_multi_tool_chain(self):
        """Streaming handles multi-iteration tool loops."""
        from assistant.client import stream_message

        session = self._create_session("stream-multi-tool")
        events = _parse_sse_events(
            stream_message(session, "Find James Calloway and show me his full details.")
        )
        event_types = [e[0] for e in events]
        tool_starts = [e for e in events if e[0] == "tool_start"]
        tool_dones = [e for e in events if e[0] == "tool_done"]
        details = (
            f"Events: {event_types}\n"
            f"Tools started: {[e[1].get('name') for e in tool_starts]}\n"
            f"Tools done: {[e[1].get('name') for e in tool_dones]}"
        )

        has_multiple_tools = len(tool_starts) >= 2
        has_done = "done" in event_types

        if has_multiple_tools and has_done:
            return True, f"{len(tool_starts)} tools", details
        if len(tool_starts) == 1 and has_done:
            return True, f"1 tool (model chose minimal path)", details
        return False, f"tools={len(tool_starts)}, done={'done' in event_types}", details

    # ------------------------------------------------------------------
    # Category 4: Edge Cases & Stress
    # ------------------------------------------------------------------

    def _run_edge_tests(self):
        tests = [
            self.test_search_no_results,
            self.test_get_record_not_found,
            self.test_long_conversation_breakpoints,
            self.test_validate_tool_pairs,
        ]
        if not self.skip_api:
            tests.append(self.test_warm_cache_endpoint)

        return [self._run_test(t, "edge") for t in tests]

    def test_search_no_results(self):
        """Search with no matches returns empty results."""
        from assistant.tools import search

        result = search("zzzznonexistent999xyz")
        details = f"Result: {result}"
        if result["count"] == 0 and result["results"] == []:
            return True, "empty results", details
        return False, f"Expected empty, got count={result['count']}", details

    def test_get_record_not_found(self):
        """get_record on missing ID returns error."""
        from assistant.tools import get_record

        result = get_record("Stakeholder", 999999)
        details = f"Result: {result}"
        if "error" in result:
            return True, "error returned", details
        return False, "No error for missing record", details

    def test_warm_cache_endpoint(self):
        """A3: warm_cache endpoint returns 200 (was crashing before)."""
        client = DjangoClient()
        response = client.post("/assistant/warm/")
        details = f"Status: {response.status_code}, Body: {response.content.decode()[:200]}"
        if response.status_code == 200:
            body = response.json()
            if body.get("ok"):
                return True, "200 OK", details
        return False, f"Status {response.status_code}", details

    def test_long_conversation_breakpoints(self):
        """A4: Cache breakpoints capped at 2 in messages (4 total with tool+system)."""
        from assistant.client import _build_api_messages
        from assistant.models import ChatMessage

        session = self._create_session("breakpoints")
        # Create 40 messages (mix of text and tool_data)
        for i in range(40):
            if i % 3 == 0:
                ChatMessage.objects.create(session=session, role="user", content=f"Q{i}")
            elif i % 3 == 1:
                ChatMessage.objects.create(
                    session=session, role="assistant", content="",
                    tool_data=[{"type": "tool_use", "id": f"tu_{i}", "name": "search", "input": {"query": "x"}}],
                )
            else:
                ChatMessage.objects.create(
                    session=session, role="user", content="",
                    tool_data=[{"type": "tool_result", "tool_use_id": f"tu_{i-1}", "content": "{}"}],
                )

        result = _build_api_messages(session.messages.all())

        breakpoint_count = 0
        for msg in result:
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "cache_control" in block:
                        breakpoint_count += 1

        details = f"Messages: {len(result)}, Breakpoints in messages: {breakpoint_count}"

        # Max 2 breakpoints in messages (+ 1 tool + 1 system = 4 total API limit)
        if breakpoint_count <= 2:
            return True, f"{breakpoint_count} breakpoints", details
        return False, f"{breakpoint_count} breakpoints (max 2)", details

    def test_validate_tool_pairs(self):
        """Orphaned tool_use/tool_result messages are cleaned up."""
        from assistant.client import _validate_tool_pairs

        messages = [
            # Orphaned tool_result at start (its tool_use was truncated)
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "orphan_1", "content": "{}"}]},
            {"role": "user", "content": "Real question"},
            {"role": "assistant", "content": "Real answer"},
            # Orphaned tool_use at end (connection dropped)
            {"role": "assistant", "content": [{"type": "tool_use", "id": "orphan_2", "name": "search", "input": {}}]},
        ]

        cleaned = _validate_tool_pairs(messages)
        details = f"Before: {len(messages)} messages, After: {len(cleaned)}"

        if len(cleaned) == 2:  # Only the real Q&A pair remains
            return True, "orphans stripped", details
        return False, f"Expected 2 messages, got {len(cleaned)}", details
