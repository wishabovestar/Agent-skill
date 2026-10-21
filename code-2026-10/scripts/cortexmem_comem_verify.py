#!/usr/bin/env python3
"""
CoMem 三机制落地验证 — 在 state.json 副本上端到端测试 (不污染真实库)
════════════════════════════════════════════════════════════════
验证项:
  1. gate_profile()  提升门决策画像 (曝光 ∧ 基线) + 停摆守卫
  2. query_diverse() 多样性过滤检索 (机制③) 端到端
  3. legacy 回退开关 CORTEXMEM_GATE=legacy
  4. 降级路径: embedding 不可用 → fails-open 返回单流
"""
import os, sys, json, shutil, tempfile, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPTS = r"<PROFILE_ROOT>\scripts"
sys.path.insert(0, SCRIPTS)
REAL_STATE = r"<PROFILE_ROOT>\knowledge_base\cortexmem\state.json"

# ── 副本 ──
tmpdir = tempfile.mkdtemp(prefix="cortexmem_verify_")
shutil.copy2(REAL_STATE, os.path.join(tmpdir, "state.json"))
print("[副本] %s (%.1f MB)" % (tmpdir, os.path.getsize(REAL_STATE) / 1e6))

import cortexmem
cortexmem.STATE_FILE = os.path.join(tmpdir, "state.json")   # ★ 重定向到副本

cm = cortexmem.CortexMem()
cm.load()
print("[载入] 节点 %d" % len(cm.state["nodes"]))

print("\n═══ 1. 提升门决策画像 (机制②) ═══")
p = cm.gate_profile()
for k, v in p.items():
    print("   %-18s %s" % (k, v))
print("   → 判定: %s" % ("🔴 停摆! 需校准" if p["frozen"] else "✅ 未停摆"))

print("\n═══ 2. 多样性过滤检索 (机制③) ═══")
# 取一个真实节点内容作查询
ids = [k for k, v in cm.state["nodes"].items() if len(v.get("content", "")) > 20]
q = cm.state["nodes"][ids[0]]["content"][:100]
print("   查询: %s" % q[:70])
plain = cm.query(q, top_k=5)
div = cm.query_diverse(q, top_k=5)
print("\n   ── 单流 query() ──")
for c in plain:
    print("     [%.3f] %s" % (c["score"], c["content"][:58]))
print("   ── query_diverse() ──")
for c in div:
    print("     [%.3f] cluster=%-3s %s" % (c["score"], c.get("cluster"), c["content"][:50]))

# 度量
def red(items):
    ems = [cortexmem.CortexMem._embed(cm.state["nodes"][c["id"]]["content"][:500]) for c in items]
    ems = [e for e in ems if e]
    if len(ems) < 2:
        return None, 0
    ps = [cortexmem.CortexMem._cosine(ems[i], ems[j])
          for i in range(len(ems)) for j in range(i + 1, len(ems))]
    return sum(ps) / len(ps), len(set(cortexmem.CortexMem._cluster_embs(ems, 0.60)))

rp, cp = red(plain)
rd, cd = red(div)
if rp is not None and rd is not None:
    print("\n   冗余度: 单流 %.4f → 多样 %.4f (↓%.1f%%)" % (rp, rd, (rp - rd) / rp * 100))
    print("   语义簇: 单流 %d → 多样 %d" % (cp, cd))

print("\n═══ 3. legacy 回退开关 ═══")
os.environ["CORTEXMEM_GATE"] = "legacy"
print("   CORTEXMEM_GATE=legacy → _gate_mode() =", cm._gate_mode())
os.environ.pop("CORTEXMEM_GATE")
print("   默认                 → _gate_mode() =", cm._gate_mode())

print("\n═══ 4. 降级路径 (embedding 不可用) ═══")
_orig = cortexmem.CortexMem._embed
cortexmem.CortexMem._embed = staticmethod(lambda t: None)
d2 = cm.query_diverse(q, top_k=5)
cortexmem.CortexMem._embed = _orig
print("   embedding 返回 None → cluster 标记:", [c.get("cluster") for c in d2])
print("   → %s" % ("✅ fails-open 降级正常 (返回单流)" if all(c.get("cluster") == -1 for c in d2)
                   else "🔴 降级异常"))
print("   条目数: %d (应为 5)" % len(d2))

print("\n═══ 5. 真实库未被污染 ═══")
print("   真实 state.json mtime: %s" % time.strftime("%Y-%m-%d %H:%M:%S",
      time.localtime(os.path.getmtime(REAL_STATE))))
print("   副本目录: %s" % tmpdir)
shutil.rmtree(tmpdir, ignore_errors=True)
print("\n  ✅ 验证完成, 副本已清理")
