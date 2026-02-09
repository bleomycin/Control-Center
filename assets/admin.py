from django.contrib import admin
from .models import RealEstate, Investment, Loan, PropertyOwnership, InvestmentParticipant, LoanParty


class PropertyOwnershipInline(admin.TabularInline):
    model = PropertyOwnership
    extra = 1
    fields = ["stakeholder", "ownership_percentage", "role", "notes"]


class InvestmentParticipantInline(admin.TabularInline):
    model = InvestmentParticipant
    extra = 1
    fields = ["stakeholder", "ownership_percentage", "role", "notes"]


class LoanPartyInline(admin.TabularInline):
    model = LoanParty
    extra = 1
    fields = ["stakeholder", "ownership_percentage", "role", "notes"]


@admin.register(RealEstate)
class RealEstateAdmin(admin.ModelAdmin):
    list_display = ["name", "address", "property_type", "estimated_value", "status"]
    list_filter = ["status", "property_type", "jurisdiction"]
    search_fields = ["name", "address", "notes_text"]
    inlines = [PropertyOwnershipInline]


@admin.register(Investment)
class InvestmentAdmin(admin.ModelAdmin):
    list_display = ["name", "investment_type", "institution", "current_value"]
    list_filter = ["investment_type", "institution"]
    search_fields = ["name", "institution", "notes_text"]
    inlines = [InvestmentParticipantInline]


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ["name", "current_balance", "interest_rate", "monthly_payment", "next_payment_date", "status"]
    list_filter = ["status"]
    search_fields = ["name", "borrower_description", "collateral", "notes_text"]
    inlines = [LoanPartyInline]
