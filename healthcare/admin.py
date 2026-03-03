from django.contrib import admin
from .models import (Advice, Appointment, Condition, HealthcareTab, Prescription,
                     Provider, Supplement, TestResult, Visit)


@admin.register(HealthcareTab)
class HealthcareTabAdmin(admin.ModelAdmin):
    list_display = ["label", "key", "sort_order", "is_builtin"]
    list_filter = ["is_builtin"]


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ["name", "provider_type", "specialty", "practice_name", "status"]
    list_filter = ["status", "provider_type"]
    search_fields = ["name", "specialty", "practice_name", "npi"]


@admin.register(Condition)
class ConditionAdmin(admin.ModelAdmin):
    list_display = ["name", "icd_code", "status", "severity", "diagnosed_date"]
    list_filter = ["status", "severity"]
    search_fields = ["name", "icd_code"]


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ["medication_name", "generic_name", "dosage", "frequency", "status", "prescribing_provider"]
    list_filter = ["status", "is_controlled"]
    search_fields = ["medication_name", "generic_name", "rx_number"]


@admin.register(Supplement)
class SupplementAdmin(admin.ModelAdmin):
    list_display = ["name", "brand", "dosage", "frequency", "status"]
    list_filter = ["status"]
    search_fields = ["name", "brand"]


@admin.register(TestResult)
class TestResultAdmin(admin.ModelAdmin):
    list_display = ["test_name", "test_type", "date", "status", "ordering_provider"]
    list_filter = ["status", "test_type"]
    search_fields = ["test_name", "facility", "result_summary"]


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ["__str__", "visit_type", "date", "provider", "facility"]
    list_filter = ["visit_type"]
    search_fields = ["reason", "diagnosis", "summary", "facility"]


@admin.register(Advice)
class AdviceAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "status", "date", "given_by"]
    list_filter = ["category", "status"]
    search_fields = ["title", "advice_text"]


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ["title", "date", "time", "provider", "status", "visit_type"]
    list_filter = ["status", "visit_type"]
    search_fields = ["title", "purpose", "facility"]
