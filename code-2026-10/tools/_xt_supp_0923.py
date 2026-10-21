import ssl, urllib.request, json, time
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
HDR={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122 Safari/537.36","Accept":"application/json"}
Q=[
 ("s_topic_agent",  "topic:agent+created:%3E2026-08-23+stars:%3E80"),
 ("s_topic_mcp",    "topic:mcp+created:%3E2026-08-10+stars:%3E80"),
 ("s_skills",       "topic:agent-skills+stars:%3E100"),
 ("s_claude_sk",    "claude+skills+created:%3E2026-08-10+stars:%3E100"),
 ("s_harness",      "agent+harness+created:%3E2026-08-10+stars:%3E80"),
 ("s_dl_new",       "deep+learning+created:%3E2026-09-01+stars:%3E30"),
 ("s_nn_new",       "neural+created:%3E2026-09-01+stars:%3E30"),
 ("s_rl_new",       "reinforcement+learning+created:%3E2026-08-20+stars:%3E50"),
 ("s_vec",          "vector+search+created:%3E2026-08-10+stars:%3E100"),
 ("s_llm_infra",    "inference+engine+created:%3E2026-08-10+stars:%3E100"),
]
out={}
for name,q in Q:
    try:
        req=urllib.request.Request(f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=15",headers=HDR)
        with urllib.request.urlopen(req,timeout=25,context=ctx) as r:
            d=json.loads(r.read().decode("utf-8","ignore"))
        items=d.get("items") or []
        out[name]=[{"full_name":i["full_name"],"stars":i["stargazers_count"],"language":i.get("language") or "N/A",
          "description":(i.get("description") or "")[:300],"topics":(i.get("topics") or [])[:12],
          "created_at":(i.get("created_at") or "")[:10],"pushed_at":(i.get("pushed_at") or "")[:10],
          "url":i.get("html_url",""),"forks":i.get("forks_count",0),"total_count":d.get("total_count",0)} for i in items]
        print(f"{name} OK n={len(items)} total={d.get('total_count',0)}")
    except Exception as e:
        print(f"{name} FAIL {type(e).__name__} {str(e)[:50]}")
        out[name]=[]
    time.sleep(7)
json.dump(out,open("D:/hermes/analysis/_xt0923/supp_0923.json","w",encoding="utf-8"),ensure_ascii=False)
print("SAVED supp total=",sum(len(v) for v in out.values()))
