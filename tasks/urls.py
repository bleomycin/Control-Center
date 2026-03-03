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
    path("<int:pk>/followup/add/", views.followup_add, name="followup_add"),
    path("followup/<int:pk>/delete/", views.followup_delete, name="followup_delete"),
]
