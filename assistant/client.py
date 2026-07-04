"""
Anthropic API client for the AI assistant.

Handles system prompt construction, message formatting,
and the tool-use loop.
"""

import json
import logging
import queue
import threading
import time

import anthropic
from django.conf import settings
from django.db import transaction

from . import registry
from .tools import TOOL_DEFINITIONS, TOOL_HANDLERS, summarize

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 25
# Anchored truncation (hysteresis), replacing the old fixed sliding window.
# A sliding window (always "last N") shifts the window start on EVERY turn
# once history exceeds N, so the byte prefix differs from position 0 each
# request — permanent message-cache miss. Instead the window start stays
# FIXED until the window exceeds TRUNCATION_HIGH_WATER, then jumps forward
# in one step to a user-text anchor leaving ~MAX_MESSAGES_TO_SEND messages:
# one cache miss per ~30 messages instead of one per turn.
MAX_MESSAGES_TO_SEND = 50  # low-water mark: window size right after a trim
TRUNCATION_HIGH_WATER = 80  # trim only once the window exceeds this
# Bridge any silent window longer than this with a keepalive comment frame.
# Must stay well under the client's 90s inactivity watchdog
# (static/js/assistant-chat.js resetWatchdog) with margin for jitter. 5s
# (down from 15s) also keeps more traffic on the wire during long thinking
# phases — every observed mid-stream disconnect (2026-06-01, 2026-06-12)
# happened in a window where only sparse keepalive frames were flowing.
HEARTBEAT_INTERVAL_SECONDS = 5
# After the client disconnects, the worker keeps consuming the tool loop so
# the turn completes and persists ("detached drain"). Bounded so a wedged
# upstream can't pin a gunicorn thread forever; generous because Opus 4.8 at
# high/max effort legitimately spends many minutes inside one turn.
DETACHED_DRAIN_BUDGET_SECONDS = 20 * 60
# Throttle for refreshing AssistantTurn.updated_at from the stream worker —
# frequent enough that the turn-status endpoint's staleness check
# (AssistantTurn.STALE_AFTER_SECONDS) never false-positives on a live turn.
TURN_TOUCH_INTERVAL_SECONDS = 30
CACHE_CONTROL = {"type": "ephemeral"}
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 8192
TITLE_MODEL = "claude-haiku-4-5-20251001"

# Ceiling for the NON-streaming path only. The SDK refuses non-streaming
# create() calls whose max_tokens imply >10 minutes of generation (it raises
# ValueError above 21,333 tokens: 600s at its assumed 128k tokens/hour).
# The streaming path has no such limit and carries the full mode budget.
NONSTREAMING_MAX_TOKENS = 20_480

# Appended to a response that stopped because it hit the max_tokens output cap,
# so a truncated answer is visible to the user instead of being silently cut
# off. Opus 4.7+ count tokens higher and effort:max spends more of the budget on
# thinking (which shares the output ceiling), so surfacing truncation matters.
TRUNCATION_NOTICE = (
    "\n\n_[Response truncated — it reached the output limit. "
    "Ask me to continue.]_"
)

# Visible notices for the other 4.7+ terminal stop_reasons, mirroring the
# max_tokens handling: a stopped response must never look complete.
CONTEXT_WINDOW_NOTICE = (
    "\n\n_[Response stopped — this conversation has filled the model's "
    "context window. Start a new chat or prune older messages.]_"
)
REFUSAL_NOTICE = (
    "\n\n_[The model declined to generate this response. "
    "Try rephrasing your request.]_"
)


def _stop_reason_notice(response):
    """Return the visible notice for a terminal stop_reason, or ""."""
    return {
        "max_tokens": TRUNCATION_NOTICE,
        "model_context_window_exceeded": CONTEXT_WINDOW_NOTICE,
        "refusal": REFUSAL_NOTICE,
    }.get(getattr(response, "stop_reason", None), "")

# Models that accept the `temperature` sampling parameter. Anthropic removed
# temperature/top_p/top_k on Opus 4.7 and later — sending temperature to those
# returns HTTP 400. temperature is attached ONLY for models matching this
# allowlist (prefix match, so dated ids like "...-20251001" are covered), so an
# unrecognized or future model fails SAFE: temperature is omitted and the model
# uses its own default rather than erroring. Add a prefix only for a model that
# supports temperature. (Modes that enable thinking never send temperature.)
TEMPERATURE_CAPABLE_PREFIXES = (
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
    "claude-opus-4-6",
)

# Injection point for benchmark-injected system prompt rules.
# Set by benchmark_intelligence to test prompt variations.
_EXTRA_RULES = ""

# Per-message mode configurations.
# Think/Max force specific models to guarantee adaptive thinking support.
MODE_CONFIGS = {
    "fast": {},  # Uses settings as-is
    # display must stay pinned to "summarized" on every thinking mode: Opus
    # 4.7+ default to "omitted", which streams NO thinking_delta events while
    # the model thinks — and the SSE keepalive (client watchdog kills the
    # stream after 90s of silence) is driven by those deltas. Same cost
    # either way; "summarized" matches the Opus 4.6 streaming behavior the
    # keepalive architecture was built against.
    "think": {
        "model": "claude-sonnet-4-6",
        "thinking": {"type": "adaptive", "display": "summarized"},
        "output_config": {"effort": "high"},
        "max_tokens": 16384,
    },
    "max": {
        "model": "claude-opus-4-8",
        "thinking": {"type": "adaptive", "display": "summarized"},
        "output_config": {"effort": "max"},
        # Opus 4.8 counts tokens higher than 4.6, and effort:max spends more on
        # thinking — which shares this budget with the visible output. Give extra
        # headroom to reduce truncation; streaming handles the larger ceiling.
        "max_tokens": 32768,
    },
}


def _model_accepts_temperature(model_name):
    """True if ``model_name`` accepts the temperature sampling parameter.

    Opus 4.7+ removed temperature/top_p/top_k (HTTP 400 if sent). Unrecognized
    models fail safe — temperature is omitted and the model uses its default.
    """
    return bool(model_name) and model_name.startswith(TEMPERATURE_CAPABLE_PREFIXES)


# Process-wide Anthropic client cache. Constructing a fresh client per turn
# pays a new httpx pool + TCP/TLS handshake (~100-300ms of TTFT); the SDK
# client is documented thread-safe, so one instance per (api_key, retries)
# pair is shared across gunicorn threads and the stream worker threads.
# The factory identity check exists for the test suite: tests patch
# ``assistant.client.anthropic.Anthropic`` per-test, and a cached client
# built from a previous test's mock (or the real class) must never leak
# into the next test.
_CLIENT_CACHE = {}
_CLIENT_CACHE_LOCK = threading.Lock()
_CLIENT_FACTORY = None


def _get_shared_client(api_key, max_retries):
    """Return a cached Anthropic client, rebuilt only when the key (or the
    client class itself) changes."""
    global _CLIENT_FACTORY
    factory = anthropic.Anthropic
    with _CLIENT_CACHE_LOCK:
        if factory is not _CLIENT_FACTORY:
            _CLIENT_CACHE.clear()
            _CLIENT_FACTORY = factory
        cache_key = (api_key, max_retries)
        client = _CLIENT_CACHE.get(cache_key)
        if client is None:
            client = factory(api_key=api_key, max_retries=max_retries)
            _CLIENT_CACHE[cache_key] = client
        return client


# Tools that are conditionally registered — included in the active tools
# array when their trigger marker is present anywhere in the conversation's
# user-authored free text. Keeps the toolset byte-identical to pre-feature
# behavior for sessions that never reference the relevant attachment.
_GATED_TOOL_NAMES = {"bulk_link_drive_files"}


def _get_active_tools(messages):
    """Return TOOL_DEFINITIONS, with marker-gated tools included when their
    trigger marker appears anywhere in the conversation's user-authored text.

    Walking the full user-message history (not just the most recent one) is
    required so the gated tool stays reachable on follow-up turns — e.g. after
    the user types "yes confirm" in a separate turn, the dry_run=False execute
    step must still see bulk_link_drive_files in the active tool set.

    User messages whose content is purely tool_result blocks (Anthropic's
    tool-use protocol writes those as role=user) contribute no text and are
    skipped naturally by the text-block extraction.

    Currently gated:
      - bulk_link_drive_files: included while [AttachedDriveFiles] appears in
        any prior user message of the active conversation.
    """
    drive_marker_present = False
    for m in messages or []:
        if m.get("role") != "user":
            continue
        content = m.get("content", "")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = "".join(
                blk.get("text", "")
                for blk in content
                if isinstance(blk, dict) and blk.get("type") == "text"
            )
        else:
            text = ""
        if "[AttachedDriveFiles]" in text:
            drive_marker_present = True
            break

    active = []
    for tool in TOOL_DEFINITIONS:
        if tool["name"] in _GATED_TOOL_NAMES and not drive_marker_present:
            continue
        active.append(tool)
    return active


SYSTEM_PREAMBLE = """You are the Control Center Assistant — an AI built into a personal management system. You help the user manage their stakeholders, legal matters, assets, tasks, notes, cash flow, healthcare records, documents, and checklists.

## Your capabilities
- Search and query any data in the system using the provided tools
- Create, update, and delete records (with user confirmation)
- Answer complex questions by combining data from multiple sources
- Provide summaries and insights about the user's affairs
- Create and manage **checklists** on any entity (stakeholders, tasks, notes, properties, legal matters) — useful for tracking itemized lists like "documents to request from Thomas" or "due diligence items for a property". Checklists have two modes via `is_reference` (default `False`). Leave `is_reference=False` for trackable work (checkboxes, optional due date, surfaces on the dashboard as outstanding items). Set `is_reference=True` for bullet-style notes that should NOT appear as outstanding work on the dashboard — e.g., "questions to ask Thomas next time", "topics for next meeting", "features I'm considering for the remodel", "people Stan mentioned in passing". Pick based on whether the items are *work to finish* (tracked) or *context to remember* (reference).

## Critical rules
1. **Write operations**: ALWAYS use dry_run=true first to preview changes. Show the preview to the user and explicitly ask for confirmation before executing with dry_run=false. NEVER skip the preview step.
2. **Be precise**: When querying data, use specific filters rather than loading everything. Start narrow, broaden if needed.
3. **Show your work**: When answering complex questions, briefly explain which queries you're running so the user understands.
4. **Links**: When referencing records, include their URL so the user can click through. ALWAYS use root-relative paths that start with a leading slash, exactly as returned by the tools (e.g., `/stakeholders/482/` — note the leading `/`). Copy the URL string from the tool's result verbatim — do not reformat, trim, or drop the leading slash. NEVER prepend a host, port, or protocol — no `http://localhost` or any domain.
5. **Dates**: Today's date is provided in the [System context] block appended to the latest user message. Use it for relative date calculations.
6. **Be concise**: Give direct answers. Use markdown formatting for readability — tables for comparisons, lists for enumerations, bold for key facts. In record previews and creation plans, always use human-readable labels (e.g. "Provider type", "Visit type", "Status") — never expose raw field names like snake_case identifiers.
7. **Batch tool calls aggressively**: Every API round-trip adds latency. Always call as many tools as possible in a single response. If you need to search for 15 entities, call search() 15 times in one response — do NOT split them across multiple iterations. Fewer iterations = faster results for the user.
8. **Meetings vs Appointments**: For scheduling meetings (business, legal, personal), create a `Task` with `task_type="meeting"` and set `due_date` + `due_time`. The `Appointment` model is ONLY for medical/healthcare appointments (doctor visits, lab work, etc.) — never use it for general meetings.
9. **Task links**: To attach reference links to a task, create `TaskLink` records (model: TaskLink, fields: task, url, label). Each TaskLink has a `task` FK (the task ID), a `url` (required), and an optional `label`. A task can have multiple links. Use this for articles, documents, external resources, websites — anything that isn't a video call join link. The `meeting_url` field on Task is exclusively for Zoom/Teams/Meet join URLs.
10. **Get full records before acting**: When you find an entity via search, ALWAYS call `get_record()` on it before using it in a plan. The search result is a preview — the full record has addresses, linked assets, relationships, and details you need. If the user says "at Jim's office" and you found Jim via search, get_record on Jim to find his actual address. Never use a search snippet when the full record is available.
11. **Search for every entity reference**: When the user mentions ANY noun that could be a record — a person, property, vehicle, aircraft, company, LLC, legal matter, loan — search for it, even if mentioned in passing or parenthetically. "Matt Jones (G600 Pilot)" means search for BOTH "Matt Jones" AND "G600". "Oak Ave contractor" means search for "Oak Ave". Batch all searches into one call. Missing a connection is always worse than an extra search.
12. **Link relationships on creation**: When creating a new stakeholder who has a described relationship to an existing entity (pilot of an aircraft, attorney for a legal matter, manager of a property, partner on an LLC), include that relationship in the creation plan. Search for the related entity first, then propose linking via the appropriate through model or M2M field.

## Email & meeting notes processing

When the user asks you to **process** a long email, meeting notes, or multi-party correspondence (i.e., extract entities and action items), follow the steps below. The goal is to extract every actionable piece of information and get it into the system with full cross-linking — so nothing falls through the cracks. If the user gives a different instruction (e.g., summarize, draft a reply, extract only action items), follow that instruction instead of the full extraction pipeline.

When the content includes structured thread markers (e.g., "--- Message 1 ---", "From:", "Date:" headers), this is a multi-message Gmail thread. Parse each message individually. Pay attention to:
- The chronological flow — messages are in order, most recent is usually most actionable
- Different senders across messages — each may have different action items
- Quoted/forwarded content within messages (often prefixed with ">") — avoid creating duplicate action items from quoted text
- Email signatures and legal disclaimers — ignore these entirely

### Step 1: Parse & identify all entities
Read the entire text carefully and extract:
- **People**: every person mentioned by name, role, or title
- **Assets**: properties, investments, loans, LLCs, vehicles, aircraft, credit lines, bank accounts
- **Action items**: tasks with assignees, deadlines, and context
- **Follow-ups**: items requiring outreach or waiting on a response
- **Legal matters**: cases, disputes, compliance items referenced
- **Relationships**: who is connected to what (attorney for a matter, lender on a loan, manager of a property, etc.)

### Step 2: Search before creating — never duplicate
For **every** person and asset identified, call `search()` to check if it already exists. **Batch ALL searches into a single iteration** — if you identified 15 entities, make 15 search() calls in one response. Do NOT search incrementally (4 now, 4 later). One big batch is much faster than many small batches. Search by name, and if ambiguous, also search by organization, address, or related details. If a search returns possible matches, use `get_record()` to inspect them before deciding. **Never create a record that already exists.** Keep search queries short — use just the name or a key identifier (e.g., search "N525BL" not "Cessna Citation CJ3+ N525BL"). The search uses substring matching, so shorter queries find more.

### Step 3: Present a structured plan before creating anything
Show the user a clear summary organized as follows:

**Found in system:**
- [Name] — [Model] — [link to record]
- ...

**New records to create:**
- Stakeholder: [Name] (entity_type: [type], organization: [if known])
- RealEstate / Investment / Loan / etc.: [Name] (key details)
- ...

**Tasks to create:**

| # | Title | Assignee | Priority | Due | Direction |
|---|-------|----------|----------|-----|-----------|
| 1 | ... | ... | ... | ... | outbound/personal/inbound |

**Checklists** (grouped under entity):
- Checklist name → on [entity type] "[name]"
  - [ ] Item 1
  - [ ] Item 2

**Action items to add to existing meeting** (if a meeting exists at the same time):
- Meeting: [meeting title]
  - [ ] Action item (as ChecklistItem on a Checklist linked to the meeting task)

**Note to save:**
- Title: [email subject or descriptive summary]
- Type: email
- Content: the full email text
- Linked to: [all relevant stakeholders, assets, legal matters]

**Wait for user confirmation** before creating anything. Let them adjust, remove, or add items.

### Step 4: Execute in dependency order
Records must be created in this order because later records reference earlier ones by ID:
1. **Stakeholders** — people and organizations (need their IDs for everything else)
2. **Assets** — RealEstate, Investment, Loan, Vehicle, Aircraft (link stakeholders via ownership through models where applicable)
3. **Legal matters** — if referenced (link related_stakeholders and related assets)
4. **Tasks** — link to related_stakeholders, related_property, related_legal_matter as appropriate. **Before creating a new task, search for existing meetings at the same date/time.** If a meeting already exists at the same time, create the action item as a ChecklistItem on that meeting (via a Checklist linked to the meeting task) instead of a separate standalone task. This keeps the calendar clean and groups related items.
5. **Checklists** — named checklists on any entity. Use a Checklist (model: Checklist) with a name and the appropriate FK (related_stakeholder, related_task, related_note, related_property, related_legal_matter), then create ChecklistItem records under it. Example: "items to request from Thomas: W-9, operating agreement, bank statements" → create a Checklist named "Items to request" on Thomas's stakeholder (related_stakeholder=Thomas's ID), with 3 ChecklistItems. Also create a companion Task for the follow-up workflow ("Follow up with Thomas on document request", direction=inbound, status=waiting, assigned_to=Thomas).
6. **Note** — the email/meeting content itself, linked to all created and found entities via participants, related_stakeholders, related_properties, related_investments, related_loans, related_legal_matters, etc.

Use `create_record` with `dry_run=true` for the batch. After the user confirms, execute all with `dry_run=false`.

### Step 5: Task assignment conventions
Use the `assigned_to` field (FK to Stakeholder) for the person responsible for the task. This is distinct from `related_stakeholders` (M2M for people involved/referenced).
- **"Amanda: do X"** or **"Amanda needs to handle X"** → `direction="outbound"`, `assigned_to=Amanda's stakeholder ID`
- **"I need to do X"** or **"reminder: X"** or self-directed items → `direction="personal"`, `assigned_to` left blank
- **"Waiting on Thomas for X"** or **"Thomas to send us X"** → `direction="inbound"`, `status="waiting"`, `assigned_to=Thomas's stakeholder ID`
- **Nested lists** like "items to request from Thomas: A, B, C" → create a **Checklist** on Thomas's stakeholder ("Items to request from Thomas") with ChecklistItems A, B, C, PLUS a companion **Task** ("Follow up with Thomas on document request", direction=inbound, status=waiting, assigned_to=Thomas). The checklist tracks the *what*, the task tracks the *when*.
- **Inline replies** from team members (e.g., "> Amanda: I'll handle the filing") → outbound task, `assigned_to=Amanda`
- Use `related_stakeholders` for other people mentioned in the task who are not the assignee (e.g., a property owner referenced in context)

### Step 6: Smart defaults
**Priority** — infer from language cues in the email:
- "ASAP", "urgent", "immediately", "critical" → `priority="critical"`
- "need to", "important", "must", "required" → `priority="high"`
- "should", "look into", "would be good to" → `priority="medium"`
- "when time allows", "eventually", "low priority", "nice to have" → `priority="low"`
- No cue → default to `priority="medium"`

**Due dates** — resolve relative references against today's date (from the [System context] block):
- "next week Thursday" → calculate the actual date
- "end of month" → last day of current month
- "by Friday" → the coming Friday
- "ASAP" with no date → tomorrow
- No deadline mentioned → leave `due_date` blank

**Stakeholder entity_type** — valid values are listed in the [System context] block. Use these inference rules:
- Company, firm, corporation, LLC, Inc., LLP, organization → "firm"
- Attorney, lawyer, counsel, partner (at a law firm) → "attorney"
- Bank, lender, credit line → "lender"
- Developer, builder, contractor, architect → "business_partner"
- Advisor, CPA, accountant, financial planner, consultant → "advisor"
- Doctor, physician, specialist → "professional"
- Individual person with no clear role → "contact"
When creating a firm and its employees, create the firm first (entity_type="firm"), then create each person with `parent_organization` set to the firm's ID. This links them as team members under the firm.

### Step 7: Google Drive file attachments
When the user's message contains an `[AttachedDriveFiles]` block, the user has selected Google Drive files to be linked as Documents in the system. The block format is:

```
[AttachedDriveFiles]
[{"id": "...", "name": "...", "mimeType": "...", "url": "..."}, ...]
[/AttachedDriveFiles]
```

The middle line is a JSON list of file dicts.

Workflow:
1. **Identify the target entity.** The user will name it ("attach to the Smith Property", "link to Stakeholder John Smith", etc.). Use `search` to resolve it and `get_record` to confirm. If the user is asking you to first CREATE a new entity from an attached email AND link these files to it, do `create_record` for the entity first (with its own dry_run preview and confirmation), then proceed.
2. **Preview with dry_run=true.** Call `bulk_link_drive_files` with `entity_type` (one of: realestate, investment, loan, lease, policy, vehicle, aircraft, stakeholder, legalmatter), `entity_id`, the full `files` list (verbatim from the block), and `dry_run=true`. The response shows which files would be created vs reused (dedupe by gdrive_file_id).
3. **Show the user.** Present the preview as a structured markdown block:
   > **About to attach N files to {Entity Name}** (RealEstate · #18)
   > - Term Sheet.pdf (new)
   > - NDA-Smith-2026.pdf (already exists, will reuse)
   >
   > Confirm to proceed.
4. **Wait for confirmation.** Do not execute until the user replies with confirmation ("yes", "confirm", "go ahead", "do it", or similar). If they amend the target ("actually link to the Investment instead"), restart at step 1.
5. **Execute with dry_run=false.** Same arguments, dry_run=false. Report the result concisely ("Linked 2 documents to Smith Property — 1 new, 1 reused").

Never call bulk_link_drive_files with dry_run=false on the same turn as the dry_run=true preview. Always wait one full user turn for confirmation.

When the message also contains an `[AttachedEmail]` or `[AttachedEmails]` block AND the user is asking you to extract entities from the email AND link the files (the common combined-flow case), do steps 1-5 of the email pipeline first (search → plan → confirm → execute), then proceed with steps 1-5 above for the files. The email's plan and the files' plan can be presented together in a single Step 3 plan if it makes the user's review faster.

## Linked email content
Entities (tasks, stakeholders, properties, legal matters, etc.) may have linked Gmail threads via EmailLink records. EmailLink stores subject, sender, and date — but NOT the email body.
When you call get_record on an entity, the response includes an `email_links` field with linked email summaries (id, subject, sender). You can also discover linked emails via: `query(model="EmailLink", filters={"related_task__id__exact": ID})` (replace `related_task` with `related_stakeholder`, `related_property`, `related_legal_matter`, etc. as appropriate).
When answering a query and the record data alone doesn't have the answer, fetch email content: `read_email(id=EMAILLINK_ID)`. When in doubt about whether an email is relevant, read it — missing buried information is worse than reading an extra email.
This is especially important when the user asks general questions — the answer may be buried in a linked email even if the user doesn't mention emails.

## Linked documents
Entities may have attached Documents (PDFs, DOCX, XLSX, Google Docs/Sheets/Slides, etc.) — closing statements, appraisals, leases, insurance policies, capital call schedules, and so on. The `Document` record stores metadata (title, filename, category, mime type, Drive link or local file) — NOT the file contents.
When you call get_record on an entity, the response includes a `documents` field listing linked documents as `{id, str}` pairs (where `str` is the document title). To read the actual content, call `read_document(id=DOC_ID)`. Supported formats: PDF, DOCX, XLSX, Google Docs/Sheets/Slides, plain text/CSV/markdown. Other formats and scanned PDFs return an explicit error or warning — when that happens, tell the user directly rather than guessing at the content.
When the user's question can't be fully answered from record metadata alone and a relevant-looking document is linked, read it. When in doubt, read it — missing buried information is worse than reading an extra document. Batch multiple `read_document` calls in a single iteration when several documents may be relevant (e.g., comparing terms across three insurance policies). Always cite the document by title in your answer so the user knows where the information came from.

**Truncation and pagination.** The `read_document` response includes a `truncated` flag plus `total_chars`, `offset`, and `next_offset`. If `truncated` is true, you only saw characters `offset`–`next_offset` of a `total_chars`-character document — content past the cutoff is NOT in your context. Rules:
1. Tell the user the document was truncated (e.g., "I read the first ~30 pages of the 50-page agreement").
2. NEVER cite, quote, paraphrase, or infer section numbers, clause text, exhibit contents, article titles, page numbers, or any specifics from positions past the slice you actually read. Do not fill gaps from training knowledge of how similar documents are typically structured.
3. If the user's question likely needs content past the cutoff, call `read_document` again with `offset=<next_offset>` to continue reading. You can chain these calls across turns if needed.
4. If a full read isn't practical (very large document, broad question), tell the user and ask them to narrow the question.

## Page context hints
When the user sends a message from the quick assistant drawer, the message may begin with a context hint like `[Context: viewing Stakeholder #482 "Thomas Wright"]`. This tells you what page the user is currently looking at. Use this context to understand what entity they're referring to (e.g., "what tasks does this person have?" means the stakeholder in the context). Do NOT repeat the context hint back to the user — just use it to inform your response.

## Attached email context
When a user message starts with `[AttachedEmail:{...JSON...}]`, the user has attached a Gmail email for reference. The JSON metadata includes thread_id, subject, from_name, from_email, and message_count. The full thread text follows, ending with `[/AttachedEmail]`. The user's actual question comes after the closing marker.

When a user message starts with `[AttachedEmails]`, the user has attached multiple Gmail threads for reference. The block contains a JSON list. Each item includes thread_id, subject, from_name, from_email, message_count, and thread_text. The block ends with `[/AttachedEmails]`, and the user's actual question comes after the closing marker. Treat each item as a separate email thread, but process the selected set together when the user's instruction asks for a batch summary, extraction, filing, or comparison.

Use the email content to inform your response. When creating records (tasks, notes, etc.) based on this email, also create an EmailLink record to connect them:
`create_record("EmailLink", {"message_id": "<thread_id from metadata>", "subject": "...", "from_name": "...", "from_email": "...", "message_count": N, "related_task": <new_task_id>})`
Replace `related_task` with the appropriate FK field for the entity type (related_note, related_stakeholder, related_property, etc.).
For `[AttachedEmails]`, create one EmailLink per attached thread when linking the emails to records.

**Common pattern — reference-list summary of an attached email:** When the user attaches an email and asks you to save, summarize, capture, file, note, or log it on an entity (stakeholder, property, task, note, legal matter) — or gives any similar instruction without specifying the output format — the preferred output is a **reference-mode Checklist** (`is_reference=True`) on that entity with 3–8 concise bullets distilling the key facts, decisions, asks, dates, and context. Each bullet should be self-contained and scannable (e.g., "Thomas confirmed W-9 will arrive by 2026-05-01", "Deal closing pushed to end of Q2 pending title review", "Amanda to loop in the CPA before signing"). Pair the Checklist with an EmailLink on the same entity (same FK field) so the full thread stays one click away. Do NOT create a companion follow-up Task — reference checklists are summaries, not work items. This is how the user captures scannable, pinned summaries of email content inside the relevant record.

Do NOT repeat the attached email metadata or raw text back to the user — just use it to inform your response.

## Data model
The system contains the following models and fields:
"""


def _build_system_prompt():
    """Construct the static system prompt (preamble + schema) as a single
    cacheable block.

    This MUST stay byte-identical across requests: system renders before
    messages in the cache prefix, so any volatile byte here invalidates
    every message-level cache entry downstream. All dynamic content (date,
    live record counts, settings-derived policy) lives in
    ``_build_turn_context()`` instead, appended to the latest user message
    at request-build time — a change there invalidates nothing before it.
    """
    schema = registry.get_schema_text()
    return [
        {
            "type": "text",
            "text": SYSTEM_PREAMBLE + _EXTRA_RULES + schema,
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        },
    ]


# First line of every injected turn-context message. Cache-marker anchor
# selection uses it to tell the request-scoped context apart from text the
# user actually typed (both are plain-string user messages).
TURN_CONTEXT_HEADER = (
    "[System context — auto-generated for this turn; not typed by the user]"
)


def _build_turn_context():
    """Live per-turn context: today's date, timezone/datetime guidance,
    reminder policy, owner, valid entity types, and record counts.

    Returned as plain text that ``_inject_turn_context`` appends as a
    trailing user message when the request is built (never persisted to
    ChatMessage rows). This content used to be an uncached second system
    block — because system renders before messages, every count change
    (i.e. every write the assistant made) and every date rollover killed
    the whole message cache. At the tail of the newest user turn it is
    rebuilt each turn but invalidates only itself.
    """
    stats = summarize()

    stats_lines = [
        TURN_CONTEXT_HEADER,
        "## Current system state",
    ]
    from django.utils import timezone
    from django.conf import settings as dj_settings
    stats_lines.append(f"Today: {timezone.localdate().isoformat()}")
    stats_lines.append(
        f"Timezone: {dj_settings.TIME_ZONE} "
        f"(all dates you see and write are in this zone unless tagged otherwise)"
    )
    stats_lines.append(
        "When writing datetime fields (e.g., Note.date, Task.due_date+due_time, "
        "appointment times), emit the datetime in the user's local timezone. "
        "Prefer full ISO format with explicit offset "
        "(e.g., '2026-04-20T19:27:00-07:00'). If you only have a raw email header "
        "in UTC, convert it to local time first."
    )

    # Include assistant settings
    from .models import AssistantSettings
    settings = AssistantSettings.load()
    owner_name = settings.owner_name
    reminder_mins = settings.default_reminder_minutes
    reminder_lines = [
        "Reminder policy:",
        "- For task_type='meeting': leave reminder_date blank. Meeting reminders come"
        " from Settings > Calendar Feed (user-configured per-category offsets).",
    ]
    if reminder_mins:
        reminder_lines.append(
            f"- For other task types with a due_date and due_time: do NOT set"
            f" reminder_date yourself — the server auto-sets it to {reminder_mins}"
            f" minutes before the due datetime."
        )
    else:
        reminder_lines.append(
            "- Auto-reminders are disabled in settings (default_reminder_minutes=0)."
            " Do NOT set reminder_date unless the user explicitly asks for a"
            " specific reminder time."
        )
    reminder_lines.append(
        "- If the user explicitly asks for a specific one-off reminder time, include"
        " reminder_date as a full ISO datetime with offset like"
        " '2026-04-22T15:30:00-07:00'."
    )
    stats_lines.append("\n".join(reminder_lines))
    if owner_name:
        stats_lines.append(f"System owner: {owner_name}")
        stats_lines.append(
            f"When processing emails, do NOT create a stakeholder record for {owner_name} — "
            f"that is the user. Messages from {owner_name} are first-person context. "
            f"Extract their commitments as personal tasks (direction=personal, no assigned_to)."
        )

    # Include valid entity types from DB (stays in sync with Settings > Manage Choices)
    from dashboard.choices import get_choices
    entity_types = get_choices("entity_type")
    if entity_types:
        type_list = ", ".join(f'"{val}"' for val, _label in entity_types)
        stats_lines.append(f"Valid stakeholder entity_type values: {type_list}")

    for key, value in stats.items():
        label = key.replace("_", " ").title()
        stats_lines.append(f"- {label}: {value}")

    return "\n".join(stats_lines)


def _inject_turn_context(api_messages, context_text):
    """Return a copy of ``api_messages`` with ``context_text`` appended as
    its own trailing user message.

    Request-scoped only — ChatMessage rows are never touched, and
    consecutive user messages are legal (the API merges them into a single
    turn). A SEPARATE message — rather than concatenating onto the user's
    message — keeps every persisted message's bytes identical from turn to
    turn, so the context (the only per-turn volatile content) is also the
    only thing each new turn re-processes; the history prefix keeps cache-
    chaining across turns. Within a turn's tool loop the context sits early
    in the growing list and is byte-stable across iterations.
    """
    if not context_text:
        return api_messages
    return list(api_messages) + [{"role": "user", "content": context_text}]


def _tool_use_ids(msg):
    """IDs of tool_use blocks in an API message (empty for non-list content)."""
    content = (msg or {}).get("content")
    if isinstance(content, list):
        return {
            b.get("id") for b in content
            if isinstance(b, dict) and b.get("type") == "tool_use"
        }
    return set()


def _tool_result_ids(msg):
    """tool_use_ids referenced by tool_result blocks in an API message."""
    content = (msg or {}).get("content")
    if isinstance(content, list):
        return {
            b.get("tool_use_id") for b in content
            if isinstance(b, dict) and b.get("type") == "tool_result"
        }
    return set()


def _validate_tool_pairs(messages):
    """
    Ensure tool_use and tool_result messages are properly paired, ANYWHERE
    in the list — not just at the ends. The Anthropic API returns HTTP 400
    for the whole request if any assistant tool_use is not answered by a
    tool_result in the very next (user) message, so a single unpaired
    message left in history bricks the session permanently. Repairing
    mid-list orphans here makes an already-corrupted session self-heal on
    its next turn.

    Handled cases:
    1. Truncation sliced off a tool_use, leaving an orphaned tool_result
       at the start.
    2. A crash between saving the tool_use message and its tool_result
       (deploy, OOM, container restart) — orphan anywhere in the list.
    3. A tool_result message whose preceding assistant tool_use is missing
       or doesn't match its ids.
    4. The list starting on a non-user message (the API requires the first
       message to be role "user") — e.g. after truncation or after this
       repair dropped a leading message.
    5. Messages with empty content ("", [], None) — the API rejects them
       on replay.

    Returns a cleaned copy of the message list.
    """
    if not messages:
        return messages

    result = []
    i = 0
    n = len(messages)
    while i < n:
        msg = messages[i]

        # Empty content ("", [], None) is rejected by the API on any
        # replayed message — drop it so this corruption class also
        # self-heals instead of leaving the session bricked.
        if not msg.get("content"):
            logger.warning("Dropping message with empty content at index %d", i)
            i += 1
            continue

        use_ids = _tool_use_ids(msg) if msg.get("role") == "assistant" else set()
        res_ids = _tool_result_ids(msg) if msg.get("role") == "user" else set()

        if use_ids:
            nxt = messages[i + 1] if i + 1 < n else None
            nxt_res_ids = (
                _tool_result_ids(nxt)
                if nxt is not None and nxt.get("role") == "user"
                else set()
            )
            # A valid pair answers every tool_use id, and references no
            # id outside this assistant message (a stray extra tool_result
            # is also a 400).
            if use_ids == nxt_res_ids:
                result.append(msg)
                result.append(nxt)
                i += 2
                continue
            # Unpaired tool_use — drop the assistant message. A partial or
            # mismatched tool_result message (if any) is handled by the
            # res_ids branch on the next iteration.
            logger.warning(
                "Dropping assistant message with unpaired tool_use at index %d", i
            )
            i += 1
            continue

        if res_ids:
            # tool_result whose paired assistant tool_use is missing (or was
            # dropped above) — the API rejects unexpected tool_use_ids.
            logger.warning(
                "Dropping user message with orphaned tool_result at index %d", i
            )
            i += 1
            continue

        result.append(msg)
        i += 1

    # Final normalization: the first message must be role "user" and must
    # not itself be a tool_result message (its tool_use partner would have
    # to precede it). Valid pairs are consumed together above, so dropping
    # a leading assistant message can expose its (kept) tool_result — the
    # loop keeps trimming until the head is a genuine user message.
    while result:
        first = result[0]
        if first.get("role") == "user" and not _tool_result_ids(first):
            break
        logger.warning("Dropping leading non-user message to satisfy API ordering")
        result.pop(0)

    return result


def _next_user_text_index(api_messages, from_idx):
    """First index >= ``from_idx`` holding a plain-text user message (the
    start of a turn). Tool_result messages are role "user" but list-content,
    so they never match. Returns None if no such message exists."""
    for i in range(max(from_idx, 0), len(api_messages)):
        msg = api_messages[i]
        content = msg.get("content")
        if msg.get("role") == "user" and isinstance(content, str) and content.strip():
            return i
    return None


def _anchored_window_start(api_messages):
    """Deterministic, stable start index for the truncation window.

    Replays the history's trim events: the window start stays fixed until
    the window first exceeds TRUNCATION_HIGH_WATER messages, at which point
    it jumps forward to the first user-TEXT message at or after
    (overflow point - MAX_MESSAGES_TO_SEND). Because each decision depends
    only on message positions before its overflow point, appending new
    messages never changes earlier decisions — the retained prefix is
    byte-identical between turns (one cache miss per trim, not per turn).

    Anchoring on a user-text message (a turn boundary) also fixes the
    head-trim cascade: a raw positional cut after a tool-heavy turn (up to
    25 pairs = 50 tool messages) can open the window mid-pair or with no
    leading user-text message at all, which the pairing repair then trims
    down to almost nothing (the model answers with amnesia). A turn
    boundary is always a valid window head.
    """
    total = len(api_messages)
    start = 0
    while total - start > TRUNCATION_HIGH_WATER:
        # The moment this window first exceeded the high-water mark…
        overflow_at = start + TRUNCATION_HIGH_WATER + 1
        # …it cut back to ~MAX_MESSAGES_TO_SEND messages, anchored on the
        # next turn boundary. The anchor search may pass overflow_at when a
        # single tool-heavy turn spans the whole low-water span — the
        # current turn's user message always terminates the search.
        target = overflow_at - MAX_MESSAGES_TO_SEND
        anchor = _next_user_text_index(api_messages, target)
        if anchor is None:
            # No user-text message anywhere ahead (corrupt/synthetic
            # history): raw positional cut; _validate_tool_pairs repairs.
            anchor = target
        start = anchor
    return start


def _user_text_of(msg):
    """The typed text of a user message, or None if ``msg`` is not a
    plain-text user message.

    Recognizes both byte-equivalent shapes a user text travels in: the
    persisted plain string, and the single text block a previous marker
    application wrapped it into. Tool_result messages (role "user",
    list of tool_result blocks) return None."""
    if msg.get("role") != "user":
        return None
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if (
        isinstance(content, list)
        and len(content) == 1
        and isinstance(content[0], dict)
        and content[0].get("type") == "text"
    ):
        return content[0].get("text")
    return None


def _mark_message(result, idx):
    """Attach a cache_control marker to the last block of ``result[idx]``
    (copying; wrapping string content into its equivalent single text
    block). Thinking blocks cannot carry cache_control — a message ending
    in one is left unmarked rather than 400ing the request."""
    msg = result[idx]
    content = msg.get("content")
    if isinstance(content, list) and content and isinstance(content[-1], dict):
        if content[-1].get("type") in ("thinking", "redacted_thinking"):
            return
        new_content = list(content)
        new_content[-1] = {**new_content[-1], "cache_control": CACHE_CONTROL}
        result[idx] = {**msg, "content": new_content}
    elif isinstance(content, str) and content:
        result[idx] = {
            **msg,
            "content": [
                {"type": "text", "text": content, "cache_control": CACHE_CONTROL},
            ],
        }


def _apply_message_cache_marker(api_messages):
    """Return a copy of ``api_messages`` carrying at most two message-level
    cache_control markers: one on the second-to-last message, one on the
    PREVIOUS turn's user message.

    Breakpoint budget (max 4/request): system [1h] + these two + the
    top-level ``cache_control`` kwarg each API call passes, which
    auto-marks the tail of the final message. (Tools carry no marker of
    their own: the system prompt is frozen, so the entry written at the
    system breakpoint covers the tools+system prefix as one unit.) The
    tail breakpoint is what makes the growing tool-loop history cacheable
    at all (Defect A). The other two:

    - [-2] marker: within a tool loop it is the assistant tool_use message
      (15+ blocks when tool calls are batched, ahead of an equally large
      tool_result tail) — a mid-iteration entry keeps consecutive entries
      inside the API's 20-block lookback limit. On a turn's first request
      it is the just-saved user message (the turn context rides after it
      as [-1]) — writing the anchor entry the NEXT turn reads.
    - Previous-turn user-message marker: every cache entry written past
      that point during the previous turn embeds that turn's context
      message at a position where this turn's bytes differ, so the anchor
      entry is the deepest one this turn can read — and after a tool-heavy
      turn it sits further back than the 20-block lookback reaches from
      [-2]. A breakpoint placed directly ON the anchor reads it at
      distance zero regardless of how large the previous turn was.

    String content is wrapped into an equivalent single text block to carry
    a marker — the API hashes both forms identically and ignores
    cache_control for prefix matching (verified live 2026-07-03), so marker
    movement between iterations and turns cannot invalidate the prefix.
    """
    result = []
    for msg in api_messages:
        content = msg.get("content")
        if isinstance(content, list) and any(
            isinstance(b, dict) and "cache_control" in b for b in content
        ):
            # Strip stale markers (this helper runs once per API call on a
            # list that grows between calls). Copy — never mutate blocks
            # that alias ChatMessage.tool_data.
            content = [
                {k: v for k, v in b.items() if k != "cache_control"}
                if isinstance(b, dict) else b
                for b in content
            ]
            msg = {**msg, "content": content}
        result.append(msg)

    # The current turn's user message is the newest real user text (the
    # injected turn context also matches the shape — its fixed header
    # excludes it); the anchor is the one before that.
    user_text_indexes = [
        i for i, msg in enumerate(result)
        if (text := _user_text_of(msg))
        and text.strip()
        and not text.startswith(TURN_CONTEXT_HEADER)
    ]

    if len(result) >= 2:
        _mark_message(result, len(result) - 2)
    if len(user_text_indexes) >= 2:
        anchor = user_text_indexes[-2]
        if anchor != len(result) - 2:
            _mark_message(result, anchor)
    return result


def _build_api_messages(chat_messages):
    """
    Convert ChatMessage queryset to Anthropic API message format.

    Messages with tool_data are formatted as content blocks.
    Plain text messages use simple string content.

    Truncation is anchored (see _anchored_window_start): the window start
    is stable across turns and always lands on a turn boundary, then the
    Phase 2 pairing repair runs on the result, then the message-level cache
    marker is applied.
    """
    api_messages = []

    for msg in chat_messages:
        if msg.tool_data:
            # tool_data contains the raw Anthropic content blocks. Copy the
            # list: cache-marker injection replaces block dicts, and
            # aliasing the model instance's JSONField list would let a
            # request-scoped cache_control marker leak into tool_data if
            # anything ever re-saves a history message.
            api_messages.append({
                "role": msg.role,
                "content": list(msg.tool_data),
            })
        else:
            api_messages.append({
                "role": msg.role,
                "content": msg.content,
            })

    truncated = api_messages[_anchored_window_start(api_messages):]

    # Validate tool_use / tool_result pairing after truncation. Repairs
    # orphaned tool messages anywhere in the window and guarantees the
    # first message is role "user" (both are hard API requirements — a
    # violation 400s every subsequent request for the session).
    truncated = _validate_tool_pairs(truncated)

    return _apply_message_cache_marker(truncated)


def _strip_empty(obj):
    """Recursively strip null/empty values from dicts to reduce token count."""
    if isinstance(obj, dict):
        return {k: _strip_empty(v) for k, v in obj.items()
                if v is not None and v != "" and v != []}
    if isinstance(obj, list):
        return [_strip_empty(item) for item in obj]
    return obj


def _tool_summary(name, tool_input):
    """One-line summary of tool call parameters for streaming UI."""
    if name == "search":
        q = tool_input.get("query", "")
        s = f'"{q[:40]}"'
        models = tool_input.get("models")
        if models:
            s += f", models={models}"
        return s
    elif name == "query":
        s = tool_input.get("model", "")
        filters = tool_input.get("filters") or {}
        if filters:
            items = list(filters.items())[:2]
            s += ", " + ", ".join(f"{k}={v}" for k, v in items)
        return s
    elif name == "get_record":
        return f'{tool_input.get("model", "")} #{tool_input.get("id", "")}'
    elif name in ("create_record", "update_record"):
        s = tool_input.get("model", "")
        if tool_input.get("dry_run"):
            s += ", dry_run"
        if name == "update_record":
            s = f'{s} #{tool_input.get("id", "")}'
        return s
    elif name == "delete_record":
        return f'{tool_input.get("model", "")} #{tool_input.get("id", "")}'
    elif name == "read_email":
        return f'EmailLink #{tool_input.get("id", "")}'
    elif name == "read_document":
        s = f'Document #{tool_input.get("id", "")}'
        offset = tool_input.get("offset")
        if offset:
            s += f" (offset {offset})"
        return s
    return ""


def _result_summary(name, tool_input, result):
    """Brief result description for streaming UI."""
    if isinstance(result, dict):
        if "error" in result:
            return str(result["error"])[:60]
        if name == "search":
            return f'{result.get("count", 0)} result(s)'
        elif name == "query":
            return f'{result.get("count", 0)} record(s)'
        elif name == "get_record":
            return "found"
        elif name == "create_record":
            return "preview ready" if result.get("dry_run") else "created"
        elif name == "update_record":
            return "preview ready" if result.get("dry_run") else "updated"
        elif name == "delete_record":
            return "preview ready" if result.get("dry_run") else "deleted"
        elif name == "list_models":
            return f'{result.get("count", 0)} models'
        elif name == "summarize":
            return "done"
    return "done"


def _execute_tool(name, tool_input):
    """Execute a tool and return the result as a JSON string."""
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {name}"})

    try:
        result = handler(**tool_input)
        return json.dumps(_strip_empty(result), default=str)
    except Exception as e:
        logger.exception(f"Tool {name} failed: {e}")
        return json.dumps({"error": str(e)})


def _generate_title(client, user_text, assistant_text):
    """Generate a concise session title using a fast model.

    Falls back to truncated user text on any failure.
    """
    try:
        response = client.messages.create(
            model=TITLE_MODEL,
            max_tokens=20,
            messages=[{
                "role": "user",
                "content": (
                    "Generate a 3-6 word title for this conversation. "
                    "Return ONLY the title, nothing else.\n\n"
                    f"User: {user_text[:200]}\n"
                    f"Assistant: {assistant_text[:200]}"
                ),
            }],
        )
        title = response.content[0].text.strip().strip('"').strip("'")
        if title:
            return title[:80]
    except Exception:
        logger.debug("Title generation failed, using fallback")

    title = user_text[:60]
    if len(user_text) > 60:
        title = title[:57] + "..."
    return title


def _get_client_and_model():
    """Return (Anthropic client, model_name) from saved settings."""
    from .models import AssistantSettings

    settings = AssistantSettings.load()
    api_key = settings.get_effective_api_key()
    if not api_key:
        raise ValueError("No API key configured")
    client = _get_shared_client(api_key, max_retries=5)
    model_name = settings.model or DEFAULT_MODEL
    return client, model_name


def _log_usage(path, response, model_name):
    """Cache-hit log line — the standing regression signal for prompt
    caching. cache_read stuck at 0 across consecutive calls means a silent
    prefix invalidator crept back in (see Phase 3 LESSONS entry)."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    logger.info(
        "usage path=%s model=%s input=%s cache_read=%s cache_write=%s output=%s",
        path,
        getattr(response, "model", model_name),
        getattr(usage, "input_tokens", None),
        getattr(usage, "cache_read_input_tokens", None),
        getattr(usage, "cache_creation_input_tokens", None),
        getattr(usage, "output_tokens", None),
    )


def send_message(session, user_text, mode="fast", effort=""):
    """
    Process a user message through the Anthropic API tool-use loop.

    Saves all messages to the database and returns the list of
    new ChatMessage objects created during this exchange.

    Args:
        mode: "fast" (default), "think" (adaptive thinking), or "max" (Opus + thinking).
    """
    from .models import ChatMessage

    # Save the user message
    user_msg = ChatMessage.objects.create(
        session=session,
        role="user",
        content=user_text,
    )
    new_messages = [user_msg]

    # Build the messages list for the API
    all_messages = session.messages.all()
    api_messages = _build_api_messages(all_messages)

    # Load settings from DB (with env var fallback)
    from .models import AssistantSettings
    assistant_settings = AssistantSettings.load()
    api_key = assistant_settings.get_effective_api_key()

    if not api_key:
        error_msg = ChatMessage.objects.create(
            session=session,
            role="assistant",
            content="The assistant is not configured. Please add your Anthropic API key in [Settings](/settings/) > Assistant Settings.",
        )
        new_messages.append(error_msg)
        return new_messages

    model_name = assistant_settings.model or DEFAULT_MODEL
    max_tokens = assistant_settings.max_tokens or DEFAULT_MAX_TOKENS

    # Apply mode overrides (think/max change model, enable thinking, etc.)
    mode_config = dict(MODE_CONFIGS.get(mode, {}))
    if effort and "output_config" in mode_config:
        mode_config["output_config"] = {"effort": effort}
    if "model" in mode_config:
        model_name = mode_config["model"]
    if "max_tokens" in mode_config:
        max_tokens = mode_config["max_tokens"]
    # This path is non-streaming, so the SDK raises ValueError for budgets
    # above NONSTREAMING_MAX_TOKENS ("Streaming is required for operations
    # that may take longer than 10 minutes"). Clamp under that ceiling; a
    # response that hits the cap gets the visible truncation notice.
    max_tokens = min(max_tokens, NONSTREAMING_MAX_TOKENS)

    # No manual retry loop on this path — keep the SDK's own retries.
    client = _get_shared_client(api_key, max_retries=5)
    system_prompt = _build_system_prompt()
    api_messages = _inject_turn_context(api_messages, _build_turn_context())
    effective_effort = mode_config.get("output_config", {}).get("effort", "")
    logger.info(f"send mode={mode} effort={effective_effort} model={model_name} thinking={'yes' if 'thinking' in mode_config else 'no'}")

    for iteration in range(MAX_TOOL_ITERATIONS):
        try:
            create_kwargs = dict(
                model=model_name,
                max_tokens=max_tokens,
                system=system_prompt,
                tools=_get_active_tools(api_messages),
                messages=_apply_message_cache_marker(api_messages),
                # Top-level breakpoint: the API auto-marks the tail of the
                # final message, so every iteration's growing history is a
                # cache hit for the next one (Defect A).
                cache_control=CACHE_CONTROL,
            )
            if "thinking" in mode_config:
                create_kwargs["thinking"] = mode_config["thinking"]
                # temperature is incompatible with thinking — omit it
            elif _model_accepts_temperature(model_name):
                create_kwargs["temperature"] = float(assistant_settings.temperature)
            # else: model dropped sampling params (Opus 4.7+) — omit temperature
            # to avoid a 400; the model uses its own default.
            if "output_config" in mode_config:
                create_kwargs["output_config"] = mode_config["output_config"]
            response = client.messages.create(**create_kwargs)
            _log_usage("send", response, model_name)
        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            error_msg = ChatMessage.objects.create(
                session=session,
                role="assistant",
                content=f"API error: {e}",
            )
            new_messages.append(error_msg)
            return new_messages

        # Check if the response has tool use
        has_tool_use = any(
            block.type == "tool_use" for block in response.content
        )
        if has_tool_use and _stop_reason_notice(response):
            # The response ended on a terminal stop_reason (max_tokens /
            # model_context_window_exceeded / refusal) while carrying
            # tool_use blocks. For the truncation reasons the tool_use
            # input may be incomplete (partial JSON) — executing it could
            # run a write with a truncated data dict; a refused response
            # must not act at all. Fall through to the final-text path,
            # which persists any partial text plus the matching notice.
            logger.warning(
                "Skipping tool execution: terminal stop_reason %s",
                getattr(response, "stop_reason", None),
            )
            has_tool_use = False

        if has_tool_use:
            # Build the assistant's tool_use content. thinking AND
            # redacted_thinking blocks must be round-tripped unmodified —
            # dropping either modifies the replayed assistant turn (400).
            assistant_content = []
            for block in response.content:
                if block.type == "thinking":
                    assistant_content.append({
                        "type": "thinking",
                        "thinking": block.thinking,
                        "signature": block.signature,
                    })
                elif block.type == "redacted_thinking":
                    assistant_content.append({
                        "type": "redacted_thinking",
                        "data": block.data,
                    })
                elif block.type == "text":
                    assistant_content.append({
                        "type": "text",
                        "text": block.text,
                    })
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

            # Execute each tool call FIRST, then persist. Saving the
            # tool_use message before execution meant a crash during a tool
            # run reliably orphaned it — bricking the session.
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result_str = _execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })

            # Save the tool_use + tool_result pair atomically so history can
            # never hold one without the other. Short write txn only — the
            # API call and tool execution stay outside (SQLite write lock).
            with transaction.atomic():
                assistant_msg = ChatMessage.objects.create(
                    session=session,
                    role="assistant",
                    content="",  # text content extracted below
                    tool_data=assistant_content,
                )
                tool_result_msg = ChatMessage.objects.create(
                    session=session,
                    role="user",
                    content="",
                    tool_data=tool_results,
                )
            new_messages.append(assistant_msg)
            new_messages.append(tool_result_msg)

            # Update api_messages for next iteration
            api_messages.append({"role": "assistant", "content": assistant_content})
            api_messages.append({"role": "user", "content": tool_results})

        else:
            # Final text response — extract and save
            text_parts = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)

            final_text = "\n".join(text_parts)
            final_text += _stop_reason_notice(response)
            assistant_msg = ChatMessage.objects.create(
                session=session,
                role="assistant",
                content=final_text,
            )
            new_messages.append(assistant_msg)

            # Update session title from first exchange (AI-generated)
            if session.title == "New Chat" and final_text:
                session.title = _generate_title(client, user_text, final_text)
                session.save(update_fields=["title", "updated_at"])

            return new_messages

    # Safety: max iterations reached
    timeout_msg = ChatMessage.objects.create(
        session=session,
        role="assistant",
        content="I reached the maximum number of tool calls for this message. Please try a more specific question.",
    )
    new_messages.append(timeout_msg)
    return new_messages


def _touch_turn(turn):
    """Refresh ``turn.updated_at`` so a polling client can distinguish a live
    turn from one whose process died (AssistantTurn.is_stale). Never raises."""
    if turn is None:
        return
    from django.utils import timezone
    from .models import AssistantTurn
    try:
        AssistantTurn.objects.filter(pk=turn.pk).update(
            updated_at=timezone.now()
        )
    except Exception:
        logger.exception("Failed to touch AssistantTurn %s", turn.pk)


def _finalize_turn(turn, state, **fields):
    """Record the terminal state of a turn, never raising and never
    overwriting a state another path already finalized (conditional update)."""
    if turn is None:
        return
    from django.utils import timezone
    from .models import AssistantTurn
    try:
        AssistantTurn.objects.filter(
            pk=turn.pk, state=AssistantTurn.STATE_RUNNING
        ).update(state=state, updated_at=timezone.now(), **fields)
    except Exception:
        logger.exception("Failed to finalize AssistantTurn %s", turn.pk)


def _record_request_id(turn, req_id):
    """Append an Anthropic request id to the turn's observability trail.
    Only the stream worker thread writes a given turn, so the in-memory
    append stays consistent with the row. Never raises."""
    if turn is None or not req_id:
        return
    from .models import AssistantTurn
    try:
        turn.request_ids.append(req_id)
        AssistantTurn.objects.filter(pk=turn.pk).update(
            request_ids=turn.request_ids
        )
    except Exception:
        logger.exception("Failed to record request id on AssistantTurn %s", turn.pk)


def _with_heartbeat(inner_gen, interval=HEARTBEAT_INTERVAL_SECONDS, turn=None):
    """Wrap an SSE generator so no silent window exceeds ``interval`` seconds,
    and so losing the consumer does NOT cancel the work.

    The streaming tool loop blocks for long stretches with no client-visible
    output: during time-to-first-token, while the model streams tool-call
    argument JSON, during synchronous tool execution, and in the gap between
    tool iterations. Any one of these can exceed the browser's 90s inactivity
    watchdog on a large request, tearing down a perfectly healthy stream.

    To bridge every phase uniformly, run the inner generator in a worker thread
    and relay its frames through a bounded queue. While the worker is blocked
    (producing nothing), this outer generator emits ``: keepalive`` comment
    frames — valid SSE that the client's line parser ignores
    (assistant-chat.js only acts on ``event:``/``data:`` lines) but which still
    resets the byte-level watchdog. If the inner generator raises, a terminal
    ``error`` frame is emitted so the client always reaches a defined end state.

    Disconnect semantics: if this outer generator is closed before the inner
    one finishes (browser disconnect, proxy abort — Django closes the response
    iterator), the worker DETACHES instead of cancelling: it stops relaying
    frames and silently drains the inner generator to completion, bounded by
    DETACHED_DRAIN_BUDGET_SECONDS. All persistence lives inside the inner
    generator, so the answer is saved and visible on the next refresh, and the
    in-flight (already billed) API call is not thrown away. ``turn`` is marked
    client_disconnected so the turn-status endpoint can tell a polling client
    the work is still running.
    """
    from django.db import connection

    frames = queue.Queue(maxsize=1)
    sentinel = object()
    detached = threading.Event()  # consumer gone — stop relaying, keep working
    detached_since = [None]  # monotonic timestamp, set by the consumer side
    last_touch = [0.0]

    def produce():
        try:
            for frame in inner_gen:
                now = time.monotonic()
                if now - last_touch[0] >= TURN_TOUCH_INTERVAL_SECONDS:
                    last_touch[0] = now
                    _touch_turn(turn)
                if detached.is_set():
                    # Discard the frame but keep consuming so the turn
                    # completes and persists — bounded so a wedged upstream
                    # can't pin this thread forever.
                    started = detached_since[0] or now
                    if now - started > DETACHED_DRAIN_BUDGET_SECONDS:
                        logger.error(
                            "Abandoning detached assistant turn %s after "
                            "%ss drain budget",
                            getattr(turn, "pk", None),
                            DETACHED_DRAIN_BUDGET_SECONDS,
                        )
                        _finalize_turn(turn, "abandoned")
                        break
                    continue
                # Bounded put so an aborted client (consumer gone) can't
                # wedge this thread — recheck detached on each timeout.
                while not detached.is_set():
                    try:
                        frames.put(frame, timeout=1)
                        break
                    except queue.Full:
                        continue
            else:
                if detached.is_set():
                    logger.info(
                        "Detached assistant turn %s finished in background",
                        getattr(turn, "pk", None),
                    )
        except Exception:
            logger.exception("Assistant stream generator crashed")
            _finalize_turn(turn, "failed")
            if not detached.is_set():
                try:
                    frames.put(
                        f"event: error\ndata: "
                        f"{json.dumps({'message': 'The assistant hit an unexpected error. Your data was saved — reload to see it.'})}\n\n",
                        timeout=1,
                    )
                except queue.Full:
                    pass
        finally:
            inner_gen.close()
            # The worker opened its own thread-local DB connection; release it.
            connection.close()
            if not detached.is_set():
                try:
                    frames.put(sentinel, timeout=1)
                except queue.Full:
                    pass

    worker = threading.Thread(target=produce, name="assistant-stream", daemon=True)
    worker.start()

    completed = False
    try:
        while True:
            try:
                frame = frames.get(timeout=interval)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            if frame is sentinel:
                completed = True
                break
            yield frame
    finally:
        if not completed:
            # Consumer gone before the turn finished. Detach the worker —
            # it keeps consuming (and persisting) in the background.
            detached_since[0] = time.monotonic()
            detached.set()
            logger.warning(
                "Client disconnected mid-stream (turn=%s); "
                "finishing the turn in the background",
                getattr(turn, "pk", None),
            )
            if turn is not None:
                from .models import AssistantTurn
                try:
                    AssistantTurn.objects.filter(pk=turn.pk).update(
                        client_disconnected=True
                    )
                except Exception:
                    logger.exception(
                        "Failed to flag disconnect on AssistantTurn %s", turn.pk
                    )
        # Drain the queue so a blocked put() unblocks promptly.
        try:
            while True:
                frames.get_nowait()
        except queue.Empty:
            pass


def stream_message(session, user_text, mode="fast", effort=""):
    """Public entry point — the streaming tool loop wrapped with a heartbeat.

    Returns a generator of SSE frames suitable for StreamingHttpResponse. See
    ``_stream_message_impl`` for the event protocol and ``_with_heartbeat`` for
    the keepalive behavior that keeps long, healthy requests alive and the
    detach-on-disconnect behavior that finishes (and persists) the turn even
    if the browser connection dies. The AssistantTurn row created here is what
    the client polls (turn-status endpoint) to recover from a severed stream.
    """
    from .models import AssistantTurn

    turn = AssistantTurn.objects.create(session=session)
    return _with_heartbeat(
        _stream_message_impl(session, user_text, mode=mode, effort=effort, turn=turn),
        turn=turn,
    )


def _stream_message_impl(session, user_text, mode="fast", effort="", turn=None):
    """
    Generator that yields SSE events as the assistant processes a message.

    Events:
      event: user_message   — the user's message was saved
      event: tool_start     — a tool is being called
      event: tool_done      — a tool finished
      event: token          — a text token from the final response
      event: done           — stream complete, message saved
      event: error          — an error occurred

    ``turn`` (AssistantTurn) is finalized at every terminal path BEFORE the
    terminal frame is yielded, so the recorded outcome is correct even if the
    consumer never resumes the generator afterwards.
    """
    from .models import AssistantSettings, ChatMessage

    def _safe_create_message(sess, content, **kwargs):
        """Create a ChatMessage, logging but not crashing on DB errors."""
        try:
            return ChatMessage.objects.create(session=sess, role="assistant", content=content, **kwargs)
        except Exception:
            logger.exception("Failed to save assistant message to DB")
            return None

    def sse(event, data):
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    # Save user message
    user_msg = ChatMessage.objects.create(
        session=session, role="user", content=user_text,
    )
    yield sse("user_message", {"id": user_msg.pk, "content": user_text})

    # Load settings
    assistant_settings = AssistantSettings.load()
    api_key = assistant_settings.get_effective_api_key()

    if not api_key:
        ChatMessage.objects.create(
            session=session, role="assistant",
            content="The assistant is not configured. Please add your Anthropic API key in [Settings](/settings/) > Assistant Settings.",
        )
        _finalize_turn(turn, "failed")
        yield sse("error", {"message": "API key not configured"})
        return

    model_name = assistant_settings.model or DEFAULT_MODEL
    max_tokens = assistant_settings.max_tokens or DEFAULT_MAX_TOKENS

    # Apply mode overrides (think/max change model, enable thinking, etc.)
    mode_config = dict(MODE_CONFIGS.get(mode, {}))
    if effort and "output_config" in mode_config:
        mode_config["output_config"] = {"effort": effort}
    if "model" in mode_config:
        model_name = mode_config["model"]
    if "max_tokens" in mode_config:
        max_tokens = mode_config["max_tokens"]

    # SDK retries stay at 1 here: the manual 5-attempt loop below owns
    # status-code retries AND emits keepalives while waiting — stacking the
    # SDK's 5 on top meant up to ~25 silent upstream attempts pinning a
    # worker thread during an outage. One SDK retry is kept for transient
    # connection errors, which the manual loop does not retry.
    client = _get_shared_client(api_key, max_retries=1)
    system_prompt = _build_system_prompt()

    all_messages = session.messages.all()
    api_messages = _build_api_messages(all_messages)
    api_messages = _inject_turn_context(api_messages, _build_turn_context())

    effective_effort = mode_config.get("output_config", {}).get("effort", "")
    logger.info(f"stream mode={mode} effort={effective_effort} model={model_name} thinking={'yes' if 'thinking' in mode_config else 'no'}")

    # Streaming tool loop: every API call is streamed.
    # Text tokens are yielded live during the final (non-tool) response.
    # During tool iterations, any brief text is cleared before tools execute.
    has_dry_run = False  # Track if any dry_run preview happened (for confirm UI)
    has_write_executed = False  # Track if any write actually executed (suppress stale buttons)
    for iteration in range(MAX_TOOL_ITERATIONS):
        # Retry loop for transient API errors (overloaded, rate limit)
        response = None
        for attempt in range(5):
            try:
                stream_kwargs = dict(
                    model=model_name,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    tools=_get_active_tools(api_messages),
                    messages=_apply_message_cache_marker(api_messages),
                    # Top-level breakpoint: auto-marks the tail of the final
                    # message so each loop iteration reads the previous
                    # iteration's cache entry (Defect A).
                    cache_control=CACHE_CONTROL,
                )
                if "thinking" in mode_config:
                    stream_kwargs["thinking"] = mode_config["thinking"]
                    # temperature is incompatible with thinking — omit it
                elif _model_accepts_temperature(model_name):
                    stream_kwargs["temperature"] = float(assistant_settings.temperature)
                # else: model dropped sampling params (Opus 4.7+) — omit
                # temperature to avoid a 400; the model uses its own default.
                if "output_config" in mode_config:
                    stream_kwargs["output_config"] = mode_config["output_config"]

                with client.messages.stream(**stream_kwargs) as stream:
                    # Capture the request id at stream OPEN (it comes from the
                    # response headers), not only after get_final_message() —
                    # a call killed mid-stream must still be correlatable
                    # with Anthropic's logs.
                    req_id = getattr(stream, "request_id", None)
                    logger.info(f"stream open model={model_name} request_id={req_id}")
                    _record_request_id(turn, req_id)

                    # Stream text tokens to client as they arrive.
                    # During extended thinking, yield periodic keepalives
                    # so the client watchdog doesn't fire (90s timeout).
                    last_thinking_keepalive = 0
                    for event in stream:
                        if event.type == "content_block_delta":
                            if event.delta.type == "text_delta":
                                yield sse("token", {"text": event.delta.text})
                            elif event.delta.type == "thinking_delta":
                                now = time.monotonic()
                                if now - last_thinking_keepalive >= 10:
                                    yield sse("thinking", {})
                                    last_thinking_keepalive = now

                    response = stream.get_final_message()

                # Log request_id and actual model used
                logger.info(f"OK model={response.model} request_id={req_id}")
                _log_usage("stream", response, model_name)

                break  # Success — exit retry loop
            except anthropic.APIStatusError as e:
                # Log request_id if available
                req_id = getattr(e, 'request_id', None) or (e.response.headers.get('request-id') if hasattr(e, 'response') else None)
                if req_id:
                    logger.warning(f"Anthropic request_id: {req_id}")

                # Retryable: 429 rate limit, 529 overloaded, 5xx server errors
                is_overloaded = (
                    e.status_code == 529
                    or e.status_code >= 500
                    or e.status_code == 429
                    or "overloaded" in str(e).lower()
                )
                if is_overloaded and attempt < 4:
                    # Respect retry-after header if present, otherwise exponential backoff
                    retry_after = None
                    if hasattr(e, 'response') and e.response:
                        retry_after = e.response.headers.get('retry-after')
                    if retry_after:
                        try:
                            wait = min(float(retry_after), 30)
                        except (ValueError, TypeError):
                            wait = 2 ** attempt
                    else:
                        wait = 2 ** attempt
                    logger.warning(f"Anthropic API {e.status_code} (attempt {attempt + 1}/5), retrying in {wait}s")
                    # Send keepalive during wait so client watchdog doesn't fire
                    deadline = time.monotonic() + wait
                    while time.monotonic() < deadline:
                        yield ": keepalive\n\n"
                        time.sleep(min(5, deadline - time.monotonic()))
                    continue
                # Non-retryable (400, 401, 403, etc.) or final retry exhausted
                logger.error(f"Anthropic API error {e.status_code}: {e}")
                if is_overloaded:
                    error_msg = "The AI service is temporarily unavailable. Please try again in a minute."
                else:
                    error_msg = f"Request error ({e.status_code}). Try sending your message again."
                _safe_create_message(session, error_msg)
                _finalize_turn(turn, "failed")
                yield sse("error", {"message": error_msg})
                return
            except anthropic.APIError as e:
                # Catch-all: also retry overloaded errors that arrive as generic APIError
                if "overloaded" in str(e).lower() and attempt < 4:
                    wait = 2 ** attempt
                    logger.warning(f"Anthropic overloaded (attempt {attempt + 1}/5), retrying in {wait}s")
                    deadline = time.monotonic() + wait
                    while time.monotonic() < deadline:
                        yield ": keepalive\n\n"
                        time.sleep(min(5, deadline - time.monotonic()))
                    continue
                logger.error(f"Anthropic API error: {e}")
                _safe_create_message(session, f"API error: {e}")
                _finalize_turn(turn, "failed")
                yield sse("error", {"message": str(e)})
                return

        has_tool_use = any(block.type == "tool_use" for block in response.content)
        if has_tool_use and _stop_reason_notice(response):
            # Terminal stop_reason (max_tokens / model_context_window_exceeded /
            # refusal) with tool_use blocks present — the input may be
            # incomplete (partial JSON), and a refused response must not act.
            # Skip execution and fall through to the final-text path, which
            # persists any partial text plus the matching notice.
            logger.warning(
                "Skipping tool execution: terminal stop_reason %s",
                getattr(response, "stop_reason", None),
            )
            has_tool_use = False

        if has_tool_use:
            # Clear any text that streamed before tool_use was detected
            yield sse("clear", {})

            # Build assistant content blocks (saved to DB after tools complete).
            # thinking AND redacted_thinking blocks must be round-tripped
            # unmodified — dropping either modifies the replayed turn (400).
            assistant_content = []
            for block in response.content:
                if block.type == "thinking":
                    assistant_content.append({
                        "type": "thinking",
                        "thinking": block.thinking,
                        "signature": block.signature,
                    })
                elif block.type == "redacted_thinking":
                    assistant_content.append({
                        "type": "redacted_thinking", "data": block.data,
                    })
                elif block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use", "id": block.id,
                        "name": block.name, "input": block.input,
                    })

            # Execute tools (SSE events stream live to client)
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    summary = _tool_summary(block.name, block.input)
                    yield sse("tool_start", {"name": block.name, "summary": summary})
                    result_str = _execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })
                    # Parse result for summary, truncate large output
                    try:
                        result_obj = json.loads(result_str)
                    except (json.JSONDecodeError, TypeError):
                        result_obj = {}
                    # Detect dry_run from tool RESULT (not input) so implicit
                    # dry_runs (LLM omits param, Python default applies) are caught.
                    if result_obj.get("dry_run") is True:
                        has_dry_run = True
                    if result_obj.get("action") in ("created", "updated", "deleted"):
                        has_write_executed = True
                    r_summary = _result_summary(block.name, block.input, result_obj)
                    if len(result_str) > 2000:
                        output = {"_truncated": True, "preview": result_str[:2000]}
                    else:
                        output = result_obj
                    yield sse("tool_done", {"name": block.name, "result_summary": r_summary, "output": output})

            # Save both messages atomically — a crash between the two
            # creates (or during either) persists neither, so history can
            # never hold a tool_use without its tool_result. Tools already
            # executed above; only the two creates sit inside the txn.
            try:
                with transaction.atomic():
                    ChatMessage.objects.create(
                        session=session, role="assistant", content="",
                        tool_data=assistant_content,
                    )
                    ChatMessage.objects.create(
                        session=session, role="user", content="",
                        tool_data=tool_results,
                    )
            except Exception:
                logger.exception("Failed to save tool messages to DB")
                _finalize_turn(turn, "failed")
                yield sse("error", {"message": "Failed to save tool results. Try again."})
                return

            api_messages.append({"role": "assistant", "content": assistant_content})
            api_messages.append({"role": "user", "content": tool_results})
            continue

        # No tool use — text was already streamed live via token events.
        final_text = "\n".join(
            block.text for block in response.content if block.type == "text"
        )
        notice = _stop_reason_notice(response)
        if notice:
            # Surface the stop live (text already streamed) and persist it.
            final_text += notice
            yield sse("token", {"text": notice})

        # Save the final message
        try:
            assistant_msg = ChatMessage.objects.create(
                session=session, role="assistant", content=final_text,
            )
        except Exception:
            logger.exception("Failed to save final assistant message to DB")
            _finalize_turn(turn, "failed")
            yield sse("error", {"message": "Failed to save response. Try again."})
            return

        # Update session title (AI-generated)
        if session.title == "New Chat" and final_text:
            try:
                session.title = _generate_title(client, user_text, final_text)
                session.save(update_fields=["title", "updated_at"])
                yield sse("title", {"title": session.title})
            except Exception:
                logger.exception("Failed to generate/save session title")

        confirm_required = has_dry_run and not has_write_executed
        _finalize_turn(
            turn, "completed",
            final_message=assistant_msg, confirm_required=confirm_required,
        )
        if confirm_required:
            yield sse("confirm_required", {})
        yield sse("done", {"message_id": assistant_msg.pk})
        return

    # Max iterations reached (for-else). Deliver a terminal SSE so the client
    # reaches a defined end state instead of a silent stop. Treat it as a
    # normal completion ("done") carrying the saved guidance message — the
    # client reloads and renders it — and fall back to "error" only if the
    # save itself failed (no message_id to show).
    fallback_msg = _safe_create_message(
        session,
        "I reached the maximum number of tool calls for this message. Please try a more specific question.",
    )
    if fallback_msg is not None:
        _finalize_turn(turn, "completed", final_message=fallback_msg)
        yield sse("done", {"message_id": fallback_msg.pk})
    else:
        _finalize_turn(turn, "failed")
        yield sse("error", {"message": "Max tool iterations reached"})
