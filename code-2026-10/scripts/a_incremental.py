# -*- coding: utf-8 -*-
"""A 线（极片热工艺）增量检索 · OpenAlex 每日增量
- arXiv 侧 A 线实测 0 覆盖（98 条工艺相关类别 0 命中），故 A 线走期刊侧
- 用 from_publication_date 滚动窗口 + 自有 seen 集，只出「没见过的新条目」
- 期刊入库有滞后，窗口默认 14 天（--days 可调）
"""
import io
import os
import re
import json
import time
import argparse
import datetime
import subprocess
from urllib.parse import quote

OUT = "D:/hermes/data/agent_knowledge/algorithm"
SEEN = OUT + "/a_seen_openalex.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "Chrome/124.0 Safari/537.36")
SEL = ("id,doi,title,publication_date,primary_location,cited_by_count,"
       "open_access,best_oa_location,abstract_inverted_index,type")

QUERIES = [
    ("electrode drying lithium-ion battery", "电极干燥"),
    ("binder migration drying electrode", "黏结剂迁移"),
    ("slot die coating battery electrode", "狭缝涂布"),
    ("calendering lithium-ion electrode", "辊压"),
    ("electrode microstructure drying simulation", "干燥微观结构"),
    ("drying induced cracking battery electrode", "干燥开裂"),
    ("lithium-ion electrode manufacturing drying oven", "干燥炉工艺"),
    ("tortuosity electrode calendering porosity", "孔隙/迂曲度"),
]
POS = {5: ["electrode drying", "calendering", "slot die", "slot-die", "binder migration"],
       3: ["electrode", "slurry", "coating", "drying", "porosity", "tortuosity", "microstructure",
           "lithium-ion", "li-ion"],
       1: ["battery", "nmc", "ncm", "graphite", "anode", "cathode", "adhesion", "cracking"]}
NEG = ["solid oxide", "perovskite solar", "fuel cell", "supercapacitor", "sodium-ion",
       "eeg", "ecg", "wearable", "skin electrode", "water electroly"]


def get(url, attempts=4):
    wait = 3
    for k in range(attempts):
        r = subprocess.run(["curl", "-s", "-m", "45", "--ssl-no-revoke", "-A", UA, url],
                           capture_output=True)
        try:
            d = json.loads(r.stdout.decode("utf-8", "replace"))
            if "results" in d:
                return d
        except Exception:
            pass
        time.sleep(wait)
        wait *= 2
    return {"results": [], "meta": {"count": 0}}


def abstract(inv):
    if not inv:
        return ""
    pos = {}
    for w, ps in inv.items():
        for p in ps:
            pos[p] = w
    return " ".join(pos[i] for i in sorted(pos))


def sc(title, ab):
    t = (title + " " + ab).lower()
    s = 0
    for w, kws in POS.items():
        for k in kws:
            if k in t:
                s += w
    for k in NEG:
        if k in t:
            s -= 6
    return s


def load_seen():
    try:
        return set(json.load(io.open(SEEN, encoding="utf-8")).get("ids", []))
    except Exception:
        return set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    since = (datetime.date.today() - datetime.timedelta(days=a.days)).isoformat()
    seen = load_seen()
    got, fails = {}, []
    for q, label in QUERIES:
        url = ("https://api.openalex.org/works?search=%s"
               "&filter=from_publication_date:%s,has_abstract:true"
               "&sort=publication_date:desc&per-page=50&select=%s"
               % (quote(q), since, SEL))
        d = get(url)
        n = 0
        for w in d.get("results", []):
            wid = (w.get("id") or "").rsplit("/", 1)[-1]
            if not wid:
                continue
            n += 1
            if wid in got:
                got[wid]["tags"].append(label)
                continue
            loc = (w.get("primary_location") or {}).get("source") or {}
            got[wid] = {"id": wid, "doi": w.get("doi") or "", "title": w.get("title") or "",
                        "date": w.get("publication_date") or "", "venue": loc.get("display_name") or "",
                        "cited": w.get("cited_by_count") or 0,
                        "oa": bool((w.get("open_access") or {}).get("is_oa")),
                        "abs": abstract(w.get("abstract_inverted_index")), "tags": [label]}
        if not n:
            fails.append(label)
        time.sleep(1)

    for x in got.values():
        x["score"] = sc(x["title"], x["abs"])
    fresh = [x for x in got.values() if x["id"] not in seen]
    good = sorted([x for x in fresh if x["score"] >= 4], key=lambda x: (-x["score"], -x["cited"]))

    L = ["🧪 A 线增量 %s（近 %d 天入库）" % (datetime.date.today().isoformat(), a.days),
         "8 式取回 %d 条 · 未见过 %d 条 · 过阈 %d 条" % (len(got), len(fresh), len(good))]
    if fails:
        L.append("⚠️ 空返回源: " + ", ".join(fails))
    for x in good[:8]:
        L.append("· %d %s" % (x["score"], x["title"][:62]))
        L.append("   %s %s %s" % (x["date"], (x["venue"] or "-")[:26],
                                  ("OA" if x["oa"] else "closed")))
    if not good:
        L.append("（本窗口无过阈新条目）")
    msg = "\n".join(L)

    io.open(OUT + "/a_incremental_%s.md" % datetime.date.today().isoformat(),
            "w", encoding="utf-8", newline="\n").write(msg + "\n")
    io.open(OUT + "/a_incremental_%s.json" % datetime.date.today().isoformat(),
            "w", encoding="utf-8", newline="\n").write(json.dumps(
                {"date": datetime.date.today().isoformat(), "since": since,
                 "fetched": len(got), "fresh": len(fresh),
                 "items": sorted(fresh, key=lambda x: -x["score"])}, ensure_ascii=False, indent=1))
    io.open(SEEN, "w", encoding="utf-8", newline="\n").write(json.dumps(
        {"updated": datetime.date.today().isoformat(), "ids": sorted(seen | set(got))},
        ensure_ascii=False))
    if not a.quiet:
        print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
