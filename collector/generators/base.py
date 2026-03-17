"""Base generator with shared LLM, web-fetch logic, and persona system."""

import os
import httpx
import json
import random
import re
from datetime import datetime, timedelta


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


async def llm_generate(prompt: str, temperature: float = 1.0, max_tokens: int = 8192) -> str:
    """Call Gemini to generate text content.
    If the response is truncated (MAX_TOKENS), automatically continues generation."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")

    # Ensure a reasonable minimum so small sizes don't get cut off
    effective_tokens = max(max_tokens, 2048)

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": effective_tokens,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
        candidate = data["candidates"][0]
        text = candidate["content"]["parts"][0]["text"]
        finish_reason = candidate.get("finishReason", "")

        # If truncated, request a continuation (up to 2 retries)
        if finish_reason == "MAX_TOKENS":
            for _ in range(2):
                continuation_prompt = (
                    prompt + "\n\n--- PARTIAL OUTPUT SO FAR (continue from where it left off) ---\n"
                    + text[-2000:]
                    + "\n--- CONTINUE WRITING FROM HERE, do not repeat what's above ---"
                )
                resp2 = await client.post(
                    f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                    json={
                        "contents": [{"parts": [{"text": continuation_prompt}]}],
                        "generationConfig": {
                            "temperature": temperature,
                            "maxOutputTokens": effective_tokens,
                        },
                    },
                )
                resp2.raise_for_status()
                data2 = resp2.json()
                candidate2 = data2["candidates"][0]
                continuation = candidate2["content"]["parts"][0]["text"]
                text += "\n" + continuation
                if candidate2.get("finishReason", "") != "MAX_TOKENS":
                    break

        return text


# Size profiles: (word_range_label, min_words, max_words, weight)
SIZE_PROFILES = [
    ("tiny",   30,   80,   10),
    ("short",  100,  250,  20),
    ("medium", 300,  600,  25),
    ("long",   800,  2000, 20),
    ("huge",   2500, 6000, 15),
    ("massive", 8000, 20000, 10),
]


def pick_size() -> tuple[str, int, int]:
    """Pick a random size profile. Returns (label, min_words, max_words)."""
    labels, mins, maxes, weights = zip(*SIZE_PROFILES)
    idx = random.choices(range(len(SIZE_PROFILES)), weights=weights, k=1)[0]
    return labels[idx], mins[idx], maxes[idx]


async def web_search_snippet(query: str) -> str:
    """Fetch a brief snippet from the web using a search query."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": 3,
                    "format": "json",
                },
            )
            resp.raise_for_status()
            results = resp.json().get("query", {}).get("search", [])
            if results:
                snippets = []
                for r in results:
                    clean = re.sub(r"<[^>]+>", "", r.get("snippet", ""))
                    snippets.append(f"{r['title']}: {clean}")
                return "\n".join(snippets)
    except Exception:
        pass
    return ""


async def fetch_wikipedia_article(query: str) -> tuple[str, str]:
    """Fetch a full Wikipedia article as plain text.
    Returns (title, content) or ("", "") on failure."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            # Search for the best matching page
            search = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "query", "list": "search", "srsearch": query,
                        "srlimit": 1, "format": "json"},
            )
            search.raise_for_status()
            results = search.json().get("query", {}).get("search", [])
            if not results:
                return "", ""

            title = results[0]["title"]

            # Fetch full plain text extract
            extract = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "query", "titles": title, "prop": "extracts",
                        "explaintext": True, "exsectionformat": "plain",
                        "format": "json"},
            )
            extract.raise_for_status()
            pages = extract.json().get("query", {}).get("pages", {})
            for page in pages.values():
                text = page.get("extract", "")
                if text:
                    return title, text
    except Exception:
        pass
    return "", ""


async def fetch_random_wikipedia(lang: str = "en") -> tuple[str, str]:
    """Fetch a random Wikipedia article. Returns (title, content)."""
    base = f"https://{lang}.wikipedia.org/w/api.php"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(base, params={
                "action": "query", "list": "random", "rnnamespace": 0,
                "rnlimit": 1, "format": "json",
            })
            resp.raise_for_status()
            pages = resp.json().get("query", {}).get("random", [])
            if not pages:
                return "", ""
            title = pages[0]["title"]

            extract = await client.get(base, params={
                "action": "query", "titles": title, "prop": "extracts",
                "explaintext": True, "exsectionformat": "plain", "format": "json",
            })
            extract.raise_for_status()
            for page in extract.json().get("query", {}).get("pages", {}).values():
                text = page.get("extract", "")
                if text and len(text) > 200:
                    return title, text
    except Exception:
        pass
    return "", ""


async def fetch_web_page(url: str, max_bytes: int = 5 * 1024 * 1024) -> str:
    """Fetch a web page and extract text content (strip HTML tags).
    Streams response to handle large pages (up to max_bytes, default 5 MB)."""
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            async with client.stream("GET", url, headers={"User-Agent": "Mozilla/5.0 (collector bot)"}) as resp:
                resp.raise_for_status()
                chunks = []
                total = 0
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= max_bytes:
                        break
            raw = b"".join(chunks)
            text = raw.decode("utf-8", errors="ignore")
            # Strip HTML tags, scripts, styles
            text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", text, flags=re.IGNORECASE)
            text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text
    except Exception:
        return ""


async def fetch_nhs_health_info(condition: str) -> str:
    """Fetch health information from NHS website."""
    try:
        slug = condition.lower().replace(" ", "-")
        url = f"https://www.nhs.uk/conditions/{slug}/"
        text = await fetch_web_page(url)
        if text and len(text) > 200:
            return text[:50000]
    except Exception:
        pass
    return ""


async def fetch_gov_uk_info(topic: str) -> str:
    """Fetch information from GOV.UK — gets search results then fetches full page content."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://www.gov.uk/api/search.json",
                params={"q": topic, "count": 5},
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                texts = []
                for r in results[:3]:
                    title = r.get("title", "")
                    desc = r.get("description", "")
                    link = r.get("link", "")
                    texts.append(f"{title}\n{desc}\nhttps://www.gov.uk{link}")
                    # Fetch full page content for the first result
                    if len(texts) == 1 and link:
                        page_text = await fetch_web_page(f"https://www.gov.uk{link}")
                        if page_text and len(page_text) > 200:
                            texts.append(f"\n--- Full content from {title} ---\n{page_text[:30000]}")
                return "\n\n".join(texts)
    except Exception:
        pass
    return ""


async def fetch_multiple_wikipedia(queries: list[str], max_per_article: int = 0) -> list[tuple[str, str]]:
    """Fetch multiple Wikipedia articles. Returns list of (title, content).
    If max_per_article > 0, trims each article to that many words."""
    results = []
    for q in queries:
        title, text = await fetch_wikipedia_article(q)
        if text:
            if max_per_article > 0:
                words = text.split()
                if len(words) > max_per_article:
                    text = " ".join(words[:max_per_article])
            results.append((title, text))
    return results


async def fetch_wikimedia_commons_text(query: str) -> str:
    """Search Wikimedia for descriptive text about a topic."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query", "titles": query,
                    "prop": "extracts|links|categories",
                    "explaintext": True, "exsectionformat": "plain",
                    "pllimit": 50, "cllimit": 20,
                    "format": "json",
                },
            )
            resp.raise_for_status()
            pages = resp.json().get("query", {}).get("pages", {})
            for page in pages.values():
                text = page.get("extract", "")
                # Append linked page titles for richer context
                links = page.get("links", [])
                categories = page.get("categories", [])
                if links:
                    link_titles = [l.get("title", "") for l in links[:30]]
                    text += "\n\nRelated topics: " + ", ".join(link_titles)
                if categories:
                    cat_names = [c.get("title", "").replace("Category:", "") for c in categories]
                    text += "\nCategories: " + ", ".join(cat_names)
                if text:
                    return text
    except Exception:
        pass
    return ""


async def fetch_bbc_news(topic: str) -> str:
    """Fetch BBC News search results for a topic."""
    try:
        url = f"https://www.bbc.co.uk/search?q={topic}&d=news_gnl"
        text = await fetch_web_page(url)
        if text and len(text) > 200:
            return text[:30000]
    except Exception:
        pass
    return ""


async def fetch_arxiv_abstracts(query: str, max_results: int = 5) -> str:
    """Fetch paper abstracts from arXiv API."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "http://export.arxiv.org/api/query",
                params={"search_query": f"all:{query}", "max_results": max_results},
            )
            resp.raise_for_status()
            text = resp.text
            # Extract titles and summaries from Atom XML
            titles = re.findall(r"<title>(.*?)</title>", text, re.DOTALL)
            summaries = re.findall(r"<summary>(.*?)</summary>", text, re.DOTALL)
            parts = []
            for t, s in zip(titles[1:], summaries):  # skip first title (feed title)
                clean_t = re.sub(r"\s+", " ", t).strip()
                clean_s = re.sub(r"\s+", " ", s).strip()
                parts.append(f"Paper: {clean_t}\nAbstract: {clean_s}")
            return "\n\n".join(parts)
    except Exception:
        pass
    return ""


def random_date(start_year=2023, end_year=2026) -> datetime:
    """Generate a random datetime."""
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 3, 1)
    delta = end - start
    random_days = random.randint(0, delta.days)
    random_seconds = random.randint(0, 86399)
    return start + timedelta(days=random_days, seconds=random_seconds)


def random_name() -> str:
    """Generate a random person name from the persona's social circle."""
    if random.random() < 0.7:
        return random.choice(list(CONTACTS.values()))
    first_names = [
        "John", "Sarah", "Michael", "Emma", "David", "Lisa", "James", "Anna",
        "Robert", "Maria", "Thomas", "Laura", "Daniel", "Sophie", "Mark",
        "Oliver", "Charlotte", "Harry", "Emily", "George", "Grace", "William",
        "Ben", "Katie", "Sam", "Nadia", "Priya", "Raj", "Ahmed", "Yuki",
    ]
    last_names = [
        "Smith", "Johnson", "Brown", "Wilson", "Taylor", "Anderson", "Clark",
        "Martin", "Garcia", "Lopez", "Martinez", "Davis", "Miller", "Moore",
        "Walker", "Hall", "Young", "King", "Wright", "Green", "Baker",
    ]
    return f"{random.choice(first_names)} {random.choice(last_names)}"


# ──────────────────────────────────────────────────────────────────────
# PERSONA SYSTEM
# Everything generated should feel like it belongs to ONE person's life.
# 85% of content is personal; 15% can be generic/informational.
# ──────────────────────────────────────────────────────────────────────

PERSONA = {
    "name": "Ethan Marsh",
    "age": 38,
    "location": "London, UK",
    "job": "Senior software engineer at a fintech company",
    "family": {
        "spouse": "Claire Marsh (teacher, works at a primary school)",
        "children": ["Lily (7, Year 3)", "Max (4, nursery)"],
        "parents": "Mother Janet in Bristol, father George passed away 2021",
        "siblings": "Sister Hannah in Manchester, brother Luke in Edinburgh",
        "in_laws": "Mother-in-law Diane in Cornwall",
    },
    "life_details": {
        "housing": "3-bed semi-detached in North London, mortgage with Barclays",
        "car": "2019 VW Golf, considering switching to electric",
        "hobbies": "tropical fish keeping, cycling, photography, cooking",
        "pets": "two cats (Whiskers and Olive)",
        "health": "mild asthma, seasonal allergies, lower back pain from desk work",
        "kids_school": "QPA Primary School — Lily in Year 3 (Mrs. Henderson's class), Max at Little Stars Nursery",
        "social": "Member of local cycling club, school PTA",
        "finances": "Mortgage, ISA savings, pension with Scottish Widows, occasional freelance work",
    },
    "ongoing_situations": [
        "Dealing with a neighbor dispute about a shared fence — solicitor involved",
        "Mother's health declining in Bristol — frequent calls and planning a visit",
        "Lily struggling with math at school — looking into tutoring",
        "Planning kitchen renovation — getting quotes from contractors",
        "Trying to sell old car and buy an EV",
        "Property inheritance issue after father's death — solicitor handling",
        "Organizing summer holiday to Portugal — need to book flights",
        "Work project deadline for payment processing migration — stressful",
        "Max's nursery fees going up — considering alternatives",
        "Thinking about getting a dog — Claire wants a labrador",
    ],
}

# Recurring people in the persona's life
CONTACTS = {
    "spouse": "Claire Marsh",
    "daughter": "Lily",
    "son": "Max",
    "mother": "Janet Marsh",
    "sister": "Hannah Brooks",
    "brother": "Luke Marsh",
    "mother_in_law": "Diane Perry",
    "best_friend": "Ryan Cooper",
    "work_colleague": "James Patterson",
    "work_colleague2": "Priya Sharma",
    "work_boss": "Richard Clarke",
    "neighbor": "Dave Mitchell",
    "neighbor2": "Sandra Mitchell",
    "school_parent_friend": "Tom Harris",
    "school_parent_friend2": "Rachel Green",
    "cycling_buddy": "Marcus Webb",
    "old_friend": "Ben Walker",
    "lawyer": "Helen Crawford",
    "property_lawyer": "Simon Holt",
    "doctor": "Dr. Anand Patel",
    "dentist": "Dr. Sarah Kim",
    "kids_teacher": "Mrs. Henderson",
    "nursery_contact": "Miss Claire",
    "contractor": "Steve from BuildRight",
    "accountant": "Phil Norton",
    "fish_shop": "AquaWorld (Mark)",
}


def get_persona_context() -> str:
    """Return a short persona description to inject into prompts."""
    p = PERSONA
    return f"""The main person is {p['name']}, {p['age']}, living in {p['location']}.
Job: {p['job']}.
Spouse: {p['family']['spouse']}.
Children: {', '.join(p['family']['children'])}.
Family: {p['family']['parents']}. {p['family']['siblings']}.
Home: {p['life_details']['housing']}.
Car: {p['life_details']['car']}.
Hobbies: {p['life_details']['hobbies']}.
Health: {p['life_details']['health']}.
Kids: {p['life_details']['kids_school']}.

ALL content must be in English. ALL content must feel like it belongs to this person's
actual life — their documents, conversations, appointments, personal files.
Use real-seeming details from their daily life. Reference their actual contacts,
family members, ongoing situations."""


def pick_ongoing_situation() -> str:
    """Pick a random ongoing life situation for context."""
    return random.choice(PERSONA["ongoing_situations"])


def pick_contacts(n: int = 3) -> list[str]:
    """Pick n random contacts from the persona's life."""
    keys = random.sample(list(CONTACTS.keys()), min(n, len(CONTACTS)))
    return [CONTACTS[k] for k in keys]


# ──────────────────────────────────────────────────────────────────────
# STORYLINES — cross-category story threads
# Each storyline has consistent specific details that should appear
# across documents in different categories. This makes the data
# feel like a real person's life where a single situation touches
# legal, messaging, calendar, finance, personal, and medical.
# ──────────────────────────────────────────────────────────────────────

STORYLINES = [
    {
        "id": "fence_dispute",
        "title": "Neighbor Fence Dispute",
        "summary": """Ethan's neighbors Dave and Sandra Mitchell replaced the shared fence between
their gardens in September 2024 without asking. They moved the fence line about 30cm into
Ethan's property. Ethan noticed when planting bulbs in October 2024. He tried to talk to Dave
but Dave insists the new line is correct. Ethan hired solicitor Helen Crawford from Crawford &
Associates (ref: HC/MARSH/2024-1187). A land surveyor (Precision Surveys Ltd) confirmed the
original boundary on 15 November 2024, report ref PS-2024-3892. Helen sent a formal letter to
Dave on 28 November 2024. Dave's solicitor (Graham Foster, Foster & Webb) responded denying the
claim on 12 December 2024. Small Claims Court hearing was set for 14 March 2025 at Barnet
County Court, claim number E4KL-2025-00234. Ethan is stressed about it, discussed with Claire
many times. Legal costs so far: £1,850 plus £420 for the survey.""",
        "people": ["Dave Mitchell", "Sandra Mitchell", "Helen Crawford"],
        "dates": {"fence_replaced": "2024-09-15", "noticed": "2024-10-08",
                  "surveyor_visit": "2024-11-15", "formal_letter": "2024-11-28",
                  "response": "2024-12-12", "court_date": "2025-03-14"},
        "references": {"solicitor_ref": "HC/MARSH/2024-1187", "survey_ref": "PS-2024-3892",
                       "court_claim": "E4KL-2025-00234"},
    },
    {
        "id": "kitchen_reno",
        "title": "Kitchen Renovation",
        "summary": """Ethan and Claire want to renovate their kitchen. They got three quotes:
BuildRight Ltd (Steve) quoted £18,500, KitchenCraft (no response after initial visit),
and Modern Spaces quoted £24,200. Steve from BuildRight came on 3 January 2025 for
measurements. His quote includes: new cabinets (Howdens), quartz worktops, new plumbing for
dishwasher relocation, rewiring for additional sockets, tiling, and painting. Timeline: 4 weeks
starting 7 April 2025. Deposit of £5,550 (30%) due by 21 March 2025, rest in two installments.
Claire wants an island but Steve says the space is too narrow. They're debating whether to
extend into the dining area which would need building regs approval. Ethan is also comparing
appliance packages at Currys and John Lewis.""",
        "people": ["Steve from BuildRight", "Claire Marsh"],
        "dates": {"first_visit": "2025-01-03", "quote_received": "2025-01-10",
                  "deposit_due": "2025-03-21", "work_starts": "2025-04-07"},
        "references": {"quote_ref": "BR-Q-2025-0147", "amount": "£18,500"},
    },
    {
        "id": "fathers_estate",
        "title": "Father's Estate / Probate",
        "summary": """Ethan's father George Marsh passed away in August 2021. He left a house at
42 Clifton Road, Bristol BS8 4EJ, valued at £385,000. The will divides everything equally
between Ethan, Hannah, and Luke. Probate was granted in February 2022 (ref: PRB-2022-BRS-4419).
The house has been rented to tenant Michael Fry since March 2022 at £1,200/month. Now the
siblings are discussing whether to sell the property or keep renting. Ethan wants to sell (needs
money for kitchen renovation), Hannah agrees, but Luke wants to keep it as investment. Solicitor
Simon Holt (Holt & Partners) is handling. Current market value estimate: £420,000. The tenant's
lease expires June 2025. Capital gains tax implications being reviewed by Phil Norton
(accountant).""",
        "people": ["Simon Holt", "Hannah Brooks", "Luke Marsh", "Phil Norton", "Janet Marsh"],
        "dates": {"death": "2021-08-14", "probate_granted": "2022-02-20",
                  "tenant_since": "2022-03-01", "lease_expires": "2025-06-30"},
        "references": {"probate_ref": "PRB-2022-BRS-4419", "property": "42 Clifton Road, Bristol BS8 4EJ",
                       "property_value": "£420,000", "rent": "£1,200/month"},
    },
    {
        "id": "mums_health",
        "title": "Mum's Health Decline",
        "summary": """Ethan's mother Janet Marsh (72) in Bristol has been showing signs of memory
loss and fatigue since mid-2024. She fell at home on 18 November 2024, bruised her hip. Her GP
Dr. Sarah Collins referred her to a neurologist at Bristol Royal Infirmary. Appointment was
12 January 2025. Tests showed early-stage vascular dementia. She's been prescribed Donepezil.
Ethan, Hannah, and Luke are coordinating care — a carer visits 3 times a week (CarePlus Bristol,
£18/hour). Ethan set up a Lasting Power of Attorney with Simon Holt. He visits Bristol every
2-3 weeks, often taking the train (£45 return). Hannah is closer and does more day-to-day.
Luke helps financially. Monthly care costs: approximately £864. Ethan is emotionally affected,
writes about it in his journal, discusses with Claire.""",
        "people": ["Janet Marsh", "Hannah Brooks", "Luke Marsh", "Simon Holt"],
        "dates": {"fall": "2024-11-18", "neuro_appointment": "2025-01-12",
                  "diagnosis": "2025-01-12", "lpa_started": "2025-02-05"},
        "references": {"care_company": "CarePlus Bristol", "care_cost": "£864/month",
                       "medication": "Donepezil 5mg", "hospital": "Bristol Royal Infirmary"},
    },
    {
        "id": "ev_purchase",
        "title": "Electric Car Purchase",
        "summary": """Ethan wants to replace the 2019 VW Golf (reg: LK19 FTH, 47,000 miles) with
an electric vehicle. He's been researching since November 2024. Shortlist: Tesla Model 3 (from
£38,990), Hyundai Ioniq 5 (from £36,400), VW ID.4 (from £37,500). Test drove the Tesla at
Brent Cross on 8 February 2025 (liked it but no Apple CarPlay). Test drove Ioniq 5 at Hyundai
Enfield on 22 February 2025 (Claire loved the space). Still need to test drive ID.4. Golf
trade-in value estimated at £12,000-£14,000 by webuyanycar. Home charger installation: got a
quote from Pod Point for £899 including OZEV grant. Need to check if the semi-detached driveway
has space. Finance options: PCP vs bank loan — Barclays offering 6.9% APR. Ryan thinks Tesla is
overpriced. Marcus (cycling buddy) has an Ioniq 5 and loves it.""",
        "people": ["Claire Marsh", "Ryan Cooper", "Marcus Webb"],
        "dates": {"tesla_test": "2025-02-08", "ioniq_test": "2025-02-22",
                  "charger_quote": "2025-01-30", "golf_valuation": "2025-02-15"},
        "references": {"golf_reg": "LK19 FTH", "golf_mileage": "47,000",
                       "charger_company": "Pod Point", "charger_cost": "£899"},
    },
    {
        "id": "work_migration",
        "title": "Payment Processing Migration at Work",
        "summary": """Ethan leads the payment processing migration project at FinEdge Technologies.
They're moving from a legacy Java monolith (PayCore v2) to a new microservices architecture
(PayFlow). The project started in September 2024, deadline is 30 April 2025. Team: Ethan (tech
lead), James Patterson (backend), Priya Sharma (QA), and two contractors. Richard Clarke (CTO)
is pushing hard on the deadline because of a client commitment to Meridian Bank. Current status:
API gateway done, transaction processing 80% done, reconciliation module behind schedule.
Key risks: data migration of 2.3 million historical transactions, PCI compliance audit needed
before go-live, Stripe integration still has edge cases. Ethan often works late, causing tension
with Claire. Sprint reviews every Friday. Jira board: PAY-xxx tickets. On-call rotation
started in February.""",
        "people": ["James Patterson", "Priya Sharma", "Richard Clarke"],
        "dates": {"project_start": "2024-09-01", "deadline": "2025-04-30",
                  "pci_audit": "2025-03-20", "client_go_live": "2025-05-15"},
        "references": {"project": "PayFlow Migration", "legacy": "PayCore v2",
                       "client": "Meridian Bank", "jira": "PAY-xxx"},
    },
    {
        "id": "lily_school",
        "title": "Lily's School Struggles",
        "summary": """Lily (7, Year 3) has been struggling with maths since the autumn term.
Mrs. Henderson raised concerns at parents evening on 14 November 2024. Lily is below expected
level in multiplication and division. She gets frustrated and sometimes cries over homework.
Ethan and Claire tried Kumon but Lily hated it (attended 3 sessions in December then refused).
They're now trying an app called Mathletics (£59/year subscription started January 2025).
School has put her in a small intervention group on Tuesday afternoons. Her reading is above
average. She also had a playground incident on 6 February 2025 — came home with a bruised knee,
school said she fell but Lily said another child pushed her. Ethan sent a complaint email to the
head teacher Mr. Robinson on 10 February. She's happy about her upcoming 8th birthday party
(science theme, 15 March 2025 at home, 12 friends invited).""",
        "people": ["Mrs. Henderson", "Claire Marsh", "Lily", "Rachel Green"],
        "dates": {"parents_evening": "2024-11-14", "kumon_started": "2024-12-02",
                  "mathletics_started": "2025-01-08", "playground_incident": "2025-02-06",
                  "complaint_email": "2025-02-10", "birthday": "2025-03-15"},
        "references": {"app": "Mathletics", "app_cost": "£59/year",
                       "school": "QPA Primary School", "teacher": "Mrs. Henderson"},
    },
    {
        "id": "fish_tank",
        "title": "Tropical Fish Tank Problems",
        "summary": """Ethan's 200-litre tropical fish tank has been having issues since December
2024. Persistent green algae bloom — tried reducing light to 6 hours, added Seachem Flourish
Excel, did 30% water changes twice weekly. Water parameters on last test (23 February 2025):
pH 7.2, ammonia 0, nitrite 0, nitrate 25ppm, phosphate 1.5ppm (too high). Lost two neon tetras
and a guppy in January (suspected columnaris). Treated with eSHa 2000. Current stock: 8 neon
tetras, 5 guppies, 4 corydoras, 2 bristlenose plecos, 6 cherry shrimp. Ordered a Fluval 307
canister filter from AquaWorld (Mark) for £189 to replace the old internal filter. CO2 system
(Dennerle) is inconsistent — bubble counter shows irregular flow. Claire says the tank is an
eyesore right now and wants it sorted before her mum Diane visits at Easter. Whiskers (cat)
keeps sitting on the tank lid.""",
        "people": ["AquaWorld (Mark)", "Claire Marsh"],
        "dates": {"algae_started": "2024-12-10", "fish_deaths": "2025-01-15",
                  "filter_ordered": "2025-02-25", "diane_visit": "2025-04-18"},
        "references": {"tank_size": "200 litres", "filter": "Fluval 307",
                       "filter_cost": "£189", "treatment": "eSHa 2000"},
    },
    {
        "id": "marriage_tension",
        "title": "Marriage Tension Over Work-Life Balance",
        "summary": """Ethan and Claire have been going through a rough patch since January 2025.
The PayFlow migration project has Ethan working late most nights and some weekends. Claire feels
like she's a single parent — handling Lily's homework, Max's bedtime routine, cooking, school
runs all alone. It came to a head on 1 February 2025 when Ethan missed Max's nursery concert
because of an emergency deployment. Claire didn't speak to him for two days. They had a long
argument on 3 February — Claire said "I didn't marry your laptop" and Ethan admitted he's been
prioritizing work over family. They agreed to have a "no screens after 8pm" rule and Ethan
promised to take Fridays off in March. On 14 February (Valentine's Day), Ethan surprised Claire
with dinner at La Mia Cucina in Highgate — they talked honestly and things improved. But it's
still fragile. Claire confided in her friend Rachel that she's worried Ethan is burning out.
Ethan wrote in his journal that he's scared of losing Claire but doesn't know how to say no to
Richard at work. They're considering couples counselling — Claire found a therapist Dr. Karen
Whitfield (£85/session) through the school mums network. First session booked for 8 March 2025.""",
        "people": ["Claire Marsh", "Rachel Green", "Richard Clarke"],
        "dates": {"missed_concert": "2025-02-01", "big_argument": "2025-02-03",
                  "valentines_dinner": "2025-02-14", "counselling_booked": "2025-03-08",
                  "no_screen_rule_started": "2025-02-05"},
        "references": {"restaurant": "La Mia Cucina, Highgate", "therapist": "Dr. Karen Whitfield",
                       "session_cost": "£85/session"},
    },
    {
        "id": "ryan_fallout",
        "title": "Falling Out With Best Friend Ryan",
        "summary": """Ethan and Ryan Cooper have been best friends since university (met at
freshers week at Leeds in 2006). In November 2024, Ethan lent Ryan £3,000 to help with a
deposit on a flat after Ryan's divorce was finalized. Ryan promised to pay it back by January
2025. January came and went — Ryan kept making excuses. Ethan mentioned it casually on 28
January and Ryan got defensive, said "I thought friends don't keep score." Ethan was hurt but
let it go. Then on 15 February 2025, Ethan saw on Instagram that Ryan bought a new mountain
bike (Canyon Spectral, around £3,500). Ethan was furious — texted Ryan "nice bike, must be nice
to afford that." Ryan didn't reply for three days, then sent a long message saying the bike was
a gift from his brother and that Ethan was being unfair. They didn't speak for two weeks. Claire
told Ethan he was being stubborn. On 5 March 2025, Ryan showed up at Ethan's door with a cheque
for £1,500 (half the money) and said he'd pay the rest by April. They went to the pub (The
Flask, Highgate) and talked it out. Ryan admitted the divorce left him financially wrecked and
he was embarrassed to ask for more time. Ethan felt guilty for the Instagram comment. Things are
slowly getting back to normal but there's still some awkwardness.""",
        "people": ["Ryan Cooper", "Claire Marsh"],
        "dates": {"money_lent": "2024-11-10", "repayment_due": "2025-01-10",
                  "first_mention": "2025-01-28", "instagram_incident": "2025-02-15",
                  "ryan_text": "2025-02-18", "doorstep_visit": "2025-03-05"},
        "references": {"amount_lent": "£3,000", "amount_returned": "£1,500",
                       "remaining": "£1,500", "pub": "The Flask, Highgate"},
    },
    {
        "id": "old_flame",
        "title": "Message From an Old Flame",
        "summary": """On 20 January 2025, Ethan received an unexpected Facebook message from Naomi
Chen, his ex-girlfriend from 2010-2012. They dated for two years before she moved to Singapore
for work. The split was amicable but emotional. Naomi is back in London now, working at a design
agency in Shoreditch. She wrote: "Hey stranger, just moved back to London. Saw your profile.
How's life treating you?" Ethan felt a weird flutter — they had a genuine connection. He replied
politely, mentioned Claire and the kids. They exchanged a few messages over the next week —
catching up, reminiscing about their old flat in Hackney. Ethan didn't tell Claire about the
messages at first, which made him feel guilty. On 2 February, Naomi suggested meeting for coffee
"for old times' sake." Ethan said he'd think about it. He wrote about it in his journal — torn
between curiosity and knowing it would upset Claire. On 10 February he told Claire about the
messages. Claire was hurt he hadn't mentioned it sooner and they argued. Ethan decided not to
meet Naomi and sent her a kind message saying "I think it's best we leave things in the past."
Naomi understood. Claire was relieved but said "next time, just tell me from the start." The
whole thing made Ethan reflect on his marriage and appreciate Claire more — one reason he
planned the Valentine's dinner.""",
        "people": ["Claire Marsh", "Naomi Chen"],
        "dates": {"first_message": "2025-01-20", "coffee_invite": "2025-02-02",
                  "told_claire": "2025-02-10", "closed_door": "2025-02-12"},
        "references": {"platform": "Facebook Messenger", "naomis_job": "design agency in Shoreditch",
                       "old_flat": "Hackney, 2010-2012"},
    },
    {
        "id": "marcus_accident",
        "title": "Marcus's Cycling Accident",
        "summary": """On 22 February 2025, Ethan's cycling buddy Marcus Webb had a bad accident
during their Saturday morning ride. They were cycling along Highgate Hill when a delivery van
pulled out of a side street without looking. Marcus swerved, hit the kerb, and went over the
handlebars. He broke his collarbone and fractured two ribs. Ethan was right behind him and
saw the whole thing — he called 999 and stayed with Marcus until the ambulance came. Marcus was
taken to Whittington Hospital. Ethan was shaken up — he called Claire from the hospital and she
could hear his voice trembling. He visited Marcus in hospital that evening with grapes and a
cycling magazine. Marcus was released on 24 February with a sling and painkillers. His bike (a
Specialized Tarmac, worth about £4,000) was badly damaged. Marcus filed a police report (ref:
MET-CAD-2025-2847) and is pursuing an insurance claim against the van driver (White Transit van,
reg partially noted: KR24 ???). Ethan has been checking on Marcus every few days, bringing meals
over. The accident made Ethan think about his own safety — he ordered a new helmet (Giro Aether,
£220) and better front lights. Claire is worried and wants him to cycle less on main roads.
The cycling club did a whip-round and collected £350 to help Marcus with physio costs.""",
        "people": ["Marcus Webb", "Claire Marsh"],
        "dates": {"accident": "2025-02-22", "hospital_visit": "2025-02-22",
                  "discharged": "2025-02-24", "police_report": "2025-02-23"},
        "references": {"hospital": "Whittington Hospital", "police_ref": "MET-CAD-2025-2847",
                       "van_reg_partial": "KR24 ???", "helmet": "Giro Aether, £220",
                       "whip_round": "£350", "marcus_bike": "Specialized Tarmac"},
    },
    {
        "id": "brother_estranged",
        "title": "Growing Distance With Brother Luke",
        "summary": """Ethan and his brother Luke Marsh have been drifting apart since their father
George's death in 2021. Luke took the death very hard — he was closest to their dad and feels
guilty he wasn't there at the end (he was on a hiking trip in Scotland). The tension surfaced
during the estate discussions. Luke wants to keep their father's Bristol house as a memorial
and rental investment. Ethan and Hannah want to sell it. Luke accused Ethan of "only caring
about money" in a heated phone call on 12 January 2025. Ethan tried to explain about the
kitchen renovation costs but Luke hung up. They didn't speak for three weeks. Hannah played
mediator — calling both brothers, trying to find a compromise. On 3 February 2025, Hannah
suggested they keep the house for one more year, then revisit. Luke reluctantly agreed, Ethan
was frustrated but went along to keep the peace. Luke sent a brief "sorry for what I said"
text on 8 February. Ethan replied "it's fine" but it clearly isn't — he wrote in his journal
that he feels Luke is unreasonable and that their father would have wanted them to get along.
Janet (their mum) is upset about the boys fighting — she mentioned it to Hannah in tears.
Ethan and Luke are civil now but conversations feel strained. They used to play online chess
together every Sunday — that stopped after the argument and hasn't resumed.""",
        "people": ["Luke Marsh", "Hannah Brooks", "Janet Marsh"],
        "dates": {"heated_call": "2025-01-12", "silence_starts": "2025-01-12",
                  "hannah_compromise": "2025-02-03", "luke_apology_text": "2025-02-08"},
        "references": {"disagreement": "father's house in Bristol — sell vs. keep",
                       "chess_app": "Chess.com", "compromise": "keep house one more year then revisit"},
    },
    {
        "id": "mum_flights",
        "title": "Mum Needs Flight Tickets Booked",
        "summary": """Janet (Ethan's mum, 72) asked Ethan to help book flights from Bristol to
Edinburgh to visit Luke for his birthday on 18 April 2025. She's not good with computers and
gets confused by booking sites. This has been an ongoing back-and-forth since early March 2025.
Janet keeps changing her mind about dates. First she wanted 16-20 April, then 15-21 because
"Luke said come earlier," then back to 16-19 because she has a doctor appointment on Monday 21st.
Ethan found flights on easyJet (Bristol to Edinburgh, £67 each way) and Ryanair (£52 but from
Bristol to Edinburgh via standsted which Janet refused — "I'm not going through London"). He
sent screenshots. Janet called back saying "the Ryanair one looks cheaper" even though she just
said no to it. Claire overheard and laughed. In between all this flight talk, Janet also asks
about the weather, tells Ethan what she cooked for dinner, complains about her neighbor's dog,
asks about Lily's school and Max's nursery, reminds Ethan to wear warm clothes, and sends
blurry photos of her garden. Ethan finally booked easyJet for 16-19 April (£134 total, ref:
EZY-8847291). Then Janet called to ask if she can bring a small suitcase AND a handbag as hand
luggage. Ethan had to check the baggage policy. She also wants Ethan to print the boarding
passes because "I don't trust phone tickets." Hannah said she'd pick Janet up from Edinburgh
airport.""",
        "people": ["Janet Marsh", "Hannah Brooks", "Luke Marsh", "Claire Marsh"],
        "dates": {"first_asked": "2025-03-02", "dates_changed_1": "2025-03-05",
                  "dates_changed_2": "2025-03-08", "booked": "2025-03-12",
                  "lukes_birthday": "2025-04-18", "flight_out": "2025-04-16", "flight_back": "2025-04-19"},
        "references": {"airline": "easyJet", "route": "Bristol to Edinburgh",
                       "booking_ref": "EZY-8847291", "total_cost": "£134",
                       "rejected_option": "Ryanair via Stansted"},
    },
    {
        "id": "claire_school_drama",
        "title": "Claire's Difficult Colleague at School",
        "summary": """Claire has been venting to Ethan about a new teaching assistant at QPA
Primary called Karen Briggs who started in January 2025. Karen undermines Claire in front of
the children, contradicts her lesson plans, and went to the head teacher Mr. Robinson to
complain about Claire's "old-fashioned" teaching methods. Claire was furious — she's been
teaching for 12 years. On 20 February 2025, Claire came home in tears after Karen told a parent
that Claire "doesn't differentiate enough for SEN children." Ethan was angry on her behalf and
wanted to email the head teacher but Claire said no, she needs to handle it professionally. She
spoke to her union rep (NEU, contact: Sarah Langley) on 24 February. The union advised her to
document everything. Claire started keeping a log. On 3 March, Claire and Karen had a mediation
meeting with Mr. Robinson. Karen was passive-aggressive but agreed to "respect boundaries."
Things improved slightly but Claire still comes home stressed about it 2-3 times a week. Ethan
listens, makes her tea, and tries to be supportive — though sometimes he's distracted by his
own work stress which annoys Claire. Rachel Green (school parent friend) also noticed the
tension and told Claire "everyone prefers you to Karen." Mixed in with all this: normal chat
about what to have for dinner, Lily's reading book, Max doing something funny at nursery,
weekend plans, who's picking up the kids.""",
        "people": ["Claire Marsh", "Rachel Green"],
        "dates": {"karen_started": "2025-01-06", "crying_incident": "2025-02-20",
                  "union_call": "2025-02-24", "mediation": "2025-03-03"},
        "references": {"colleague": "Karen Briggs", "head_teacher": "Mr. Robinson",
                       "union": "NEU", "union_rep": "Sarah Langley"},
    },
]


def pick_storyline() -> dict:
    """Pick a random storyline for cross-category content generation."""
    return random.choice(STORYLINES)


def get_storyline_context(storyline: dict) -> str:
    """Format a storyline into a prompt-injectable context block."""
    dates_str = "\n".join(f"  - {k.replace('_', ' ')}: {v}" for k, v in storyline["dates"].items())
    refs_str = "\n".join(f"  - {k.replace('_', ' ')}: {v}" for k, v in storyline["references"].items())
    people_str = ", ".join(storyline["people"])

    return f"""STORYLINE: {storyline['title']}
{storyline['summary']}

Key people: {people_str}
Key dates:
{dates_str}
Reference numbers/details:
{refs_str}

IMPORTANT: Use the EXACT names, dates, reference numbers, and amounts from above.
These details must be consistent across all documents about this storyline.
Other documents about this same situation already exist with these exact details."""
