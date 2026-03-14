# Perihan — Investor Overview

## The Problem

People don't need another AI chatbot that knows the internet. They need an AI that knows *them*.

Your life is scattered across dozens of apps — WhatsApp groups, Gmail threads, Google Drive, local files, calendars, project boards. When you need to find something, plan something, or make sense of your own situation, there's no single assistant that can help — because no assistant has the full picture.

Today, finding "what did the lawyer say?" means scrolling through chat histories. But the deeper problem goes beyond search. Nobody is helping you *act* on your own data: preparing for tomorrow's meeting using last week's conversations, tracking your personal goals across scattered notes, or coaching you through a tough period with full context of your life.

The average person is in 20+ WhatsApp groups, receives 100+ emails per week, and stores thousands of files. This isn't just a search problem — it's an **assistance** problem. And it gets worse every day.

## The Solution: Perihan

Perihan is a **private AI personal assistant that actually knows you**. It starts by indexing your messages, documents, and files into a personal knowledge base. But searching your data is just the foundation — the real product is an assistant that uses that knowledge to **help you manage your life**.

The vision has three layers:

1. **Know** — Index and understand all your personal data (POC, working today)
2. **Answer** — Find information and answer questions across all sources (POC, working today)
3. **Assist** — Coach you, prepare you, remind you, and help you act (planned skills, in development)

Ask in any language. Get answers with source citations. All running privately on your machine.

### What It Does Today (Proof of Concept)

| Capability | Status |
|---|---|
| Index WhatsApp chat exports (txt, xml) | Working |
| Index local files (pdf, docx, md, txt, xml) | Working |
| Index Google Drive files (with LLM summaries) | Working |
| Index Gmail messages | Working |
| Hybrid search (keyword + vector + fuzzy matching) | Working |
| Multi-language support (English, Turkish tested) | Working |
| Typo-tolerant search ("hedgehg" finds "Hedgehogs") | Working |
| Deep Think mode (agentic fallback for hard questions) | Working |
| Switch between local AI (Ollama) and cloud AI (Gemini) | Working |
| One-click Windows installer | Working |
| REST API for integration | Working |

### Real-World Validation

The POC is tested against **27 real questions** drawn from actual WhatsApp groups, legal conversations, school communications, and personal documents — in both English and Turkish. Current accuracy: **90%+** (43-44 out of 46 possible points).

Examples of questions Perihan can answer today:
- "Was a lost water bottle found in the Beavers 37th group?" (finds specific message)
- "What is the court date in the apartment case?" (finds legal info in Turkish)
- "What is Seb's email address?" (finds contact info across chats)
- "Which school groups am I in on WhatsApp?" (synthesises across multiple sources)
- "suleyman mutlu apartmaninda ne oldu?" (handles typos, missing Turkish characters)

## Technology

### Architecture

Perihan uses a **hybrid RAG (Retrieval-Augmented Generation) pipeline** with multiple fallback layers:

```
User question
    |
Hybrid Search (keyword scoring + vector similarity + fuzzy matching)
    |
LLM generates answer from retrieved context
    |
If uncertain → Deep Think (agentic tool-calling, searches deeper)
    |
If still uncertain → Google Drive native search fallback
```

**Key technical differentiators:**
- **Hybrid search** combines TF-IDF-style keyword scoring with vector embeddings — handles both exact recall and semantic queries
- **Fuzzy matching** with typo correction — critical for real-world queries with misspellings and missing diacritics
- **Cross-folder diversity** — prevents one source from monopolising results
- **LLM-agnostic** — works with local models (Ollama/Llama) for full privacy, or cloud models (Gemini) for better quality
- **Agentic fallback** — when simple retrieval isn't enough, the system autonomously uses tools to dig deeper

### Stack
- **Backend:** Python, FastAPI, ChromaDB (vector DB)
- **LLMs:** Google Gemini (cloud), Ollama (local) — switchable at runtime
- **Integrations:** Google Drive API, Gmail API, Google OAuth
- **Distribution:** Standalone Windows installer with embedded Python 3.12

## Market Opportunity

### The Personal AI Market

The market is moving from "AI that knows everything on the internet" to **"AI that knows everything about me."** Major players are heading this direction (Apple Intelligence, Google Gemini with Gmail/Drive, Microsoft Copilot), but they are locked to their own ecosystems.

**Nobody owns the cross-platform personal knowledge layer.**

A user's life doesn't live in one ecosystem. Their school communication is on WhatsApp, legal documents are on Google Drive, work files are local, family photos are on iCloud. Perihan is platform-agnostic by design.

### Target Users

**Phase 1 — Individual power users:**
- Parents managing school groups, activities, and family logistics
- Professionals who need to search across years of messages and documents
- People managing legal, medical, or financial correspondence
- Multilingual users (existing tools struggle with mixed-language data)

**Phase 2 — Teams and small businesses:**
- Shared knowledge bases across team communication channels
- Client/server deployment for organisations
- Role-based access to company knowledge

**Phase 3 — Platform:**
- Plugin ecosystem for new data sources (Slack, Telegram, Outlook, Notion)
- Skill system (coaching, wellbeing adviser, project management)
- API marketplace for third-party integrations

## Product Roadmap

### Near-Term (Next 6 months) — From Search to Assistant

| Feature | Description |
|---|---|
| **Web UI** | User-friendly frontend (currently API-only) |
| **Image indexing** | OCR and vision-based indexing of photos and screenshots |
| **Email attachment reading** | Parse and index attachments (PDFs, docs) from indexed emails |
| **Trello/calendar integration** | Index boards, cards, events — the assistant knows your schedule and tasks |
| **Personal coaching skill** | The user shares their biography, goals, routines, and priorities. Perihan acts as a life coach — tracking progress, suggesting adjustments, holding the user accountable. Unlike generic AI coaches, Perihan has read your actual messages, documents, and calendar. |
| **Project coaching skill** | AI project management assistant — understands project context from indexed docs and communication, helps plan, prioritise, and track progress |
| **Wellbeing adviser skill** | Personal wellbeing support grounded in your context — not generic advice, but guidance informed by what you're actually going through |

### Medium-Term (6-18 months) — Deeper Intelligence

| Feature | Description |
|---|---|
| **Knowledge graph** | Entity relationship mapping — Perihan understands *who* people are, how they relate to you, and what you've discussed with them |
| **Analytical queries** | Map-reduce pipeline for "analyse all my data" questions (e.g. "How has my relationship with X changed over time?") |
| **Proactive insights** | "You have a meeting with X tomorrow — here's what you discussed last time." "You said you'd follow up with Y this week." |
| **Slack/Teams integration** | Index workplace communication |
| **Mobile app** | iOS/Android companion — your assistant in your pocket |
| **Multi-user support** | Client/server architecture with authentication |
| **Telegram/Signal** | Additional messaging platform support |

### Long-Term Vision — The Personal AI Platform

| Feature | Description |
|---|---|
| **Skill marketplace** | Third-party skills and data source plugins — anyone can extend what Perihan can do |
| **Autonomous actions** | Not just answering — sending reminders, drafting replies, scheduling meetings on your behalf |
| **Enterprise edition** | On-premise deployment, SSO, audit logs, team coaching |
| **Neural network research** | Custom fine-tuned models optimised for personal data understanding |

## Deployment Models

Three planned deployment tiers:

1. **Singleton (current)** — Single user runs Perihan locally on their machine. Full privacy, zero cloud dependency (with Ollama). One-click Windows installer already built.

2. **Server-only** — For teams and companies. Central Perihan server indexes shared data. Multiple users connect via API.

3. **Client-only** — Lightweight client that connects to a remote Perihan server. For organisations that want centralised infrastructure.

## Competitive Landscape

| Product | Personal Data | Cross-Platform | Private/Local | Multi-Language | Open |
|---|---|---|---|---|---|
| **ChatGPT** | No (internet only) | No | No | Yes | No |
| **Google Gemini** | Google only | No | No | Yes | No |
| **Apple Intelligence** | Apple only | No | Yes | Limited | No |
| **Microsoft Copilot** | Microsoft only | No | No | Yes | No |
| **Perihan** | **Any source** | **Yes** | **Yes** | **Yes** | **Yes** |

Perihan's moat is **source-agnostic personal knowledge with privacy-first architecture**. Big tech assistants will always be limited to their own ecosystems. Generic AI coaches don't know you. Perihan combines cross-platform knowledge with personalised assistance — the full-context personal assistant that nobody else can build.

## Current Status

- **Stage:** Proof of concept, working end-to-end
- **Validation:** 27 real-world test cases, 90%+ accuracy
- **Distribution:** Windows installer package ready
- **Data sources:** WhatsApp, Gmail, Google Drive, local files (pdf/docx/txt/md/xml)
- **Languages tested:** English, Turkish (architecture is language-agnostic)
- **LLM support:** Gemini (cloud), Ollama with any local model

## What We Need

Funding to move from POC to product:

- **Frontend development** — Web UI and mobile apps
- **Additional integrations** — Slack, Telegram, Outlook, Notion, Trello
- **Infrastructure** — Cloud deployment option, user authentication, multi-tenancy
- **Team** — Frontend developer, DevOps, QA
- **Go-to-market** — Landing page, beta program, community building

## The Journey: Document Assistant to Personal Assistant

```
TODAY (POC)                    NEXT 6 MONTHS                   LONG-TERM VISION
─────────────                  ──────────────                   ────────────────
"What did the                  "Prepare me for                  "Handle my week.
 lawyer say?"                   tomorrow's meeting               Remind me about the
                                based on our last                follow-ups, draft
"Find Seb's email"             conversation"                    the reply to the
                                                                 lawyer, and coach
"Which school groups           "I've been stressed —            me on my goals."
 am I in?"                      help me think through
                                what's going on"

Search your data.              Coach you with context.          Manage your life.
```

The POC proves the hardest part: reliably finding information across messy, multilingual, cross-platform personal data. That foundation makes everything else possible — because a personal assistant is only as good as its knowledge of you.

## The Vision

Every person deserves an AI assistant that knows their life as well as a trusted human assistant would — one that remembers every conversation, understands every relationship, and helps navigate every day. Privately, in any language, from any source.

**Perihan: Your life, assisted.**
