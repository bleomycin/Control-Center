from django.contrib import admin
from .models import LegalMatter, Evidence, FirmEngagement, LegalCommunication


class EvidenceInline(admin.TabularInline):
    model = Evidence
    extra = 0
    fields = ["title", "evidence_type", "date_obtained", "file", "url", "description"]


class FirmEngagementInline(admin.TabularInline):
    model = FirmEngagement
    extra = 0
    fields = ["firm", "status", "scope", "initial_contact_date", "referred_by"]


@admin.register(LegalMatter)
class LegalMatterAdmin(admin.ModelAdmin):
    list_display = ["title", "case_number", "matter_type", "status", "jurisdiction", "filing_date", "next_hearing_date"]
    list_filter = ["matter_type", "status", "jurisdiction"]
    search_fields = ["title", "case_number", "description"]
    filter_horizontal = ["attorneys", "related_stakeholders", "related_properties"]
    inlines = [EvidenceInline, FirmEngagementInline]


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ["title", "legal_matter", "evidence_type", "date_obtained", "url"]
    list_filter = ["evidence_type"]
    search_fields = ["title", "description"]


class LegalCommunicationInline(admin.TabularInline):
    model = LegalCommunication
    extra = 0
    fields = ["date", "direction", "method", "stakeholder", "summary", "follow_up_needed", "follow_up_date"]


@admin.register(LegalCommunication)
class LegalCommunicationAdmin(admin.ModelAdmin):
    list_display = ["legal_matter", "date", "direction", "method", "stakeholder", "follow_up_needed"]
    list_filter = ["direction", "method", "follow_up_needed"]
    search_fields = ["summary"]


@admin.register(FirmEngagement)
class FirmEngagementAdmin(admin.ModelAdmin):
    list_display = ["legal_matter", "firm", "status", "initial_contact_date", "referred_by"]
    list_filter = ["status"]
    search_fields = ["firm__name", "scope"]
