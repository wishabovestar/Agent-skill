#!/usr/bin/env python3
"""机制① 蒸馏半部适用性量化: 本机未蒸馏原始轨迹占比 (真实数据)"""
import json, sys, re, random, collections, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

P = r"<PROFILE_ROOT>\knowledge_base\cortexmem\state.json"
n = json.load(open(P, encoding="utf-8"))["nodes"]
random.seed(7)
sample = random.sample(list(n.values()), 800)

FENCE = chr(96) * 3      # 三个反引号
NOISE = [
    (re.escape("[ASYNC DELEGATION"), "异步委派样板"),
    (re.escape("[IMPORTANT"), "系统提示样板"),
    (re.escape(FENCE), "代码块围栏"),
    (r"Traceback \(most recent", "异常栈"),
    (r'^\s*\{"', "JSON 原文"),
    (re.escape("[OUT-OF-BAND"), "OOB 样板"),
    (r"</?[a-z]+>", "HTML 标签"),
]
cnt = collections.Counter()
hit = 0
for v in sample:
    c = v.get("content", "") or ""
    m = [name for pat, name in NOISE if re.search(pat, c, re.M)]
    if m:
        cnt[m[0]] += 1
        hit += 1
print("  严格噪声判定 (样板/栈/代码围栏/JSON原文): %d / %d = %.1f%%"
      % (hit, len(sample), hit / len(sample) * 100))
for k, c in cnt.most_common():
    print("    %-16s %d" % (k, c))

full = sum(1 for v in n.values() if FENCE in (v.get("content") or ""))
print("\n  ★ 全库含代码围栏的节点: %d / %d = %.1f%%"
      % (full, len(n), full / len(n) * 100))
boiler = sum(1 for v in n.values()
             if "[ASYNC DELEGATION" in (v.get("content") or "")
             or "[IMPORTANT" in (v.get("content") or ""))
print("  ★ 全库含系统样板 (委派/OOB/IMPORTANT) 的节点: %d / %d = %.1f%%"
      % (boiler, len(n), boiler / len(n) * 100))
