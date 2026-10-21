# -*- coding: utf-8 -*-
import json

OUT = r"D:/hermes/hermes-data/profiles/mybot/cron/output/"
L = []

s = json.load(open(OUT + "sleep_consolidation_20261019.json", encoding="utf-8"))
L.append("### SLEEP 2026-10-19")
L.append(json.dumps({k: s[k] for k in ("timestamp", "version", "status", "algorithms",
                                       "sources_found", "errors")}, ensure_ascii=False, indent=1))
L.append("-- stage1_memory:")
L.append(json.dumps(s.get("stage1_memory"), ensure_ascii=False)[:600])
L.append("-- stage1_integrity:")
L.append(json.dumps(s.get("stage1_integrity"), ensure_ascii=False)[:600])
L.append("-- findings:")
for f in s.get("findings", []):
    L.append("  * " + json.dumps(f, ensure_ascii=False)[:400])
L.append("-- suggestions:")
for f in s.get("suggestions", []):
    L.append("  > " + json.dumps(f, ensure_ascii=False)[:400])
L.append("-- stage2_dreaming:")
L.append(json.dumps(s.get("stage2_dreaming"), ensure_ascii=False)[:600])

d = json.load(open(OUT + "daydream_v4_20261019_0200.json", encoding="utf-8"))
L.append("")
L.append("### DREAM 2026-10-19_0200")
L.append(json.dumps({k: d[k] for k in ("version", "timestamp", "source_stats", "real_sessions",
                                       "noise_sessions", "selected", "elapsed_s", "status")},
                    ensure_ascii=False, indent=1)[:900])
L.append(f"replayed={len(d.get('replayed', []))} concepts={len(d.get('concepts', []))} "
         f"cross_ideas={len(d.get('cross_domain_ideas', []))} "
         f"attempted={d.get('cross_domain_attempted')} rejected={d.get('cross_domain_rejected')}")

# 消费侧：有没有别的东西在读这两个产物
import os
import subprocess
L.append("")
L.append("### 消费检查（谁读 sleep/daydream 产物）")
for name in ("sleep_consolidation_20261019.json", "daydream_v4_20261019_0200.json",
             "daydream_v4_20261019.md", "dreaming_20261019.md"):
    pass

open(r"D:/hermes/analysis/_dream_sleep_detail.txt", "w", encoding="utf-8").write("\n".join(L))
print("ok", len(L))
