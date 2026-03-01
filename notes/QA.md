# Perihan — WhatsApp QA Test Cases

Real questions based on indexed WhatsApp data. Each entry includes the expected answer and which chat it comes from, so results can be verified objectively.

---

## Category 1: Direct Recall (English)

**Q1:** Was a lost water bottle found in the Beavers 37th group?
- **Expected:** Yes — a black water bottle (Mikey's) was found at the end.
- **Source:** Beavers 37th / 2026-01-30

---

**Q2:** Can the school administer antibiotics?
- **Expected:** Only if the prescription is 4 times a day. If it's 3 times a day, the school won't do it.
- **Source:** Hedgehogs class / 2026-02-26

---

**Q3:** When did QPA school reopen after the holidays?
- **Expected:** Monday 5th January. No inset day.
- **Source:** 🦋🦋3NH🦋🦋 / 2026-01-03

---

**Q4:** What event did 🦔Hedgehogs🦔 ask parents to bake for?
- **Expected:** Carols with the Band. Donations of home-baked nut-free cakes/biscuits needed at studio drop-off on Thursday 11th December.
- **Source:** 🦔Hedgehogs🦔 / 2025-12-04

---

**Q5:** What did the Castle Gate Close group talk about on New Year's Day?
- **Expected:** Everyone wished each other Happy New Year.
- **Source:** Castle Gate Close / 2026-01-01

---

## Category 2: Direct Recall (Turkish)

**Q6:** SÜLEYMAN MUTLU APARTMANI grubunda mahkeme tarihleri nelerdir?
- **Expected:** 13 Şubat'ta biri mahkemeden arandı, 3 Mart 2026'da mahkeme var.
- **Source:** SÜLEYMAN MUTLU APARTMANI / 2026-01-20

---

**Q7:** SÜLEYMAN MUTLU APARTMANI davasında ne tür bir suçlama var?
- **Expected:** Kasten adam öldürme. İddianame hazırlandı, tüm taraflara tebliğ edildi. Davaya katılmak isteyenlerin bunu açıkça beyan etmesi gerekiyor.
- **Source:** SÜLEYMAN MUTLU APARTMANI / 2026-01-20

---

**Q8:** Avukat Alp'in aldığı ücret oranı nedir?
- **Expected:** %15 (akraba olduğu için 2026 AAÜT üzerinden işlem yaptı, tam yargı davası sonunda o ücreti de düşecek).
- **Source:** 114603149250795 / 2026-02-20

---

**Q9:** 👑Kazananlar👑 grubunda birinin sağlık sorunu neydi?
- **Expected:** Şişlik var, ağrısı azaldı. Doktor birkaç hafta daha takip edecek, geçmezse küçük bir operasyonla iltihaplı bezi alacak.
- **Source:** 👑Kazananlar👑 / 2025-12-04

---

**Q10:** BUND grubunda Noel mesajı kim gönderdi ve ne söyledi?
- **Expected:** "Merry Christmas gençler 🎄 Hediyeler için teşekkür ederiz" yazıldı.
- **Source:** BUND / 2025-12-25

---

## Category 3: Personal / Contact Info

**Q11:** What is Seb's email address?
- **Expected:** seb.chevenement@yahoo.fr
- **Source:** Ezg-Ron / 2026-01-01

---

**Q21:** What is Dominik's URL?
- **Expected:** www.umuttesto.com/7839809873 (Dominik Prod tenant in Web Application Access document)
- **Source:** trainer/s/Web_Application_Access.docx

---

**Q12:** Avukat Alp tam yargı davası açmamı neden tavsiye etti?
- **Expected:** Dosyadaki sorumlu şahıslar bitik durumda, icra kabiliyeti yok. Kurumların sorumluluğu var ve diğer müştekiler de bu yola başvuruyor.
- **Source:** 114603149250795 / 2026-02-20

---

## Category 4: Multi-source / Synthesis

**Q13:** Which school groups am I in on WhatsApp?
- **Expected:** Beavers 37th, Hedgehogs class, 🦔Hedgehogs🦔, 🦋🦋3NH🦋🦋, QPA 4L, parents
- **Source:** Multiple folders

---

**Q14:** Which groups sent New Year messages?
- **Expected:** At least Castle Gate Close and Ezg-Ron (both have 2026-01-01 messages with New Year wishes). Other groups like QPA 4L, Hedgehogs etc. are also correct if mentioned.
- **Source:** Castle Gate Close / 2026-01-01, Ezg-Ron / 2026-01-01

---

## Category 5: Uncertainty / Out of Scope

**Q15:** What did I have for lunch last Tuesday?
- **Expected:** System should say it doesn't know — no food/meal data in chats.

---

**Q16:** What is the weather in my city today?
- **Expected:** System should say it doesn't know — real-time data not available.

---

**Q17:** Annemin telefon numarası nedir?
- **Expected:** System should say it doesn't know — phone numbers are not stored as metadata.

---

## Category 6: Fuzzy / Typo Tolerance

**Q18:** "hedgehg class" hakkında ne biliyorsun?
- **Expected:** Should resolve to "Hedgehogs class" and return relevant info.

---

**Q19:** "suleyman mutlu" apartmanında ne oldu?
- **Expected:** Should match "SÜLEYMAN MUTLU APARTMANI" and return the court/legal discussion.

---

**Q20:** Beavers grubunda kayıp bir eşya var mıydı?
- **Expected:** Should match "Beavers 37th" and return the black water bottle story.

---

## Category 7: Trainer File Recall

**Q22:** What is Deniz's motorbike's brand?
- **Expected:** Royal Enfield
- **Source:** trainer/denizmuratoglu.txt

---

**Q23:** Abdullah ile ilk yazışma tarihim ne zaman?
- **Expected:** 30 Ağustos 2006
- **Source:** WhatsApp / Abdullah

---

**Q24:** What are my online fish sellers?
- **Expected:** Abyss, SwellUK, Sims, Auatics to Your Door, RiverPark, Tropco, marineworldaquatics, Essex, Vision, Delta, DC, aquatropics, lgpleco, chens discus, riftvalleycichlids, The Reef Experience
- **Source:** Google Drive spreadsheet (Fish sellers sheet)

---

**Q25:** Where did Umut's grandparents migrate from?
- **Expected:** Umut's paternal grandparents immigrated from Macedonia to Turkey.
- **Source:** trainer / personal background

---

## Scoring Guide

| Result | Score |
|--------|-------|
| Correct answer, right source | ✅ 2 pts |
| Correct answer, wrong/missing source | ⚠️ 1 pt |
| Partially correct | ⚠️ 1 pt |
| Wrong answer or hallucination | ❌ 0 pts |
| Correctly says "I don't know" (Q15-17) | ✅ 2 pts |

**Max score: 42 pts**
