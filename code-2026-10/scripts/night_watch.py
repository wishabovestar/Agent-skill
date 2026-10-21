# -*- coding: utf-8 -*-
"""夜间论文追踪 v2（生产版 · cron no_agent）
抓 arXiv /new 列表（绕开 429 的 API）→ 去重 → 双线打分 → 落盘 + 推送摘要。

改动（相对 _batch9/night_watch.py）：
1. 增量去重改用自有 `night_seen.json`（不写采集器的 tmp/seen.json，避免互相污染）
2. 推送只保留「新投稿」且 B 线 >= PUSH_MIN 的条目（replacement/cross-list 只计数）
3. 任一类别抓取失败 -> 记为 fail 并在推送里自曝；全失败 -> exit 3（禁止假 PASS）
4. 输出改为微信友好短摘要（<= 1200 字符）
"""
import io
import os
import re
import json
import time
import subprocess
import datetime

OUT = "D:/hermes/data/agent_knowledge/algorithm"
SEEN = OUT + "/night_seen.json"
TAG = datetime.datetime.now().strftime("%Y-%m-%d")
PUSH_MIN = 15
CATS = ["cs.AI", "cs.LG", "cs.CL", "cs.MA", "cond-mat.mtrl-sci", "cond-mat.soft",
        "physics.app-ph", "eess.SY", "cs.CE"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "Chrome/124.0 Safari/537.36")

A_POS = {5: ["electrode drying", "calendering", "slot die", "slot-die", "binder migration", "lithium-ion"],
         3: ["electrode", "slurry", "cathode", "anode", "porosity", "tortuosity", "coating", "drying",
             "battery", "nmc", "ncm", "graphite", "silicon anode", "solid electrolyte"],
         1: ["lithium", "cell", "adhesion", "cracking", "microstructure"]}
A_NEG = {6: ["eeg", "ecg", "brain-computer", "wearable", "skin electrode", "fuel cell", "proton exchange",
             "water electroly", "perovskite solar", "supercapacitor", "sodium-ion"]}
A_CORE = ["electrode drying", "calendering", "slot die", "slot-die", "binder migration",
          "electrode manufacturing", "slurry", "roll-to-roll", "battery electrode", "electrode coating",
          "drying", "li-ion", "lithium-ion", "battery cell"]
B_POS = {5: ["kv cache", "speculative decoding", "prefix caching", "paged attention", "token pruning",
             "context compression", "inference latency", "serving system", "quantization"],
         3: ["llm inference", "efficient attention", "sparse attention", "distillation", "pruning",
             "memory footprint", "tokens/s", "long context", "agent memory", "gpu memory"],
         1: ["large language model", "llm", "transformer", "efficiency", "benchmark"]}
B_NEG = {6: ["medical image", "eeg", "speech recognition", "recommendation system", "autonomous driving"]}


def fetch(cat):
    url = "https://arxiv.org/list/%s/new?skip=0&show=1000" % cat
    for attempt in range(3):
        p = subprocess.run(["curl", "-s", "--ssl-no-revoke", "-m", "60", "-A", UA, url],
                           capture_output=True)
        h = p.stdout.decode("utf-8", "ignore")
        if len(h) > 20000:
            return h
        time.sleep(5 + 5 * attempt)
    return ""


def parse(h):
    out = []
    blocks = []
    for seg in h.split("<h3>")[1:]:
        sec = re.sub(r"<[^>]+>", "", seg.split("</h3>")[0])
        sec = re.sub(r"\s+", " ", sec).split("(")[0].strip()
        for blk in seg.split("<dt>")[1:]:
            blocks.append((sec, blk))
    for sec, blk in blocks:
        m = re.search(r'id="(\d{4}\.\d{4,5})"', blk)
        if not m:
            continue
        t = re.search(r"list-title mathjax'><span class='descriptor'>Title:</span>(.*?)</div>", blk, re.S)
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t.group(1))).strip() if t else ""
        a = re.search(r"<p class='mathjax'>(.*?)</p>", blk, re.S)
        ab = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", a.group(1))).strip() if a else ""
        if title:
            out.append({"id": m.group(1), "title": title, "summary": ab, "sec": sec})
    return out


def hits(text, table):
    t = text.lower()
    got, s = [], 0
    for w, kws in table.items():
        for k in kws:
            if k in t:
                got.append(k)
                s += w
    return s, got


def score(x, pos, neg):
    st, ht = hits(x["title"], pos)
    sa, ha = hits(x["summary"], pos)
    sn, hn = hits(x["title"] + " " + x["summary"], neg)
    return st * 2 + sa - sn * 2, sorted(set(ht + ha))


def load_seen():
    try:
        d = json.load(io.open(SEEN, encoding="utf-8"))
        return set(d.get("ids", []))
    except Exception:
        return set()


def save_seen(ids):
    io.open(SEEN, "w", encoding="utf-8", newline="\n").write(
        json.dumps({"updated": TAG, "ids": sorted(ids)}, ensure_ascii=False))


def main():
    seen = load_seen()
    per, allit, fails = {}, {}, []
    for c in CATS:
        h = fetch(c)
        items = parse(h)
        per[c] = len(items)
        if not items:
            fails.append(c)
        for x in items:
            if x["id"] not in allit:
                allit[x["id"]] = dict(x, cats=[c])
            else:
                allit[x["id"]]["cats"].append(c)
        time.sleep(2)

    if len(fails) == len(CATS):
        print("[FAIL] 全部 %d 个类别均未取到列表（网络/结构变更），本次不出报告" % len(CATS))
        return 3

    rows = []
    for x in allit.values():
        a, ag = score(x, A_POS, A_NEG)
        if not any(c in (x["title"] + " " + x["summary"]).lower() for c in A_CORE):
            a = 0
        b, bg = score(x, B_POS, B_NEG)
        rows.append(dict(x, A=a, A_kw=ag, B=b, B_kw=bg, new=x["id"] not in seen))

    new = [r for r in rows if r["new"]]
    by = {}
    for r in new:
        by.setdefault(r["sec"], []).append(r)
    nn = len(by.get("New submissions", []))
    nr = len(by.get("Replacement submissions", []))
    ncross = len(by.get("Cross submissions", []))
    pushB = sorted([r for r in new if r["sec"] == "New submissions" and r["B"] >= PUSH_MIN],
                   key=lambda r: -r["B"])[:6]
    pushA = sorted([r for r in new if r["A"] > 0], key=lambda r: -r["A"])[:3]
    repB = sorted([r for r in new if r["sec"] == "Replacement submissions" and r["B"] >= 20],
                  key=lambda r: -r["B"])[:3]

    L = ["🛰 夜巡 %s · %d 类 %d 条 → 未见 %d" % (TAG, len(CATS), len(rows), len(new)),
         "新投稿 %d · 改版 %d · cross %d · A线 %d" % (nn, nr, ncross, len([r for r in new if r["A"] > 0]))]
    if fails:
        L.append("⚠️ 失败源: " + ", ".join(fails))
    if pushA:
        L.append("")
        L.append("🔴 A 线（极片工艺）:")
        for r in pushA:
            L.append("· %d %s `%s`" % (r["A"], r["title"][:58], r["id"]))
    else:
        L.append("🔴 A 线: 0 命中")
    if pushB:
        L.append("")
        L.append("🟡 新投稿 B≥%d:" % PUSH_MIN)
        for r in pushB:
            L.append("· %d %s `%s`" % (r["B"], r["title"][:56], r["id"]))
    if repB:
        L.append("")
        L.append("🔁 改版重点: " + " · ".join("`%s`(%d)" % (r["id"], r["B"]) for r in repB))
    msg = "\n".join(L)

    p_md = OUT + "/night_watch_%s.md" % TAG
    p_js = OUT + "/night_watch_%s.json" % TAG
    io.open(p_md, "w", encoding="utf-8", newline="\n").write(msg + "\n")
    io.open(p_js, "w", encoding="utf-8", newline="\n").write(json.dumps(
        {"date": TAG, "per_cat": per, "fails": fails, "seen": len(seen),
         "rows": rows}, ensure_ascii=False, indent=1))
    save_seen(seen | {r["id"] for r in rows})
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
