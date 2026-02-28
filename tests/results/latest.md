# Perihan QA Report — 2026-02-28 02-30
Model: `gemini-2.5-flash`  |  Judge: `gemini-2.5-flash`
Score: 26/40 (65.0%)  |  Previous: 0/40 (0.0%) [unknown]  |  Change: +26

## Category Breakdown
| Category | Score | Max | % |
|----------|-------|-----|---|
| Direct Recall (English) | 7 | 10 | 70% |
| Direct Recall (Turkish) | 6 | 10 | 60% |
| Personal / Contact Info | 2 | 4 | 50% |
| Multi-source / Synthesis | 2 | 4 | 50% |
| Uncertainty / Out of Scope | 4 | 6 | 67% |
| Fuzzy / Typo Tolerance | 5 | 6 | 83% |

## Improvements ✅
- Q1: 0pts → 2pts — Perihan's response correctly and completely answers the question, providing all the key details present in the expected answer.
- Q2: 0pts → 2pts — Perihan's response accurately and completely matches the expected answer, providing all the necessary conditions for antibiotic administration by the school.
- Q3: 0pts → 1pts — Perihan's response is correct but misses the detail about there being no inset day, which was part of the expected answer.
- Q5: 0pts → 2pts — Perihan's response accurately states that the group exchanged New Year wishes, which aligns perfectly with the expected answer.
- Q6: 0pts → 2pts — Perihan correctly identifies both court dates, 13 Şubat and 3 Mart 2026, matching the expected answer.
- Q8: 0pts → 2pts — Perihan's response correctly states the 15% fee, the reason for it (being a relative), the basis (2026 AAÜT), and the deduction at the end of the full jurisdiction case, matching all details in the expected answer.
- Q9: 0pts → 2pts — Perihan's response correctly and completely identifies the health problem, the follow-up plan, and the potential treatment, aligning with all key details in the expected answer, even though it includes an additional, seemingly factual detail not present in the expected answer.
- Q12: 0pts → 2pts — Perihan's response accurately and completely covers all the reasons provided in the expected answer.
- Q13: 0pts → 1pts — Perihan correctly identified two of the WhatsApp groups but missed several others listed in the expected answer.
- Q14: 0pts → 1pts — The response correctly identified Ezg-Ron but missed Castle Gate Close and included 🦔Hedgehogs🦔 which was not part of the expected answer.
- Q15: 0pts → 2pts — Perihan correctly states that it does not have the information, aligning with the expected answer, and provides relevant context from the documents it did search.
- Q16: 0pts → 2pts — Perihan correctly states that it does not have real-time weather information, aligning with the expected answer.
- Q18: 0pts → 2pts — Perihan successfully resolved the typo "hedgehg class" to "Hedgehogs class" and returned relevant information about the class from the documents.
- Q19: 0pts → 1pts — Perihan correctly identified the apartment and provided some contextual details, but it failed to return the expected "court/legal discussion" and incorrectly stated that the documents do not specify what happened there.
- Q20: 0pts → 2pts — Perihan's response correctly identifies the lost item (black water bottle) associated with the Beavers group and provides the relevant details, matching the expected answer.

## Full Results
| ID | Category | Q | Score | Reason |
|----|----------|---|-------|--------|
| Q1 | Direct Recall (English) | Was a lost water bottle found in the Beavers 37th group? | ✅ 2 | Perihan's response correctly and completely answers the question, providing all the key details present in the expected answer. |
| Q2 | Direct Recall (English) | Can the school administer antibiotics? | ✅ 2 | Perihan's response accurately and completely matches the expected answer, providing all the necessary conditions for antibiotic administration by the school. |
| Q3 | Direct Recall (English) | When did QPA school reopen after the holidays? | ⚠️ 1 | Perihan's response is correct but misses the detail about there being no inset day, which was part of the expected answer. |
| Q4 | Direct Recall (English) | What event did 🦔Hedgehogs🦔 ask parents to bake for? | ❌ 0 | Perihan correctly identified "Carols with the Band" but hallucinated an additional event ("PFA bake sale") and specific years, while also missing details from the expected answer. |
| Q5 | Direct Recall (English) | What did the Castle Gate Close group talk about on New Year'… | ✅ 2 | Perihan's response accurately states that the group exchanged New Year wishes, which aligns perfectly with the expected answer. |
| Q6 | Direct Recall (Turkish) | SÜLEYMAN MUTLU APARTMANI grubunda mahkeme tarihleri nelerdir… | ✅ 2 | Perihan correctly identifies both court dates, 13 Şubat and 3 Mart 2026, matching the expected answer. |
| Q7 | Direct Recall (Turkish) | SÜLEYMAN MUTLU APARTMANI davasında ne tür bir suçlama var? | ❌ 0 | Perihan's response is a server error message, which is not an answer to the question and indicates a failure to respond. |
| Q8 | Direct Recall (Turkish) | Avukat Alp'in aldığı ücret oranı nedir? | ✅ 2 | Perihan's response correctly states the 15% fee, the reason for it (being a relative), the basis (2026 AAÜT), and the deduction at the end of the full jurisdiction case, matching all details in the expected answer. |
| Q9 | Direct Recall (Turkish) | 👑Kazananlar👑 grubunda birinin sağlık sorunu neydi? | ✅ 2 | Perihan's response correctly and completely identifies the health problem, the follow-up plan, and the potential treatment, aligning with all key details in the expected answer, even though it includes an additional, seemingly factual detail not present in the expected answer. |
| Q10 | Direct Recall (Turkish) | BUND grubunda Noel mesajı kim gönderdi ve ne söyledi? | ❌ 0 | Perihan stated it could not find the information, but the expected answer shows the information should have been available and retrieved. |
| Q11 | Personal / Contact Info | What is Seb's email address? | ❌ 0 | Perihan's response indicates it could not find the information, but the expected answer provides a specific email address, meaning Perihan failed to retrieve the correct information. |
| Q12 | Personal / Contact Info | Avukat Alp tam yargı davası açmamı neden tavsiye etti? | ✅ 2 | Perihan's response accurately and completely covers all the reasons provided in the expected answer. |
| Q13 | Multi-source / Synthesis | Which school groups am I in on WhatsApp? | ⚠️ 1 | Perihan correctly identified two of the WhatsApp groups but missed several others listed in the expected answer. |
| Q14 | Multi-source / Synthesis | Which groups sent New Year messages? | ⚠️ 1 | The response correctly identified Ezg-Ron but missed Castle Gate Close and included 🦔Hedgehogs🦔 which was not part of the expected answer. |
| Q15 | Uncertainty / Out of Scope | What did I have for lunch last Tuesday? | ✅ 2 | Perihan correctly states that it does not have the information, aligning with the expected answer, and provides relevant context from the documents it did search. |
| Q16 | Uncertainty / Out of Scope | What is the weather in my city today? | ✅ 2 | Perihan correctly states that it does not have real-time weather information, aligning with the expected answer. |
| Q17 | Uncertainty / Out of Scope | Annemin telefon numarası nedir? | ❌ 0 | Perihan fabricated an answer by providing a phone number instead of stating it does not have that information, which was the expected behavior. |
| Q18 | Fuzzy / Typo Tolerance | "hedgehg class" hakkında ne biliyorsun? | ✅ 2 | Perihan successfully resolved the typo "hedgehg class" to "Hedgehogs class" and returned relevant information about the class from the documents. |
| Q19 | Fuzzy / Typo Tolerance | "suleyman mutlu" apartmanında ne oldu? | ⚠️ 1 | Perihan correctly identified the apartment and provided some contextual details, but it failed to return the expected "court/legal discussion" and incorrectly stated that the documents do not specify what happened there. |
| Q20 | Fuzzy / Typo Tolerance | Beavers grubunda kayıp bir eşya var mıydı? | ✅ 2 | Perihan's response correctly identifies the lost item (black water bottle) associated with the Beavers group and provides the relevant details, matching the expected answer. |
