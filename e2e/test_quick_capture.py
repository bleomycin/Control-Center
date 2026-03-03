from django.utils import timezone

from dashboard.models import ChoiceOption
from notes.models import Note, Tag
from e2e.base import PlaywrightTestCase


class QuickCaptureModalTests(PlaywrightTestCase):
    """Test that Quick Capture modal opens and basic form works."""

    def setUp(self):
        super().setUp()
        for val, label in [("general", "General"), ("call", "Call")]:
            ChoiceOption.objects.get_or_create(
                category="note_type", value=val,
                defaults={"label": label, "is_active": True},
            )

    def _open_quick_capture(self):
        """Navigate to any page and open Quick Capture modal via sidebar button."""
        self.page.goto(self.url("/notes/"))
        self.page.click("button:has-text('Quick Note')")
        self.page.wait_for_selector("#qc-root", state="visible")

    def test_modal_opens_with_form(self):
        """Quick Capture modal opens and shows content textarea + save button."""
        self._open_quick_capture()

        # Content textarea should be visible
        content = self.page.locator("#id_content")
        self.assertTrue(content.is_visible())

        # Save button should exist
        save_btn = self.page.locator("#qc-form button[type='submit']")
        self.assertTrue(save_btn.is_visible())

    def test_form_fields_visible(self):
        """Title, date, type, and more options all visible in normal mode."""
        self._open_quick_capture()

        self.assertTrue(self.page.locator("#id_title").is_visible())
        self.assertTrue(self.page.locator("#id_date").is_visible())
        self.assertTrue(self.page.locator("#id_note_type").is_visible())

        # More options summary should be visible
        summary = self.page.locator("#qc-form-fields details summary")
        self.assertTrue(summary.is_visible())

    def test_expand_button_visible(self):
        """The expand button (arrow icon) is visible next to Content label."""
        self._open_quick_capture()

        expand_btn = self.page.locator("#qc-expand-btn")
        self.assertTrue(expand_btn.is_visible())

    def test_fullscreen_bar_hidden_by_default(self):
        """Fullscreen bar and markdown bar are hidden in normal mode."""
        self._open_quick_capture()

        fs_bar = self.page.locator("#qc-fullscreen-bar")
        self.assertTrue(fs_bar.is_hidden())

        md_bar = self.page.locator("#qc-md-bar")
        self.assertTrue(md_bar.is_hidden())

    def test_submit_creates_note(self):
        """Submit the quick capture form and verify note is created."""
        self._open_quick_capture()

        self.page.fill("#id_content", "Quick capture test content")
        self.page.click("#qc-form button[type='submit']")

        # Modal should close (HTMX triggers closeModal)
        self.page.wait_for_selector("#modal-container.hidden", state="attached")

        # Verify note was created
        note = Note.objects.get(content="Quick capture test content")
        self.assertIn("Quick capture test", note.title)


class QuickCaptureExpandTests(PlaywrightTestCase):
    """Test fullscreen expand/collapse for Quick Capture editor."""

    def setUp(self):
        super().setUp()
        for val, label in [("general", "General"), ("call", "Call")]:
            ChoiceOption.objects.get_or_create(
                category="note_type", value=val,
                defaults={"label": label, "is_active": True},
            )

    def _open_quick_capture(self):
        self.page.goto(self.url("/notes/"))
        self.page.click("button:has-text('Quick Note')")
        self.page.wait_for_selector("#qc-root", state="visible")

    def test_expand_shows_fullscreen_bar(self):
        """Clicking expand button shows the fullscreen top bar."""
        self._open_quick_capture()
        self.page.click("#qc-expand-btn")

        fs_bar = self.page.locator("#qc-fullscreen-bar")
        fs_bar.wait_for(state="visible")
        self.assertTrue(fs_bar.is_visible())

        # Should contain "Quick Capture" text and Done button
        self.assertIn("Quick Capture", fs_bar.text_content())
        done_btn = fs_bar.locator("button:has-text('Done')")
        self.assertTrue(done_btn.is_visible())

    def test_expand_shows_markdown_bar(self):
        """Clicking expand shows the markdown helper bar."""
        self._open_quick_capture()
        self.page.click("#qc-expand-btn")

        md_bar = self.page.locator("#qc-md-bar")
        md_bar.wait_for(state="visible")
        self.assertTrue(md_bar.is_visible())

        # Should have all 6 markdown buttons
        buttons = md_bar.locator("button")
        self.assertEqual(6, buttons.count())

    def test_expand_hides_form_fields(self):
        """Expanding hides title, date/type, more options, and save bar."""
        self._open_quick_capture()
        self.page.click("#qc-expand-btn")

        # Wait for fullscreen bar to confirm expand happened
        self.page.wait_for_selector("#qc-fullscreen-bar", state="visible")

        # Form fields should be hidden
        fields = self.page.locator("#qc-form-fields")
        self.assertTrue(fields.is_hidden())

        # Heading should be hidden
        heading = self.page.locator("#qc-heading")
        self.assertTrue(heading.is_hidden())

        # Expand button itself should be hidden
        expand_btn = self.page.locator("#qc-expand-btn")
        self.assertTrue(expand_btn.is_hidden())

    def test_expand_modal_goes_fullscreen(self):
        """Modal content element gets fullscreen classes after expand."""
        self._open_quick_capture()
        self.page.click("#qc-expand-btn")
        self.page.wait_for_selector("#qc-fullscreen-bar", state="visible")

        modal = self.page.locator("#modal-content")
        classes = modal.get_attribute("class")

        # Should have fullscreen classes
        self.assertIn("w-full", classes)
        self.assertIn("h-full", classes)

        # Should NOT have normal modal classes
        self.assertNotIn("max-w-2xl", classes)
        self.assertNotIn("rounded-lg", classes)

    def test_content_textarea_visible_in_fullscreen(self):
        """Content textarea remains visible and editable in fullscreen."""
        self._open_quick_capture()
        self.page.fill("#id_content", "Before expand")
        self.page.click("#qc-expand-btn")
        self.page.wait_for_selector("#qc-fullscreen-bar", state="visible")

        content = self.page.locator("#id_content")
        self.assertTrue(content.is_visible())
        self.assertEqual("Before expand", content.input_value())

        # Can still type
        content.fill("Before expand — more text after expand")
        self.assertEqual("Before expand — more text after expand", content.input_value())

    def test_collapse_restores_normal_mode(self):
        """Clicking Done collapses back to normal modal mode."""
        self._open_quick_capture()
        self.page.click("#qc-expand-btn")
        self.page.wait_for_selector("#qc-fullscreen-bar", state="visible")

        # Click Done
        self.page.click("#qc-fullscreen-bar button:has-text('Done')")

        # Fullscreen bar should be hidden again
        fs_bar = self.page.locator("#qc-fullscreen-bar")
        self.assertTrue(fs_bar.is_hidden())

        # Markdown bar should be hidden
        md_bar = self.page.locator("#qc-md-bar")
        self.assertTrue(md_bar.is_hidden())

        # Form fields should be visible again
        fields = self.page.locator("#qc-form-fields")
        self.assertTrue(fields.is_visible())

        # Heading should be visible again
        heading = self.page.locator("#qc-heading")
        self.assertTrue(heading.is_visible())

        # Expand button should be visible again
        expand_btn = self.page.locator("#qc-expand-btn")
        self.assertTrue(expand_btn.is_visible())

    def test_collapse_restores_modal_classes(self):
        """After collapse, modal gets its normal classes back."""
        self._open_quick_capture()
        self.page.click("#qc-expand-btn")
        self.page.wait_for_selector("#qc-fullscreen-bar", state="visible")

        # Collapse
        self.page.click("#qc-fullscreen-bar button:has-text('Done')")

        modal = self.page.locator("#modal-content")
        classes = modal.get_attribute("class")

        # Should have normal classes back
        self.assertIn("max-w-2xl", classes)
        self.assertIn("rounded-lg", classes)

        # Should NOT have fullscreen classes
        self.assertNotIn("h-full", classes)
        self.assertNotIn("max-w-none", classes)

    def test_content_preserved_after_collapse(self):
        """Text typed in fullscreen mode is preserved after collapsing."""
        self._open_quick_capture()
        self.page.fill("#id_content", "Start typing")

        # Expand
        self.page.click("#qc-expand-btn")
        self.page.wait_for_selector("#qc-fullscreen-bar", state="visible")

        # Type more in fullscreen
        content = self.page.locator("#id_content")
        content.fill("Start typing — continued in fullscreen")

        # Collapse
        self.page.click("#qc-fullscreen-bar button:has-text('Done')")

        # Content should be preserved
        self.assertEqual("Start typing — continued in fullscreen", content.input_value())

    def test_submit_after_collapse_saves_note(self):
        """Type in fullscreen, collapse, submit — note is saved correctly."""
        self._open_quick_capture()

        # Expand
        self.page.click("#qc-expand-btn")
        self.page.wait_for_selector("#qc-fullscreen-bar", state="visible")

        # Type content in fullscreen
        self.page.fill("#id_content", "Fullscreen note content here")

        # Collapse
        self.page.click("#qc-fullscreen-bar button:has-text('Done')")

        # Fill in title after collapse
        self.page.fill("#id_title", "My Fullscreen Note")

        # Submit
        self.page.click("#qc-form button[type='submit']")
        self.page.wait_for_selector("#modal-container.hidden", state="attached")

        # Verify note was created with correct content
        note = Note.objects.get(title="My Fullscreen Note")
        self.assertEqual("Fullscreen note content here", note.content)


class QuickCaptureMarkdownBarTests(PlaywrightTestCase):
    """Test markdown helper bar buttons in fullscreen mode."""

    def setUp(self):
        super().setUp()
        ChoiceOption.objects.get_or_create(
            category="note_type", value="general",
            defaults={"label": "General", "is_active": True},
        )

    def _open_fullscreen(self):
        self.page.goto(self.url("/notes/"))
        self.page.click("button:has-text('Quick Note')")
        self.page.wait_for_selector("#qc-root", state="visible")
        self.page.click("#qc-expand-btn")
        self.page.wait_for_selector("#qc-md-bar", state="visible")

    def test_bold_button_inserts_markdown(self):
        """Bold button wraps selection or inserts ** markers."""
        self._open_fullscreen()

        content = self.page.locator("#id_content")
        content.fill("hello world")

        # Select "world" (chars 6-11)
        content.evaluate("el => { el.selectionStart = 6; el.selectionEnd = 11; }")

        # Click Bold
        self.page.click("#qc-md-bar button:nth-child(1)")

        val = content.input_value()
        self.assertEqual("hello **world**", val)

    def test_italic_button_inserts_markdown(self):
        """Italic button wraps selection with single asterisks."""
        self._open_fullscreen()

        content = self.page.locator("#id_content")
        content.fill("hello world")
        content.evaluate("el => { el.selectionStart = 6; el.selectionEnd = 11; }")

        # Click Italic
        self.page.click("#qc-md-bar button:nth-child(2)")

        val = content.input_value()
        self.assertEqual("hello *world*", val)

    def test_heading_button_inserts_h2(self):
        """H2 button inserts ## prefix."""
        self._open_fullscreen()

        content = self.page.locator("#id_content")
        content.fill("")

        # Place cursor at start
        content.evaluate("el => { el.selectionStart = 0; el.selectionEnd = 0; }")

        # Click H2
        self.page.click("#qc-md-bar button:nth-child(3)")

        val = content.input_value()
        self.assertEqual("## ", val)

    def test_list_button_inserts_dash(self):
        """List button inserts '- ' prefix."""
        self._open_fullscreen()

        content = self.page.locator("#id_content")
        content.fill("")
        content.evaluate("el => { el.selectionStart = 0; el.selectionEnd = 0; }")

        # Click List
        self.page.click("#qc-md-bar button:nth-child(4)")

        val = content.input_value()
        self.assertEqual("- ", val)

    def test_link_button_inserts_link_syntax(self):
        """Link button wraps selection with [](url) syntax."""
        self._open_fullscreen()

        content = self.page.locator("#id_content")
        content.fill("click here")
        content.evaluate("el => { el.selectionStart = 0; el.selectionEnd = 10; }")

        # Click Link
        self.page.click("#qc-md-bar button:nth-child(5)")

        val = content.input_value()
        self.assertEqual("[click here](url)", val)

    def test_code_button_inserts_backticks(self):
        """Code button wraps selection with backticks."""
        self._open_fullscreen()

        content = self.page.locator("#id_content")
        content.fill("myVar")
        content.evaluate("el => { el.selectionStart = 0; el.selectionEnd = 5; }")

        # Click Code
        self.page.click("#qc-md-bar button:nth-child(6)")

        val = content.input_value()
        self.assertEqual("`myVar`", val)


class QuickCaptureMobileExpandTests(PlaywrightTestCase):
    """Test fullscreen expand behavior at mobile viewport."""

    def setUp(self):
        super().setUp()
        ChoiceOption.objects.get_or_create(
            category="note_type", value="general",
            defaults={"label": "General", "is_active": True},
        )

    def _open_quick_capture_mobile(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.goto(self.url("/notes/"))
        # On mobile, sidebar is off-screen. Use JS to trigger the HTMX request directly.
        self.page.evaluate("""
            document.getElementById('sidebar').classList.remove('-translate-x-full');
        """)
        self.page.click("button:has-text('Quick Note')")
        self.page.wait_for_selector("#qc-root", state="visible")

    def test_mobile_expand_and_collapse(self):
        """Full expand/collapse cycle works at mobile viewport."""
        self._open_quick_capture_mobile()

        # Expand
        self.page.click("#qc-expand-btn")
        self.page.wait_for_selector("#qc-fullscreen-bar", state="visible")

        # Form fields hidden
        self.assertTrue(self.page.locator("#qc-form-fields").is_hidden())

        # Content textarea visible
        self.assertTrue(self.page.locator("#id_content").is_visible())

        # Markdown bar visible
        self.assertTrue(self.page.locator("#qc-md-bar").is_visible())

        # Collapse
        self.page.click("#qc-fullscreen-bar button:has-text('Done')")

        # Form fields visible again
        self.assertTrue(self.page.locator("#qc-form-fields").is_visible())
        self.assertTrue(self.page.locator("#qc-fullscreen-bar").is_hidden())

    def test_mobile_fullscreen_submit_flow(self):
        """Mobile: expand -> type -> collapse -> fill metadata -> submit."""
        self._open_quick_capture_mobile()

        # Expand and write content
        self.page.click("#qc-expand-btn")
        self.page.wait_for_selector("#qc-fullscreen-bar", state="visible")
        self.page.fill("#id_content", "Mobile fullscreen note")

        # Use a markdown button
        content = self.page.locator("#id_content")
        content.evaluate("el => { el.selectionStart = el.value.length; el.selectionEnd = el.value.length; }")
        self.page.click("#qc-md-bar button:nth-child(1)")  # Bold inserts **

        # Collapse
        self.page.click("#qc-fullscreen-bar button:has-text('Done')")

        # Fill title
        self.page.fill("#id_title", "Mobile Note Title")

        # Submit
        self.page.click("#qc-form button[type='submit']")
        self.page.wait_for_selector("#modal-container.hidden", state="attached")

        # Verify note saved
        note = Note.objects.get(title="Mobile Note Title")
        self.assertIn("Mobile fullscreen note", note.content)

    def test_mobile_more_options_after_collapse(self):
        """More options section works correctly after expanding and collapsing."""
        self._open_quick_capture_mobile()

        # Expand then collapse
        self.page.click("#qc-expand-btn")
        self.page.wait_for_selector("#qc-fullscreen-bar", state="visible")
        self.page.click("#qc-fullscreen-bar button:has-text('Done')")

        # More options should be openable
        summary = self.page.locator("#qc-form-fields details summary")
        summary.click()

        # Folder field should become visible
        folder = self.page.locator("#id_folder")
        folder.wait_for(state="visible")
        self.assertTrue(folder.is_visible())


class QuickCaptureTagPillTests(PlaywrightTestCase):
    """Test tag pills in Quick Capture still work with the new structure."""

    def setUp(self):
        super().setUp()
        ChoiceOption.objects.get_or_create(
            category="note_type", value="general",
            defaults={"label": "General", "is_active": True},
        )
        self.tag = Tag.objects.create(name="Urgent", slug="urgent", color="red")

    def test_tag_pills_toggle_in_quick_capture(self):
        """Tag pills in More options toggle correctly."""
        self.page.goto(self.url("/notes/"))
        self.page.click("button:has-text('Quick Note')")
        self.page.wait_for_selector("#qc-root", state="visible")

        # Open More options
        self.page.click("#qc-form-fields details summary")

        # Find tag pill
        pill = self.page.locator("#qc-form-fields .form-tag-pill")
        pill.wait_for(state="visible")

        # Initially inactive
        self.assertIn("border-gray-600", pill.get_attribute("class"))

        # Click to activate
        pill.click()
        active_bg = pill.get_attribute("data-active-bg")
        self.page.wait_for_function(
            f"document.querySelector('#qc-form-fields .form-tag-pill').classList.contains('{active_bg}')"
        )
        self.assertIn(active_bg, pill.get_attribute("class"))

    def test_tag_selection_saved_with_note(self):
        """Select a tag, submit, verify tag is applied."""
        self.page.goto(self.url("/notes/"))
        self.page.click("button:has-text('Quick Note')")
        self.page.wait_for_selector("#qc-root", state="visible")

        # Fill content
        self.page.fill("#id_content", "Note with tag")

        # Open More options and select tag
        self.page.click("#qc-form-fields details summary")
        pill = self.page.locator("#qc-form-fields .form-tag-pill")
        pill.wait_for(state="visible")
        pill.click()

        # Submit
        self.page.click("#qc-form button[type='submit']")
        self.page.wait_for_selector("#modal-container.hidden", state="attached")

        # Verify
        note = Note.objects.get(content="Note with tag")
        self.assertIn(self.tag.pk, list(note.tags.values_list("pk", flat=True)))
