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
    # Insurance policy types
    ("policy_type", "auto", "Auto", 0),
    ("policy_type", "homeowners", "Homeowners", 1),
    ("policy_type", "commercial_property", "Commercial Property", 2),
    ("policy_type", "aviation", "Aviation", 3),
    ("policy_type", "umbrella", "Umbrella", 4),
    ("policy_type", "liability", "Liability", 5),
    ("policy_type", "life", "Life", 6),
    ("policy_type", "general", "General", 7),
    # Vehicle types
    ("vehicle_type", "sedan", "Sedan", 0),
    ("vehicle_type", "suv", "SUV", 1),
    ("vehicle_type", "truck", "Truck", 2),
    ("vehicle_type", "motorcycle", "Motorcycle", 3),
    ("vehicle_type", "rv", "RV", 4),
    ("vehicle_type", "van", "Van", 5),
    ("vehicle_type", "boat", "Boat", 6),
    ("vehicle_type", "other", "Other", 7),
    # Aircraft types
    ("aircraft_type", "single_engine", "Single Engine", 0),
    ("aircraft_type", "multi_engine", "Multi Engine", 1),
    ("aircraft_type", "turboprop", "Turboprop", 2),
    ("aircraft_type", "jet", "Jet", 3),
    ("aircraft_type", "helicopter", "Helicopter", 4),
    ("aircraft_type", "glider", "Glider", 5),
    # Cash flow categories
    ("cashflow_category", "rental_income", "Rental Income", 0),
    ("cashflow_category", "mortgage", "Mortgage", 1),
    ("cashflow_category", "loan_payment", "Loan Payment", 2),
    ("cashflow_category", "insurance", "Insurance", 3),
    ("cashflow_category", "legal_fees", "Legal Fees", 4),
    ("cashflow_category", "renovation", "Renovation", 5),
    ("cashflow_category", "investment", "Investment", 6),
    ("cashflow_category", "investment_income", "Investment Income", 7),
    ("cashflow_category", "professional_services", "Professional Services", 8),
    ("cashflow_category", "acquisition", "Acquisition", 9),
    ("cashflow_category", "taxes", "Taxes", 10),
    ("cashflow_category", "maintenance", "Maintenance", 11),
    ("cashflow_category", "other", "Other", 12),
    # Lease types
    ("lease_type", "residential", "Residential", 0),
    ("lease_type", "commercial", "Commercial", 1),
    ("lease_type", "industrial", "Industrial", 2),
    ("lease_type", "retail", "Retail", 3),
    ("lease_type", "office", "Office", 4),
    ("lease_type", "ground_lease", "Ground Lease", 5),
    ("lease_type", "sublease", "Sublease", 6),
    ("lease_type", "other", "Other", 7),
]
