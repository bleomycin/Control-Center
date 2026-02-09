from django.urls import path
from . import views

app_name = "cashflow"

urlpatterns = [
    path("", views.CashFlowListView.as_view(), name="list"),
    path("charts/data/", views.chart_data, name="chart_data"),
    path("export/", views.export_csv, name="export_csv"),
    path("create/", views.CashFlowCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", views.CashFlowUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.CashFlowDeleteView.as_view(), name="delete"),
    path("bulk/delete/", views.bulk_delete, name="bulk_delete"),
    path("bulk/export/", views.bulk_export_csv, name="bulk_export_csv"),
]
