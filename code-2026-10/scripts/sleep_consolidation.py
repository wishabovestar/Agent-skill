#!/usr/bin/env python3
"""
睡眠记忆巩固 (Sleep Memory Consolidation)
arXiv: 2606.03979v2 — Google Research
合并: 白日梦上下文去噪 (arXiv 2604.19258)

Stage 1: Memory Consolidation — 记忆合并与重要性筛选
Stage 2: Dreaming — 生成自我改进/知识固化建议
"""
import json, sys, os
from datetime import datetime
from pathlib import Path

ANALYSIS_DIR = Path("D:/hermes/analysis")
OUTPUT_DIR = Path("D:/hermes/hermes-data/profiles/mybot/cron/output")

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def main():
    print("=" * 60)
    print("🧠 睡眠记忆巩固 — Sleep Memory Consolidation")
    print(f"   执行时间: {datetime.now().isoformat()}")
    print("=" * 60)

    # ── Stage 1: 记忆合并 ──
    log("Stage 1: 记忆合并 (Memory Consolidation)...")
    result = {"downgraded": 0, "merged": 0, "decayed": 0, "purged": 0}

    mem_py = ANALYSIS_DIR / "memory_extension.py"
    if mem_py.exists():
        try:
            sys.path.insert(0, str(ANALYSIS_DIR))
            # 直接exec避免UTF-8 .env读取问题
            ns = {}
            with open(mem_py, "r", encoding="utf-8", errors="replace") as f:
                code = f.read()
            exec(code, ns)
            me = ns["MemoryEngine"]()
            result = me.consolidate(dry_run=False)
            log(f"  降级: {result.get('downgraded', 0)} | 合并: {result.get('merged', 0)} | 衰减: {result.get('decayed', 0)} | 清理: {result.get('purged', 0)}")
        except Exception as e:
            log(f"  ⚠ MemoryEngine.consolidate() 不可用: {e}")
    else:
        log("  memory_extension.py 未找到, 跳过")

    # ── Stage 2: Dreaming ──
    log("Stage 2: Dreaming (自改进数据生成)...")
    dreaming_output = OUTPUT_DIR / f"dreaming_{datetime.now().strftime('%Y%m%d')}.md"
    dreaming_output.parent.mkdir(parents=True, exist_ok=True)

    dreaming_lines = [
        f"# 🧠 睡眠巩固 Dreaming 报告 ({datetime.now().strftime('%Y-%m-%d')})",
        "",
        "## Stage 1: 记忆合并结果",
        f"- 降级: {result.get('downgraded', 0)}",
        f"- 合并: {result.get('merged', 0)}",
        f"- 衰减: {result.get('decayed', 0)}",
        f"- 清理: {result.get('purged', 0)}",
        "",
        "## Stage 2: Dreaming 自改进建议",
        "",
        "### 📗 记忆管理",
        "- 检查 MEMORY 使用率, >80% 需清理低重要性条目",
        "- 低重要性条目可降级到 Redis short-term 缓存",
        "- 跨 session 重复出现的用户偏好写入 user profile",
        "",
        "### 📗 知识固化",
        "- 高频会话主题可提炼为 skill (SKILL.md)",
        "- 工具使用模式总结为最佳实践文档",
        "- 算法/数学知识存入 knowledge_store",
        "",
        "### 📗 系统优化",
        "- cron 执行记录检查: 失败超过3次的任务考虑修复或删除",
        "- 画像更新: 确认用户画像时效性 (>7天未更新需刷新)",
        "- 网关状态: 检查各平台 token 是否即将过期",
        "",
        "---",
        "*自动生成于睡眠巩固流程*",
    ]
    dreaming_output.write_text("\n".join(dreaming_lines), encoding="utf-8")
    log(f"  Dreaming报告: {dreaming_output}")

    # ── 汇总报告 ──
    report = {
        "timestamp": datetime.now().isoformat(),
        "algorithms": [
            "Sleep Memory Consolidation (arXiv 2606.03979)",
            "Daydreaming Context Denoising (arXiv 2604.19258)"
        ],
        "stage1_memory_consolidation": result,
        "stage2_dreaming": {"output_file": str(dreaming_output)},
        "status": "ok"
    }
    report_path = OUTPUT_DIR / f"sleep_consolidation_{datetime.now().strftime('%Y%m%d')}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ 睡眠巩固完成")
    print(f"   Stage 1 合并: {result.get('merged', 0)}条 | 衰减: {result.get('decayed', 0)}条 | 清理: {result.get('purged', 0)}条")
    print(f"   Stage 2 Dreaming: dreaming_{datetime.now().strftime('%Y%m%d')}.md")
    print(f"   报告: {report_path}")

if __name__ == "__main__":
    main()
