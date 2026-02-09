"""
Management command to populate Control Center with comprehensive sample data.
Usage: python manage.py load_sample_data
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from stakeholders.models import Stakeholder, Relationship, ContactLog
from assets.models import RealEstate, Investment, Loan
from legal.models import LegalMatter, Evidence
from tasks.models import Task, FollowUp
from cashflow.models import CashFlowEntry
from notes.models import Note


class Command(BaseCommand):
    help = "Load comprehensive sample data for demo purposes"

    def handle(self, *args, **options):
        today = date.today()
        now = timezone.now()

        self.stdout.write("Creating stakeholders...")
        stakeholders = {}
        data = [
            ("Marcus Reed", "attorney", "marcus.reed@reedlaw.com", "555-201-4400", "Reed & Associates", 5, 1,
             "Primary litigation attorney. Very responsive, bills fairly."),
            ("Sandra Liu", "attorney", "sliu@liulegal.com", "555-303-7100", "Liu Legal Group", 4, 1,
             "Real estate transactional attorney. Handles all closings."),
            ("Tom Driscoll", "business_partner", "tom@driscollventures.com", "555-817-2200", "Driscoll Ventures LLC", 3, 3,
             "50/50 partner on Elm St property. Has been slow to respond lately."),
            ("Janet Cobb", "lender", "jcobb@firstnational.com", "555-422-8000", "First National Bank", 4, 2,
             "Loan officer handling the commercial mortgage. Good relationship."),
            ("Derek Vasquez", "advisor", "derek@vfinancial.com", "555-610-3300", "Vasquez Financial Advisory", 5, 1,
             "Financial advisor managing investment portfolio. Quarterly reviews."),
            ("Karen Whitfield", "professional", "kwhitfield@appraisalco.com", "555-774-1500", "Whitfield Appraisals", 4, 1,
             "Licensed appraiser. Used for property valuations."),
            ("Ray Holston", "contact", "ray.holston@email.com", "555-229-6600", "", 2, 4,
             "Former tenant at Oak Ave. Owes back rent. Unresponsive."),
            ("Nina Patel", "business_partner", "nina@npinvestments.com", "555-888-4100", "NP Investments", 4, 2,
             "Co-investor on Magnolia portfolio. Reliable so far."),
            ("Victor Huang", "lender", "vhuang@privatelending.com", "555-316-9200", "Huang Private Lending", 3, 3,
             "Private money lender. High rates but fast closes. Use cautiously."),
            ("Alicia Moreno", "professional", "amoreno@titlefirst.com", "555-502-7700", "Title First Agency", 5, 1,
             "Title agent handling all closings. Extremely thorough."),
            ("James Calloway", "contact", "james.c@email.com", "555-119-3400", "Calloway Construction", 3, 2,
             "General contractor. Good work but missed deadlines on Oak Ave renovation."),
            ("Dr. Helen Park", "advisor", "hpark@estateplanning.com", "555-667-4800", "Park Estate Planning", 5, 1,
             "Estate planning attorney. Handles trust and succession planning."),
        ]
        for name, etype, email, phone, org, trust, risk, notes in data:
            s = Stakeholder.objects.create(
                name=name, entity_type=etype, email=email, phone=phone,
                organization=org, trust_rating=trust, risk_rating=risk, notes_text=notes,
            )
            stakeholders[name] = s

        self.stdout.write("Creating relationships...")
        rels = [
            ("Marcus Reed", "Sandra Liu", "colleague", "Both in legal, refer work to each other"),
            ("Tom Driscoll", "Nina Patel", "business associate", "Have co-invested before"),
            ("Janet Cobb", "Alicia Moreno", "professional contact", "Bank refers title work to her"),
            ("Derek Vasquez", "Dr. Helen Park", "referral partner", "Cross-refer wealth management clients"),
            ("James Calloway", "Tom Driscoll", "contractor", "Calloway does rehab work for Driscoll projects"),
        ]
        for f, t, rtype, desc in rels:
            Relationship.objects.create(
                from_stakeholder=stakeholders[f], to_stakeholder=stakeholders[t],
                relationship_type=rtype, description=desc,
            )

        self.stdout.write("Creating contact logs...")
        logs = [
            ("Marcus Reed", -2, "call", "Discussed status of Holston eviction. Filing motion next week.", True, 7),
            ("Marcus Reed", -15, "email", "Sent updated retainer agreement. Awaiting signature.", False, None),
            ("Sandra Liu", -5, "meeting", "Reviewed closing docs for Magnolia Blvd. All clear to proceed.", False, None),
            ("Tom Driscoll", -8, "call", "Left voicemail about Elm St maintenance issues. No answer.", True, 3),
            ("Tom Driscoll", -22, "email", "Sent Q4 expense report for Elm St property.", False, None),
            ("Janet Cobb", -3, "call", "Confirmed next mortgage payment dates. No issues.", False, None),
            ("Derek Vasquez", -1, "meeting", "Quarterly portfolio review. Recommended shifting 10% to bonds.", False, None),
            ("Ray Holston", -10, "call", "Attempted contact re: outstanding balance. No answer.", True, 5),
            ("Ray Holston", -30, "email", "Sent formal demand letter for $4,200 in back rent.", True, 14),
            ("Nina Patel", -6, "email", "Discussed potential acquisition of 440 Birch St.", False, None),
            ("James Calloway", -4, "call", "Got updated timeline for bathroom renovation. 2 weeks out.", True, 14),
            ("Karen Whitfield", -12, "email", "Requested appraisal for 1200 Oak Ave. Scheduled for next week.", False, None),
            ("Alicia Moreno", -7, "call", "Title search on Magnolia property is clean. Ready for closing.", False, None),
            ("Dr. Helen Park", -20, "meeting", "Annual trust review. Updated beneficiary designations.", False, None),
        ]
        for name, days_ago, method, summary, followup, fu_days in logs:
            ContactLog.objects.create(
                stakeholder=stakeholders[name],
                date=now + timedelta(days=days_ago),
                method=method, summary=summary,
                follow_up_needed=followup,
                follow_up_date=today + timedelta(days=fu_days) if fu_days else None,
            )

        self.stdout.write("Creating real estate...")
        properties = {}
        prop_data = [
            ("1200 Oak Avenue", "1200 Oak Ave, Austin, TX 78701", "Travis County, TX", "Single Family",
             Decimal("385000.00"), today - timedelta(days=730), "owned", "Tom Driscoll",
             "Rental property. Currently undergoing bathroom renovation. Tenant issues with Ray Holston."),
            ("450 Elm Street", "450 Elm St, Austin, TX 78702", "Travis County, TX", "Duplex",
             Decimal("520000.00"), today - timedelta(days=1095), "owned", "Tom Driscoll",
             "Co-owned 50/50 with Tom Driscoll. Both units rented. Needs roof inspection."),
            ("3300 Magnolia Blvd", "3300 Magnolia Blvd, San Antonio, TX 78205", "Bexar County, TX", "Commercial",
             Decimal("1250000.00"), None, "under_contract", "Nina Patel",
             "Under contract. Closing scheduled for next month. Co-investing with Nina Patel."),
            ("890 Cedar Lane", "890 Cedar Ln, Dallas, TX 75201", "Dallas County, TX", "Single Family",
             Decimal("275000.00"), today - timedelta(days=1460), "in_dispute", None,
             "Property boundary dispute with neighbor. Marcus Reed handling litigation."),
            ("15 Riverside Dr", "15 Riverside Dr, Houston, TX 77001", "Harris County, TX", "Vacant Land",
             Decimal("180000.00"), today - timedelta(days=365), "owned", None,
             "Undeveloped lot. Zoning permits under review for residential development."),
        ]
        for name, addr, juris, ptype, val, acq, status, sh_name, notes in prop_data:
            p = RealEstate.objects.create(
                name=name, address=addr, jurisdiction=juris, property_type=ptype,
                estimated_value=val, acquisition_date=acq, status=status,
                stakeholder=stakeholders.get(sh_name), notes_text=notes,
            )
            properties[name] = p

        self.stdout.write("Creating investments...")
        investments = {}
        inv_data = [
            ("Vanguard Total Market Index", "Index Fund", "Vanguard", Decimal("142500.00"), "Derek Vasquez",
             "Core holding. Dollar-cost averaging $2k/month."),
            ("Schwab S&P 500 ETF", "ETF", "Charles Schwab", Decimal("87300.00"), "Derek Vasquez",
             "Large cap exposure. Rebalance quarterly."),
            ("Municipal Bond Fund", "Bond Fund", "Fidelity", Decimal("65000.00"), "Derek Vasquez",
             "Tax-advantaged income. Added per advisor recommendation."),
            ("NP Investments LP - Fund II", "Private Equity", "NP Investments", Decimal("50000.00"), "Nina Patel",
             "Committed $50k to Nina's real estate fund. 3-year lockup. Annual distributions."),
            ("Bitcoin Holdings", "Cryptocurrency", "Coinbase", Decimal("22400.00"), None,
             "Speculative position. 0.35 BTC. Consider taking profits if above $70k."),
        ]
        for name, itype, inst, val, sh_name, notes in inv_data:
            inv = Investment.objects.create(
                name=name, investment_type=itype, institution=inst, current_value=val,
                stakeholder=stakeholders.get(sh_name), notes_text=notes,
            )
            investments[name] = inv

        self.stdout.write("Creating loans...")
        loans = {}
        loan_data = [
            ("First National - Oak Ave Mortgage", "Janet Cobb", "Blaine (personal)",
             Decimal("320000.00"), Decimal("285400.00"), Decimal("4.750"),
             Decimal("2100.00"), today + timedelta(days=22), today + timedelta(days=365 * 25),
             "1200 Oak Avenue property", "active",
             "30-year fixed. Good rate locked in 2023."),
            ("First National - Elm St Mortgage", "Janet Cobb", "Blaine & Tom Driscoll (50/50)",
             Decimal("410000.00"), Decimal("372000.00"), Decimal("5.125"),
             Decimal("2800.00"), today + timedelta(days=15), today + timedelta(days=365 * 27),
             "450 Elm Street duplex", "active",
             "Joint mortgage with Tom. Both personally guaranteeing."),
            ("Huang Bridge Loan - Magnolia", "Victor Huang", "Blaine & Nina Patel",
             Decimal("200000.00"), Decimal("200000.00"), Decimal("9.500"),
             Decimal("1583.33"), today + timedelta(days=8), today + timedelta(days=180),
             "3300 Magnolia Blvd purchase", "active",
             "6-month bridge loan for acquisition. Need to refinance into permanent financing ASAP."),
            ("Vehicle Loan - F-150", None, "Blaine (personal)",
             Decimal("45000.00"), Decimal("28700.00"), Decimal("3.900"),
             Decimal("750.00"), today + timedelta(days=18), today + timedelta(days=365 * 3),
             "2023 Ford F-150", "active",
             "Auto loan through credit union. On track."),
        ]
        for name, lender_name, borrower, orig, bal, rate, pmt, npd, mat, collat, status, notes in loan_data:
            ln = Loan.objects.create(
                name=name, lender=stakeholders.get(lender_name),
                borrower_description=borrower, original_amount=orig,
                current_balance=bal, interest_rate=rate, monthly_payment=pmt,
                next_payment_date=npd, maturity_date=mat, collateral=collat,
                status=status, notes_text=notes,
            )
            loans[name] = ln

        self.stdout.write("Creating legal matters...")
        legal_matters = {}
        lm_data = [
            ("Holston Eviction - 1200 Oak Ave",
             "2024-CV-4821", "litigation", "active", "Travis County, TX",
             "Travis County District Court", today - timedelta(days=45),
             "Eviction proceeding against Ray Holston for non-payment of rent ($4,200 outstanding). "
             "Filed after 30-day demand letter went unanswered. Hearing scheduled.",
             ["Marcus Reed"], ["Ray Holston"], ["1200 Oak Avenue"]),
            ("Cedar Lane Boundary Dispute",
             "2023-CV-11034", "litigation", "active", "Dallas County, TX",
             "Dallas County Civil Court", today - timedelta(days=210),
             "Neighbor claims fence encroaches 3 feet onto their lot. Survey shows otherwise. "
             "Attempting mediation before trial.",
             ["Marcus Reed"], [], ["890 Cedar Lane"]),
            ("Magnolia Blvd Acquisition - Due Diligence",
             "", "transaction", "pending", "Bexar County, TX", "",
             today - timedelta(days=30),
             "Due diligence review for 3300 Magnolia Blvd acquisition. Environmental Phase I complete. "
             "Title search clean. Reviewing seller's disclosures.",
             ["Sandra Liu"], ["Nina Patel"], ["3300 Magnolia Blvd"]),
            ("Riverside Zoning Application",
             "ZN-2025-0188", "compliance", "pending", "Harris County, TX",
             "Harris County Planning Commission", today - timedelta(days=60),
             "Zoning change request from agricultural to residential for 15 Riverside Dr. "
             "Public hearing scheduled. Need community support documentation.",
             [], [], ["15 Riverside Dr"]),
            ("Estate Plan Update",
             "", "other", "active", "", "",
             today - timedelta(days=90),
             "Comprehensive estate plan review and update. Revising trust documents, "
             "updating beneficiary designations, power of attorney refresh.",
             ["Dr. Helen Park"], [], []),
        ]
        for title, case, mtype, status, juris, court, filed, desc, attys, shs, props in lm_data:
            lm = LegalMatter.objects.create(
                title=title, case_number=case, matter_type=mtype, status=status,
                jurisdiction=juris, court=court, filing_date=filed, description=desc,
            )
            for a in attys:
                lm.attorneys.add(stakeholders[a])
            for s in shs:
                lm.related_stakeholders.add(stakeholders[s])
            for p in props:
                lm.related_properties.add(properties[p])
            legal_matters[title] = lm

        self.stdout.write("Creating evidence...")
        evidence_data = [
            ("Holston Eviction - 1200 Oak Ave", [
                ("Lease Agreement - Holston", "Original signed lease with Ray Holston", "Document", today - timedelta(days=400)),
                ("Demand Letter - 30 Day Notice", "Certified mail demand letter sent to Holston", "Correspondence", today - timedelta(days=60)),
                ("Rent Ledger", "Payment history showing 3 months delinquent", "Financial Record", today - timedelta(days=45)),
            ]),
            ("Cedar Lane Boundary Dispute", [
                ("Property Survey - 2024", "Licensed surveyor report showing fence placement", "Survey", today - timedelta(days=180)),
                ("Original Deed - 890 Cedar", "Deed with metes and bounds description", "Document", today - timedelta(days=200)),
                ("Neighbor Communications", "Email thread with neighbor's initial complaint", "Correspondence", today - timedelta(days=220)),
            ]),
            ("Magnolia Blvd Acquisition - Due Diligence", [
                ("Phase I Environmental Report", "Clean environmental assessment", "Report", today - timedelta(days=20)),
                ("Title Search Results", "Clear title, no liens or encumbrances", "Document", today - timedelta(days=15)),
                ("Property Inspection Report", "Structural and mechanical inspection findings", "Report", today - timedelta(days=18)),
            ]),
        ]
        for lm_title, items in evidence_data:
            for title, desc, etype, dt in items:
                Evidence.objects.create(
                    legal_matter=legal_matters[lm_title],
                    title=title, description=desc, evidence_type=etype, date_obtained=dt,
                )

        self.stdout.write("Creating tasks...")
        tasks = {}
        task_data = [
            ("Follow up with Marcus on Holston hearing date", "Call Marcus Reed to confirm hearing date and discuss strategy.",
             today + timedelta(days=3), "not_started", "high", "one_time",
             "Marcus Reed", "Holston Eviction - 1200 Oak Ave", "1200 Oak Avenue"),
            ("Pay Oak Ave mortgage", "Monthly mortgage payment to First National.",
             today + timedelta(days=22), "not_started", "high", "one_time",
             None, None, "1200 Oak Avenue"),
            ("Pay Elm St mortgage", "Monthly mortgage payment to First National. Split with Tom.",
             today + timedelta(days=15), "not_started", "high", "one_time",
             "Tom Driscoll", None, "450 Elm Street"),
            ("Schedule roof inspection - Elm St", "Get 2-3 quotes for roof inspection on the duplex.",
             today + timedelta(days=10), "in_progress", "medium", "one_time",
             "James Calloway", None, "450 Elm Street"),
            ("Review Magnolia closing documents", "Final review of all closing docs before signing.",
             today + timedelta(days=5), "waiting", "critical", "one_time",
             "Sandra Liu", "Magnolia Blvd Acquisition - Due Diligence", "3300 Magnolia Blvd"),
            ("Refinance Huang bridge loan", "Find permanent financing to replace the 9.5% bridge loan.",
             today + timedelta(days=30), "not_started", "critical", "one_time",
             "Janet Cobb", None, None),
            ("Prepare zoning hearing materials", "Compile community support letters and development plan for hearing.",
             today + timedelta(days=14), "in_progress", "high", "one_time",
             None, "Riverside Zoning Application", "15 Riverside Dr"),
            ("Quarterly portfolio review follow-up", "Review Derek's bond allocation recommendation and make decision.",
             today + timedelta(days=7), "not_started", "medium", "one_time",
             "Derek Vasquez", None, None),
            ("Send Holston back rent to collections", "If eviction proceeds, send $4,200 balance to collections agency.",
             today + timedelta(days=45), "not_started", "medium", "one_time",
             "Ray Holston", "Holston Eviction - 1200 Oak Ave", None),
            ("Oak Ave bathroom renovation check-in", "Verify Calloway is on schedule. Due in 2 weeks.",
             today + timedelta(days=5), "not_started", "medium", "one_time",
             "James Calloway", None, "1200 Oak Avenue"),
            ("Update estate plan documents", "Sign updated trust and POA documents at Helen's office.",
             today + timedelta(days=20), "waiting", "medium", "one_time",
             "Dr. Helen Park", "Estate Plan Update", None),
            ("Review Q4 Elm St expense report", "Tom sent Q4 expenses. Verify amounts and approve.",
             today - timedelta(days=5), "not_started", "medium", "one_time",
             "Tom Driscoll", None, "450 Elm Street"),
            ("Pay Huang bridge loan interest", "Monthly interest-only payment due.",
             today + timedelta(days=8), "not_started", "high", "one_time",
             "Victor Huang", None, None),
            ("File property tax protest - Cedar Lane", "Assessed value seems high given boundary dispute. File protest.",
             today - timedelta(days=10), "not_started", "low", "one_time",
             None, "Cedar Lane Boundary Dispute", "890 Cedar Lane"),
            ("Research Bitcoin exit strategy", "Price is near target. Set limit orders or hold?",
             today + timedelta(days=2), "not_started", "low", "one_time",
             None, None, None),
        ]
        for title, desc, due, status, priority, ttype, sh_name, lm_title, prop_name in task_data:
            t = Task.objects.create(
                title=title, description=desc, due_date=due,
                status=status, priority=priority, task_type=ttype,
                related_stakeholder=stakeholders.get(sh_name),
                related_legal_matter=legal_matters.get(lm_title) if lm_title else None,
                related_property=properties.get(prop_name) if prop_name else None,
            )
            tasks[title] = t

        self.stdout.write("Creating follow-ups...")
        followup_data = [
            ("Follow up with Marcus on Holston hearing date", "Marcus Reed", -2, "call", False, None,
             "Left voicemail. Will try again tomorrow."),
            ("Review Q4 Elm St expense report", "Tom Driscoll", -5, "email", False, None,
             "Sent email asking for supporting receipts."),
            ("Review Q4 Elm St expense report", "Tom Driscoll", -12, "call", False, None,
             "Called to discuss expense report. He said he'd send it over."),
            ("Schedule roof inspection - Elm St", "James Calloway", -4, "call", True, now - timedelta(days=2),
             "Called Calloway for a quote. He'll send one by Friday."),
            ("Schedule roof inspection - Elm St", "James Calloway", -1, "email", False, None,
             "Following up on the quote. No response yet."),
            ("Review Magnolia closing documents", "Sandra Liu", -5, "email", True, now - timedelta(days=3),
             "Sandra confirmed docs are ready for review. Picking up Thursday."),
            ("Send Holston back rent to collections", "Ray Holston", -10, "call", False, None,
             "Attempted contact one more time before going to collections. No answer."),
            ("Update estate plan documents", "Dr. Helen Park", -20, "meeting", True, now - timedelta(days=18),
             "Met to review draft documents. A few changes needed before signing."),
        ]
        for task_title, sh_name, days_ago, method, responded, resp_date, notes in followup_data:
            FollowUp.objects.create(
                task=tasks[task_title], stakeholder=stakeholders[sh_name],
                outreach_date=now + timedelta(days=days_ago),
                method=method, response_received=responded,
                response_date=resp_date, notes_text=notes,
            )

        self.stdout.write("Creating cash flow entries...")
        cf_data = [
            # Recent actual entries
            ("Oak Ave rent received", Decimal("1800.00"), "inflow", "Rental Income", today - timedelta(days=2), False,
             None, "1200 Oak Avenue", None, "February rent from current tenant."),
            ("Elm St Unit A rent", Decimal("1400.00"), "inflow", "Rental Income", today - timedelta(days=5), False,
             "Tom Driscoll", "450 Elm Street", None, "Split 50/50 with Tom."),
            ("Elm St Unit B rent", Decimal("1350.00"), "inflow", "Rental Income", today - timedelta(days=5), False,
             "Tom Driscoll", "450 Elm Street", None, "Split 50/50 with Tom."),
            ("Oak Ave mortgage payment", Decimal("2100.00"), "outflow", "Mortgage", today - timedelta(days=10), False,
             "Janet Cobb", "1200 Oak Avenue", "First National - Oak Ave Mortgage", "Monthly P&I."),
            ("Elm St mortgage payment", Decimal("2800.00"), "outflow", "Mortgage", today - timedelta(days=10), False,
             "Janet Cobb", "450 Elm Street", "First National - Elm St Mortgage", "Monthly P&I."),
            ("Huang bridge loan interest", Decimal("1583.33"), "outflow", "Loan Payment", today - timedelta(days=8), False,
             "Victor Huang", None, "Huang Bridge Loan - Magnolia", "Monthly interest only."),
            ("Vehicle loan payment", Decimal("750.00"), "outflow", "Loan Payment", today - timedelta(days=12), False,
             None, None, "Vehicle Loan - F-150", ""),
            ("Property insurance - Oak Ave", Decimal("245.00"), "outflow", "Insurance", today - timedelta(days=15), False,
             None, "1200 Oak Avenue", None, "Monthly premium."),
            ("Property insurance - Elm St", Decimal("310.00"), "outflow", "Insurance", today - timedelta(days=15), False,
             None, "450 Elm Street", None, "Monthly premium."),
            ("Reed & Associates retainer", Decimal("3500.00"), "outflow", "Legal Fees", today - timedelta(days=20), False,
             "Marcus Reed", None, None, "Monthly retainer for Holston eviction + Cedar Lane."),
            ("Calloway - Oak Ave renovation", Decimal("4800.00"), "outflow", "Renovation", today - timedelta(days=7), False,
             "James Calloway", "1200 Oak Avenue", None, "Progress payment for bathroom renovation."),
            ("Vanguard monthly investment", Decimal("2000.00"), "outflow", "Investment", today - timedelta(days=1), False,
             "Derek Vasquez", None, None, "Monthly dollar-cost average into index fund."),
            ("Whitfield appraisal fee", Decimal("450.00"), "outflow", "Professional Services", today - timedelta(days=12), False,
             "Karen Whitfield", "1200 Oak Avenue", None, "Appraisal for refinance consideration."),
            # Projected entries
            ("Magnolia closing - down payment", Decimal("250000.00"), "outflow", "Acquisition", today + timedelta(days=25), True,
             "Nina Patel", "3300 Magnolia Blvd", None, "Due at closing. Split with Nina."),
            ("Magnolia closing - closing costs", Decimal("18500.00"), "outflow", "Acquisition", today + timedelta(days=25), True,
             None, "3300 Magnolia Blvd", None, "Estimated title, recording, legal fees."),
            ("Expected Oak Ave rent - March", Decimal("1800.00"), "inflow", "Rental Income", today + timedelta(days=28), True,
             None, "1200 Oak Avenue", None, ""),
            ("Expected Elm St rent - March", Decimal("2750.00"), "inflow", "Rental Income", today + timedelta(days=28), True,
             "Tom Driscoll", "450 Elm Street", None, "Both units combined."),
            ("Oak Ave mortgage - March", Decimal("2100.00"), "outflow", "Mortgage", today + timedelta(days=22), True,
             "Janet Cobb", "1200 Oak Avenue", "First National - Oak Ave Mortgage", ""),
            ("Elm St mortgage - March", Decimal("2800.00"), "outflow", "Mortgage", today + timedelta(days=15), True,
             "Janet Cobb", "450 Elm Street", "First National - Elm St Mortgage", ""),
            ("Huang bridge interest - March", Decimal("1583.33"), "outflow", "Loan Payment", today + timedelta(days=8), True,
             "Victor Huang", None, "Huang Bridge Loan - Magnolia", ""),
            ("NP Investments annual distribution", Decimal("4500.00"), "inflow", "Investment Income", today + timedelta(days=60), True,
             "Nina Patel", None, None, "Estimated annual distribution from Fund II."),
            ("Property tax - all properties", Decimal("8200.00"), "outflow", "Taxes", today + timedelta(days=45), True,
             None, None, None, "Quarterly property tax bill across all holdings."),
        ]
        for desc, amt, etype, cat, dt, proj, sh_name, prop_name, loan_name, notes in cf_data:
            CashFlowEntry.objects.create(
                description=desc, amount=amt, entry_type=etype, category=cat,
                date=dt, is_projected=proj,
                related_stakeholder=stakeholders.get(sh_name),
                related_property=properties.get(prop_name) if prop_name else None,
                related_loan=loans.get(loan_name) if loan_name else None,
                notes_text=notes,
            )

        self.stdout.write("Creating notes...")
        note_data = [
            ("Holston eviction strategy call with Marcus", "call", now - timedelta(days=2),
             "Called Marcus to discuss eviction strategy.\n\n"
             "Key points:\n"
             "- Hearing likely in 3-4 weeks\n"
             "- Judge typically rules in landlord's favor with proper documentation\n"
             "- We have strong case: signed lease, payment history, demand letter\n"
             "- Marcus recommends also pursuing judgment for back rent\n"
             "- Total exposure: $4,200 back rent + ~$3,500 legal fees\n\n"
             "Action items:\n"
             "- Gather last 12 months bank statements showing no payments\n"
             "- Get written statement from property manager about condition of unit",
             ["Marcus Reed"], ["Marcus Reed", "Ray Holston"], ["Holston Eviction - 1200 Oak Ave"],
             ["1200 Oak Avenue"], ["Follow up with Marcus on Holston hearing date"]),

            ("Magnolia Blvd walkthrough notes", "meeting", now - timedelta(days=10),
             "Walked the property with Nina and Sandra.\n\n"
             "Observations:\n"
             "- Building is in good condition overall\n"
             "- HVAC systems (3 units) are 8 years old - budget for replacement in 3-5 years\n"
             "- Parking lot needs resealing - est $12k\n"
             "- Current tenants are month-to-month, rents below market by ~15%\n"
             "- Clear upside: raise rents gradually after closing\n\n"
             "Nina's take: strong buy at asking price. I agree.\n\n"
             "Next steps: finalize financing, review seller's disclosures, schedule closing.",
             ["Nina Patel", "Sandra Liu"], ["Nina Patel", "Sandra Liu"],
             ["Magnolia Blvd Acquisition - Due Diligence"], ["3300 Magnolia Blvd"],
             ["Review Magnolia closing documents"]),

            ("Quarterly portfolio review with Derek", "meeting", now - timedelta(days=1),
             "Met with Derek for Q4 review.\n\n"
             "Portfolio summary:\n"
             "- Total liquid investments: ~$367k\n"
             "- YTD return: 11.2% (vs S&P 10.8%)\n"
             "- Vanguard Total Market: strong performance, continue DCA\n"
             "- Municipal bonds: providing steady 3.8% tax-free yield\n"
             "- Bitcoin: up 45% since purchase, consider trimming\n\n"
             "Derek's recommendations:\n"
             "1. Shift 10% from equities to bonds (rising rate environment)\n"
             "2. Take partial profits on Bitcoin above $70k\n"
             "3. Max out IRA contribution before April deadline\n"
             "4. Consider tax-loss harvesting in taxable account",
             ["Derek Vasquez"], ["Derek Vasquez"], [], [], ["Quarterly portfolio review follow-up"]),

            ("Cedar Lane mediation prep", "research", now - timedelta(days=15),
             "Research for upcoming mediation on boundary dispute.\n\n"
             "Our position:\n"
             "- 2024 survey clearly shows fence is 100% on our property\n"
             "- Original deed metes and bounds support our survey\n"
             "- Fence has been in place since 2019 (5 years)\n"
             "- Neighbor's survey (done by a less reputable firm) shows 3ft encroachment\n\n"
             "Legal strategy:\n"
             "- Lead with our survey + deed\n"
             "- Offer to split cost of a third independent survey\n"
             "- If mediation fails, file for declaratory judgment\n"
             "- Marcus estimates trial would cost $15-20k\n\n"
             "Ideal outcome: neighbor accepts our survey, we avoid court costs.",
             [], [], ["Cedar Lane Boundary Dispute"], ["890 Cedar Lane"],
             ["File property tax protest - Cedar Lane"]),

            ("Elm St roof concerns", "general", now - timedelta(days=6),
             "Tom mentioned during our last call that Unit B tenant reported a small leak "
             "in the back bedroom during the last heavy rain.\n\n"
             "Need to:\n"
             "1. Get Calloway or another contractor to inspect\n"
             "2. Check if this is covered under existing homeowner's insurance\n"
             "3. Get 2-3 quotes for repair/replacement\n"
             "4. Discuss cost split with Tom (50/50 per our agreement)\n\n"
             "Roof is ~18 years old. May be time for full replacement rather than patching.",
             [], ["Tom Driscoll", "James Calloway"], [], ["450 Elm Street"],
             ["Schedule roof inspection - Elm St"]),

            ("Estate planning meeting notes", "meeting", now - timedelta(days=20),
             "Annual review with Dr. Helen Park.\n\n"
             "Updates made:\n"
             "- Revocable living trust updated with new property acquisitions\n"
             "- Added 3300 Magnolia Blvd (pending closing) to trust schedule\n"
             "- Updated beneficiary designations on all investment accounts\n"
             "- Renewed power of attorney documents\n"
             "- Healthcare directive remains current\n\n"
             "Outstanding items:\n"
             "- Need to sign final documents at Helen's office\n"
             "- Consider forming LLC for Magnolia Blvd (discuss with Sandra)\n"
             "- Review life insurance coverage given increased asset base",
             ["Dr. Helen Park"], ["Dr. Helen Park"], ["Estate Plan Update"], [],
             ["Update estate plan documents"]),

            ("Huang bridge loan terms review", "research", now - timedelta(days=25),
             "Reviewed the terms on Victor Huang's bridge loan.\n\n"
             "Terms:\n"
             "- Principal: $200,000\n"
             "- Rate: 9.5% (interest only)\n"
             "- Term: 6 months\n"
             "- Monthly payment: $1,583.33\n"
             "- Maturity: ~5 months from now\n"
             "- Prepayment penalty: None after 90 days\n\n"
             "Total interest cost if held to maturity: ~$9,500\n"
             "Need to refinance ASAP. Talk to Janet about rolling into a conventional loan "
             "once Magnolia closes and we have rental income to show.",
             [], ["Victor Huang", "Janet Cobb"], [], [],
             ["Refinance Huang bridge loan"]),

            ("Riverside development feasibility", "research", now - timedelta(days=40),
             "Researched development options for 15 Riverside Dr.\n\n"
             "Zoning: Currently agricultural, requesting residential\n"
             "Lot size: 0.8 acres\n"
             "Estimated build cost: $280-350k for single family\n"
             "Comparable sales in area: $450-520k\n"
             "Timeline: 6-8 months for permitting + 10-12 months construction\n\n"
             "Pros: Good margins, growing area, no HOA restrictions\n"
             "Cons: Long timeline, capital intensive, zoning not guaranteed\n\n"
             "Decision: Proceed with zoning application, then reassess based on approval and "
             "available capital after Magnolia closing.",
             [], [], ["Riverside Zoning Application"], ["15 Riverside Dr"],
             ["Prepare zoning hearing materials"]),

            ("Call with Tom about Elm St expenses", "call", now - timedelta(days=22),
             "Quick call with Tom about Q4 expenses.\n\n"
             "He reported:\n"
             "- Plumbing repair Unit A: $380\n"
             "- Landscaping Q4: $600\n"
             "- Pest control: $150\n"
             "- General maintenance: $425\n"
             "- Total: $1,555 (my half: $777.50)\n\n"
             "Asked him to send receipts for everything. He said he'd email them over. "
             "Still waiting as of today.",
             ["Tom Driscoll"], ["Tom Driscoll"], [], ["450 Elm Street"],
             ["Review Q4 Elm St expense report"]),

            ("Quick note - Bitcoin price alert", "general", now - timedelta(hours=6),
             "Bitcoin hit $68,500 today. Getting close to my $70k target for trimming. "
             "Set a limit sell for 0.1 BTC at $71,000 on Coinbase. "
             "Will reassess remaining position after.",
             [], [], [], [], ["Research Bitcoin exit strategy"]),
        ]
        for title, ntype, dt, content, participants, rel_sh, rel_lm, rel_props, rel_tasks in note_data:
            note = Note.objects.create(
                title=title, note_type=ntype, date=dt, content=content,
            )
            for name in participants:
                note.participants.add(stakeholders[name])
            for name in rel_sh:
                note.related_stakeholders.add(stakeholders[name])
            for t in rel_lm:
                note.related_legal_matters.add(legal_matters[t])
            for p in rel_props:
                note.related_properties.add(properties[p])
            for t in rel_tasks:
                note.related_tasks.add(tasks[t])

        # Print summary
        self.stdout.write(self.style.SUCCESS(
            f"\nSample data loaded successfully!\n"
            f"  Stakeholders:   {Stakeholder.objects.count()}\n"
            f"  Relationships:  {Relationship.objects.count()}\n"
            f"  Contact Logs:   {ContactLog.objects.count()}\n"
            f"  Properties:     {RealEstate.objects.count()}\n"
            f"  Investments:    {Investment.objects.count()}\n"
            f"  Loans:          {Loan.objects.count()}\n"
            f"  Legal Matters:  {LegalMatter.objects.count()}\n"
            f"  Evidence:       {Evidence.objects.count()}\n"
            f"  Tasks:          {Task.objects.count()}\n"
            f"  Follow-ups:     {FollowUp.objects.count()}\n"
            f"  Cash Flow:      {CashFlowEntry.objects.count()}\n"
            f"  Notes:          {Note.objects.count()}"
        ))
