from django import forms


class TailwindFormMixin:
    """Mixin that auto-applies Tailwind CSS classes to all form fields."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            widget = field.widget
            base_classes = (
                "block w-full rounded-md border-gray-600 bg-gray-700 text-gray-100 "
                "shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm px-3 py-2"
            )
            if isinstance(widget, (forms.CheckboxInput,)):
                widget.attrs.setdefault("class", "h-4 w-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-500")
            elif isinstance(widget, (forms.CheckboxSelectMultiple,)):
                widget.attrs.setdefault("class", "space-y-2")
            elif isinstance(widget, (forms.SelectMultiple, forms.Select)):
                widget.attrs.setdefault(
                    "class",
                    "block w-full rounded-md border-gray-600 bg-gray-700 text-gray-100 "
                    "shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm px-3 py-2",
                )
            elif isinstance(widget, (forms.Textarea,)):
                widget.attrs.setdefault("class", base_classes)
                widget.attrs.setdefault("rows", 4)
            elif isinstance(widget, (forms.FileInput, forms.ClearableFileInput)):
                widget.attrs.setdefault(
                    "class",
                    "block w-full text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 "
                    "file:rounded-md file:border-0 file:text-sm file:font-semibold "
                    "file:bg-blue-600 file:text-white hover:file:bg-blue-500",
                )
            else:
                widget.attrs.setdefault("class", base_classes)
