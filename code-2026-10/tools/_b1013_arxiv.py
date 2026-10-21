# -*- coding: utf-8 -*-
"""Daily brief A: arXiv (AI/DL + battery) — direct + proxy fallback."""
import urllib.request, urllib.parse, ssl, json, time, re, os

ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122 Safari/537.36"
PROXY = os.environ.get("ALL_PROXY") or "socks5h://127.0.0.1:10808"
OUT = {}

def open_url(url, headers=None, timeout=35, use_proxy=False):
    h = {"User-Agent": UA}
    if headers: h.update(headers)
    req = urllib.request.Request(url, headers=h)
    if use_proxy:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
    else:
        op = urllib.request.build_opener()
    return op.open(req, timeout=timeout)

def arxiv(query, maxr=22, sort="submittedDate", use_proxy=False):
    q = urllib.parse.quote(query)
    url = f"https://export.arxiv.org/api/query?search_query={q}&start=0&max_results={maxr}&sortBy={sort}&sortOrder=descending"
    for att in range(3):
        try:
            r = open_url(url, timeout=35, use_proxy=use_proxy)
            xml = r.read().decode("utf-8", "ignore")
            entries = re.findall(r"<entry>(.*?)</entry>", xml, re.S)
            out = []
            for e in entries:
                def g(tag):
                    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", e, re.S)
                    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
                authors = re.findall(r"<name>(.*?)</name>", e, re.S)
                out.append({"title": g("title"), "summary": g("summary")[:420],
                            "published": g("published"), "authors": authors[:4], "link": g("id")})
            return out
        except Exception as ex:
            if att == 2: return [{"ERR": f"{type(ex).__name__}:{str(ex)[:80]}"}]
            time.sleep(3)

ARXIV_QUERIES = {
    "ai_dl_nn": 'cat:cs.LG OR cat:cs.AI OR cat:cs.CL OR cat:cs.CV',
    "transformer": 'all:"transformer" OR all:"attention mechanism"',
    "diffusion": 'all:"diffusion model"',
    "gnn": 'all:"graph neural network"',
    "rl": 'all:"reinforcement learning"',
    "multimodal": 'all:"multimodal" OR all:"vision language model"',
    "agent_llm": 'all:"LLM agent" OR all:"language model agent"',
    "battery_li": 'all:"lithium-ion battery" OR all:"lithium battery"',
    "solid_state": 'all:"solid-state battery" OR all:"solid electrolyte"',
    "silicon_anode": 'all:"silicon anode"',
    "li_s_air": 'all:"lithium-sulfur" OR all:"lithium air battery"',
    "prelithiation": 'all:"prelithiation" OR all:"pre-lithiation"',
}
OUT["arxiv"] = {}
for k, q in ARXIV_QUERIES.items():
    res = arxiv(q, maxr=20, use_proxy=False)
    if res and "ERR" in res[0]:
        res2 = arxiv(q, maxr=20, use_proxy=True)
        OUT["arxiv"][k] = {"via": "proxy" if "ERR" not in res2[0] else "fail", "items": res2}
    else:
        OUT["arxiv"][k] = {"via": "direct", "items": res}
    print(f"arxiv {k}: {len(OUT['arxiv'][k]['items'])} via {OUT['arxiv'][k]['via']}")

with open("D:/hermes/analysis/_b1013_arxiv.json", "w", encoding="utf-8") as f:
    json.dump(OUT, f, ensure_ascii=False, indent=1)
print("SAVED _b1013_arxiv.json")
