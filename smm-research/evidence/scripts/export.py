import json, re, csv, collections, statistics, sys
sys.stdout.reconfigure(encoding="utf-8")
OUT = "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/smm-research/"
D = json.load(open("rows.json", encoding="utf-8")); R = D["rows"]; META = D["meta"]
DEST = re.compile(r"(stud(y|ying)|degree|campus|universit|\bmba\b|masters?|bachelor|programme|program|college|institute|intake|admission|scholarship|course)[^.\n|]{0,60}(dubai|\buae\b|emirates|abu dhabi|sharjah)|(dubai|\buae\b|abu dhabi|sharjah)[^.\n|]{0,40}(campus|universit|\bmba\b|degree|programme|program|college|institute|intake|admission|stud)", re.I)
# advertisers whose Dubai-campus programme is evident from their name or reviewed ad text but missed by the regex
MANUAL_DEST = {"The Confluence Global Education", "Manipal Academy of Higher Education - MAHE, Dubai", "Vibe Education Dubai",
               "The North Land Institute of Training - Canadian College in Dubai"}
SCRIPT = [("Malayalam", r"[\u0D00-\u0D7F]"), ("Hindi/Devanagari", r"[\u0900-\u097F]"), ("Tamil", r"[\u0B80-\u0BFF]"),
          ("Telugu", r"[\u0C00-\u0C7F]"), ("Gujarati", r"[\u0A80-\u0AFF]"), ("Punjabi", r"[\u0A00-\u0A7F]"), ("Kannada", r"[\u0C80-\u0CFF]")]
AUD = [("Class 12 / plus-two", r"plus.?two|\+2|class 12|12th|after 12|school leavers?|പ്ലസ് ടു"), ("Graduates", r"graduates?|bachelor'?s (holders|graduates)|after (graduation|degree)|degree holders"),
       ("Working professionals", r"working professional|work experience|experienced|mid.?career|full.?time job"), ("Parents", r"parent|your child|your ward"),
       ("MBA aspirants", r"\bmba\b"), ("Nurses/Healthcare", r"nurs|\bdha\b|pharm"), ("Students who missed admission", r"missed|gap year|year isn.?t wasted")]
TRUST = [("Accreditation/recognition", r"khda|\bcaa\b|teqsa|accredit|recogni[sz]ed|aacsb|equis|amba|city & guilds|pearson|ugc"),
         ("Branch campus of foreign university", r"branch campus|uk degree|british degree|australian degree|same degree"),
         ("Ranking", r"\branked|ranking|\bqs\b|times higher|\btop \d+"), ("Volume claims", r"\d[\d,]*\+\s*(students|success|universit|partners|experts|years)"),
         ("Years in business", r"\d+\+? years"), ("Testimonials", r"alumni|testimonial|success stor|placed at")]
def lang(t): return "; ".join(n for n, p in SCRIPT if re.search(p, t)) or "English"
NONEDU = re.compile(r"cholesterol|capsule|supplement|milk thistle|pipitea|gevilo|blood sugar|lipitor", re.I)
for r in R:
    t = r["primary_text"] + " " + r["headline"] + " " + r["link_description"]
    if NONEDU.search(t + " " + r["landing_destination"]): r["relevance_tier"] = "D: off-topic keyword match"
    r["dubai_as_destination"] = r["relevance_tier"].startswith("A") and (bool(DEST.search(t)) or r["advertiser"] in MANUAL_DEST)
    r["language_script"] = lang(t)

# ---------- 03 ad-level CSV (relevant tiers only) ----------
cols = ["ad_library_id", "advertiser", "relevance_tier", "dubai_as_destination", "platforms", "on_facebook", "on_instagram", "advertised_offer",
        "primary_text", "headline", "link_description", "cta_text", "cta_type", "format", "cards_count", "creative_description", "first_seen",
        "days_running_at_obs", "observation_date", "active_at_obs", "collation_count", "landing_destination", "advertised_course", "fees_mentioned",
        "job_guarantee_mentioned", "job_guarantee_excerpt", "refund_mentioned", "refund_excerpt", "scholarship_claim", "testimonial_usage",
        "hook_primary", "hooks_all", "language_script", "page_id", "page_url", "page_like_count_at_obs", "search_terms_matched",
        "spend_reach_targeting", "evidence_confidence", "source_url"]
rel = [r for r in R if not r["relevance_tier"].startswith("D")]
with open(OUT + "03-facebook-ad-library-analysis.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rel)

# ---------- 02 competitor CSV ----------
A = [r for r in R if r["relevance_tier"].startswith("A")]
by = collections.defaultdict(list)
for r in A: by[r["advertiser"]].append(r)
comps = []
for adv, v in by.items():
    dest = [r for r in v if r["dubai_as_destination"]]
    if not dest: continue
    txt = " ".join(r["primary_text"] + " " + r["headline"] for r in v)
    days = [r["days_running_at_obs"] for r in v if r["days_running_at_obs"] != ""]
    multi = sum(1 for r in v if (r["collation_count"] or 0) > 1)
    hooks = collections.Counter(h for r in v for h in r["hooks_all"].split("; ") if h)
    kind = "University / institution" if re.search(r"universit|campus|institute|school of|college|iiccm|icca|tiib|bits|hult|business school|academy of higher", adv, re.I) and not re.search(r"consult|overseas|abroad", adv, re.I) else "Consultant / aggregator"
    score = len(dest) * 2 + min(len(v), 40) + multi + sum(1 for d in days if d >= 90) * 2
    likes = max((r["page_like_count_at_obs"] or 0) for r in v)
    comps.append({
        "advertiser": adv, "advertiser_type_inferred": kind, "facebook_page_url": v[0]["page_url"], "instagram_profile_url": "see 04-instagram-competitor-analysis.md",
        "meta_ad_library_link": f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=IN&view_all_page_id={v[0]['page_id']}",
        "geographic_market_verifiable": "Ads served in India (Ad Library country filter = IN); targeting detail not disclosed",
        "language_of_ads": "; ".join(sorted({r["language_script"] for r in v})),
        "programmes_advertised": "; ".join(c for c, _ in collections.Counter(c for r in v for c in r["advertised_course"].split("; ") if c).most_common(5)),
        "offers_promoted": "; ".join(f"{h} ({n})" for h, n in hooks.most_common() if h in ("Scholarships", "Job guarantee", "Refund promise", "Employment assistance", "Free counselling", "Affordable education")),
        "ads_captured_uae_relevant": len(v), "ads_dubai_as_destination": len(dest), "ads_multi_version": multi,
        "earliest_first_seen": min(r["first_seen"] for r in v if r["first_seen"]) if days else "", "max_days_running": max(days) if days else "",
        "ads_running_90plus_days": sum(1 for d in days if d >= 90),
        "formats": "; ".join(f"{k} ({n})" for k, n in collections.Counter(r["format"] for r in v).most_common()),
        "platforms_seen": "; ".join(sorted({p for r in v for p in r["platforms"].split("|") if p})),
        "ctas": "; ".join(f"{k} ({n})" for k, n in collections.Counter(r["cta_type"] for r in v if r["cta_type"]).most_common(4)),
        "landing_types": "; ".join(f"{k} ({n})" for k, n in collections.Counter(("Meta form/redirect" if r["landing_destination"].startswith("fb.me") else "WhatsApp" if "WhatsApp" in r["landing_destination"] else "none" if not r["landing_destination"] else "website") for r in v).most_common()),
        "audience_signals_from_creative": "; ".join(n for n, p in AUD if re.search(p, txt, re.I)) or "none explicit",
        "trust_signals": "; ".join(n for n, p in TRUST if re.search(p, txt, re.I)) or "none explicit",
        "job_guarantee_claim_seen": any(r["job_guarantee_mentioned"] for r in v), "refund_claim_seen": any(r["refund_mentioned"] for r in v),
        "page_likes_at_obs": likes or "", "relevance_activity_score": score,
        "score_method": "2*dest_ads + min(ads,40) + multi_version_ads + 2*ads_90plus_days (observable activity only; not spend)",
        "observation_date": "2026-10-27"})
comps.sort(key=lambda c: -c["relevance_activity_score"])
for i, c in enumerate(comps, 1): c["rank"] = i
top = comps[:50]
with open(OUT + "02-meta-competitors.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["rank"] + [k for k in top[0] if k != "rank"]); w.writeheader(); w.writerows(top)
json.dump({"comps": comps, "rows": R, "meta": META}, open("final.json", "w", encoding="utf-8"), ensure_ascii=False)
print("03 rows", len(rel), "competitors", len(comps), "top50 written")
for c in top[:25]: print(c["rank"], c["advertiser"], c["advertiser_type_inferred"], c["ads_captured_uae_relevant"], c["ads_dubai_as_destination"], c["max_days_running"], c["page_likes_at_obs"], c["language_of_ads"])
print("lang A", collections.Counter(r["language_script"] for r in A).most_common())
D2 = [r for r in A if r["dubai_as_destination"]]
print("dest n", len(D2))
print("dest hooks", collections.Counter(h for r in D2 for h in r["hooks_all"].split("; ") if h).most_common())
print("dest fmt", collections.Counter(r["format"] for r in D2).most_common(), "cta", collections.Counter(r["cta_type"] for r in D2).most_common(6))
print("dest IG-only", sum(1 for r in D2 if r["platforms"].startswith("INSTAGRAM")), "on IG", sum(r["on_instagram"] for r in D2), "on FB", sum(r["on_facebook"] for r in D2))
print("dest land", collections.Counter(("form" if r["landing_destination"].startswith("fb.me") else "wa" if "WhatsApp" in r["landing_destination"] else "none" if not r["landing_destination"] else "web") for r in D2))
print("dest fees", sum(bool(r["fees_mentioned"]) for r in D2), "testi", sum(r["testimonial_usage"] for r in D2), "jg", sum(r["job_guarantee_mentioned"] for r in D2), "rf", sum(r["refund_mentioned"] for r in D2))
dd = [r["days_running_at_obs"] for r in D2 if r["days_running_at_obs"] != ""]
print("dest days median", statistics.median(dd), "90+", sum(1 for x in dd if x >= 90), "multi", sum(1 for r in D2 if (r["collation_count"] or 0) > 1))
print("courses dest", collections.Counter(c for r in D2 for c in r["advertised_course"].split("; ") if c).most_common())
print("kinds", collections.Counter(c["advertiser_type_inferred"] for c in comps))
