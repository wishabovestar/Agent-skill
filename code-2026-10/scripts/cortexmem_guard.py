# -*- coding: utf-8 -*-
"""CortexMem + memory_guard 安全整合 v1.0 (2026-08-11)
写入 CortexMem 前经 memory_guard 注入防御校验
恶意内容 → 隔离 (不写入, 记 quarantine)

用法:
  python cortexmem_guard.py '{"action":"add","content":"...","type":"semantic"}'
  python cortexmem_guard.py '{"action":"query","query":"..."}'
"""
# side_effects: [写数据文件]
import os, sys, io, json

# stdout 重配放 __main__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cortexmem import CortexMem, SEMANTIC, EPISODIC, PROCEDURAL
from memory_guard import check, protect

QUARANTINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cortexmem_quarantine.json")

def load_quarantine():
    if os.path.exists(QUARANTINE):
        try:
            return json.load(open(QUARANTINE, encoding="utf-8"))
        except Exception:
            return []
    return []

def save_quarantine(items):
    if os.path.exists(QUARANTINE):
        if os.path.exists(QUARANTINE + ".bak"):
            try: os.remove(QUARANTINE + ".bak")
            except OSError: pass
        os.rename(QUARANTINE, QUARANTINE + ".bak")
    json.dump(items, open(QUARANTINE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def guarded_add(content: str, ntype: str) -> dict:
    """安全写入: memory_guard 校验 → CortexMem"""
    # 1. 注入检测
    result = check(content, "cortexmem")
    findings = result.get("findings", [])

    if findings:
        # 2. 恶意 → 隔离
        quarantine = load_quarantine()
        quarantine.append({"content": content[:200], "findings": findings,
                           "time": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
                           "action": result.get("action", "block")})
        save_quarantine(quarantine)
        return {"success": False, "blocked": True, "findings": findings,
                "quarantined": True, "message": f"已隔离: {findings}"}

    # 3. 安全 → 写入
    mem = CortexMem()
    type_map = {"semantic": SEMANTIC, "episodic": EPISODIC, "procedural": PROCEDURAL}
    mem.add(content, type_map.get(ntype, SEMANTIC))
    mem.save()
    return {"success": True, "blocked": False,
            "nodes": mem.stats()["nodes"], "risk": result.get("risk_level", "safe")}

def handle(args: dict) -> dict:
    action = args.get("action", "query")

    if action == "add":
        content = args.get("content", "")
        ntype = args.get("type", "semantic")
        if not content:
            return {"success": False, "error": "content 为空"}
        return guarded_add(content, ntype)

    elif action == "query":
        mem = CortexMem()
        q = args.get("query", "")
        results = mem.query(q, int(args.get("top_k", 5)))
        return {"success": True, "data": {
            "query": q,
            "results": [{"content": r["content"], "type": r["type"],
                         "state": r["state"], "score": r["score"]} for r in results],
        }}

    elif action == "quarantine":
        return {"success": True, "data": {"quarantined": load_quarantine()}}

    elif action == "stats":
        mem = CortexMem()
        return {"success": True, "data": mem.stats()}

    else:
        return {"success": False, "error": f"未知 action: {action}"}

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    try:
        args = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {"action": "stats"}
        print(json.dumps(handle(args), ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
