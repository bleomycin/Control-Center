import csv

from django.http import HttpResponse


def export_csv(queryset, fields, filename):
    """Generic CSV export utility.

    Args:
        queryset: Django queryset to export
        fields: list of (field_name, header_label) tuples
        filename: output filename (without .csv extension)
    """
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'

    writer = csv.writer(response)
    writer.writerow([label for _, label in fields])

    for obj in queryset:
        row = []
        for field_name, _ in fields:
            value = obj
            for attr in field_name.split("__"):
                if value is None:
                    break
                value = getattr(value, attr, None)
                if callable(value):
                    value = value()
            row.append(value if value is not None else "")
        writer.writerow(row)

    return response
