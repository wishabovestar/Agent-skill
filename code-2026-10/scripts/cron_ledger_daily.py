#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cron_ledger_daily.py — 持久执行账本每日守护 (no_agent, 静默设计)

【设计原则: 安安静静, 出事才响】
  正常 → stdout 为空 → cron 不投递任何消息 (watchdog pattern)
  异常 → 打印告警 → 由 cron 投递给用户

【为什么需要它 (P0-1 的由来)】
  executions.db 是 1000 行环形缓冲, 实测只覆盖 ~19.6 小时。
  任何"某 job 从未跑 / 凌晨不执行"的判断超出该窗口就是假阴性
  (本机 2026-09-15/16 两次同形状误判已归档)。
  本守护把执行史固化进 append-only 账本, 从此可做跨月判断 (D6 观测基础)。

【告警判据 (仅这些会响)】
  ① 有 fire-fence 锁【被进程持有】 (可能僵死 → 真会阻塞)
  ② 断言失败: 账本 0 条 / 全部 job 都有记录 (闸门失效嫌疑)
  ③ 应跑的 job 长时间无记录: 按 schedule 推算"本应执行"但账本 ≥N 倍周期无记录
  ④ 采集本身失败 (脚本异常)
"""
# side_effects: [写 data/cron_ledger.jsonl, 写 data/cron_ledger_report.md]

import os
import subprocess
import sys
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PY = sys.executable
ALERTS = []


def run(args):
    r = subprocess.run([PY, "-X", "utf8", os.path.join(BASE, "cron_ledger.py")] + args,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main():
    rc1, out1 = run(["--backfill"])
    rc2, out2 = run(["--ingest"])
    rc3, out3 = run(["--locks"])
    rc4, out4 = run(["--report"])

    if rc1 or rc2 or rc3 or rc4:
        ALERTS.append("🔴 账本采集异常: backfill=%s ingest=%s locks=%s report=%s"
                      % (rc1, rc2, rc3, rc4))
        for nm, o in (("backfill", out1), ("ingest", out2), ("locks", out3), ("report", out4)):
            if o.strip():
                tail = [l for l in o.strip().split("\n") if l.strip()][-3:]
                ALERTS.append("  [%s] %s" % (nm, " | ".join(x.strip() for x in tail)[:220]))

    # ① 被持有的锁
    if "被持有(可能僵死): " in out3:
        try:
            seg = out3.split("被持有(可能僵死): ")[1].split("|")[0].strip()
            held = int(seg)
            if held > 0:
                ALERTS.append("🔴 fire-fence 锁被持有 %d 个 → 可能僵死阻塞" % held)
                for l in out3.split("\n"):
                    if "🔴 持有中" in l:
                        ALERTS.append("   " + l.strip())
        except Exception:
            pass

    # ② 账本断言
    try:
        import json as _j
        led = os.path.join(os.path.dirname(BASE), "data", "cron_ledger.jsonl")
        recs = []
        if os.path.exists(led):
            for ln in open(led, encoding="utf-8"):
                ln = ln.strip()
                if ln:
                    recs.append(_j.loads(ln))
        if not recs:
            ALERTS.append("🔴 账本 0 条 → 采集未生效 (断言: 不得为 0)")
        else:
            jf = os.path.join(os.path.dirname(BASE), "cron", "jobs.json")
            cfg = 0
            if os.path.exists(jf):
                with open(jf, encoding="utf-8") as fh:
                    cfg = len(_j.load(fh).get("jobs", []))
            ids = set(r.get("job_id") for r in recs)
            # ★ 新增停摆守卫 (2026-09-16): 账本真正的失效模式是【采集停摆】而非"覆盖太多"
            #   (原断言「不是全部」是从门控场景误移植 —— 对执行账本而言
            #    "所有 job 都有记录"是好事, 不是异常; 且历史已删 job 会让计数 > 配置数)
            newest = max((r.get("ingested_at") or r.get("started_at") or "" for r in recs),
                         default="")
            if newest:
                try:
                    nd = datetime.fromisoformat(newest[:19])
                    gap_h = (datetime.now() - nd).total_seconds() / 3600.0
                    # 每日采集 + 执行频繁 ⇒ 超过 48h 没有新入账 = 停摆
                    if gap_h >= 48:
                        ALERTS.append("🔴 账本采集疑似停摆: 最新入账 %.1f 小时前 (%s)"
                                      % (gap_h, newest[:16]))
                except Exception:
                    pass
            ALERTS.append("__INFO__ 账本 %d 条 / %d job (配置 %d)"
                          % (len(recs), len(ids), cfg))
            # ③ 应跑但无记录
            now = datetime.now()
            last = {}
            for r in recs:
                ts = r.get("started_at")
                if ts and (r.get("job_id") not in last or ts > last[r.get("job_id")]):
                    last[r.get("job_id")] = ts
            stale = []
            for r in recs:
                jid = r.get("job_id")
                if jid in stale:
                    continue
                sch = str(r.get("schedule") or "")
                t = last.get(jid)
                if not t:
                    continue
                try:
                    d = datetime.fromisoformat(t[:19])
                except Exception:
                    continue
                # ★ 只对【严格每日或更频繁】的 job 判停滞:
                #   5 段 cron 的 日/月/星期 三位都必须是 * ——
                #   否则周任务 (0 8 * * 1) 会被误判 (它隔 7 天才跑一次是正常的)
                parts = sch.split()
                is_daily = (len(parts) == 5 and parts[2] == "*"
                            and parts[3] == "*" and parts[4] == "*")
                if is_daily and (now - d).days >= 4:
                    stale.append((jid, r.get("job_name") or "", t[:16], (now - d).days))
            if stale:
                ALERTS.append("🟡 应每日执行但 ≥4 天无记录: %d 个" % len(stale))
                for jid, nm, t, dd in sorted(stale, key=lambda x: -x[3])[:6]:
                    ALERTS.append("   %s %s — 最近 %s (%d 天前)" % (jid, (nm or "")[:22], t, dd))
    except Exception as e:
        ALERTS.append("🔴 账本断言检查异常: %s" % str(e)[:160])

    # __INFO__ 前缀仅为日志信息, 不算告警 (不单独触发投递)
    real = [a for a in ALERTS if not a.startswith("__INFO__")]
    info = [a.replace("__INFO__ ", "") for a in ALERTS if a.startswith("__INFO__")]

    if real:
        print("📒 **cron 持久账本守护 — 发现问题**")
        print("")
        for a in real:
            print(a)
        if info:
            print("")
            for a in info:
                print("ℹ️ " + a)
        print("")
        print("报告: `%s`" % os.path.join(os.path.dirname(BASE), "data", "cron_ledger_report.md"))
    # 正常 → 静默 (stdout 为空 → cron 不投递)
    return 0


if __name__ == "__main__":
    sys.exit(main())
