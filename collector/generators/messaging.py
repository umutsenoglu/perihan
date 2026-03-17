"""Generate fictional messaging conversations — personal to the main persona."""

import random
from .base import llm_generate, random_date, pick_size, get_persona_context, PERSONA, CONTACTS, pick_ongoing_situation, pick_storyline, get_storyline_context

PLATFORMS = ["whatsapp", "email", "sms", "telegram"]

# Personal conversation scenarios — all English
PERSONAL_CONVERSATIONS = [
    {"theme": "family group chat about mum's health", "participants": ["Hannah Brooks", "Luke Marsh"],
     "group": "Marsh Family", "platform": "whatsapp"},
    {"theme": "planning summer trip to Portugal", "participants": ["Claire Marsh"],
     "group": None, "platform": "whatsapp"},
    {"theme": "school parents discussing upcoming bake sale", "participants": ["Tom Harris", "Rachel Green", "Mrs. Henderson"],
     "group": "Year 3 Parents", "platform": "whatsapp"},
    {"theme": "coordinating kitchen renovation quotes", "participants": ["Steve from BuildRight"],
     "group": None, "platform": "whatsapp"},
    {"theme": "catching up with old uni friend", "participants": ["Ben Walker"],
     "group": None, "platform": "whatsapp"},
    {"theme": "work team discussing payment migration deadline", "participants": ["James Patterson", "Priya Sharma", "Richard Clarke"],
     "group": "Payments Team", "platform": "telegram"},
    {"theme": "cycling club weekend ride planning", "participants": ["Marcus Webb", "Dave Mitchell"],
     "group": "North London Cyclists", "platform": "whatsapp"},
    {"theme": "neighbor dispute about fence with Sandra and Dave", "participants": ["Dave Mitchell", "Sandra Mitchell"],
     "group": None, "platform": "sms"},
    {"theme": "email thread with solicitor about fence dispute", "participants": ["Helen Crawford"],
     "group": None, "platform": "email"},
    {"theme": "email with property lawyer about inheritance case", "participants": ["Simon Holt"],
     "group": None, "platform": "email"},
    {"theme": "spouse discussing Max's nursery fees and alternatives", "participants": ["Claire Marsh"],
     "group": None, "platform": "whatsapp"},
    {"theme": "ordering fish supplies from aquarium shop", "participants": ["AquaWorld (Mark)"],
     "group": None, "platform": "whatsapp"},
    {"theme": "arranging playdate for Lily", "participants": ["Rachel Green"],
     "group": None, "platform": "whatsapp"},
    {"theme": "discussing EV options and test drives", "participants": ["Ryan Cooper"],
     "group": None, "platform": "whatsapp"},
    {"theme": "PTA meeting coordination", "participants": ["Tom Harris", "Rachel Green"],
     "group": "QPA PTA Group", "platform": "whatsapp"},
    {"theme": "checking on mum in Bristol after doctor visit", "participants": ["Janet Marsh"],
     "group": None, "platform": "whatsapp"},
    {"theme": "accountant discussing tax return and freelance income", "participants": ["Phil Norton"],
     "group": None, "platform": "email"},
    {"theme": "work colleague sharing funny memes and weekend plans", "participants": ["James Patterson"],
     "group": None, "platform": "whatsapp"},
    {"theme": "sister asking for help choosing a new laptop", "participants": ["Hannah Brooks"],
     "group": None, "platform": "whatsapp"},
    {"theme": "nursery teacher sending update about Max's day", "participants": ["Miss Claire"],
     "group": "Little Stars Updates", "platform": "whatsapp"},
    {"theme": "mother-in-law planning Easter visit", "participants": ["Diane Perry", "Claire Marsh"],
     "group": None, "platform": "whatsapp"},
    {"theme": "discussing Lily's birthday party planning", "participants": ["Claire Marsh", "Rachel Green"],
     "group": None, "platform": "whatsapp"},
]


async def generate() -> dict:
    """Generate a fictional messaging conversation from persona's life."""
    is_personal = random.random() < 0.85
    start_date = random_date()
    size_label, min_w, max_w = pick_size()

    msg_counts = {"tiny": (3, 6), "short": (8, 15), "medium": (15, 35), "long": (40, 80), "huge": (100, 200), "massive": (300, 600)}
    min_msgs, max_msgs = msg_counts[size_label]
    num_msgs = random.randint(min_msgs, max_msgs)

    use_storyline = is_personal and random.random() < 0.40
    storyline_ctx = ""
    storyline_id = None

    if use_storyline:
        storyline = pick_storyline()
        storyline_id = storyline["id"]
        storyline_ctx = get_storyline_context(storyline)
        # Generate a conversation about this storyline
        platform = random.choice(["whatsapp", "email", "sms"])
        theme = f"discussing {storyline['title'].lower()}"
        participants = [PERSONA["name"]] + storyline["people"][:3]
        group_name = None
        persona_ctx = get_persona_context()
    elif is_personal:
        conv = random.choice(PERSONAL_CONVERSATIONS)
        platform = conv["platform"]
        theme = conv["theme"]
        participants = [PERSONA["name"]] + conv["participants"]
        group_name = conv["group"]
        persona_ctx = get_persona_context()
    else:
        platform = random.choice(PLATFORMS)
        theme = random.choice([
            "planning a weekend trip", "discussing a movie",
            "organizing a birthday party", "sharing recipes",
        ])
        participants = [f"{random.choice(['John','Emma','David','Sarah'])} {random.choice(['Smith','Brown','Wilson'])}" for _ in range(random.randint(2, 4))]
        group_name = None
        persona_ctx = ""

    personal_note = ""
    if is_personal:
        personal_note = f"""
{persona_ctx}
{storyline_ctx}

This is a REAL conversation from {PERSONA['name']}'s phone/email.
Write entirely in English.
Make it feel authentic — use their actual names, reference real situations from their life.
Include typical personal touches: typos, abbreviations, emojis, voice notes, inside jokes.

VERY IMPORTANT — make this feel like REAL people chatting, NOT a structured document:
- People talk about MULTIPLE things in one conversation — they jump between topics
- Mix the main storyline topic with everyday mundane stuff: "what's for dinner", "did you
  pick up milk", "Max said something hilarious today", "have you seen my keys", "the boiler
  is making that noise again"
- Conversations trail off and resume hours later
- People send random links, photos, memes in between serious talk
- Short messages, often just "ok", "lol", "???", "hang on", "sorry was in a meeting"
- Typos and autocorrect errors that don't get corrected
- Messages sent at realistic times (not all in a neat sequence)
- Sometimes someone doesn't reply for hours and the other sends "??" or "hello?"
- Inside jokes, references to past conversations without explanation
- Emoji reactions, voice note references [Voice note 0:47]
- Real people don't stay on topic — they weave in and out"""

    if platform == "email":
        email_counts = {"tiny": "1-2", "short": "3-4", "medium": "5-8", "long": "10-15", "huge": "20-30", "massive": "40-80"}
        prompt = f"""Generate a realistic fictional email thread about: {theme}

Participants: {', '.join(participants)}
Starting date: {start_date.strftime('%Y-%m-%d %H:%M')}

Create {email_counts[size_label]} emails. Each with From, To, Date, Subject headers.
Target length: {min_w}-{max_w} words.
Write in English.
{personal_note}

This is FICTIONAL test data."""

    elif platform == "whatsapp":
        group_label = f"Group name: {group_name}" if group_name else "Private chat"
        prompt = f"""Generate a realistic fictional WhatsApp conversation about: {theme}

{group_label}
Participants: {', '.join(participants)}
Starting time: {start_date.strftime('%Y-%m-%d %H:%M')}

Create approximately {num_msgs} messages. Format:
[{start_date.strftime('%Y-%m-%d')} HH:MM] Name: message

Include typical WhatsApp behaviors — short messages, emojis, voice notes, photos.
Target length: {min_w}-{max_w} words.
Write in English.
{personal_note}

This is FICTIONAL test data."""

    else:
        prompt = f"""Generate a realistic fictional {platform.upper()} conversation about: {theme}

Between: {' and '.join(participants[:2])}
Starting: {start_date.strftime('%Y-%m-%d %H:%M')}

Create approximately {num_msgs} messages. Format: [HH:MM] Name: message
Target length: {min_w}-{max_w} words.
Write in English.
{personal_note}

This is FICTIONAL test data."""

    max_tokens = min(max_w * 3, 65000)
    content = await llm_generate(prompt, temperature=1.0, max_tokens=max_tokens)
    date_str = start_date.strftime('%Y%m%d')
    filename = f"messaging_{platform}_{theme.replace(' ', '_')[:30]}_{date_str}_{random.randint(100,999)}.txt"

    return {
        "filename": filename,
        "content": content,
        "description": f"{platform.title()}: {theme[:45]} [{size_label}]",
        "category": "messaging",
        "source": "generated",
        "storyline": storyline_id,
    }
