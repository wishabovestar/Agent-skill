#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cron_replay.py — 用 cron 历史做【离线反事实评估】(Dream-RSI 借鉴落地)

★ 借鉴点(r1184): Dream-RSI「accumulated discovery history serves as a replay
  simulator over the realized search space」—— 一次昂贵的在线运行, 换数千次
  【零执行成本】的 off-policy 评估。

本机对应物: data/cron_ledger.jsonl(5,519 条 / 98 job / 61 天)
  已存字段: job_id, job_name, schedule.expr(计划时刻), started_at(实际启动),
            status, error, no_agent, pinned_model

★★ 关键方法学: 不做"重跑实验", 而是用【历史中天然存在的变异】做准实验 ——
   同一个 job 的 started_at 会有波动 ⇒ 落在不同的"并发环境"里
   ⇒ 可比同一 job 在高并发 vs 低并发下的成功率。

输出:
  ① 每条运行的"同刻并发数"(由其他 job 的 started_at 落在 ±60s 内计数)
  ② ★ 并发档 × status 的交叉表(检验"撞车导致失败"是否成立)
  ③ 对每个 job: 它在高低并发下的成功率差(只报样本足够的)
  ④ ★ 反事实: 把某 job 从当前分钟挪到目标分钟 ⇒ 该分钟并发如何变化

诚实边界: 观测性数据 ⇒ 相关非因果; 且需警惕"并发数"本身可能是别的因素的代理。
"""
import collections
import datetime as dt
import io
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
LEDGER = r"D:\hermes\hermes-data\profiles\qqbot3\data\cron_ledger.jsonl"
WIN = 60.0   # 并发窗口(秒): 两条运行相距 <= 60s 视为同刻


def parse_ts(s):
    """★ 统一为 naive 本地时间 —— 账本里混有带/不带时区的时间戳,
    直接比较会抛 'can't compare offset-naive and offset-aware datetimes'。"""
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(s)
    except Exception:
        return None
    if d.tzinfo is not None:
        d = d.astimezone().replace(tzinfo=None)
    return d


rows = []
with io.open(LEDGER, encoding="utf-8", errors="replace") as f:
    for ln in f:
        ln = ln.strip()
        if not ln:
            continue
        try:
            d = json.loads(ln)
        except Exception:
            continue
        st = parse_ts(d.get("started_at"))
        if st is None:
            continue
        d["_t"] = st
        d["_sched"] = (d.get("schedule") or {}).get("expr", "") or ""
        rows.append(d)

# ★★★ r1187 修正(重大): cron_ledger 里混着【两个来源】的记录 ——
#   source="artifact" (2,927 条) = 从 cron/output 产物文件【回填】的, status 恒为 "artifact",
#                                  ★ 它不是运行结果, 是【来源标记】; 且其 started_at 部分来自
#                                  os.path.getmtime(fp) (cron_ledger.py:171) ⇒ 有毒日期代理
#   <无 source>      (2,592 条) = 真实【执行记录】(executions 表 + 补跑)
#   ⇒ ★ 把两者混在一起算"失败率"会【系统性低估】(artifact 全被当成非失败的分母)。
EXEC = [r for r in rows if "source" not in r]
ARTF = [r for r in rows if r.get("source") == "artifact"]
print("\n  ★★★ 样本分层(修正): 全部 %d = 真实执行 %d + 产物回填 %d"
      % (len(rows), len(EXEC), len(ARTF)))
print("     ⇒ ★ 后续统计【只用真实执行记录】(%d 条)" % len(EXEC))
rows = EXEC

rows.sort(key=lambda r: r["_t"])
print("=" * 88)
print("  cron 历史重放分析  运行条目 %d  时间跨度 %s → %s"
      % (len(rows), rows[0]["_t"].date(), rows[-1]["_t"].date()))
print("=" * 88)

# ── ① 同刻并发数 ─────────────────────────────────────────────
print("\n  ① 计算每条运行的【同刻并发数】(窗口 ±%ds, 按不同 job 计)" % WIN)
ts = [r["_t"] for r in rows]
N = len(rows)
conc = [0] * N
for i in range(N):
    lo = ts[i] - dt.timedelta(seconds=WIN)
    hi = ts[i] + dt.timedelta(seconds=WIN)
    js = set()
    # 线性扫描足够(5.5k 条)
    j = i
    while j >= 0 and ts[j] >= lo:
        if j != i:
            js.add(rows[j].get("job_id"))
        j -= 1
    j = i + 1
    while j < N and ts[j] <= hi:
        js.add(rows[j].get("job_id"))
        j += 1
    conc[i] = len(js)
for i, r in enumerate(rows):
    r["_conc"] = conc[i]
c_dist = collections.Counter(conc)
print("     并发分布: %s" % dict(sorted(c_dist.items())[:10]))

# ── ② 并发档 × status ───────────────────────────────────────
print("\n  ② ★ 并发档 × status 交叉表(检验'撞车导致失败')")


def bucket(c):
    return "0 (独占)" if c == 0 else ("1" if c == 1 else ("2-3" if c <= 3 else "4+"))


tab = collections.defaultdict(collections.Counter)
for r in rows:
    tab[bucket(r["_conc"])][r.get("status", "?")] += 1

STAT = ["completed", "artifact", "failed", "unknown", "running"]
print("     %-10s %8s %8s %8s %8s | %9s" % ("并发档", "completed", "artifact", "failed", "unknown", "失败率"))
for b in ["0 (独占)", "1", "2-3", "4+"]:
    c = tab.get(b)
    if not c:
        continue
    tot = sum(c.values())
    fail = c.get("failed", 0) + c.get("unknown", 0)
    print("     %-10s %8d %8d %8d %8d | %8.2f%%  (n=%d)"
          % (b, c.get("completed", 0), c.get("artifact", 0), c.get("failed", 0),
             c.get("unknown", 0), 100.0 * fail / tot if tot else 0, tot))

# ── ③ 每个 job 在高/低并发下的成功率(只报样本足) ──────────
print("\n  ③ ★ 同一 job 在【高并发 vs 低并发】下的失败率(样本 >= 12 的 job)")
print("     (这是准实验: 利用 started_at 的自然波动)")

by_job = collections.defaultdict(list)
for r in rows:
    by_job[r.get("job_id")].append(r)


def bad(r):
    return r.get("status") in ("failed", "unknown")


res = []
for jid, rs in by_job.items():
    if len(rs) < 12:
        continue
    lo = [r for r in rs if r["_conc"] <= 1]
    hi = [r for r in rs if r["_conc"] >= 2]
    if len(lo) < 5 or len(hi) < 5:
        continue
    flo = sum(bad(r) for r in lo) / len(lo)
    fhi = sum(bad(r) for r in hi) / len(hi)
    res.append((rs[0].get("job_name", jid)[:34], jid, len(lo), flo, len(hi), fhi, fhi - flo))

res.sort(key=lambda x: -abs(x[6]))
if not res:
    print("     (无满足样本要求的 job)")
for nm, jid, nlo, flo, nhi, fhi, d in res[:12]:
    flag = "★" if abs(d) > 0.15 else " "
    print("     %s %-34s lo(n=%2d)=%5.1f%%  hi(n=%2d)=%5.1f%%  Δ=%+6.1f%%"
          % (flag, nm, nlo, 100 * flo, nhi, 100 * fhi, 100 * d))

# ── ④ 反事实: 挪动某 job 的分钟 ─────────────────────────────
print("\n  ④ ★ 反事实: 计划时刻的占用(判断挪动后会不会变挤)")
print("     ★ 修正: 早先版本用 r'^(\\d+)\\s+(\\d+)\\s' 解析, 会把 '*/30 3 * * *'")
print("       的 30 当成【分钟】⇒ 产出非法的 '30:03'。此版显式区分定点/步长/区间。")

sched_map = collections.defaultdict(set)   # (hour,minute) -> {job_id}
name_of = {}
unparsed = []


def parse_cron_min_hour(expr):
    """返回 [(hour, minute)]; 可解析的【定点】时刻。步长/区间/通配 ⇒ None"""
    f = (expr or "").split()
    if len(f) < 2:
        return None
    mi, hr = f[0], f[1]
    if not mi.isdigit() or not hr.isdigit():
        return None          # */N, N-M, * 等都归为"非定点"
    m, h = int(mi), int(hr)
    if not (0 <= m <= 59 and 0 <= h <= 23):
        return None
    return [(h, m)]


for r in rows:
    got = parse_cron_min_hour(r["_sched"])
    if not got:
        if r["_sched"] and r["_sched"] not in [u[0] for u in unparsed[:40]]:
            unparsed.append((r["_sched"], r.get("job_name", "")[:30]))
        continue
    for (h, m) in got:
        sched_map[(m, h)].add(r.get("job_id"))
    name_of[r.get("job_id")] = r.get("job_name", "")

print("     计划时刻占用 Top10(按 job 数, 仅定点时刻):")
for (mi, hr), js in sorted(sched_map.items(), key=lambda kv: -len(kv[1]))[:10]:
    print("        %02d:%02d  %d 个 job" % (hr, mi, len(js)))
print("\n     ★ 单 job 独占的分钟数: %d / %d" % (sum(1 for v in sched_map.values() if len(v) == 1), len(sched_map)))
print("     ★ 有 >=2 job 的分钟数: %d" % sum(1 for v in sched_map.values() if len(v) >= 2))
if unparsed:
    print("     ★ 非定点表达式(未参与): %d 种, 例: %s"
          % (len(unparsed), ", ".join(u[0] for u in unparsed[:6])))

# ── ⑤ ★ 可执行建议(把相关性转成行动) ──────────────────────
print("\n  ⑤ ★ 可执行建议: 由 ③ 的效应量排序(Δ > +1.0% 且样本 >= 20)")
print("     ⇒ 建议【错峰】这些 job(它们是高并发受害最明显的)")

recs = [r for r in res if r[6] > 0.010 and (r[2] + r[4]) >= 20]
for nm, jid, nlo, flo, nhi, fhi, d in recs[:8]:
    print("       %-34s %s  高并发失败率 %.1f%% vs 低并发 %.1f%%  (Δ=%+.1f%%)"
          % (nm, jid, 100 * fhi, 100 * flo, 100 * d))
if not recs:
    print("       (无)")

print("\n  ★★ 诚实边界")
print("     · 观测性数据 ⇒ 相关非因果; '并发'可能是别的因素(如系统负载、时段)的代理")
print("     · 未控制【时段】(深夜 vs 白天)与【宿主负载】⇒ 需再做分层或配对")
print("     · failed+unknown 合并计为'坏', unknown 语义未核")
print("     · 窗口 ±60s 是人为选择, 未做敏感性分析")
