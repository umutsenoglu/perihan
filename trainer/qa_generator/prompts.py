"""Prompts for QA generation — one per strategy."""


def single_doc_prompt(doc_path: str, doc_content: str, qa_count: int,
                      similar_docs: list[dict] | None = None) -> str:
    """Strategy 1: Generate search/factual questions from a single document.

    If similar_docs is provided (other docs of the same type), the prompt tells
    the LLM about them so ambiguous questions get expected answers covering ALL
    matching documents, not just the primary one.
    """
    similar_section = ""
    if similar_docs:
        similar_section = f"""
IMPORTANT — SIMILAR DOCUMENTS EXIST:
There are {len(similar_docs) + 1} documents of the same type (including the primary one above).
Here are the others:

"""
        for sd in similar_docs:
            similar_section += f"=== FILE: {sd['path']} ===\n{sd['content']}\n\n"

        similar_section += """When you write a question that could apply to ANY of these similar documents
(e.g., "When is the grocery list dated?" when there are multiple grocery lists),
the expected answer MUST cover ALL matching documents, not just the primary one.

For example:
- BAD: "When is the grocery list dated?" → "06/01/2025" (only one doc)
- GOOD: "When is the grocery list dated?" → "There are multiple grocery lists dated: 06/01/2025, 08/09/2025, 09/06/2025" (covers all)
- ALSO GOOD: "In the grocery list that mentions organic chicken, what date is it?" → "06/01/2025" (specific enough for one doc)

You may write EITHER kind of question:
1. Specific questions targeting the primary document (use disambiguating details)
2. Broad questions where the answer covers all similar documents
"""

    return f"""You are a QA dataset generator. Given the document below, generate exactly {qa_count} question-answer pairs.

RULES:
- Questions should test whether a search system can find specific facts
- Answers should be concise and directly extracted from the document(s)
- Include the exact text passage that contains the answer as "evidence"
- Vary question types: who, what, when, where, how much, which

DOCUMENT PATH: {doc_path}
---
{doc_content}
---
{similar_section}
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
