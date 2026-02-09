from django.urls import path
from . import views

app_name = "stakeholders"

urlpatterns = [
    path("", views.StakeholderListView.as_view(), name="list"),
    path("export/", views.export_csv, name="export_csv"),
    path("create/", views.StakeholderCreateView.as_view(), name="create"),
    path("<int:pk>/", views.StakeholderDetailView.as_view(), name="detail"),
    path("<int:pk>/pdf/", views.export_pdf_detail, name="export_pdf"),
    path("<int:pk>/edit/", views.StakeholderUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.StakeholderDeleteView.as_view(), name="delete"),
    path("<int:pk>/graph-data/", views.relationship_graph_data, name="graph_data"),
    path("<int:pk>/contact-log/add/", views.contact_log_add, name="contact_log_add"),
    path("contact-log/<int:pk>/delete/", views.contact_log_delete, name="contact_log_delete"),
    path("bulk/delete/", views.bulk_delete, name="bulk_delete"),
    path("bulk/export/", views.bulk_export_csv, name="bulk_export_csv"),
]
