from django.urls import path
from . import views

app_name = "legal"

urlpatterns = [
    path("", views.LegalMatterListView.as_view(), name="list"),
    path("export/", views.export_csv, name="export_csv"),
    path("create/", views.LegalMatterCreateView.as_view(), name="create"),
    path("<int:pk>/", views.LegalMatterDetailView.as_view(), name="detail"),
    path("<int:pk>/pdf/", views.export_pdf_detail, name="export_pdf"),
    path("<int:pk>/edit/", views.LegalMatterUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.LegalMatterDeleteView.as_view(), name="delete"),
    path("<int:pk>/evidence/add/", views.evidence_add, name="evidence_add"),
    path("evidence/<int:pk>/edit/", views.evidence_edit, name="evidence_edit"),
    path("evidence/<int:pk>/delete/", views.evidence_delete, name="evidence_delete"),
    path("<int:pk>/activity/", views.activity_list, name="activity_list"),
    path("<int:pk>/communications/add/", views.communication_add, name="communication_add"),
    path("communications/<int:pk>/edit/", views.communication_edit, name="communication_edit"),
    path("communications/<int:pk>/delete/", views.communication_delete, name="communication_delete"),
    path("communications/<int:pk>/toggle-followup/", views.communication_toggle_followup, name="communication_toggle_followup"),
    path("bulk/delete/", views.bulk_delete, name="bulk_delete"),
    path("bulk/export/", views.bulk_export_csv, name="bulk_export_csv"),
    path("<int:pk>/checklist/add/", views.checklist_add, name="checklist_add"),
    path("checklist/<int:pk>/toggle/", views.checklist_toggle, name="checklist_toggle"),
    path("checklist/<int:pk>/edit/", views.checklist_edit, name="checklist_edit"),
    path("checklist/<int:pk>/delete/", views.checklist_delete, name="checklist_delete"),
    path("<int:pk>/case-logs/add/", views.case_log_add, name="case_log_add"),
    path("case-logs/<int:pk>/edit/", views.case_log_edit, name="case_log_edit"),
    path("case-logs/<int:pk>/delete/", views.case_log_delete, name="case_log_delete"),
    path("<int:pk>/related/link/", views.related_entity_link, name="related_entity_link"),
    path("<int:pk>/related/unlink/", views.related_entity_unlink, name="related_entity_unlink"),
    path("<int:pk>/related/options/", views.related_entity_options, name="related_entity_options"),
]
