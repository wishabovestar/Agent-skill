import subprocess, urllib.parse, io, re, json, sys

CATS = ["cs.AI","cs.CL","cs.LG","cs.CR","cs.RO","cs.MA","cs.SE","cs.GT","cs.HC","cs.IR","cs.NI","math.OC","cs.DC","cs.AR","q-bio.GN"]
cat_q = "(" + " OR ".join(f"cat:{c}" for c in CATS) + ")"
q = f"{cat_q} AND (abs:agent OR abs:agentic OR abs:\"LLM agent\") AND submittedDate:[202610190000 TO 202610192359]"
url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({
    "search_query": q, "start": 0, "max_results": 400,
    "sortBy": "submittedDate", "sortOrder": "descending"})
out = "_digest_1019.xml"
cmd = ["curl","-sSL","-m","120","--ssl-no-revoke","-A",
       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
       url,"-o",out,"-w","http=%{http_code} size=%{size_download}"]
r = subprocess.run(cmd, capture_output=True, text=True, shell=False)
print(r.stdout.strip(), "| rc", r.returncode)
raw = io.open(out, encoding="utf-8", errors="ignore").read()
print("xml chars", len(raw))

NS = "{http://www.w3.org/2005/Atom}"
import xml.etree.ElementTree as ET
root = ET.fromstring(raw)
items = []
for e in root.findall(NS+"entry"):
    t = re.sub(r"\s+", " ", e.findtext(NS+"title","")).strip()
    s = re.sub(r"\s+", " ", e.findtext(NS+"summary","")).strip()
    aid = (e.findtext(NS+"id","") or "").split("/abs/")[-1]
    pub = e.findtext(NS+"published","")
    cats = [c.get("term") for c in e.findall(NS+"category")]
    prim = e.find("{http://arxiv.org/schemas/atom}primary_category")
    items.append({"id":aid,"title":t,"abs":s,"pub":pub,"cats":cats,"prim":prim.get("term") if prim is not None else ""})
print("entries", len(items))
json.dump(items, io.open("_digest_1019.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
for it in items[:5]:
    print(" -", it["id"], "|", it["prim"], "|", it["title"][:90])
