import ssl, urllib.request, json, time
ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
HDR={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122 Safari/537.36","Accept":"application/json"}
CANDS=["google/ax","agent-substrate/substrate","anthropics/financial-services","anthropics/knowledge-work-plugins",
"dream-num/univer","davila7/claude-code-templates","superdesigndev/treg","browser-use/video-use","stablyai/orca",
"addyosmani/agent-skills","affaan-m/ECC","Tencent/WeKnora","TencentCloud/Octop","alibaba/open-code-review",
"EKKOLearnAI/ekko-studio","jev-chat/jev-chat-jarvis","maanHimself/OpenDLSS-NR","software-mansion/runntime",
"JustVugg/colibri","sergebulaev/linkedin-skills","anthropics/claude-code","danny-avila/LibreChat","mvt-project/mvt",
"kyky2347/ALTA"]
out={}
for fn in CANDS:
    try:
        req=urllib.request.Request(f"https://api.github.com/repos/{fn}",headers=HDR)
        with urllib.request.urlopen(req,timeout=20,context=ctx) as r:
            d=json.loads(r.read().decode("utf-8","ignore"))
        out[fn]={"stars":d.get("stargazers_count",0),"forks":d.get("forks_count",0),
          "language":d.get("language") or "N/A","desc":(d.get("description") or "")[:280],
          "topics":(d.get("topics") or [])[:14],"created":(d.get("created_at") or "")[:10],
          "pushed":(d.get("pushed_at") or "")[:10],"license":((d.get("license") or {}).get("spdx_id") or "NONE"),
          "open_issues":d.get("open_issues_count",0),"archived":d.get("archived",False)}
        print(f"{fn}|{out[fn]['stars']}|{out[fn]['created']}|{out[fn]['pushed']}|{out[fn]['license']}")
    except Exception as e:
        print(f"{fn}|FAIL|{type(e).__name__}:{str(e)[:50]}")
        out[fn]={"error":str(e)[:80]}
    time.sleep(1.2)
json.dump(out,open("D:/hermes/analysis/_xt0923/details_0923.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
print("SAVED details n=",len(out))
