import subprocess, json, time
repos = ["OrchestratorInc/agent-orchestrator","codewhale-hq/Codewhale","superplanehq/superplane",
         "facebookresearch/swe-sweep","lostparakeetmagnify/Adobe-Illustrator","leter/zh-tech-writing",
         "Jakeschincariol/arena-skill"]
for r in repos:
    p = subprocess.run(["curl","-s","-k","--max-time","15",f"https://api.github.com/repos/{r}"],
                       capture_output=True, text=True, timeout=25)
    try:
        d = json.loads(p.stdout)
        print(f"{r} | ★{d.get('stargazers_count')} | fork{d.get('forks_count')} | open_issues{d.get('open_issues_count')} | "
              f"created {str(d.get('created_at'))[:10]} | pushed {str(d.get('pushed_at'))[:10]} | "
              f"size {d.get('size')}KB | topics {len(d.get('topics') or [])} | home {bool(d.get('homepage'))} | "
              f"archived {d.get('archived')} | license {(d.get('license') or {}).get('spdx_id')}")
    except Exception as e:
        print(r, "ERR", p.stdout[:100])
    time.sleep(1)
