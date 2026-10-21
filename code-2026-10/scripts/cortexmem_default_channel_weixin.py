# -*- coding: utf-8 -*-
"""把 cortexmem 的【无来源】节点统一归为本 weixin 渠道。

★ 用户指令 (2026-09-19):
  「将 cortexmem 无来源的数据全都视为本 weixin 渠道来源」

★ 语义界定(重要, 勿混淆):
  这是设定【渠道归属默认值】, 【不是】按内容推断渠道。
  ⇒ 因此对每条被改写的节点打标 `channel_source = "default-weixin"`,
     与实测来源(`channel_source = "measured"`)区分开, 保持可审计。
  ⇒ 原值另存于 `channel_prev` 以便回滚。

★ 纪律:
  - 默认 dry-run; 必须显式 --apply 才写盘
  - 写盘前备份 state.json
  - 紧凑 JSON 落盘(与 r1298 口径一致)
"""
import io
import json
import os
import shutil
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROFILES = r"D:\hermes\hermes-data\profiles"
WEIXIN = "weixin"
TARGETS = ("legacy-unknown",)          # 仅这两类算"无来源"
APPLY = "--apply" in sys.argv
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

print("=" * 74)
print(" cortexmem 无来源 → weixin 渠道默认值  [%s]" % ("APPLY(写盘)" if APPLY else "DRY-RUN(仅预演)"))
print("=" * 74)

grand_changed = 0
grand_nodes = 0
report = []

for prof in sorted(os.listdir(PROFILES)):
    f = os.path.join(PROFILES, prof, "knowledge_base", "cortexmem", "state.json")
    if not os.path.isfile(f):
        continue
    try:
        d = json.load(io.open(f, encoding="utf-8"))
    except Exception as e:
        report.append("  %-8s ✗ 读取失败: %s" % (prof, str(e)[:50]))
        continue
    nodes = d.get("nodes") or {}
    if not isinstance(nodes, dict):
        report.append("  %-8s ✗ nodes 非 dict, 跳过" % prof)
        continue

    changed = 0
    for nid, nd in nodes.items():
        if not isinstance(nd, dict):
            continue
        cur = nd.get("channel")
        # ★ "无来源" = legacy-unknown / None / 空串 / 缺字段
        if cur in TARGETS or cur is None or cur == "":
            nd["channel_prev"] = cur
            nd["channel"] = WEIXIN
            nd["channel_source"] = "default-weixin"
            changed += 1
        elif "channel_source" not in nd:
            # 已有实测来源 ⇒ 补标 measured, 不动 channel 值
            nd["channel_source"] = "measured"

    grand_nodes += len(nodes)
    if changed:
        grand_changed += changed
        if APPLY:
            bak = f + ".bak_weixin_default_" + STAMP
            shutil.copy2(f, bak)
            tmp = f + ".tmp"
            io.open(tmp, "w", encoding="utf-8").write(
                json.dumps(d, ensure_ascii=False, separators=(",", ":")))
            os.replace(tmp, f)
            report.append("  %-8s %5d/%5d 改写 ✓ 备份=%s" % (
                prof, changed, len(nodes), os.path.basename(bak)))
        else:
            report.append("  %-8s %5d/%5d 将改写" % (prof, changed, len(nodes)))
    else:
        report.append("  %-8s %5d/%5d 无目标" % (prof, 0, len(nodes)))

print()
for r in report:
    print(r)
print()
print("  合计: %d 个节点中 %d 个归为本 weixin 渠道" % (grand_nodes, grand_changed))
if not APPLY:
    print("  ★ 这是预演。确认后加 --apply 执行。")
