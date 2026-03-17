"""Generate fictional legal documents — personal to the main persona."""

import random
from .base import llm_generate, random_date, pick_size, get_persona_context, PERSONA, CONTACTS, fetch_gov_uk_info, fetch_wikipedia_article, pick_storyline, get_storyline_context

# Legal scenarios from the persona's life
PERSONAL_SCENARIOS = [
    {"type": "solicitor_letter", "case": "neighbor fence boundary dispute",
     "lawyer": CONTACTS["lawyer"], "opponent": "Dave and Sandra Mitchell",
     "context": "Neighbors replaced shared fence without consent, moved boundary 30cm into Ethan's garden"},
    {"type": "property_valuation", "case": "fence dispute evidence",
     "lawyer": CONTACTS["lawyer"], "opponent": "Dave Mitchell",
     "context": "Surveyor report needed to establish original boundary line"},
    {"type": "inheritance_document", "case": "property transfer after father's death",
     "lawyer": CONTACTS["property_lawyer"], "opponent": None,
     "context": "Father George's house in Bristol needs to be transferred to three siblings via probate"},
    {"type": "power_of_attorney", "case": "lasting power of attorney for mother",
     "lawyer": CONTACTS["property_lawyer"], "opponent": None,
     "context": "Ethan setting up LPA for mother Janet as her health declines"},
    {"type": "citizenship_application", "case": "British citizenship naturalization",
     "lawyer": None, "opponent": None,
     "context": "Gathering documents for Life in the UK test passed, applying for naturalization"},
    {"type": "employment_contract_review", "case": "new role contract terms",
     "lawyer": None, "opponent": None,
     "context": "Ethan reviewing updated employment contract after promotion, non-compete clause concern"},
    {"type": "tenancy_agreement", "case": "rental property inherited from father",
     "lawyer": CONTACTS["property_lawyer"], "opponent": None,
     "context": "Existing tenant in father's Bristol house, need to update lease after probate"},
    {"type": "court_notice", "case": "neighbor fence dispute escalation",
     "lawyer": CONTACTS["lawyer"], "opponent": "Dave Mitchell",
     "context": "Small claims court date set for the boundary dispute"},
    {"type": "insurance_claim", "case": "car insurance claim after minor accident",
     "lawyer": None, "opponent": "Third party driver",
     "context": "VW Golf rear-ended in Tesco car park, dealing with insurance"},
    {"type": "school_complaint", "case": "formal complaint about playground supervision",
     "lawyer": None, "opponent": None,
     "context": "Lily came home with a bruise, school supervision inadequate during lunch break"},
]

GENERIC_SCENARIOS = [
    {"type": "court_ruling", "case": "landlord-tenant rent dispute"},
    {"type": "settlement_agreement", "case": "employment termination"},
    {"type": "cease_and_desist", "case": "noise complaint"},
]


async def generate() -> dict:
    """Generate a fictional legal document from persona's life."""
    is_personal = random.random() < 0.85
    date = random_date()
    size_label, min_w, max_w = pick_size()

    use_storyline = is_personal and random.random() < 0.40
    storyline_ctx = ""

    if use_storyline:
        storyline = pick_storyline()
        storyline_ctx = get_storyline_context(storyline)
        # Generate a legal document for this storyline
        doc_type = random.choice(["solicitor_letter", "court_notice", "settlement_agreement",
                                   "legal_notice", "witness_statement", "invoice"])
        case_theme = storyline["title"].lower()
        lawyer = storyline["people"][0] if storyline["people"] else ""
        opponent = storyline["people"][1] if len(storyline["people"]) > 1 else ""
        life_context = storyline["summary"][:200]
        persona_ctx = get_persona_context()

        personal_note = f"""
{persona_ctx}
{storyline_ctx}

This is a legal document from {PERSONA['name']}'s personal files.
Use the EXACT reference numbers, dates, amounts, and names from the storyline above.
Make it feel like a real document from their solicitor's office or their own records.
Include specific addresses (North London area), case reference numbers, and realistic UK legal formatting."""

    elif is_personal:
        scenario = random.choice(PERSONAL_SCENARIOS)
        doc_type = scenario["type"]
        case_theme = scenario["case"]
        lawyer = scenario.get("lawyer", "")
        opponent = scenario.get("opponent", "")
        life_context = scenario.get("context", "")
        persona_ctx = get_persona_context()

        personal_note = f"""
{persona_ctx}

This is a legal document from {PERSONA['name']}'s personal files.
Life context: {life_context}
Make it feel like a real document from their solicitor's office or their own records.
Include specific addresses (North London area), NHS numbers where relevant,
case reference numbers, and realistic UK legal formatting."""
    else:
        doc_type = random.choice(GENERIC_SCENARIOS)["type"]
        case_theme = random.choice(GENERIC_SCENARIOS)["case"]
        lawyer = f"Atty. {random.choice(['Smith','Demir','Johnson'])}"
        opponent = ""
        personal_note = ""

    case_number = f"{random.randint(2023,2026)}/{random.choice('ABCDE')}-{random.randint(1000,9999)}"

    size_guidance = {
        "tiny": "A brief legal notice or short formal letter.",
        "short": "A concise one-page legal letter or notice.",
        "medium": "A standard legal document with sections and references.",
        "long": "A detailed legal document with extensive background, arguments, and specific demands.",
        "huge": "A comprehensive legal case file with full procedural history, evidence references, and formal orders.",
        "massive": "An exhaustive legal bundle — multiple documents compiled together: correspondence, court filings, witness statements, evidence schedules, solicitor invoices, and case chronology.",
    }

    # Try to fetch real legal info from GOV.UK or Wikipedia
    legal_search_map = {
        "neighbor fence boundary dispute": "boundary disputes neighbours",
        "British citizenship naturalization": "apply british citizenship",
        "property transfer after father's death": "probate property transfer",
        "car insurance claim after minor accident": "car insurance claim",
        "employment contract review": "employment contract rights",
        "school complaint": "school complaints procedure",
    }
    source = "generated"
    real_info = ""

    search_term = legal_search_map.get(case_theme, "")
    if search_term and random.random() < 0.5:
        gov_info = await fetch_gov_uk_info(search_term)
        if gov_info:
            real_info = gov_info
            source = "internet"
        else:
            _, wiki = await fetch_wikipedia_article(search_term)
            if wiki:
                real_info = wiki[:20000]
                source = "internet"

    real_info_section = ""
    if real_info:
        real_info_section = f"""
Use this real legal reference information to make the document accurate:
{real_info[:20000]}
"""

    prompt = f"""Generate a realistic but completely fictional legal document.

Type: {doc_type.replace('_', ' ')}
Case: {case_theme}
Case number: {case_number}
Main party: {PERSONA['name'] if is_personal else 'John Smith'}
{f'Opponent: {opponent}' if opponent else ''}
{f'Lawyer: {lawyer}' if lawyer else ''}
Date: {date.strftime('%Y-%m-%d')}

{size_guidance[size_label]}
Target length: {min_w}-{max_w} words.
{personal_note}
{real_info_section}

This is FICTIONAL test data. Format as plain text legal document."""

    max_tokens = min(max_w * 3, 65000)
    content = await llm_generate(prompt, temperature=0.7, max_tokens=max_tokens)

    date_str = date.strftime('%Y%m%d')
    filename = f"legal_{doc_type}_{date_str}_{random.randint(100,999)}.txt"

    return {
        "filename": filename,
        "content": content,
        "description": f"Legal {doc_type.replace('_', ' ')} - {case_theme[:40]} [{size_label}]",
        "category": "legal",
        "source": source,
    }
