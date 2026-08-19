# -*- coding: utf-8 -*-
"""Tokenless 工具输出预处理层 v1.0 (2026-08-16, GK)
场景感知 reducer: 大输出 → 保留关键行 (错误/计数/头尾)
吸收: MineEcho TokenLess (15 规则) + A/B 验证 (88.9% 节省)

用法:
  from tokenless_reducer import reduce_output
  out = reduce_output(raw_text)  # 自动场景检测 + 压缩 + 统计
"""
import io
import json
import os
import re
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
STATS = os.path.join(os.path.dirname(BASE), "data", "tokenless_stats.jsonl")

MAX_KEEP = 4000  # 超过才压缩 (字符)


# ── 场景检测 ──
def detect_scene(output):
    """检测输出场景 (优先级: 编译 > git > json > 通用)"""
    low = output.lower()
    if re.search(r"error\[|warning:|compilation failed|traceback", low):
        return "compile"
    if re.search(r"^commit [0-9a-f]{7,}", output, re.M) or "git log" in low:
        return "git"
    if output.lstrip().startswith(("{", "[")):
        return "json"
    return "doc"


# ── 场景 reducer 规则 ──
def reduce_compile(lines):
    critical = [l for l in lines if re.search(r"error|warning|failed|^\s*\d+ \|", l.lower())
                or re.match(r"\s*-->>", l)]
    count = {"errors": len(re.findall(r"error\[", "\n".join(lines))),
             "warnings": len(re.findall(r"warning:", "\n".join(lines)))}
    return f"[compile {count}] 关键行:\n" + "\n".join(critical[:60])


def reduce_git(lines):
    commits = len([l for l in lines if re.match(r"^commit ", l)])
    head = [l for l in lines[:6] if l.strip()][:4]
    tail = [l for l in lines[-4:] if l.strip()][-2:]
    return f"[git {commits} commits] 头尾:\n" + "\n".join(head + ["..."] + tail)


def reduce_json(output):
    # JSON: 保留结构 + 截断长值
    try:
        data = json.loads(output)
        n = len(data) if isinstance(data, (list, dict)) else 1
        s = json.dumps(data, ensure_ascii=False)[:MAX_KEEP]
        return f"[json {n} 项] {s}..."
    except Exception:
        return f"[json 解析失败] 头800: {output[:800]}"


def reduce_doc(lines):
    count = len(lines)
    head = [l for l in lines[:4] if l.strip()][:3]
    tail = [l for l in lines[-3:] if l.strip()][-2:]
    return f"[doc {count} 行] 头尾:\n" + "\n".join(head + ["..."] + tail)


REDUCERS = {"compile": reduce_compile, "git": reduce_git,
            "json": reduce_json, "doc": reduce_doc}


# ── 主入口 ──
def reduce_output(output, force=False):
    """压缩工具输出: 超阈值 + 场景检测 + 统计"""
    if not force and len(output) <= MAX_KEEP:
        return output
    scene = detect_scene(output)
    reduced = REDUCERS[scene](output.split("\n"))
    # 统计 (raw → reduced 节省)
    try:
        with open(STATS, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "scene": scene, "raw": len(output), "reduced": len(reduced),
                "save_pct": round((1 - len(reduced) / len(output)) * 100, 1),
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return reduced


def stats_summary():
    """节省统计汇总"""
    if not os.path.exists(STATS):
        return {"calls": 0, "avg_save": 0}
    raw = red = calls = 0
    for line in open(STATS, encoding="utf-8"):
        try:
            d = json.loads(line)
            raw += d["raw"]
            red += d["reduced"]
            calls += 1
        except Exception:
            pass
    return {"calls": calls, "raw": raw, "reduced": red,
            "avg_save": round((1 - red / raw) * 100, 1) if raw else 0}


def main():
    # 演示: 3 场景真实压缩
    test_git = "\n".join(f"commit {hex(i)[2:].zfill(40)}  feat: m{i}" for i in range(1, 50))
    test_compile = "error[E0308]: mismatch\n --> src:42\n" + "warning: unused\n" + \
                   "\n".join(f"info: check {i}" for i in range(30))
    test_doc = "\n".join(f"文档行 {i} 内容" for i in range(200))

    print("=== Tokenless 预处理层 v1.0 演示 ===\n")
    for name, out in [("git", test_git), ("compile", test_compile), ("doc", test_doc)]:
        r = reduce_output(out, force=True)
        print(f"[{name}] {len(out)} → {len(r)} 字符 "
              f"({(1 - len(r) / len(out)) * 100:.0f}% 节省) | 场景: {detect_scene(out)}")
        print(f"  输出: {r.splitlines()[0][:70]}")

    s = stats_summary()
    print(f"\n=== 统计: {s['calls']} 次压缩 | 平均节省 {s['avg_save']}% ===")
    print("✅ P1 落地完成: reduce_output() 可挂工具输出链路")


if __name__ == "__main__":
    main()
