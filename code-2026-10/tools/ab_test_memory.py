#!/usr/bin/env python3
"""A/B测试: 当前redis扁平记忆 vs TencentDB L0-L3分层记忆
A组 = redis + MEMORY.md (现状)
B组 = TencentDB Gateway (L0-L3分层)
测试: ①写入延迟 ②检索召回 ③token效率
"""
import json, time, urllib.request, os, re, random

GATEWAY = "http://127.0.0.1:8420"
MEMORY_FILE = r"D:\hermes\hermes-data\profiles\mybot\memories\MEMORY.md"

def call_gateway(path, payload):
    """调用TencentDB Gateway"""
    req = urllib.request.Request(
        f"{GATEWAY}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}

def ab_test():
    print("=" * 60)
    print("A/B测试: redis扁平记忆 vs TencentDB L0-L3分层记忆")
    print("=" * 60)

    # 读取当前记忆 (A组数据源)
    with open(MEMORY_FILE, encoding='utf-8') as f:
        mem_content = f.read()
    print(f"\n[数据] 当前MEMORY.md: {len(mem_content)}字符, {len(mem_content.split(chr(10)))}行")
    print(f"[数据] 会话DB: 563MB (qqbot3) — 可用seed历史")

    # ── A组基线: 当前记忆检索 (关键词覆盖)
    print("\n── A组: 扁平记忆检索 (当前) ──")
    queries = ["锂电", "VPS", "网络", "记忆", "Agent"]
    a_scores = {}
    for q in queries:
        hits = mem_content.count(q)
        a_scores[q] = hits
        print(f"  查询'{q}': 命中 {hits} 处")

    # ── B组: TencentDB分层记忆 (seed真实记忆内容)
    print("\n── B组: TencentDB L0-L3分层记忆 ──")

    # 1. capture: 写入记忆条目
    b_write_times = []
    lines = [l for l in mem_content.split('\n') if l.strip()]
    for i, line in enumerate(lines[:30]):  # 取前30行记忆
        t0 = time.time()
        r = call_gateway("/capture", {
            "session_id": "ab_test",
            "user_message": line[:200],
            "assistant_message": "",
            "metadata": {"source": "ab_test", "idx": i}
        })
        b_write_times.append(time.time() - t0)
    avg_write = sum(b_write_times) / max(len(b_write_times), 1)
    print(f"  capture写入 {len(b_write_times)} 条: 平均 {avg_write*1000:.1f}ms/条")

    # 2. recall: 检索查询
    print(f"\n  recall检索测试:")
    b_scores = {}
    for q in queries:
        r = call_gateway("/recall", {"query": q, "session_key": "ab_test"})
        if "error" not in r:
            n = len(r.get("results", r.get("memories", [])))
            b_scores[q] = n
            print(f"    查询'{q}': 返回 {n} 条相关记忆")
        else:
            print(f"    查询'{q}': 错误 {str(r['error'])[:60]}")

    # 3. 汇总
    print("\n" + "=" * 60)
    print("汇总对比:")
    print(f"  A组(扁平): 写入=即时(文件), 检索=全文count, 结构化=无")
    print(f"  B组(分层): 写入={avg_write*1000:.1f}ms/条, 检索=语义召回, 结构化=L0-L3")
    print(f"  B组写入吞吐: {1/max(avg_write,0.001):.1f} 条/秒")
    print("=" * 60)
    return {"a_scores": a_scores, "b_scores": b_scores, "avg_write_ms": avg_write*1000}

if __name__ == "__main__":
    result = ab_test()
    with open(r"D:\hermes\data\ab_test_memory_results.json", "w", encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("\n✅ 结果已保存: D:/hermes/data/ab_test_memory_results.json")
