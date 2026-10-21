"""冷启动假设验证：temp>0 下的离群是否只发生在模型刚加载后的第一次调用。

两阶段（同一进程内）：
  A 冷启动：先 keep_alive=0 卸载模型 → 立刻跑 N 次
  B 热启动：先跑 1 次丢弃（预热）→ 再跑 N 次
判据：A 阶段离群固定出现在 i=0、B 阶段无离群 ⇒ 冷启动/重载是诱因。
"""
from __future__ import annotations

import hashlib
import io
import json
import time
import urllib.request

URL = "http://127.0.0.1:11434/api/generate"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
PROMPT = ("You are a deterministic test harness. Reply with exactly 30 words about why fixed "
          "seeds matter for reproducible ML experiments. No preamble.")
MODEL = __import__("sys").argv[1] if len(__import__("sys").argv) > 1 else "qwen2.5:1.5b"
TAG = MODEL.replace(":", "_").replace(".", "")


def gen(temp=0.9, npred=60, seed=42, keep_alive=None):
    opt = {"num_predict": npred, "seed": seed, "temperature": temp}
    body = {"model": MODEL, "prompt": PROMPT, "stream": False, "options": opt}
    if keep_alive is not None:
        body["keep_alive"] = keep_alive
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with OPENER.open(req, timeout=300) as r:
        return json.loads(r.read().decode())


def phase(name, n=10, unload=False):
    if unload:
        gen(npred=1, keep_alive=0)  # 触发卸载
        time.sleep(2)
    rows = []
    for i in range(n):
        d = gen()
        t = d.get("response", "")
        rows.append({"i": i, "h": hashlib.sha256(t.encode()).hexdigest()[:16], "len": len(t),
                     "ec": d.get("eval_count"), "dr": d.get("done_reason"),
                     "load_ms": round((d.get("load_duration") or 0) / 1e6), "text": t})
    cw = {}
    for r in rows:
        cw[r["h"]] = cw.get(r["h"], 0) + 1
    maj = max(cw, key=cw.get)
    outliers = [r for r in rows if r["h"] != maj]
    return {"phase": name, "clusters": cw, "outliers": outliers, "rows": rows}


def main():
    out = []
    a = phase("A_cold", unload=True)
    b = phase("B_warm", unload=False)
    for p in (a, b):
        out.append(f"[{p['phase']}] 簇={p['clusters']} 离群数={len(p['outliers'])} "
                   f"离群下标={[r['i'] for r in p['outliers']]}")
        out.append(f"   load_ms 序列={[r['load_ms'] for r in p['rows']]}")
        out.append(f"   eval_count 序列={[r['ec'] for r in p['rows']]}")
        out.append(f"   done_reason 序列={[r['dr'] for r in p['rows']]}")
        for r in p["outliers"]:
            out.append(f"   离群 i={r['i']} len={r['len']} eval_count={r['ec']} "
                       f"done_reason={r['dr']} load_ms={r['load_ms']}")
    verdict = ("冷启动假设成立：A 有离群且都在 i=0，B 无离群" if
               (a["outliers"] and [r["i"] for r in a["outliers"]] == [0] and not b["outliers"])
               else "冷启动假设不成立或需再测")
    out.append("判读: " + verdict)
    io.open(f"_det_coldstart_{TAG}.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
    io.open(f"_det_coldstart_{TAG}.json", "w", encoding="utf-8").write(
        json.dumps({"A": a["clusters"], "B": b["clusters"],
                    "A_outliers": [r["i"] for r in a["outliers"]],
                    "B_outliers": [r["i"] for r in b["outliers"]]}, ensure_ascii=False))
    print("wrote _det_coldstart.txt")


if __name__ == "__main__":
    main()
