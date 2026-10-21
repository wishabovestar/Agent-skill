import sys, re
sys.path.insert(0, "D:/hermes/analysis")
import vps_ssh

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
cmd = ("for p in daily weekly monthly; do echo \"===XX:$p===XX\"; "
       "curl -s -A '" + UA + "' --max-time 40 \"https://github.com/trending?since=$p\"; echo; done")
try:
    out, err = vps_ssh.run(cmd, timeout=180)
except Exception as e:
    print("VPS_FAIL", type(e).__name__, str(e)[:120]); sys.exit(1)

open("D:/hermes/analysis/trending_raw.html","w",encoding="utf-8",errors="replace").write(out)
parts = re.split(r"===XX:(\w+)===XX", out)
cards = {parts[i]: parts[i+1].count('<article class="Box-row">') for i in range(1, len(parts)-1, 2)}
print("VPS_TREND bytes=%d parts=%d" % (len(out), (len(parts)-1)//2))
print("CARDS:", cards)
