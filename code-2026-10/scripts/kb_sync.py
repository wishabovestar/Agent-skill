#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
kb_sync.py — 知识库同步驱动（每周 cron 入口）

链路：
  [1] MatSeek 结构化   D:/hermes/analysis/matseek_pipeline.py
      → 文档/章节/图表/实体/三元组/知识图谱  (D:/hermes/data/matseek/)
  [2] 知识域索引       <scripts>/kb_domain_structuring.py
      → 知识域归并 + 去重 + SQLite FTS5  (D:/hermes/data/agent_knowledge/_structured/)

输出：D:/hermes/data/kb_sync/last_run.json + sync_<date>.md（供 cron 投递/留档）
幂等：两步均为覆盖式重建；失败不阻断另一步，逐条记录。
"""
import os, sys, json, time, subprocess, datetime

ANALYSIS = r"D:\hermes\analysis"
SCRIPTS  = r"D:\hermes\hermes-data\profiles\mybot\scripts"
LOG_DIR  = r"D:\hermes\data\kb_sync"
os.makedirs(LOG_DIR, exist_ok=True)

STEPS = [
    ("MatSeek 结构化(三元组/图谱)", os.path.join(ANALYSIS, "matseek_pipeline.py")),
    ("知识域结构化(索引/FTS5)",    os.path.join(SCRIPTS,  "kb_domain_structuring.py")),
]

def pick_python():
    """优先挑一个能 import fitz 的解释器（MatSeek 解析 PDF 需要 pymupdf）。"""
    cands = [
        r"C:\Users\Administrator\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe",
        sys.executable, "python3", "python",
    ]
    for c in cands:
        try:
            if os.path.sep in c and not os.path.exists(c):
                continue
            r = subprocess.run([c, "-c", "import fitz"], capture_output=True, timeout=90)
            if r.returncode == 0:
                return c
        except Exception:
            continue
    return sys.executable

def run(py, script, timeout=3600):
    env = dict(os.environ); env["PYTHONUTF8"] = "1"; env["PYTHONIOENCODING"] = "utf-8"
    t0 = time.time()
    try:
        p = subprocess.run([py, script], capture_output=True, text=True, timeout=timeout, env=env,
                           encoding="utf-8", errors="replace")
        return {"rc": p.returncode, "sec": round(time.time()-t0, 1),
                "tail": (p.stdout or "")[-1500:] + (("\n[stderr] " + (p.stderr or "")[-600:]) if p.stderr else "")}
    except subprocess.TimeoutExpired:
        return {"rc": -9, "sec": round(time.time()-t0, 1), "tail": f"[timeout >{timeout}s]"}
    except Exception as e:
        return {"rc": -1, "sec": round(time.time()-t0, 1), "tail": f"[error] {e}"}

def main():
    py = pick_python()
    stamp = datetime.datetime.now()
    results = []
    for label, script in STEPS:
        if not os.path.exists(script):
            results.append({"step": label, "script": script, "rc": -2, "sec": 0, "tail": "[missing script]"}); continue
        results.append(dict(step=label, script=script, **run(py, script)))

    ok = all(r["rc"] == 0 for r in results)
    summary = {"generated_at": stamp.isoformat(timespec="seconds"), "python": py,
               "ok": ok, "steps": results}
    json.dump(summary, open(os.path.join(LOG_DIR, "last_run.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # 读取源库规模（同步效果）
    def count_recs():
        try:
            import json as _j
            return len(_j.load(open(r"D:\hermes\data\agent_knowledge\_structured\records.json", encoding="utf-8")))
        except Exception:
            return None
    def matseek_docs():
        try:
            import json as _j
            m = _j.load(open(r"D:\hermes\data\matseek\manifest.json", encoding="utf-8"))
            return m.get("documents_total"), m.get("triples_total")
        except Exception:
            return None, None

    recs = count_recs(); docs, trips = matseek_docs()
    lines = [f"# 知识库同步 {stamp:%Y-%m-%d %H:%M}", "",
             f"- 状态：{'✅ 成功' if ok else '⚠️ 有失败'}",
             f"- 解释器：`{py}`",
             f"- 知识域索引：{recs if recs is not None else '未获取到'} 条",
             f"- MatSeek：文档 {docs if docs is not None else '未获取到'} · 三元组 {trips if trips is not None else '未获取到'}", "",
             "## 步骤", "", "| 步骤 | 退出码 | 耗时(s) |", "|:---|---:|---:|"]
    for r in results:
        lines.append(f"| {r['step']} | {r['rc']} | {r['sec']} |")
    if not ok:
        lines += ["", "## 失败详情", ""]
        for r in results:
            if r["rc"] != 0:
                lines += [f"### {r['step']}", "```", r["tail"][-800:], "```", ""]
    md = os.path.join(LOG_DIR, f"sync_{stamp:%Y%m%d}.md")
    open(md, "w", encoding="utf-8").write("\n".join(lines))

    # stdout = cron(no_agent) 投递内容
    print(f"[kb_sync] {'OK' if ok else 'FAIL'} | " + " | ".join(f"{r['step']}:rc={r['rc']}" for r in results))
    print(f"  知识域索引={recs}  MatSeek文档={docs} 三元组={trips}  log={md}")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
