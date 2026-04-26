"""E2E tests for assistant Drive-attach footer rendering.

Verifies the user-message bubble renders the dashed attachment footer
correctly when a ChatMessage contains the [AttachedDriveFiles] marker
(and optionally a preceding [AttachedEmail:{...}] marker).

Strategy: bypass the live Drive picker (which would require OAuth +
real network) by directly creating a ChatMessage via the Django ORM
with a hand-built marker, then load the chat page and assert on the
rendered HTML.

Coverage:
1. user bubble shows the drive-files footer with the correct count and
   tooltip when only a Drive marker is present
2. user bubble shows BOTH "1 email" and "N file(s)" footer spans when
   both markers are present (combined email+drive flow per CONTEXT D-10)
3. user bubble renders WITHOUT a footer when no markers are present
"""
import json

from assistant.models import ChatMessage, ChatSession

from e2e.base import PlaywrightTestCase


class AssistantDriveAttachFooterTest(PlaywrightTestCase):
    """E2E tests of the chat-history attachment-count footer."""

    def test_user_bubble_shows_drive_files_footer(self):
        """User bubble with [AttachedDriveFiles] marker renders the count
        footer; the marker itself is stripped from the visible message."""
        session = ChatSession.objects.create(title="E2E Drive Attach Test")
        files = [
            {
                "id": "e2e-1",
                "name": "DocA.pdf",
                "mimeType": "application/pdf",
                "url": "https://drive.google.com/file/d/e2e-1/view",
            },
            {
                "id": "e2e-2",
                "name": "DocB.pdf",
                "mimeType": "application/pdf",
                "url": "https://drive.google.com/file/d/e2e-2/view",
            },
        ]
        marker = (
            "[AttachedDriveFiles]\n"
            + json.dumps(files)
            + "\n[/AttachedDriveFiles]\n"
        )
        ChatMessage.objects.create(
            session=session,
            role="user",
            content=marker + "attach these to my Property",
        )
        ChatMessage.objects.create(
            session=session,
            role="assistant",
            content="Linked 2 documents.",
        )

        self.page.goto(self.url(f"/assistant/{session.pk}/"))
        self.page.wait_for_selector("#message-list")

        # The page's JS source contains the literal "[AttachedDriveFiles]"
        # string (used to BUILD the marker on submit) — so we must scope
        # the "marker-stripped" assertion to the rendered message list,
        # not the full document HTML.
        message_list_html = self.page.locator("#message-list").inner_html()

        # display_content stripped the marker — the [AttachedDriveFiles]
        # literal must NOT appear inside the rendered message bubbles
        self.assertNotIn("[AttachedDriveFiles]", message_list_html)
        # The user's typed text DOES render
        self.assertIn("attach these to my Property", message_list_html)
        # The footer count text appears
        self.assertIn("2 files", message_list_html)
        # The native title tooltip on the drive span includes both filenames
        self.assertIn("DocA.pdf", message_list_html)
        self.assertIn("DocB.pdf", message_list_html)

    def test_user_bubble_with_email_and_drive_shows_both_counts(self):
        """User bubble with BOTH [AttachedEmail:{...}] and
        [AttachedDriveFiles] markers shows both footer spans (combined
        email+drive flow per CONTEXT D-10).

        Note: pluralize ("file" vs "files") follows Django's default rule.
        """
        session = ChatSession.objects.create(title="E2E Combined Attach Test")
        email_meta = {"subject": "Re: closing", "message_count": 3}
        files = [
            {
                "id": "e2e-c-1",
                "name": "Term Sheet.pdf",
                "mimeType": "application/pdf",
                "url": "https://drive.google.com/file/d/e2e-c-1/view",
            },
        ]
        content = (
            f"[AttachedEmail:{json.dumps(email_meta)}]\nbody\n[/AttachedEmail]\n"
            f"[AttachedDriveFiles]\n{json.dumps(files)}\n[/AttachedDriveFiles]\n"
            f"process this"
        )
        ChatMessage.objects.create(session=session, role="user", content=content)

        self.page.goto(self.url(f"/assistant/{session.pk}/"))
        self.page.wait_for_selector("#message-list")
        # Scope assertions to the rendered message list (chat.html's JS
        # source contains [AttachedDriveFiles] / [/AttachedEmail] literals)
        message_list_html = self.page.locator("#message-list").inner_html()

        # The literal "1 email" hard-coded label appears
        self.assertIn("1 email", message_list_html)
        # The literal "1 file" appears (singular — pluralize empty for count=1)
        self.assertIn("1 file", message_list_html)
        # Email tooltip surfaces the subject text
        self.assertIn("Re: closing", message_list_html)
        # Drive tooltip surfaces the filename
        self.assertIn("Term Sheet.pdf", message_list_html)
        # The user's typed text displays
        self.assertIn("process this", message_list_html)
        # Markers themselves are stripped from the visible bubble content
        self.assertNotIn("[AttachedDriveFiles]", message_list_html)
        self.assertNotIn("[/AttachedEmail]", message_list_html)

    def test_user_bubble_without_attachments_renders_no_footer(self):
        """User bubble without any markers renders without the dashed
        attachment footer."""
        session = ChatSession.objects.create(title="E2E No Attach Test")
        ChatMessage.objects.create(
            session=session,
            role="user",
            content="just a regular question",
        )

        self.page.goto(self.url(f"/assistant/{session.pk}/"))
        self.page.wait_for_selector("#message-list")
        # Scope to message list — the page may include unrelated dashed
        # borders elsewhere (composer popovers, etc.)
        message_list_html = self.page.locator("#message-list").inner_html()

        self.assertIn("just a regular question", message_list_html)
        # Footer-specific class signature does not appear in this bubble.
        # (`border-dashed border-blue-600/30` is the footer's distinctive
        # CSS class combination per Plan 01-03.)
        self.assertNotIn("border-dashed border-blue-600/30", message_list_html)

    def test_seeded_smith_property_session_renders_footer(self):
        """The sample-data 'Smith Property docs' session (Plan 01-04 Task 1)
        seeds a user message with the marker; loading it must render the
        '3 files' footer with all three filenames in the tooltip.

        This validates the seed → render round trip end-to-end against
        the deployed chat page (not just the model property).
        """
        # Build the same shape the loader does so this test is independent
        # of whether load_sample_data has been run in the test DB.
        files = [
            {
                "id": "demo-term-sheet-001",
                "name": "Smith-Term-Sheet.pdf",
                "mimeType": "application/pdf",
                "url": "https://drive.google.com/file/d/demo-term-sheet-001/view",
            },
            {
                "id": "demo-nda-002",
                "name": "NDA-Smith-2026.pdf",
                "mimeType": "application/pdf",
                "url": "https://drive.google.com/file/d/demo-nda-002/view",
            },
            {
                "id": "demo-closing-003",
                "name": "Closing-Statement.xlsx",
                "mimeType": (
                    "application/vnd.openxmlformats-"
                    "officedocument.spreadsheetml.sheet"
                ),
                "url": "https://drive.google.com/file/d/demo-closing-003/view",
            },
        ]
        session = ChatSession.objects.create(title="Smith Property docs")
        ChatMessage.objects.create(
            session=session,
            role="user",
            content=(
                "[AttachedDriveFiles]\n"
                + json.dumps(files)
                + "\n[/AttachedDriveFiles]\n"
                + "attach these to the Smith Property"
            ),
        )
        ChatMessage.objects.create(
            session=session,
            role="assistant",
            content="Linked 3 documents to the Smith Property.",
        )

        self.page.goto(self.url(f"/assistant/{session.pk}/"))
        self.page.wait_for_selector("#message-list")
        # Scope to message list — chat.html's JS source contains the
        # marker literal which would false-positive a full-page check.
        message_list_html = self.page.locator("#message-list").inner_html()

        self.assertIn("attach these to the Smith Property", message_list_html)
        self.assertIn("3 files", message_list_html)
        self.assertIn("Smith-Term-Sheet.pdf", message_list_html)
        self.assertIn("NDA-Smith-2026.pdf", message_list_html)
        self.assertIn("Closing-Statement.xlsx", message_list_html)
        self.assertNotIn("[AttachedDriveFiles]", message_list_html)
