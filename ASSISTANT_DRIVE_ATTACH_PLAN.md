# Assistant — Drive File Attach — Implementation Plan

## Overview

**Goal:** Let the user attach Google Drive files to the assistant chat composer (via the in-app Drive browser modal that shipped today) so the assistant can bulk-link them to a chosen entity in one tool call. Works alongside the existing email-attach flow.

**Approach:** Add one new conditionally-registered assistant tool (`bulk_link_drive_files`) wrapping the already-shipped `documents.bulk_create_and_link` endpoint. Consolidate the existing standalone email-attach button into a new "+" attach menu. Render attached files as a collapsible summary above the textarea, and as a count-only footer in the user's message bubble after sending.

**Baseline release:** v0.22.x-alpha (commit 3ceed64 — Drive browser modal shipped today). Tag a fresh baseline before this work begins.

**Rollback:** If anything goes sideways, reset to the pre-implementation tag.

**Sketch reference:** `.planning/sketches/007-assistant-drive-attach/` — winners locked: 1B (combined "+" menu) · 2C (collapsible summary) · 3C (footer attribution) · 4A (pre-action confirm — implemented via existing `dry_run` pattern).

---

## Milestone Tracker

| # | Milestone | Status | Files Changed | Notes |
|---|-----------|--------|---------------|-------|
| 1 | Backend tool + system prompt + display_content | Not started | ~5 | New `bulk_link_drive_files` tool; conditional registration; marker stripping |
| 2 | Composer UI (+ menu, collapsible summary, Drive picker wiring) | Not started | ~3 | Replaces standalone email icon with consolidated "+" menu |
| 3 | History bubble footer attribution | Not started | ~2 | Parses marker, renders count-only footer with hover tooltip |
| 4 | Tests + sample data + manual verification | Not started | ~4 | Unit tests, e2e test, sample-data update, full Definition of Done |

---

## Design Principles

1. **Match the existing assistant safety posture.** The assistant already requires `dry_run=true` previews before any write (per system-prompt rule 1). The new tool MUST follow the same pattern — there is no auto-execute path. The "confirmation card" from the sketch is just the markdown-formatted preview text the assistant emits during dry-run; the user types "confirm" / "yes" / "go ahead" and the assistant re-calls the tool with `dry_run=false`. No new HTMX confirmation widgets, no new state machine.
2. **Drive attach is additive, not a refactor.** When the user has not picked any Drive files, the chat composer behaves exactly as today (minus the icon consolidation). When the user does not have Google Drive connected, the Drive option in the "+" menu is hidden.
3. **Conditional tool registration.** The new tool is only included in the `TOOL_DEFINITIONS` array sent to Claude when the current user message contains an `[AttachedDriveFiles]` block. Messages without attachments see an identical toolset to today — zero surface-area change for 99% of interactions.
4. **Reuse the battle-tested endpoint.** `bulk_create_and_link` (documents/views.py:430+) already handles Document creation, dedupe on `gdrive_file_id`, and FK linking. The new tool wraps this logic; it does not reimplement it.
5. **No DB schema changes.** Attached file metadata is parsed back out of the message marker at render time (parallel to how `display_content` already handles `[AttachedEmail:...]`).
6. **Email-attach behavior is preserved bit-for-bit.** Consolidating the email button into the "+" menu is the only change to the existing flow — the picker panel, JSON marker format, attachment badge, and submit handler all remain functional.

---

## Architecture Summary

```
assistant/
├── tools.py                 ← Add bulk_link_drive_files() function + tool definition
├── client.py                ← Conditional tool registration; replace Step 7 system prompt block
├── models.py                ← Extend ChatMessage.display_content + new attached_drive_files property
└── templates/assistant/
    ├── chat.html            ← Replace email icon with + menu; add Drive picker wiring; collapsible summary
    └── partials/
        └── _message.html    ← Add count-only footer with hover tooltip

documents/
└── views.py                 ← (No change — bulk_create_and_link already exists)

dashboard/management/commands/
└── load_sample_data.py      ← Seed one assistant ChatMessage with attached drive files marker for QA
```

---

## Marker Format

To match the existing `[AttachedEmail:...]\n...\n[/AttachedEmail]\n` pattern, the new marker uses the same prefix-block convention:

```
[AttachedDriveFiles]
[{"id":"1A2b3...","name":"Term Sheet.pdf","mimeType":"application/pdf","url":"https://drive.google.com/file/d/.../view"},{"id":"...","name":"NDA-Smith-2026.pdf","mimeType":"application/pdf","url":"..."}]
[/AttachedDriveFiles]
{user's actual message text}
```

- The block is prepended to `chat-input` value just before form submit (parallel to `_buildAttachedEmailBlock` in chat.html line ~410).
- The middle line is JSON (a list of file dicts). Always one line — no pretty-printing.
- `display_content` strips the entire block (opening tag through closing tag plus the trailing newline).
- A new `attached_drive_files` property on `ChatMessage` parses the JSON list and returns it (or `[]` if no marker present).
- Multiple attached blocks (drive + email) can coexist on one message — the strippers run in sequence.

---

## Tool Specification

```python
{
  "name": "bulk_link_drive_files",
  "description": (
    "Create Document records for one or more Google Drive files and link them to a "
    "single target entity in a single batch. Use this when the user has attached "
    "Drive files (you'll see an [AttachedDriveFiles] block in the user's message) "
    "and wants them linked to a property, stakeholder, investment, etc. "
    "IMPORTANT: Always call with dry_run=true first to preview, show the user the "
    "target entity and file list, and get their confirmation before calling again "
    "with dry_run=false. NEVER skip the preview step."
  ),
  "input_schema": {
    "type": "object",
    "properties": {
      "entity_type": {
        "type": "string",
        "enum": ["realestate", "investment", "loan", "lease", "policy",
                 "vehicle", "aircraft", "stakeholder", "legalmatter"],
        "description": "The target entity type to link the files to."
      },
      "entity_id": {
        "type": "integer",
        "description": "Primary key of the target entity. If you just created the entity, use the new pk returned by create_record."
      },
      "files": {
        "type": "array",
        "description": "Drive files to link. Each item: {id, name, mimeType, url}. Pass the file list verbatim from the [AttachedDriveFiles] block in the user's message.",
        "items": {
          "type": "object",
          "properties": {
            "id":       {"type": "string", "description": "Google Drive file ID"},
            "name":     {"type": "string", "description": "Filename (with extension)"},
            "mimeType": {"type": "string", "description": "Drive MIME type"},
            "url":      {"type": "string", "description": "Drive shareable URL"}
          },
          "required": ["id", "name", "mimeType", "url"]
        }
      },
      "dry_run": {
        "type": "boolean",
        "description": "If true, preview only (no database changes). Always preview first.",
        "default": True
      }
    },
    "required": ["entity_type", "entity_id", "files"]
  }
}
```

**Handler return shape (dry_run=true):**

```json
{
  "dry_run": true,
  "target": {"entity_type": "realestate", "entity_id": 18, "name": "Smith Property"},
  "would_create": [
    {"name": "Term Sheet.pdf", "gdrive_file_id": "1A2b3...", "action": "create_and_link"},
    {"name": "NDA-Smith-2026.pdf", "gdrive_file_id": "5C6d7...", "action": "link_existing"}
  ],
  "summary": "Would create 1 new Document and link 1 existing Document (matched by gdrive_file_id) to Smith Property."
}
```

**Handler return shape (dry_run=false):**

```json
{
  "dry_run": false,
  "target": {"entity_type": "realestate", "entity_id": 18, "name": "Smith Property"},
  "linked": [
    {"document_id": 142, "name": "Term Sheet.pdf", "created": true},
    {"document_id": 87, "name": "NDA-Smith-2026.pdf", "created": false}
  ],
  "summary": "Linked 2 documents (1 created, 1 reused) to Smith Property."
}
```

The handler internally calls the existing `documents.views.bulk_create_and_link` view function (refactored to be importable, see Milestone 1) — does not perform an HTTP round-trip.

---

## Milestone 1: Backend (tool + system prompt + marker stripping)

### Scope

Add the `bulk_link_drive_files` tool to `assistant/tools.py`, wire it into `TOOL_HANDLERS`, register it conditionally in `assistant/client.py` (only when the user message contains `[AttachedDriveFiles]`), replace the loose Step 7 system-prompt instructions with a concrete directive that uses the new tool, and extend `ChatMessage.display_content` plus add `attached_drive_files` property.

### Checklist

**Refactor `documents.views.bulk_create_and_link` for internal use:**
- [ ] Extract the inner logic of `bulk_create_and_link` into a pure function `documents.services.bulk_link_drive_files(entity_type, entity_id, files, dry_run=False)` returning a dict (no `request`/`HttpResponse`)
- [ ] Update the existing view to call the service function and wrap the dict in a JsonResponse
- [ ] Service function handles: entity validation, FK field name lookup (existing pattern in `ENTITY_CONFIG`), Document creation with gdrive_* fields, dedupe on `gdrive_file_id`, returning structured result (dry_run preview vs actual)
- [ ] Existing endpoint behavior unchanged — verified by all existing documents tests still passing

**New tool in `assistant/tools.py`:**
- [ ] Add `bulk_link_drive_files(entity_type, entity_id, files, dry_run=True)` function — calls `documents.services.bulk_link_drive_files`, returns the dict directly
- [ ] Add tool definition to `TOOL_DEFINITIONS` list (schema as specified above) — placed after `delete_record`
- [ ] Add `"bulk_link_drive_files": bulk_link_drive_files` to `TOOL_HANDLERS` mapping
- [ ] The tool uses `additionalProperties: False` on the file item schema for strict validation
- [ ] Returns clear error dict if `entity_type` invalid, `entity_id` not found, or `files` list empty

**Conditional registration in `assistant/client.py`:**
- [ ] Add helper `_get_active_tools(messages)` that returns the full `TOOL_DEFINITIONS` list MINUS `bulk_link_drive_files` UNLESS the most recent user message content contains the literal substring `[AttachedDriveFiles]`
- [ ] Call this helper instead of passing `TOOL_DEFINITIONS` directly when constructing the API request
- [ ] When the tool is excluded, the resulting tools array is byte-identical to today's — verified by snapshot test

**System prompt update at `client.py:175` (Step 7):**
- [ ] REPLACE the existing Step 7 block (currently 5 lines about "Attached Google Drive files" and `create_record`) with the new directive (concrete tool name, dry-run discipline, target-resolution rules)
- [ ] New block content (verbatim):
  ```
  ### Step 7: Google Drive file attachments
  When the user's message contains an `[AttachedDriveFiles]` block, the user has selected Google Drive files to be linked as Documents in the system. The block is JSON: a list of file dicts {id, name, mimeType, url} between `[AttachedDriveFiles]` and `[/AttachedDriveFiles]` markers.

  Workflow:
  1. **Identify the target entity.** The user will name it ("attach to the Smith Property", "link to Stakeholder John Smith", etc.). Use `search` to resolve it and `get_record` to confirm. If the user is asking you to first CREATE a new entity from an attached email AND link these files to it, do `create_record` for the entity first (with its own dry_run preview), then proceed.
  2. **Preview with dry_run=true.** Call `bulk_link_drive_files` with `entity_type`, `entity_id`, the full `files` list (verbatim from the block), and `dry_run=true`. The response shows which files would be created vs reused (dedupe by gdrive_file_id).
  3. **Show the user.** Present the preview as a structured markdown block:
     > **About to attach N files to {Entity Name}** (RealEstate · #18)
     > - Term Sheet.pdf (new)
     > - NDA-Smith-2026.pdf (already exists, will reuse)
     >
     > Confirm to proceed.
  4. **Wait for confirmation.** Do not execute until the user replies "yes" / "confirm" / "go ahead" or similar. If they amend the target ("actually link to the Investment instead"), restart at step 1.
  5. **Execute with dry_run=false.** Same arguments, dry_run=false. Report the result ("Linked 2 documents to Smith Property — 1 new, 1 reused") concisely.

  Never call `bulk_link_drive_files` with dry_run=false on the same turn as the dry_run=true preview. Always wait one full user turn for confirmation.

  When the message also contains an `[AttachedEmail]` block AND the user is asking you to extract entities from the email AND link the files (the common combined-flow case), do steps 1-5 of the email pipeline first (search → plan → confirm → execute), then proceed with steps 1-5 above for the files. The email's plan and the files' plan can be presented together in a single Step 3 plan if it makes the user's review faster.
  ```
- [ ] Verify the new block does not break system-prompt caching — the preamble is one big string concatenated with the schema; ordering changes are fine, content shrinkage is fine

**`ChatMessage` model in `assistant/models.py`:**
- [ ] Extend `display_content` property to also strip the `[AttachedDriveFiles]\n...\n[/AttachedDriveFiles]\n` block (place after the existing AttachedEmail strip, before the Context strip)
- [ ] Add new property `attached_drive_files` returning `list[dict]`:
  ```python
  @property
  def attached_drive_files(self):
      """Parse the [AttachedDriveFiles] block from content and return the file list."""
      import json
      text = self.content or ""
      open_marker = "[AttachedDriveFiles]"
      close_marker = "[/AttachedDriveFiles]"
      i = text.find(open_marker)
      if i < 0:
          return []
      j = text.find(close_marker, i)
      if j < 0:
          return []
      json_text = text[i + len(open_marker):j].strip()
      try:
          parsed = json.loads(json_text)
          return parsed if isinstance(parsed, list) else []
      except (ValueError, TypeError):
          return []
  ```
- [ ] Add `attached_email_summary` property returning a dict (or None) parsed from the `[AttachedEmail:{json}]` marker — this is needed for the footer rendering to show "✉ 1 email" when an email is attached. Returns `{"subject": "...", "message_count": N}` or `None`.

**Unit tests (`assistant/tests.py`):**
- [ ] Test: `bulk_link_drive_files` with valid input, dry_run=true returns expected preview shape
- [ ] Test: `bulk_link_drive_files` with valid input, dry_run=false creates Document records and FK links them
- [ ] Test: dedupe — calling twice with the same `gdrive_file_id` reuses the existing Document, does not create a duplicate
- [ ] Test: invalid `entity_type` returns error dict
- [ ] Test: `entity_id` not found returns error dict
- [ ] Test: empty `files` list returns error dict
- [ ] Test: `_get_active_tools` returns 11 tools when no `[AttachedDriveFiles]` in messages (matches existing baseline)
- [ ] Test: `_get_active_tools` returns 12 tools when `[AttachedDriveFiles]` IS in the most recent user message
- [ ] Test: `ChatMessage.display_content` strips the new marker (and combined with email marker on same message)
- [ ] Test: `ChatMessage.attached_drive_files` parses the marker and returns the list of file dicts
- [ ] Test: `ChatMessage.attached_drive_files` returns `[]` when no marker present, malformed JSON, or missing close marker
- [ ] Test: `ChatMessage.attached_email_summary` parses the existing `[AttachedEmail:{...}]` marker and returns subject + message_count

### Verification

- [ ] `make test-unit` — all existing + new tests pass
- [ ] `python manage.py shell` smoke test: register a session, send a synthetic message containing `[AttachedDriveFiles]` block + a question, verify `_get_active_tools` returns 12 entries
- [ ] No changes to non-assistant tests (documents tests still pass after the service refactor)

---

## Milestone 2: Composer UI ("+" menu, collapsible summary, Drive picker wiring)

### Scope

In the chat composer, replace the standalone email icon with a single "+" attach menu (popover with Email / Drive entries). Render attached files as a collapsible summary bar. Wire the in-app Drive browser modal (`_drive_browser_modal.html`) to populate the file list on pick.

### Checklist

**Replace email icon with "+" menu (`assistant/templates/assistant/chat.html`):**
- [ ] Remove the `<button id="attach-email-btn">` block (lines ~213-216)
- [ ] Add a new attach-menu container left of the textarea:
  ```html
  <div class="relative">
    <button type="button" id="attach-menu-btn" onclick="toggleAttachMenu()" title="Attach"
            class="text-gray-400 hover:text-gray-200 shrink-0 self-end p-2 -ml-1 transition-colors">
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
      </svg>
    </button>
    <div id="attach-menu-popover" class="hidden absolute bottom-full mb-1 left-0 z-50
         bg-gray-800 border border-gray-600 rounded-md shadow-lg py-1 min-w-[10rem]">
      {% if gmail_available %}
      <button type="button" onclick="openEmailFromMenu()"
              class="w-full text-left px-3 py-1.5 text-sm text-gray-200 hover:bg-gray-700 flex items-center gap-2">
        <svg class="w-4 h-4 text-green-400" ...>{mail icon}</svg>
        Email
      </button>
      {% endif %}
      {% if drive_connected %}
      <button type="button" onclick="openDriveFromMenu()"
              class="w-full text-left px-3 py-1.5 text-sm text-gray-200 hover:bg-gray-700 flex items-center gap-2">
        <svg class="w-4 h-4 text-blue-400" ...>{drive icon}</svg>
        Drive files
      </button>
      {% endif %}
    </div>
  </div>
  ```
- [ ] Add `chat_view` context: pass `drive_connected = GoogleDriveSettings.load().is_connected` (from `documents.models`) — view at `assistant/views.py`
- [ ] JS: `toggleAttachMenu()` — toggle popover visibility; close on outside click (delegate listener)
- [ ] JS: `openEmailFromMenu()` — closes menu, calls existing `toggleEmailPicker()` (preserves existing behavior)
- [ ] JS: `openDriveFromMenu()` — closes menu, opens the in-app Drive browser modal (new wiring, see below)

**Drive browser modal wiring:**
- [ ] Include the existing `_drive_browser_modal.html` partial in `chat.html` (e.g., at the bottom of the chat-area container, conditional on `drive_connected`)
- [ ] The modal already has its own JS in `static/js/gdrive-browser.js` and accepts a callback for selection. Identify the callback signature (read `_drive_browser_modal.html` + `gdrive-browser.js` first task).
- [ ] In chat.html JS, register a callback that receives the picked files array `[{id, name, mimeType, url}, ...]` and pushes each into `_attachedDriveFiles` (deduped on `id`)
- [ ] Trigger `_renderDriveSummary()` after each pick

**Collapsible summary above textarea:**
- [ ] Replace the existing `attached-email-badge` block (chat.html:162-171) with a generic `attached-context-summary` container that holds zero or more rows
- [ ] Email summary row (when `_attachedEmail` is set) — single-line badge identical to today's (subject + count + ✕)
- [ ] Drive summary row (when `_attachedDriveFiles.length > 0`) — collapsible bar:
  - Collapsed: `📁 N files attached · {first filename if N=1}` with caret + ✕ (✕ clears all)
  - Expanded: collapsed bar PLUS a list of filenames each with its own ✕ (removes single file)
- [ ] JS state: `_attachedDriveFiles = []` (mirrors the existing `_attachedEmail` pattern)
- [ ] JS: `_addDriveFile(file)` (dedupes by id, calls `_renderDriveSummary`)
- [ ] JS: `_removeDriveFile(id)` and `_clearDriveFiles()`
- [ ] JS: `_renderDriveSummary()` — rebuilds the DOM for the drive summary row (collapsed by default; remembers expanded state across renders via a module-level boolean)
- [ ] JS: `_buildAttachedDriveFilesBlock()` returns the marker string (parallel to `_buildAttachedEmailBlock`):
  ```javascript
  function _buildAttachedDriveFilesBlock() {
    if (_attachedDriveFiles.length === 0) return '';
    return '[AttachedDriveFiles]\n' + JSON.stringify(_attachedDriveFiles) + '\n[/AttachedDriveFiles]\n';
  }
  ```
- [ ] Update the form submit handler (chat.html:464+) to prepend BOTH the email block and the drive block (in that order) to the user text:
  ```javascript
  if (_attachedEmail)            text = _buildAttachedEmailBlock(_attachedEmail) + text;
  if (_attachedDriveFiles.length) text = _buildAttachedDriveFilesBlock() + text;
  // (then clear both)
  ```
- [ ] After submit, clear `_attachedDriveFiles` and re-render

**Tailwind classes:**
- [ ] All new classes use existing Tailwind utilities (gray-800, gray-700, blue-400, green-400, etc.) — no new design tokens
- [ ] Run `make tailwind-build` after wiring

### Verification

- [ ] cmux desktop check at 1512×982: open `/assistant/`, click "+" — popover appears with Email + Drive options
- [ ] Click Email — existing email picker panel opens (regression check)
- [ ] Click Drive files — in-app Drive browser modal opens
- [ ] Pick 1 file — collapsed summary shows filename
- [ ] Pick 3 more files — collapsed summary shows "4 files attached"; click bar to expand, individual ✕ removes one file, bar ✕ clears all
- [ ] iOS Simulator (iPhone 16e): "+" menu and collapsible summary fit at 375pt without overflow

---

## Milestone 3: History bubble footer attribution

### Scope

After a message is sent, render a thin dashed footer in the user's message bubble showing the count of attached emails and drive files, with hover tooltip listing names.

### Checklist

**Update `assistant/templates/assistant/partials/_message.html`:**
- [ ] Inside the user message bubble (after the `<p>` rendering `display_content`), add a footer block conditional on either `message.attached_email_summary` or `message.attached_drive_files`:
  ```django
  {% if message.attached_email_summary or message.attached_drive_files %}
  <div class="mt-2 pt-1.5 border-t border-dashed border-blue-600/30 text-[10px] text-gray-400 flex gap-3 items-center">
    {% if message.attached_email_summary %}
    <span title="{{ message.attached_email_summary.subject }}{% if message.attached_email_summary.message_count > 1 %} ({{ message.attached_email_summary.message_count }} msgs){% endif %}"
          class="inline-flex items-center gap-1">
      <svg class="w-3 h-3 text-green-400" ...>{mail icon}</svg>
      1 email
    </span>
    {% endif %}
    {% if message.attached_drive_files %}
    <span title="{% for f in message.attached_drive_files %}{{ f.name }}{% if not forloop.last %}, {% endif %}{% endfor %}"
          class="inline-flex items-center gap-1">
      <svg class="w-3 h-3 text-blue-400" ...>{drive icon}</svg>
      {{ message.attached_drive_files|length }} file{{ message.attached_drive_files|length|pluralize }}
    </span>
    {% endif %}
  </div>
  {% endif %}
  ```
- [ ] Footer renders ONLY for `message.role == "user"` (already gated by the surrounding template block)
- [ ] Hover tooltip uses native `title` attribute (no JS) — comma-joined filenames; if very long, truncates per browser default

**Visual refinement:**
- [ ] Verify dashed border color (`border-blue-600/30`) reads correctly inside the existing `bg-blue-600/20 border-blue-600/30` user bubble
- [ ] Verify text weight + size against the existing timestamp (`text-xs text-gray-600`) — footer uses slightly smaller (`text-[10px] text-gray-400`) to feel like metadata, not body text

### Verification

- [ ] cmux desktop check: send a message with 1 email + 3 files attached → user bubble shows text + footer "✉ 1 email · 📁 3 files"
- [ ] Hover footer items — native tooltip shows email subject and comma-joined filenames
- [ ] Send a message with no attachments — no footer appears
- [ ] Edit & Resend on a message-with-attachments: the existing flow puts `display_content` into the textarea, which means the marker is stripped — attachments do NOT carry over on re-send. This is intentional for now (re-send is rare and re-attaching is fast); flag as a known limitation in the Usage Guide.

---

## Milestone 4: Tests + sample data + Definition of Done

### Scope

E2E coverage of the full happy path, sample data update so the rendering can be verified without configuring real Google Drive, and the full Definition-of-Done checklist from CLAUDE.md.

### Checklist

**E2E test (`e2e/test_assistant_drive_attach.py`):**
- [ ] Test: navigate to `/assistant/`, open the new chat, click "+" → popover appears
- [ ] Test: simulate message submission with a hardcoded `[AttachedDriveFiles]` block (bypasses real Drive picker which needs OAuth) → message saves, user bubble shows footer with "📁 N files"
- [ ] Test: hover/long-press the footer → tooltip text contains all filenames
- [ ] Test: send the same message contents twice — assistant tool call (mocked Anthropic response in test) routes through `_get_active_tools` → second call has the new tool registered

**Sample data update (`dashboard/management/commands/load_sample_data.py`):**
- [ ] Add a sample `ChatSession` titled "Smith Property docs" if it doesn't exist
- [ ] Add 2 sample `ChatMessage` records to that session:
  - User message containing `[AttachedDriveFiles]\n[{...3 files about Smith Property...}]\n[/AttachedDriveFiles]\nAttach these to Smith Property` (use the actual Smith property PK from the existing sample data — look up at runtime)
  - Assistant message: `Linked 3 documents to **Smith Property** (RealEstate · #N).`
- [ ] Update `clean_sample_data.py` to remove this session by title
- [ ] Update SAMPLE_NAMES if needed

**Definition of Done (per CLAUDE.md):**
- [ ] (a) `make test-unit` (Docker) — all pass; `make test-e2e` (local) — all pass
- [ ] (b) Interactive verification in Docker on :8000:
  - Open `/assistant/`
  - Click "+" → popover toggles correctly; outside click closes it
  - Click Email → existing email picker panel opens (regression check — picker, search, label dropdown, thread selection all work)
  - Pick an email — green badge appears as today
  - Click "+" → Drive files → Drive browser modal opens
  - Pick 1, 3, and 6 files in three separate sessions — collapsible summary scales correctly
  - Send a message with email + drive files → assistant performs dry-run, shows the preview, user types "confirm" → bulk-link executes → assistant reports linked docs
  - Navigate to the target entity detail page — confirm the new Documents are linked
  - Refresh the chat page — history footer renders with correct counts and hover tooltips intact
  - Verify HTMX swaps don't blow away the attach state (state is JS-only; HTMX swaps for messages should not touch composer DOM)
- [ ] (c) Desktop screenshots via Playwright at 1512×982 (MacBook Pro) and 960×1080 (4K split):
  - Composer with attach popover open
  - Composer with 1 email + 3 drive files attached (summary collapsed and expanded)
  - History bubble with footer
  - Confirmation preview from the assistant
- [ ] (d) Desktop headed pass: keyboard nav (Tab through composer reaches "+" then textarea then Send), Enter submits, Shift+Enter newlines, Esc closes popover
- [ ] (e) iOS Simulator (iPhone 16e at 375pt): "+" menu reachable, popover doesn't overflow viewport, collapsible summary readable, picker modal scrollable
- [ ] (f) `make tailwind-build` (no new utility classes were used, but rerun to confirm)

---

## Failure Mode Matrix

| Failure | User Experience | App Impact |
|---------|----------------|------------|
| Drive not connected | "Drive files" option hidden from "+" menu. Email-only attach still works. | Zero |
| User picks 0 files in modal | Modal closes, no summary appears, composer state unchanged. | Zero |
| Drive browser modal fails to load | "+" menu Drive option click silently no-ops; user can still attach email. Existing modal failure handling applies. | Zero |
| User sends message with `[AttachedDriveFiles]` but no target named in their text | Assistant asks "Which entity should I link these to?" before calling the tool. (Per system prompt Step 7 step 1.) | Zero |
| User cancels at the dry-run preview ("never mind") | Assistant acknowledges, no tool call with dry_run=false. Files remain in marker on the message but are now orphaned context — next message can re-reference them or ignore them. | Zero |
| `bulk_link_drive_files` fails mid-batch (e.g., DB error after creating 2 of 3 docs) | Existing endpoint behavior preserved — partial creates committed before the error remain; assistant reports the partial success and the error from the tool result. | Documents may be in a half-linked state — same as today's bulk-link endpoint behavior. |
| User edits & resends a message that had attached files | Files are NOT carried into the resend (display_content strips the marker before populating the textarea). User must re-pick. Documented as known limitation. | Zero |
| Conditional registration false-negative (assistant message also contains the marker text) | The `_get_active_tools` helper checks the most recent USER message only, not assistant messages — so this can't happen. | Zero |
| User attaches 50+ files | Marker JSON is large but well under the message size limit. Anthropic API can handle it; bulk-link endpoint is already O(N). UX-wise, summary bar caps at scrollable list. | Mild — slow tool call; future enhancement could chunk. |

---

## Pages & URLs Affected

### Modified Pages

| Page | What Changed |
|------|-------------|
| **Assistant Chat** (`assistant/templates/assistant/chat.html`) | Email button replaced with "+" attach menu; collapsible drive-files summary; drive picker modal included; new JS state and helpers |
| **Assistant Message Partial** (`assistant/templates/assistant/partials/_message.html`) | New attachment footer in user bubble |

### No New URLs

The new tool is purely internal (assistant → Python service function). No new HTTP endpoints needed because the existing bulk-link endpoint is already in place and will be reused via service refactor.

---

## Dependencies Added

None. Uses existing `anthropic`, Django, and HTMX infrastructure.

---

## Usage Guide

### Attaching Drive Files to the Assistant

**Prerequisites:** Google Drive must be connected (Settings → Google Drive). If not connected, the "Drive files" option won't appear in the attach menu.

1. Open the assistant chat (`/assistant/`)
2. Click the **+** icon left of the message textarea
3. Select **Drive files** → the in-app Drive browser modal opens
4. Pick one or more files (folders expand inline) → modal closes
5. The composer shows a **📁 N files attached** bar above the textarea — click to expand, ✕ to remove individual files or clear all
6. Type your instruction. Be explicit about where the files should go — e.g., *"Attach these to the Smith Property"* or *"Link to Stakeholder John Smith"*
7. Click **Send**
8. The assistant will:
   - Look up the target entity
   - Show you a preview: *"About to attach 3 files to Smith Property: Term Sheet.pdf (new), NDA-Smith-2026.pdf (already exists, will reuse)…"*
   - Wait for your confirmation
9. Reply **yes** / **confirm** / **go ahead** → the assistant executes and reports the result
10. Navigate to the target entity's detail page → the new Documents appear in its Documents section

### Combined Email + Drive Attach

The common workflow — attach an email AND a few Drive documents, ask the assistant to extract entities and link the docs:

1. Click **+** → **Email** → search and pick an email thread (existing flow, unchanged)
2. Click **+** → **Drive files** → pick the relevant Drive files
3. Both attachments are summarized above the textarea (one row each)
4. Type your instruction: *"Process this email and attach these files to whatever Property/Investment it discusses"*
5. The assistant will extract entities from the email per the existing email-processing pipeline, then run the file-attach pipeline against the entity it identified or created. Both previews come back together for your single confirmation.

### History Footer

After a message is sent, the user's bubble shows a thin dashed footer with attachment counts:

- **✉ 1 email · 📁 3 files** — hover (or long-press on mobile) for the email subject and comma-joined filenames

The full attached content is preserved in the message data but hidden from view to keep the bubble clean. The assistant can still read the attached content when re-prompted on the same conversation thread.

### Known Limitations

- **Edit & Resend doesn't carry attachments.** If you edit a previously-sent message, the attached files are not re-attached — re-pick them if you want to include them again. (The marker is stripped from the message text before it's loaded into the textarea.)
- **Drive must be connected before the picker is available.** Connect at Settings → Google Drive (see Drive Integration plan).
- **Email-only attach behavior is bit-for-bit preserved.** This change only affects the icon (consolidated into "+") and adds the Drive option alongside it.

---

## Testing Strategy Summary

| Layer | What's Tested | Where |
|-------|--------------|-------|
| Service function | `bulk_link_drive_files` service: dry-run preview, real execution, dedupe, validation | `documents/tests.py` |
| Tool handler | Tool wraps service correctly, returns expected dict shapes | `assistant/tests.py` |
| Conditional tool registration | Tool excluded by default, included when `[AttachedDriveFiles]` in user message | `assistant/tests.py` |
| Marker parsing | `display_content` strips marker, `attached_drive_files` and `attached_email_summary` parse correctly | `assistant/tests.py` |
| System prompt | New Step 7 block present and correctly worded | `assistant/tests.py` (string assertion on `SYSTEM_PREAMBLE`) |
| Composer interaction | "+" menu opens/closes; Drive modal wiring; collapsible summary; submit appends marker | `e2e/test_assistant_drive_attach.py` (Playwright) |
| History rendering | Footer renders for messages with attachments, tooltip text correct | `e2e/test_assistant_drive_attach.py` |
| Existing flows | Email attach still works; messages without attachments use identical toolset | `assistant/tests.py` + manual regression |
| Mobile | iPhone 16e (375pt) layout doesn't break | iOS Simulator manual + screenshot |

---

## Out of Scope (Deferred)

- **Migrating `_process_email_form.html` Drive section to the new in-app browser.** That modal still uses the old `gapi` Picker. Worth doing in a follow-up phase but not part of this work.
- **Native HTMX confirmation buttons.** The dry-run-preview-then-confirm flow is conversational. If a future user prefers explicit click-to-confirm UI, that's an opt-in setting we can add later.
- **Attachment carry-over on Edit & Resend.** Documented as a known limitation. Would require persisting attachment metadata separately on `ChatMessage` (new field or separate model).
- **Multi-target attach in one tool call.** Current tool links files to ONE entity. If the user wants the same files linked to BOTH a Property and a Stakeholder, the assistant calls the tool twice. Multi-target could be added if it becomes a common pattern.
- **Bulk attach via folder selection.** The Drive browser modal already supports folder expansion (returns the contained files). No additional work needed here.
