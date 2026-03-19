"""Prompts for QA generation — one per strategy."""


def single_doc_prompt(doc_path: str, doc_content: str, qa_count: int) -> str:
    """Strategy 1: Generate search/factual questions from a single document."""
    return f"""You are a QA dataset generator. Given the document below, generate exactly {qa_count} question-answer pairs.

RULES:
- Questions should be answerable ONLY from the information in this document
- Questions should test whether a search system can find specific facts
- Answers should be concise and directly extracted from the document
- Include the exact text passage that contains the answer as "evidence"
- Vary question types: who, what, when, where, how much, which

DOCUMENT PATH: {doc_path}
---
{doc_content}
---

Respond with valid JSON only. No markdown, no explanation. Use this exact format:
{{
  "questions": [
    {{
      "question": "the question text",
      "answer": "the concise answer",
      "evidence": [
        {{
          "file": "{doc_path}",
          "excerpt": "the exact passage from the document that contains the answer"
        }}
      ]
    }}
  ]
}}"""


def same_category_prompt(docs: list[dict], category: str, qa_count: int) -> str:
    """Strategy 2: Generate reasoning questions from same-category documents."""
    doc_sections = []
    for d in docs:
        doc_sections.append(f"=== FILE: {d['path']} ===\n{d['content']}")
    all_docs = "\n\n".join(doc_sections)
    file_list = ", ".join(d["path"] for d in docs)

    return f"""You are a QA dataset generator. Given the {len(docs)} documents below (all from the "{category}" category), generate exactly {qa_count} question-answer pairs.

RULES:
- Questions should require REASONING or INTERPRETATION, not just finding a single fact
- Good question types:
  - Compare/contrast information across documents
  - Identify patterns or trends across multiple entries
  - Infer emotions, motivations, or intentions from the text
  - Summarize or synthesize information from multiple documents
  - Timeline questions (what happened first/last, sequence of events)
- Answers should reference specific documents as evidence
- Each answer should explain the reasoning, not just state a fact

DOCUMENTS:
{all_docs}

Respond with valid JSON only. No markdown, no explanation. Use this exact format:
{{
  "questions": [
    {{
      "question": "the question text",
      "answer": "the answer with reasoning",
      "evidence": [
        {{
          "file": "path/to/file.txt",
          "excerpt": "the relevant passage from that file"
        }}
      ]
    }}
  ]
}}

Available files: {file_list}"""


def cross_storyline_prompt(docs: list[dict], storyline: str, qa_count: int) -> str:
    """Strategy 3: Generate multi-doc questions across categories for a storyline."""
    doc_sections = []
    for d in docs:
        doc_sections.append(f"=== FILE: {d['path']} ===\n{d['content']}")
    all_docs = "\n\n".join(doc_sections)
    file_list = ", ".join(d["path"] for d in docs)

    return f"""You are a QA dataset generator. Given the documents below (from DIFFERENT categories but related to the same life situation: "{storyline}"), generate exactly {qa_count} question-answer pairs.

RULES:
- Questions MUST require connecting information from at least 2 different documents
- Good question types:
  - Combine facts from different document types (e.g., legal letter + diary entry + financial record)
  - Ask about the full picture that only emerges when reading multiple documents
  - Timeline questions that span across document types
  - Financial totals that require adding amounts from different documents
  - Emotional/personal impact questions that connect formal documents with personal reflections
- Answers MUST cite evidence from multiple documents
- Each answer should show HOW the information connects across documents

DOCUMENTS:
{all_docs}

Respond with valid JSON only. No markdown, no explanation. Use this exact format:
{{
  "questions": [
    {{
      "question": "the question text",
      "answer": "the answer connecting information from multiple documents",
      "evidence": [
        {{
          "file": "path/to/file1.txt",
          "excerpt": "relevant passage from first file"
        }},
        {{
          "file": "path/to/file2.txt",
          "excerpt": "relevant passage from second file"
        }}
      ]
    }}
  ]
}}

Available files: {file_list}"""
