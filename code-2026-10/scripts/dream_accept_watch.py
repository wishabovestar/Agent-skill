# -*- coding: utf-8 -*-
"""白日梦跨域接受率 · 连续三晚观察
- 每晚 02:00 白日梦跑完，次日 09:50 读取最新 daydream_v4_*.json 记账
- 未满 3 晚：静默（stdout 为空 ⇒ cron 不推送）
- 满 3 晚：输出对照表 + 判定（是否触发 v4.3 的「放宽空谈闸」预案）
"""
import io
import os
import json
import glob
import datetime

OUT = "D:/hermes/data/agent_knowledge/algorithm"
LEDGER = OUT + "/dream_accept_ledger.json"
SRC = "D:/hermes/hermes-data/profiles/mybot/cron/output"
NEED = 3


def latest():
    fs = glob.glob(SRC + "/daydream_v4_*.json")
    return max(fs, key=os.path.getmtime) if fs else None


def load():
    try:
        return json.load(io.open(LEDGER, encoding="utf-8")).get("nights", [])
    except Exception:
        return []


def save(nights):
    io.open(LEDGER, "w", encoding="utf-8", newline="\n").write(
        json.dumps({"updated": datetime.date.today().isoformat(), "nights": nights},
                   ensure_ascii=False, indent=1))


def main():
    f = latest()
    if not f:
        return 3
    d = json.load(io.open(f, encoding="utf-8"))
    cf = d.get("cross_filter_stats") or {}
    night = {
        "date": (d.get("timestamp") or "")[:10],
        "file": os.path.basename(f),
        "version": d.get("version", "?"),
        "attempted": cf.get("attempted", d.get("cross_domain_attempted", 0)),
        "accepted": cf.get("accepted", len(d.get("cross_domain_ideas") or [])),
        "rej": {k: cf.get(k, 0) for k in
                ("same_topic", "dup_prev", "ungrounded", "vague", "llm_null")},
        "abs": d.get("abstract_src") or {},
        "status": d.get("status", "?"),
    }
    nights = [x for x in load() if x["date"] != night["date"]] + [night]
    nights.sort(key=lambda x: x["date"])
    save(nights)

    if len(nights) < NEED:
        return 0                      # 静默，等下一晚
    tail = nights[-NEED:]
    L = ["🌙 白日梦跨域接受率 · 连续 %d 晚" % NEED]
    for x in tail:
        r = x["rej"]
        L.append("· %s %s 试 %d 收 %d | 空谈%d 跨天%d 同题%d LLM判无%d | 抽象 llm%s/cache%s"
                 % (x["date"], x["version"], x["attempted"], x["accepted"],
                    r["ungrounded"], r["dup_prev"], r["same_topic"], r["llm_null"],
                    x["abs"].get("llm", "?"), x["abs"].get("cache", "?")))
    tot_a = sum(x["accepted"] for x in tail)
    tot_t = sum(x["attempted"] for x in tail)
    L.append("三晚合计 %d/%d = %.0f%%" % (tot_a, tot_t, 100.0 * tot_a / max(tot_t, 1)))
    if tot_a == 0:
        L.append("判定：仍 0 接受 ⇒ 按 v4.3 预案放宽「空谈闸」——允许「A 正文含具体对象"
                 "（文件名/命令/参数）」替代抽象原则，但「具象闸」与「跨天闸」保留。")
    elif tot_a * 3 < tot_t:
        L.append("判定：接受率 <1/3 ⇒ 保持四道闸，先看被接受样本是否可执行再决定是否放宽。")
    else:
        L.append("判定：接受率正常 ⇒ 四道闸生效，无需调整。")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
