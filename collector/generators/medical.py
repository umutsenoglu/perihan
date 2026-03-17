"""Generate fictional medical documents — personal to the main persona."""

import random
from .base import llm_generate, random_date, pick_size, get_persona_context, PERSONA, CONTACTS, fetch_nhs_health_info, fetch_wikipedia_article, pick_storyline, get_storyline_context

# Medical scenarios tied to the persona's life
PERSONAL_SCENARIOS = [
    {"patient": PERSONA["name"], "condition": "asthma review", "doctor": CONTACTS["doctor"],
     "context": "Annual asthma review, been using blue inhaler more often lately due to cycling in cold weather"},
    {"patient": PERSONA["name"], "condition": "lower back pain", "doctor": CONTACTS["doctor"],
     "context": "Recurring lower back pain from long hours at desk, referred to physiotherapy"},
    {"patient": PERSONA["name"], "condition": "seasonal allergies", "doctor": CONTACTS["doctor"],
     "context": "Spring allergies flaring up, needs prescription renewal for antihistamines"},
    {"patient": PERSONA["name"], "condition": "routine blood test", "doctor": CONTACTS["doctor"],
     "context": "Annual health check, cholesterol slightly elevated last time"},
    {"patient": PERSONA["name"], "condition": "dental checkup", "doctor": CONTACTS["dentist"],
     "context": "6-monthly dental checkup, wisdom tooth being monitored"},
    {"patient": "Lily Marsh", "condition": "childhood vaccination", "doctor": "Dr. Patel",
     "context": "Year 3 booster vaccinations, parent Ethan brought her in"},
    {"patient": "Max Marsh", "condition": "ear infection", "doctor": "Dr. Patel",
     "context": "Recurrent ear infections, third episode this winter, might need ENT referral"},
    {"patient": "Max Marsh", "condition": "nursery health form", "doctor": "Dr. Patel",
     "context": "Annual health form for Little Stars Nursery, no major concerns"},
    {"patient": "Lily Marsh", "condition": "eye test", "doctor": "Ms. Roberts (optometrist)",
     "context": "School flagged possible vision issues, sitting close to whiteboard"},
    {"patient": PERSONA["name"], "condition": "stress and anxiety", "doctor": CONTACTS["doctor"],
     "context": "Work deadline pressure, mother's health worry, sleep problems for 3 weeks"},
    {"patient": "Claire Marsh", "condition": "knee pain", "doctor": CONTACTS["doctor"],
     "context": "Left knee pain after playground supervision at school, possible ligament strain"},
    {"patient": PERSONA["name"], "condition": "travel vaccinations", "doctor": "Travel Clinic nurse",
     "context": "Planning summer trip to Portugal, checking if any boosters needed"},
]

# Generic medical scenarios (15%)
GENERIC_SCENARIOS = [
    {"patient": None, "condition": "type 2 diabetes management", "doctor": None, "context": ""},
    {"patient": None, "condition": "vitamin D deficiency", "doctor": None, "context": ""},
    {"patient": None, "condition": "migraine headaches", "doctor": None, "context": ""},
    {"patient": None, "condition": "physical exam", "doctor": None, "context": ""},
]

DOC_TYPES = [
    "GP visit notes", "prescription", "blood test results", "referral letter",
    "discharge summary", "vaccination record", "specialist report",
    "physiotherapy notes", "dental report", "optometry report",
]


async def generate() -> dict:
    """Generate a fictional medical document tied to persona's life."""
    is_personal = random.random() < 0.85
    date = random_date()
    doc_type = random.choice(DOC_TYPES)
    size_label, min_w, max_w = pick_size()

    use_storyline = is_personal and random.random() < 0.30
    storyline_ctx = ""

    if use_storyline:
        # Only some storylines have medical angles
        medical_storylines = ["mums_health", "lily_school", "work_migration"]
        storyline = pick_storyline()
        if storyline["id"] in medical_storylines:
            storyline_ctx = get_storyline_context(storyline)
            patient = PERSONA["name"]
            condition = {"mums_health": "dementia care referral", "lily_school": "child stress assessment",
                         "work_migration": "stress and insomnia"}[storyline["id"]]
            doctor = CONTACTS["doctor"]
            life_context = storyline["summary"][:200]
            persona_ctx = get_persona_context()
        else:
            use_storyline = False

    if not use_storyline and is_personal:
        scenario = random.choice(PERSONAL_SCENARIOS)
        patient = scenario["patient"]
        condition = scenario["condition"]
        doctor = scenario["doctor"]
        life_context = scenario["context"]
        persona_ctx = get_persona_context()
    elif not use_storyline:
        scenario = random.choice(GENERIC_SCENARIOS)
        patient = f"{random.choice(['John','Emma','David','Sarah'])} {random.choice(['Smith','Brown','Wilson'])}"
        condition = scenario["condition"]
        doctor = f"Dr. {random.choice(['Ahmed','Wilson','Kovacs'])}"
        life_context = ""
        persona_ctx = ""

    facility = random.choice([
        "Whittington Hospital", "North London Medical Centre",
        "Archway Surgery", "Highgate Family Practice",
        "Royal Free Hospital", "Barnet General Hospital",
    ]) if is_personal else random.choice(["City General Hospital", "Memorial Medical Center"])

    size_guidance = {
        "tiny": "Just a brief prescription slip or a single lab result — very short.",
        "short": "A concise doctor visit note or a single-page report.",
        "medium": "A standard medical report with findings, assessment, and plan.",
        "long": "A detailed report with full history, examination, differential diagnosis, treatment plan, and follow-up.",
        "huge": "An extensive medical case file with multiple visit notes, lab history, specialist consultations, and treatment timeline.",
        "massive": "A comprehensive patient medical history file spanning years — multiple conditions, referrals, test results, prescriptions, specialist letters, and GP notes all compiled together.",
    }

    # Try to fetch real NHS health info for this condition
    nhs_slugs = {
        "asthma review": "asthma",
        "seasonal allergies": "allergies",
        "lower back pain": "back-pain",
        "ear infection": "ear-infections",
        "childhood vaccination": "vaccinations",
        "stress and anxiety": "generalised-anxiety-disorder",
        "knee pain": "knee-pain",
        "travel vaccinations": "travel-vaccinations",
        "routine blood test": "blood-tests",
    }
    nhs_content = ""
    source = "generated"
    slug = nhs_slugs.get(condition, "")
    if slug and random.random() < 0.6:
        nhs_content = await fetch_nhs_health_info(slug)
        if nhs_content:
            source = "internet"

    # Also try Wikipedia for the condition
    if not nhs_content and random.random() < 0.4:
        _, wiki_text = await fetch_wikipedia_article(condition)
        if wiki_text:
            nhs_content = wiki_text[:20000]
            source = "internet"

    personal_note = ""
    if is_personal and life_context:
        personal_note = f"""
{persona_ctx}
{storyline_ctx}

Patient context: {life_context}
This is a real medical document from their life. Include NHS references where appropriate.
The document should feel authentic — like something you'd find in their filing cabinet or NHS app."""

    if nhs_content:
        # Use real medical info as the base, wrap in a personal document
        prompt = f"""Using the real NHS/medical information below, create a medical document
that {patient} received or saved.

Type: {doc_type}
Patient: {patient}
Doctor: {doctor}
Facility: {facility}
Date: {date.strftime('%Y-%m-%d')}
Condition: {condition}

Incorporate the real medical facts from the reference info below into the document.
{size_guidance[size_label]}
Target length: {min_w}-{max_w} words.
{personal_note}

REAL MEDICAL REFERENCE INFO:
{nhs_content[:20000]}

Create the document using this real information. Add patient-specific details
(measurements, dates, dosages) but keep the medical facts real.
This is FICTIONAL test data - patient details are made up.
Format as a plain text medical document."""
    else:
        prompt = f"""Generate a realistic but completely fictional medical document.

Type: {doc_type}
Patient: {patient}
Doctor: {doctor}
Facility: {facility}
Date: {date.strftime('%Y-%m-%d')}
Condition: {condition}

{size_guidance[size_label]}
Target length: {min_w}-{max_w} words.
{personal_note}

Make it realistic with medical terminology, specific measurements/values.
This is FICTIONAL test data - all names and data are made up.
Format as a plain text medical document with headers and sections."""

    max_tokens = min(max_w * 3, 65000)
    content = await llm_generate(prompt, temperature=0.8, max_tokens=max_tokens)

    filename = f"medical_{doc_type.replace(' ', '_')}_{date.strftime('%Y%m%d')}_{random.randint(100,999)}.txt"

    return {
        "filename": filename,
        "content": content,
        "description": f"Medical {doc_type} for {patient} - {condition} [{size_label}]",
        "category": "medical",
        "source": source,
    }
