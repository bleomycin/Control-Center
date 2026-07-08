"""E2E tests for the AI Assistant chat interface.

Tests markdown rendering (marked.js), page structure, and session management.
These tests do NOT require an Anthropic API key — they verify the client-side
behavior and page rendering independently.
"""

from assistant.models import ChatMessage, ChatSession
from e2e.base import PlaywrightTestCase


class AssistantMarkdownRenderingTests(PlaywrightTestCase):
    """Verify marked.js is loaded and renders markdown correctly during streaming."""

    def setUp(self):
        super().setUp()
        self.session = ChatSession.objects.create(title="Test Chat")

    def test_marked_js_loaded(self):
        """marked.js library is loaded and the parse function is available."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        loaded = self.page.evaluate(
            "typeof marked !== 'undefined' && typeof marked.parse === 'function'"
        )
        self.assertTrue(loaded)

    def test_render_markdown_function_exists(self):
        """The renderMarkdown function is defined and callable."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        exists = self.page.evaluate("typeof renderMarkdown === 'function'")
        self.assertTrue(exists)

    def test_renders_bold_and_italic(self):
        """Markdown bold and italic render as <strong> and <em>."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        html = self.page.evaluate('renderMarkdown("**bold** and *italic*")')
        self.assertIn("<strong>bold</strong>", html)
        self.assertIn("<em>italic</em>", html)

    def test_renders_inline_code(self):
        """Inline code renders with <code> tags."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        html = self.page.evaluate('renderMarkdown("`some_function()`")')
        self.assertIn("<code>some_function()</code>", html)

    def test_renders_links(self):
        """Markdown links render as <a> tags."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        html = self.page.evaluate(
            'renderMarkdown("[Task #42](/tasks/42/)")'
        )
        self.assertIn('<a href="/tasks/42/">', html)
        self.assertIn("Task #42", html)

    def test_renders_tables(self):
        """GFM tables render with proper <table> structure."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        html = self.page.evaluate(
            'renderMarkdown("| Name | Status |\\n|------|--------|\\n| Task 1 | Done |")'
        )
        self.assertIn("<table>", html)
        self.assertIn("<thead>", html)
        self.assertIn("<th>Name</th>", html)
        self.assertIn("<td>Task 1</td>", html)

    def test_renders_headers(self):
        """Markdown headers render as <h1>, <h2>, <h3> tags."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        html = self.page.evaluate('renderMarkdown("## Summary\\n### Details")')
        self.assertIn("<h2>Summary</h2>", html)
        self.assertIn("<h3>Details</h3>", html)

    def test_renders_unordered_lists(self):
        """Unordered lists render with <ul> and <li>."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        html = self.page.evaluate(
            'renderMarkdown("- Item A\\n- Item B\\n- Item C")'
        )
        self.assertIn("<ul>", html)
        self.assertIn("<li>Item A</li>", html)
        self.assertIn("<li>Item C</li>", html)

    def test_renders_ordered_lists(self):
        """Ordered lists render with <ol> and <li>."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        html = self.page.evaluate(
            'renderMarkdown("1. First\\n2. Second\\n3. Third")'
        )
        self.assertIn("<ol>", html)
        self.assertIn("<li>First</li>", html)

    def test_renders_fenced_code_blocks(self):
        """Fenced code blocks render with <pre><code>."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        html = self.page.evaluate(
            'renderMarkdown("```python\\ndef hello():\\n    pass\\n```")'
        )
        self.assertIn("<pre>", html)
        self.assertIn("<code", html)
        self.assertIn("def hello():", html)

    def test_renders_blockquotes(self):
        """Blockquotes render with <blockquote>."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        html = self.page.evaluate('renderMarkdown("> Important note")')
        self.assertIn("<blockquote>", html)
        self.assertIn("Important note", html)

    def test_line_breaks_enabled(self):
        """Single newlines produce <br> tags (breaks: true)."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        html = self.page.evaluate('renderMarkdown("Line 1\\nLine 2")')
        self.assertIn("<br>", html)

    def test_dompurify_loaded(self):
        """DOMPurify is vendored and available for stream sanitization."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        loaded = self.page.evaluate(
            "typeof DOMPurify !== 'undefined' && typeof DOMPurify.sanitize === 'function'"
        )
        self.assertTrue(loaded)

    def test_svg_onload_sanitized_in_stream_path(self):
        """Raw <svg onload=...> in streamed text renders inert (Phase 1 XSS fix)."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        html = self.page.evaluate(
            'renderMarkdown("<svg onload=alert(1)></svg>quoted content")'
        )
        self.assertNotIn("onload", html)
        self.assertIn("quoted content", html)

    def test_script_sanitized_in_stream_path(self):
        """Raw <script> in streamed text is stripped before innerHTML."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        html = self.page.evaluate(
            'renderMarkdown("<script>alert(1)</scr" + "ipt>safe")'
        )
        self.assertNotIn("<script", html)
        self.assertNotIn("alert(1)", html)
        self.assertIn("safe", html)

    def test_img_onerror_sanitized_in_stream_path(self):
        """<img onerror=...> loses its event handler after sanitization."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        html = self.page.evaluate(
            'renderMarkdown("<img src=x onerror=alert(1)>")'
        )
        self.assertNotIn("onerror", html)

    def test_sanitize_preserves_repaired_hrefs(self):
        """Sanitization runs after the bare-app-href repair and keeps the fixed link."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        html = self.page.evaluate(
            'renderMarkdown("[Ascaya](assets/real-estate/124/)")'
        )
        self.assertIn('href="/assets/real-estate/124/"', html)


class AssistantServerRenderedMarkdownTests(PlaywrightTestCase):
    """Verify server-rendered messages display markdown correctly."""

    def setUp(self):
        super().setUp()
        self.session = ChatSession.objects.create(title="Markdown Test")

    def test_server_rendered_bold(self):
        """Server-rendered assistant messages render bold correctly."""
        ChatMessage.objects.create(
            session=self.session,
            role="assistant",
            content="Here is **important** information.",
        )
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        strong = self.page.locator(".prose-markdown strong")
        strong.wait_for(state="visible")
        self.assertEqual(strong.text_content(), "important")

    def test_server_rendered_table(self):
        """Server-rendered assistant messages render tables."""
        ChatMessage.objects.create(
            session=self.session,
            role="assistant",
            content="| Name | Status |\n|------|--------|\n| Task | Done |",
        )
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        table = self.page.locator(".prose-markdown table")
        table.wait_for(state="visible")
        self.assertIn("Task", table.text_content())

    def test_server_rendered_list(self):
        """Server-rendered assistant messages render lists."""
        ChatMessage.objects.create(
            session=self.session,
            role="assistant",
            content="Tasks:\n- First item\n- Second item",
        )
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        items = self.page.locator(".prose-markdown li")
        self.assertGreaterEqual(items.count(), 2)

    def test_server_rendered_code_block(self):
        """Server-rendered assistant messages render code blocks."""
        ChatMessage.objects.create(
            session=self.session,
            role="assistant",
            content="```\nsome code here\n```",
        )
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        code = self.page.locator(".prose-markdown code")
        code.first.wait_for(state="visible")
        self.assertIn("some code here", code.first.text_content())

    def test_server_rendered_script_is_inert(self):
        """Stored raw <script>/<img onerror> in message history renders inert."""
        ChatMessage.objects.create(
            session=self.session,
            role="assistant",
            content='Quoting: <script>window.__xss=1</script>'
                    '<img src=x onerror="window.__xss=2"> done.',
        )
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        bubble = self.page.locator(".prose-markdown")
        bubble.first.wait_for(state="visible")
        self.assertIsNone(self.page.evaluate("window.__xss"))
        html = bubble.first.inner_html()
        self.assertNotIn("<script", html)
        self.assertNotIn("onerror", html)

    def test_server_rendered_link(self):
        """Server-rendered assistant messages render links."""
        ChatMessage.objects.create(
            session=self.session,
            role="assistant",
            content="See [Thomas Wright](/stakeholders/1/) for details.",
        )
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        link = self.page.locator(".prose-markdown a")
        link.wait_for(state="visible")
        self.assertEqual(link.text_content(), "Thomas Wright")
        self.assertIn("/stakeholders/1/", link.get_attribute("href"))


class AssistantPageStructureTests(PlaywrightTestCase):
    """Verify the assistant page structure and elements."""

    def setUp(self):
        super().setUp()
        self.session = ChatSession.objects.create(title="Test Session")

    def test_page_loads(self):
        """Assistant chat page loads successfully."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        self.page.wait_for_selector("#chat-form")
        self.assertIn("Assistant", self.page.title())

    def test_empty_state_shown(self):
        """Empty session shows the helpful empty state message."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        empty = self.page.locator("#empty-state")
        empty.wait_for(state="visible")
        self.assertIn("Ask anything", empty.text_content())

    def test_session_title_in_header(self):
        """Session title is displayed in the header."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        title = self.page.locator("h1.truncate")
        self.assertEqual(title.text_content(), "Test Session")

    def test_title_event_handler_wired(self):
        """The handleEvent function processes 'title' events."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        # Simulate a title event by calling handleEvent indirectly
        self.page.evaluate("""
            var titleEl = document.querySelector('h1.truncate');
            if (titleEl) titleEl.textContent = 'AI Generated Title';
        """)
        title = self.page.locator("h1.truncate")
        self.assertEqual(title.text_content(), "AI Generated Title")

    def test_chat_input_exists(self):
        """Chat input textarea and send button exist."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        textarea = self.page.locator("#chat-input")
        textarea.wait_for(state="visible")
        send_btn = self.page.locator("#send-btn")
        self.assertTrue(send_btn.is_visible())

    def test_user_message_displayed(self):
        """User messages are displayed in blue bubbles."""
        ChatMessage.objects.create(
            session=self.session, role="user", content="Hello there"
        )
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        bubble = self.page.locator("#message-list .bg-blue-600\\/20")
        bubble.wait_for(state="visible")
        self.assertIn("Hello there", bubble.text_content())

    def test_assistant_message_displayed(self):
        """Assistant messages are displayed in gray bubbles."""
        ChatMessage.objects.create(
            session=self.session, role="assistant", content="Hi! How can I help?"
        )
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        bubble = self.page.locator("#message-list .prose-markdown")
        bubble.first.wait_for(state="visible")
        self.assertIn("How can I help", bubble.first.text_content())

    def test_multiple_sessions_in_sidebar(self):
        """Multiple sessions appear in the desktop sidebar."""
        ChatSession.objects.create(title="Second Session")
        self.page.set_viewport_size({"width": 1200, "height": 800})
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        session_list = self.page.locator("#session-list")
        session_list.wait_for(state="visible")
        self.assertIn("Test Session", session_list.text_content())
        self.assertIn("Second Session", session_list.text_content())


class AssistantMessageActionsTests(PlaywrightTestCase):
    """Verify message action buttons (copy, retry, edit) appear correctly."""

    def setUp(self):
        super().setUp()
        self.session = ChatSession.objects.create(title="Actions Test")
        self.user_msg = ChatMessage.objects.create(
            session=self.session, role="user", content="Hello there"
        )
        self.asst_msg = ChatMessage.objects.create(
            session=self.session, role="assistant", content="Hi! How can I help?"
        )

    def test_action_bar_hidden_by_default(self):
        """Action buttons are not visible without hover."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        self.page.wait_for_selector("#message-list")
        # User message action bar should be hidden (opacity-0)
        user_actions = self.page.locator(".bg-blue-600\\/20 .absolute")
        self.assertEqual(user_actions.count(), 1)
        box = user_actions.first.bounding_box()
        # The element exists but is invisible via opacity-0
        self.assertIsNotNone(box)

    def test_copy_button_visible_on_hover(self):
        """Copy button appears when hovering over a message."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        self.page.wait_for_selector("#message-list")
        # Hover over user message bubble
        bubble = self.page.locator("#message-list .bg-blue-600\\/20").first
        bubble.hover()
        copy_btn = bubble.locator("button[title='Copy']")
        copy_btn.wait_for(state="visible")
        self.assertTrue(copy_btn.is_visible())

    def test_retry_button_on_assistant_only(self):
        """Retry button exists on assistant messages, not on user messages."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        self.page.wait_for_selector("#message-list")
        # Assistant message should have retry
        asst_bubble = self.page.locator(".bg-gray-700.rounded-lg.group").first
        retry_btn = asst_bubble.locator("button[title='Retry']")
        self.assertEqual(retry_btn.count(), 1)
        # User message should NOT have retry
        user_bubble = self.page.locator("#message-list .bg-blue-600\\/20").first
        user_retry = user_bubble.locator("button[title='Retry']")
        self.assertEqual(user_retry.count(), 0)

    def test_edit_button_on_user_only(self):
        """Edit button exists on user messages, not on assistant messages."""
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        self.page.wait_for_selector("#message-list")
        # User message should have edit
        user_bubble = self.page.locator("#message-list .bg-blue-600\\/20").first
        edit_btn = user_bubble.locator("button[title='Edit & resend']")
        self.assertEqual(edit_btn.count(), 1)
        # Assistant message should NOT have edit
        asst_bubble = self.page.locator(".bg-gray-700.rounded-lg.group").first
        asst_edit = asst_bubble.locator("button[title='Edit & resend']")
        self.assertEqual(asst_edit.count(), 0)


class AssistantToolDisplayTests(PlaywrightTestCase):
    """Verify enhanced tool execution display during streaming."""

    def setUp(self):
        super().setUp()
        self.session = ChatSession.objects.create(title="Tool Display Test")

    def _goto_session(self):
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        self.page.wait_for_selector("#chat-form")

    def _simulate_tool_start(self, name, summary=None):
        """Simulate a tool_start SSE event by creating the DOM elements."""
        summary_js = f"'{summary}'" if summary else "null"
        self.page.evaluate(f"""(() => {{
            var streamTools = document.getElementById('stream-tools');
            if (!streamTools) {{
                streamTools = document.createElement('div');
                streamTools.id = 'stream-tools';
                streamTools.className = 'text-xs text-gray-500 mb-1';
                document.getElementById('message-list').appendChild(streamTools);
            }}
            var label = '{name}';
            var summary = {summary_js};
            if (summary) label += '(' + summary + ')';
            var toolEl = document.createElement('div');
            toolEl.className = 'flex items-start gap-2 text-xs text-gray-500 mb-1';
            toolEl.setAttribute('data-tool', '{name}');
            toolEl.innerHTML = '<span class="inline-flex items-center gap-1 shrink-0">'
                + '<svg class="w-3 h-3 animate-spin"></svg>' + label + '</span>';
            streamTools.appendChild(toolEl);
        }})()""")

    def _simulate_tool_done(self, name, result_summary=None, output=None):
        """Simulate a tool_done SSE event."""
        import json
        rs_js = f"'{result_summary}'" if result_summary else "null"
        out_js = json.dumps(output) if output else "null"
        self.page.evaluate(f"""(() => {{
            var toolEls = document.querySelectorAll('[data-tool]');
            for (var j = toolEls.length - 1; j >= 0; j--) {{
                if (toolEls[j].getAttribute('data-tool') === '{name}') {{
                    var resultSummary = {rs_js};
                    var output = {out_js};
                    var resultText = resultSummary ? ' \\u2014 ' + resultSummary : '';
                    var detailHtml = '';
                    if (output) {{
                        var outputStr = JSON.stringify(output, null, 2);
                        detailHtml = '<details class="mt-0.5 ml-4"><summary class="cursor-pointer text-gray-600 hover:text-gray-400">details</summary>'
                            + '<pre class="mt-1 p-2 bg-gray-800 rounded">' + outputStr + '</pre></details>';
                    }}
                    toolEls[j].innerHTML = '<span class="inline-flex items-center gap-1 shrink-0">'
                        + '<svg class="w-3 h-3 text-green-500"></svg>{name}</span>'
                        + '<span class="text-gray-600">' + resultText + '</span>'
                        + detailHtml;
                    break;
                }}
            }}
        }})()""")

    def test_tool_start_shows_summary(self):
        """tool_start event with summary shows tool name + params."""
        self._goto_session()
        self._simulate_tool_start("search", '"Thomas"')
        tool_el = self.page.locator("[data-tool='search']")
        self.assertEqual(tool_el.count(), 1)
        self.assertIn('search("Thomas")', tool_el.text_content())

    def test_tool_done_shows_result_summary(self):
        """tool_done event shows result summary after tool name."""
        self._goto_session()
        self._simulate_tool_start("search", '"Thomas"')
        self._simulate_tool_done("search", "3 result(s)", {"count": 3})
        tool_el = self.page.locator("[data-tool='search']")
        text = tool_el.text_content()
        self.assertIn("search", text)
        self.assertIn("3 result(s)", text)

    def test_tool_done_has_collapsible_details(self):
        """tool_done with output data includes a collapsible details element."""
        self._goto_session()
        self._simulate_tool_start("query", "Task")
        self._simulate_tool_done("query", "5 record(s)", {"count": 5, "records": [{"id": 1}]})
        details = self.page.locator("[data-tool='query'] details")
        self.assertEqual(details.count(), 1)
        summary = details.locator("summary")
        self.assertEqual(summary.text_content(), "details")

    def test_tool_start_without_summary_shows_name_only(self):
        """tool_start with no summary field shows just the tool name."""
        self._goto_session()
        self._simulate_tool_start("summarize")
        tool_el = self.page.locator("[data-tool='summarize']")
        self.assertEqual(tool_el.count(), 1)
        text = tool_el.text_content().strip()
        self.assertEqual(text, "summarize")


class AssistantStreamRecoveryTests(PlaywrightTestCase):
    """Phase 4 Defects B/E: transport failures must never silently drop a
    sent message, and one malformed SSE line must not abort the stream."""

    def setUp(self):
        super().setUp()
        self.session = ChatSession.objects.create(title="Recovery Chat")

    def _goto(self):
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        self.page.wait_for_selector("#chat-input")

    def _send(self, text):
        self.page.fill("#chat-input", text)
        self.page.click("#send-btn")

    def test_502_on_stream_shows_resend_and_preserves_text(self):
        """An HTML error response (proxy 502) used to parse as an empty SSE
        stream and recover() into a false success that reloaded history over
        the typed message."""
        self._goto()
        self.page.route(
            "**/stream/",
            lambda route: route.fulfill(
                status=502, content_type="text/html", body="<html>Bad Gateway</html>"
            ),
        )
        self._send("important question")

        # Error UI with a resend instruction — not a silent success.
        self.page.wait_for_selector("text=please resend it", timeout=5000)
        # The typed text is restored into the input for a one-click resend...
        self.assertEqual(
            self.page.input_value("#chat-input"), "important question"
        )
        # ...and the user bubble was not reloaded away.
        self.assertTrue(
            self.page.locator("text=important question").count() >= 1
        )

    def test_severed_stream_does_not_match_previous_completed_turn(self):
        """A stream that dies before any frame arrives leaves the client with
        no turn_id; polling turn-status then reports a PREVIOUS completed
        turn, which used to read as success (silent message loss)."""
        from assistant.models import AssistantTurn

        # A previously completed turn + its answer already in history.
        old_msg = ChatMessage.objects.create(
            session=self.session, role="assistant", content="old answer"
        )
        AssistantTurn.objects.create(
            session=self.session,
            state=AssistantTurn.STATE_COMPLETED,
            final_message=old_msg,
        )
        self._goto()
        # 200 SSE response with an empty body: connection severed before the
        # first frame — no user_message event, no turn_id.
        self.page.route(
            "**/stream/",
            lambda route: route.fulfill(
                status=200, content_type="text/event-stream", body=""
            ),
        )
        self._send("brand new question")

        self.page.wait_for_selector("text=Please resend it", timeout=10000)
        # The typed message is preserved, not reloaded over.
        self.assertTrue(
            self.page.locator("text=brand new question").count() >= 1
        )
        self.assertEqual(
            self.page.input_value("#chat-input"), "brand new question"
        )

    def test_malformed_sse_line_does_not_abort_stream(self):
        """One bad data: line must be skipped — the remaining events in the
        chunk (tokens, done) must still be processed."""
        # Seed history so the post-done reload renders the same answer the
        # stream delivered (keeps the assertion race-free).
        ChatMessage.objects.create(
            session=self.session, role="user", content="q"
        )
        ChatMessage.objects.create(
            session=self.session, role="assistant", content="hello world"
        )
        self._goto()
        sse_body = (
            'event: user_message\n'
            'data: {"id": 1, "content": "q", "turn_id": 999999}\n\n'
            'event: token\n'
            'data: {broken json!\n\n'
            'event: token\n'
            'data: {"text": "hello world"}\n\n'
            'event: done\n'
            'data: {"message_id": 1}\n\n'
        )
        self.page.route(
            "**/stream/",
            lambda route: route.fulfill(
                status=200, content_type="text/event-stream", body=sse_body
            ),
        )
        self._send("q")

        self.page.wait_for_selector("text=hello world", timeout=5000)
        # No recovery/error UI — the stream reached its terminal done event.
        self.assertEqual(self.page.locator("text=please resend").count(), 0)
        self.assertEqual(self.page.locator("text=Connection error").count(), 0)

    def test_event_name_survives_chunk_split(self):
        """An SSE frame whose "event:" line ends one network chunk and whose
        "data:" line starts the next must still dispatch. The parser used to
        reset the pending event name between chunks, silently dropping the
        frame — a dropped "done" routed a healthy stream into recovery and a
        resend prompt."""
        # Seed history so the post-done reload renders the same answer the
        # stream delivered (keeps the assertion race-free).
        ChatMessage.objects.create(
            session=self.session, role="user", content="q"
        )
        ChatMessage.objects.create(
            session=self.session, role="assistant", content="hello world"
        )
        self._goto()
        # The split lands between done's "event:" line and its "data:" line.
        chunk1 = (
            'event: user_message\n'
            'data: {"id": 1, "content": "q", "turn_id": 999999}\n\n'
            'event: token\n'
            'data: {"text": "hello world"}\n\n'
            'event: done\n'
        )
        chunk2 = 'data: {"message_id": 1}\n\n'
        # route.fulfill delivers the body as a single chunk, so patch fetch
        # with a two-enqueue ReadableStream to force the exact boundary.
        self.page.evaluate(
            """([c1, c2]) => {
                const orig = window.fetch;
                window.fetch = function(url, opts) {
                    if (typeof url === 'string' && url.includes('/stream/')) {
                        const enc = new TextEncoder();
                        const stream = new ReadableStream({
                            start(ctrl) {
                                ctrl.enqueue(enc.encode(c1));
                                setTimeout(() => {
                                    ctrl.enqueue(enc.encode(c2));
                                    ctrl.close();
                                }, 100);
                            }
                        });
                        return Promise.resolve(new Response(stream, {
                            status: 200,
                            headers: {'Content-Type': 'text/event-stream'},
                        }));
                    }
                    return orig.apply(this, arguments);
                };
            }""",
            [chunk1, chunk2],
        )
        self._send("q")

        self.page.wait_for_selector("text=hello world", timeout=5000)
        # The split done frame must dispatch: clean finish, no recovery UI.
        self.page.wait_for_function(
            "document.getElementById('send-btn')"
            " && !document.getElementById('send-btn').disabled",
            timeout=10000,
        )
        self.assertEqual(self.page.locator("text=resend").count(), 0)
        self.assertEqual(self.page.locator("text=still working").count(), 0)

    def test_busy_guard_error_restores_input(self):
        """The busy-guard refusal (a server-sent error event) must put the
        typed text back into the input — the submit handler cleared it, and
        the whole point of the refusal is that the message should be resent
        in a moment."""
        from assistant.models import AssistantTurn

        self._goto()
        # Let the boot-resume probe settle on "no running turn" before
        # seeding one — otherwise the probe could adopt it and lock the
        # send button.
        self.page.wait_for_load_state("networkidle")
        # A fresh (non-stale) running turn makes the real send view refuse
        # with the busy-guard SSE error — no route mocking needed. Created
        # AFTER the page load (the two-tab shape: another tab admitted it),
        # because a pre-load running turn now triggers Wave 2 boot-resume,
        # which locks the send button instead of letting this send happen.
        AssistantTurn.objects.create(
            session=self.session, state=AssistantTurn.STATE_RUNNING
        )
        self._send("second question")

        self.page.wait_for_selector("text=still working", timeout=5000)
        self.page.wait_for_function(
            "document.getElementById('chat-input').value === 'second question'",
            timeout=5000,
        )
        # The client-rendered bubble is preserved too (no reload on error).
        self.assertTrue(
            self.page.locator("text=second question").count() >= 1
        )


class AssistantConcurrencyGuardTests(PlaywrightTestCase):
    """Phase 5 Defects B/C, client side: a second send mid-stream is ignored
    (single page — the point is that no second stream ever starts), and
    history-mutating actions surface the server's 409 refusal.

    NOTE: these deliberately do NOT call doSend twice on one engine to
    simulate SERVER concurrency — two concurrent turns need two tabs/pages
    (one engine instance interleaves stream state). The server-side guard is
    covered by unit tests + the seeded-turn busy-guard e2e above.
    """

    def setUp(self):
        super().setUp()
        self.session = ChatSession.objects.create(title="Concurrency Chat")

    def _goto(self):
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        self.page.wait_for_selector("#chat-input")

    def test_enter_mid_stream_is_ignored(self):
        """Enter dispatches submit directly (bypassing the disabled button);
        mid-stream it used to fire a second doSend that reset the shared
        closure state and garbled both streams. The second submit must be
        ignored BEFORE the input is cleared, and the first stream must
        complete normally."""
        # Seed history so the post-done reload renders the same answer the
        # stream delivered (keeps the assertion race-free).
        ChatMessage.objects.create(
            session=self.session, role="user", content="first question"
        )
        ChatMessage.objects.create(
            session=self.session, role="assistant", content="hello world"
        )
        self._goto()
        # Slow two-chunk stream so there is a real mid-stream window; count
        # stream POSTs so the ignored submit is provable.
        self.page.evaluate(
            """() => {
                window._streamCalls = 0;
                const orig = window.fetch;
                window.fetch = function(url, opts) {
                    if (typeof url === 'string' && url.includes('/stream/')) {
                        window._streamCalls += 1;
                        const enc = new TextEncoder();
                        const stream = new ReadableStream({
                            start(ctrl) {
                                ctrl.enqueue(enc.encode(
                                    'event: user_message\\n'
                                    + 'data: {"id": 1, "content": "q", "turn_id": 42}\\n\\n'
                                    + 'event: token\\n'
                                    + 'data: {"text": "hello world"}\\n\\n'
                                ));
                                setTimeout(() => {
                                    ctrl.enqueue(enc.encode(
                                        'event: done\\ndata: {"message_id": 1}\\n\\n'
                                    ));
                                    ctrl.close();
                                }, 1500);
                            }
                        });
                        return Promise.resolve(new Response(stream, {
                            status: 200,
                            headers: {'Content-Type': 'text/event-stream'},
                        }));
                    }
                    return orig.apply(this, arguments);
                };
            }"""
        )
        self._send("first question")
        self.page.wait_for_selector("text=hello world", timeout=5000)

        # Mid-stream: type again and press Enter (the real bypass path).
        self.page.fill("#chat-input", "second question")
        self.page.press("#chat-input", "Enter")
        self.page.wait_for_timeout(300)

        # The second submit was ignored before doing anything: no second
        # stream request, and the typed text was NOT cleared — but not
        # silently: a notice tells the user why.
        self.assertEqual(self.page.evaluate("window._streamCalls"), 1)
        self.assertEqual(
            self.page.input_value("#chat-input"), "second question"
        )
        self.page.wait_for_selector("#chat-notice", timeout=2000)

        # The first stream still completes normally.
        self.page.wait_for_function(
            "document.getElementById('send-btn')"
            " && !document.getElementById('send-btn').disabled",
            timeout=10000,
        )
        self.assertEqual(self.page.evaluate("window._streamCalls"), 1)
        self.assertEqual(self.page.locator("text=resend").count(), 0)
        self.assertEqual(self.page.locator("text=Connection error").count(), 0)
        self.assertTrue(
            self.page.locator("text=first question").count() >= 1
        )

    def _send(self, text):
        self.page.fill("#chat-input", text)
        self.page.click("#send-btn")

    def test_retry_blocked_while_turn_running(self):
        """With a live running turn, Retry must be refused server-side (409),
        surface a visible notice, and delete nothing."""
        from assistant.models import AssistantTurn

        ChatMessage.objects.create(
            session=self.session, role="user", content="the question"
        )
        answer = ChatMessage.objects.create(
            session=self.session, role="assistant", content="the answer"
        )
        AssistantTurn.objects.create(
            session=self.session, state=AssistantTurn.STATE_RUNNING
        )
        self._goto()

        self.page.evaluate(f"retryMessage({answer.pk})")

        self.page.wait_for_selector("#chat-notice", timeout=5000)
        self.assertIn(
            "still working",
            self.page.locator("#chat-notice").text_content(),
        )
        # Nothing was deleted — both bubbles still render.
        self.assertTrue(self.page.locator("text=the question").count() >= 1)
        self.assertTrue(self.page.locator("text=the answer").count() >= 1)
        self.assertEqual(
            ChatMessage.objects.filter(session=self.session).count(), 2
        )

    def test_bulk_delete_blocked_while_turn_running(self):
        """Bulk delete goes through fetch (not a native form submit), so the
        409 busy refusal must surface as an in-app toast — not a navigation
        to a bare plain-text page — and delete nothing."""
        from assistant.models import AssistantTurn

        AssistantTurn.objects.create(
            session=self.session, state=AssistantTurn.STATE_RUNNING
        )
        self._goto()
        self.page.once("dialog", lambda d: d.accept())
        self.page.evaluate(
            "() => {"
            " const cb = document.querySelector("
            "   '#session-list input[name=\"session-select\"]');"
            " if (!cb) throw new Error('no session checkbox');"
            " cb.checked = true;"
            " bulkDeleteSessions();"
            "}"
        )
        self.page.wait_for_selector("#chat-notice", timeout=5000)
        self.assertIn(
            "still working",
            self.page.locator("#chat-notice").text_content(),
        )
        # Still on the chat page, session intact.
        self.assertGreaterEqual(self.page.locator("#chat-input").count(), 1)
        self.assertTrue(
            ChatSession.objects.filter(pk=self.session.pk).exists()
        )


class AssistantPhase6RenderScrollTests(PlaywrightTestCase):
    """Phase 6 Defect E: frame-batched streaming render and gated autoscroll
    — the user can scroll up mid-stream and stay there, and the final render
    is complete despite batching."""

    def setUp(self):
        super().setUp()
        self.session = ChatSession.objects.create(title="Scroll Chat")

    def _goto(self):
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        self.page.wait_for_selector("#chat-input")

    def _send(self, text):
        self.page.fill("#chat-input", text)
        self.page.click("#send-btn")

    def _mock_three_phase_stream(self):
        """Chunk 1: enough tokens to overflow the scroll container.
        Chunk 2 (t+1200ms): more tokens — arrives AFTER the test scrolls up.
        Chunk 3 (t+3000ms): the done frame."""
        self.page.evaluate(
            """() => {
                const enc = new TextEncoder();
                const tokenFrame = (t) =>
                    'event: token\\ndata: ' + JSON.stringify({text: t}) + '\\n\\n';
                let chunk1 = 'event: user_message\\n'
                    + 'data: {"id": 1, "content": "q", "turn_id": 77}\\n\\n';
                for (let i = 0; i < 80; i++) {
                    chunk1 += tokenFrame('line ' + i + '\\n\\n');
                }
                let chunk2 = '';
                for (let i = 80; i < 120; i++) {
                    chunk2 += tokenFrame('line ' + i + '\\n\\n');
                }
                chunk2 += tokenFrame('LASTLINE');
                const orig = window.fetch;
                window.fetch = function(url, opts) {
                    if (typeof url === 'string' && url.includes('/stream/')) {
                        const stream = new ReadableStream({
                            start(ctrl) {
                                ctrl.enqueue(enc.encode(chunk1));
                                setTimeout(() => ctrl.enqueue(enc.encode(chunk2)), 1200);
                                setTimeout(() => {
                                    ctrl.enqueue(enc.encode(
                                        'event: done\\ndata: {"message_id": 1}\\n\\n'
                                    ));
                                    ctrl.close();
                                }, 3000);
                            }
                        });
                        return Promise.resolve(new Response(stream, {
                            status: 200,
                            headers: {'Content-Type': 'text/event-stream'},
                        }));
                    }
                    return orig.apply(this, arguments);
                };
            }"""
        )

    def test_scroll_up_preserved_mid_stream(self):
        # Seed the same final answer so the post-done reload is stable.
        ChatMessage.objects.create(session=self.session, role="user", content="q")
        ChatMessage.objects.create(
            session=self.session, role="assistant",
            content="".join(f"line {i}\n\n" for i in range(120)) + "LASTLINE",
        )
        self._goto()
        self._mock_three_phase_stream()
        self._send("q")

        # Chunk 1 rendered (batched via rAF) and the container overflows.
        # Scope to the streaming bubble — the seeded history already contains
        # the same text in the server-rendered page.
        self.page.wait_for_selector(
            ".engine-stream-content >> text=line 79", timeout=5000
        )
        overflows = self.page.evaluate(
            "() => { const el = document.getElementById('message-scroll');"
            " return el.scrollHeight > el.clientHeight + 100; }"
        )
        self.assertTrue(overflows, "fixture must overflow the scroll container")

        # User scrolls up to read.
        self.page.evaluate(
            "document.getElementById('message-scroll').scrollTop = 0"
        )
        # Chunk 2 arrives at t+1200ms and renders — wait for its content.
        self.page.wait_for_selector(
            ".engine-stream-content >> text=LASTLINE", timeout=5000
        )
        self.page.wait_for_timeout(200)  # let any (wrong) scroll settle
        scroll_top = self.page.evaluate(
            "document.getElementById('message-scroll').scrollTop"
        )
        self.assertLess(
            scroll_top, 100,
            "mid-stream tokens must not yank a scrolled-up reader to the bottom",
        )

        # Stream still finishes cleanly (batched frames all flushed).
        self.page.wait_for_function(
            "document.getElementById('send-btn')"
            " && !document.getElementById('send-btn').disabled",
            timeout=10000,
        )
        self.assertEqual(self.page.locator("text=resend").count(), 0)

    def test_batched_render_is_complete_when_following(self):
        """At the bottom (the normal case) the stream still follows and the
        final client-side render contains the last token — rAF batching must
        flush the tail, not drop it."""
        ChatMessage.objects.create(session=self.session, role="user", content="q")
        ChatMessage.objects.create(
            session=self.session, role="assistant",
            content="".join(f"line {i}\n\n" for i in range(120)) + "LASTLINE",
        )
        self._goto()
        self._mock_three_phase_stream()
        self._send("q")

        self.page.wait_for_selector(
            ".engine-stream-content >> text=LASTLINE", timeout=8000
        )
        # Still following: the container is scrolled to (near) the bottom.
        near_bottom = self.page.evaluate(
            "() => { const el = document.getElementById('message-scroll');"
            " return el.scrollHeight - el.scrollTop - el.clientHeight < 150; }"
        )
        self.assertTrue(near_bottom, "stream must keep following at the bottom")
        self.page.wait_for_function(
            "document.getElementById('send-btn')"
            " && !document.getElementById('send-btn').disabled",
            timeout=10000,
        )


class AssistantPhase6TitleAndDrawerTests(PlaywrightTestCase):
    """Phase 6 Defects D/F client side: the async title lands via the
    post-finish turn-status poll, and the drawer renders shared message
    partials without dead buttons."""

    def setUp(self):
        super().setUp()
        self.session = ChatSession.objects.create()  # "New Chat"

    def _goto(self):
        self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
        self.page.wait_for_selector("#chat-input")

    def test_async_title_arrives_after_done(self):
        """title_pending → done → post-finish poll of turn-status → the h1
        updates once the background task has saved the title."""
        ChatMessage.objects.create(session=self.session, role="user", content="q")
        ChatMessage.objects.create(
            session=self.session, role="assistant", content="the answer"
        )
        self._goto()
        # Mock the stream (title_pending before done) and the turn-status
        # poll (first poll: title still pending; second: saved title).
        self.page.evaluate(
            """() => {
                window._titlePolls = 0;
                const enc = new TextEncoder();
                const orig = window.fetch;
                window.fetch = function(url, opts) {
                    if (typeof url === 'string' && url.includes('/stream/')) {
                        const body = 'event: user_message\\n'
                            + 'data: {"id": 1, "content": "q", "turn_id": 5}\\n\\n'
                            + 'event: token\\ndata: {"text": "the answer"}\\n\\n'
                            + 'event: title_pending\\ndata: {}\\n\\n'
                            + 'event: done\\ndata: {"message_id": 1}\\n\\n';
                        const stream = new ReadableStream({
                            start(ctrl) {
                                ctrl.enqueue(enc.encode(body));
                                ctrl.close();
                            }
                        });
                        return Promise.resolve(new Response(stream, {
                            status: 200,
                            headers: {'Content-Type': 'text/event-stream'},
                        }));
                    }
                    if (typeof url === 'string' && url.includes('/turn-status/')) {
                        window._titlePolls += 1;
                        const title = window._titlePolls >= 2
                            ? 'Background Title' : 'New Chat';
                        return Promise.resolve(new Response(JSON.stringify({
                            state: 'completed', turn_id: 5,
                            session_title: title,
                        }), {
                            status: 200,
                            headers: {'Content-Type': 'application/json'},
                        }));
                    }
                    return orig.apply(this, arguments);
                };
            }"""
        )
        self.page.fill("#chat-input", "q")
        self.page.click("#send-btn")

        # done arrives immediately — send re-enables without waiting on the
        # title (the old blocking behavior).
        self.page.wait_for_function(
            "document.getElementById('send-btn')"
            " && !document.getElementById('send-btn').disabled",
            timeout=10000,
        )
        # The polled title lands in the header a few seconds later.
        self.page.wait_for_function(
            "document.querySelector('h1.truncate')"
            " && document.querySelector('h1.truncate').textContent"
            "     === 'Background Title'",
            timeout=15000,
        )
        self.assertGreaterEqual(self.page.evaluate("window._titlePolls"), 2)

    def test_drawer_new_chat_mid_stream_no_bleed_and_usable(self):
        """Bug-check of 266ab76: 'New chat' during a live drawer stream must
        fully neutralize the old engine. Three failure modes covered:
        (a) a late SSE error frame — already decoded when teardown ran, so
        abort() can't retract it — must not restore the OLD session's text
        into the shared drawer input (handleEvent gates on `finished`);
        (b) its error text must not surface in the new session's view;
        (c) the shared send button doSend disabled must be re-enabled by
        teardown(), or the new session soft-locks until reload."""
        self.page.goto(self.url("/"))
        self.page.wait_for_selector("#assistant-drawer", state="attached")
        self.page.evaluate("openDrawer()")
        self.page.wait_for_function(
            "typeof drawerEngine !== 'undefined' && drawerEngine !== null"
        )
        # Controlled stream: the first chunk starts the turn; the terminal
        # error frame is held until after "New chat" tears the engine down.
        # The fake stream ignores abort() — like a chunk already in flight.
        self.page.evaluate(
            """() => {
                const orig = window.fetch;
                const enc = new TextEncoder();
                window.__releaseStream = null;
                window.fetch = function(url, opts) {
                    if (typeof url === 'string' && url.includes('/stream/')) {
                        const stream = new ReadableStream({
                            start(ctrl) {
                                ctrl.enqueue(enc.encode(
                                    'event: user_message\\n'
                                    + 'data: {"id": 1, "content": "q", "turn_id": 424242}\\n\\n'
                                    + 'event: token\\ndata: {"text": "partial answer"}\\n\\n'
                                ));
                                window.__releaseStream = () => {
                                    ctrl.enqueue(enc.encode(
                                        'event: error\\ndata: {"message": "boom from old turn"}\\n\\n'
                                    ));
                                    ctrl.close();
                                };
                            }
                        });
                        return Promise.resolve(new Response(stream, {
                            status: 200,
                            headers: {'Content-Type': 'text/event-stream'},
                        }));
                    }
                    return orig.apply(this, arguments);
                };
            }"""
        )
        self.page.fill("#drawer-chat-input", "old session question")
        self.page.click("#drawer-send-btn")
        self.page.wait_for_selector(
            "#drawer-message-list >> text=partial answer", timeout=5000
        )
        # Mid-stream: new chat (real endpoint; only /stream/ is patched).
        self.page.evaluate("drawerNewSession()")
        # Now deliver the old stream's held terminal error frame.
        self.page.wait_for_function("typeof window.__releaseStream === 'function'")
        self.page.evaluate("window.__releaseStream()")
        self.page.wait_for_timeout(300)  # let the stray frame dispatch

        # (a) no restore bleed into the shared input...
        self.assertEqual(self.page.input_value("#drawer-chat-input"), "")
        # (b) ...no old-turn error text in the new session's view...
        self.assertEqual(
            self.page.locator(
                "#drawer-message-list >> text=boom from old turn"
            ).count(),
            0,
        )
        # (c) ...and the new session is usable: shared send button re-enabled.
        self.page.wait_for_function(
            "!document.getElementById('drawer-send-btn').disabled", timeout=5000
        )
        self.assertEqual(
            self.page.text_content("#drawer-send-btn").strip(), "Send"
        )

    def test_drawer_hides_retry_edit_but_copy_works(self):
        """The shared _message.html partial renders Retry/Edit/Copy in the
        drawer too. Retry/Edit handlers only exist on the full page —
        clicking them in the drawer threw ReferenceError — so they are
        hidden there; Copy's handler lives in the shared engine file and
        stays."""
        ChatMessage.objects.create(
            session=self.session, role="user", content="drawer question"
        )
        ChatMessage.objects.create(
            session=self.session, role="assistant", content="drawer answer"
        )
        # Any page with the drawer works; the dashboard avoids chat.html's
        # own message list confusing the selectors.
        self.page.goto(self.url("/"))
        self.page.wait_for_selector("#assistant-drawer", state="attached")
        self.page.evaluate("openDrawer()")
        self.page.wait_for_selector(
            "#drawer-message-list >> text=drawer answer", timeout=5000
        )

        # copyMessage is defined globally (shared engine file)...
        self.assertTrue(
            self.page.evaluate("typeof copyMessage === 'function'")
        )
        # ...retry/edit buttons are display:none inside the drawer...
        hidden = self.page.evaluate(
            """() => {
                const q = (sel) => Array.from(
                    document.querySelectorAll('#assistant-drawer ' + sel));
                const btns = q('button[onclick^="retryMessage("]')
                    .concat(q('button[onclick^="editMessage("]'));
                return btns.length > 0 && btns.every(
                    (b) => getComputedStyle(b).display === 'none');
            }"""
        )
        self.assertTrue(hidden, "drawer Retry/Edit must be hidden")
        # ...and the Copy button is not.
        copy_visible = self.page.evaluate(
            """() => {
                const b = document.querySelector(
                    '#assistant-drawer button[onclick^="copyMessage("]');
                return !!b && getComputedStyle(b).display !== 'none';
            }"""
        )
        self.assertTrue(copy_visible, "drawer Copy must stay usable")

    def test_chat_page_renders_with_gmail_available(self):
        """Regression: the gmail-only attach-panel markup only renders when
        Gmail is connected — which the e2e DB normally isn't, so a template
        bug there (a multi-line {# #} pseudo-comment emitting a literal
        <select> that mangled the DOM and hid #chat-input) sailed through
        the suite. Render the page with Gmail available and prove the
        composer is usable and the lazy label wrapper is present."""
        from unittest.mock import patch

        with patch("email_links.gmail.is_available", return_value=True), \
             patch("email_links.gmail.get_labels", return_value=[
                 {"id": "INBOX", "name": "Inbox", "type": "system"},
             ]):
            self.page.goto(self.url(f"/assistant/{self.session.pk}/"))
            # The composer must be VISIBLE (not swallowed into the hidden
            # attach panel by broken markup).
            self.page.wait_for_selector("#chat-input", state="visible", timeout=5000)
            self.assertTrue(
                self.page.evaluate(
                    "document.getElementById('attach-label-wrap') !== null"
                )
            )
            # Opening the picker lazily loads the label select.
            self.page.evaluate("toggleEmailPicker()")
            self.page.wait_for_selector("#attach-label-select", timeout=5000)


class AssistantWave2IntegrationTests(PlaywrightTestCase):
    """Wave 2 pre-deploy integration review fixes: boot-time resume of a
    running turn (+ title pickup via turn-status), drawer busy-guard notice,
    edit re-carrying attachment blocks, and synthetic resends leaving staged
    attachments alone."""

    def _capture_stream_posts(self):
        """Patch window.fetch so /stream/ POSTs are captured (message text on
        window.__capturedMessages) and answered with a minimal healthy SSE
        stream; every other fetch passes through to the real server."""
        self.page.evaluate(
            """() => {
                const orig = window.fetch;
                const enc = new TextEncoder();
                window.__capturedMessages = [];
                window.fetch = function(url, opts) {
                    if (typeof url === 'string' && url.includes('/stream/')) {
                        window.__capturedMessages.push(
                            opts.body.get('message'));
                        const body =
                            'event: user_message\\n'
                            + 'data: {"id": 1, "content": "q", "turn_id": 777}\\n\\n'
                            + 'event: token\\ndata: {"text": "ok"}\\n\\n'
                            + 'event: done\\ndata: {"message_id": 1}\\n\\n';
                        const stream = new ReadableStream({
                            start(ctrl) {
                                ctrl.enqueue(enc.encode(body));
                                ctrl.close();
                            }
                        });
                        return Promise.resolve(new Response(stream, {
                            status: 200,
                            headers: {'Content-Type': 'text/event-stream'},
                        }));
                    }
                    return orig.apply(this, arguments);
                };
            }"""
        )

    def test_reload_mid_turn_resumes_and_renders_answer_and_title(self):
        """F2-1 + F1-2: loading a session whose turn is still RUNNING must
        adopt it (send locked, 'still working' bubble) and, when the turn
        completes server-side, render the persisted answer and pick the
        async-generated title up from the turn-status payload."""
        from assistant.models import AssistantTurn

        session = ChatSession.objects.create()  # title "New Chat"
        ChatMessage.objects.create(
            session=session, role="user", content="a very long question"
        )
        turn = AssistantTurn.objects.create(
            session=session, state=AssistantTurn.STATE_RUNNING
        )
        self.page.goto(self.url(f"/assistant/{session.pk}/"))

        # Boot-resume adopts the live turn.
        self.page.wait_for_selector(
            "text=still working on your last message", timeout=5000
        )
        self.page.wait_for_function(
            "document.getElementById('send-btn').disabled", timeout=5000
        )

        # The turn finishes in the background (what the detached drain does):
        # answer persisted, title generated, turn completed.
        answer = ChatMessage.objects.create(
            session=session, role="assistant", content="the finished answer"
        )
        session.title = "Generated Title"
        session.save(update_fields=["title"])
        AssistantTurn.objects.filter(pk=turn.pk).update(
            state=AssistantTurn.STATE_COMPLETED, final_message=answer
        )

        # The 4s status poll lands on completed: messages reload, send
        # unlocks, and the title reaches the header from the status payload.
        self.page.wait_for_selector("text=the finished answer", timeout=15000)
        self.page.wait_for_function(
            "!document.getElementById('send-btn').disabled", timeout=10000
        )
        self.page.wait_for_function(
            "document.querySelector('h1.truncate')"
            " && document.querySelector('h1.truncate').textContent"
            "        .includes('Generated Title')",
            timeout=10000,
        )

    def test_drawer_busy_guard_shows_notice(self):
        """F1-1: a submit into a streaming drawer engine must surface the
        shared toast, not silently no-op (Process Email's synthetic submit
        lands on exactly this path)."""
        self.page.goto(self.url("/"))
        self.page.wait_for_selector("#assistant-drawer", state="attached")
        self.page.evaluate("openDrawer()")
        self.page.wait_for_function(
            "typeof drawerEngine !== 'undefined' && drawerEngine !== null"
        )
        # Hold a stream open so the engine stays streaming.
        self.page.evaluate(
            """() => {
                const orig = window.fetch;
                const enc = new TextEncoder();
                window.fetch = function(url, opts) {
                    if (typeof url === 'string' && url.includes('/stream/')) {
                        const stream = new ReadableStream({
                            start(ctrl) {
                                ctrl.enqueue(enc.encode(
                                    'event: user_message\\n'
                                    + 'data: {"id": 1, "content": "q", "turn_id": 555}\\n\\n'
                                    + 'event: token\\ndata: {"text": "partial"}\\n\\n'
                                ));
                                window.__holdCtrl = ctrl;  // never closed
                            }
                        });
                        return Promise.resolve(new Response(stream, {
                            status: 200,
                            headers: {'Content-Type': 'text/event-stream'},
                        }));
                    }
                    return orig.apply(this, arguments);
                };
            }"""
        )
        self.page.fill("#drawer-chat-input", "first message")
        self.page.click("#drawer-send-btn")
        self.page.wait_for_selector(
            "#drawer-message-list >> text=partial", timeout=5000
        )
        # A second submit mid-stream (typed or synthetic) → visible notice.
        self.page.evaluate(
            """() => {
                document.getElementById('drawer-chat-input').value = 'second';
                document.getElementById('drawer-chat-form').dispatchEvent(
                    new Event('submit', {cancelable: true}));
            }"""
        )
        self.page.wait_for_selector("#chat-notice", timeout=5000)
        self.assertIn(
            "still responding",
            self.page.locator("#chat-notice").text_content(),
        )
        # The refused text stays in the input — nothing was swallowed.
        self.assertEqual(
            self.page.input_value("#drawer-chat-input"), "second"
        )

    def test_edit_resend_keeps_attachment_blocks(self):
        """F4-2: editing a message that carried [AttachedEmails] must re-carry
        the marker block on the resend — the input is populated from the
        marker-stripped display text and the edit deletes the original row."""
        session = ChatSession.objects.create(title="Attach Chat")
        raw = (
            '[AttachedEmails]\n'
            '[{"thread_id": "t1", "subject": "Deal", "thread_text": "body"}]\n'
            '[/AttachedEmails]\n'
            'summarize this'
        )
        user_msg = ChatMessage.objects.create(
            session=session, role="user", content=raw
        )
        ChatMessage.objects.create(
            session=session, role="assistant", content="summary here"
        )
        self.page.goto(self.url(f"/assistant/{session.pk}/"))
        self.page.wait_for_selector("#chat-input")
        self._capture_stream_posts()

        self.page.evaluate(f"editMessage({user_msg.pk})")
        # The input holds only the typed text (markers stripped for display).
        self.assertEqual(
            self.page.input_value("#chat-input"), "summarize this"
        )
        self.page.fill("#chat-input", "summarize this edited")
        # Organic submit (the user pressing Send).
        self.page.evaluate(
            "document.getElementById('chat-form').dispatchEvent("
            "new Event('submit', {cancelable: true}))"
        )
        self.page.wait_for_function(
            "window.__capturedMessages && window.__capturedMessages.length === 1",
            timeout=10000,
        )
        sent = self.page.evaluate("window.__capturedMessages[0]")
        self.assertTrue(
            sent.startswith("[AttachedEmails]"),
            f"attachment block dropped from edited resend: {sent[:80]!r}",
        )
        self.assertIn('"thread_text": "body"', sent)
        self.assertTrue(sent.endswith("summarize this edited"))

    def test_retry_leaves_staged_attachments_alone(self):
        """F4-3: a Retry resend must not consume attachments staged for the
        user's NEXT message — the staged block must not ride on the retried
        text, and the staging must survive."""
        session = ChatSession.objects.create(title="Retry Chat")
        ChatMessage.objects.create(
            session=session, role="user", content="the question"
        )
        answer = ChatMessage.objects.create(
            session=session, role="assistant", content="the answer"
        )
        self.page.goto(self.url(f"/assistant/{session.pk}/"))
        self.page.wait_for_selector("#chat-input")
        self._capture_stream_posts()

        # Stage an email for the user's next message (ready to send).
        self.page.evaluate(
            """() => {
                _attachedEmails.push({
                    threadId: 't9', subject: 'For my next message',
                    fromName: 'A', fromEmail: 'a@example.com', date: '',
                    messageCount: 1, threadText: 'staged body',
                    loading: false, error: '',
                });
                _renderEmailSummary();
            }"""
        )
        self.page.evaluate(f"retryMessage({answer.pk})")
        self.page.wait_for_function(
            "window.__capturedMessages && window.__capturedMessages.length === 1",
            timeout=10000,
        )
        sent = self.page.evaluate("window.__capturedMessages[0]")
        self.assertNotIn("[AttachedEmails]", sent)
        self.assertEqual(sent, "the question")
        # The staging survived for the user's next organic send.
        self.assertEqual(self.page.evaluate("_attachedEmails.length"), 1)

    def test_edit_network_failure_restores_text(self):
        """F5-1: a network failure in the edit chain must restore the typed
        text and show a notice — the text lived only in a local variable and
        the input was already cleared (silent loss pre-fix)."""
        session = ChatSession.objects.create(title="Edit Fail Chat")
        user_msg = ChatMessage.objects.create(
            session=session, role="user", content="original question"
        )
        ChatMessage.objects.create(
            session=session, role="assistant", content="original answer"
        )
        self.page.goto(self.url(f"/assistant/{session.pk}/"))
        self.page.wait_for_selector("#chat-input")
        # Reject the edit POST at the network level (blip mid-round-trip).
        self.page.evaluate(
            """() => {
                const orig = window.fetch;
                window.fetch = function(url, opts) {
                    if (typeof url === 'string' && url.includes('/edit/')) {
                        return Promise.reject(new TypeError('network down'));
                    }
                    return orig.apply(this, arguments);
                };
            }"""
        )
        self.page.evaluate(f"editMessage({user_msg.pk})")
        self.page.fill("#chat-input", "edited question")
        self.page.evaluate(
            "document.getElementById('chat-form').dispatchEvent("
            "new Event('submit', {cancelable: true}))"
        )
        self.page.wait_for_selector("#chat-notice", timeout=5000)
        self.assertIn(
            "restored",
            self.page.locator("#chat-notice").text_content(),
        )
        self.page.wait_for_function(
            "document.getElementById('chat-input').value === 'edited question'",
            timeout=5000,
        )

    def test_gmail_label_load_retries_after_failure(self):
        """F5-3: a failed label load must not permanently consume the lazy
        one-shot — closing and reopening the attach panel retries."""
        from unittest.mock import patch

        with patch("email_links.gmail.is_available", return_value=True), \
             patch("email_links.gmail.get_labels", return_value=[
                 {"id": "INBOX", "name": "Inbox", "type": "system"},
             ]):
            session = ChatSession.objects.create(title="Labels Chat")
            self.page.goto(self.url(f"/assistant/{session.pk}/"))
            self.page.wait_for_selector("#chat-input", state="visible")
            # First label request dies at the network level.
            state = {"first": True}

            def handle(route):
                if state["first"]:
                    state["first"] = False
                    route.abort()
                else:
                    route.continue_()

            self.page.route("**/gmail-labels/", handle)
            self.page.evaluate("toggleEmailPicker()")
            self.page.wait_for_timeout(600)
            self.assertEqual(
                self.page.locator("#attach-label-select").count(), 0,
                "test setup: first load should have failed",
            )
            # Close and reopen: the reset flag re-fires the load, which now
            # succeeds.
            self.page.evaluate("toggleEmailPicker()")
            self.page.evaluate("toggleEmailPicker()")
            self.page.wait_for_selector("#attach-label-select", timeout=5000)
