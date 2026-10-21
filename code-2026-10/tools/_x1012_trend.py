# -*- coding: utf-8 -*-
import ssl, urllib.request, subprocess, sys, os, json
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
OUT = r"D:/hermes/data/agent_knowledge/算法/tmp/trending_raw_1012.txt"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

def local(period):
    for _ in range(2):
        try:
            req = urllib.request.Request("https://github.com/trending?since=" + period,
                headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
            with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            err = f"{type(e).__name__}:{str(e)[:60]}"
    return None

chunks = {}
need_vps = []
for p in ("daily", "weekly", "monthly"):
    h = local(p)
    if h and h.count('<article class="Box-row">') >= 3:
        chunks[p] = h
        print("LOCAL_OK", p, len(h), h.count('<article class="Box-row">'))
    else:
        need_vps.append(p)
        print("LOCAL_FAIL", p)

if need_vps:
    # VPS relay for all needed periods in one command
    qs = " ".join(need_vps)
    cmd = ("for p in %s; do echo \"===XX:$p===XX\"; "
           "curl -s -A '%s' --max-time 40 \"https://github.com/trending?since=$p\"; echo; done" % (qs, UA))
    r = subprocess.run([sys.executable, r"D:/hermes/analysis/vps_ssh.py", "exec", cmd],
                       capture_output=True, text=True, timeout=200)
    out = r.stdout
    print("VPS_RC:", r.returncode, "bytes:", len(out))
    import re
    parts = re.split(r"===XX:(\w+)===XX", out)
    for i in range(1, len(parts), 2):
        chunks[parts[i]] = parts[i+1]
        print("VPS_GOT", parts[i], len(parts[i+1]), parts[i+1].count('<article class="Box-row">'))

# write combined with markers
buf = []
for p in ("daily", "weekly", "monthly"):
    buf.append("===XX:%s===XX" % p)
    buf.append(chunks.get(p, ""))
open(OUT, "w", encoding="utf-8").write("\n".join(buf))
print("WROTE", OUT, os.path.getsize(OUT), "periods:", list(chunks.keys()))
