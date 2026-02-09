from django.urls import path
from . import views

app_name = "notes"

urlpatterns = [
    path("", views.NoteListView.as_view(), name="list"),
    path("export/", views.export_csv, name="export_csv"),
    path("create/", views.NoteCreateView.as_view(), name="create"),
    path("<int:pk>/", views.NoteDetailView.as_view(), name="detail"),
    path("<int:pk>/pdf/", views.export_pdf_detail, name="export_pdf"),
    path("<int:pk>/edit/", views.NoteUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.NoteDeleteView.as_view(), name="delete"),
    path("<int:pk>/attachment/add/", views.attachment_add, name="attachment_add"),
    path("attachment/<int:pk>/delete/", views.attachment_delete, name="attachment_delete"),
    path("quick-capture/", views.quick_capture, name="quick_capture"),
    path("bulk/delete/", views.bulk_delete, name="bulk_delete"),
    path("bulk/export/", views.bulk_export_csv, name="bulk_export_csv"),
]
