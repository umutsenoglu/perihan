"""Generate fictional Trello board exports in XML — from the persona's projects."""

import random
from .base import llm_generate, random_date, pick_size, get_persona_context, PERSONA, CONTACTS

# Trello boards the persona would actually have
PERSONAL_BOARDS = [
    {"name": "Kitchen Renovation", "lists": ["Research", "Get Quotes", "Decide", "In Progress", "Done"],
     "context": "Tracking the kitchen reno project — quotes from Steve (BuildRight), appliance research, timeline"},
    {"name": "EV Car Research", "lists": ["Models to Check", "Test Drives", "Financing", "Insurance Quotes", "Decision"],
     "context": "Comparing electric vehicles — Tesla 3, Ioniq 5, ID.4, trade-in value of VW Golf"},
    {"name": "Citizenship Application", "lists": ["Documents Needed", "Documents Gathered", "Forms to Fill", "Submitted", "Done"],
     "context": "British citizenship naturalization process — Life in UK test done, gathering references"},
    {"name": "Summer Holiday Portugal", "lists": ["Flights", "Accommodation", "Activities", "Packing", "Done"],
     "context": "Planning family trip to the Algarve — beach activities for kids, villa rental"},
    {"name": "Lily Birthday Party", "lists": ["Ideas", "To Buy", "To Book", "Invitations", "Done"],
     "context": "Science-themed 8th birthday party planning — venue, experiments, cake, guest list"},
    {"name": "Fish Tank Setup", "lists": ["Equipment", "Fish List", "Water Parameters", "Maintenance Schedule", "Completed"],
     "context": "Tropical fish tank management — compatible species, CO2 setup, algae control"},
    {"name": "Work - Payment Migration", "lists": ["Backlog", "Sprint", "In Progress", "Code Review", "QA", "Done"],
     "context": "Payment processing system migration at FinEdge — API redesign, data migration, testing"},
    {"name": "House Maintenance", "lists": ["Urgent", "This Month", "This Quarter", "Someday", "Done"],
     "context": "Ongoing house tasks — boiler service, gutter cleaning, garden fence (not the disputed one), painting"},
    {"name": "Freelance Projects", "lists": ["Leads", "Proposals Sent", "Active", "Invoiced", "Paid"],
     "context": "Side freelance development work — React dashboards, API integrations"},
    {"name": "Family Admin", "lists": ["To Do", "Waiting", "Recurring", "Done"],
     "context": "Family paperwork — school forms, nursery registration, GP appointments, insurance renewals"},
]

GENERIC_BOARDS = [
    {"name": "Product Launch Q2", "lists": ["Backlog", "Sprint", "In Progress", "Review", "Done"]},
    {"name": "Marketing Campaign", "lists": ["Ideas", "Planning", "In Progress", "Review", "Live"]},
]


async def generate() -> dict:
    """Generate a fictional Trello board export from persona's life."""
    is_personal = random.random() < 0.85
    date = random_date()
    size_label, min_w, max_w = pick_size()

    card_counts = {"tiny": (3, 5), "short": (6, 12), "medium": (15, 25), "long": (30, 50), "huge": (60, 100), "massive": (150, 300)}
    min_cards, max_cards = card_counts[size_label]
    num_cards = random.randint(min_cards, max_cards)

    if is_personal:
        board = random.choice(PERSONAL_BOARDS)
        board_name = board["name"]
        lists = board["lists"]
        context = board["context"]
        members = [PERSONA["name"]] + random.sample(
            [CONTACTS["spouse"], CONTACTS["work_colleague"], CONTACTS["work_colleague2"], CONTACTS["contractor"]],
            k=random.randint(1, 3)
        )
        persona_ctx = get_persona_context()

        personal_note = f"""
{persona_ctx}

This is {PERSONA['name']}'s actual Trello board.
Context: {context}
Cards should reference real people, places, and situations from their life.
Include personal notes in cards like "ask Claire", "Steve said 3 weeks", "check with Richard".
Write entirely in English."""
    else:
        board = random.choice(GENERIC_BOARDS)
        board_name = board["name"]
        lists = board["lists"]
        members = [f"{random.choice(['Ali','John','Emma'])} {random.choice(['Smith','Demir'])}"]
        personal_note = ""

    prompt = f"""Generate a realistic fictional Trello board export in XML format.

Board name: {board_name}
Members: {', '.join(members)}
Export date: {date.strftime('%Y-%m-%d')}
Lists: {', '.join(lists)}
Number of cards: approximately {num_cards}

Target length: {min_w}-{max_w} words.
{personal_note}

Use this XML structure:
<?xml version="1.0" encoding="UTF-8"?>
<board>
  <name>{board_name}</name>
  <exportDate>{date.strftime('%Y-%m-%d')}</exportDate>
  <members><member>name</member></members>
  <lists>
    <list>
      <name>List Name</name>
      <cards>
        <card>
          <title>Card title</title>
          <description>Description</description>
          <labels><label color="green">Label</label></labels>
          <dueDate>2025-03-15</dueDate>
          <assignedTo>Member</assignedTo>
          <checklists>
            <checklist><name>Name</name>
              <items><item completed="true">Item</item></items>
            </checklist>
          </checklists>
          <comments>
            <comment><author>Name</author><date>2025-03-10</date><text>Text</text></comment>
          </comments>
        </card>
      </cards>
    </list>
  </lists>
</board>

Vary detail level naturally. This is FICTIONAL test data. Output valid XML only."""

    max_tokens = min(max_w * 4, 65000)
    content = await llm_generate(prompt, temperature=0.8, max_tokens=max_tokens)
    date_str = date.strftime('%Y%m%d')
    safe_name = board_name.replace(" ", "_").replace("-", "_")[:30]
    filename = f"trello_{safe_name}_{date_str}_{random.randint(100, 999)}.xml"

    return {
        "filename": filename,
        "content": content,
        "description": f"Trello: {board_name} ({num_cards} cards) [{size_label}]",
        "category": "trello",
        "source": "generated",
        "storyline": None,
    }
