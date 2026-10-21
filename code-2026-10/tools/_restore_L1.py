#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""恢复 MEMORY.md 的 L1 段（合并式，非覆盖）。

来源：L1 内容取【最新已知良好版】—— 即本会话系统提示里注入的那份（2026-10-12 22:38 快照），
      它比备份 .bak_before_dfact_20261012（10-12 02:31）更新：
        · 归档计数写「计数现算勿手维护」（备份写死 188篇/铁律142/1587KB）
        · 模型清单 8 个 + mistral:7b（备份写 7 个）

合并策略：
  · 在 L0 段之后插入 ## L1 段
  · 删掉当前文件里那条被截短的独立「本机模型…」行（L1 里有更全的版本）
  · 其余全部保留（含 ⭐⭐ 多用户隔离、§ 深读规范）

用法：python _restore_L1.py            # 试算（不写盘）
      python _restore_L1.py --apply   # 备份后写入
"""
import io
import os
import shutil
import sys
import datetime

P = r'D:/hermes/hermes-data/profiles/mybot/memories/MEMORY.md'

L1 = """## L1 · 事实条（权威件位置见 harness/README.md）
⭐ 工具栈在 D:/hermes/analysis/harness/{tools,docs,state,sandbox}；体检 = harness/tools/baseline.py --check。
⛔ 钉在 analysis 根（skill 引用）：rsi_gate.py · PAPER_ARCHIVE_agent_memory_swarm_2026-10.md（计数现算）· AGENT_MEMORY_COORD_DESIGN_CHECKLIST_v1.md · THEMATIC_BRIEF_8papers.md
11 器（exit=0）：rsi_gate · cluster_audit · persist_audit · memory_layer · meta_recursion · write_gate · repro_audit · repro_probe · verify_layer_v2 · check_local_models · baseline。
Gateway：单 host 服务全部 profile；重启=Hermes_Gateway_76bff4d2.vbs。PYTHONUTF8=1。
VPS 203.0.113.10:2222 仅密钥；GFW 旁路=vps_ssh.py；xray socks5 127.0.0.1:10808。
HF 被墙⇒hf-mirror。微信限流⇒错峰 06:15-30 摘要化。图纸隐私 AES-256-GCM，外发前过 drawing_privacy_enforcer.py。提权 IsInRole(Admin)=True。"""
# 注：L1 里【不含】本机模型行 —— 现有文件里那条精简版保留，避免重复占预算。


def build(cur: str, l1: str):
    lines = cur.splitlines()
    out, inserted, dropped = [], False, None
    for ln in lines:
        # L0 段结束于第一个单独的 §  → 在其后插入 L1
        if not inserted and ln.strip() == "§":
            out.append(ln)
            out.append(l1)
            inserted = True
            continue
        # L1 里不含本机模型行 ⇒ 现有的精简版保留（不再删）
        out.append(ln)
    # 若没插进去（没找到 §），退化为在 L2 标题前插
    if not inserted:
        out2 = []
        for ln in out:
            if ln.startswith("## L2"):
                out2.append(l1)
                inserted = True
            out2.append(ln)
        out = out2
    return "\n".join(out) + "\n", inserted, dropped


def main():
    apply = "--apply" in sys.argv
    cur = io.open(P, encoding="utf-8").read()
    new, ok, dropped = build(cur, L1)

    LIMIT = 2200
    print(f"  当前  : {len(cur)} 字符")
    print(f"  L1 段 : {len(L1)} 字符")
    print(f"  合并后: {len(new)} 字符  ({100.0*len(new)/LIMIT:.1f}% of {LIMIT})")
    print(f"  插入 L1: {'✓' if ok else '✗ 未找到插入点'}")
    print(f"  删除冗余行: {('「' + dropped[:40] + '…」') if dropped else '（无）'}")
    print(f"  段清单: ", end="")
    for ln in new.splitlines():
        if ln.startswith("## "):
            print(f"[{ln[3:].split('（')[0]}]", end=" ")
    print()

    if not ok:
        print("  ✗ 插入点未找到，中止")
        return 1
    if not apply:
        print("\n  （试算，未写盘。加 --apply 生效）")
        print("\n--- 合并后前 12 行预览 ---")
        for ln in new.splitlines()[:12]:
            print("   " + ln[:100])
        return 0

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{P}.bak_before_L1restore_{ts}"
    shutil.copy2(P, bak)
    io.open(P, "w", encoding="utf-8", newline="\n").write(new)
    chk = io.open(P, encoding="utf-8").read()
    print(f"\n  ✅ 已写入。备份: {bak}")
    print(f"  验证: {len(chk)} 字符 · 含 L1 段: {'✓' if '## L1 · 事实条' in chk else '✗'} · "
          f"含多用户隔离: {'✓' if '多用户隔离' in chk else '✗'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
