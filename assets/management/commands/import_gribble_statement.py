"""
Import data from Stanley W. Gribble Statement of Financial Condition (Dec 31, 2024).

Creates stakeholders (entities/LLCs), real estate, aircraft, investments, and loans
with full ownership linkages. All operations are idempotent via get_or_create.
Each record's notes_text contains the full verbatim text from the corresponding
PDF note for context.

Usage:
    python manage.py import_gribble_statement
    python manage.py import_gribble_statement --dry-run
    python manage.py import_gribble_statement --update   # update notes on existing records
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from assets.models import (
    Aircraft,
    AircraftOwner,
    Investment,
    InvestmentParticipant,
    Loan,
    LoanParty,
    PropertyOwnership,
    RealEstate,
)
from dashboard.choices import invalidate_choice_cache
from stakeholders.models import Stakeholder

SWG_NAME = "Stanley W. Gribble"


# ── Entities / LLCs ──────────────────────────────────────────────────────────
#
# Each entity's notes_text contains the full verbatim text from the
# corresponding PDF note.

ENTITIES = [
    # (name, entity_type, ownership_pct by SWG, notes_text)
    (
        SWG_NAME, "contact", None,
        "STANLEY W. GRIBBLE — NOTES TO STATEMENT OF FINANCIAL CONDITION "
        "AS OF DECEMBER 31, 2024\n\n"
        "SUMMARY OF SIGNIFICANT ACCOUNTING POLICIES\n\n"
        "The accompanying statements of financial condition includes the assets "
        "and liabilities of Stanley W. Gribble presented at their estimated "
        "current market values provided by the client.\n\n"
        "NOTE 19 — INCOME TAX LIABILITY\n\n"
        "At 12/31/24 Stanley W. Gribble has federal and state tax liabilities "
        "of $5,920,700."
    ),
    (
        "Huntington Oaks Associates, LP", "entity", Decimal("93"),
        "NOTE 1 — INVESTMENT IN HUNTINGTON OAKS ASSOCIATES, LP\n\n"
        "Huntington Oaks Associates, LP is a Partnership owned 93% by Stanley "
        "W. Gribble. The property sold October 2024."
    ),
    (
        "Arcadia Gateway Centre, LP", "entity", Decimal("100"),
        "NOTE 2 — INVESTMENT IN ARCADIA GATEWAY CENTRE, LP\n\n"
        "Arcadia Gateway Centre, LP and Arcadia Gateway Centre Associates, LTD "
        "is owned 100% by Stanley W. Gribble. Both entities hold a 100% "
        "investment in CVS Store Leases. Arcadia Gateway Centre, LP hold seven "
        "CVS Stores and Arcadia Gateway Centre Associates, LTD holds thirteen "
        "CVS Stores located in various States. The investment values are "
        "reported at their acquisition cost, net of land loans and Section 467 "
        "loans:\n\n"
        "Arcadia Gateway Centre, LP:\n"
        "  CVS Purchase Price: $25,233,504\n"
        "  CVS Land Loan: ($17,308,974)\n"
        "  CVS S467 Loan: ($3,569,742)\n"
        "  Net Estimated Value: $4,354,788"
    ),
    (
        "Arcadia Gateway Centre Associates, LTD", "entity", Decimal("100"),
        "NOTE 2 — INVESTMENT IN ARCADIA GATEWAY CENTRE ASSOCIATES, LTD\n\n"
        "Arcadia Gateway Centre, LP and Arcadia Gateway Centre Associates, LTD "
        "is owned 100% by Stanley W. Gribble. Both entities hold a 100% "
        "investment in CVS Store Leases. Arcadia Gateway Centre, LP hold seven "
        "CVS Stores and Arcadia Gateway Centre Associates, LTD holds thirteen "
        "CVS Stores located in various States. The investment values are "
        "reported at their acquisition cost, net of land loans and Section 467 "
        "loans:\n\n"
        "Arcadia Gateway Centre Associates, LTD:\n"
        "  CVS Purchase Price: $41,199,433\n"
        "  CVS Land Loan: ($27,813,716)\n"
        "  CVS S467 Loan: ($5,916,266)\n"
        "  Net Estimated Value: $7,469,451"
    ),
    (
        "Bend Properties, Inc.", "entity", Decimal("100"),
        "NOTE 3 — BEND PROPERTIES, INC.\n\n"
        "Bend Properties, Inc. is owned 100% by Stanley W. Gribble. The "
        "corporate assets include cash and cash alternatives of $11,046,909."
    ),
    (
        "314SG, LLC", "entity", Decimal("100"),
        "NOTE 4 — 314 SG, LLC\n\n"
        "314SG, LLC is owned 100% by Stanley W. Gribble, and it is composed "
        "of a cash account and various investments in commercial properties "
        "with Equitas Investment, LLC. The valuation of these commercial "
        "properties are presented at capital investment value, plus accrued "
        "preferred return and percentage of equity ownership at December 31, "
        "2024. Three properties sold during 2024.\n\n"
        "Bank of America Cash: $713,651\n"
        "Equitas Managed Bank Cash: $811,373\n"
        "Commercial Properties: $34,653,468\n"
        "Total: $36,178,492"
    ),
    (
        "G4SP, LLC", "entity", Decimal("100"),
        "NOTE 5 — G4SP, LLC\n\n"
        "G4SP, LLC owns a Gulfstream GIV-SP N15Y passenger aircraft. The "
        "aircraft sold July 2024."
    ),
    (
        "Pecos Properties, LP", "entity", Decimal("100"),
        "NOTE 6 — PECOS PROPERTIES, LP\n\n"
        "Pecos Properties, LP is owned 100% by Stanley W. Gribble, and is "
        "composed of nine CVS Stores Leases located in Georgia (3), Florida "
        "(4), Maryland (1), and North Carolina (1). Pecos Properties, LP CVS "
        "investments are valued at acquisition cost of $26,539,443, net of a "
        "land loan of $7,496,049 and Sec. 467 loan $4,027,200.\n\n"
        "Pecos Properties, LP also holds a bank account with a balance of "
        "$237,473.\n\n"
        "Cash Account: $237,473\n"
        "CVS Investments: $15,016,194\n"
        "Total: $15,253,667"
    ),
    (
        "Bend Gucci Exchange, LLC", "entity", Decimal("100"),
        "NOTE 6 — BEND GUCCI EXCHANGE, LLC\n\n"
        "Bend Gucci Exchange, LLC is owned 100% by Stanley W. Gribble. Bend "
        "Gucci Exchange, LLC owns investment in twenty CVS Drug Store leases. "
        "The total investment is valued at the total acquisition cost of "
        "$56,825,131, net of a land loan in the amount of $29,456,626 and "
        "Sec. 467 Loans in the amount of $8,155,572.\n\n"
        "Bend Gucci Exchange, LLC also holds a bank account with a cash "
        "balance of $45,522.\n\n"
        "Cash Account: $45,522\n"
        "CVS: $19,212,933\n"
        "Net Investment Value: $19,258,455"
    ),
    (
        "Gondola Vista, LLC", "entity", Decimal("70"),
        "NOTE 7 — GONDOLA VISTA, LLC\n\n"
        "Gondola Vista, LLC is owned 70% by Stanley W. Gribble and consists "
        "of 10 duplexes, or 20 unites in Lake Tahoe. The estimated fair "
        "market value at December 31, 2025 of the investment is $33,250,000, "
        "net of debt and is computed on the aggregated retail sales potential. "
        "Stanley W. Gribble's share of the investment is valued at "
        "$23,275,000, 70% of $33,250,000. In August 2025, Gondola Vista, LLC "
        "entered into foreclosure proceedings and is currently being litigated."
    ),
    (
        "Freedom Ranch Development Co, LLC", "entity", Decimal("50"),
        "NOTE 8 — FREEDOM RANCH DEVELOPMENT CO, LLC\n\n"
        "Freedom Ranch Development Company, LLC is owned 50% by Stanley W. "
        "Gribble. It is a real estate development currently building homes. "
        "Freedom Ranch Development Co, LLC entered into litigation with the "
        "homeowners and the underlying property was transferred out of the "
        "entity as part of the settlement early 2025."
    ),
    (
        "SWG Kortum, LLC", "entity", Decimal("100"),
        "NOTE 10 — SWG KORTUM, LLC\n\n"
        "SWG Kortum, LLC is owned 100% by Stan W. Gribble. The underlying "
        "investment is undeveloped land in Calistoga, CA which is being "
        "entitled for development. The investment estimated fair market value "
        "is reported at a net cost basis of $3,874,380."
    ),
    (
        "SG550, LLC", "entity", Decimal("100"),
        "NOTE 11 — SG550, LLC\n\n"
        "SG550, LLC owned a Gulfstream passenger aircraft. It was sold "
        "February 2024."
    ),
    (
        "Bend Capfund, LLC", "entity", Decimal("100"),
        "NOTE 12 — BEND CAPFUND, LLC\n\n"
        "Bend Capfund, LLC is owned 100% by Stan W. Gribble. Bend Capfund, "
        "LLC owns a 53% interest in Charlinda Mission Viejo, LLC. Charlinda "
        "Mission Viejo, LLC owns a 11,704 sq ft commercial property that is "
        "being leased. The investment is valued at a fair market value of "
        "$2,548,627."
    ),
    (
        "Festival Keller, LLC", "entity", Decimal("30"),
        "NOTE 13 — FESTIVAL KELLER, LLC\n\n"
        "Festival Keller, LLC is effectively owned 30% by Stan W. Gribble. "
        "Festival Keller, LLC owns a commercial property in Santa Monica, CA. "
        "The property is held out for lease and only 200 sq ft out of 19,725 "
        "sq ft is occupied. The investment is valued at $600,000, net of debt."
    ),
    (
        "N888GM, LLC", "entity", Decimal("100"),
        "NOTE 14 — N888GM, LLC\n\n"
        "N888GM, LLC owns a Gulfstream G600 passenger aircraft. The aircraft "
        "is currently used in air charter operations. The fair market value of "
        "this aircraft is valued at $4,641,881, net of debt, per the broker."
    ),
    (
        "N885GM, LLC", "entity", Decimal("100"),
        "NOTE 20 — N885GM, LLC\n\n"
        "N885GM, LLC holds a loan with UBS for the aircraft owned by SG550, "
        "LLC. The loan balance has been paid in full as of 02/29/2024 when "
        "the aircraft has been sold."
    ),
    (
        "Axis Research and Technology", "business_partner", None,
        "NOTE 21 — AXIS RESEARCH AND TECHNOLOGY\n\n"
        "Stanley W. Gribble has $18,000,000 stock in Axis Research and "
        "Technology and a convertible note valued at $500,000 with a "
        "$8,678.08 interest receivable."
    ),
]


# ── Real Estate ──────────────────────────────────────────────────────────────

PROPERTIES = [
    # NOTE 1 — Huntington Oaks Associates, LP (sold)
    {
        "name": "Huntington Oaks Associates, LP — Investment Property",
        "address": "Huntington Oaks (Partnership property)",
        "property_type": "Commercial",
        "estimated_value": None,
        "status": "sold",
        "owner_entity": "Huntington Oaks Associates, LP",
        "owner_pct": Decimal("93"),
        "notes_text": (
            "NOTE 1 — INVESTMENT IN HUNTINGTON OAKS ASSOCIATES, LP\n\n"
            "Huntington Oaks Associates, LP is a Partnership owned 93% by "
            "Stanley W. Gribble. The property sold October 2024."
        ),
    },
    # NOTE 2 — Arcadia Gateway Centre, LP (CVS stores)
    {
        "name": "CVS Store Investments — Arcadia Gateway Centre, LP",
        "address": "Various locations (Arcadia Gateway Centre, LP portfolio)",
        "property_type": "Commercial",
        "estimated_value": Decimal("4354788"),
        "status": "owned",
        "owner_entity": "Arcadia Gateway Centre, LP",
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 2 — INVESTMENT IN ARCADIA GATEWAY CENTRE, LP\n\n"
            "Arcadia Gateway Centre, LP and Arcadia Gateway Centre Associates, "
            "LTD is owned 100% by Stanley W. Gribble. Both entities hold a "
            "100% investment in CVS Store Leases. Arcadia Gateway Centre, LP "
            "hold seven CVS Stores and Arcadia Gateway Centre Associates, LTD "
            "holds thirteen CVS Stores located in various States. The "
            "investment values are reported at their acquisition cost, net of "
            "land loans and Section 467 loans:\n\n"
            "Arcadia Gateway Centre, LP:\n"
            "  CVS Purchase Price: $25,233,504\n"
            "  CVS Land Loan: ($17,308,974)\n"
            "  CVS S467 Loan: ($3,569,742)\n"
            "  Net Estimated Value: $4,354,788"
        ),
    },
    # NOTE 2 — Arcadia Gateway Centre Associates, LTD (CVS stores)
    {
        "name": "CVS Store Investments — Arcadia Gateway Centre Associates, LTD",
        "address": "Various locations (Arcadia Gateway Centre Associates, LTD portfolio)",
        "property_type": "Commercial",
        "estimated_value": Decimal("7469451"),
        "status": "owned",
        "owner_entity": "Arcadia Gateway Centre Associates, LTD",
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 2 — INVESTMENT IN ARCADIA GATEWAY CENTRE ASSOCIATES, LTD\n\n"
            "Arcadia Gateway Centre, LP and Arcadia Gateway Centre Associates, "
            "LTD is owned 100% by Stanley W. Gribble. Both entities hold a "
            "100% investment in CVS Store Leases. Arcadia Gateway Centre, LP "
            "hold seven CVS Stores and Arcadia Gateway Centre Associates, LTD "
            "holds thirteen CVS Stores located in various States. The "
            "investment values are reported at their acquisition cost, net of "
            "land loans and Section 467 loans:\n\n"
            "Arcadia Gateway Centre Associates, LTD:\n"
            "  CVS Purchase Price: $41,199,433\n"
            "  CVS Land Loan: ($27,813,716)\n"
            "  CVS S467 Loan: ($5,916,266)\n"
            "  Net Estimated Value: $7,469,451"
        ),
    },
    # NOTE 6 — Pecos Properties, LP (CVS leases)
    {
        "name": "CVS Store Leases — Pecos Properties, LP",
        "address": "Various locations — Georgia (3), Florida (4), Maryland (1), North Carolina (1)",
        "property_type": "Commercial",
        "estimated_value": Decimal("15016194"),
        "status": "owned",
        "owner_entity": "Pecos Properties, LP",
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 6 — PECOS PROPERTIES, LP\n\n"
            "Pecos Properties, LP is owned 100% by Stanley W. Gribble, and is "
            "composed of nine CVS Stores Leases located in Georgia (3), "
            "Florida (4), Maryland (1), and North Carolina (1). Pecos "
            "Properties, LP CVS investments are valued at acquisition cost of "
            "$26,539,443, net of a land loan of $7,496,049 and Sec. 467 loan "
            "$4,027,200.\n\n"
            "Pecos Properties, LP also holds a bank account with a balance of "
            "$237,473.\n\n"
            "Cash Account: $237,473\n"
            "CVS Investments: $15,016,194\n"
            "Total: $15,253,667"
        ),
    },
    # NOTE 6 — Bend Gucci Exchange, LLC (CVS leases)
    {
        "name": "CVS Drug Store Leases — Bend Gucci Exchange, LLC",
        "address": "Various locations — 9 states (20 CVS Drug Store lease investments)",
        "property_type": "Commercial",
        "estimated_value": Decimal("19212933"),
        "status": "owned",
        "owner_entity": "Bend Gucci Exchange, LLC",
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 6 — BEND GUCCI EXCHANGE, LLC\n\n"
            "Bend Gucci Exchange, LLC is owned 100% by Stanley W. Gribble. "
            "Bend Gucci Exchange, LLC owns investment in twenty CVS Drug Store "
            "leases. The total investment is valued at the total acquisition "
            "cost of $56,825,131, net of a land loan in the amount of "
            "$29,456,626 and Sec. 467 Loans in the amount of $8,155,572.\n\n"
            "Bend Gucci Exchange, LLC also holds a bank account with a cash "
            "balance of $45,522.\n\n"
            "Cash Account: $45,522\n"
            "CVS: $19,212,933\n"
            "Net Investment Value: $19,258,455"
        ),
    },
    # NOTE 7 — Gondola Vista, LLC (10 duplexes)
    {
        "name": "10 Duplexes — Lake Tahoe",
        "address": "Lake Tahoe, NV (10 duplexes, 20 units)",
        "property_type": "Residential",
        "estimated_value": Decimal("33250000"),
        "status": "in_dispute",
        "owner_entity": "Gondola Vista, LLC",
        "owner_pct": Decimal("70"),
        "notes_text": (
            "NOTE 7 — GONDOLA VISTA, LLC\n\n"
            "Gondola Vista, LLC is owned 70% by Stanley W. Gribble and "
            "consists of 10 duplexes, or 20 unites in Lake Tahoe. The "
            "estimated fair market value at December 31, 2025 of the "
            "investment is $33,250,000, net of debt and is computed on the "
            "aggregated retail sales potential. Stanley W. Gribble's share of "
            "the investment is valued at $23,275,000, 70% of $33,250,000. In "
            "August 2025, Gondola Vista, LLC entered into foreclosure "
            "proceedings and is currently being litigated."
        ),
    },
    # NOTE 8 — Freedom Ranch Development Co, LLC
    {
        "name": "Freedom Ranch Development",
        "address": "Freedom Ranch (real estate development)",
        "property_type": "Land",
        "estimated_value": None,
        "status": "sold",
        "owner_entity": "Freedom Ranch Development Co, LLC",
        "owner_pct": Decimal("50"),
        "notes_text": (
            "NOTE 8 — FREEDOM RANCH DEVELOPMENT CO, LLC\n\n"
            "Freedom Ranch Development Company, LLC is owned 50% by Stanley "
            "W. Gribble. It is a real estate development currently building "
            "homes. Freedom Ranch Development Co, LLC entered into litigation "
            "with the homeowners and the underlying property was transferred "
            "out of the entity as part of the settlement early 2025."
        ),
    },
    # NOTE 9 — Clear Creek Lots
    {
        "name": "Clear Creek Lots",
        "address": "Clear Creek, NV (5 lots)",
        "property_type": "Land",
        "estimated_value": Decimal("2395000"),
        "status": "owned",
        "owner_entity": None,  # Direct SWG ownership
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 9 — CLEAR CREEK LOTS\n\n"
            "Stanley W. Gribble owns five lots in Clear Creek Nevada. The lots "
            "are being developed into single family homes. The investment "
            "estimated market value based on the value of the finished homes "
            "of $3,659,500. In 2025, various lots have been liquidated in the "
            "amount of $1,264,500 and thus the remaining asset is valued at "
            "$2,395,000."
        ),
    },
    # NOTE 10 — SWG Kortum, LLC
    {
        "name": "Undeveloped Land — Calistoga, CA",
        "address": "Calistoga, CA (undeveloped land)",
        "property_type": "Land",
        "estimated_value": Decimal("3874380"),
        "status": "owned",
        "owner_entity": "SWG Kortum, LLC",
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 10 — SWG KORTUM, LLC\n\n"
            "SWG Kortum, LLC is owned 100% by Stan W. Gribble. The underlying "
            "investment is undeveloped land in Calistoga, CA which is being "
            "entitled for development. The investment estimated fair market "
            "value is reported at a net cost basis of $3,874,380."
        ),
    },
    # NOTE 12 — Bend Capfund, LLC (Charlinda Mission Viejo)
    {
        "name": "Charlinda Mission Viejo",
        "address": "Mission Viejo, CA (11,704 sq ft commercial)",
        "property_type": "Commercial",
        "estimated_value": Decimal("2548627"),
        "status": "owned",
        "owner_entity": "Bend Capfund, LLC",
        "owner_pct": Decimal("53"),
        "notes_text": (
            "NOTE 12 — BEND CAPFUND, LLC\n\n"
            "Bend Capfund, LLC is owned 100% by Stan W. Gribble. Bend "
            "Capfund, LLC owns a 53% interest in Charlinda Mission Viejo, "
            "LLC. Charlinda Mission Viejo, LLC owns a 11,704 sq ft commercial "
            "property that is being leased. The investment is valued at a fair "
            "market value of $2,548,627."
        ),
    },
    # NOTE 13 — Festival Keller, LLC (Santa Monica)
    {
        "name": "Commercial Property — Santa Monica",
        "address": "Santa Monica, CA (19,725 sq ft commercial)",
        "property_type": "Commercial",
        "estimated_value": Decimal("600000"),
        "status": "owned",
        "owner_entity": "Festival Keller, LLC",
        "owner_pct": Decimal("30"),
        "notes_text": (
            "NOTE 13 — FESTIVAL KELLER, LLC\n\n"
            "Festival Keller, LLC is effectively owned 30% by Stan W. "
            "Gribble. Festival Keller, LLC owns a commercial property in "
            "Santa Monica, CA. The property is held out for lease and only "
            "200 sq ft out of 19,725 sq ft is occupied. The investment is "
            "valued at $600,000, net of debt."
        ),
    },
    # NOTE 15 — Los Cabos boat/fuel dock
    {
        "name": "Boat & Fuel Dock — Los Cabos, Mexico",
        "address": "Los Cabos, Mexico",
        "property_type": "Other",
        "estimated_value": None,
        "status": "sold",
        "owner_entity": None,
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 15 — LOS CABOS, MEXICO\n\n"
            "The boat and fuel dock which was originally part of the "
            "investment in Los Cabos, Mexico has been sold."
        ),
    },
    # NOTE 17 — 20 Harbor Point, CA
    {
        "name": "20 Harbor Point",
        "address": "20 Harbor Point, CA",
        "property_type": "Residential",
        "estimated_value": Decimal("5525000"),
        "status": "owned",
        "owner_entity": None,
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 17 — RESIDENTIAL PROPERTIES\n\n"
            "Stanley W. Gribble owns five residences as of December 31, 2024 "
            "reported at their estimated fair market value.\n\n"
            "20 Harbor Point, Ca: $5,525,000\n"
            "Zephyr Cove, NV: $2,319,078\n"
            "23 Observatory, CA: $7,805,000\n"
            "Cabo Villa 2: $11,289,464\n"
            "Cabo Villa 21: $15,782,295\n"
            "Total Residences: $42,820,837"
        ),
    },
    # NOTE 17 — Zephyr Cove, NV
    {
        "name": "Zephyr Cove Residence",
        "address": "Zephyr Cove, NV",
        "property_type": "Residential",
        "estimated_value": Decimal("2319078"),
        "status": "owned",
        "owner_entity": None,
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 17 — RESIDENTIAL PROPERTIES\n\n"
            "Stanley W. Gribble owns five residences as of December 31, 2024 "
            "reported at their estimated fair market value.\n\n"
            "20 Harbor Point, Ca: $5,525,000\n"
            "Zephyr Cove, NV: $2,319,078\n"
            "23 Observatory, CA: $7,805,000\n"
            "Cabo Villa 2: $11,289,464\n"
            "Cabo Villa 21: $15,782,295\n"
            "Total Residences: $42,820,837"
        ),
    },
    # NOTE 17 — 23 Observatory, CA
    {
        "name": "23 Observatory",
        "address": "23 Observatory, CA",
        "property_type": "Residential",
        "estimated_value": Decimal("7805000"),
        "status": "owned",
        "owner_entity": None,
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 17 — RESIDENTIAL PROPERTIES\n\n"
            "Stanley W. Gribble owns five residences as of December 31, 2024 "
            "reported at their estimated fair market value.\n\n"
            "20 Harbor Point, Ca: $5,525,000\n"
            "Zephyr Cove, NV: $2,319,078\n"
            "23 Observatory, CA: $7,805,000\n"
            "Cabo Villa 2: $11,289,464\n"
            "Cabo Villa 21: $15,782,295\n"
            "Total Residences: $42,820,837"
        ),
    },
    # NOTE 17 — Cabo Villa 2
    {
        "name": "Cabo Villa 2",
        "address": "Cabo San Lucas, Mexico (Villa 2)",
        "property_type": "Residential",
        "estimated_value": Decimal("11289464"),
        "status": "owned",
        "owner_entity": None,
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 17 — RESIDENTIAL PROPERTIES\n\n"
            "Stanley W. Gribble owns five residences as of December 31, 2024 "
            "reported at their estimated fair market value.\n\n"
            "20 Harbor Point, Ca: $5,525,000\n"
            "Zephyr Cove, NV: $2,319,078\n"
            "23 Observatory, CA: $7,805,000\n"
            "Cabo Villa 2: $11,289,464\n"
            "Cabo Villa 21: $15,782,295\n"
            "Total Residences: $42,820,837"
        ),
    },
    # NOTE 17 — Cabo Villa 21
    {
        "name": "Cabo Villa 21",
        "address": "Cabo San Lucas, Mexico (Villa 21)",
        "property_type": "Residential",
        "estimated_value": Decimal("15782295"),
        "status": "owned",
        "owner_entity": None,
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 17 — RESIDENTIAL PROPERTIES\n\n"
            "Stanley W. Gribble owns five residences as of December 31, 2024 "
            "reported at their estimated fair market value.\n\n"
            "20 Harbor Point, Ca: $5,525,000\n"
            "Zephyr Cove, NV: $2,319,078\n"
            "23 Observatory, CA: $7,805,000\n"
            "Cabo Villa 2: $11,289,464\n"
            "Cabo Villa 21: $15,782,295\n"
            "Total Residences: $42,820,837"
        ),
    },
    # NOTE 18 — Ascaya Lots
    {
        "name": "Ascaya Lots (2 lots)",
        "address": "Ascaya, NV (2 lots in residential neighborhood)",
        "property_type": "Land",
        "estimated_value": Decimal("18808507"),
        "status": "owned",
        "owner_entity": None,
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 18 — ASCAYA LOTS\n\n"
            "Stanley W. Gribble investment of $18,808,507 is composed of two "
            "lots in the Ascaya residential neighborhood in Nevada with a cost "
            "basis of $17,704,412 and a $1,104,095 cost basis on an additional "
            "lot to be closed on July 2025."
        ),
    },
]


# ── Aircraft ─────────────────────────────────────────────────────────────────

AIRCRAFT_DATA = [
    # NOTE 5 — G4SP, LLC
    {
        "name": "Gulfstream GIV-SP",
        "tail_number": "N15Y",
        "make": "Gulfstream",
        "model_name": "GIV-SP",
        "aircraft_type": "jet",
        "status": "sold",
        "owner_entity": "G4SP, LLC",
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 5 — G4SP, LLC\n\n"
            "G4SP, LLC owns a Gulfstream GIV-SP N15Y passenger aircraft. The "
            "aircraft sold July 2024."
        ),
    },
    # NOTE 11 — SG550, LLC
    {
        "name": "Gulfstream (SG550, LLC)",
        "tail_number": "",
        "make": "Gulfstream",
        "model_name": "",
        "aircraft_type": "jet",
        "status": "sold",
        "owner_entity": "SG550, LLC",
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 11 — SG550, LLC\n\n"
            "SG550, LLC owned a Gulfstream passenger aircraft. It was sold "
            "February 2024."
        ),
    },
    # NOTE 14 — N888GM, LLC
    {
        "name": "Gulfstream G600",
        "tail_number": "N888GM",
        "make": "Gulfstream",
        "model_name": "G600",
        "aircraft_type": "jet",
        "estimated_value": Decimal("4641881"),
        "status": "active",
        "owner_entity": "N888GM, LLC",
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 14 — N888GM, LLC\n\n"
            "N888GM, LLC owns a Gulfstream G600 passenger aircraft. The "
            "aircraft is currently used in air charter operations. The fair "
            "market value of this aircraft is valued at $4,641,881, net of "
            "debt, per the broker."
        ),
    },
]


# ── Investments ──────────────────────────────────────────────────────────────

INVESTMENTS = [
    # NOTE 3 — Bend Properties, Inc. cash
    {
        "name": "Bend Properties, Inc. — Cash & Cash Alternatives",
        "investment_type": "Cash",
        "institution": "Bend Properties, Inc.",
        "current_value": Decimal("11046909"),
        "owner_entity": "Bend Properties, Inc.",
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 3 — BEND PROPERTIES, INC.\n\n"
            "Bend Properties, Inc. is owned 100% by Stanley W. Gribble. The "
            "corporate assets include cash and cash alternatives of "
            "$11,046,909."
        ),
    },
    # NOTE 4 — 314SG, LLC cash accounts
    {
        "name": "314SG, LLC — Bank of America Cash",
        "investment_type": "Cash",
        "institution": "Bank of America",
        "current_value": Decimal("713651"),
        "owner_entity": "314SG, LLC",
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 4 — 314 SG, LLC\n\n"
            "314SG, LLC is owned 100% by Stanley W. Gribble, and it is "
            "composed of a cash account and various investments in commercial "
            "properties with Equitas Investment, LLC. The valuation of these "
            "commercial properties are presented at capital investment value, "
            "plus accrued preferred return and percentage of equity ownership "
            "at December 31, 2024. Three properties sold during 2024.\n\n"
            "Bank of America Cash: $713,651\n"
            "Equitas Managed Bank Cash: $811,373\n"
            "Commercial Properties: $34,653,468\n"
            "Total: $36,178,492"
        ),
    },
    {
        "name": "314SG, LLC — Equitas Managed Bank Cash",
        "investment_type": "Cash",
        "institution": "Equitas Investment, LLC",
        "current_value": Decimal("811373"),
        "owner_entity": "314SG, LLC",
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 4 — 314 SG, LLC\n\n"
            "314SG, LLC is owned 100% by Stanley W. Gribble, and it is "
            "composed of a cash account and various investments in commercial "
            "properties with Equitas Investment, LLC. The valuation of these "
            "commercial properties are presented at capital investment value, "
            "plus accrued preferred return and percentage of equity ownership "
            "at December 31, 2024. Three properties sold during 2024.\n\n"
            "Bank of America Cash: $713,651\n"
            "Equitas Managed Bank Cash: $811,373\n"
            "Commercial Properties: $34,653,468\n"
            "Total: $36,178,492"
        ),
    },
    # NOTE 21 — Axis Research and Technology stock
    {
        "name": "Axis Research and Technology — Stock",
        "investment_type": "Stock",
        "institution": "Axis Research and Technology",
        "current_value": Decimal("18000000"),
        "owner_entity": None,  # Direct SWG
        "owner_pct": Decimal("100"),
        "notes_text": (
            "NOTE 21 — AXIS RESEARCH AND TECHNOLOGY\n\n"
            "Stanley W. Gribble has $18,000,000 stock in Axis Research and "
            "Technology and a convertible note valued at $500,000 with a "
            "$8,678.08 interest receivable."
        ),
    },
]


# ── Loans ────────────────────────────────────────────────────────────────────

LOANS = [
    # NOTE 2 — Arcadia Gateway Centre, LP loans
    {
        "name": "CVS Land Loan — Arcadia Gateway Centre, LP",
        "original_amount": Decimal("17308974"),
        "current_balance": Decimal("17308974"),
        "status": "active",
        "borrower_entity": "Arcadia Gateway Centre, LP",
        "linked_property_name": "CVS Store Investments — Arcadia Gateway Centre, LP",
        "notes_text": (
            "NOTE 2 — CVS Land Loan for Arcadia Gateway Centre, LP\n\n"
            "Part of the CVS Store investment structure. Arcadia Gateway "
            "Centre, LP hold seven CVS Stores. CVS Purchase Price: "
            "$25,233,504. This land loan of $17,308,974 offsets the purchase "
            "price along with the Sec 467 loan."
        ),
    },
    {
        "name": "CVS Sec 467 Loan — Arcadia Gateway Centre, LP",
        "original_amount": Decimal("3569742"),
        "current_balance": Decimal("3569742"),
        "status": "active",
        "borrower_entity": "Arcadia Gateway Centre, LP",
        "linked_property_name": "CVS Store Investments — Arcadia Gateway Centre, LP",
        "notes_text": (
            "NOTE 2 — CVS Section 467 Loan for Arcadia Gateway Centre, LP\n\n"
            "Part of the CVS Store investment structure. Section 467 loan of "
            "$3,569,742 for Arcadia Gateway Centre, LP's seven CVS Stores."
        ),
    },
    # NOTE 2 — Arcadia Gateway Centre Associates, LTD loans
    {
        "name": "CVS Land Loan — Arcadia Gateway Centre Associates, LTD",
        "original_amount": Decimal("27813716"),
        "current_balance": Decimal("27813716"),
        "status": "active",
        "borrower_entity": "Arcadia Gateway Centre Associates, LTD",
        "linked_property_name": "CVS Store Investments — Arcadia Gateway Centre Associates, LTD",
        "notes_text": (
            "NOTE 2 — CVS Land Loan for Arcadia Gateway Centre Associates, LTD\n\n"
            "Part of the CVS Store investment structure. Arcadia Gateway "
            "Centre Associates, LTD holds thirteen CVS Stores. CVS Purchase "
            "Price: $41,199,433. This land loan of $27,813,716 offsets the "
            "purchase price along with the Sec 467 loan."
        ),
    },
    {
        "name": "CVS Sec 467 Loan — Arcadia Gateway Centre Associates, LTD",
        "original_amount": Decimal("5916266"),
        "current_balance": Decimal("5916266"),
        "status": "active",
        "borrower_entity": "Arcadia Gateway Centre Associates, LTD",
        "linked_property_name": "CVS Store Investments — Arcadia Gateway Centre Associates, LTD",
        "notes_text": (
            "NOTE 2 — CVS Section 467 Loan for Arcadia Gateway Centre "
            "Associates, LTD\n\n"
            "Part of the CVS Store investment structure. Section 467 loan of "
            "$5,916,266 for Arcadia Gateway Centre Associates, LTD's thirteen "
            "CVS Stores."
        ),
    },
    # NOTE 6 — Pecos Properties, LP loans
    {
        "name": "CVS Land Loan — Pecos Properties, LP",
        "original_amount": Decimal("7496049"),
        "current_balance": Decimal("7496049"),
        "status": "active",
        "borrower_entity": "Pecos Properties, LP",
        "linked_property_name": "CVS Store Leases — Pecos Properties, LP",
        "notes_text": (
            "NOTE 6 — Land Loan for Pecos Properties, LP\n\n"
            "Pecos Properties, LP CVS investments are valued at acquisition "
            "cost of $26,539,443, net of a land loan of $7,496,049 and Sec. "
            "467 loan $4,027,200. Nine CVS Stores Leases located in Georgia "
            "(3), Florida (4), Maryland (1), and North Carolina (1)."
        ),
    },
    {
        "name": "CVS Sec 467 Loan — Pecos Properties, LP",
        "original_amount": Decimal("4027200"),
        "current_balance": Decimal("4027200"),
        "status": "active",
        "borrower_entity": "Pecos Properties, LP",
        "linked_property_name": "CVS Store Leases — Pecos Properties, LP",
        "notes_text": (
            "NOTE 6 — Section 467 Loan for Pecos Properties, LP\n\n"
            "Section 467 loan of $4,027,200 for Pecos Properties, LP's nine "
            "CVS Stores Leases. Total acquisition cost $26,539,443."
        ),
    },
    # NOTE 6 — Bend Gucci Exchange, LLC loans
    {
        "name": "CVS Land Loan — Bend Gucci Exchange, LLC",
        "original_amount": Decimal("29456626"),
        "current_balance": Decimal("29456626"),
        "status": "active",
        "borrower_entity": "Bend Gucci Exchange, LLC",
        "linked_property_name": "CVS Drug Store Leases — Bend Gucci Exchange, LLC",
        "notes_text": (
            "NOTE 6 — Land Loan for Bend Gucci Exchange, LLC\n\n"
            "Bend Gucci Exchange, LLC owns investment in twenty CVS Drug Store "
            "leases. The total investment is valued at the total acquisition "
            "cost of $56,825,131, net of a land loan in the amount of "
            "$29,456,626 and Sec. 467 Loans in the amount of $8,155,572."
        ),
    },
    {
        "name": "CVS Sec 467 Loan — Bend Gucci Exchange, LLC",
        "original_amount": Decimal("8155572"),
        "current_balance": Decimal("8155572"),
        "status": "active",
        "borrower_entity": "Bend Gucci Exchange, LLC",
        "linked_property_name": "CVS Drug Store Leases — Bend Gucci Exchange, LLC",
        "notes_text": (
            "NOTE 6 — Section 467 Loan for Bend Gucci Exchange, LLC\n\n"
            "Section 467 loan of $8,155,572 for Bend Gucci Exchange, LLC's "
            "twenty CVS Drug Store leases. Total acquisition cost $56,825,131."
        ),
    },
    # NOTE 16/21 — Note receivable from Axis R&T
    {
        "name": "Convertible Note — Axis Research and Technology",
        "original_amount": Decimal("500000"),
        "current_balance": Decimal("508678"),
        "status": "active",
        "borrower_entity": "Axis Research and Technology",
        "linked_property_name": None,
        "notes_text": (
            "NOTE 16 — NOTES RECEIVABLE\n\n"
            "The Notes receivable are composed of $500,000 note receivable "
            "and accrued interest of $8,678.00 with Axis Research & "
            "Technology.\n\n"
            "NOTE 21 — AXIS RESEARCH AND TECHNOLOGY\n\n"
            "Stanley W. Gribble has $18,000,000 stock in Axis Research and "
            "Technology and a convertible note valued at $500,000 with a "
            "$8,678.08 interest receivable."
        ),
    },
    # NOTE 20 — N885GM, LLC / UBS loan (paid off)
    {
        "name": "UBS Aircraft Loan — N885GM, LLC / SG550, LLC",
        "original_amount": None,
        "current_balance": Decimal("0"),
        "status": "paid_off",
        "borrower_entity": "N885GM, LLC",
        "linked_property_name": None,
        "linked_aircraft_name": "Gulfstream (SG550, LLC)",
        "notes_text": (
            "NOTE 20 — N885GM, LLC\n\n"
            "N885GM, LLC holds a loan with UBS for the aircraft owned by "
            "SG550, LLC. The loan balance has been paid in full as of "
            "02/29/2024 when the aircraft has been sold."
        ),
    },
]


class Command(BaseCommand):
    help = "Import Gribble financial statement data (entities, properties, aircraft, investments, loans)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Preview changes without saving")
        parser.add_argument("--update", action="store_true",
                            help="Update notes_text on existing records")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        update = options["update"]
        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY RUN ===\n"))

        counts = {
            "stakeholders": 0,
            "properties": 0,
            "aircraft": 0,
            "investments": 0,
            "loans": 0,
            "ownership_links": 0,
            "updated": 0,
        }

        # Phase 1: Stakeholders
        self.stdout.write(self.style.WARNING("--- Phase 1: Stakeholders / Entities ---"))
        stakeholder_map = self._create_stakeholders(dry_run, update, counts)

        # Phase 2: Real Estate
        self.stdout.write(self.style.WARNING("\n--- Phase 2: Real Estate ---"))
        property_map = self._create_properties(stakeholder_map, dry_run, update, counts)

        # Phase 3: Aircraft
        self.stdout.write(self.style.WARNING("\n--- Phase 3: Aircraft ---"))
        aircraft_map = self._create_aircraft(stakeholder_map, dry_run, update, counts)

        # Phase 4: Investments
        self.stdout.write(self.style.WARNING("\n--- Phase 4: Investments ---"))
        self._create_investments(stakeholder_map, dry_run, update, counts)

        # Phase 5: Loans
        self.stdout.write(self.style.WARNING("\n--- Phase 5: Loans ---"))
        self._create_loans(stakeholder_map, property_map, aircraft_map, dry_run, update, counts)

        # Invalidate choice cache
        if not dry_run:
            invalidate_choice_cache()

        # Summary
        parts = []
        verb = "Would create" if dry_run else "Created"
        parts.append(f"{counts['stakeholders']} stakeholders")
        parts.append(f"{counts['properties']} properties")
        parts.append(f"{counts['aircraft']} aircraft")
        parts.append(f"{counts['investments']} investments")
        parts.append(f"{counts['loans']} loans")
        parts.append(f"{counts['ownership_links']} ownership links")
        if counts["updated"]:
            parts.append(f"{counts['updated']} records updated")
        self.stdout.write(self.style.SUCCESS(f"\n{verb}: {', '.join(parts)}"))
        self.stdout.write(self.style.SUCCESS("Done."))

    def _update_notes(self, obj, new_notes, dry_run, counts):
        """Update notes_text on an existing record if it differs."""
        if obj.notes_text != new_notes:
            if dry_run:
                self.stdout.write(self.style.NOTICE(
                    f"    WOULD UPDATE notes on: {obj}"
                ))
            else:
                obj.notes_text = new_notes
                obj.save(update_fields=["notes_text"])
                self.stdout.write(self.style.SUCCESS(
                    f"    UPDATED notes on: {obj}"
                ))
            counts["updated"] += 1

    # ── Phase 1: Stakeholders ────────────────────────────────────────────

    def _create_stakeholders(self, dry_run, update, counts):
        stakeholder_map = {}

        for name, entity_type, _ownership_pct, notes in ENTITIES:
            if dry_run:
                obj = Stakeholder.objects.filter(name=name).first()
                if obj:
                    self.stdout.write(f"  EXISTS: {name}")
                    stakeholder_map[name] = obj
                    if update:
                        self._update_notes(obj, notes, dry_run, counts)
                else:
                    self.stdout.write(self.style.NOTICE(f"  WOULD CREATE: {name} ({entity_type})"))
                    counts["stakeholders"] += 1
            else:
                obj, created = Stakeholder.objects.get_or_create(
                    name=name,
                    defaults={
                        "entity_type": entity_type,
                        "notes_text": notes,
                    },
                )
                stakeholder_map[name] = obj
                if created:
                    self.stdout.write(self.style.SUCCESS(f"  CREATED: {name} (pk={obj.pk})"))
                    counts["stakeholders"] += 1
                else:
                    self.stdout.write(f"  EXISTS: {name} (pk={obj.pk})")
                    if update:
                        self._update_notes(obj, notes, dry_run, counts)

        # Set parent_organization on all LLCs → SWG
        swg = stakeholder_map.get(SWG_NAME)
        if swg and not dry_run:
            for name, entity_type, _pct, _notes in ENTITIES:
                if name == SWG_NAME or entity_type == "business_partner":
                    continue
                obj = stakeholder_map.get(name)
                if obj and not obj.parent_organization:
                    obj.parent_organization = swg
                    obj.save(update_fields=["parent_organization"])
                    self.stdout.write(f"    Set parent: {name} → {SWG_NAME}")

        # Also set 314SG as child of SWG if it exists
        sg314 = stakeholder_map.get("314SG, LLC")
        if sg314 and swg and not dry_run:
            if sg314.parent_organization != swg:
                sg314.parent_organization = swg
                sg314.save(update_fields=["parent_organization"])

        return stakeholder_map

    # ── Phase 2: Real Estate ─────────────────────────────────────────────

    def _create_properties(self, stakeholder_map, dry_run, update, counts):
        property_map = {}
        swg = stakeholder_map.get(SWG_NAME)

        for prop in PROPERTIES:
            name = prop["name"]

            if dry_run:
                obj = RealEstate.objects.filter(name=name).first()
                if obj:
                    self.stdout.write(f"  EXISTS: {name}")
                    property_map[name] = obj
                    if update:
                        self._update_notes(obj, prop["notes_text"], dry_run, counts)
                else:
                    val = f"${prop['estimated_value']:,.0f}" if prop["estimated_value"] else "N/A"
                    self.stdout.write(self.style.NOTICE(
                        f"  WOULD CREATE: {name} — {val} ({prop['status']})"
                    ))
                    counts["properties"] += 1
                    counts["ownership_links"] += 1
                    if prop.get("owner_entity"):
                        counts["ownership_links"] += 1
            else:
                obj, created = RealEstate.objects.get_or_create(
                    name=name,
                    defaults={
                        "address": prop["address"],
                        "property_type": prop.get("property_type", ""),
                        "estimated_value": prop.get("estimated_value"),
                        "status": prop["status"],
                        "notes_text": prop.get("notes_text", ""),
                    },
                )
                property_map[name] = obj
                if created:
                    self.stdout.write(self.style.SUCCESS(f"  CREATED: {name} (pk={obj.pk})"))
                    counts["properties"] += 1
                else:
                    self.stdout.write(f"  EXISTS: {name} (pk={obj.pk})")
                    if update:
                        self._update_notes(obj, prop["notes_text"], dry_run, counts)

                # Ownership: entity LLC
                entity_name = prop.get("owner_entity")
                if entity_name and entity_name in stakeholder_map:
                    entity = stakeholder_map[entity_name]
                    _, link_created = PropertyOwnership.objects.get_or_create(
                        property=obj,
                        stakeholder=entity,
                        defaults={
                            "ownership_percentage": prop.get("owner_pct"),
                            "role": "Holding Entity",
                        },
                    )
                    if link_created:
                        counts["ownership_links"] += 1

                # Ownership: SWG direct
                if swg:
                    _, link_created = PropertyOwnership.objects.get_or_create(
                        property=obj,
                        stakeholder=swg,
                        defaults={
                            "ownership_percentage": prop.get("owner_pct"),
                            "role": "Owner",
                        },
                    )
                    if link_created:
                        counts["ownership_links"] += 1

        return property_map

    # ── Phase 3: Aircraft ────────────────────────────────────────────────

    def _create_aircraft(self, stakeholder_map, dry_run, update, counts):
        aircraft_map = {}
        swg = stakeholder_map.get(SWG_NAME)

        for ac in AIRCRAFT_DATA:
            name = ac["name"]

            if dry_run:
                obj = Aircraft.objects.filter(name=name).first()
                if obj:
                    self.stdout.write(f"  EXISTS: {name}")
                    aircraft_map[name] = obj
                    if update:
                        self._update_notes(obj, ac["notes_text"], dry_run, counts)
                else:
                    self.stdout.write(self.style.NOTICE(
                        f"  WOULD CREATE: {name} (tail: {ac.get('tail_number', 'N/A')}, {ac['status']})"
                    ))
                    counts["aircraft"] += 1
                    counts["ownership_links"] += 1
                    if ac.get("owner_entity"):
                        counts["ownership_links"] += 1
            else:
                obj, created = Aircraft.objects.get_or_create(
                    name=name,
                    defaults={
                        "tail_number": ac.get("tail_number", ""),
                        "make": ac.get("make", ""),
                        "model_name": ac.get("model_name", ""),
                        "aircraft_type": ac.get("aircraft_type", "jet"),
                        "estimated_value": ac.get("estimated_value"),
                        "status": ac["status"],
                        "notes_text": ac.get("notes_text", ""),
                    },
                )
                aircraft_map[name] = obj
                if created:
                    self.stdout.write(self.style.SUCCESS(f"  CREATED: {name} (pk={obj.pk})"))
                    counts["aircraft"] += 1
                else:
                    self.stdout.write(f"  EXISTS: {name} (pk={obj.pk})")
                    if update:
                        self._update_notes(obj, ac["notes_text"], dry_run, counts)

                # Ownership: entity LLC
                entity_name = ac.get("owner_entity")
                if entity_name and entity_name in stakeholder_map:
                    entity = stakeholder_map[entity_name]
                    _, link_created = AircraftOwner.objects.get_or_create(
                        aircraft=obj,
                        stakeholder=entity,
                        defaults={
                            "ownership_percentage": ac.get("owner_pct"),
                            "role": "Holding Entity",
                        },
                    )
                    if link_created:
                        counts["ownership_links"] += 1

                # Ownership: SWG direct
                if swg:
                    _, link_created = AircraftOwner.objects.get_or_create(
                        aircraft=obj,
                        stakeholder=swg,
                        defaults={
                            "ownership_percentage": ac.get("owner_pct"),
                            "role": "Owner",
                        },
                    )
                    if link_created:
                        counts["ownership_links"] += 1

        return aircraft_map

    # ── Phase 4: Investments ─────────────────────────────────────────────

    def _create_investments(self, stakeholder_map, dry_run, update, counts):
        swg = stakeholder_map.get(SWG_NAME)

        for inv in INVESTMENTS:
            name = inv["name"]

            if dry_run:
                obj = Investment.objects.filter(name=name).first()
                if obj:
                    self.stdout.write(f"  EXISTS: {name}")
                    if update:
                        self._update_notes(obj, inv["notes_text"], dry_run, counts)
                else:
                    val = f"${inv['current_value']:,.0f}" if inv["current_value"] else "N/A"
                    self.stdout.write(self.style.NOTICE(
                        f"  WOULD CREATE: {name} — {val}"
                    ))
                    counts["investments"] += 1
                    counts["ownership_links"] += 1
                    if inv.get("owner_entity"):
                        counts["ownership_links"] += 1
            else:
                obj, created = Investment.objects.get_or_create(
                    name=name,
                    defaults={
                        "investment_type": inv.get("investment_type", ""),
                        "institution": inv.get("institution", ""),
                        "current_value": inv.get("current_value"),
                        "notes_text": inv.get("notes_text", ""),
                    },
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f"  CREATED: {name} (pk={obj.pk})"))
                    counts["investments"] += 1
                else:
                    self.stdout.write(f"  EXISTS: {name} (pk={obj.pk})")
                    if update:
                        self._update_notes(obj, inv["notes_text"], dry_run, counts)

                # Ownership: entity LLC
                entity_name = inv.get("owner_entity")
                if entity_name and entity_name in stakeholder_map:
                    entity = stakeholder_map[entity_name]
                    _, link_created = InvestmentParticipant.objects.get_or_create(
                        investment=obj,
                        stakeholder=entity,
                        defaults={
                            "ownership_percentage": inv.get("owner_pct"),
                            "role": "Holding Entity",
                        },
                    )
                    if link_created:
                        counts["ownership_links"] += 1

                # Ownership: SWG direct
                if swg:
                    _, link_created = InvestmentParticipant.objects.get_or_create(
                        investment=obj,
                        stakeholder=swg,
                        defaults={
                            "ownership_percentage": inv.get("owner_pct"),
                            "role": "Owner",
                        },
                    )
                    if link_created:
                        counts["ownership_links"] += 1

    # ── Phase 5: Loans ───────────────────────────────────────────────────

    def _create_loans(self, stakeholder_map, property_map, aircraft_map, dry_run, update, counts):
        for loan_data in LOANS:
            name = loan_data["name"]

            if dry_run:
                obj = Loan.objects.filter(name=name).first()
                if obj:
                    self.stdout.write(f"  EXISTS: {name}")
                    if update:
                        self._update_notes(obj, loan_data["notes_text"], dry_run, counts)
                else:
                    bal = loan_data.get("current_balance")
                    bal_str = f"${bal:,.0f}" if bal is not None else "N/A"
                    self.stdout.write(self.style.NOTICE(
                        f"  WOULD CREATE: {name} — balance {bal_str} ({loan_data['status']})"
                    ))
                    counts["loans"] += 1
                    if loan_data.get("borrower_entity"):
                        counts["ownership_links"] += 1
            else:
                # Resolve linked property
                linked_prop = None
                prop_name = loan_data.get("linked_property_name")
                if prop_name:
                    linked_prop = property_map.get(prop_name)
                    if not linked_prop:
                        linked_prop = RealEstate.objects.filter(name=prop_name).first()

                # Resolve linked aircraft
                linked_ac = None
                ac_name = loan_data.get("linked_aircraft_name")
                if ac_name:
                    linked_ac = aircraft_map.get(ac_name)
                    if not linked_ac:
                        linked_ac = Aircraft.objects.filter(name=ac_name).first()

                obj, created = Loan.objects.get_or_create(
                    name=name,
                    defaults={
                        "original_amount": loan_data.get("original_amount"),
                        "current_balance": loan_data.get("current_balance"),
                        "status": loan_data["status"],
                        "related_property": linked_prop,
                        "related_aircraft": linked_ac,
                        "notes_text": loan_data.get("notes_text", ""),
                    },
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f"  CREATED: {name} (pk={obj.pk})"))
                    counts["loans"] += 1
                else:
                    self.stdout.write(f"  EXISTS: {name} (pk={obj.pk})")
                    if update:
                        self._update_notes(obj, loan_data["notes_text"], dry_run, counts)

                # LoanParty: borrower entity
                borrower_name = loan_data.get("borrower_entity")
                if borrower_name and borrower_name in stakeholder_map:
                    borrower = stakeholder_map[borrower_name]
                    _, link_created = LoanParty.objects.get_or_create(
                        loan=obj,
                        stakeholder=borrower,
                        defaults={"role": "Borrower"},
                    )
                    if link_created:
                        counts["ownership_links"] += 1
