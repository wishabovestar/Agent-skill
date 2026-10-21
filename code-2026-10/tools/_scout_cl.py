import ssl, urllib.request, json, re

ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, text/html"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", errors="ignore")

DOCKET = "73602437"
out = {}
try:
    d = json.loads(get(f"https://www.courtlistener.com/api/rest/v4/docket-entries/?docket={DOCKET}&order_by=-entry_number&page_size=15"))
    out["api"] = [{"n": e.get("entry_number"), "date": e.get("date_filed"),
                   "desc": (e.get("description") or "")[:120]} for e in d.get("results", [])]
    print("API OK, results:", len(out["api"]))
except Exception as e:
    print("API ERR:", str(e)[:120])
    out["api_err"] = str(e)[:200]

try:
    html = get(f"https://www.courtlistener.com/docket/{DOCKET}/apple-inc-v-liu/")
    open(r"D:/hermes/data/intel/logs/_cl_docket_20260918.html", "w", encoding="utf-8").write(html)
    print("HTML len:", len(html))
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = re.sub(r"\s+", " ", txt)
    m = re.findall(r"(\d{3})\s+([A-Z][a-z]{2} \d{1,2}, \d{4})\s+([A-Z][^|]{5,120})", txt)
    out["head"] = m[:25]
    print("parsed rows:", len(m))
except Exception as e:
    print("HTML ERR:", str(e)[:120])

json.dump(out, open(r"D:/hermes/data/intel/logs/_cl_20260918.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
