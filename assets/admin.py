from django.contrib import admin
from .models import RealEstate, Investment, Loan


@admin.register(RealEstate)
class RealEstateAdmin(admin.ModelAdmin):
    list_display = ["name", "address", "property_type", "estimated_value", "status", "stakeholder"]
    list_filter = ["status", "property_type", "jurisdiction"]
    search_fields = ["name", "address", "notes_text"]


@admin.register(Investment)
class InvestmentAdmin(admin.ModelAdmin):
    list_display = ["name", "investment_type", "institution", "current_value", "stakeholder"]
    list_filter = ["investment_type", "institution"]
    search_fields = ["name", "institution", "notes_text"]


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ["name", "lender", "current_balance", "interest_rate", "monthly_payment", "next_payment_date", "status"]
    list_filter = ["status"]
    search_fields = ["name", "borrower_description", "collateral", "notes_text"]
