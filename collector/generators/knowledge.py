"""Generate knowledge articles — fetch real content from the internet, personalize with LLM."""

import random
from .base import (llm_generate, fetch_wikipedia_article, fetch_random_wikipedia,
                   fetch_web_page, fetch_gov_uk_info, pick_size, get_persona_context,
                   pick_ongoing_situation, PERSONA, fetch_multiple_wikipedia,
                   fetch_wikimedia_commons_text, fetch_bbc_news, fetch_arxiv_abstracts)

# Topics the persona would actually research — mapped to Wikipedia search terms
PERSONAL_TOPICS = [
    ("electric cars comparison", "Electric car"),
    ("tropical fish aquarium care", "Tropical fish"),
    ("UK inheritance law", "Inheritance law in England and Wales"),
    ("British citizenship naturalisation", "British nationality law"),
    ("kitchen renovation guide", "Kitchen renovation"),
    ("asthma management", "Asthma"),
    ("primary school mathematics UK", "Mathematics education"),
    ("cycling routes London", "Cycling in London"),
    ("boundary disputes UK property", "Boundary (real estate)"),
    ("ISA savings account UK", "Individual savings account"),
    ("nursery childcare costs UK", "Childcare in the United Kingdom"),
    ("Volkswagen Golf", "Volkswagen Golf"),
    ("UK property law probate", "Probate"),
    ("payment processing systems", "Payment processor"),
    ("guppy fish care", "Guppy"),
    ("photography basics aperture", "Aperture"),
    ("lahmacun recipe", "Lahmacun"),
    ("cat safe houseplants", "List of pet-safe houseplants"),
    ("mortgage overpayment UK", "Mortgage loan"),
    ("elderly parent care UK", "Elderly care in the United Kingdom"),
    ("EV charging home installation", "Charging station"),
    ("Hyundai Ioniq 5", "Hyundai Ioniq 5"),
    ("Tesla Model 3", "Tesla Model 3"),
    ("aquarium algae control", "Algae scrubber"),
    ("North London history", "North London"),
]

# GOV.UK topics for practical UK life info
GOV_UK_TOPICS = [
    "apply british citizenship",
    "self assessment tax return",
    "childcare costs help",
    "building regulations extension",
    "vehicle tax car",
    "boundary dispute neighbour",
    "council tax bands",
    "NHS dentist register",
    "school admissions appeal",
    "passport renewal",
]

# Generic Wikipedia topics (15%)
GENERIC_WIKI_SEARCHES = [
    "Quantum computing", "Ottoman Empire", "Climate change",
    "Renewable energy", "Sleep", "Behavioral economics",
    "Space exploration", "Nanotechnology", "Silk Road",
    "Artificial intelligence", "Machine learning", "Cryptocurrency",
    "Blockchain", "DNA sequencing", "CRISPR gene editing",
    "Mars exploration", "Nuclear fusion", "History of the Internet",
    "World Wide Web", "Theory of relativity", "Black hole",
]

# Topics for multi-article deep dives (massive size)
DEEP_DIVE_TOPICS = [
    {
        "label": "electric vehicles comparison",
        "queries": ["Electric car", "Tesla Model 3", "Hyundai Ioniq 5", "Volkswagen ID.4",
                     "Electric vehicle charging", "Battery electric vehicle"],
    },
    {
        "label": "UK property and inheritance law",
        "queries": ["Probate", "Inheritance law in England and Wales",
                     "Land registration in England and Wales", "Capital gains tax United Kingdom"],
    },
    {
        "label": "tropical aquarium fish keeping",
        "queries": ["Tropical fish", "Guppy", "Neon tetra", "Aquarium", "Aquarium filtration"],
    },
    {
        "label": "cycling in London safety and routes",
        "queries": ["Cycling in London", "Cycle superhighway", "Road traffic safety",
                     "Bicycle helmet"],
    },
    {
        "label": "payment processing fintech",
        "queries": ["Payment processor", "Payment card industry", "Stripe (company)",
                     "Microservices", "PCI DSS"],
    },
    {
        "label": "dementia care and elderly support UK",
        "queries": ["Dementia", "Vascular dementia", "Donepezil",
                     "Elderly care in the United Kingdom", "Power of attorney"],
    },
    {
        "label": "UK primary education and child development",
        "queries": ["Primary education in England", "Mathematics education",
                     "Dyscalculia", "Child development stages"],
    },
    {
        "label": "photography techniques and equipment",
        "queries": ["Photography", "Aperture", "Shutter speed", "Digital camera",
                     "Image sensor"],
    },
]

# BBC News topics for current-events style content
BBC_TOPICS = [
    "electric cars UK", "property prices London", "NHS waiting times",
    "cycling safety London", "primary school education UK",
    "fintech payments", "dementia research", "climate change UK",
    "artificial intelligence", "renewable energy UK",
]

# arXiv topics for technical/research content
ARXIV_TOPICS = [
    "machine learning", "neural network", "natural language processing",
    "computer vision", "reinforcement learning", "quantum computing",
    "electric vehicle battery", "payment fraud detection",
]


async def generate() -> dict:
    """Generate a knowledge article — fetch real content from internet."""
    is_personal = random.random() < 0.85
    size_label, min_w, max_w = pick_size()

    content = ""
    source = "generated"
    topic_name = ""

    # For massive sizes, prefer deep dive (multi-article) or full web pages
    if size_label == "massive":
        strategies = ["deep_dive", "wikipedia_full", "bbc_news", "web_page_full"]
        weights = [40, 30, 15, 15]
    else:
        strategies = ["wikipedia", "govuk", "wikipedia_random", "bbc_news",
                       "arxiv", "web_page", "llm_only"]
        weights = [35, 10, 12, 12, 8, 8, 15]

    strategy = random.choices(strategies, weights=weights, k=1)[0]

    if strategy == "deep_dive":
        # Multi-article compilation for massive content
        topic = random.choice(DEEP_DIVE_TOPICS)
        articles = await fetch_multiple_wikipedia(topic["queries"], max_per_article=max_w // len(topic["queries"]))
        if articles:
            parts = []
            for title, text in articles:
                parts.append(f"{'=' * 60}\n{title}\n{'=' * 60}\n\n{text}")
            combined = "\n\n".join(parts)

            if is_personal:
                persona_ctx = get_persona_context()
                situation = pick_ongoing_situation()
                prompt = f"""Below is a collection of Wikipedia articles that {PERSONA['name']} compiled
while researching "{topic['label']}". Add personal annotations throughout —
margin notes, sticky notes, questions, "need to check this", "Claire said...",
bookmarks, cross-references between the articles, and notes about which parts
are most relevant to their situation.

{persona_ctx}
Related life situation: {situation}

Keep all the original article content intact, just add personal notes.
Write entirely in English.

COMPILED RESEARCH:
{combined[:60000]}"""
                content = await llm_generate(prompt, temperature=0.8, max_tokens=min(max_w * 2, 65000))
            else:
                content = f"Research compilation: {topic['label']}\n\n{combined}"
            topic_name = topic["label"]
            source = "internet"

    elif strategy == "wikipedia_full":
        # Fetch a full Wikipedia article WITHOUT trimming
        if is_personal:
            topic_label, wiki_search = random.choice(PERSONAL_TOPICS)
        else:
            wiki_search = random.choice(GENERIC_WIKI_SEARCHES)
            topic_label = wiki_search

        title, article = await fetch_wikipedia_article(wiki_search)
        if article:
            # Also fetch related topics for richer content
            enriched = await fetch_wikimedia_commons_text(title)
            if enriched and len(enriched) > len(article):
                article = enriched

            if is_personal:
                persona_ctx = get_persona_context()
                situation = pick_ongoing_situation()
                prompt = f"""Below is a full Wikipedia article that {PERSONA['name']} saved as reference material.
Add personal annotations throughout — sticky notes, margin comments, questions,
"need to check this", "relevant to our situation", cross-references.

{persona_ctx}
Related life situation: {situation}

Keep the full original article intact, add notes in [brackets] or as "MY NOTE:" lines.
Write entirely in English.

ARTICLE:
{title}
{article[:60000]}"""
                content = await llm_generate(prompt, temperature=0.8, max_tokens=min(max_w * 2, 65000))
            else:
                content = f"{title}\n\n{article}"
            topic_name = topic_label
            source = "internet"

    elif strategy == "wikipedia":
        if is_personal:
            topic_label, wiki_search = random.choice(PERSONAL_TOPICS)
        else:
            wiki_search = random.choice(GENERIC_WIKI_SEARCHES)
            topic_label = wiki_search

        title, article = await fetch_wikipedia_article(wiki_search)
        if article:
            # Trim to target size only if needed
            words = article.split()
            if len(words) > max_w * 2:
                article = " ".join(words[:max_w * 2])

            if is_personal:
                persona_ctx = get_persona_context()
                situation = pick_ongoing_situation()
                prompt = f"""Below is a Wikipedia article that {PERSONA['name']} saved for personal reference.
Add 3-5 personal annotations/notes throughout — like sticky notes or margin comments
that show why they saved this and how it relates to their life.

{persona_ctx}
Related life situation: {situation}

Keep the original article intact, just add notes in [brackets] or as "MY NOTE:" lines.
Write entirely in English.

ARTICLE:
{title}
{article}"""
                content = await llm_generate(prompt, temperature=0.8, max_tokens=min(max_w * 3, 65000))
            else:
                content = f"{title}\n\n{article}"

            topic_name = topic_label
            source = "internet"

    elif strategy == "govuk" and is_personal:
        topic = random.choice(GOV_UK_TOPICS)
        gov_text = await fetch_gov_uk_info(topic)
        if gov_text:
            persona_ctx = get_persona_context()
            prompt = f"""Below is GOV.UK information that {PERSONA['name']} looked up.
Reformat it as their personal research notes — add their own comments,
questions, next steps, things to remember. Keep the factual content but
make it feel like someone's personal Notion/Evernote page.

{persona_ctx}

GOV.UK INFO:
{gov_text[:30000]}

Write as personal notes, entirely in English.
Target length: {min_w}-{max_w} words."""
            content = await llm_generate(prompt, temperature=0.8, max_tokens=min(max_w * 3, 65000))
            topic_name = topic
            source = "internet"

    elif strategy == "bbc_news":
        topic = random.choice(BBC_TOPICS)
        news_text = await fetch_bbc_news(topic)
        if news_text:
            if is_personal:
                persona_ctx = get_persona_context()
                situation = pick_ongoing_situation()
                prompt = f"""Below is BBC News content that {PERSONA['name']} found while researching "{topic}".
Reformat as their personal notes — highlight the key facts, add their own comments,
questions, how it affects their life/decisions.

{persona_ctx}
Related life situation: {situation}

BBC NEWS CONTENT:
{news_text[:30000]}

Write as personal research notes, entirely in English.
Target length: {min_w}-{max_w} words."""
                content = await llm_generate(prompt, temperature=0.8, max_tokens=min(max_w * 3, 65000))
            else:
                content = f"News research: {topic}\n\n{news_text[:max_w * 6]}"
            topic_name = f"news_{topic}"
            source = "internet"

    elif strategy == "arxiv":
        topic = random.choice(ARXIV_TOPICS)
        arxiv_text = await fetch_arxiv_abstracts(topic, max_results=8)
        if arxiv_text:
            if is_personal:
                persona_ctx = get_persona_context()
                prompt = f"""Below are research paper abstracts from arXiv that {PERSONA['name']} collected
while looking into "{topic}" for work or personal interest.
Add personal annotations — which papers seem useful, questions, "need to read full paper",
how it relates to the PayFlow migration project or other work.

{persona_ctx}

ARXIV PAPERS:
{arxiv_text[:20000]}

Write as personal annotated reading list, entirely in English.
Target length: {min_w}-{max_w} words."""
                content = await llm_generate(prompt, temperature=0.8, max_tokens=min(max_w * 3, 65000))
            else:
                content = f"Research papers: {topic}\n\n{arxiv_text}"
            topic_name = f"research_{topic}"
            source = "internet"

    elif strategy == "web_page" or strategy == "web_page_full":
        # Fetch full web pages from informational sites
        urls = [
            ("https://www.which.co.uk/reviews/electric-cars", "electric cars reviews"),
            ("https://www.moneyhelper.org.uk/en/homes/buying-a-home/mortgage-overpayments", "mortgage overpayments"),
            ("https://www.citizensadvice.org.uk/housing/problems-with-neighbours/neighbour-disputes/", "neighbour disputes"),
            ("https://www.ageuk.org.uk/information-advice/health-wellbeing/conditions-illnesses/dementia/", "dementia care"),
        ]
        url, topic_label = random.choice(urls)
        page_text = await fetch_web_page(url)
        if page_text and len(page_text) > 500:
            if is_personal:
                persona_ctx = get_persona_context()
                situation = pick_ongoing_situation()
                prompt = f"""Below is web page content that {PERSONA['name']} saved from the internet
while researching "{topic_label}".
Reformat as their personal research notes — key takeaways, questions, action items,
how it relates to their life.

{persona_ctx}
Related life situation: {situation}

WEB CONTENT:
{page_text[:50000]}

Write as personal research notes, entirely in English.
Target length: {min_w}-{max_w} words."""
                content = await llm_generate(prompt, temperature=0.8, max_tokens=min(max_w * 3, 65000))
            else:
                content = f"Web research: {topic_label}\n\n{page_text[:max_w * 6]}"
            topic_name = topic_label
            source = "internet"

    elif strategy == "wikipedia_random":
        title, article = await fetch_random_wikipedia("en")
        if article:
            words = article.split()
            if len(words) > max_w * 2:
                article = " ".join(words[:max_w * 2])
            content = f"{title}\n\n{article}"
            topic_name = title
            source = "internet"

    # Fallback: if internet fetch failed or strategy was llm_only
    if not content:
        if is_personal:
            topic_label = random.choice(PERSONAL_TOPICS)[0]
            persona_ctx = get_persona_context()
            situation = pick_ongoing_situation()
            prompt = f"""Write personal research notes about: {topic_label}

{persona_ctx}
Related to: {situation}

Write as {PERSONA['name']}'s personal notes — include their thoughts,
questions, comparisons, "need to check this", "Claire said...", etc.
Target length: {min_w}-{max_w} words. Write in English."""
        else:
            topic_label = random.choice(GENERIC_WIKI_SEARCHES)
            prompt = f"""Write an informational article about: {topic_label}
Target length: {min_w}-{max_w} words. Plain text format."""

        content = await llm_generate(prompt, temperature=0.9, max_tokens=min(max_w * 3, 65000))
        topic_name = topic_label
        source = "generated"

    safe_topic = topic_name.replace(" ", "_").replace("/", "-")[:40]
    filename = f"knowledge_{safe_topic}_{random.randint(1000,9999)}.txt"

    return {
        "filename": filename,
        "content": content,
        "description": f"Knowledge: {topic_name[:50]} [{size_label}]",
        "category": "knowledge",
        "source": source,
    }
