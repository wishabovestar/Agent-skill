# -*- coding: utf-8 -*-
"""趋势信号：Hermes可落地方向定向 arXiv 检索"""
import ssl, urllib.request, urllib.parse, json, os, re, time

RAW = r"D:/hermes/data/agent_knowledge/algorithm/tmp"
seen = json.load(open(os.path.join(RAW, "seen.json"), encoding="utf-8"))
sp = set(seen["papers"])

def fetch(url, timeout=35):
    ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 Chrome/120","Accept":"application/atom+xml"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", errors="ignore")

TOPICS = {
    "kv_cache":      'all:"KV cache" AND all:compression',
    "spec_decoding": 'all:"speculative decoding"',
    "moe":           'all:"mixture of experts" AND all:efficient',
    "sparse_attn":   'all:"sparse attention" AND all:long-context',
    "test_time":     'all:"test-time compute" OR all:"test-time scaling"',
    "quantization":  'all:"quantization" AND all:"large language model" AND all:efficient',
    "token_compress":'all:"token compression" OR all:"context compression"',
    "agent_memory":  'all:"agent memory" OR all:"context management" agent',
}
out = {}
for k, q in TOPICS.items():
    url = ("http://export.arxiv.org/api/query?search_query=%s&sortBy=submittedDate&sortOrder=descending&max_results=6"
           % urllib.parse.quote(q, safe=''))
    try:
        xml = fetch(url)
    except Exception as e:
        out[k] = [{"err": type(e).__name__ + str(e)[:50]}]; print("ERR", k); time.sleep(3); continue
    lst = []
    for e in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
        t = re.search(r"<title>(.*?)</title>", e, re.S); i = re.search(r"<id>(.*?)</id>", e, re.S)
        p = re.search(r"<published>(.*?)</published>", e, re.S); s = re.search(r"<summary>(.*?)</summary>", e, re.S)
        if not (t and i): continue
        pid = i.group(1).strip().rstrip("/").split("/")[-1]
        lst.append({"title": re.sub(r"\s+"," ",t.group(1)).strip(), "id": i.group(1).strip(),
                    "published": p.group(1).strip()[:10] if p else "",
                    "summary": re.sub(r"\s+"," ",s.group(1)).strip()[:300] if s else "",
                    "is_new": pid not in sp})
    out[k] = lst
    time.sleep(3)
json.dump(out, open(os.path.join(RAW, "arxiv_trends.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("TRENDS_DONE", {k: (len(v) if isinstance(v, list) else 0) for k, v in out.items()})
