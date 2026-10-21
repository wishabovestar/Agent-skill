# -*- coding: utf-8 -*-
import subprocess, sys, os, re, json, time
sys.path.insert(0, r"D:/hermes/analysis")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
OUT = r"D:/hermes/data/agent_knowledge/算法/tmp/trending_vps_1011.txt"

cmd = ("for p in daily weekly monthly; do echo \"===XX:$p===XX\"; "
       "curl -s -A '%s' --max-time 40 \"https://github.com/trending?since=$p\"; echo; done" % UA)

r = subprocess.run([sys.executable, r"D:/hermes/analysis/vps_ssh.py", "exec", cmd],
                   capture_output=True, text=True, timeout=180)
out = r.stdout
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w", encoding="utf-8").write(out)
print("VPS_RC:", r.returncode, "bytes:", len(out))
if r.stderr.strip():
    print("ERR:", r.stderr.strip()[:200])
# split
parts = re.split(r"===XX:(\w+)===XX", out)
print("sections:", len(parts))
ART = '<article class="Box-row">'
for i in range(1, len(parts), 2):
    per = parts[i]; html = parts[i+1]
    print("  %s: %d chars, articles=%d, h2=%d" % (per, len(html), html.count(ART), html.count('h3 lh-condensed')))
