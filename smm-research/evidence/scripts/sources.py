import csv, json, os
S = "C:/Users/admin/AppData/Local/Temp/claude/C--Users-admin-Documents-edu-EduSphere-Claude-From-Scratch-Final-v3-edusphere/b4f1e8ac-3275-4b68-a887-47684942dc8d/scratchpad/"
OUT = "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/smm-research/research-sources.csv"
F = json.load(open(S + "adlib/final.json", encoding="utf-8"))
rows = []
for term, m in F["meta"].items():
    rows.append(["meta_ad_library_search", f"Ad Library keyword search: {term} (IN, active)", m["url"], m["observed"], "Primary observed",
                 f"Meta-reported results: ~{m['results']}; ads captured: {m['captured']}", "03, 02, 06, 07"])
web = [
 ("web_offer_terms", "Brookstone Institute of Global Studies (BIGS) homepage", "https://www.brookstone.ae/", "Primary (provider)", "100% Placement Support; KHDA; not degree-awarding; AED 85,200; no terms page", "06"),
 ("web_offer_terms", "GBS Dubai homepage", "https://gbs.ac.ae/", "Primary (provider)", "Employability support; KHDA-permitted; no guarantee/refund on page", "06"),
 ("web_offer_terms", "University of Law Employment Promise", "https://www.law.ac.uk/employability/employment-promise/", "Primary (provider)", "100% fees back = 50% cash + 50% credit; 9 months", "06"),
 ("web_offer_terms", "Kraftshala homepage (placement pledge)", "https://www.kraftshala.com/", "Primary (provider)", "60% refund if minimum CTC not met", "06"),
 ("web_secondary", "Shiksha BIGS fees page", "https://www.shiksha.com/studyabroad/uae/universities/brookstone-institute-of-global-studies-bigs/fees", "Secondary (aggregator)", "Fee figures (not fetched in full)", "06"),
 ("web_secondary", "helpstudyabroad BIGS article", "https://helpstudyabroad.com/study-abroad/brookstone-institute-dubai-fees-courses/", "Secondary (consultant)", "'Assured placements' AED 52k-65k claim (search snippet)", "06"),
 ("regulation", "ASCI Guidelines for Educational Institutions", "https://www.ascionline.in/wp-content/uploads/2023/05/ASCI-GUIDELINES-FOR-EDUCATIONAL-INSTITUTIONS-PROGRAMMES-AND-PLATFORMS.pdf", "Primary (regulator, via search summary)", "Job-guarantee substantiation, disclaimer, no 100% abstract claims", "06, 10"),
 ("regulation", "CCPA coaching-sector misleading-ad guidelines (news)", "https://www.exchange4media.com/advertising-news/govt-issues-guidelines-to-crack-down-on-misleading-ads-by-coaching-centres-138682.html", "Secondary (news)", "Nov 2024 guidelines summary", "06"),
 ("platform_policy", "Meta Marketing API: Special Ad Categories", "https://developers.facebook.com/documentation/ads-commerce/marketing-api/audiences/special-ad-category", "Primary (platform)", "Housing/employment/financial/political categories", "06, 08"),
 ("market_data", "MEA Indian students abroad annexure", "https://www.mea.gov.in/Images/CPV/557-en-01-04-12-2025.pdf", "Primary (government; UAE row not seen)", "~2.53 lakh Indian students in UAE (via press)", "08"),
 ("market_data", "Gulf News: Indian students 43% of Dubai intake", "https://gulfnews.com/uae/indian-students-top-dubais-global-intake-at-43-pakistanis-at-6-1.500190286", "Secondary (news citing KHDA)", "43% Indian share 2024-25", "08"),
 ("market_data", "education-uae: Dubai HE growth 2025", "https://www.education-uae.com/dubai-higher-education-growth-2025/", "Secondary", "41 providers / 37 branch campuses", "08"),
 ("market_data", "credila UAE visa guide", "https://www.credila.com/study-abroad/visa-guide-uae", "Secondary (lender blog)", "Part-time work permit mention (unverified)", "08"),
 ("market_data", "AECC: study in Dubai while working", "https://aeccglobal.in/blog/how-can-i-study-in-dubai-while-working", "Secondary (competitor blog)", "15 h/week claim (unverified, conflicting)", "08"),
]
for k, t, u, cls, note, used in web:
    rows.append([k, t, u, "2026-10-27", cls, note, used])
repo = ["apify/awesome-skills", "tenfoldmarc/ad-spy-skill", "realbrianhanson/fb-ad-intel", "kelpi-ai/meta-ads-skills", "mardab96/meta-ads-skills",
        "Hiberius/competitor-ad-intelligence", "sergebulaev/facebook-skills", "vnklab/claude-smm-skills"]
for r in repo:
    rows.append(["github_repo", r, f"https://github.com/{r}", "2026-10-27", "Primary (repo, read-only)", "See 01 appendix", "01"])
for c in F["comps"][:50]:
    rows.append(["competitor_ad_library", c["advertiser"], c["meta_ad_library_link"], "2026-10-27", "Primary observed", f"{c['ads_captured_uae_relevant']} UAE-edu ads captured", "02"])
org = S + "organic/organic-findings.json"
if os.path.exists(org):
    try:
        O = json.load(open(org, encoding="utf-8"))
        seen = set()
        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if isinstance(v, str) and v.startswith("http") and v not in seen and ("instagram.com" in v or "facebook.com" in v):
                        seen.add(v); rows.append(["organic_profile", k, v, "2026-10-27", "Observed (logged-out)", "", "04, 05"])
                    else: walk(v)
            elif isinstance(o, list):
                for v in o: walk(v)
        walk(O)
    except Exception as e: print("organic parse", e)
with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f); w.writerow(["source_type", "title", "url", "accessed", "evidence_class", "what_it_supports", "used_in"]); w.writerows(rows)
print(len(rows))
