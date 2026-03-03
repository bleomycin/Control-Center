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
    path("evidence/<int:pk>/delete/", views.evidence_delete, name="evidence_delete"),
]
