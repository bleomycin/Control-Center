from django.urls import path
from . import views

app_name = "tasks"

urlpatterns = [
    path("", views.TaskListView.as_view(), name="list"),
    path("export/", views.export_csv, name="export_csv"),
    path("create/", views.TaskCreateView.as_view(), name="create"),
    path("quick-create/", views.quick_create, name="quick_create"),
    path("<int:pk>/", views.TaskDetailView.as_view(), name="detail"),
    path("<int:pk>/pdf/", views.export_pdf_detail, name="export_pdf"),
    path("<int:pk>/edit/", views.TaskUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.TaskDeleteView.as_view(), name="delete"),
    path("<int:pk>/toggle/", views.toggle_complete, name="toggle_complete"),
    path("<int:pk>/kanban-update/", views.kanban_update, name="kanban_update"),
    path("<int:pk>/inline-update/", views.inline_update, name="inline_update"),
    path("<int:pk>/followup/add/", views.followup_add, name="followup_add"),
    path("followup/<int:pk>/edit/", views.followup_edit, name="followup_edit"),
    path("followup/<int:pk>/delete/", views.followup_delete, name="followup_delete"),
    path("followup/<int:pk>/respond/", views.followup_respond, name="followup_respond"),
    path("<int:pk>/inline-subtasks/", views.inline_subtasks, name="inline_subtasks"),
    path("<int:pk>/subtasks/add/", views.subtask_add, name="subtask_add"),
    path("subtask/<int:pk>/toggle/", views.subtask_toggle, name="subtask_toggle"),
    path("subtask/<int:pk>/edit/", views.subtask_edit, name="subtask_edit"),
    path("subtask/<int:pk>/delete/", views.subtask_delete, name="subtask_delete"),
    path("<int:pk>/inline/title/", views.inline_edit_title, name="inline_edit_title"),
    path("<int:pk>/inline/description/", views.inline_edit_description, name="inline_edit_description"),
    path("<int:pk>/inline/metadata/", views.inline_edit_metadata, name="inline_edit_metadata"),
    path("bulk/delete/", views.bulk_delete, name="bulk_delete"),
    path("bulk/export/", views.bulk_export_csv, name="bulk_export_csv"),
    path("bulk/complete/", views.bulk_complete, name="bulk_complete"),
]
