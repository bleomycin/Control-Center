/**
 * Shared chat engine for the assistant.
 * Used by both the full /assistant/ page and the global drawer.
 *
 * Usage:
 *   var engine = createChatEngine({ streamUrl, csrfToken, ... });
 *   engine.doSend("Hello");
 */

/* global marked */

// Configure marked.js once (idempotent)
if (typeof marked !== 'undefined') {
    marked.setOptions({ breaks: true, gfm: true });
}

// Mirror of dashboard/templatetags/markdown_filter.py:_APP_PREFIXES /
// _BARE_APP_HREF. During streaming, markdown is rendered client-side by
// marked.js — the server-side filter only runs after the stream ends.
// Apply the same bare-app-path repair here so mid-stream link clicks
// don't hit /assistant/<prefix>/... 404s.
var _APP_PREFIXES = [
    'assets', 'stakeholders', 'legal', 'tasks', 'cashflow', 'notes',
    'healthcare', 'documents', 'emails', 'checklists', 'assistant',
    'settings'
];
var _BARE_APP_HREF = new RegExp(
    '(<a\\s[^>]*?\\bhref=")(' + _APP_PREFIXES.join('|') + ')/',
    'gi'
);

// Recovery after a severed stream: the server finishes a disconnected turn in
// the background (assistant/client.py detached drain), so the client polls
// turn-status until the answer lands instead of treating EOF as success.
var RECOVERY_POLL_MS = 4000;
// Give up polling after this long — matches the server's drain budget order
// of magnitude (Opus max-effort turns can legitimately run many minutes).
var RECOVERY_BUDGET_MS = 15 * 60 * 1000;

var SPINNER_SVG = '<svg class="w-4 h-4 animate-spin shrink-0" fill="none" viewBox="0 0 24 24">'
    + '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>'
    + '<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/>'
    + '</svg>';

function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderMarkdown(text) {
    return marked.parse(text).replace(_BARE_APP_HREF, '$1/$2/');
}

/**
 * Create a chat engine instance.
 *
 * @param {Object} config
 * @param {string} config.streamUrl       - SSE endpoint URL
 * @param {string} config.csrfToken       - CSRF token
 * @param {Element} config.messageListEl  - message container
 * @param {Element} config.scrollEl       - scrollable parent
 * @param {Element} config.inputEl        - textarea
 * @param {Element} config.sendBtnEl      - send button
 * @param {Element|null} config.emptyStateEl - empty state (nullable)
 * @param {number} config.sessionPk       - session ID
 * @param {string} config.messagesUrl     - URL to fetch rendered messages
 * @param {string} config.turnStatusUrl   - JSON endpoint for turn state (stream recovery)
 * @param {function():string|null} config.getPageContext - returns context string or null
 * @param {function()} config.onFinish    - callback after stream ends
 * @param {function(string)} config.onTitle - callback for title events (nullable)
 * @returns {Object} engine with doSend, loadMessages, refreshMessages, autoScroll, isStreaming
 */
function createChatEngine(config) {
    var streaming = false;
    var collectedText = '';
    var firstToken = true;
    var currentMode = 'fast';  // Sticky per-session: "fast", "think", "max"
    // Direct DOM refs to current stream elements (no IDs needed)
    var currentStreamContent = null;
    var currentStreamTools = null;
    var inactivityTimer = null;
    var endedWithError = false;
    var endedWithTimeout = false;  // watchdog fired (vs. a server-sent error)
    var finished = false;          // guard: finish() may be reached >1 way
    var abortController = null;     // tears down the fetch when we give up
    var sawTerminal = false;       // a done/error SSE event arrived this stream
    var recovering = false;        // polling turn-status after a severed stream
    var recoverTimer = null;
    var recoverDeadline = 0;

    function autoScroll() {
        config.scrollEl.scrollTop = config.scrollEl.scrollHeight;
    }

    function resetWatchdog() {
        if (inactivityTimer) clearTimeout(inactivityTimer);
        inactivityTimer = setTimeout(function() {
            // 90s of total silence despite the server's 5s heartbeat frames:
            // the connection is dead. The turn survives a disconnect
            // server-side, so enter recovery instead of giving up.
            console.error('Stream inactivity timeout (90s) — entering recovery');
            recover();
        }, 90000);
    }

    function recover() {
        // The stream ended without a terminal done/error event: the
        // CONNECTION died, not the turn. The server finishes a disconnected
        // turn in the background and persists the answer — poll turn-status
        // until it lands, then reload messages.
        if (finished || recovering) return;
        recovering = true;
        if (inactivityTimer) clearTimeout(inactivityTimer);
        // Stop consuming the dead stream (no-op if it already hit EOF).
        if (abortController) abortController.abort();
        if (currentStreamContent) {
            currentStreamContent.innerHTML = '<span class="text-amber-400 flex items-center gap-2">'
                + SPINNER_SVG
                + 'Connection interrupted — the assistant is still working…</span>';
        }
        recoverDeadline = Date.now() + RECOVERY_BUDGET_MS;
        pollTurnStatus();
    }

    function pollTurnStatus() {
        if (finished) return;
        fetch(config.turnStatusUrl)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (finished) return;
                if (data.state === 'completed') {
                    if (data.confirm_required) pendingQuickReply = true;
                    recovering = false;
                    finish();  // onFinish reloads messages — the answer is saved
                    return;
                }
                if (data.state === 'running') {
                    if (Date.now() > recoverDeadline) {
                        recoveryFailed('The connection was lost and the assistant did not finish in time. Please resend your message.', false);
                        return;
                    }
                    recoverTimer = setTimeout(pollTurnStatus, RECOVERY_POLL_MS);
                    return;
                }
                if (data.state === 'failed') {
                    // The server persisted a specific error message — reload
                    // so it becomes visible.
                    recoveryFailed('The assistant hit an error while finishing. Loading details…', true);
                    return;
                }
                // abandoned / stale / none — the turn will not finish.
                recoveryFailed('The connection was lost and the assistant could not finish. Please resend your message.', false);
            })
            .catch(function() {
                // Network still down — keep trying until the deadline.
                if (finished) return;
                if (Date.now() > recoverDeadline) {
                    recoveryFailed('The connection was lost and the assistant could not finish. Please resend your message.', false);
                    return;
                }
                recoverTimer = setTimeout(pollTurnStatus, RECOVERY_POLL_MS);
            });
    }

    function recoveryFailed(message, reload) {
        recovering = false;
        endedWithError = true;
        // endedWithTimeout doubles as "reload anyway" in finish(): true when
        // the server persisted something worth showing (failed turns save an
        // error message); false keeps the resend instruction visible.
        endedWithTimeout = !!reload;
        if (currentStreamContent) {
            currentStreamContent.innerHTML = '<span class="text-red-400">' + escapeHtml(message) + '</span>';
        }
        finish();
    }

    function handleEvent(event, data) {
        if (event === 'tool_start') {
            var label = data.name;
            if (data.summary) label += '(' + escapeHtml(data.summary) + ')';
            var toolEl = document.createElement('div');
            toolEl.className = 'flex items-start gap-2 text-xs text-gray-500 mb-1';
            toolEl.setAttribute('data-tool', data.name);
            toolEl.innerHTML = '<span class="inline-flex items-center gap-1 shrink-0">'
                + '<svg class="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">'
                + '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>'
                + '<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>'
                + '</svg>' + escapeHtml(label) + '</span>';
            if (currentStreamTools) currentStreamTools.appendChild(toolEl);
            autoScroll();
        } else if (event === 'tool_done') {
            if (!currentStreamTools) return;
            var toolEls = currentStreamTools.querySelectorAll('[data-tool]');
            for (var j = toolEls.length - 1; j >= 0; j--) {
                if (toolEls[j].getAttribute('data-tool') === data.name) {
                    var resultText = data.result_summary ? ' \u2014 ' + escapeHtml(data.result_summary) : '';
                    var detailHtml = '';
                    if (data.output) {
                        var outputStr = typeof data.output === 'string' ? data.output : JSON.stringify(data.output, null, 2);
                        detailHtml = '<details class="mt-0.5 ml-4"><summary class="cursor-pointer text-gray-600 hover:text-gray-400">details</summary>'
                            + '<pre class="mt-1 p-2 bg-gray-800 rounded text-xs text-gray-500 font-mono overflow-x-auto max-h-32 overflow-y-auto whitespace-pre-wrap">'
                            + escapeHtml(outputStr) + '</pre></details>';
                    }
                    toolEls[j].innerHTML = '<span class="inline-flex items-center gap-1 shrink-0">'
                        + '<svg class="w-3 h-3 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
                        + '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>'
                        + escapeHtml(data.name) + '</span>'
                        + '<span class="text-gray-600">' + resultText + '</span>'
                        + detailHtml;
                    break;
                }
            }
        } else if (event === 'clear') {
            collectedText = '';
            firstToken = true;
            if (currentStreamContent) {
                currentStreamContent.innerHTML = '<span class="text-gray-500 flex items-center gap-2">'
                    + '<svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">'
                    + '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>'
                    + '<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/>'
                    + '</svg>Thinking...</span>';
            }
        } else if (event === 'token') {
            if (firstToken && currentStreamContent) {
                currentStreamContent.innerHTML = '';
                firstToken = false;
            }
            collectedText += data.text;
            if (currentStreamContent) {
                currentStreamContent.innerHTML = renderMarkdown(collectedText);
            }
            autoScroll();
        } else if (event === 'title') {
            if (config.onTitle) config.onTitle(data.title);
        } else if (event === 'confirm_required') {
            pendingQuickReply = true;
        } else if (event === 'thinking') {
            // Extended thinking keepalive — reset watchdog and show deep-thinking indicator
            resetWatchdog();
            if (currentStreamContent && firstToken) {
                currentStreamContent.innerHTML = '<span class="text-gray-500 flex items-center gap-2">'
                    + '<svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">'
                    + '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>'
                    + '<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/>'
                    + '</svg>Thinking deeply\u2026</span>';
            }
        } else if (event === 'done') {
            sawTerminal = true;
        } else if (event === 'error') {
            sawTerminal = true;
            endedWithError = true;
            if (currentStreamContent) {
                currentStreamContent.innerHTML = '<span class="text-red-400">' + escapeHtml(data.message) + '</span>';
            }
        }
    }

    // Pending quick-reply state: set during finish, injected after refresh
    var pendingQuickReply = false;

    function _injectQuickReplyButtons() {
        // Find the last assistant message bubble and append buttons after it
        var bubbles = config.messageListEl.querySelectorAll('.bg-gray-700');
        if (bubbles.length === 0) return;
        var lastBubble = bubbles[bubbles.length - 1];

        var btnContainer = document.createElement('div');
        btnContainer.className = 'flex gap-2 mt-2 quick-reply-buttons';
        btnContainer.innerHTML =
            '<button class="px-3 py-1 bg-green-600 hover:bg-green-500 text-white text-xs font-medium rounded-md transition-colors">Confirm</button>' +
            '<button class="px-3 py-1 bg-gray-600 hover:bg-gray-500 text-white text-xs font-medium rounded-md transition-colors">Deny</button>';
        lastBubble.parentNode.after(btnContainer);

        btnContainer.querySelectorAll('button').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var reply = btn.textContent.toLowerCase();
                config.inputEl.value = reply;
                config.inputEl.focus();
                document.querySelectorAll('.quick-reply-buttons').forEach(function(el) { el.remove(); });
                config.inputEl.form.dispatchEvent(new Event('submit'));
            });
        });
    }

    function finish() {
        // May be reached from the watchdog, the read() loop's done branch, its
        // catch, or the fetch catch — run the teardown only once per stream.
        if (finished) return;
        finished = true;
        if (inactivityTimer) clearTimeout(inactivityTimer);
        if (recoverTimer) clearTimeout(recoverTimer);
        recovering = false;
        streaming = false;
        config.sendBtnEl.disabled = false;
        config.sendBtnEl.textContent = 'Send';

        // pendingQuickReply is set by the confirm_required SSE event
        // (emitted by the backend after dry_run tool calls)

        currentStreamContent = null;
        currentStreamTools = null;
        // Delay onFinish slightly so the server saves the message before we refresh.
        // Reload on normal completion AND on watchdog timeout (to surface any
        // results the server already persisted). Skip only for a server-sent
        // error event, where the error message is preserved in the bubble.
        if (config.onFinish && (!endedWithError || endedWithTimeout)) {
            setTimeout(function() { config.onFinish(); }, 300);
        }
    }

    function doSend(text) {
        endedWithError = false;
        endedWithTimeout = false;
        finished = false;
        sawTerminal = false;
        recovering = false;
        if (recoverTimer) clearTimeout(recoverTimer);
        // Prepend page context if available
        var context = config.getPageContext ? config.getPageContext() : null;
        var fullText = text;
        if (context) {
            fullText = '[Context: ' + context + ']\n' + text;
        }

        // Display text strips context prefix
        var displayText = text;

        streaming = true;
        config.sendBtnEl.disabled = true;
        config.sendBtnEl.textContent = '...';

        // Remove any quick-reply buttons from previous messages
        document.querySelectorAll('.quick-reply-buttons').forEach(function(el) { el.remove(); });

        // Hide empty state
        if (config.emptyStateEl) config.emptyStateEl.style.display = 'none';

        // Add user message bubble
        var userBubble = document.createElement('div');
        userBubble.className = 'flex justify-end';
        userBubble.innerHTML = '<div class="max-w-[85%] sm:max-w-[70%]">'
            + '<div class="bg-blue-600/20 border border-blue-600/30 rounded-lg px-4 py-2">'
            + '<p class="text-sm text-gray-200 whitespace-pre-wrap">' + escapeHtml(displayText) + '</p>'
            + '</div></div>';
        config.messageListEl.appendChild(userBubble);

        // Add assistant bubble placeholder
        var assistantBubble = document.createElement('div');
        assistantBubble.innerHTML = '<div class="overflow-hidden">'
            + '<div class="engine-stream-tools text-xs text-gray-500 mb-1"></div>'
            + '<div class="bg-gray-700 rounded-lg px-4 py-2">'
            + '<div class="engine-stream-content prose-markdown text-sm text-gray-300 break-words"></div>'
            + '</div></div>';
        config.messageListEl.appendChild(assistantBubble);

        // Store direct refs (no IDs — safe for multiple engines)
        currentStreamContent = assistantBubble.querySelector('.engine-stream-content');
        currentStreamTools = assistantBubble.querySelector('.engine-stream-tools');
        currentStreamContent.innerHTML = '<span class="text-gray-500 flex items-center gap-2">'
            + '<svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">'
            + '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>'
            + '<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/>'
            + '</svg>Thinking...</span>';
        autoScroll();

        // Reset state for this stream
        collectedText = '';
        firstToken = true;

        // Start SSE stream
        var body = new FormData();
        body.append('message', fullText);
        body.append('mode', currentMode);
        var eff = config.getEffort ? config.getEffort(currentMode) : '';
        if (eff) body.append('effort', eff);
        resetWatchdog();

        abortController = new AbortController();
        fetch(config.streamUrl, {
            method: 'POST',
            headers: {'X-CSRFToken': config.csrfToken},
            body: body,
            signal: abortController.signal,
        }).then(function(resp) {
            var reader = resp.body.getReader();
            var decoder = new TextDecoder();
            var buffer = '';

            function read() {
                reader.read().then(function(result) {
                    if (result.done) {
                        // EOF without a terminal done/error event means the
                        // stream was SEVERED (proxy abort, network drop) —
                        // not a finished turn. Recover instead of silently
                        // treating it as success.
                        if (sawTerminal) { finish(); } else { recover(); }
                        return;
                    }
                    resetWatchdog();
                    buffer += decoder.decode(result.value, {stream: true});
                    var lines = buffer.split('\n');
                    buffer = lines.pop();

                    var currentEvent = '';
                    for (var i = 0; i < lines.length; i++) {
                        var line = lines[i];
                        if (line.startsWith('event: ')) {
                            currentEvent = line.substring(7);
                        } else if (line.startsWith('data: ')) {
                            var eventData = JSON.parse(line.substring(6));
                            handleEvent(currentEvent, eventData);
                            currentEvent = '';
                        }
                    }
                    read();
                }).catch(function(err) {
                    // AbortError = we intentionally tore down the stream
                    // (watchdog → recover()); recovery is already running.
                    if (err && err.name === 'AbortError') return;
                    console.error('Stream error:', err);
                    if (sawTerminal) { finish(); } else { recover(); }
                });
            }

            read();
        }).catch(function(err) {
            // AbortError = intentional teardown; recovery (or finish) already
            // handled the UI — don't tear down a recovery in progress.
            if (err && err.name === 'AbortError') { if (!recovering) finish(); return; }
            if (currentStreamContent) {
                currentStreamContent.innerHTML = '<span class="text-red-400">Connection error: ' + escapeHtml(err.message) + '</span>';
            }
            streaming = false;
            config.sendBtnEl.disabled = false;
            config.sendBtnEl.textContent = 'Send';
        });
    }

    function loadMessages() {
        return fetch(config.messagesUrl, {
            headers: {'HX-Request': 'true'}
        }).then(function(r) { return r.text(); })
        .then(function(html) {
            config.messageListEl.innerHTML = html;
            // Inject quick-reply buttons after refresh if pending
            if (pendingQuickReply) {
                pendingQuickReply = false;
                _injectQuickReplyButtons();
            }
            if (config.emptyStateEl) {
                config.emptyStateEl.style.display = config.messageListEl.innerHTML.trim() ? 'none' : '';
            }
            autoScroll();
        });
    }

    function refreshMessages() {
        return loadMessages();
    }

    return {
        doSend: doSend,
        loadMessages: loadMessages,
        refreshMessages: refreshMessages,
        autoScroll: autoScroll,
        isStreaming: function() { return streaming; },
        setMode: function(m) { currentMode = m; },
        getMode: function() { return currentMode; },
    };
}
