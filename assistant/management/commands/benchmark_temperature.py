"""
Temperature benchmarking for the AI assistant.

Runs identical complex scenarios at multiple temperature values against the
live Anthropic API to determine the optimal setting for tool-use efficiency,
correctness, and latency.

Usage:
    docker compose exec web python manage.py benchmark_temperature
    docker compose exec web python manage.py benchmark_temperature --temps 0.0 0.3 1.0
    docker compose exec web python manage.py benchmark_temperature --scenario system_overview
    docker compose exec web python manage.py benchmark_temperature --verbose
"""

import time
import traceback
from dataclasses import dataclass
from decimal import Decimal

from django.core.management.base import BaseCommand


SESSION_PREFIX = "[BENCH]"

DEFAULT_TEMPS = [0.0, 0.2, 0.5, 0.7, 1.0]

SCENARIOS = {
    "system_overview": {
        "prompt": (
            "Give me a complete overview of my system — stakeholders, tasks, "
            "properties, legal matters, overdue items, and upcoming appointments."
        ),
        "expected_facts": ["21", "29", "overdue"],
        "description": "System stats via summarize tool",
    },
    "multi_entity_search": {
        "prompt": (
            "Look up James Calloway, Alicia Moreno, Derek Vasquez, and Dr. Helen Park. "
            "For each person, tell me their entity type and organization."
        ),
        "expected_facts": ["calloway", "moreno", "vasquez", "park"],
        "description": "Batch search + get_record for 4 people",
    },
    "deep_property_exploration": {
        "prompt": (
            "Show me everything about 1200 Oak Avenue — property details, all owners, "
            "any loans, insurance, related legal matters, and linked tasks. Be thorough."
        ),
        "expected_facts": ["oak", "385", "austin"],
        "description": "Deep multi-tool property exploration",
    },
    "filtered_query_analysis": {
        "prompt": (
            "What are all my overdue tasks? For each one, show the title, priority, "
            "due date, and who it's assigned to. Then tell me which ones are critical priority."
        ),
        "expected_facts": ["overdue", "priority"],
        "description": "Filtered query with analysis",
    },
    "cross_model_correlation": {
        "prompt": (
            "Which of my stakeholders are connected to the most legal matters? "
            "Show me the top 3 with their legal matter details."
        ),
        "expected_facts": ["legal", "stakeholder"],
        "description": "Cross-model relationship analysis",
    },
    "email_style_create": {
        "prompt": (
            "I just got off a call with James Calloway. He needs to send us the updated "
            "contractor invoice for the Oak Avenue renovation by next Friday. Create a task "
            "for this — direction inbound, assigned to James, high priority. Just show me the preview."
        ),
        "expected_facts": ["preview", "james", "invoice"],
        "description": "Entity search + create_record dry_run",
    },
}


@dataclass
class RunResult:
    scenario: str
    temperature: float
    iterations: int
    tool_calls: int
    tools_per_iteration: float
    latency: float
    correct: bool
    facts_found: int
    facts_total: int
    response_length: int
    error: str = ""
    tool_names: str = ""


class Command(BaseCommand):
    help = "Benchmark assistant performance across temperature settings."

    def add_arguments(self, parser):
        parser.add_argument(
            "--temps", nargs="+", type=float, default=DEFAULT_TEMPS,
            help=f"Temperature values to test (default: {DEFAULT_TEMPS})",
        )
        parser.add_argument(
            "--scenario", nargs="+", choices=list(SCENARIOS.keys()),
            help="Run only specific scenarios",
        )
        parser.add_argument(
            "--verbose", action="store_true",
            help="Show full responses for each run",
        )

    def handle(self, *args, **options):
        self.verbose = options["verbose"]
        temps = sorted(options["temps"])
        scenario_names = options["scenario"] or list(SCENARIOS.keys())

        # Prerequisites
        from assistant.models import AssistantSettings
        settings = AssistantSettings.load()
        if not settings.get_effective_api_key():
            self.stderr.write(self.style.ERROR("No API key configured."))
            return

        original_temp = settings.temperature
        self._cleanup()

        self.stdout.write(self.style.NOTICE(
            f"Benchmarking {len(scenario_names)} scenarios x {len(temps)} temperatures "
            f"= {len(scenario_names) * len(temps)} API calls"
        ))
        self.stdout.write(f"Model: {settings.model}")
        self.stdout.write(f"Temperatures: {temps}")
        self.stdout.write("")

        results = []
        try:
            for scenario_name in scenario_names:
                scenario = SCENARIOS[scenario_name]
                self.stdout.write(self.style.NOTICE(
                    f"Scenario: {scenario_name} — {scenario['description']}"
                ))
                for temp in temps:
                    result = self._run_single(scenario_name, scenario, temp)
                    results.append(result)

                    status = self.style.SUCCESS("OK") if result.correct else self.style.WARNING("MISS")
                    err = f"  ERROR: {result.error}" if result.error else ""
                    self.stdout.write(
                        f"  temp={temp:.1f}  iter={result.iterations}  "
                        f"tools={result.tool_calls}  "
                        f"t/i={result.tools_per_iteration:.1f}  "
                        f"{result.latency:.1f}s  "
                        f"facts={result.facts_found}/{result.facts_total}  "
                        f"{status}{err}"
                    )
                    if self.verbose and not result.error:
                        self.stdout.write(f"    Tools: {result.tool_names}")
                self.stdout.write("")
        finally:
            # Restore original temperature
            settings = AssistantSettings.load()
            settings.temperature = original_temp
            settings.save()
            self._cleanup()

        self._print_report(results, temps, scenario_names)

    def _cleanup(self):
        from assistant.models import ChatSession
        ChatSession.objects.filter(title__startswith=SESSION_PREFIX).delete()

    def _run_single(self, scenario_name, scenario, temperature):
        """Run one scenario at one temperature."""
        from assistant.client import send_message
        from assistant.models import AssistantSettings, ChatSession

        # Set temperature
        settings = AssistantSettings.load()
        settings.temperature = Decimal(str(temperature))
        settings.save()

        session = ChatSession.objects.create(title=f"{SESSION_PREFIX} {scenario_name} t={temperature}")

        try:
            start = time.time()
            messages = send_message(session, scenario["prompt"])
            latency = time.time() - start

            # Extract metrics
            iterations = 0
            tool_calls = 0
            tool_names = []
            response_text = ""

            for msg in messages:
                if msg.tool_data:
                    for block in msg.tool_data:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tool_calls += 1
                            tool_names.append(block["name"])
                    if msg.role == "assistant":
                        iterations += 1
                if msg.role == "assistant" and msg.content:
                    response_text = msg.content

            # Check for API errors in response
            if "api error" in response_text.lower():
                return RunResult(
                    scenario=scenario_name, temperature=temperature,
                    iterations=0, tool_calls=0, tools_per_iteration=0,
                    latency=latency, correct=False, facts_found=0,
                    facts_total=len(scenario["expected_facts"]),
                    response_length=0, error=response_text[:100],
                )

            # Check correctness
            text_lower = response_text.lower()
            facts = scenario["expected_facts"]
            facts_found = sum(1 for f in facts if f.lower() in text_lower)

            tpi = tool_calls / iterations if iterations > 0 else 0

            return RunResult(
                scenario=scenario_name, temperature=temperature,
                iterations=iterations, tool_calls=tool_calls,
                tools_per_iteration=round(tpi, 1),
                latency=round(latency, 1), correct=(facts_found == len(facts)),
                facts_found=facts_found, facts_total=len(facts),
                response_length=len(response_text),
                tool_names=", ".join(tool_names),
            )
        except Exception as e:
            return RunResult(
                scenario=scenario_name, temperature=temperature,
                iterations=0, tool_calls=0, tools_per_iteration=0,
                latency=0, correct=False, facts_found=0,
                facts_total=len(scenario["expected_facts"]),
                response_length=0, error=str(e)[:100],
            )

    def _print_report(self, results, temps, scenario_names):
        self.stdout.write("=" * 75)
        self.stdout.write("TEMPERATURE BENCHMARK RESULTS")
        self.stdout.write("=" * 75)

        # Per-scenario tables
        for sname in scenario_names:
            scenario_results = [r for r in results if r.scenario == sname]
            self.stdout.write(f"\nScenario: {sname}")
            self.stdout.write(f"  {SCENARIOS[sname]['prompt'][:80]}...")
            self.stdout.write(
                f"  {'Temp':>5s}  {'Iter':>4s}  {'Tools':>5s}  "
                f"{'T/I':>5s}  {'Time':>6s}  {'Facts':>7s}  {'OK':>3s}  Tools Used"
            )
            self.stdout.write("  " + "-" * 70)
            for r in scenario_results:
                ok = self.style.SUCCESS("YES") if r.correct else self.style.ERROR("NO ")
                err = f"  ERR: {r.error[:40]}" if r.error else ""
                self.stdout.write(
                    f"  {r.temperature:5.1f}  {r.iterations:4d}  {r.tool_calls:5d}  "
                    f"{r.tools_per_iteration:5.1f}  {r.latency:5.1f}s  "
                    f"{r.facts_found}/{r.facts_total:>3d}  {ok}  "
                    f"{r.tool_names[:30]}{err}"
                )

        # Aggregate summary
        self.stdout.write("\n" + "=" * 75)
        self.stdout.write("AGGREGATE SUMMARY")
        self.stdout.write("=" * 75)
        self.stdout.write(
            f"  {'Temp':>5s}  {'Avg Iter':>8s}  {'Avg Tools':>9s}  "
            f"{'Avg T/I':>7s}  {'Avg Time':>8s}  {'Correct':>8s}"
        )
        self.stdout.write("  " + "-" * 55)

        best_temp = None
        best_score = -1

        for temp in temps:
            temp_results = [r for r in results if r.temperature == temp and not r.error]
            if not temp_results:
                self.stdout.write(f"  {temp:5.1f}  {'(all errors)':>40s}")
                continue

            n = len(temp_results)
            avg_iter = sum(r.iterations for r in temp_results) / n
            avg_tools = sum(r.tool_calls for r in temp_results) / n
            avg_tpi = sum(r.tools_per_iteration for r in temp_results) / n
            avg_time = sum(r.latency for r in temp_results) / n
            correct_pct = sum(1 for r in temp_results if r.correct) / n * 100

            self.stdout.write(
                f"  {temp:5.1f}  {avg_iter:8.1f}  {avg_tools:9.1f}  "
                f"{avg_tpi:7.1f}  {avg_time:7.1f}s  {correct_pct:7.0f}%"
            )

            # Score: correctness * 100 - avg_iterations * 10 - avg_time
            # Higher is better
            score = correct_pct - avg_iter * 10 - avg_time * 0.5
            if score > best_score:
                best_score = score
                best_temp = temp

        self.stdout.write("\n" + "=" * 75)
        if best_temp is not None:
            self.stdout.write(self.style.SUCCESS(
                f"RECOMMENDATION: temperature={best_temp:.1f} "
                f"(best balance of correctness, efficiency, and speed)"
            ))
        self.stdout.write("=" * 75)
