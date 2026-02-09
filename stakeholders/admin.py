from django.contrib import admin
from .models import Stakeholder, Relationship, ContactLog


class ContactLogInline(admin.TabularInline):
    model = ContactLog
    extra = 0
    fields = ["date", "method", "summary", "follow_up_needed", "follow_up_date"]


class RelationshipFromInline(admin.TabularInline):
    model = Relationship
    fk_name = "from_stakeholder"
    extra = 0
    verbose_name = "Relationship (outgoing)"
    verbose_name_plural = "Relationships (outgoing)"


@admin.register(Stakeholder)
class StakeholderAdmin(admin.ModelAdmin):
    list_display = ["name", "entity_type", "organization", "email", "phone", "trust_rating", "risk_rating"]
    list_filter = ["entity_type", "trust_rating", "risk_rating"]
    search_fields = ["name", "email", "organization", "notes_text"]
    inlines = [ContactLogInline, RelationshipFromInline]


@admin.register(Relationship)
class RelationshipAdmin(admin.ModelAdmin):
    list_display = ["from_stakeholder", "to_stakeholder", "relationship_type"]
    list_filter = ["relationship_type"]
    search_fields = ["from_stakeholder__name", "to_stakeholder__name", "relationship_type", "description"]


@admin.register(ContactLog)
class ContactLogAdmin(admin.ModelAdmin):
    list_display = ["stakeholder", "date", "method", "follow_up_needed", "follow_up_date"]
    list_filter = ["method", "follow_up_needed"]
    search_fields = ["stakeholder__name", "summary"]
