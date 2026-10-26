# 07 — Creative Intelligence Report

Observed: 2026-10-27. Corpus: 534 Dubai/UAE education ads (India, active), of which 322 position Dubai as the study destination
(`03-facebook-ad-library-analysis.csv`, column `dubai_as_destination`).
Visual sample: 21 creatives (one per leading advertiser, highest variation count first), downloaded from the image/cover URLs Meta exposes in the
public Ad Library and reviewed by Claude (multimodal vision). Images are **not** redistributed here; see each Ad Library ID.

## 1. What could and could not be analysed

| Item | Status |
|---|---|
| Ad text, headline, CTA type, display format, platforms, start date, variation count (all 322 destination ads) | **Analysed** (structured Ad Library data) |
| Static images (13 of 21 sample) | **Analysed visually** with the rubric below |
| Video ads (119 destination ads) | **Cover frame only** for 7 sampled videos. Audio, voice-over, pacing, duration, subtitles beyond frame 1, and the 3-second hook in motion: **NOT ANALYSED** (no transcription tool approved; MP4 URLs exist in the Library data and could be transcribed locally later) |
| Carousel/DCO cards beyond card 1 | Text analysed; images of card 1 only |
| Delivery performance (CTR, reach, spend) | Not available; **never inferred** |

## 2. Market-level creative patterns (measured from ad data, n = 322 Dubai-destination ads)

| Signal | Measured | Reading (qualitative) |
|---|---|---|
| Format | Image 156 · Video 119 · DCO (dynamic) 37 · Carousel 10 | Static image still dominates; video is a close second |
| Placement | 319 run on Instagram, 291 on Facebook, 31 Instagram-only | Instagram is effectively universal; FB is near-universal |
| CTA type | Apply Now 136 · Sign Up 74 · Learn More 46 · See Details 35 · WhatsApp 16 · View IG profile 5 | High-commitment "Apply Now" dominates, even at the awareness stage |
| Destination | Meta instant form/redirect 194 · Website 90 · none 22 · WhatsApp 16 | Lead-form-first market; WhatsApp is strongest among Kerala advertisers |
| Variation | 128 ads belong to a multi-version set | Scaled messages: see proven angles below |
| Longevity | Median 14 days running; 16 ads ≥ 90 days | Short creative cycles; long runners are mostly small consultants |
| Language | English 452 / Malayalam 76 / Hindi 4 (all UAE-edu ads) | **Kerala is the only region with heavy vernacular Dubai advertising** |
| Hooks present (multi-label) | Scholarships 131 · Limited-time/intake 106 · Free counselling 97 · Affordability 88 · Reputation 85 · Employment assistance 73 · International career 54 · Job guarantee 26 · Dubai lifestyle 23 · Parent trust 22 · Student success 20 | **Scholarship + intake urgency + free counselling** is the market's default stack; student-success and parent-trust hooks are under-used |

### Proven angles (competitor-ad-teardown rule: ≥3 variations or ≥90 days running)

| Angle | Evidence (Ad Library IDs / signal) | Who it targets (read from the creative) |
|---|---|---|
| "Foreign (UK/Australian) degree, studied in Dubai, for less" | StudyIn × Curtin Dubai ×8 variants; DMU Dubai ×3; MWT "Earn a UK Degree in Dubai" 106 days; AEC Overseas "fraction of UK/Australian cost" | Graduates and parents, cost-sensitive |
| "No IELTS + fast offer letter + scholarship %" | Edtiger/Edhike 293 days ("24 hours offer letter", "IELTS waiver", "40% scholarship"); Education Vibes ×4; Leverage Edu "visa under 10 days" | Students with weaker English scores, urgency-driven |
| Admissions days / university fairs | Fateh "UK/Ireland/Dubai Admissions Day" ×11 variants, 96 days; StudyIn city fairs (Chennai, Jaipur) ×5 DCO; AECC Punjab fair | Tier-2 city families |
| Price anchor "Masters in Dubai from ₹5–8 lakh" | AHZ India ×5 ("₹5 Lakhs"); Leverage Edu "₹8 Lakhs" | Budget-first graduates |
| Plus-two → Dubai with stipend/paid internship (Malayalam) | TIIB.Dubai ×6, 71–74 days | Kerala Class-12 leavers and parents |
| Embedded internship / industry integration (institutions) | BITS Pilani Dubai "7.5-month integrated internship", "5.5 months mandatory corporate placement"; Hult "Dubai Internet City, Google, AWS" | Career-outcome-driven UG/MBA |

### White space (what nobody runs)

- **Transparent outcome mechanics**: no Dubai advertiser explains *how* placement works (definition, timeline, obligations), not even the ones selling guarantees.
- **Total cost of living + tuition** in one honest number: only Brookstone's own ad (₹17.5 lakh all-in) attempts it.
- **Real student outcome stories with name, role and employer**: only MAHE Dubai uses on-camera student testimonials; Leap uses UGC-style travel selfies.
- **Parent safety/ROI explainers**: 22 of 322 ads; none address safety, accommodation supervision or how money flows.
- **Myth-busting the "job guarantee" itself**: zero ads, a genuine differentiation opportunity for an honest positioning.

## 3. Scoring rubric (static images and video covers)

Seven criteria, 0–5 each (35 max): **R** headline readability at phone size · **H** visual hierarchy (one focal message) · **O** offer prominence/clarity ·
**B** branding (who is speaking, partner co-brand) · **C** credibility signals (accreditation, specifics, sourced stats; *minus* for unsourced or absolute claims) ·
**M** mobile suitability (aspect ratio, text density, safe zones) · **A** CTA visibility.
A separate **compliance flag** marks claims that conflict with ASCI education guidance or need substantiation. Scores are **qualitative judgements by one reviewer (Claude)**, not measured performance.

| # | Advertiser | Ad ID | Type | R | H | O | B | C | M | A | Total /35 | Notes / compliance flag |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | StudyIn × Curtin Dubai | 2276013526517399 | Image | 5 | 5 | 4 | 5 | 4 | 5 | 5 | **33** | Clean promise ("Study in Dubai. Earn an Australian degree."), intake date, "Book Free Counselling" button |
| 2 | BITS Pilani Dubai | 1127031563595247 | DCO card | 5 | 5 | 5 | 5 | 4 | 5 | 4 | **33** | Concrete differentiator ("BBA (Hons.) with an integrated 7.5-month internship") |
| 3 | AEC Overseas × Curtin Dubai | 2142579156600434 | DCO card | 5 | 5 | 5 | 5 | 2 | 4 | 5 | **31** | ⚠ "97% Graduate Placement Rate": no year, base or source |
| 4 | De Montfort University Dubai | 2210867970308774 | Image | 5 | 4 | 4 | 5 | 4 | 4 | 4 | **30** | Polished; intake-led |
| 5 | AHZ India | 1500368101895629 | Image | 5 | 4 | 5 | 3 | 1 | 4 | 5 | **27** | ⚠ "Guaranteed Placement" badge (image-only) + "Masters in 5 Lakhs" (tuition-only?) |
| 6 | Middlesex Dubai | 1424864703189527 | Image | 5 | 4 | 3 | 4 | 3 | 4 | 2 | **25** | Programme list is dense; no CTA in image |
| 7 | Leverage Edu (Birmingham Dubai) | 1781169449687265 | Image | 4 | 4 | 4 | 4 | 4 | 3 | 2 | **25** | QS #68 cited; "visa in under 10 days" needs substantiation |
| 8 | ICCA Dubai | 1441376628151251 | Image | 4 | 4 | 3 | 4 | 3 | 4 | 3 | **25** | ⚠ "Study and work in Dubai": work-rights implication |
| 9 | Heriot-Watt Dubai | 1453228863385782 | Carousel card | 5 | 4 | 3 | 5 | 4 | 4 | 0 | **25** | Brand-led, no CTA in image |
| 10 | Edtiger (creative branded "EDHIKE") | 1412967463948568 | Image | 4 | 3 | 4 | 2 | 3 | 3 | 4 | **23** | ⚠ Stale: "For Jan/Sept 2026 intake!" while running 293 days; brand mismatch |
| 11 | Confluence (Brookstone creative) | 1534089164699650 | DCO card | 3 | 3 | 5 | 3 | 1 | 3 | 4 | **22** | ⚠ "Guaranteed placement from AED 55,000*": footnote illegible on mobile |
| 12 | Education Vibes | 1112129701262539 | Image | 4 | 3 | 3 | 3 | 2 | 3 | 3 | **21** | ⚠ "Higher visa success ratio" unsourced; 5 bullets crowd the frame |
| 13 | SP Jain | 1362007086034668 | DCO card | 3 | 3 | 4 | 3 | 4 | 2 | 2 | **21** | Honest fine print, but unreadable at phone size |
| V1 | MAHE Dubai | 1127624992967520 | Video cover | 4 | 4 | 3 | 4 | 5 | 5 | n/a | 25/30 | **Best-practice**: real student on camera, burned-in subtitles ("MAHE Dubai, for me, was like the best option") |
| V2 | TIIB.Dubai | 923903156806690 | Video cover | 4 | 3 | 4 | 2 | 2 | 4 | n/a | 19/30 | Talking head + "Comment 'DUBAI'" (comment-to-DM mechanic) |
| V3 | Fateh Education | 1027118183065734 | Video cover | 1 | 4 | 1 | 2 | 2 | 5 | n/a | 15/30 | Expressive-face pattern interrupt; no on-frame message |
| V4 | Shiksha Study Abroad | 1148089897791470 | Video cover | 2 | 3 | 2 | 2 | 2 | 5 | n/a | 16/30 | Presenter + UAE flag; message in VO (not analysed) |
| V5 | IICCM | 1646743306885715 | Video cover | 1 | 3 | 1 | 2 | 2 | 4 | n/a | 13/30 | Founder talking head, low production |
| V6 | Leverage Edu | 953625664478606 | Video cover | 4 | 4 | 2 | 3 | 1 | 5 | n/a | 19/30 | Scenic "Study in Dubai" title card |
| V7 | Skymark Education | 1606906794355451 | Video cover | 0 | 2 | 0 | 1 | 1 | 4 | n/a | 8/30 | Unrelated sports-analytics studio scene (likely stock/AI) |
| V8 | Leap Scholar | 28208217552143581 | DCO card (photo) | 0 | 4 | 0 | 1 | 3 | 5 | 0 | 13/35 | UGC-style airport selfie with passport: authentic feel, no message |

Video covers are scored on 6 criteria (/30); CTA is not visible on a cover.

## 4. Strongest patterns to learn from (not to copy)

1. **One promise + one proof + one action** (StudyIn, BITS, DMU): headline ≤ 8 words, one specific proof (intake date, internship length, awarding university), a single button.
2. **Specificity beats superlatives**: "7.5-month integrated internship" (BITS) is more credible than "100% placement support".
3. **Co-branding with the institution** (consultant logo + university logo) lifts credibility. EduSphere should co-brand only with **written partner approval**.
4. **Real students on camera with subtitles** (MAHE) is the rarest and most credible video pattern.
5. **Comment-to-DM** ("Comment DUBAI", "DM 'DUBAI 2027'") is used by TIIB, Weconnect and UrbanCoach. It works for Reels but requires a staffed DM/WhatsApp response.

## 5. Patterns to avoid

- Guarantee badges with illegible or missing conditions (AHZ, Confluence/Brookstone).
- Unsourced placement percentages (AEC/Curtin 97%), visa-speed and visa-success claims.
- Stale intake dates on long-running ads (Edtiger).
- Off-topic stock/AI visuals (Skymark).
- Price anchors that silently exclude living costs (₹5 lakh).

## 6. Limitations

21 creatives is a convenience sample of top advertisers. One reviewer, no inter-rater check. Video judged on the cover frame only.
No competitor creative is reproduced in EduSphere deliverables; `12` concepts are original.
