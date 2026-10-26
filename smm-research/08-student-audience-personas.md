# 08 — Student Audience Personas & Social Audience Strategy

Observed: 2026-10-27. Personas are **evidence-based hypotheses**: built from (a) audience signals written into 322 competitor Dubai-study ads,
(b) public market data, and (c) organic comment questions (`04`, `05`). They are not survey results. Validate them with EduSphere CRM data
once leads arrive.

## 1. Market context (public sources)

| Fact | Value | Source (accessed 2026-10-27) | Confidence |
|---|---|---|---|
| Indian students in the UAE (all levels incl. school) | ≈ 2.53 lakh (as on 1 Jan 2025) | MEA data via press, https://www.mea.gov.in/Images/CPV/557-en-01-04-12-2025.pdf | Medium (UAE row not seen in the annexure itself) |
| Indian share of Dubai international higher-ed students | 42–43% (2024–25, KHDA) | https://gulfnews.com/uae/indian-students-top-dubais-global-intake-at-43-pakistanis-at-6-1.500190286 | Medium (secondary reporting of KHDA) |
| Dubai private HE providers | 41, of which 37 international branch campuses; 42,026 students (2024–25) | https://www.education-uae.com/dubai-higher-education-growth-2025/ | Medium |
| Student part-time work in UAE | Permit-based; hour limits **conflicting** across sources (15 h/week vs 6 h/day) | credila.com, aeccglobal.in blogs | **Low: do not advertise work rights until verified with MOHRE/ICP** |

## 2. Signals observed in competitor creatives (n = 322 Dubai-destination ads)

| Signal | Ads | Implication |
|---|---|---|
| Graduates / Masters / 1-year PG | Masters 58 · MBA 19 | Core market is post-graduation |
| Class 12 / plus-two | concentrated in Malayalam ads (TIIB, Dream Abroad) | Kerala UG market, often parent-decided |
| Parents addressed directly ("your child") | 22 | Under-served (Fateh, AEC, SP Jain only) |
| Working professionals / weekend study | Leacon (Sat–Sun classes), BITS MBA "work while you study" | Niche, but present |
| Missed-admission / gap-year rescue | Best Career Counselling Surat ("Missed MBA admission this year? Your year isn't wasted.") | Timely seasonal angle (Oct–Jan intakes) |
| Regional focus | Malayalam 76 of 534 UAE-edu ads; fairs in Chennai, Jaipur, Coimbatore, Delhi, Punjab | Kerala + South India + Tier-2 North |
| Price anchors | ₹5 lakh (AHZ), ₹8 lakh (Leverage), ₹17.5 lakh all-in (Brookstone), AED 68,160–85,200 | Budget band ₹5–20 lakh; "all-in" vs "tuition-only" confusion |

## 3. Personas

### P1 — "Arjun", final-year BCom/BBA student, Tier-2 city (20–22)
- **Goal:** a 1-year international PG that leads to a Gulf job; avoid a 2-year Indian MBA without a top brand.
- **Motivations:** international exposure, salary in AED, "foreign degree" status, peers already in the Gulf.
- **Affordability questions:** "What is the total cost, not just tuition?", "Is there an education loan?", "Can I work part-time?"
- **Objections:** "Is a Dubai degree valid in India?", "Is the job guarantee real or a trap?", "Agent fees?"
- **Content that would work:** cost breakdown carousel; "What counts as placement" explainer; alumni day-in-the-life Reels.
- **Conversion action:** eligibility check (lead form with qualifying questions) → counselling call.

### P2 — "Neha", recent graduate (B.Tech/BSc IT, 22–24), 0–2 years' experience
- **Goal:** AI/Data/Cyber Master's with industry exposure, as an alternative to UK/Canada visa uncertainty.
- **Motivations:** tech hub narrative (Dubai Internet City), lower cost than UK, proximity to India.
- **Objections:** "Will employers in Dubai hire freshers?", "Is the degree the same as the UK main campus?"
- **Content:** programme comparison Reels (Heriot-Watt/BITS style specificity); "same degree?" myth-buster; live Q&A with a faculty or alum.
- **Conversion:** webinar sign-up → counselling.

### P3 — "Rahul", MBA aspirant who missed CAT cut-offs or Indian admissions (22–27)
- **Goal:** not lose a year; 1-year global MBA/management programme with an internship.
- **Motivations:** speed, embedded internship, placement assurance.
- **Highest exposure to guarantee claims.** Must understand non-degree vs degree (e.g. BIGS = KHDA-approved training institute, UK award via partner).
- **Content:** "Before you sign: 7 questions to ask about any placement promise" (positions EduSphere as the honest advisor).
- **Conversion:** offer-terms explainer → document check.

### P4 — "Anjali", working professional (25–32), 2–6 years' experience
- **Goal:** career switch or a Gulf move with a credential.
- **Objections:** opportunity cost, family, part-time vs full-time feasibility, visa sponsorship after study.
- **Content:** LinkedIn-style carousels, case studies, weekend-format comparisons.
- **Conversion:** 1:1 profile evaluation.

### P5 — "Thomas", Class 12 student in Kerala (17–18), parent-led decision
- **Goal:** affordable UG abroad close to family in the Gulf.
- **Motivations:** relatives in the UAE, Malayalam-language guidance, scholarships, stipend/internship.
- **Constraint:** **minor**. Meta restricts targeting and content for under-18s. Address the **parent**, or target 18+ only; never collect data from minors without guardian consent.
- **Content:** Malayalam parent-explainer videos; scholarship eligibility; hostel and safety walkthroughs.
- **Conversion:** parent counselling (WhatsApp).

### P6 — "Mr & Mrs Menon", parents (45–55), funding decision-makers
- **Goal:** safe, reputable, ROI-positive education; avoid fraud.
- **Questions:** safety, accommodation supervision, total cost and payment schedule, who holds the money, refund rules, visa and Emirates ID process, job outcome evidence.
- **Content:** "Where your money goes" explainer; campus/hostel tours; parent-to-parent testimonial (with written consent); live parent sessions.
- **Conversion:** parent webinar → family counselling.

## 4. Facebook & Instagram audience hypotheses (to test; verify options in Ads Manager first)

> Settings below must be re-checked in Ads Manager at build time. The installed `audience-builder` skill states that Meta retired interest
> categories in Jan 2026 and that broad targeting usually wins. That statement is from the skill author and is **not independently verified** here.

| Layer | Hypothesis | Why | Notes |
|---|---|---|---|
| Broad (primary) | India, 18–30, all genders; Advantage+ audience; let the creative do the targeting (persona-specific hooks) | Algorithm aims by creative; competitors' ads are persona-explicit | Exclude existing applicants via a customer list |
| Geo clusters (test cells) | Kerala; Tamil Nadu + Karnataka; Gujarat + Maharashtra; Punjab/Delhi NCR | Observed competitor concentration (Malayalam ads, city fairs) | Vernacular creative for Kerala |
| Parents | 40–60, India, broad, parent-angle creatives | Parent-trust hook under-used by competitors | No targeting of minors |
| Interest-based (if available) | Study abroad, IELTS/PTE, MBA, Dubai, UAE | Legacy approach; may not be available | Treat as a control only |
| Retargeting | 50% video viewers (30d), IG/FB engagers (60d), lead-form openers not submitted (30d), website visitors via Pixel/CAPI (30d) | Lower CPL, higher intent | Pixel/CAPI must be verified (`pixel-conversions` skill) |
| First-party | CRM leads/enrolled students → custom audience (exclude) and a 1% lookalike seed (only with consent under the DPDP Act 2023) | Seed quality | Needs consent wording + legal check |
| Special Ad Category | Keep education ads out of "Employment" by **not** advertising job openings; if a creative reads as a job offer, Meta may re-categorise or reject it | Policy | Disclaimer: "This is a study programme, not a job offer" |

## 5. Gaps

- No EduSphere CRM history yet to validate personas by conversion.
- Instagram comment mining was partial (login wall; see `04`).
- Work-rights and visa facts need official verification before any creative uses them.
