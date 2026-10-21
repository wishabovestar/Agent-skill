#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A/B 测试调度器 v1.0 — 队列管理与顺序执行
=========================================
管理10项A/B测试套件，按依赖关系和优先级顺序执行。
队列状态持久化到 ab_test_queue.json。

用法:
  python ab_test_scheduler.py --status          # 查看队列状态
  python ab_test_scheduler.py --run SLEEP-02    # 执行指定实验
  python ab_test_scheduler.py --run-all         # 按序执行所有可运行实验
  python ab_test_scheduler.py --absorb <id>     # 标记吸收亮点(算法改善)
  python ab_test_scheduler.py --orthogonal <id> # 标记正交化排队
"""
import json, sys, subprocess
from pathlib import Path
from datetime import datetime

QUEUE_FILE = Path(r"D:/hermes/data/ab_test_queue.json")
SCRIPTS_DIR = Path(r"D:/hermes/hermes-data/profiles/mybot/scripts")
RESULTS_DIR = Path(r"D:/hermes/hermes-data/profiles/mybot/knowledge_base/research")

# 实验定义: id -> {script, depends_on, priority, status, notes}
EXPERIMENTS = {
    "AB-SLEEP-02": {
        "name": "睡眠promote渐进搜索(18-25%)",
        "script": "ab_sleep02_test.py",
        "depends_on": ["AB-SLEEP-01"],  # 01已完成: 保持18%
        "priority": "P1",
        "status": "queued",
        "note": "从18→25%步进2%, 找边际收益=边际成本点。01结论: 22%更差, 重点测20%附近",
    },
    "AB-SEARCH-02": {
        "name": "MMR lambda场景自适应",
        "script": "ab_search02_test.py",
        "depends_on": ["AB-SEARCH-01"],  # 01已完成: 固定0.6
        "priority": "P1",
        "status": "queued",
        "note": "固定λ=0.57 vs λ自适应(窄0.80/宽0.55), 多样性覆盖率+15%假设",
    },
    "AB-6D-01": {
        "name": "6D评分权重优化",
        "script": "ab_6d01_test.py",
        "depends_on": [],
        "priority": "P1",
        "status": "queued",
        "note": "均匀权重 vs 优化权重(freq=0.2,div=0.2...), rank_correlation提升20%假设",
    },
    "AB-DREAM-01": {
        "name": "白日梦跨域链接量优化",
        "script": "ab_dream01_test.py",
        "depends_on": ["DREAM-v3-ONLINE"],  # 需daydream_v3积累数据
        "priority": "P0",
        "status": "waiting_data",
        "note": "v3已上线, 积累30 session后执行。目标1.5链接/session",
    },
    "AB-DREAM-02": {
        "name": "白日梦链接质量阈值调优",
        "script": "ab_dream02_test.py",
        "depends_on": ["AB-DREAM-01"],
        "priority": "P1",
        "status": "waiting_data",
        "note": "阈值0.7-0.95测试, 依赖DREAM-01",
    },
    "AB-TEMP-02": {
        "name": "压缩阶段边界优化",
        "script": "ab_temp02_test.py",
        "depends_on": ["AB-TEMP-01-DATA"],  # 需>30天记忆数据
        "priority": "P1",
        "status": "waiting_data",
        "note": "stage边界3/10/30d vs 7/30d, 依赖库积累>30天数据(预计10月中)",
    },
    "AB-PI-01": {
        "name": "扩展门控阈值优化",
        "script": "ab_pi01_test.py",
        "depends_on": [],
        "priority": "P1",
        "status": "queued",
        "note": "block_threshold 0.8 vs 1.0, 安全敏感需隔离环境验证",
    },
}

def load_queue():
    if QUEUE_FILE.exists():
        return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    return {"updated": None, "experiments": EXPERIMENTS}

def save_queue(q):
    q["updated"] = datetime.now().isoformat()
    QUEUE_FILE.write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")

def status():
    q = load_queue()
    print(f"=== A/B测试队列 ({q['updated'] or '未初始化'}) ===")
    print(f"{'ID':<15} {'优先级':<6} {'状态':<14} 实验")
    print("-" * 70)
    for eid, exp in q["experiments"].items():
        print(f"{eid:<15} {exp['priority']:<6} {exp['status']:<14} {exp['name']}")

def run_experiment(eid, q):
    exp = q["experiments"].get(eid)
    if not exp:
        print(f"未知实验: {eid}")
        return False
    if exp["status"] == "completed":
        print(f"⏭ {eid} 已完成，跳过")
        return True
    if exp["status"] == "waiting_data":
        print(f"⏸ {eid} 等待数据积累: {exp['note']}")
        return False
    script = SCRIPTS_DIR / exp["script"]
    if not script.exists():
        print(f"⚠ {eid} 脚本不存在: {script} — 标记待创建")
        exp["status"] = "script_missing"
        save_queue(q)
        return False
    print(f"▶ 执行 {eid}: {exp['name']}")
    exp["status"] = "running"
    save_queue(q)
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, encoding="utf-8", timeout=600)
    print(r.stdout[-1500:] if r.stdout else "")
    if r.stderr:
        print(f"[stderr] {r.stderr[-500:]}")
    exp["status"] = "completed" if r.returncode == 0 else "failed"
    exp["result"] = r.stdout[-1000:] if r.stdout else ""
    exp["finished"] = datetime.now().isoformat()
    save_queue(q)
    print(f"{'✅' if r.returncode == 0 else '❌'} {eid} 完成 (rc={r.returncode})")
    return r.returncode == 0

def run_all():
    q = load_queue()
    # 排序: P0优先, 再按依赖
    order = sorted(q["experiments"].items(),
                   key=lambda kv: (kv[1]["priority"] != "P0", len(kv[1].get("depends_on", []))))
    for eid, _ in order:
        exp = q["experiments"][eid]
        if exp["status"] in ("completed", "running"):
            continue
        run_experiment(eid, q)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    elif sys.argv[1] == "--status":
        status()
    elif sys.argv[1] == "--run" and len(sys.argv) > 2:
        q = load_queue()
        run_experiment(sys.argv[2], q)
    elif sys.argv[1] == "--run-all":
        run_all()
    else:
        print(__doc__)
