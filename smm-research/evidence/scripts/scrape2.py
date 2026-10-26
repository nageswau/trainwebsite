import time, urllib.parse, json, re, datetime
from playwright.sync_api import sync_playwright
TERMS = ["Study in Dubai","Study in UAE","Study abroad Dubai","Dubai university admission",
 "Study in Dubai with job guarantee","Study in Dubai with placement","Study in Dubai 50% fee refund",
 "Study abroad with job guarantee","Study and work in Dubai","Dubai student visa",
 "Dubai MBA with placement","Dubai scholarships","Study in Dubai 2027"]
def walk(o,out):
    if isinstance(o,dict):
        if "ad_archive_id" in o and "snapshot" in o: out.append(o)
        for v in o.values(): walk(v,out)
    elif isinstance(o,list):
        for v in o: walk(v,out)
def parse_blobs(texts):
    out=[]
    for t in texts:
        t=t.replace("for (;;);","")
        for line in t.split("\n"):
            line=line.strip()
            if not line.startswith("{"): continue
            try: walk(json.loads(line),out)
            except Exception: pass
    return out
ads={}; meta={}
obs=datetime.date.today().isoformat()
with sync_playwright() as p:
    b=p.chromium.launch(headless=True)
    pg=b.new_page(viewport={"width":1280,"height":2200},locale="en-US",user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36")
    bodies=[]
    def on(r):
        if "graphql" in r.url:
            try: bodies.append(r.text())
            except: pass
    pg.on("response",on)
    for term in TERMS:
        bodies.clear()
        url="https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=IN&q="+urllib.parse.quote(term)+"&search_type=keyword_unordered&media_type=all"
        pg.goto(url,wait_until="domcontentloaded",timeout=60000); time.sleep(8)
        for _ in range(10): pg.mouse.wheel(0,5000); time.sleep(2)
        scripts=pg.eval_on_selector_all('script[type="application/json"]',"els=>els.map(e=>e.textContent)")
        body=pg.inner_text("body"); m=re.search(r"~?([\d,]+) results",body)
        found=parse_blobs(scripts+bodies)
        n=0
        for o in found:
            i=str(o["ad_archive_id"])
            if i not in ads: ads[i]=o; ads[i]["_terms"]=[]; n+=1
            if term not in ads[i]["_terms"]: ads[i]["_terms"].append(term)
        meta[term]={"url":url,"results":m.group(1) if m else None,"captured":len({str(o['ad_archive_id']) for o in found}),"observed":obs}
        print(term,meta[term]["captured"],n,meta[term]["results"],flush=True)
    b.close()
json.dump({"meta":meta,"ads":ads},open("raw2.json","w",encoding="utf-8"),ensure_ascii=False)
print("total",len(ads))
