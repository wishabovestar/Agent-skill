# -*- coding: utf-8 -*-
"""CortexMem 每日巩固 cron 脚本 v1.0 (2026-08-11)
每日: 同步新消息 + 睡眠巩固
周度: 完整验证报告

输出: knowledge_base/audit/cortexmem_daily_YYYYMMDD.md
"""
# side_effects: [写数据文件]
import os, sys, io, json, time, datetime

# [修复] stdout 重配移入 __main__ (herdr State/Runtime 分离)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cortexmem_integrate import sync_new_messages
from cortexmem import CortexMem

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT = os.path.join(BASE, "knowledge_base", "audit")

def main():
    today = datetime.date.today().isoformat()
    print(f"🌙 CortexMem 每日巩固 {today}")
    print("=" * 50)

    # 0. [AJ1] 周度备份 (周日): state.json → audit/cortexmem_backup/ (防覆盖事故)
    if datetime.date.today().weekday() == 6:
        bak_dir = os.path.join(AUDIT, "cortexmem_backup")
        os.makedirs(bak_dir, exist_ok=True)
        src = os.path.join(BASE, "knowledge_base", "cortexmem", "state.json")
        dst = os.path.join(bak_dir, f"state_{today}.json")
        if os.path.exists(src):
            import shutil
            shutil.copy(src, dst)
            print(f"💾 周度备份: {dst} ({os.path.getsize(dst)} bytes)")
        else:
            print(f"⚠️ state.json 不存在, 跳过备份: {src}")

    # 1. 同步新消息
    added, stats = sync_new_messages()
    print(f"🔄 同步: 语义{added['semantic']} 情景{added['episodic']} 高权重{added['high_weight']}")
    print(f"   总节点: {stats['nodes']} | 状态: {stats['states']}")

    # 2. 睡眠巩固
    mem = CortexMem()
    before = mem.stats()["nodes"]
    r = mem.sleep()
    mem.save()
    after = mem.stats()["nodes"]
    print(f"🌙 巩固: 蒸馏{r['distilled']} 聚类{r['clusters']} 剪枝{r['pruned']}")
    print(f"   节点: {before} → {after}")

    # 2.5 [AO1] 模板压缩 (cron 同构消息, 每日)
    t0 = mem.compress_templates(min_count=10)
    if t0:
        print(f"🧹 模板压缩: {t0} 节点 (同构消息归档)")
        print(f"   节点: {after} → {mem.stats()['nodes']}")

    # 3. 周度验证 (周一)
    if datetime.date.today().weekday() == 0:
        print("\n📊 周度验证:")
        # 抽查 3 个查询
        for q in ["记忆", "错误", "优化"]:
            results = mem.query(q, 3)
            print(f"   '{q}': {len(results)} 命中")
        # 30天模拟
        sim = mem.simulate_30d()
        print(f"   30天保持率: {sim:.3f} (基线 0.331)")

    # 报告
    report = {
        "date": today, "added": added, "stats": stats,
        "consolidation": r, "sim_30d": sim if datetime.date.today().weekday() == 0 else None,
    }
    os.makedirs(AUDIT, exist_ok=True)
    with open(os.path.join(AUDIT, f"cortexmem_daily_{today}.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"\n✅ 报告: audit/cortexmem_daily_{today}.json")

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
