from django.urls import path
from . import views

app_name = "cashflow"

urlpatterns = [
    path("", views.CashFlowListView.as_view(), name="list"),
    path("charts/data/", views.chart_data, name="chart_data"),
    path("export/", views.export_csv, name="export_csv"),
    path("create/", views.CashFlowCreateView.as_view(), name="create"),
    path("<int:pk>/", views.CashFlowDetailView.as_view(), name="detail"),
    path("<int:pk>/pdf/", views.export_pdf_detail, name="export_pdf"),
    path("<int:pk>/edit/", views.CashFlowUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.CashFlowDeleteView.as_view(), name="delete"),
    path("bulk/delete/", views.bulk_delete, name="bulk_delete"),
    path("bulk/export/", views.bulk_export_csv, name="bulk_export_csv"),
    # Inline cashflow for detail pages
    path("property/<int:pk>/add/", views.property_cashflow_add, name="property_cashflow_add"),
    path("property/<int:pk>/delete/", views.property_cashflow_delete, name="property_cashflow_delete"),
    path("loan/<int:pk>/add/", views.loan_cashflow_add, name="loan_cashflow_add"),
    path("loan/<int:pk>/delete/", views.loan_cashflow_delete, name="loan_cashflow_delete"),
    path("investment/<int:pk>/add/", views.investment_cashflow_add, name="investment_cashflow_add"),
    path("investment/<int:pk>/delete/", views.investment_cashflow_delete, name="investment_cashflow_delete"),
    path("stakeholder/<int:pk>/add/", views.stakeholder_cashflow_add, name="stakeholder_cashflow_add"),
    path("stakeholder/<int:pk>/delete/", views.stakeholder_cashflow_delete, name="stakeholder_cashflow_delete"),
]
