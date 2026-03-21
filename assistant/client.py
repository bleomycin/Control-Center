"""
Anthropic API client for the AI assistant.

Handles system prompt construction, message formatting,
and the tool-use loop.
"""

import json
import logging

import anthropic
from django.conf import settings

from . import registry
from .tools import TOOL_DEFINITIONS, TOOL_HANDLERS, summarize

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 25
MAX_MESSAGES_TO_SEND = 50
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 8192

SYSTEM_PREAMBLE = """You are the Control Center Assistant — an AI built into a personal management system. You help the user manage their stakeholders, legal matters, assets, tasks, notes, cash flow, healthcare records, and documents.

## Your capabilities
- Search and query any data in the system using the provided tools
- Create, update, and delete records (with user confirmation)
- Answer complex questions by combining data from multiple sources
- Provide summaries and insights about the user's affairs

## Critical rules
1. **Write operations**: ALWAYS use dry_run=true first to preview changes. Show the preview to the user and explicitly ask for confirmation before executing with dry_run=false. NEVER skip the preview step.
2. **Be precise**: When querying data, use specific filters rather than loading everything. Start narrow, broaden if needed.
3. **Show your work**: When answering complex questions, briefly explain which queries you're running so the user understands.
4. **Links**: When referencing records, include their URL so the user can click through. ALWAYS use relative URLs exactly as returned by the tools (e.g., `/stakeholders/482/`). NEVER prepend a host, port, or protocol — no `http://localhost` or any domain.
5. **Dates**: Today's date is provided in the system stats. Use it for relative date calculations.
6. **Be concise**: Give direct answers. Use markdown formatting for readability — tables for comparisons, lists for enumerations, bold for key facts.
7. **Batch tool calls aggressively**: Every API round-trip adds latency. Always call as many tools as possible in a single response. If you need to search for 15 entities, call search() 15 times in one response — do NOT split them across multiple iterations. Fewer iterations = faster results for the user.

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

**Subtasks** (grouped under parent):
- Parent task title
  - [ ] Subtask 1
  - [ ] Subtask 2

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
4. **Tasks** — link to related_stakeholders, related_property, related_legal_matter as appropriate
5. **SubTasks** — under their parent tasks
6. **Note** — the email/meeting content itself, linked to all created and found entities via participants, related_stakeholders, related_properties, related_investments, related_loans, related_legal_matters, etc.

Use `create_record` with `dry_run=true` for the batch. After the user confirms, execute all with `dry_run=false`.

### Step 5: Task assignment conventions
Use the `assigned_to` field (FK to Stakeholder) for the person responsible for the task. This is distinct from `related_stakeholders` (M2M for people involved/referenced).
- **"Amanda: do X"** or **"Amanda needs to handle X"** → `direction="outbound"`, `assigned_to=Amanda's stakeholder ID`
- **"I need to do X"** or **"reminder: X"** or self-directed items → `direction="personal"`, `assigned_to` left blank
- **"Waiting on Thomas for X"** or **"Thomas to send us X"** → `direction="inbound"`, `status="waiting"`, `assigned_to=Thomas's stakeholder ID`
- **Nested lists** like "items to request from Thomas: A, B, C" → create one parent task ("Request items from Thomas", `assigned_to=Thomas`) with SubTasks for each item (A, B, C)
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

**Stakeholder entity_type** — infer from context:
- Attorney, lawyer, counsel → "Attorney"
- Bank, lender, credit line → "Lender"
- Developer, builder, contractor, architect → "Business Partner"
- Advisor, CPA, accountant, financial planner → "Advisor"
- Doctor, physician, specialist → "Professional"
- General or unclear → "Contact"

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

    # Include owner identity if configured
    from .models import AssistantSettings
    owner_name = AssistantSettings.load().owner_name
    if owner_name:
        stats_lines.append(f"System owner: {owner_name}")
        stats_lines.append(
            f"When processing emails, do NOT create a stakeholder record for {owner_name} — "
            f"that is the user. Messages from {owner_name} are first-person context. "
            f"Extract their commitments as personal tasks (direction=personal, no assigned_to)."
        )

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


def _build_api_messages(chat_messages):
    """
    Convert ChatMessage queryset to Anthropic API message format.

    Messages with tool_data are formatted as content blocks.
    Plain text messages use simple string content.
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

    return api_messages[-MAX_MESSAGES_TO_SEND:]


def _strip_empty(obj):
    """Recursively strip null/empty values from dicts to reduce token count."""
    if isinstance(obj, dict):
        return {k: _strip_empty(v) for k, v in obj.items()
                if v is not None and v != "" and v != []}
    if isinstance(obj, list):
        return [_strip_empty(item) for item in obj]
    return obj


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

            # Update session title from first exchange
            if session.title == "New Chat" and final_text:
                title = user_text[:60]
                if len(user_text) > 60:
                    title = title[:57] + "..."
                session.title = title
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
                break  # Success — exit retry loop
            except anthropic.APIStatusError as e:
                if (e.status_code >= 500 or e.status_code == 429) and attempt < 4:
                    wait = 2 ** attempt  # 1, 2, 4, 8, 16 seconds
                    logger.warning(f"Anthropic API {e.status_code} (attempt {attempt + 1}/5), retrying in {wait}s")
                    import time
                    time.sleep(wait)
                    continue
                # Final attempt or non-retryable error
                logger.error(f"Anthropic API error: {e}")
                ChatMessage.objects.create(
                    session=session, role="assistant",
                    content="The AI service is temporarily unavailable. Please try again in a minute.",
                )
                yield sse("error", {"message": "Service temporarily unavailable. Please try again."})
                return
            except anthropic.APIError as e:
                logger.error(f"Anthropic API error: {e}")
                ChatMessage.objects.create(
                    session=session, role="assistant", content=f"API error: {e}",
                )
                yield sse("error", {"message": str(e)})
                return
            return

        has_tool_use = any(block.type == "tool_use" for block in response.content)

        if has_tool_use:
            # Clear any text that streamed before tool_use was detected
            yield sse("clear", {})

            # Save tool_use message
            assistant_content = []
            for block in response.content:
                if block.type == "text":
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_content.append({
                        "type": "tool_use", "id": block.id,
                        "name": block.name, "input": block.input,
                    })

            ChatMessage.objects.create(
                session=session, role="assistant", content="",
                tool_data=assistant_content,
            )

            # Execute tools
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    yield sse("tool_start", {"name": block.name})
                    result_str = _execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })
                    yield sse("tool_done", {"name": block.name})

            ChatMessage.objects.create(
                session=session, role="user", content="",
                tool_data=tool_results,
            )

            api_messages.append({"role": "assistant", "content": assistant_content})
            api_messages.append({"role": "user", "content": tool_results})
            continue

        # No tool use — text was already streamed live via token events.
        final_text = "\n".join(
            block.text for block in response.content if block.type == "text"
        )

        # Save the final message
        assistant_msg = ChatMessage.objects.create(
            session=session, role="assistant", content=final_text,
        )

        # Update session title
        if session.title == "New Chat" and final_text:
            title = user_text[:60]
            if len(user_text) > 60:
                title = title[:57] + "..."
            session.title = title
            session.save(update_fields=["title", "updated_at"])

        yield sse("done", {"message_id": assistant_msg.pk})
        return

    # Max iterations reached (for-else)
    ChatMessage.objects.create(
        session=session, role="assistant",
        content="I reached the maximum number of tool calls for this message. Please try a more specific question.",
    )
    yield sse("error", {"message": "Max tool iterations reached"})
