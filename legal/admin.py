from django.contrib import admin
from .models import LegalMatter, Evidence


class EvidenceInline(admin.TabularInline):
    model = Evidence
    extra = 0
    fields = ["title", "evidence_type", "date_obtained", "file", "description"]


@admin.register(LegalMatter)
class LegalMatterAdmin(admin.ModelAdmin):
    list_display = ["title", "case_number", "matter_type", "status", "jurisdiction", "filing_date"]
    list_filter = ["matter_type", "status", "jurisdiction"]
    search_fields = ["title", "case_number", "description"]
    filter_horizontal = ["attorneys", "related_stakeholders", "related_properties"]
    inlines = [EvidenceInline]


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ["title", "legal_matter", "evidence_type", "date_obtained"]
    list_filter = ["evidence_type"]
    search_fields = ["title", "description"]
