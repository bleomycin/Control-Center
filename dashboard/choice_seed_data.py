"""
Seed data for ChoiceOption model.
Shared between migration 0004 and load_sample_data management command.
"""

SEED_DATA = [
    # Entity types
    ("entity_type", "advisor", "Advisor", 0),
    ("entity_type", "business_partner", "Business Partner", 1),
    ("entity_type", "lender", "Lender", 2),
    ("entity_type", "contact", "Contact", 3),
    ("entity_type", "professional", "Professional", 4),
    ("entity_type", "attorney", "Attorney", 5),
    ("entity_type", "firm", "Firm", 6),
    ("entity_type", "other", "Other", 7),
    # Contact methods
    ("contact_method", "call", "Call", 0),
    ("contact_method", "email", "Email", 1),
    ("contact_method", "text", "Text", 2),
    ("contact_method", "meeting", "Meeting", 3),
    ("contact_method", "other", "Other", 4),
    # Legal matter types
    ("matter_type", "litigation", "Litigation", 0),
    ("matter_type", "compliance", "Compliance", 1),
    ("matter_type", "investigation", "Investigation", 2),
    ("matter_type", "transaction", "Transaction", 3),
    ("matter_type", "other", "Other", 4),
    # Note types
    ("note_type", "call", "Call", 0),
    ("note_type", "email", "Email", 1),
    ("note_type", "meeting", "Meeting", 2),
    ("note_type", "research", "Research", 3),
    ("note_type", "legal_update", "Legal Update", 4),
    ("note_type", "general", "General", 5),
]
