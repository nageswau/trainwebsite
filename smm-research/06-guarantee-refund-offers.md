# 06 — Guarantee & Refund Competitor Claims Report

Observed: 2026-10-27 · Source: public Meta Ad Library (country = India, active ads) for 13 search terms, plus public web pages for written terms.
Every Ad Library ID links to `https://www.facebook.com/ads/library/?id=<ID>`. Evidence classes follow the project constitution
(`UNVERIFIED` = third-party claim not backed by a document we could inspect).

## 0. Headline findings

1. **The EduSphere offer already exists in the market, sold by the institution itself and by at least four other consultants.**
   EduSphere's Dubai partner **BIGS = Brookstone Institute of Global Studies, Dubai** runs its own India ad:
   "**Not Placed? Half Your Fee Comes Back** … We put ours in the enrolment agreement. If you complete the programme and aren't placed,
   half your fee comes back. The conditions are published, not buried." (ID `2146143089665140`, page "Brookstone Institute of Global Studies, India",
   first seen 2026-09-23, FB+IG, 9 page likes at observation). Consultants advertise the same programme as "Guaranteed placement from AED 55,000*"
   (The Confluence Global Education, `1534089164699650`), "Minimum Assured Package: AED 50,000 (Placement assurance email shared on Day 1 – subject to eligibility)"
   (Weconnect overseas, `1978014122873386`), "100% Placement Assurance" (Best Career Counselling Surat, `1869964704193821`, AED 85,200 → AED 68,160 KHDA-approved Global Management Program),
   and "Work across all 7 emirates while you study" (EdushikshaGuide, `1092820360248248`).
   **Implication:** EduSphere cannot win on the offer itself, because it is not exclusive. It can win on **clarity, documentation and honest qualification**.
2. **The "published" conditions could not be found.** `brookstone.ae` (fetched 2026-10-27) shows "100% Placement Support", "KHDA Approved",
   "not a degree-awarding institution", "Program Fees: AED 85,200", and **no** guarantee, refund or placement-policy page. Its footer
   "Career Outcome" and "All Inclusive Fees" links point to `#`. Classification: **UNVERIFIED** until the enrolment agreement is inspected.
3. **Claims are inconsistent across sellers of the same programme.** The salary floor is quoted as AED 50,000 vs AED 55,000. The guarantee is
   "guaranteed" vs "assured" vs "assurance email … subject to eligibility". The refund is "half your fee" (Brookstone) vs "100% placement assurance" (Surat).
   The degree is described as an "MBA" (Brookstone, Confluence) while BIGS describes itself as a non-degree-awarding professional training institute
   and the programme as a "Global Management Program". The UK award is attributed to Plymouth Marjon University in the ads, but the BIGS site does not name it.
4. **A UK "job guarantee / fee back in 9 months" cluster is aggressive in Kerala (Malayalam creatives).** Skymark Education, 24 Study Abroad and
   Eduvertex advertise "100% Job Guarantee … if no job within 9 months, 100% fee refund". The closest public source is the University of Law (UK)
   **Employment Promise**, which returns 100% of fees made up of **50% cashback + 50% course credit**. The ads present it as a 100% fee refund.
5. **Text scanning undercounts image-only claims.** AHZ India's creative (`1500368101895629`) shows a "Guaranteed Placement" badge in the image that is absent
   from its ad text. AEC Overseas × Curtin Dubai (`2142579156600434`) shows "97% Graduate Placement Rate" in the image with no period or source.

## 1. Regulatory yardsticks used (verify current text before relying on them)

| Source | What it says (summary) | URL |
|---|---|---|
| ASCI Guidelines for Advertising of Educational Institutions | No implying enrolment guarantees a job/admission/salary unless substantiated; disclaimer "past record is no guarantee of future prospects" in a font not smaller than the claim; **no "100%" for abstract claims such as "100% placement/job assistance"**; placement stats only from the latest completed year with total-student denominator | https://www.ascionline.in/wp-content/uploads/2023/05/ASCI-GUIDELINES-FOR-EDUCATIONAL-INSTITUTIONS-PROGRAMMES-AND-PLATFORMS.pdf |
| CCPA — Prevention of Misleading Advertisement in Coaching Sector (Nov 2024) | Prohibits false claims on fee/refund policies, "guaranteed job security or salary increases", testimonials without written consent; requires prominent disclaimers. Counselling is excluded from "coaching"; applicability to overseas-study consultants is a **legal question** | https://www.exchange4media.com/advertising-news/govt-issues-guidelines-to-crack-down-on-misleading-ads-by-coaching-centres-138682.html |
| Meta Special Ad Categories | Employment, housing, financial products and issues/political ads. Ads promoting job opportunities/internships may fall in "Employment" (restricted targeting); education ads generally do not. **Ads that read like a job offer risk re-categorisation or rejection** | https://developers.facebook.com/documentation/ads-commerce/marketing-api/audiences/special-ad-category |
| EduSphere internal | `docs/delivery/SEO_SMM_BACKLOG.md` seo-011 proposes banning "guaranteed job", "job guarantee", "100% placement" on EduSphere pages (DEC-SCOPE-234 **proposed, not recorded**) | repo |

## 2. Claim register (Dubai/UAE study offers)

| # | Advertiser | Ad ID(s) | Exact advertised claim (verbatim excerpt) | Written terms found? | Eligibility / exclusions stated | Refund timeline | What counts as a job | Status | Likely student misunderstanding |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Brookstone Institute of Global Studies, India (institution) | 2146143089665140 | "Not Placed? Half Your Fee Comes Back" · "If you complete the programme and aren't placed, half your fee comes back." · "₹17.5 lakh covers tuition, accommodation, flights and insurance." · "Applications close 29 October." | **No**. Ad says "published"; none found on brookstone.ae | "complete the programme" only | Not stated | Not stated | UNVERIFIED (claim by provider) | "Half my fee" = half of ₹17.5 lakh all-inclusive? Or tuition only? "Placed" = any job, internship, or salary ≥ AED 50k? |
| 2 | The Confluence Global Education | 1534089164699650 (DCO, 2 cards; creative shows Brookstone logo) | "Guaranteed placement from AED 55,000*" · "UK Degree • Internship • Guaranteed Placement*" · "6–8 months of embedded internship" | No (asterisk; footnote text illegible in creative) | none in text | n/a | "from AED 55,000" (annual? total?) | UNVERIFIED | Reads as an unconditional job + salary guarantee; the internship may be counted as "placement" |
| 3 | Weconnect overseas | 1978014122873386 (carousel card "Study at BIGS university") | "Study in Dubai – Assured Career Opportunity!" · "Minimum Assured Package: AED 50,000 (Placement assurance email shared on Day 1 – subject to eligibility)" · "Minimum 50% Academic Requirement · No IELTS Required" | No; "assurance email" is not a contract | 50% academics; "subject to eligibility" undefined | n/a | "package" AED 50k | UNVERIFIED | An email ≠ an enforceable agreement; "package" may include allowances |
| 4 | Best Career Counselling Surat | 1869964704193821 | "100% Placement Assurance" alongside "Please note: this is a paid study programme for graduates, not a job opening" and "Not a job or work visa offer" | No | Bachelor's graduates | n/a | n/a | UNVERIFIED; "100%" abstract claim conflicts with ASCI | Contradictory: assurance vs "not a job offer" |
| 5 | TIIB.Dubai (institution) | 941235029006853, 923903156806690 | "Guaranteed Paid Internships (Earn while you learn!)" · "1000 Dirhams PAID Internship" · "54% Scholarship" (Malayalam, Plus-Two audience) | No (web search found no TIIB terms) | Plus-two pass | n/a | Internship, AED 1,000 | UNVERIFIED | "Paid internship" ≠ job; AED 1,000 stipend vs Dubai living costs |
| 6 | IICCM (culinary, India campus with Dubai career angle) | 1430552335158267, 2362976427780374 +24 | "Written placement guarantees in India & abroad" · "100% Placement Guarantee (With Written Agreement)" | Not public; a "written agreement" is claimed | none in ad | n/a | 4★/5★ hotels "India and abroad" | UNVERIFIED (claimed written) | Abroad placement implied but not promised |
| 7 | AHZ India | 1500368101895629 (+6 variants) | Image: "Study Masters in 5 Lakhs Dubai · Low Tuition Fee · **Guaranteed Placement**"; text: "Study Masters in Dubai from ₹5 Lakhs" | No | none | n/a | none | UNVERIFIED; image-only claim | "₹5 lakh" likely tuition only, excluding living costs |
| 8 | AEC Overseas × Curtin University Dubai | 2142579156600434 | Image: "97% Graduate Placement Rate. Career-Ready, in Dubai." | Not cited (no year, denominator or source) | n/a | n/a | n/a | UNVERIFIED statistic | Reads as Dubai-campus outcomes; may be the parent university's global figure |
| 9 | Adi Group of Institutions | 1046835734852741, 1011112211923300 | "100% Placement Support … Available in Kerala & Dubai" | n/a (support, not a guarantee) | n/a | n/a | n/a | "100%" abstract claim (ASCI) | Support read as a guarantee |
| 10 | Leacon Wayanad | 1807003443979330 | "Full-Time Job + Part-Time Study · 100% Placement & Job Assistance" (Dubai, weekend classes) | No | n/a | n/a | n/a | UNVERIFIED | Implies a job is provided alongside study; visa/work-right implications unexplained |
| 11 | Leverage Edu | (video set, 24 days) | "Eligible students may qualify for the Golden Visa*" | No | asterisked | n/a | n/a | Conditional, asterisk | Golden Visa read as an automatic study outcome |

**Positive disclaimer models observed (Dubai jobs/visa, not education):** Adman Voyage `1093059850279640`: "Job support does not guarantee placement."
immigrationvingsabroad `1828513918562688`: "No job or visa outcome is guaranteed." These show disclaimers in the ad body, the standard EduSphere should meet.

## 3. Benchmark claims outside Dubai (same mechanism, India audience)

| Advertiser | Ad ID(s) | Claim | Public terms | Gap vs ad |
|---|---|---|---|---|
| Skymark Education (Kerala; offices incl. Dubai) | 1742183293522791, 1121342043741934, 1419617683616470 | UK LLM / MSc Legal Technology "100% Job Guarantee" · "if no job within 9 months, 100% refund on fees" (Malayalam) | Closest public scheme: University of Law **Employment Promise**: "100% of your fees back, made up of 50% as cashback, plus 50% as credit towards another course"; full T&Cs in PDFs; 9-month trigger. https://www.law.ac.uk/employability/employment-promise/ | Ad says 100% refund; source says 50% cash + 50% credit. "Job" not defined on the source page either |
| 24 Study Abroad | 899093973285650, 1004854042660653 | "100% Job Guarantee · Tuition fee refund if no job in 9 months · ₹3 lakh scholarship*" | as above (inferred, not stated) | same |
| Eduvertex Study Abroad | 2687860201611930 | "100% Tuition Fee Refund by the university if you don't get a job within 9 months after graduation" | as above (inferred) | same |
| Kraftshala (India, not study abroad) | 2013241619414104, 1484127416181642 | "Program is job-linked and if your job < 4.5L, you get a 60% refund" / "< 7.5 LPA → 60% refund" | Homepage pledge: "if you don't land a job with a minimum CTC, you get a 60% refund", thresholds per programme. https://www.kraftshala.com/ | **Best-practice reference:** threshold-based definition of a job (CTC), publicly stated per programme, placement reports linked. No full refund T&C page found |
| Collegedunia Study Abroad | 2157325651569891, 2284079695721473 | "50% VISA Fee Refund*" / "Visa Refund up to 50%" | Not found | "Visa refund" ambiguous: visa fee? on refusal? |
| AECC Global | 1312266524205180 | IELTS-score-based tuition refund ("score below 6 … full tuition refund") | Not reviewed | Different mechanism (test-prep), not placement |
| Magnate Study Abroad | 1134797936071976 | "up to 70% fee refund via tax credit" (Malta Get Qualified scheme) | Government tax-credit scheme, not a provider refund | "Refund" framing for a tax credit |
| GradezeAbroad | 1475214567811443 (+2) | "Master's abroad … backed by a 100% placement guarantee" (webinar funnel) | Not found | Unqualified 100% guarantee |

## 4. Comparison with EduSphere's proposed offer

| Dimension | EduSphere "Job Guarantee or 50% Fee Back" (as stated by the user, 2026-10-27) | Market reality | Recommendation |
|---|---|---|---|
| Institution | GBS Dubai + BIGS Dubai ("all", meaning unclear: all courses vs all partners) | BIGS already sells a half-fee-back promise directly; GBS public site shows employability **support** only, no guarantee | Treat the BIGS scheme as **BIGS's contract**; EduSphere is a reseller of the promise. **GBS coverage needs written proof**, since none is public |
| Refund base | Tuition, paid by the institution | Brookstone ad bundles tuition + accommodation + flights + insurance at ₹17.5 lakh | State "50% of tuition fees paid to the institution" (never "50% of fees") and give the rupee/AED figure |
| Contract status | User says signed + legal-approved; **document not yet inspected** | No competitor publishes terms | Publishing the terms is the **differentiator**. Until EduSphere has read the contract, the status stays `NEEDS_CONFIRMATION` and refund/guarantee ads stay on hold |
| Wording | "Job Guarantee" | Internal seo-011 proposal + ASCI 100%/guarantee rules + CCPA coaching guidance | Use **"Placement-or-50%-Tuition-Back (conditions apply)"**. Avoid the bare word "guarantee"; never use "100%" |

## 5. Questions the contract must answer before any guarantee/refund ad runs

1. Exact covered programmes (BIGS Global Management Program? which GBS courses?) and intakes.
2. Definition of "placed": full-time vs internship, minimum salary (AED 50k or 55k? annual? gross? allowances included?), location (UAE only?), employer type, and whether an offer the student declines counts.
3. Placement window (e.g. within N months of completion) and how the clock starts.
4. Student obligations: attendance %, passing all modules first attempt, career-service sessions, minimum applications/interviews, visa/document compliance, conduct.
5. Refund base: tuition only; exclusions (application, visa, accommodation, insurance, flights, scholarships deducted?); refund currency/FX.
6. Claim process: claim deadline, evidence, decision time, payment time, payer (institution), and escalation route.
7. EduSphere's legal role: agent/referrer only? What liability does EduSphere carry if the institution does not pay?
8. Legal sign-off covering **Indian advertising** (ASCI/CCPA/Consumer Protection Act), not only UAE/KHDA.

## 6. Limitations

- India-only, active ads, keyword search; ~13 searches × ~100 ads each; not exhaustive (Meta reports e.g. ~26,000 results for "Study in Dubai").
- Text detection misses claims baked into images/videos; 21 creatives were reviewed visually (see `07`).
- Landing pages behind `fb.me` (Meta instant forms) cannot be opened logged-out; any terms inside forms were not seen.
- No terms were verified by contacting advertisers.
