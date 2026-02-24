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
    path("<int:pk>/pin/", views.toggle_pin, name="toggle_pin"),
    path("<int:pk>/inline/content/", views.inline_edit_content, name="inline_edit_content"),
    path("<int:pk>/inline/title/", views.inline_edit_title, name="inline_edit_title"),
    path("<int:pk>/inline/metadata/", views.inline_edit_metadata, name="inline_edit_metadata"),
    path("<int:pk>/attachment/add/", views.attachment_add, name="attachment_add"),
    path("attachment/<int:pk>/delete/", views.attachment_delete, name="attachment_delete"),
    path("<int:pk>/link/add/", views.link_add, name="link_add"),
    path("link/<int:pk>/edit/", views.link_edit, name="link_edit"),
    path("link/<int:pk>/delete/", views.link_delete, name="link_delete"),
    path("quick-capture/", views.quick_capture, name="quick_capture"),
    path("bulk/delete/", views.bulk_delete, name="bulk_delete"),
    path("bulk/export/", views.bulk_export_csv, name="bulk_export_csv"),
    path("bulk/apply-tags/", views.bulk_apply_tags, name="bulk_apply_tags"),
    path("bulk/move-folder/", views.bulk_move_folder, name="bulk_move_folder"),
    # Tag management
    path("tags/", views.tag_list, name="tag_list"),
    path("tags/add/", views.tag_add, name="tag_add"),
    path("tags/<int:pk>/edit/", views.tag_edit, name="tag_edit"),
    path("tags/<int:pk>/delete/", views.tag_delete, name="tag_delete"),
    # Folder management
    path("folders/tabs/", views.folder_tabs, name="folder_tabs"),
    path("folders/", views.folder_list, name="folder_list"),
    path("folders/add/", views.folder_add, name="folder_add"),
    path("folders/<int:pk>/edit/", views.folder_edit, name="folder_edit"),
    path("folders/<int:pk>/delete/", views.folder_delete, name="folder_delete"),
]
