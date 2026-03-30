# Small Model Limitations — Evidence from RAG Testing

## Findings (2026-03-30)

Local small models fail at basic fact extraction even when the answer is explicitly stated in the provided text.

### phi4:14b — Q0003: "When did George Marsh pass away?"
- Answer "passed away on 2021-01-05" is stated verbatim in 3 of 5 returned chunks
- Model returns **2017** (Lily's DOB year, which appears near "George Marsh" in another chunk)
- Fails to disambiguate nearby dates — picks the wrong one
- Benchmark mode (same model, same question, single document) answers correctly
- **Diagnosis:** Multiple chunks with overlapping entities and different dates confuse the model

### gemma3:27b — Q0160: "How many people work at InnovateEco?"
- Summary chunk explicitly says "InnovateEco is a smaller company with around 70 people"
- Model returns "I don't have enough information"
- The summary chunk is ~4000 tokens with many sections (People, Places, Dates, Key Facts)
- **Diagnosis:** Answer buried in a long structured chunk — model loses it in the noise

## Implications

These are not reasoning or inference tasks. They are **basic reading comprehension** — extracting a fact that is literally stated in the input. Models at 14-27B parameters fail at this reliably.

For autonomous on-device use cases (cars, phones, IoT):
- Requirements are harder: real-time, safety-critical, ambiguous sensor input, no human fallback
- If a 14B model can't read "passed away 2021" from clean text, it won't reliably interpret noisy sensor data
- Industry approach: narrow specialized models (distillation for one task), not general-purpose small LLMs

## The Case for Specialized Reasoning Models

General LLMs at 14B params are trained to know everything but know everything *poorly*. For RAG and on-device use cases, world knowledge is irrelevant — the documents/sensors provide all the facts. The model only needs to:
1. Read the given context carefully
2. Match the question to the relevant part
3. Extract and return the answer

This is a much narrower task than "be a general assistant." A small model distilled specifically for context-grounded QA (reading comprehension + extraction) would likely outperform phi4:14b at a fraction of the size.

This is essentially what BERT-family models did — no generation, just extraction. The industry moved toward general LLMs, but for on-device and embedded use cases, the pendulum may swing back toward task-specific models. The right tool isn't a small LLM that's supposed to know everything — it's a specialized reasoning model that knows nothing but reads perfectly.
