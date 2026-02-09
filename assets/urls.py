from django.urls import path
from . import views

app_name = "assets"

urlpatterns = [
    # Real Estate
    path("real-estate/", views.RealEstateListView.as_view(), name="realestate_list"),
    path("real-estate/export/", views.export_realestate_csv, name="realestate_export_csv"),
    path("real-estate/create/", views.RealEstateCreateView.as_view(), name="realestate_create"),
    path("real-estate/<int:pk>/", views.RealEstateDetailView.as_view(), name="realestate_detail"),
    path("real-estate/<int:pk>/pdf/", views.export_pdf_realestate_detail, name="realestate_export_pdf"),
    path("real-estate/<int:pk>/edit/", views.RealEstateUpdateView.as_view(), name="realestate_edit"),
    path("real-estate/<int:pk>/delete/", views.RealEstateDeleteView.as_view(), name="realestate_delete"),
    # Investments
    path("investments/", views.InvestmentListView.as_view(), name="investment_list"),
    path("investments/export/", views.export_investment_csv, name="investment_export_csv"),
    path("investments/create/", views.InvestmentCreateView.as_view(), name="investment_create"),
    path("investments/<int:pk>/", views.InvestmentDetailView.as_view(), name="investment_detail"),
    path("investments/<int:pk>/pdf/", views.export_pdf_investment_detail, name="investment_export_pdf"),
    path("investments/<int:pk>/edit/", views.InvestmentUpdateView.as_view(), name="investment_edit"),
    path("investments/<int:pk>/delete/", views.InvestmentDeleteView.as_view(), name="investment_delete"),
    # Loans
    path("loans/", views.LoanListView.as_view(), name="loan_list"),
    path("loans/export/", views.export_loan_csv, name="loan_export_csv"),
    path("loans/create/", views.LoanCreateView.as_view(), name="loan_create"),
    path("loans/<int:pk>/", views.LoanDetailView.as_view(), name="loan_detail"),
    path("loans/<int:pk>/pdf/", views.export_pdf_loan_detail, name="loan_export_pdf"),
    path("loans/<int:pk>/edit/", views.LoanUpdateView.as_view(), name="loan_edit"),
    path("loans/<int:pk>/delete/", views.LoanDeleteView.as_view(), name="loan_delete"),
]
