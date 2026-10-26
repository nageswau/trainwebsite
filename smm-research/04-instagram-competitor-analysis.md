# 04 — Instagram Content & Engagement Analysis

Observed: 2026-10-27 · Method: logged-out headless Chromium; public profile grid and post pages; `og:description` meta for counts.
No login, no API, no paid tool. Post-level evidence: `evidence/organic-post-appendix.md` (Appendix A). Structured data with a source URL for every number: `evidence/organic-findings.json`.

## Access limits (read first)

- Logged-out Instagram shows **at most 12 grid items** per profile, including pinned posts and collabs authored by other accounts. **The 20–30 posts per account requested could not be reached** without logging in.
- Blocked: **Skymark** (18+ restricted profile, login wall; follower count only), **Algate International** ("Profile isn't available").
- Name/bio match only (no link from the brand's own site): Skymark, AECC (`aecc.india`), Confluence (`theconfluence.global`). All others were verified via a link from the brand's FB page or website.
- Stories were not accessible. Highlights: names only. Comments: only a few render logged-out, so **an unanswered-looking question is not proof the brand never replied.**
- Reach, impressions, saves, shares and Insights: **never accessed, never estimated.**

**Engagement formula:** per-post ER% = (visible likes + visible comments) ÷ IG followers (from `og:description`, rounded e.g. "99K") × 100.
Account ER = median over the account's own posts with visible likes. It is approximate because the follower counts are rounded.

## 1. Account table

| Competitor | Handle | Followers | Total posts | Own posts seen | Posts/week* (window) | Median likes | Median ER% | Format mix (seen) | Highlights (visible names, abridged) |
|---|---|---|---|---|---|---|---|---|---|
| India - StudyIn | in_studyin | 99K | 5,054 | 8 | 6.2 (Oct 17–26) | 21 | 0.02 | Reels 7, video 2, img/carousel 3 | City fairs (Delhi, Chennai, Bengaluru, Lucknow), Pre-departure |
| Skymark Education | skymark.education | 65K | 3,180 | BLOCKED | — | — | — | — | — |
| Fateh Education | fateh.educationofficial | 303K | 1,146 | 11 | 5.9 | 59 | 0.02 | Reels 8, img 4 | City tour highlights (Pune, Bengaluru, Mumbai…) |
| Algate International | algateinternational | BLOCKED | — | — | — | — | — | — | — |
| AECC Global (India) | aecc.india | 244K | 3,225 | 10 | 15.4 | 6 | 0.003 | img 7, Reels 5 | Testimonials, Fairs & Events, country tabs |
| Leverage Edu | leverageedu | 427K | 2,523 | 9 | 9.0 | 43 | 0.01 | Reels 7, img 5 | Students Speak, Careers, Student life |
| Leap Scholar | leapscholar | 640K | 1,590 | 10 | 11.2 | 764 | 0.12 | img 8, Reels 4 | Real Talk, Success Stories, Full Scholarships |
| Shiksha Study Abroad | shikshastudyabroad | 83K | 1,024 | 12 | 5.1 | 61 | 0.07 | Reels 12 | Success Stories, VISA SUCCESS, Q&A, Webinar |
| upGrad Abroad | upgradstudyabroad | 89K | 1,303 | 6 | 8.0 | 19 | 0.02 | Reels 12 | TheirSAJourney, Webinars, EduExpo |
| IICCM | iiccm.in | 49K | 3,880 | 3 | n/a† | 691 | 1.43 | img 11, Reel 1 | **"Dubai Placements", "Anantara Dubai", "Rixos UAE", "Grand Hyatt Doha"** |
| Middlesex Univ. Dubai | middlesexdubai | 69K | 7,170 | 12 | 19.2 | 109 | 0.16 | Reels 7, img 5 | Student Life, Support, FAQ's, Alumni, Accommodation |
| Heriot-Watt Dubai | hwdubai | 73K | 1,889 | 12 | 1.6 | 109 | 0.15 | img 8, Reels 4 | none visible |
| De Montfort Univ. Dubai | dmudubai | 61K | 2,365 | 11 | 7.0 | 110 | 0.18 | img 11, Reel 1 | none visible |
| BITS Pilani Dubai | bitspilanidubai | 19K | 2,792 | 11 | 6.3 | 20 | 0.11 | img 11, Reel 1 | Open Day, FAQ, Student Life, Career Services |
| SP Jain Global | spjainglobal | 37K | 2,387 | 7 | 14.0 | 84 | 0.24 | Reels 7, img 5 | GMBA Life, SG Myth/Facts |
| MAHE Dubai | manipaldxb | 18K | 3,112 | 8 | 7.9 | 327 | **1.87** | Reels 9, img 3 | Podcast Series, Alumni Meet, Open House |
| The Confluence Global Education | theconfluence.global | 317 | 6 | 6 | n/a (all posts Aug 9–11) | 0 | 0.0 | img 5, Reel 1 | — |
| TIIB Dubai | tiib.dubai | 5,094 | 347 | 9 | 3.5 | 45 | 0.88 | Reels 9, img 3 | — |

\* Posts/week = (dated unpinned grid items − 1) ÷ span days × 7. Short windows exaggerate the rate; treat it as indicative.
† IICCM's visible grid is dominated by old pinned posts (2022–2026), so its frequency is not computable and its ER is inflated by those pinned posts.

## 2. Patterns

| Theme | Observation (evidence in Appendix A) | Gap for EduSphere |
|---|---|---|
| Educational content | Consultancies teach through **country/cost/salary comparisons** (Shiksha "Germany vs Italy", "Australia vs New Zealand"; StudyIn "UK vs New Zealand"; Leverage part-time earnings) | **Nobody compares Dubai** with UK/Australia/India on cost, recognition and outcomes |
| Career advice | Leap ("Why would someone leave Google to build AI in Dubai?"), Fateh job-application tips, AECC "where is the world hiring" | Dubai-specific job-market explainers with sources are rare |
| Student success | Leap/Shiksha "Success Stories" highlights; MAHE alumni podcast; Middlesex graduation content; Confluence reel "Why did Ashish Roy choose **Brookstone Dubai**?" (confirms Confluence resells BIGS) | Success content rarely states programme, timeline and outcome together |
| Dubai student life | Branch campuses own this (Middlesex "Student Life", "Accommodation"; BITS clubs; DMU campus) | Consultancies post almost no Dubai life content, an opening for EduSphere UGC |
| Tuition & living costs | Cost appears almost only as **scholarships** (MAHE "AED 25 million fund", BITS "up to 75%", HWU Diwali award) | **No account showed Dubai living costs in AED/INR**, a clear white space (C06, C09, C12) |
| Admissions | Fairs dominate (StudyIn city fairs, Fateh city tours, DMU/BITS at Najah 2026) | Online-first admissions explainers for Tier-2 audiences |
| Placement support | IICCM highlights named after Dubai/UAE hotels (implied placements); Confluence "Guaranteed Placement from AED 55,000*" on a 317-follower account | Verified placement transparency is absent |
| Scholarships | Leap "Full Scholarships" highlight; Comment-to-DM guides | Scholarship eligibility explained with criteria is rare |
| Parent guidance | Keyword flag "parent" ≤ 1 per account; Leap reel "When Varsha told her parents…" | **Parent content is rare across all 16 accessible accounts** |
| Engagement mechanics | Leap "Comment LEAP/LINK/FUTURE/Canada" (2,675 likes / 395 comments on one post): comment-to-DM inflates comment counts | Use comment-to-DM only with staffed replies |
| Hashtags | Brand + generic (#StudyAbroad, #StudyAbroadIndia, #GlobalEducation); Dubai campuses use campus tags | EduSphere: brand tag + #StudyInDubai + #DubaiStudents + topic tags; avoid hashtag stuffing |

### Highest observed engagement (accessible accounts, own posts)

MAHE Dubai (median ER ≈ 1.87%, student/alumni reels) and TIIB (≈ 0.88%, founder/student stories) beat much larger consultancy accounts
(Leap 0.12%, AECC 0.003%). On this sample, **smaller, people-led campus accounts engage better than large consultancy accounts.**
This is a correlation on ≤ 12 posts per account; do not treat it as causal.

## 3. Comment questions and objections (visible, logged-out)

| Account | Comment (verbatim, abridged) | Theme |
|---|---|---|
| Fateh Education | "Would you guys help in Dubai as well" | Dubai service awareness: **demand signal** |
| Heriot-Watt Dubai | "Still haven't received entry permit 😢" | Visa/entry-permit anxiety |
| Leap Scholar | "Leap Scholar, stop making promises you cannot deliver on. I want accountability…" | Trust / broken promises |
| upGrad Abroad | "Please provide the refund of our registration fee asap!!!!"; "Poor refund handling… No transparency, no accountability" | **Refund distrust**: directly relevant to a fee-back offer |
| Shiksha / others | "Bro fees detail", "Fully funded scholarship iruka bro 🤔" | Fees and scholarships |
| Heriot-Watt Dubai | "Please check dm" / "Could you please check your DM?" | Slow DM response |

**Implication:** students already associate study-abroad brands with refunds that are slow or never paid. A fee-back promise
will be read through that lens. Publishing the claim process and payer upfront (C18–C20) is essential.

## 4. Limitations

12-item cap; keyword flags only work on English captions (Arabic and Malayalam not coded); follower counts rounded; no Stories; no private metrics;
one observation day. Re-run while logged in (the user's own account, read-only and human-supervised) to reach 20–30 posts per account.
