import sqlite3, os

db = "D:/hermes/hermes-data/state.db"
conn = sqlite3.connect(db)
cur = conn.cursor()

lines = []

# Check state_meta
cur.execute("SELECT * FROM state_meta")
lines.append("=== state_meta ===")
for r in cur.fetchall():
    lines.append(str(r))

# Check sessions for weixin
cur.execute("SELECT id, title, source, started_at, ended_at, end_reason FROM sessions WHERE source='weixin' ORDER BY started_at DESC LIMIT 5")
lines.append("\n=== Recent WeChat Sessions ===")
for r in cur.fetchall():
    lines.append(str(r))

# Check config from env files
envs = ["D:/hermes/hermes-data/.env"]
for p in [os.path.expanduser("~/.hermes"), "D:/hermes/hermes-data/profiles/default"]:
    if os.path.isdir(p):
        for f in os.listdir(p):
            envs.append(os.path.join(p, f))

for f in envs:
    if os.path.isfile(f):
        lines.append(f"\n=== {f} ===")
        with open(f) as fh:
            content = fh.read()
            for line in content.split("\n")[:30]:
                if any(k in line.lower() for k in ["weixin", "wechat", "ilink", "gateway", "wx"]):
                    lines.append(line)

# Check if hermesd is running
import subprocess
try:
    r = subprocess.run(["tasklist", "/fi", "IMAGENAME eq hermesd.exe", "/fo", "csv", "/nh"], capture_output=True, text=True, timeout=10)
    lines.append(f"\n=== hermesd process ===")
    lines.append(r.stdout)
except:
    lines.append("Could not check hermesd process")

out = "\n".join(lines)
print(out)

with open("D:/hermes/analysis/gw_check.txt", "w") as f:
    f.write(out)

conn.close()
