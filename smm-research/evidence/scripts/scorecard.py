"""Builds 09-competitor-scorecard.csv. Scores 0-5 per criterion; None = N/A (excluded from the denominator, never zero)."""
import csv
OUT = "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/smm-research/09-competitor-scorecard.csv"
W = {"offer_clarity": 12, "creative_quality": 12, "social_consistency": 10, "engagement_signals": 8, "student_success_evidence": 10,
     "transparency": 14, "cta_strength": 8, "brand_credibility": 12, "job_claims_responsibility": 7, "refund_policy_clarity": 7}
BASIS = {"offer_clarity": "Q", "creative_quality": "Q (07 rubric /35 or /30 rescaled)", "social_consistency": "M (IG posts/week, visible grid)",
         "engagement_signals": "M (IG median ER%)", "student_success_evidence": "Q", "transparency": "Q", "cta_strength": "Q+M (CTA types)",
         "brand_credibility": "Q", "job_claims_responsibility": "Q (5=specific/substantiated, 1=unsubstantiated guarantee)",
         "refund_policy_clarity": "Q (only if a refund is claimed)"}
N = None
#           offer cre  cons eng  succ trans cta  cred job  refund   type                note
D = [
 ("India - StudyIn",          5, 4.7, 5,  2,  2, 3, 5, 4, N, N, "Consultant", "Curtin Dubai co-brand; 99 UAE ads; ER 0.02%"),
 ("Fateh Education",          3, 2,   5,  1,  3, 2, 4, 3, N, N, "Consultant", "DCO copy mismatch (UK text on Dubai headline); '45,000+ success stories' unsourced"),
 ("IICCM",                    3, 2,   N,  N,  3, 2, 3, 3, 1, N, "Institution (India)", "'100% Placement Guarantee (With Written Agreement)' not public; ER inflated by pinned posts"),
 ("De Montfort University Dubai", 4, 4.3, 5, 4, 2, 4, 4, 5, N, N, "Branch campus", "Clean intake-led creatives"),
 ("SP Jain School of Global Management", 4, 3, 5, 4, 3, 5, 2, 5, 4, N, "Institution", "Honest fine print, poor legibility"),
 ("AEC Overseas",             5, 4.4, N,  N,  2, 2, 5, 4, 2, N, "Consultant", "'97% Graduate Placement Rate' unsourced"),
 ("AHZ India",                4, 3.9, N,  N,  N, 1, 5, 2, 1, N, "Consultant", "'Guaranteed Placement' badge image-only; 'Masters in 5 Lakhs'"),
 ("Middlesex University Dubai", 3, 3.6, 5, 4, 4, 4, 2, 5, N, N, "Branch campus", "Strong student life/alumni highlights"),
 ("Leap Scholar",             3, 2,   5,  3,  4, 2, 4, 4, N, N, "Consultant", "Comment-to-DM; visible accountability complaint"),
 ("Heriot-Watt University Dubai", 3, 3.6, 3, 4, 2, 4, 1, 5, N, N, "Branch campus", "226K-view programme reel on FB; few CTAs"),
 ("TIIB Dubai",               4, 3.2, 4,  4,  3, 1, 4, 2, 1, N, "Institution", "'Guaranteed Paid Internships' unverified; Malayalam plus-two"),
 ("Leverage Edu",             4, 3.3, 5,  1,  3, 3, 3, 4, 3, N, "Consultant", "'Golden Visa*', 'visa in under 10 days'"),
 ("BITS Pilani Dubai Campus", 5, 4.7, 5,  3,  2, 4, 4, 5, 5, N, "Branch campus", "Specific internship lengths: best practice"),
 ("MAHE Dubai",               3, 4.2, 5,  5,  5, 3, 2, 5, N, N, "Branch campus", "Real student video testimonials; highest ER"),
 ("Shiksha Study Abroad",     3, 2.7, 5,  3,  3, 3, 3, 4, N, N, "Consultant/portal", "'Free counselling, no hidden charges'"),
 ("The Confluence Global Education", 4, 3.1, 1, 1, 2, 1, 4, 1, 1, N, "Consultant (BIGS reseller)", "'Guaranteed placement from AED 55,000*'; 317 IG followers; no posts since Aug"),
 ("Brookstone Institute of Global Studies, India", 5, N, N, N, N, 2, 3, 2, 2, 2, "Institution (EduSphere partner BIGS)", "'Not Placed? Half Your Fee Comes Back'; terms claimed published, not found"),
 ("Skymark Education",        3, 1,   N,  N,  3, 1, 3, 2, 1, 1, "Consultant (UK benchmark)", "'100% Job Guarantee / 100% fee refund in 9 months' vs source 50% cash + 50% credit; IG login-walled"),
]
keys = list(W)
rows = []
for name, *vals in D:
    sc, typ, note = vals[:10], vals[10], vals[11]
    num = sum(W[k] * s / 5 for k, s in zip(keys, sc) if s is not None)
    den = sum(W[k] for k, s in zip(keys, sc) if s is not None)
    rows.append([name, typ] + ["N/A" if s is None else s for s in sc] + [round(num / den * 100, 1), den, note])
rows.sort(key=lambda r: -r[-3])
with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["competitor", "type"] + [f"{k} (w={W[k]}; {BASIS[k]})" for k in keys] + ["score_normalised_0_100", "weight_coverage_of_100", "notes"])
    for i, r in enumerate(rows, 1): w.writerow(r)
    w.writerow([])
    w.writerow(["METHOD: score_normalised = sum(weight*score/5 over scored criteria) / sum(weights of scored criteria) * 100. N/A criteria are excluded, never scored 0. "
                "M = measured from public data (2026-10-27), Q = qualitative judgement by one reviewer (Claude). Compare totals only between rows with similar weight coverage."])
for r in rows: print(r[0], r[-3], r[-2])
