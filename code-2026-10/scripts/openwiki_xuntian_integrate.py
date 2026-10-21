#!/usr/bin/env python3
"""OpenWiki + 巡天知识采集 集成脚本。

集成工作流:
1. OpenWiki personal mode 从各源采集知识
2. 输出写入 ~/.openwiki/wiki/
3. 巡天知识库定期从 OpenWiki wiki 同步

用法:
  python openwiki_xuntian_integrate.py --init    初始化配置
  python openwiki_xuntian_integrate.py --sync    同步 OpenWiki → 巡天
  python openwiki_xuntian_integrate.py --ingest  全量采集+同步
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERMES_HOME = os.environ.get(
    "HERMES_HOME",
    "D:\\hermes\\hermes-data\\profiles\\mybot"
)
OPENWIKI_DIR = Path.home() / ".openwiki" / "wiki"
XUNTIAN_KB_DIR = Path(HERMES_HOME) / "knowledge_base" / "openwiki_sync"
SKILLS_DIR = Path(HERMES_HOME) / "skills" / "research"


def check_openwiki():
    """Check if npx openwiki is available."""
    try:
        r = subprocess.run(
            ["npx", "openwiki", "--version"],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "")}
        )
        return True
    except Exception:
        return False


def init_openwiki_personal():
    """Initialize OpenWiki personal mode configuration."""
    print("=== OpenWiki 个人知识库初始化 ===")

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("⚠ OPENAI_API_KEY 未设置。OpenWiki 需要 OpenAI API Key。")
        print("  设置: set OPENAI_API_KEY=sk-...")
        print("  或通过 .env 文件配置")
        return False

    print(f"✓ OpenAI API Key 已找到 ({api_key[:8]}...)")
    print("  运行初始化: npx openwiki personal --init")
    print()
    print("OpenWiki personal mode 支持的数据源:")
    print("  openwiki auth gmail      - Gmail 集成")
    print("  openwiki auth notion     - Notion 集成")
    print("  openwiki auth slack      - Slack 集成")
    print("  openwiki auth web-search - 网页搜索")
    print()
    print("配置完成后运行:")
    print("  openwiki personal --init  初始化个人Wiki")
    print("  openwiki ingest all       采集所有源")
    print()
    return True


def sync_to_xuntian():
    """Sync OpenWiki wiki → 巡天知识库."""
    if not OPENWIKI_DIR.exists():
        print(f"⚠ OpenWiki wiki 目录不存在: {OPENWIKI_DIR}")
        print("  先运行: npx openwiki personal --init")
        return False

    XUNTIAN_KB_DIR.mkdir(parents=True, exist_ok=True)

    count = 0
    for md_file in OPENWIKI_DIR.rglob("*.md"):
        rel_path = md_file.relative_to(OPENWIKI_DIR)
        dest = XUNTIAN_KB_DIR / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(md_file, dest)
        count += 1

    print(f"✓ 已同步 {count} 个文件到巡天知识库: {XUNTIAN_KB_DIR}")
    return True


def run_ingest():
    """Run full OpenWiki ingestion + sync to 巡天."""
    if not check_openwiki():
        print("❌ OpenWiki 未安装。运行: npm install -g openwiki")
        return False

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("❌ OPENAI_API_KEY 未设置")
        return False

    env = {**os.environ, "OPENAI_API_KEY": api_key}

    print("=== OpenWiki 全量采集 ===")
    r = subprocess.run(
        ["npx", "openwiki", "ingest", "all", "--print"],
        capture_output=True, text=True, timeout=300, env=env
    )
    print(r.stdout[-500:] if len(r.stdout) > 500 else r.stdout)
    if r.returncode != 0:
        print(f"⚠ ingest 返回码: {r.returncode}")
        if r.stderr:
            print(f"stderr: {r.stderr[-300:]}")

    print()
    print("=== 同步到巡天知识库 ===")
    sync_to_xuntian()

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenWiki + 巡天集成")
    parser.add_argument("--init", action="store_true", help="初始化配置")
    parser.add_argument("--sync", action="store_true", help="同步到巡天")
    parser.add_argument("--ingest", action="store_true", help="全量采集+同步")

    args = parser.parse_args()

    if args.init:
        sys.exit(0 if init_openwiki_personal() else 1)
    elif args.sync:
        sys.exit(0 if sync_to_xuntian() else 1)
    elif args.ingest:
        sys.exit(0 if run_ingest() else 1)
    else:
        parser.print_help()
