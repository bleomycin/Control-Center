from django import forms
from django.test import SimpleTestCase, TestCase, RequestFactory

from .export import export_csv
from .forms import TailwindFormMixin
from .pdf_export import render_pdf

from stakeholders.models import Stakeholder


# --- TailwindFormMixin Tests ---

class SampleForm(TailwindFormMixin, forms.Form):
    name = forms.CharField()
    agree = forms.BooleanField(required=False)
    category = forms.ChoiceField(choices=[("a", "A"), ("b", "B")])
    bio = forms.CharField(widget=forms.Textarea)
    avatar = forms.FileField(required=False)


class SampleFormWithClass(TailwindFormMixin, forms.Form):
    name = forms.CharField(widget=forms.TextInput(attrs={"class": "my-custom"}))


class TailwindFormMixinTests(SimpleTestCase):
    def test_text_input_gets_classes(self):
        form = SampleForm()
        cls = form.fields["name"].widget.attrs.get("class", "")
        self.assertIn("rounded-md", cls)
        self.assertIn("bg-gray-700", cls)

    def test_checkbox_gets_specific_classes(self):
        form = SampleForm()
        cls = form.fields["agree"].widget.attrs.get("class", "")
        self.assertIn("h-4", cls)
        self.assertIn("w-4", cls)

    def test_select_gets_classes(self):
        form = SampleForm()
        cls = form.fields["category"].widget.attrs.get("class", "")
        self.assertIn("rounded-md", cls)

    def test_textarea_gets_classes(self):
        form = SampleForm()
        cls = form.fields["bio"].widget.attrs.get("class", "")
        self.assertIn("rounded-md", cls)

    def test_file_input_gets_classes(self):
        form = SampleForm()
        cls = form.fields["avatar"].widget.attrs.get("class", "")
        self.assertIn("file:", cls)

    def test_existing_class_preserved(self):
        form = SampleFormWithClass()
        cls = form.fields["name"].widget.attrs.get("class", "")
        self.assertEqual(cls, "my-custom")


# --- Export CSV Tests ---

class ExportCsvTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.s1 = Stakeholder.objects.create(name="Alice", entity_type="advisor", organization="Org A")
        cls.s2 = Stakeholder.objects.create(name="Bob", entity_type="contact")

    def test_response_headers(self):
        qs = Stakeholder.objects.all()
        fields = [("name", "Name"), ("entity_type", "Type")]
        resp = export_csv(qs, fields, "test")
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("attachment", resp["Content-Disposition"])
        self.assertIn("test.csv", resp["Content-Disposition"])

    def test_header_row(self):
        qs = Stakeholder.objects.all()
        fields = [("name", "Name"), ("entity_type", "Type")]
        resp = export_csv(qs, fields, "test")
        lines = resp.content.decode().strip().split("\r\n")
        self.assertEqual(lines[0], "Name,Type")

    def test_data_rows(self):
        qs = Stakeholder.objects.filter(name="Alice")
        fields = [("name", "Name"), ("organization", "Org")]
        resp = export_csv(qs, fields, "test")
        lines = resp.content.decode().strip().split("\r\n")
        self.assertEqual(len(lines), 2)  # header + 1 data row
        self.assertIn("Alice", lines[1])
        self.assertIn("Org A", lines[1])

    def test_nested_field(self):
        from tasks.models import Task
        t = Task.objects.create(title="Nested Test", related_stakeholder=self.s1)
        qs = Task.objects.filter(pk=t.pk)
        fields = [("title", "Title"), ("related_stakeholder__name", "Stakeholder")]
        resp = export_csv(qs, fields, "test")
        content = resp.content.decode()
        self.assertIn("Alice", content)

    def test_none_becomes_empty(self):
        from tasks.models import Task
        t = Task.objects.create(title="No FK")
        qs = Task.objects.filter(pk=t.pk)
        fields = [("title", "Title"), ("related_stakeholder__name", "Stakeholder")]
        resp = export_csv(qs, fields, "test")
        lines = resp.content.decode().strip().split("\r\n")
        self.assertTrue(lines[1].endswith(","))


# --- Render PDF Tests ---

class RenderPdfTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.request = self.factory.get("/")

    def test_returns_pdf(self):
        resp = render_pdf(self.request, "test", "Test Title", sections=[])
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_content_disposition(self):
        resp = render_pdf(self.request, "my-report", "Title", sections=[])
        self.assertIn("my-report.pdf", resp["Content-Disposition"])

    def test_info_section(self):
        sections = [{"heading": "Info", "type": "info", "rows": [("Key", "Value")]}]
        resp = render_pdf(self.request, "test", "Title", sections=sections)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_table_section(self):
        sections = [{"heading": "Table", "type": "table",
                      "headers": ["Col1", "Col2"],
                      "rows": [["A", "B"], ["C", "D"]]}]
        resp = render_pdf(self.request, "test", "Title", sections=sections)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_text_section(self):
        sections = [{"heading": "Text", "type": "text", "content": "Hello world"}]
        resp = render_pdf(self.request, "test", "Title", sections=sections)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_empty_sections(self):
        resp = render_pdf(self.request, "test", "Title", sections=[])
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_subtitle_included(self):
        resp = render_pdf(self.request, "test", "Title", subtitle="Sub", sections=[])
        self.assertEqual(resp["Content-Type"], "application/pdf")
