"""
Intelligence benchmarking for the AI assistant.

Compares cross-referencing ability and latency across three configurations:
  - baseline:        Current system prompt, no thinking
  - rules:           Current prompt + cross-referencing rules, no thinking
  - rules_thinking:  Current prompt + cross-referencing rules + extended thinking

Tests 8 scenarios: 4 cross-referencing (the core problem) + 4 regression.

Usage:
    docker compose exec web python manage.py benchmark_intelligence
    docker compose exec web python manage.py benchmark_intelligence --config rules
    docker compose exec web python manage.py benchmark_intelligence --scenario implicit_entity_link
    docker compose exec web python manage.py benchmark_intelligence --verbose
"""

import time
from dataclasses import dataclass, field
from decimal import Decimal

from django.core.management.base import BaseCommand


SESSION_PREFIX = "[INTEL-BENCH]"

EXTRA_RULES = """
10. **Get full records before acting**: When you find an entity via search, ALWAYS call `get_record()` on it before using it in a plan. The search result is a preview — the full record has addresses, linked assets, relationships, and details you need. If the user says "at Jim's office" and you found Jim via search, get_record on Jim to find his actual address. Never use a search snippet when the full record is available.
11. **Search for every entity reference**: When the user mentions ANY noun that could be a record — a person, property, vehicle, aircraft, company, LLC, legal matter, loan — search for it, even if mentioned in passing or parenthetically. "Matt Jones (G600 Pilot)" means search for BOTH "Matt Jones" AND "G600". "Oak Ave contractor" means search for "Oak Ave". Batch all searches into one call. Missing a connection is always worse than an extra search.
12. **Link relationships on creation**: When creating a new stakeholder who has a described relationship to an existing entity (pilot of an aircraft, attorney for a legal matter, manager of a property, partner on an LLC), include that relationship in the creation plan. Search for the related entity first, then propose linking via the appropriate through model or M2M field.
"""

CONFIGS = {
    "baseline": {
        "extra_rules": "",
        "thinking": None,
        "temperature": None,  # Use DB setting
        "description": "Current production behavior",
    },
    "rules": {
        "extra_rules": EXTRA_RULES,
        "thinking": None,
        "temperature": None,
        "description": "Prompt + cross-referencing rules",
    },
    "rules_thinking": {
        "extra_rules": EXTRA_RULES,
        "thinking": {"type": "enabled", "budget_tokens": 4096},
        "temperature": Decimal("1.0"),  # Required for thinking
        "description": "Prompt + rules + extended thinking",
    },
}

SCENARIOS = {
    # --- Cross-referencing scenarios (the core problem) ---
    "implicit_entity_link": {
        "prompt": (
            "I have a meeting tomorrow with Jim Wood at his office at 3pm "
            "with Matt Jones (G600 Pilot). Set it up."
        ),
        "expected_facts": ["g600", "gulfstream", "pilot", "wood"],
        "min_facts": 3,  # Need at least 3 of 4
        "expected_searches": ["wood", "jones", "g600"],
        "description": "Cross-ref: implicit entity link via parenthetical hint",
        "category": "crossref",
    },
    "org_stakeholder_link": {
        "prompt": (
            "Add Aaron Swerdlow as a contact. He's the CEO of Equitas "
            "Investments and a partner on 314SG LLC."
        ),
        "expected_facts": ["swerdlow", "equitas", "314sg"],
        "min_facts": 3,
        "expected_searches": ["swerdlow", "equitas", "314sg"],
        "description": "Cross-ref: org + LLC linkage on stakeholder creation",
        "category": "crossref",
    },
    "property_context_lookup": {
        "prompt": (
            "What's the insurance situation on the Oak Ave property? "
            "And who manages it?"
        ),
        "expected_facts": ["oak", "insurance", "homeowner"],
        "min_facts": 2,
        "expected_searches": ["oak"],
        "description": "Cross-ref: property → insurance + manager follow-through",
        "category": "crossref",
    },
    "multi_hop_relationship": {
        "prompt": (
            "Which attorney is handling the Cedar Lane dispute? "
            "I need their contact info."
        ),
        "expected_facts": ["cedar", "attorney", "whitfield"],
        "min_facts": 2,
        "expected_searches": ["cedar"],
        "description": "Cross-ref: legal matter → attorney → contact info",
        "category": "crossref",
    },
    # --- Regression scenarios (must stay fast) ---
    "simple_query": {
        "prompt": "What are my overdue tasks?",
        "expected_facts": ["overdue"],
        "min_facts": 1,
        "expected_searches": [],
        "description": "Regression: simple filtered query",
        "category": "regression",
    },
    "simple_search": {
        "prompt": "Look up Tom Driscoll",
        "expected_facts": ["driscoll"],
        "min_facts": 1,
        "expected_searches": ["driscoll"],
        "description": "Regression: simple entity search",
        "category": "regression",
    },
    "system_overview": {
        "prompt": "Give me a quick summary of everything",
        "expected_facts": ["stakeholder", "task"],
        "min_facts": 2,
        "expected_searches": [],
        "description": "Regression: system overview via summarize",
        "category": "regression",
    },
    "email_processing": {
        "prompt": (
            "I got an email from Sandra Liu about the Magnolia Blvd due "
            "diligence. She needs the Phase 1 ESA report by next week. "
            "Create a task for this."
        ),
        "expected_facts": ["sandra", "magnolia", "esa"],
        "min_facts": 2,
        "expected_searches": ["sandra", "magnolia"],
        "description": "Regression: email-style creation with entity linking",
        "category": "regression",
    },
}


@dataclass
class RunResult:
    scenario: str
    config: str
    iterations: int
    tool_calls: int
    tools_per_iteration: float
    latency: float
    correct: bool
    facts_found: int
    facts_total: int
    searches_made: int = 0
    get_records_made: int = 0
    response_length: int = 0
    error: str = ""
    tool_names: str = ""


class Command(BaseCommand):
    help = "Benchmark assistant intelligence across prompt/thinking configurations."

    def add_arguments(self, parser):
        parser.add_argument(
            "--config", nargs="+", choices=list(CONFIGS.keys()),
            help="Run only specific configurations",
        )
        parser.add_argument(
            "--scenario", nargs="+", choices=list(SCENARIOS.keys()),
            help="Run only specific scenarios",
        )
        parser.add_argument(
            "--verbose", action="store_true",
            help="Show full responses and tool details",
        )

    def handle(self, *args, **options):
        self.verbose = options["verbose"]
        config_names = options["config"] or list(CONFIGS.keys())
        scenario_names = options["scenario"] or list(SCENARIOS.keys())

        from assistant.models import AssistantSettings
        settings = AssistantSettings.load()
        if not settings.get_effective_api_key():
            self.stderr.write(self.style.ERROR("No API key configured."))
            return

        original_temp = settings.temperature
        self._cleanup()

        total_calls = len(config_names) * len(scenario_names)
        self.stdout.write(self.style.NOTICE(
            f"Benchmarking {len(config_names)} configs x {len(scenario_names)} scenarios "
            f"= {total_calls} API calls"
        ))
        self.stdout.write(f"Model: {settings.model}")
        self.stdout.write(f"Configs: {config_names}")
        self.stdout.write("")

        results = []
        try:
            for config_name in config_names:
                config = CONFIGS[config_name]
                self.stdout.write(self.style.NOTICE(
                    f"Config: {config_name} — {config['description']}"
                ))
                for scenario_name in scenario_names:
                    scenario = SCENARIOS[scenario_name]
                    result = self._run_single(
                        config_name, config, scenario_name, scenario,
                    )
                    results.append(result)

                    status = (self.style.SUCCESS("OK") if result.correct
                              else self.style.WARNING("MISS"))
                    err = f"  ERROR: {result.error}" if result.error else ""
                    self.stdout.write(
                        f"  {scenario_name:<28s} iter={result.iterations}  "
                        f"tools={result.tool_calls}  "
                        f"srch={result.searches_made}  "
                        f"get={result.get_records_made}  "
                        f"{result.latency:.1f}s  "
                        f"facts={result.facts_found}/{result.facts_total}  "
                        f"{status}{err}"
                    )
                    if self.verbose and result.tool_names:
                        self.stdout.write(f"    Tools: {result.tool_names}")
                self.stdout.write("")
        finally:
            # Restore original settings
            import assistant.client as client_mod
            client_mod._EXTRA_RULES = ""
            settings = AssistantSettings.load()
            settings.temperature = original_temp
            settings.save()
            self._cleanup()

        self._print_report(results, config_names, scenario_names)

    def _cleanup(self):
        from assistant.models import ChatSession
        ChatSession.objects.filter(title__startswith=SESSION_PREFIX).delete()

    def _run_single(self, config_name, config, scenario_name, scenario):
        """Run one scenario under one configuration."""
        import assistant.client as client_mod
        from assistant.client import send_message
        from assistant.models import AssistantSettings, ChatSession

        # Apply config
        client_mod._EXTRA_RULES = config["extra_rules"]
        if config["temperature"] is not None:
            settings = AssistantSettings.load()
            settings.temperature = config["temperature"]
            settings.save()

        session = ChatSession.objects.create(
            title=f"{SESSION_PREFIX} {config_name}/{scenario_name}"
        )

        try:
            start = time.time()
            messages = send_message(
                session, scenario["prompt"], thinking=config["thinking"],
            )
            latency = time.time() - start

            # Extract metrics
            iterations = 0
            tool_calls = 0
            searches = 0
            get_records = 0
            tool_names = []
            response_text = ""

            for msg in messages:
                if msg.tool_data:
                    for block in msg.tool_data:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tool_calls += 1
                            name = block["name"]
                            tool_names.append(name)
                            if name == "search":
                                searches += 1
                            elif name == "get_record":
                                get_records += 1
                    if msg.role == "assistant":
                        iterations += 1
                if msg.role == "assistant" and msg.content:
                    response_text = msg.content

            # Check for API errors
            if response_text and "api error" in response_text.lower():
                return RunResult(
                    scenario=scenario_name, config=config_name,
                    iterations=0, tool_calls=0, tools_per_iteration=0,
                    latency=latency, correct=False, facts_found=0,
                    facts_total=len(scenario["expected_facts"]),
                    error=response_text[:100],
                )

            # Check correctness
            text_lower = response_text.lower()
            facts = scenario["expected_facts"]
            facts_found = sum(1 for f in facts if f.lower() in text_lower)
            min_facts = scenario.get("min_facts", len(facts))
            correct = facts_found >= min_facts

            tpi = tool_calls / iterations if iterations > 0 else 0

            return RunResult(
                scenario=scenario_name, config=config_name,
                iterations=iterations, tool_calls=tool_calls,
                tools_per_iteration=round(tpi, 1),
                latency=round(latency, 1), correct=correct,
                facts_found=facts_found, facts_total=len(facts),
                searches_made=searches, get_records_made=get_records,
                response_length=len(response_text),
                tool_names=", ".join(tool_names),
            )
        except Exception as e:
            return RunResult(
                scenario=scenario_name, config=config_name,
                iterations=0, tool_calls=0, tools_per_iteration=0,
                latency=0, correct=False, facts_found=0,
                facts_total=len(scenario["expected_facts"]),
                error=str(e)[:100],
            )

    def _print_report(self, results, config_names, scenario_names):
        self.stdout.write("=" * 80)
        self.stdout.write("INTELLIGENCE BENCHMARK RESULTS")
        self.stdout.write("=" * 80)

        # Per-scenario tables
        for sname in scenario_names:
            scenario = SCENARIOS[sname]
            self.stdout.write(f"\nScenario: {sname} [{scenario['category']}]")
            self.stdout.write(f"  {scenario['prompt'][:75]}...")
            self.stdout.write(
                f"  {'Config':<20s}  {'Iter':>4s}  {'Tools':>5s}  "
                f"{'Srch':>4s}  {'Get':>3s}  {'Time':>6s}  "
                f"{'Facts':>7s}  {'OK':>3s}"
            )
            self.stdout.write("  " + "-" * 70)
            for cname in config_names:
                r = next((r for r in results
                          if r.scenario == sname and r.config == cname), None)
                if not r:
                    continue
                ok = self.style.SUCCESS("YES") if r.correct else self.style.ERROR("NO ")
                err = f"  ERR: {r.error[:30]}" if r.error else ""
                self.stdout.write(
                    f"  {cname:<20s}  {r.iterations:4d}  {r.tool_calls:5d}  "
                    f"{r.searches_made:4d}  {r.get_records_made:3d}  "
                    f"{r.latency:5.1f}s  "
                    f"{r.facts_found}/{r.facts_total:>3d}  {ok}{err}"
                )

        # Aggregate by config
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("AGGREGATE SUMMARY")
        self.stdout.write("=" * 80)
        self.stdout.write(
            f"  {'Config':<20s}  {'Avg Time':>8s}  {'Correct':>8s}  "
            f"{'Avg Srch':>8s}  {'Avg Get':>7s}"
        )
        self.stdout.write("  " + "-" * 58)

        for cname in config_names:
            cr = [r for r in results if r.config == cname and not r.error]
            if not cr:
                self.stdout.write(f"  {cname:<20s}  {'(all errors)':>40s}")
                continue
            n = len(cr)
            self.stdout.write(
                f"  {cname:<20s}  {sum(r.latency for r in cr)/n:7.1f}s  "
                f"{sum(1 for r in cr if r.correct)/n*100:7.0f}%  "
                f"{sum(r.searches_made for r in cr)/n:8.1f}  "
                f"{sum(r.get_records_made for r in cr)/n:7.1f}"
            )

        # Cross-ref vs regression breakdown
        for category, label in [("crossref", "CROSS-REF SCENARIOS"),
                                ("regression", "REGRESSION SCENARIOS")]:
            self.stdout.write(f"\n  {label}:")
            self.stdout.write(
                f"  {'Config':<20s}  {'Avg Time':>8s}  {'Correct':>8s}  "
                f"{'Avg Srch':>8s}  {'Avg Get':>7s}"
            )
            self.stdout.write("  " + "-" * 58)
            cat_scenarios = {k for k, v in SCENARIOS.items()
                            if v["category"] == category}
            for cname in config_names:
                cr = [r for r in results
                      if r.config == cname and r.scenario in cat_scenarios
                      and not r.error]
                if not cr:
                    continue
                n = len(cr)
                self.stdout.write(
                    f"  {cname:<20s}  {sum(r.latency for r in cr)/n:7.1f}s  "
                    f"{sum(1 for r in cr if r.correct)/n*100:7.0f}%  "
                    f"{sum(r.searches_made for r in cr)/n:8.1f}  "
                    f"{sum(r.get_records_made for r in cr)/n:7.1f}"
                )

        self.stdout.write("\n" + "=" * 80)
