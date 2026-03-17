"""Generate fictional personal documents — diaries, notes, journals from the persona's life."""

import random
from .base import llm_generate, random_date, pick_size, get_persona_context, PERSONA, pick_ongoing_situation, pick_storyline, get_storyline_context

PERSONAL_DOC_TYPES = [
    "diary_entry",
    "personal_note",
    "journal",
    "to_do_list",
    "grocery_list",
    "dream_log",
    "gratitude_journal",
    "book_notes",
    "recipe_notes",
    "workout_log",
    "goal_setting",
    "reflection",
    "packing_list",
    "pros_cons_list",
    "brainstorm",
    "phone_memo",
    "shopping_research",
]

LIFE_MOMENTS = [
    "stressful day at work — payment migration hitting issues, Richard breathing down my neck",
    "lovely cycling ride with Marcus through Hampstead Heath, spotted a fox",
    "Lily brought home a painting from school, so proud of her",
    "had a long call with mum in Bristol, she sounds tired",
    "kitchen renovation quote came in way over budget, need to rethink",
    "Max said the funniest thing at nursery today, Miss Claire told us",
    "argument with Dave next door about the fence again",
    "got the letter from Helen Crawford about court date for fence dispute",
    "Claire and I discussed whether to move Max to a cheaper nursery",
    "researching EVs all evening, the Tesla Model 3 vs Hyundai Ioniq 5",
    "tried a new pasta recipe for dinner, kids actually loved it",
    "Whiskers (cat) knocked over the fish tank light again",
    "inheritance paperwork finally moving forward, Simon Holt called with an update",
    "sister Hannah called about choosing a laptop, spent 2 hours helping",
    "back pain flaring up, need to book physio appointment",
    "server went down at work at 11pm, had to fix it from bed",
    "planning Lily's 8th birthday party, she wants a science theme",
    "fish tank algae problem — need to check water parameters",
    "rainy Sunday, watched a film with Claire, kids playing upstairs",
    "got freelance project offer, decent money but no time",
]


async def generate() -> dict:
    """Generate a fictional personal document from the persona's life."""
    doc_type = random.choice(PERSONAL_DOC_TYPES)
    date = random_date()
    size_label, min_w, max_w = pick_size()
    moment = random.choice(LIFE_MOMENTS)
    situation = pick_ongoing_situation()
    persona_ctx = get_persona_context()

    # 40% chance to tie to a storyline
    storyline_ctx = ""
    storyline_id = None
    if random.random() < 0.40:
        storyline = pick_storyline()
        storyline_id = storyline["id"]
        storyline_ctx = get_storyline_context(storyline)
        moment = f"thinking about {storyline['title'].lower()}"

    size_guidance = {
        "tiny": "Just a quick scribble — a sentence or two, like a phone memo or sticky note.",
        "short": "A brief personal entry — a few paragraphs at most.",
        "medium": "A standard diary entry or set of notes with some detail and reflection.",
        "long": "A lengthy, deeply reflective journal entry spanning the whole day.",
        "huge": "An extensive personal document — like a week's worth of diary entries or a very long reflective piece.",
        "massive": "A massive personal archive — an entire month of daily journal entries, or a deeply detailed life document covering multiple storylines, events, and reflections.",
    }

    lang_instruction = "Write entirely in English."

    prompt = f"""Generate a realistic fictional personal document.

Type: {doc_type.replace('_', ' ')}
Written by: {PERSONA['name']}
Date: {date.strftime('%Y-%m-%d')}
Today's moment: {moment}
Ongoing situation: {situation}

{persona_ctx}
{storyline_ctx}

{size_guidance[size_label]}
Target length: {min_w}-{max_w} words.

{lang_instruction}

Write in first person. Make it feel deeply authentic — this is from {PERSONA['name']}'s
personal phone notes or private journal. Include:
- Real emotions, mundane details, small observations about their day
- References to family (Claire, Lily, Max, mum, Hannah), colleagues (James, Priya, Richard), friends
- Incomplete thoughts, abbreviations, things only they would understand
- For lists: casual format with checkboxes, dashes, crossed out items
- For diary: stream of consciousness, not perfectly written

This is FICTIONAL test data. Format as plain text."""

    max_tokens = min(max_w * 3, 65000)
    content = await llm_generate(prompt, temperature=1.0, max_tokens=max_tokens)
    date_str = date.strftime('%Y%m%d')
    filename = f"personal_{doc_type}_{date_str}_{random.randint(100, 999)}.txt"

    return {
        "filename": filename,
        "content": content,
        "description": f"Personal {doc_type.replace('_', ' ')} - {moment[:40]} [{size_label}]",
        "category": "personal",
        "source": "generated",
        "storyline": storyline_id,
    }
