from django.urls import path
from . import views

app_name = "assets"

urlpatterns = [
    # Unified asset list
    path("", views.asset_list, name="asset_list"),
    # Asset tab settings
    path("tabs/", views.asset_tab_settings, name="asset_tab_settings"),
    path("tabs/add/", views.asset_tab_add, name="asset_tab_add"),
    path("tabs/<int:pk>/edit/", views.asset_tab_edit, name="asset_tab_edit"),
    path("tabs/<int:pk>/delete/", views.asset_tab_delete, name="asset_tab_delete"),
    # Real Estate
    path("real-estate/", views.RealEstateListView.as_view(), name="realestate_list"),
    path("real-estate/<int:pk>/inline-status/", views.inline_update_realestate_status, name="realestate_inline_status"),
    path("real-estate/export/", views.export_realestate_csv, name="realestate_export_csv"),
    path("real-estate/create/", views.RealEstateCreateView.as_view(), name="realestate_create"),
    path("real-estate/<int:pk>/", views.RealEstateDetailView.as_view(), name="realestate_detail"),
    path("real-estate/<int:pk>/pdf/", views.export_pdf_realestate_detail, name="realestate_export_pdf"),
    path("real-estate/<int:pk>/edit/", views.RealEstateUpdateView.as_view(), name="realestate_edit"),
    path("real-estate/<int:pk>/delete/", views.RealEstateDeleteView.as_view(), name="realestate_delete"),
    path("real-estate/<int:pk>/ownership/add/", views.ownership_add, name="ownership_add"),
    path("ownership/<int:pk>/delete/", views.ownership_delete, name="ownership_delete"),
    path("real-estate/bulk/delete/", views.bulk_delete_realestate, name="realestate_bulk_delete"),
    path("real-estate/bulk/export/", views.bulk_export_realestate_csv, name="realestate_bulk_export_csv"),
    # Investments
    path("investments/", views.InvestmentListView.as_view(), name="investment_list"),
    path("investments/export/", views.export_investment_csv, name="investment_export_csv"),
    path("investments/create/", views.InvestmentCreateView.as_view(), name="investment_create"),
    path("investments/<int:pk>/", views.InvestmentDetailView.as_view(), name="investment_detail"),
    path("investments/<int:pk>/pdf/", views.export_pdf_investment_detail, name="investment_export_pdf"),
    path("investments/<int:pk>/edit/", views.InvestmentUpdateView.as_view(), name="investment_edit"),
    path("investments/<int:pk>/delete/", views.InvestmentDeleteView.as_view(), name="investment_delete"),
    path("investments/<int:pk>/participant/add/", views.participant_add, name="participant_add"),
    path("participant/<int:pk>/delete/", views.participant_delete, name="participant_delete"),
    path("investments/bulk/delete/", views.bulk_delete_investment, name="investment_bulk_delete"),
    path("investments/bulk/export/", views.bulk_export_investment_csv, name="investment_bulk_export_csv"),
    # Loans
    path("loans/", views.LoanListView.as_view(), name="loan_list"),
    path("loans/<int:pk>/inline-status/", views.inline_update_loan_status, name="loan_inline_status"),
    path("loans/export/", views.export_loan_csv, name="loan_export_csv"),
    path("loans/create/", views.LoanCreateView.as_view(), name="loan_create"),
    path("loans/<int:pk>/", views.LoanDetailView.as_view(), name="loan_detail"),
    path("loans/<int:pk>/pdf/", views.export_pdf_loan_detail, name="loan_export_pdf"),
    path("loans/<int:pk>/edit/", views.LoanUpdateView.as_view(), name="loan_edit"),
    path("loans/<int:pk>/delete/", views.LoanDeleteView.as_view(), name="loan_delete"),
    path("loans/<int:pk>/party/add/", views.loan_party_add, name="loan_party_add"),
    path("party/<int:pk>/delete/", views.loan_party_delete, name="loan_party_delete"),
    path("loans/bulk/delete/", views.bulk_delete_loan, name="loan_bulk_delete"),
    path("loans/bulk/export/", views.bulk_export_loan_csv, name="loan_bulk_export_csv"),
    # Insurance Policies
    path("policies/", views.InsurancePolicyListView.as_view(), name="policy_list"),
    path("policies/<int:pk>/inline-status/", views.inline_update_policy_status, name="policy_inline_status"),
    path("policies/export/", views.export_policy_csv, name="policy_export_csv"),
    path("policies/create/", views.InsurancePolicyCreateView.as_view(), name="policy_create"),
    path("policies/<int:pk>/", views.InsurancePolicyDetailView.as_view(), name="policy_detail"),
    path("policies/<int:pk>/pdf/", views.export_pdf_policy_detail, name="policy_export_pdf"),
    path("policies/<int:pk>/edit/", views.InsurancePolicyUpdateView.as_view(), name="policy_edit"),
    path("policies/<int:pk>/delete/", views.InsurancePolicyDeleteView.as_view(), name="policy_delete"),
    path("policies/<int:pk>/policyholder/add/", views.policyholder_add, name="policyholder_add"),
    path("policyholder/<int:pk>/delete/", views.policyholder_delete, name="policyholder_delete"),
    path("policies/bulk/delete/", views.bulk_delete_policy, name="policy_bulk_delete"),
    path("policies/bulk/export/", views.bulk_export_policy_csv, name="policy_bulk_export_csv"),
]
