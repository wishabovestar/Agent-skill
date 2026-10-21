#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""投递失败自动重投看门狗 (防复发加固 2026-09-04; 2026-09-17 真修)

输出: 失败 job 清单 (job_id + 名称 + 时间) — 供 agent 型 cron 自动 run 补投
正常: 输出 [WATCHDOG-OK] ... 静默 (agent 型 cron 据此回 [SILENT])
用法: python cron_delivery_watchdog.py

════════════════════════════════════════════════════════════════════════
★★★ 2026-09-17 真修三个叠加缺陷 (本会话实测暴露)
────────────────────────────────────────────────────────────────────────
缺陷1 只读 agent.log 近 65 分钟, 不看 jobs.json 的持久 last_delivery_error
      ⇒ 跨天/日志轮转后的失败**永久隐身**。实测: 看门狗打印
        「[WATCHDOG-OK] 近 65 分钟无致命投递失败」, 而 jobs.json 里
        **挂着 13 个 last_delivery_error** —— 两个判据完全不衔接。
      ⇒ 修: 增加【持久字段扫描】, 它才是权威源; 日志只作佐证。
缺陷2 `JOB_NAMES[j.get("job_id", "")]` —— jobs.json 的主键实际是 `id`
      (无 `job_id` 字段) ⇒ 映射退化成 {"": 最后一个 job 名} ⇒ 报出的名字**永远是错的**。
      ⇒ 修: 兼容取 `id` / `job_id`。
缺陷3 `rate_limit` 被 `continue` **永久跳过不补投** (理由: 防反馈循环)。
      但实测 **13 个失败全部是 `rate limited`** ⇒ 这一类**永远不会被补投**。
      ⇒ 修: 改为【冷却式有限重投】: 记录补投次数, 未超上限就报, 超上限则
        明确报「已放弃」让人工介入 —— 而不是静默永跳。
════════════════════════════════════════════════════════════════════════
★★★ 2026-09-17 ③ 再修 (本会话实测暴露的**通知风暴**)
────────────────────────────────────────────────────────────────────────
缺陷4 EXHAUSTED 分支**既不写状态、也无去重** ⇒ 一旦某个 job 的失败进入
      「已放弃」态, 只要 jobs.json 里那条 last_delivery_error 还在 (周度 job
      可挂 7 天), 看门狗**每小时**都把同样的 11 条重报一次 ⇒ agent 每小时
      回一次 ~5KB 摘要 ⇒ 把本就限流的微信通道持续加压 (自伤循环)。
      实测: 2026-09-17 07:37→22:38 共 12 次重复上报同一批 job。
      ⇒ 修: (job_id, 失败批次时间) 级【一次性通知账本】—— 同一批失败只报一次;
        失败解除 (不再出现在本轮检测) 时账本自清理; 全被抑制时回归 [WATCHDOG-OK]。
        注意: 只对 EXHAUSTED 去重, to_retry 的 90 分钟冷却 + MAX_RETRIES
        重投语义**保持不变** (那才是本脚本的主职)。
════════════════════════════════════════════════════════════════════════
"""
# side_effects: [读日志/读jobs.json/写重投状态]
import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(BASE, "logs", "agent.log")
JOBS = os.path.join(BASE, "cron", "jobs.json")

# 持久字段判据: last_run_at 在这么多天内才算"最近失败" (防陈年账目刷屏)
PERSIST_DAYS = 7
# 单个 job 允许的最大重投次数 (超过则报"已放弃"交人工)
MAX_RETRIES = 3
GATEWAY_LOG = os.path.join(BASE, "logs", "gateway.log")
CHANNEL_QUIET_S = 300     # 诊断用窗口, 不作放行闸门(见 channel_recovered 的说明)
POST_EXHAUST_S = 21600    # ★ 到顶后宽限重试间隔 (6h): 独立通道可能已恢复, 不永久放弃
MAX_RELEASE_PER_RUN = 3   # ★ 每轮最多放行几项到顶积压: 既有设计已证明"一次转发十几个
                          #    几十 KB 的产物必然再次失败"(redelivery_index.py 原话),
                          #    所以放行必须限量, 宁可分多小时清完, 不可一次压垮通道。
RECOVERED_LEDGER = "_recovered_retried"
# ★ 2026-09-17③ 一次性通知账本在状态文件里的键 (防 EXHAUSTED 每小时重报)
NOTIFY_LEDGER = "_exhausted_notified"
# ★ 2026-09-19 加固: 独立进程补投脚本(redeliver_failed.py)写下的【已送达】job 标记。
#   本脚本此前从不读它 ⇒ 已补投成功的 job 因 jobs.json 的 last_delivery_error
#   永不清除, 仍被计入"积压/EXHAUSTED 需人工处置", 虚增待办。
#   实测 2026-09-19 17:37: EXHAUSTED 列 6 项, 其中 2 项(310dd85c5fca / 17af2e8c6592)
#   已在 16:47 补投成功并写入标记 ⇒ 上报的"待人工处置"有 1/3 是假的。
REDELIVERED_MARK = os.path.join(BASE, "data", "redelivered_ids.json")

# job id → 名 映射 (★ 缺陷2: 主键是 id, 不是 job_id)
JOB_NAMES = {}


def load_job_names():
    try:
        d = json.load(open(JOBS, encoding="utf-8"))
        for j in d.get("jobs", []):
            jid = j.get("id") or j.get("job_id")
            if jid:
                JOB_NAMES[jid] = j.get("name", "")
    except Exception:
        pass


def classify_error(msg):
    """rate_limit: 限流 (可恢复, 但★不再永久跳过 —— 见缺陷3)
    fatal: 真失败 (Connection/DNS/超时)
    """
    ml = (msg or "").lower()
    if "rate limited" in ml or "rate_limit" in ml or "cooldown" in ml:
        return "rate_limit"
    return "fatal"


def load_state():
    try:
        return json.load(open(os.path.join(BASE, "data", "watchdog_retry_state.json"),
                              encoding="utf-8"))
    except Exception:
        return {}


def save_state(st):
    try:
        p = os.path.join(BASE, "data", "watchdog_retry_state.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def scan_persistent(now):
    """★ 缺陷1 的修: 扫 jobs.json 的持久 last_delivery_error —— 权威源"""
    out = []
    try:
        d = json.load(open(JOBS, encoding="utf-8"))
    except Exception:
        return out
    for j in d.get("jobs", []):
        err = j.get("last_delivery_error")
        if not err:
            continue
        lr = j.get("last_run_at") or ""
        try:
            t = datetime.fromisoformat(lr)
        except Exception:
            continue
        if t.tzinfo is not None:
            t = t.replace(tzinfo=None)
        if (now - t).days > PERSIST_DAYS:
            continue
        jid = j.get("id") or j.get("job_id") or "?"
        out.append((lr[:19], jid, classify_error(err), "persist"))
    return out


def scan_log(now):
    """原判据: agent.log 近 65 分钟 (保留, 但降级为佐证)"""
    out = []
    if not os.path.exists(LOG):
        return out
    win = now - timedelta(minutes=65)
    size = os.path.getsize(LOG)
    with open(LOG, encoding="utf-8", errors="ignore") as f:
        if size > 2_000_000:
            f.seek(size - 2_000_000)
        data = f.read()
    pat = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ ERROR cron\.scheduler: "
        r"Job '([^']+)'[^:]*:.{0,120}(?:failed|delivery error|rate limited)")
    for m in pat.finditer(data):
        try:
            t = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        if t >= win:
            out.append((m.group(1), m.group(2), classify_error(m.group(0)), "log"))
    return out


def has_artifact(jid, last_run_at):
    """★ 2026-09-17 补: 该 job 在 last_run_at 附近是否**已有产物落盘**。

    用途: 区分两种截然不同的处置 ——
      · 有产物 ⇒ 任务其实**成功了**, 只是没送达 ⇒ **只需补投递**, 别重跑
      · 无产物 ⇒ 任务真的没产出 ⇒ 才需要重跑
    不做这个区分, 就会把 12 个昂贵的 agent 任务无谓重跑一遍。
    """
    od = os.path.join(BASE, "cron", "output", jid)
    if not os.path.isdir(od):
        return False
    try:
        t = datetime.fromisoformat(last_run_at)
    except Exception:
        return False
    if t.tzinfo is not None:
        t = t.replace(tzinfo=None)
    # 产物 mtime 落在 [last_run_at - 10min, last_run_at + 30min] 即视为本次产出
    lo = t.timestamp() - 600
    hi = t.timestamp() + 1800
    for f in glob.glob(os.path.join(od, "*")):
        try:
            mt = os.path.getmtime(f)
        except OSError:
            continue
        if lo <= mt <= hi:
            return True
    return False


def channel_recovered(window_s=CHANNEL_QUIET_S):
    """诊断用: gateway 发送路径最近 window_s 秒内是否仍有 iLink 限流记录。

    ★★★ 重要(2026-09-19 实测纠正, 勿把它当"通道是否可用"的闸门):
      它测的是【gateway 自身发送路径】的状态, 不等于【账号/通道】的状态。
      证据: 同一时刻 gateway.log 尾 500 行里有 315 条限流(09:51 仍在 backing off 48s),
      但【独立进程】`hermes send -t weixin` 返回 rc=0 "Sent to weixin home channel"。
      ⇒ gateway 的限流记录很大程度是【它自己的 48s 退避重试风暴】打出来的,
        不代表 iLink 对账号封了通道。
      ⇒ 因此【不要用它拦住补投】; 补投应走 `hermes send`(独立路径),
        而独立路径失败【不会加重 gateway 的限流】, 所以"直接试投 + 失败退避"才正确。
      本函数保留作诊断输出, 不参与放行决策。
    """
    try:
        with open(GATEWAY_LOG, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()[-500:]
    except Exception:
        return False
    cutoff = datetime.now() - timedelta(seconds=window_s)
    for line in reversed(lines):
        m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
        if not m:
            continue
        try:
            t = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if t < cutoff:
            return True          # 已越过窗口, 窗口内无更晚记录 ⇒ 安静
        if "rate limited" in line or "rate limit" in line:
            return False         # 窗口内仍有限流
    return True


def main():
    load_job_names()
    now = datetime.now()
    state = load_state()
    # 兼容旧格式 ( {jid: ts} ) 与 新格式 ( {jid: {"ts":, "n":}} )
    norm = {}
    for k, v in state.items():
        if isinstance(v, dict):
            norm[k] = v
        else:
            norm[k] = {"ts": float(v), "n": 0}
    state = norm

    found = scan_persistent(now) + scan_log(now)

    # 去重: 同一 job 取最先出现的一条, 但合并报错类型 (persist 优先)
    best = {}
    for ts, jid, ctype, src in found:
        cur = best.get(jid)
        if cur is None or (src == "persist" and cur[3] == "log"):
            best[jid] = (ts, jid, ctype, src)

    # ★ 2026-09-19 加固: 先扣除【已补投成功】的 job (标记见 REDELIVERED_MARK)。
    #   判据链: redeliver_failed.py 只有拿到平台 message_id / success=true 才写标记,
    #   所以标记 = 平台确认送达 ⇒ 这些 job 不该再算积压。
    done_ids, dropped = set(), []
    try:
        with open(REDELIVERED_MARK, encoding="utf-8") as f:
            done_ids = set(json.load(f).get("done", []))
    except Exception:
        pass
    for jid in list(best):
        if jid in done_ids:
            dropped.append(best.pop(jid)[1])

    to_retry, exhausted, recovered = [], [], []
    for jid, (ts, _j, ctype, src) in best.items():
        rec = state.get(jid) or {"ts": 0.0, "n": 0}
        # ★ 冷却: 90 分钟内已报过就不再报 (防反馈循环) —— 与旧版一致
        if now.timestamp() - rec.get("ts", 0) < 5400:
            continue
        # ★ 缺陷3 的修: rate_limit 不再永久跳过; 但受 MAX_RETRIES 上限约束
        # ★★ 2026-09-19 修 (间歇限流下"到顶即永久放弃"是错的):
        #    实测微信 iLink 限流是【间歇性】的, 且 gateway 的 315 条限流记录大多是
        #    【它自己 48s 退避重试风暴】打出来的, 不代表账号通道被封 ——
        #    同一时刻【独立进程】`hermes send -t weixin` 仍返回 rc=0。
        #    旧逻辑一到 n>=3 就永久 exhausted ⇒ 通道恢复了那 29 项也永不重投, 静默积压。
        #    现在: 到顶后每 POST_EXHAUST_S 宽限重试一次, 并把计数重置。
        #    (独立路径失败不会加重 gateway 限流, 所以"试投"本身是安全的。)
        if ctype == "rate_limit" and rec.get("n", 0) >= MAX_RETRIES:
            if (now.timestamp() - rec.get("ts", 0) >= POST_EXHAUST_S
                    and len(recovered) < MAX_RELEASE_PER_RUN):
                state[jid] = {"ts": rec.get("ts", 0.0), "n": 0}
                to_retry.append((ts, jid, ctype, src))
                recovered.append((ts, jid, ctype, rec.get("n", 0), src))
                continue
            exhausted.append((ts, jid, ctype, rec.get("n", 0), src))
            continue
        to_retry.append((ts, jid, ctype, src))

    if dropped:
        # 只作口径说明, 不改变上面 [WATCHDOG-OK]/[WATCHDOG-REDELIVER] 的判定关键字
        print("  ☆ 口径修正: 已扣除 %d 项【补投成功】标记, 不再计为积压 — %s"
              % (len(dropped), ", ".join(sorted(JOB_NAMES.get(d, d) for d in dropped))[:200]))
        print()

    if not to_retry and not exhausted:
        print("[WATCHDOG-OK] 无待补投的致命投递失败 "
              "(持久账本 %d 天内 + 日志近 65 分钟)" % PERSIST_DAYS)
        return

    if to_retry:
        # ★ 分成两类处置 (避免无谓重跑昂贵的 agent 任务)
        need_rerun, need_redeliver = [], []
        for ts, jid, ctype, src in sorted(to_retry):
            (need_redeliver if has_artifact(jid, ts) else need_rerun).append((ts, jid, ctype, src))

        if need_redeliver:
            print("[WATCHDOG-REDELIVER] ★ 产物已落盘, 只需【补投递】, 不要重跑任务:")
            for ts, jid, ctype, src in need_redeliver:
                print("  %s | %s | %s | %s | 来源=%s"
                      % (ts, jid, JOB_NAMES.get(jid, jid), ctype, src))
            print("  ⇒ 处理: 直接读取 cron/output/<job_id>/ 下对应产物并转发; "
                  "重跑只会重复计费。")
            print("  ⇒ 操作手册(2026-09-17 固化): ①python redelivery_index.py 取件索引 "
                  "②python redelivery_brief.py 一句话结论 ③把合并摘要作为本次回复正文发出 "
                  "(deliver=origin 自动送达), 禁 hermes cron run —— 重跑既重复计费, "
                  "又会再次撞上 iLink 限流。")
            print()
        if need_rerun:
            print("[WATCHDOG-RETRY] 检测到投递失败且【无产物】—— 需重跑:")
            for ts, jid, ctype, src in need_rerun:
                print("  %s | %s | %s | %s | 来源=%s"
                      % (ts, jid, JOB_NAMES.get(jid, jid), ctype, src))
            print("  请对上述 job 执行 cronjob action=run 补投 "
                  "(冷却 90 分钟由状态文件保证; rate_limit 类最多补投 %d 次)" % MAX_RETRIES)

        for _ts, jid, ctype, _src in to_retry:
            rec = state.get(jid) or {"ts": 0.0, "n": 0}
            state[jid] = {"ts": now.timestamp(),
                          "n": int(rec.get("n", 0)) + (1 if ctype == "rate_limit" else 0)}
        save_state(state)

    if recovered:
        print("[WATCHDOG-RECOVERED] ★ 到顶积压宽限放行(每轮最多 %d 项: 通道可能已恢复,"
              "且独立发送路径失败不会加重 gateway 限流)⇒ 重置计数并重新排入补投:"
              % MAX_RELEASE_PER_RUN)
        for ts, jid, ctype, n_was, src in sorted(recovered):
            print("  %s | %s | %s | %s | 到顶时n=%s | 来源=%s"
                  % (ts, jid, JOB_NAMES.get(jid, jid), ctype, n_was, src))
        print("  ⇒ 处理: 与 [WATCHDOG-REDELIVER] 同手册(取件索引 → 一句话结论 → 作为正文发出); "
              "禁 hermes cron run。")
        print("  ⇒ ★ 注意: 经 gateway 回复投递仍可能被 iLink 限流; "
              "确需必达时走【独立进程】hermes send(见 scripts/redeliver_failed.py)。")
        print()

    if exhausted:
        # ★ 2026-09-17③ 缺陷4 的修: (job_id, 失败批次) 级一次性通知账本
        #   同一批失败只通知一次 —— 防"每小时重报 11 条 ⇒ 每小时推 5KB ⇒ 持续压限流通道"
        led = state.get(NOTIFY_LEDGER)
        if not isinstance(led, dict):
            led = {}
        alive = set(jid for _ts, jid, _c, _n, _s in exhausted)
        for k in [k for k in led if k not in alive]:
            led.pop(k, None)          # 失败已解除/超窗 ⇒ 账本自清理
        fresh = [e for e in sorted(exhausted) if led.get(e[1]) != e[0]]
        for ts, jid, _c, _n, _s in fresh:
            led[jid] = ts
        state[NOTIFY_LEDGER] = led
        save_state(state)

        if fresh:
            print()
            print("[WATCHDOG-EXHAUSTED] 以下 job 的限流型失败已补投 %d 次仍未成功, 不再自动重试:"
                  % MAX_RETRIES)
            for ts, jid, ctype, n, src in fresh:
                print("  %s | %s | %s | 已试 %d 次 | 来源=%s"
                      % (ts, jid, JOB_NAMES.get(jid, jid), n, src))
            print("⇒ 需人工处置: 检查微信 iLink 限流/通道状态, 或确认产物本身是否已落盘可直接取用。")
            print("★ 已记入一次性通知账本: 同一批失败不再重复上报。")
        else:
            print("[WATCHDOG-OK] 无待补投的致命投递失败 "
                  "(持久账本 %d 天内 + 日志近 65 分钟); 另 %d 条已放弃项已通知过, "
                  "去重抑制, 本轮无需处置。" % (PERSIST_DAYS, len(exhausted)))


if __name__ == "__main__":
    main()
