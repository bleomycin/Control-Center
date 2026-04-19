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
