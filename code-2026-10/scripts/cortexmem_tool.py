# -*- coding: utf-8 -*-
"""CortexMem 查询工具 v1.0 (2026-08-11)
供 Hermes agent 调用的 JSON 输出接口

用法 (agent 调用):
  python cortexmem_tool.py '{"action":"query","query":"奥卡姆","top_k":5}'
  python cortexmem_tool.py '{"action":"add","content":"新知识","type":"semantic"}'
  python cortexmem_tool.py '{"action":"stats"}'

输出: JSON {success, data, error}
"""
# side_effects: [写数据文件]
import os, sys, io, json

# stdout 重配放 __main__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cortexmem import CortexMem, SEMANTIC, EPISODIC, PROCEDURAL

def handle(args: dict) -> dict:
    action = args.get("action", "query")
    mem = CortexMem()

    # ── [CoMem 借鉴 2026-09-16] 多样性过滤检索 (机制③) ──
    if action == "query_diverse":
        q = args.get("query", "")
        top_k = int(args.get("top_k", 5))
        if not q:
            return {"success": False, "error": "query 参数为空"}
        results = mem.query_diverse(q, top_k)
        return {"success": True, "data": {
            "query": q,
            "mode": "diverse" if results and results[0].get("cluster", -1) >= 0 else "degraded",
            "results": [{"content": r["content"], "type": r["type"],
                         "state": r["state"], "score": r["score"],
                         "cluster": r.get("cluster")} for r in results],
            "hit_count": len(results),
        }}

    # ── CoMem 提升门诊断 (机制②) ──
    if action == "gate_profile":
        return {"success": True, "data": mem.gate_profile()}

    if action == "query":
        q = args.get("query", "")
        top_k = int(args.get("top_k", 5))
        if not q:
            return {"success": False, "error": "query 参数为空"}
        results = mem.query(q, top_k)
        return {"success": True, "data": {
            "query": q,
            "results": [{"content": r["content"], "type": r["type"],
                         "state": r["state"], "score": r["score"]} for r in results],
            "hit_count": len(results),
        }}

    elif action == "add":
        content = args.get("content", "")
        ntype = args.get("type", "semantic")
        if not content:
            return {"success": False, "error": "content 参数为空"}
        type_map = {"semantic": SEMANTIC, "episodic": EPISODIC, "procedural": PROCEDURAL}
        mem.add(content, type_map.get(ntype, SEMANTIC))
        mem.save()
        return {"success": True, "data": {"added": content[:50], "nodes": mem.stats()["nodes"]}}

    elif action == "stats":
        return {"success": True, "data": mem.stats()}

    elif action == "sleep":
        r = mem.sleep()
        mem.save()
        return {"success": True, "data": {"consolidation": r, "stats": mem.stats()}}

    # ── v2.2 新功能 (P1 接入) ──
    elif action == "disclose":
        """L0/L1/L2 渐进披露"""
        q = args.get("query", "")
        top_k = int(args.get("top_k", 5))
        if not q:
            return {"success": False, "error": "query 参数为空"}
        r = mem.disclose(q, top_k)
        return {"success": True, "data": r}

    elif action == "expand":
        """L2 展开全文"""
        nid = args.get("id", "")
        if not nid:
            return {"success": False, "error": "id 参数为空"}
        return {"success": True, "data": mem.expand(nid)}

    elif action == "pin":
        """固定记忆 (永不驱逐)"""
        nid = args.get("id", "")
        pinned = bool(args.get("pinned", True))
        if not nid:
            return {"success": False, "error": "id 参数为空"}
        return {"success": True, "data": mem.pin(nid, pinned)}

    elif action == "compress":
        """符号压缩长记忆"""
        nid = args.get("id", "")
        if not nid:
            return {"success": False, "error": "id 参数为空"}
        r = mem.compress(nid)
        return {"success": True, "data": r}

    elif action == "feedback":
        """用户反馈驱动权重"""
        nid = args.get("id", "")
        liked = bool(args.get("liked", True))
        if not nid:
            return {"success": False, "error": "id 参数为空"}
        return {"success": True, "data": mem.feedback(nid, liked)}

    elif action == "repair":
        """决策修复 (检索失败自动修复)"""
        q = args.get("query", "")
        top_k = int(args.get("top_k", 3))
        if not q:
            return {"success": False, "error": "query 参数为空"}
        return {"success": True, "data": mem.query_repair(q, top_k)}

    elif action == "archive_query":
        """[AL1] 归档检索 (蒸馏归档的 episodic 组)"""
        q = args.get("query", "")
        top_k = int(args.get("top_k", 5))
        if not q:
            return {"success": False, "error": "query 参数为空"}
        return {"success": True, "data": mem.archive_query(q, top_k)}

    elif action == "cache":
        """缓存查询 (LRU+TTL)"""
        q = args.get("query", "")
        top_k = int(args.get("top_k", 5))
        ttl = int(args.get("ttl", 3600))
        if not q:
            return {"success": False, "error": "query 参数为空"}
        r = mem.cached_query(q, top_k, ttl)
        return {"success": True, "data": {"cached": r["cached"],
                                          "results": [{"content": x["content"], "score": x["score"]} for x in r["results"]]}}

    else:
        return {"success": False, "error": f"未知 action: {action}"}

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    try:
        if len(sys.argv) > 1:
            args = json.loads(sys.argv[1])
        else:
            args = {"action": "stats"}
        result = handle(args)
    except json.JSONDecodeError as e:
        result = {"success": False, "error": f"JSON 解析失败: {e}"}
    except Exception as e:
        result = {"success": False, "error": f"异常: {e}"}
    print(json.dumps(result, ensure_ascii=False))
# test
