"""Test DeBERTa-v3 extractive QA on Q0003 and Q0160 chunks."""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import torch
from transformers import AutoTokenizer, AutoModelForQuestionAnswering

MODEL = "deepset/deberta-v3-large-squad2"
print(f"Loading {MODEL}...")
tokenizer = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForQuestionAnswering.from_pretrained(MODEL)
model.eval()
print("Model loaded.\n")


def ask(question, context):
    inputs = tokenizer(question, context, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        outputs = model(**inputs)
    start = torch.argmax(outputs.start_logits)
    end = torch.argmax(outputs.end_logits) + 1
    tokens = inputs["input_ids"][0][start:end]
    answer = tokenizer.decode(tokens, skip_special_tokens=True)
    score = (outputs.start_logits[0][start] + outputs.end_logits[0][end - 1]).item()
    return answer, score


# Q0003 — the chunk that confused phi4:14b
q3_context = """Date: 2021-03-15 Type: GP Consultation - Low Mood / Stress.
Father George passed away in February, which has also been a significant factor.
Patient reports increased stress at work, difficulty sleeping, and general low mood
which has increased his stress levels."""

# Q0003 — chunk with correct explicit answer
q3_context_explicit = """7. 2021-01-10: GP Consultation - Bereavement Support (Father's passing)
Patient: Mr. Ethan Marsh (DOB: 1986-05-15)
Mr. Marsh presents stating his father, George Marsh, passed away on 2021-01-05 at the age of 65."""

# Q0003 — chunk with mixed dates (the confusing one)
q3_context_noisy = """NHS ID: 771 893 4569. DOB: 2017-03-05 (Age: 7). School: QPA Primary.
George Marsh (Father of Ethan, passed away 2021). Hannah Marsh (Sister of Ethan, resides Manchester).
Janet Marsh (Mother of Ethan, resides Bristol)."""

# Q0160 — summary chunk
q160_context = """InnovateEco is a smaller company with around 70 people.
Promotions at Apex are tied to an annual review cycle, performance calibration
against 20 other seniors, and waiting for someone to leave or retire."""

# Q0160 — the long source chunk
q160_context_long = """The recruiter (Sarah from Future Talent) was pretty clear about their growth
trajectory for senior engineers. They're still small enough (around 70 people)
that individual contributions really matter, and promotions can happen faster
if you prove yourself. At Apex, it's all about the annual review cycle."""

tests = [
    ("Q0003 (ambiguous chunk)", "When did Ethan Marsh's father George Marsh pass away?", q3_context),
    ("Q0003 (explicit chunk)", "When did Ethan Marsh's father George Marsh pass away?", q3_context_explicit),
    ("Q0003 (noisy mixed dates)", "When did Ethan Marsh's father George Marsh pass away?", q3_context_noisy),
    ("Q0160 (summary)", "How many people work at InnovateEco?", q160_context),
    ("Q0160 (source)", "How many people work at InnovateEco?", q160_context_long),
]

for label, question, context in tests:
    answer, score = ask(question, context)
    print(f"=== {label} ===")
    print(f"  Q: {question}")
    print(f"  A: {answer}")
    print(f"  Score: {score:.2f}")
    print()
