# -*- coding: utf-8 -*-
"""① 看改动后 sleep json 的 integrity 字段；② 负向对照：拿【瘦身前】快照当基线，
应当报出丢段（证明检测器还能响，不是被永久静音）。"""
import json
import subprocess
import sys

sys.path.insert(0, r"D:/hermes/hermes-data/profiles/mybot/scripts")
import sleep_consolidation_v2 as S

L = []
d = json.load(open(r"D:/hermes/hermes-data/profiles/mybot/cron/output/sleep_consolidation_20261019.json",
                   encoding="utf-8"))
L.append("integrity = " + json.dumps(d["stage1_integrity"], ensure_ascii=False))
L.append("status = " + d["status"])
L.append("findings = " + json.dumps(d["findings"], ensure_ascii=False))

cur = S.MEMORY_MD.read_text(encoding="utf-8", errors="replace")
cs = set(S.parse_sections(cur).keys())

out = subprocess.run(["git", "-C", str(S.GIT_REPO), "log", "--format=%H %ad", "--date=short",
                      "--", "MEMORY.md"], capture_output=True, text=True).stdout
rows = [ln.split() for ln in out.splitlines() if ln.strip()]
L.append("")
L.append(f"=== 负向对照：快照共 {len(rows)} 个，抽最老/最近几个当基线 ===")
picks = rows[-3:] + rows[:2]
for h, date in picks:
    t = subprocess.run(["git", "-C", str(S.GIT_REPO), "show", f"{h}:MEMORY.md"],
                       capture_output=True).stdout.decode("utf-8", "replace")
    lost = sorted(set(S.parse_sections(t).keys()) - cs)
    L.append(f"  {date} {h[:8]}: 该快照独有段 {len(lost)} -> {lost[:4]}")

open(r"D:/hermes/analysis/_sleep_verify.txt", "w", encoding="utf-8").write("\n".join(L))
print("ok", len(rows))
