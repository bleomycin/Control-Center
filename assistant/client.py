"""
Anthropic API client for the AI assistant.

Handles system prompt construction, message formatting,
and the tool-use loop.
"""

import json
import logging
import time

import anthropic
from django.conf import settings

from . import registry
from .tools import TOOL_DEFINITIONS, TOOL_HANDLERS, summarize

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 25
MAX_MESSAGES_TO_SEND = 50
CACHE_BREAKPOINT_INTERVAL = 15  # Add cache breakpoint every N messages
CACHE_CONTROL = {"type": "ephemeral"}
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 8192
TITLE_MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PREAMBLE = """You are the Control Center Assistant — an AI built into a personal management system. You help the user manage their stakeholders, legal matters, assets, tasks, notes, cash flow, healthcare records, documents, and checklists.

## Your capabilities
- Search and query any data in the system using the provided tools
- Create, update, and delete records (with user confirmation)
- Answer complex questions by combining data from multiple sources
- Provide summaries and insights about the user's affairs
- Create and manage **checklists** on any entity (stakeholders, tasks, notes, properties, legal matters) — useful for tracking itemized lists like "documents to request from Thomas" or "due diligence items for a property"

## Critical rules
1. **Write operations**: ALWAYS use dry_run=true first to preview changes. Show the preview to the user and explicitly ask for confirmation before executing with dry_run=false. NEVER skip the preview step.
2. **Be precise**: When querying data, use specific filters rather than loading everything. Start narrow, broaden if needed.
3. **Show your work**: When answering complex questions, briefly explain which queries you're running so the user understands.
4. **Links**: When referencing records, include their URL so the user can click through. ALWAYS use relative URLs exactly as returned by the tools (e.g., `/stakeholders/482/`). NEVER prepend a host, port, or protocol — no `http://localhost` or any domain.
5. **Dates**: Today's date is provided in the system stats. Use it for relative date calculations.
6. **Be concise**: Give direct answers. Use markdown formatting for readability — tables for comparisons, lists for enumerations, bold for key facts.
7. **Batch tool calls aggressively**: Every API round-trip adds latency. Always call as many tools as possible in a single response. If you need to search for 15 entities, call search() 15 times in one response — do NOT split them across multiple iterations. Fewer iterations = faster results for the user.
8. **Meetings vs Appointments**: For scheduling meetings (business, legal, personal), create a `Task` with `task_type="meeting"` and set `due_date` + `due_time`. The `Appointment` model is ONLY for medical/healthcare appointments (doctor visits, lab work, etc.) — never use it for general meetings.
9. **Task links**: To attach reference links to a task, create `TaskLink` records (model: TaskLink, fields: task, url, label). Each TaskLink has a `task` FK (the task ID), a `url` (required), and an optional `label`. A task can have multiple links. Use this for articles, documents, external resources, websites — anything that isn't a video call join link. The `meeting_url` field on Task is exclusively for Zoom/Teams/Meet join URLs.

## Email & meeting notes processing

When the user pastes a long email, meeting notes, or multi-party correspondence, process it systematically using the steps below. The goal is to extract every actionable piece of information and get it into the system with full cross-linking — so nothing falls through the cracks.

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

**Due dates** — resolve relative references against today's date (from system stats):
- "next week Thursday" → calculate the actual date
- "end of month" → last day of current month
- "by Friday" → the coming Friday
- "ASAP" with no date → tomorrow
- No deadline mentioned → leave `due_date` blank

**Stakeholder entity_type** — valid values are listed in the system state below. Use these inference rules:
- Company, firm, corporation, LLC, Inc., LLP, organization → "firm"
- Attorney, lawyer, counsel, partner (at a law firm) → "attorney"
- Bank, lender, credit line → "lender"
- Developer, builder, contractor, architect → "business_partner"
- Advisor, CPA, accountant, financial planner, consultant → "advisor"
- Doctor, physician, specialist → "professional"
- Individual person with no clear role → "contact"
When creating a firm and its employees, create the firm first (entity_type="firm"), then create each person with `parent_organization` set to the firm's ID. This links them as team members under the firm.

### Step 7: Google Drive file attachments
When the user's message includes a section starting with "Attached Google Drive files", these are files the user selected from Google Drive to link as documents. For each file listed:
1. Create a `Document` record with: `title` (filename without extension), `gdrive_file_id` (the ID), `gdrive_url` (the URL), `gdrive_mime_type` (the Type), `gdrive_file_name` (the full filename).
2. Link each Document to the relevant entity using the appropriate FK (`related_property`, `related_loan`, `related_stakeholder`, `related_legal_matter`, etc.) based on the email content. For example, if the email discusses loan documents for a specific property, link the documents to that property and/or loan.
3. Include these in the Step 3 plan so the user can review before creation.
4. Create Documents in Step 4 after stakeholders and assets exist (since Documents link to them via FKs).

## Linked email content
Entities (tasks, stakeholders, properties, legal matters, etc.) may have linked Gmail threads via EmailLink records. EmailLink stores subject, sender, and date — but NOT the email body.
When answering a query and the record data alone doesn't have the answer:
1. Check for linked emails: `query(model="EmailLink", filters={"related_task__id__exact": ID})` (replace `related_task` with `related_stakeholder`, `related_property`, `related_legal_matter`, etc. as appropriate)
2. If any email subject looks relevant to the query, fetch its content: `read_email(id=EMAILLINK_ID)`
3. Only fetch emails whose subjects suggest relevance — don't read every linked email.
This is especially important when the user asks general questions — the answer may be buried in a linked email even if the user doesn't mention emails.

## Page context hints
When the user sends a message from the quick assistant drawer, the message may begin with a context hint like `[Context: viewing Stakeholder #482 "Thomas Wright"]`. This tells you what page the user is currently looking at. Use this context to understand what entity they're referring to (e.g., "what tasks does this person have?" means the stakeholder in the context). Do NOT repeat the context hint back to the user — just use it to inform your response.

## Data model
The system contains the following models and fields:
"""


def _build_system_prompt():
    """Construct the full system prompt with schema and live stats.

    Returns a list of content blocks with cache_control on the static
    portion (preamble + schema) so Anthropic caches it across calls.
    The dynamic stats block is appended without caching.
    """
    schema = registry.get_schema_text()
    stats = summarize()

    stats_lines = ["\n## Current system state"]
    from django.utils import timezone
    stats_lines.append(f"Today: {timezone.localdate().isoformat()}")

    # Include assistant settings
    from .models import AssistantSettings
    settings = AssistantSettings.load()
    owner_name = settings.owner_name
    reminder_mins = settings.default_reminder_minutes
    if reminder_mins:
        stats_lines.append(f"Default task reminder: {reminder_mins} minutes before due time")
        stats_lines.append(
            "When creating a task with a due_date and due_time, automatically set "
            f"reminder_date to {reminder_mins} minutes before the due datetime. "
            "For example, if due_date=2026-04-01 and due_time=14:00, set "
            f"reminder_date to the datetime {reminder_mins} minutes earlier. "
            "Skip this for tasks without a due_time."
        )
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

    return [
        {
            "type": "text",
            "text": SYSTEM_PREAMBLE + schema,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": "\n".join(stats_lines),
        },
    ]


def _validate_tool_pairs(messages):
    """
    Ensure tool_use and tool_result messages are properly paired.

    Fixes two edge cases:
    1. Truncation sliced off a tool_use, leaving an orphaned tool_result at the start.
    2. Connection dropped after saving tool_use but before tool_result (orphan at the end).

    Returns a cleaned copy of the message list.
    """
    if not messages:
        return messages

    def _has_tool_use(msg):
        content = msg.get("content")
        if isinstance(content, list):
            return any(b.get("type") == "tool_use" for b in content)
        return False

    def _has_tool_result(msg):
        content = msg.get("content")
        if isinstance(content, list):
            return any(b.get("type") == "tool_result" for b in content)
        return False

    result = list(messages)

    # Strip orphaned tool_result at the start (its tool_use was truncated away)
    while result and result[0].get("role") == "user" and _has_tool_result(result[0]):
        logger.warning("Stripping orphaned tool_result at start of message list")
        result.pop(0)

    # Strip orphaned tool_use at the end (tool_result was never saved)
    while result and result[-1].get("role") == "assistant" and _has_tool_use(result[-1]):
        logger.warning("Stripping orphaned tool_use at end of message list")
        result.pop()

    return result


def _build_api_messages(chat_messages):
    """
    Convert ChatMessage queryset to Anthropic API message format.

    Messages with tool_data are formatted as content blocks.
    Plain text messages use simple string content.

    Adds explicit cache_control breakpoints every CACHE_BREAKPOINT_INTERVAL
    messages to ensure cache hits on long conversations (the API has a
    20-block lookback limit for automatic caching).
    """
    api_messages = []

    for msg in chat_messages:
        if msg.tool_data:
            # tool_data contains the raw Anthropic content blocks
            api_messages.append({
                "role": msg.role,
                "content": msg.tool_data,
            })
        else:
            api_messages.append({
                "role": msg.role,
                "content": msg.content,
            })

    truncated = api_messages[-MAX_MESSAGES_TO_SEND:]

    # Validate tool_use / tool_result pairing after truncation.
    # Strip orphaned tool_result at the start (truncation cut its tool_use)
    # and orphaned tool_use at the end (connection dropped before tool_result).
    truncated = _validate_tool_pairs(truncated)

    # Add cache breakpoints at regular intervals for long conversations.
    # This prevents cache misses when the conversation exceeds the
    # 20-block lookback window. Max 4 explicit breakpoints allowed.
    if len(truncated) > CACHE_BREAKPOINT_INTERVAL:
        breakpoints_added = 0
        for i in range(CACHE_BREAKPOINT_INTERVAL - 1, len(truncated) - 1, CACHE_BREAKPOINT_INTERVAL):
            if breakpoints_added >= 3:  # Max 4 total: 1 system + 3 messages
                break
            msg = truncated[i]
            content = msg.get("content")
            # Only add breakpoints to plain text messages (not tool_data blocks)
            if isinstance(content, str):
                truncated[i] = {
                    "role": msg["role"],
                    "content": [
                        {"type": "text", "text": content, "cache_control": CACHE_CONTROL},
                    ],
                }
                breakpoints_added += 1

    return truncated


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
        s = tool_input.get("model_name", "")
        filters = tool_input.get("filters") or {}
        if filters:
            items = list(filters.items())[:2]
            s += ", " + ", ".join(f"{k}={v}" for k, v in items)
        return s
    elif name == "get_record":
        return f'{tool_input.get("model_name", "")} #{tool_input.get("record_id", "")}'
    elif name in ("create_record", "update_record"):
        s = tool_input.get("model_name", "")
        if tool_input.get("dry_run"):
            s += ", dry_run"
        if name == "update_record":
            s = f'{s} #{tool_input.get("record_id", "")}'
        return s
    elif name == "delete_record":
        return f'{tool_input.get("model_name", "")} #{tool_input.get("record_id", "")}'
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


def send_message(session, user_text):
    """
    Process a user message through the Anthropic API tool-use loop.

    Saves all messages to the database and returns the list of
    new ChatMessage objects created during this exchange.
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

    client = anthropic.Anthropic(api_key=api_key, max_retries=5)
    system_prompt = _build_system_prompt()

    for iteration in range(MAX_TOOL_ITERATIONS):
        try:
            response = client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                system=system_prompt,
                tools=TOOL_DEFINITIONS,
                messages=api_messages,
            )
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

        if has_tool_use:
            # Save the assistant's tool_use response
            assistant_content = []
            for block in response.content:
                if block.type == "text":
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

            assistant_msg = ChatMessage.objects.create(
                session=session,
                role="assistant",
                content="",  # text content extracted below
                tool_data=assistant_content,
            )
            new_messages.append(assistant_msg)

            # Execute each tool call and build results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result_str = _execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })

            # Save tool results as a user message (Anthropic convention)
            tool_result_msg = ChatMessage.objects.create(
                session=session,
                role="user",
                content="",
                tool_data=tool_results,
            )
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


def stream_message(session, user_text):
    """
    Generator that yields SSE events as the assistant processes a message.

    Events:
      event: user_message   — the user's message was saved
      event: tool_start     — a tool is being called
      event: tool_done      — a tool finished
      event: token          — a text token from the final response
      event: done           — stream complete, message saved
      event: error          — an error occurred
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
        yield sse("error", {"message": "API key not configured"})
        return

    model_name = assistant_settings.model or DEFAULT_MODEL
    max_tokens = assistant_settings.max_tokens or DEFAULT_MAX_TOKENS

    client = anthropic.Anthropic(api_key=api_key, max_retries=5)
    system_prompt = _build_system_prompt()

    all_messages = session.messages.all()
    api_messages = _build_api_messages(all_messages)

    # Streaming tool loop: every API call is streamed.
    # Text tokens are yielded live during the final (non-tool) response.
    # During tool iterations, any brief text is cleared before tools execute.
    for iteration in range(MAX_TOOL_ITERATIONS):
        # Retry loop for transient API errors (overloaded, rate limit)
        response = None
        for attempt in range(5):
            try:
                with client.messages.stream(
                    model=model_name,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    tools=TOOL_DEFINITIONS,
                    messages=api_messages,
                ) as stream:
                    # Stream text tokens to client as they arrive
                    for event in stream:
                        if event.type == "content_block_delta":
                            if event.delta.type == "text_delta":
                                yield sse("token", {"text": event.delta.text})

                    response = stream.get_final_message()

                # Log request_id for debugging API issues
                if hasattr(response, '_request_id'):
                    logger.info(f"Anthropic request_id: {response._request_id}")

                break  # Success — exit retry loop
            except anthropic.APIStatusError as e:
                # Log request_id if available
                req_id = getattr(e, 'request_id', None) or (e.response.headers.get('request-id') if hasattr(e, 'response') else None)
                if req_id:
                    logger.warning(f"Anthropic request_id: {req_id}")

                # Retryable: 429 rate limit, 5xx server errors
                if (e.status_code >= 500 or e.status_code == 429) and attempt < 4:
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
                if e.status_code >= 500 or e.status_code == 429:
                    error_msg = "The AI service is temporarily unavailable. Please try again in a minute."
                else:
                    error_msg = f"Request error ({e.status_code}). Try sending your message again."
                _safe_create_message(session, error_msg)
                yield sse("error", {"message": error_msg})
                return
            except anthropic.APIError as e:
                logger.error(f"Anthropic API error: {e}")
                _safe_create_message(session, f"API error: {e}")
                yield sse("error", {"message": str(e)})
                return

        has_tool_use = any(block.type == "tool_use" for block in response.content)

        if has_tool_use:
            # Clear any text that streamed before tool_use was detected
            yield sse("clear", {})

            # Build assistant content blocks (saved to DB after tools complete)
            assistant_content = []
            for block in response.content:
                if block.type == "text":
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
                    r_summary = _result_summary(block.name, block.input, result_obj)
                    if len(result_str) > 2000:
                        output = {"_truncated": True, "preview": result_str[:2000]}
                    else:
                        output = result_obj
                    yield sse("tool_done", {"name": block.name, "result_summary": r_summary, "output": output})

            # Save both messages together — if execution crashed above,
            # neither is saved, preventing orphaned tool_use messages.
            try:
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
                yield sse("error", {"message": "Failed to save tool results. Try again."})
                return

            api_messages.append({"role": "assistant", "content": assistant_content})
            api_messages.append({"role": "user", "content": tool_results})
            continue

        # No tool use — text was already streamed live via token events.
        final_text = "\n".join(
            block.text for block in response.content if block.type == "text"
        )

        # Save the final message
        try:
            assistant_msg = ChatMessage.objects.create(
                session=session, role="assistant", content=final_text,
            )
        except Exception:
            logger.exception("Failed to save final assistant message to DB")
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

        yield sse("done", {"message_id": assistant_msg.pk})
        return

    # Max iterations reached (for-else)
    _safe_create_message(
        session,
        "I reached the maximum number of tool calls for this message. Please try a more specific question.",
    )
    yield sse("error", {"message": "Max tool iterations reached"})
