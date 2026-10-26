import json, re, datetime, collections, sys, statistics
sys.stdout.reconfigure(encoding="utf-8")
D = json.load(open("raw2.json", encoding="utf-8")); ads = D["ads"]; meta = D["meta"]
OBS = "2026-10-27"

def txt(s):
    if isinstance(s, dict): return s.get("text") or ""
    return s or ""

def date(e): return datetime.datetime.utcfromtimestamp(e).date().isoformat() if e else ""

UAE = re.compile(r"dubai|\buae\b|emirates|abu dhabi|sharjah|ras al|ajman|knowledge park|academic city", re.I)
EDU = re.compile(r"stud(y|ies|ent)|universit|degree|\bmba\b|\bbba\b|course|admission|college|campus|scholarship|diploma|bachelor|master|\bug\b|\bpg\b|intake|programme|program|foundation|institute|school|academy|education", re.I)
HOOKS = [
 ("Job guarantee", r"(job|placement|employment)[^.\n]{0,20}guarant|guarant[^.\n]{0,25}(job|placement|employment|internship)|100% (job|placement)|placement assurance|assured (job|placement)|job.?assur"),
 ("Refund promise", r"refund|money.?back|fee.?back|cash.?back"),
 ("Employment assistance", r"placement|career support|job (assistance|support|search)|internship|employab|career services|work permit|part.?time (job|work)|post.?study work|earn while|golden visa|job.?ready|hiring partner"),
 ("Scholarships", r"scholarship|bursar|\bgrants?\b|waiver|% off"),
 ("Affordable education", r"afford|low cost|lowest|budget|cheap|₹\s?\d|\binr\b|\brs\.?\s?\d|lakh|aed\s?[\d,]+|fees? (starting|from)|half the (price|cost)"),
 ("Dubai lifestyle", r"lifestyle|skyline|burj|tax.?free|safe city|multicultural|vibrant|sunshine|beach|student life|campus life|explore dubai"),
 ("International career", r"global career|international career|career abroad|work abroad|global exposure|international exposure|global opportunit|career in (the )?(uae|dubai|gulf)|global citizen"),
 ("University reputation", r"\branked|ranking|accredit|recogni[sz]ed|khda|\bcaa\b|teqsa|\bqs\b|world.?class|top university|russell group|branch campus|uk degree|british degree|australian degree"),
 ("Student success", r"success stor|alumni|placed at|testimonial|our students|students placed|\d+[,\d]*\+ (students|success)"),
 ("Parent trust", r"parent|your child|guardian|\bsafe\b|safety"),
 ("Limited-time admissions", r"limited seats|last date|deadline|closing|hurry|apply before|admissions? (open|closing)|seats left|last chance|\d{4} intake"),
 ("Free counselling", r"free (counsel|consult|session|webinar|seminar|profile|assessment|registration)|book (a|your) (free )?(call|session|counsel)|expert guidance|talk to (an |our )?(expert|counsel)"),
]
HOOKS = [(n, re.compile(p, re.I)) for n, p in HOOKS]
COURSE = [("MBA", r"\bmba\b|management program|global management"), ("BBA/Business UG", r"\bbba\b|bachelor of business|business management"),
 ("Masters (general)", r"\bmasters?\b|\bmsc\b|\bpg\b|postgrad"), ("Bachelors (general)", r"bachelor|\bug\b|undergrad|\bbsc\b"),
 ("Foundation year", r"foundation"), ("Diploma/Certificate", r"diploma|certificat"),
 ("Culinary/Hospitality", r"culinar|chef|hospitality|hotel management"), ("Data/AI/IT", r"data science|\bai\b|artificial intel|computer science|cyber|software"),
 ("Engineering", r"engineering|b\.?tech"), ("Law", r"\bllm\b|\blaw\b|legal"), ("Healthcare/Nursing/Medicine", r"nurs|mbbs|medic|pharm|\bdha\b|health"),
 ("Accounting/Finance", r"\bacca\b|\bcma\b|accounting|finance|\bcfa\b"), ("Aviation", r"aviation|cabin crew|pilot")]
COURSE = [(n, re.compile(p, re.I)) for n, p in COURSE]
FEE = re.compile(r"(₹\s?[\d,.]+\s?(lakhs?|lacs?|l|k|cr)?\b|\b(rs\.?|inr)\s?[\d,.]+\s?(lakhs?|lacs?|l|k)?\b|\b[\d,.]+\s?(lakhs?|lacs?)\b|\baed\s?[\d,]+(\s?k)?\b|\b[\d,]+\s?aed\b|\$\s?[\d,]+|\busd\s?[\d,]+|£\s?[\d,]+)", re.I)
TESTI = re.compile(r"alumni|alumnus|testimonial|success stor|hear from|my journey|\bi (studied|joined|chose|got)\b|placed at|now works at", re.I)

rows = []
for i, o in ads.items():
    s = o["snapshot"]; body = txt(s.get("body")); title = s.get("title") or ""; desc = s.get("link_description") or ""
    link = s.get("link_url") or ""; cards = s.get("cards") or []
    if cards and not body.strip(): body = txt(cards[0].get("body"))
    if cards and not title: title = cards[0].get("title") or ""
    if cards and not link: link = cards[0].get("link_url") or ""
    cardtext = " ".join(txt(c.get("body")) + " " + (c.get("title") or "") + " " + (c.get("link_description") or "") for c in cards)
    full = " ".join([body, title, desc, cardtext])
    uae = bool(UAE.search(full + " " + link)); edu = bool(EDU.search(full))
    hooks = [n for n, p in HOOKS if p.search(full)]
    jg = bool(HOOKS[0][1].search(full)); rf = bool(HOOKS[1][1].search(full))
    if uae and edu: rel = "A: Dubai/UAE education"
    elif (jg or rf) and edu: rel = "B: guarantee/refund benchmark (non-UAE education)"
    elif uae: rel = "C: Dubai/UAE non-education (jobs/visa/other)"
    else: rel = "D: off-topic keyword match"
    fmt = s.get("display_format") or ""
    land = link
    if re.match(r"https?://fb\.me/?$", link or ""): land = "fb.me (Meta-hosted form/redirect; final destination not exposed)"
    if "wa.me" in (link or "") or s.get("cta_type") == "WHATSAPP_MESSAGE": land = (link or "") + " [WhatsApp click-to-chat]"
    def around(p, a=60, b=80):
        m = p.search(full)
        return full[max(0, m.start() - a):m.end() + b].replace("\n", " ").strip() if m else ""
    m = re.search(r"[^.\n]{0,40}scholarship[^.\n]{0,60}", full, re.I)
    plats = o.get("publisher_platform") or []
    sd = date(o.get("start_date"))
    rows.append({
     "relevance_tier": rel, "advertiser": o.get("page_name") or s.get("page_name"), "page_id": o.get("page_id"),
     "ad_library_id": i, "platforms": "|".join(plats), "on_facebook": "FACEBOOK" in plats, "on_instagram": "INSTAGRAM" in plats,
     "advertised_offer": "; ".join(h for h in hooks if h in ("Job guarantee", "Refund promise", "Scholarships", "Free counselling", "Employment assistance")),
     "primary_text": body.strip()[:1500], "headline": title.strip(), "link_description": desc.strip()[:300],
     "cta_text": s.get("cta_text") or "", "cta_type": s.get("cta_type") or "", "format": fmt, "cards_count": len(cards),
     "creative_description": f"{fmt.lower() or 'unknown'} ad; {len(cards)} cards; {len(s.get('videos') or [])} video(s); {len(s.get('images') or [])} image(s)",
     "first_seen": sd, "active_at_obs": o.get("is_active"),
     "days_running_at_obs": (datetime.date.fromisoformat(OBS) - datetime.date.fromisoformat(sd)).days if sd else "",
     "observation_date": OBS, "collation_count": o.get("collation_count"), "landing_destination": land,
     "advertised_course": "; ".join(n for n, p in COURSE if p.search(full)),
     "fees_mentioned": "; ".join(sorted({m2.group(0).strip() for m2 in FEE.finditer(full)}))[:200],
     "job_guarantee_mentioned": jg, "job_guarantee_excerpt": around(HOOKS[0][1])[:300],
     "refund_mentioned": rf, "refund_excerpt": around(HOOKS[1][1])[:300],
     "scholarship_claim": (m.group(0).strip() if m else "")[:200], "testimonial_usage": bool(TESTI.search(full)),
     "hook_primary": hooks[0] if hooks else "Unclassified", "hooks_all": "; ".join(hooks),
     "page_like_count_at_obs": s.get("page_like_count"), "page_url": s.get("page_profile_uri") or "",
     "search_terms_matched": "; ".join(o["_terms"]),
     "spend_reach_targeting": "not disclosed (non-political ad, India)",
     "evidence_confidence": "High: Meta Ad Library JSON observed directly" if body.strip() else "Medium: no primary text in Library JSON (image/video-only or DCO)",
     "source_url": f"https://www.facebook.com/ads/library/?id={i}"})
rows.sort(key=lambda r: (r["relevance_tier"], (r["advertiser"] or "").lower(), r["first_seen"]))
json.dump({"rows": rows, "meta": meta}, open("rows.json", "w", encoding="utf-8"), ensure_ascii=False)
print(collections.Counter(r["relevance_tier"] for r in rows))
A = [r for r in rows if r["relevance_tier"].startswith("A")]
print("A advertisers", len({r["advertiser"] for r in A}))
print("primary", collections.Counter(r["hook_primary"] for r in A).most_common())
print("hooks_all", collections.Counter(h for r in A for h in r["hooks_all"].split("; ") if h).most_common())
print("fmt", collections.Counter(r["format"] for r in A))
print("cta", collections.Counter(r["cta_type"] for r in A).most_common())
print("plat", collections.Counter(r["platforms"] for r in A).most_common())
print("jg", sum(r["job_guarantee_mentioned"] for r in A), "rf", sum(r["refund_mentioned"] for r in A), "testi", sum(r["testimonial_usage"] for r in A), "fees", sum(bool(r["fees_mentioned"]) for r in A))
print("courses", collections.Counter(c for r in A for c in r["advertised_course"].split("; ") if c).most_common())
print("collation>1", sum(1 for r in A if (r["collation_count"] or 0) > 1))
d = [r["days_running_at_obs"] for r in A if r["days_running_at_obs"] != ""]
print("days median", statistics.median(d), "90+", sum(1 for x in d if x >= 90), "n", len(d))
print("land", collections.Counter(("fb.me" if r["landing_destination"].startswith("fb.me") else "whatsapp" if "WhatsApp" in r["landing_destination"] else "none" if not r["landing_destination"] else "web") for r in A))
print("medium conf", sum(1 for r in A if r["evidence_confidence"].startswith("Medium")))
