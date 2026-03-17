"""Generate fictional calendar items — from the persona's actual schedule."""

import random
from .base import llm_generate, random_date, pick_size, get_persona_context, PERSONA, CONTACTS, pick_storyline, get_storyline_context

# Real-life calendar event types
PERSONAL_EVENTS = [
    "Dr. Patel — asthma review",
    "Lily's parents evening at QPA",
    "Kitchen renovation meeting with Steve (BuildRight)",
    "Work standup — Payments Team",
    "Cycling with Marcus — Hampstead Heath",
    "Max — Little Stars Nursery pickup",
    "Helen Crawford — fence dispute update call",
    "Video call with mum (Bristol)",
    "Lily's swimming lesson",
    "PTA meeting at QPA",
    "Dentist — Dr. Kim checkup",
    "Car MOT — VW Golf",
    "Freelance project deadline",
    "Claire's birthday dinner",
    "Barclays mortgage review appointment",
    "Grocery run — Tesco",
    "Max's vaccination — Dr. Patel",
    "Flight to Lisbon — summer holiday",
    "Lily's birthday party — science theme",
    "Work quarterly review with Richard",
    "Physio appointment — lower back",
    "Fish tank maintenance day",
    "Hannah visiting from Manchester",
    "Court date — fence dispute",
]


async def generate() -> dict:
    """Generate fictional calendar items from persona's life."""
    size_label, min_w, max_w = pick_size()
    start_date = random_date()

    event_counts = {"tiny": (1, 2), "short": (3, 5), "medium": (5, 10), "long": (12, 25), "huge": (30, 60), "massive": (80, 200)}
    min_events, max_events = event_counts[size_label]
    num_events = random.randint(min_events, max_events)

    span_options = {
        "tiny": "a single day",
        "short": "2-3 days",
        "medium": "one week",
        "long": "two weeks",
        "huge": "a full month",
        "massive": "three months",
    }

    persona_ctx = get_persona_context()

    # 40% chance to include storyline-related events
    storyline_ctx = ""
    if random.random() < 0.40:
        storyline = pick_storyline()
        storyline_ctx = get_storyline_context(storyline)

    # Pick some events for variety
    selected_events = random.sample(PERSONAL_EVENTS, min(num_events, len(PERSONAL_EVENTS)))

    prompt = f"""Generate a realistic fictional calendar export for a person.

{persona_ctx}
{storyline_ctx}

Starting date: {start_date.strftime('%Y-%m-%d')}
Time span: {span_options[size_label]}
Number of events: approximately {num_events}

Target length: {min_w}-{max_w} words.

Include events like: {', '.join(selected_events[:8])}

Format each event:
---
Event: [title]
Date: YYYY-MM-DD
Time: HH:MM - HH:MM
Location: [specific place — North London addresses, QPA school, Whittington Hospital, etc.]
Notes: [personal reminders like "bring Lily's PE kit", "ask about fence survey results"]
---

Mix of:
- Work events (standups, 1:1 with Richard, sprint reviews)
- Family (school pickup, nursery, kids activities)
- Personal (gym, cycling, doctor appointments)
- Recurring events (weekly standup, Lily's swimming Tuesdays)
- Occasional [CANCELLED] events
- Some with attendees listed

Write entirely in English.

This is FICTIONAL test data. Format as plain text calendar export."""

    max_tokens = min(max_w * 3, 65000)
    content = await llm_generate(prompt, temperature=0.9, max_tokens=max_tokens)
    date_str = start_date.strftime('%Y%m%d')
    filename = f"calendar_{span_options[size_label].replace(' ', '_')}_{date_str}_{random.randint(100, 999)}.txt"

    return {
        "filename": filename,
        "content": content,
        "description": f"Calendar: {span_options[size_label]} ({num_events} events) [{size_label}]",
        "category": "calendar",
        "source": "generated",
    }
