"""Generate fictional financial documents — personal to the main persona."""

import random
from .base import llm_generate, random_date, pick_size, get_persona_context, PERSONA, CONTACTS, pick_storyline, get_storyline_context

PERSONAL_SCENARIOS = [
    {"type": "bank_statement", "company": "Barclays", "context": "Monthly current account statement showing mortgage payments, Tesco shops, nursery fees, and transfers"},
    {"type": "credit_card_statement", "company": "Barclays", "context": "Monthly Visa statement with Amazon purchases, petrol, restaurants, AquaWorld fish shop"},
    {"type": "mortgage_statement", "company": "Barclays Mortgages", "context": "Annual mortgage statement for the North London semi-detached, showing remaining balance and interest"},
    {"type": "payslip", "company": "FinEdge Technologies Ltd", "context": "Monthly payslip showing salary, tax, NI, pension contribution to Scottish Widows"},
    {"type": "pension_statement", "company": "Scottish Widows", "context": "Annual pension statement showing employer and employee contributions, projected retirement income"},
    {"type": "ISA_statement", "company": "Vanguard", "context": "Stocks and shares ISA annual statement with fund performance"},
    {"type": "utility_bill", "company": "British Gas", "context": "Quarterly gas and electricity bill for the house"},
    {"type": "utility_bill", "company": "Thames Water", "context": "Water bill for the semi-detached"},
    {"type": "council_tax_bill", "company": "London Borough of Haringey", "context": "Annual council tax bill, Band D property"},
    {"type": "car_insurance", "company": "Direct Line", "context": "Annual car insurance renewal for the 2019 VW Golf"},
    {"type": "nursery_invoice", "company": "Little Stars Nursery", "context": "Monthly nursery fees for Max, showing government 15-hour funding applied"},
    {"type": "freelance_invoice", "company": "Ethan Marsh (self)", "context": "Invoice sent to a client for freelance weekend development work"},
    {"type": "tax_return_summary", "company": "HMRC", "context": "Self-assessment tax return summary showing employment income plus freelance earnings"},
    {"type": "home_insurance", "company": "Aviva", "context": "Buildings and contents insurance for the house"},
    {"type": "renovation_quote", "company": "BuildRight Ltd", "context": "Detailed kitchen renovation quote from Steve — cabinets, worktops, plumbing, electrics"},
]

GENERIC_SCENARIOS = [
    {"type": "invoice", "company": "TechCorp Solutions"},
    {"type": "bank_statement", "company": "First National Bank"},
    {"type": "expense_report", "company": "Global Industries"},
]


async def generate() -> dict:
    """Generate a fictional financial document from persona's life."""
    is_personal = random.random() < 0.85
    date = random_date()
    size_label, min_w, max_w = pick_size()

    use_storyline = is_personal and random.random() < 0.40
    storyline_ctx = ""

    if use_storyline:
        storyline = pick_storyline()
        storyline_ctx = get_storyline_context(storyline)
        # Generate a financial document related to this storyline
        doc_type = random.choice(["invoice", "bank_statement", "expense_report", "payment_receipt"])
        company = storyline["people"][0] if storyline["people"] else "Various"
        life_context = f"Financial document related to: {storyline['title']}"
        persona_ctx = get_persona_context()
        currency = "GBP"

        personal_note = f"""
{persona_ctx}
{storyline_ctx}

This is {PERSONA['name']}'s actual financial document.
Context: {life_context}
Use the EXACT amounts, reference numbers, and details from the storyline above.
Use realistic UK financial formatting — GBP, sort codes, account numbers (masked),
NI numbers (masked), tax codes. Include their actual address area (North London).
This should look like a real document from their filing cabinet or banking app."""

    elif is_personal:
        scenario = random.choice(PERSONAL_SCENARIOS)
        doc_type = scenario["type"]
        company = scenario["company"]
        life_context = scenario["context"]
        persona_ctx = get_persona_context()
        currency = "GBP"

        personal_note = f"""
{persona_ctx}

This is {PERSONA['name']}'s actual financial document.
Context: {life_context}
Use realistic UK financial formatting — GBP, sort codes, account numbers (masked),
NI numbers (masked), tax codes. Include their actual address area (North London).
This should look like a real document from their filing cabinet or banking app."""
    else:
        scenario = random.choice(GENERIC_SCENARIOS)
        doc_type = scenario["type"]
        company = scenario["company"]
        currency = random.choice(["USD", "EUR", "GBP"])
        personal_note = ""

    size_guidance = {
        "tiny": "A very brief receipt or payment confirmation.",
        "short": "A concise one-page bill or simple statement.",
        "medium": "A standard financial document with line items and totals.",
        "long": "A detailed multi-page statement with many transactions and breakdowns.",
        "huge": "An exhaustive financial document — full annual statement with 50+ transactions or comprehensive tax summary.",
        "massive": "A comprehensive financial archive — multiple years of statements, hundreds of transactions, full tax returns, pension summaries, mortgage documents, and investment portfolio all compiled together.",
    }

    prompt = f"""Generate a realistic but completely fictional financial document.

Type: {doc_type.replace('_', ' ')}
Account holder: {PERSONA['name'] if is_personal else 'John Smith'}
Company: {company}
Date: {date.strftime('%Y-%m-%d')}
Currency: {currency}

{size_guidance[size_label]}
Target length: {min_w}-{max_w} words.
{personal_note}

Include specific amounts, masked account numbers, dates, reference numbers.
This is FICTIONAL test data. Format as plain text."""

    max_tokens = min(max_w * 3, 65000)
    content = await llm_generate(prompt, temperature=0.8, max_tokens=max_tokens)
    date_str = date.strftime('%Y%m%d')
    filename = f"finance_{doc_type}_{date_str}_{random.randint(100,999)}.txt"

    return {
        "filename": filename,
        "content": content,
        "description": f"Finance: {doc_type.replace('_', ' ')} from {company} [{size_label}]",
        "category": "finance",
        "source": "generated",
    }
