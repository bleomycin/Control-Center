from django.urls import path
from . import views

app_name = "cashflow"

urlpatterns = [
    path("", views.CashFlowListView.as_view(), name="list"),
    path("charts/data/", views.chart_data, name="chart_data"),
    path("export/", views.export_csv, name="export_csv"),
    path("export/pdf/", views.export_pdf, name="export_pdf"),
    path("create/", views.CashFlowCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", views.CashFlowUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.CashFlowDeleteView.as_view(), name="delete"),
]
