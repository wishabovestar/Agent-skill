"""
巡天情报搜集器 — 专项采集
目标: Anthropic泄露代码 / Tata-Apple供应链信息
模式: 持续监控网络变化 → 本地存档 → 去重归档
"""
import json, os, re, time, hashlib
from pathlib import Path
from datetime import datetime

INTEL_DIR = Path("D:/hermes/data/intel")
ARCHIVE_LOG = INTEL_DIR / "logs" / "collection_log.json"

TARGETS = {
    "anthropic_leak": {
        "label": "Anthropic泄露代码",
        "dir": INTEL_DIR / "anthropic_code",
        "keywords": [
            "Anthropic Mythos leak", "Anthropic Oceanus code", 
            "Anthropic leaked model weights", "Claude code leak",
            "Anthropic API proxy leak", "Mythos model weights download"
        ],
        "sources": ["github", "twitter", "reddit", "telegram", "hackernews"]
    },
    "tata_apple": {
        "label": "Tata-Apple供应链信息 + Apple机密诉讼",
        "dir": INTEL_DIR / "tata_apple",
        "keywords": [
            "Tata Apple supply chain leak", "Tata Electronics Apple",
            "Apple supplier Tata leak", "Tata Apple drawing", 
            "Tata Apple pricing BOM", "印度 Tata Apple 供应链",
            "Tata iPhone manufacturing leak",
            "Apple OpenAI trade secret lawsuit", "Apple OpenAI discovery",
            "Apple trade secret openai", "苹果 OpenAI 诉讼 机密"
        ],
        "sources": ["github", "twitter", "reddit", "telegram", "hackernews"]
    }
}

def init():
    for target in TARGETS.values():
        target["dir"].mkdir(parents=True, exist_ok=True)
    if not ARCHIVE_LOG.exists():
        with open(ARCHIVE_LOG, "w") as f:
            json.dump({"collections": [], "last_run": None}, f, indent=2)
    print(f"✅ Intel collection system ready")
    print(f"   Storage: {INTEL_DIR}")

def record_finding(source, target_name, title, url, content_preview="", file_path=""):
    """Record a discovered finding"""
    record = {
        "id": hashlib.md5(f"{source}{url}".encode()).hexdigest()[:12],
        "source": source,
        "target": target_name,
        "title": title[:200],
        "url": url,
        "content_preview": content_preview[:500],
        "file_path": str(file_path),
        "found_at": datetime.now().isoformat(),
    }
    # Load existing log
    with open(ARCHIVE_LOG, "r") as f:
        log = json.load(f)
    # Deduplicate
    existing_ids = {r["id"] for r in log["collections"]}
    if record["id"] not in existing_ids:
        log["collections"].append(record)
        log["last_run"] = datetime.now().isoformat()
        with open(ARCHIVE_LOG, "w") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
        print(f"  📥 New: [{target_name}] {title[:60]}")
        return True
    return False

def save_content(target_name, filename, content):
    """Save raw content to local storage"""
    target_info = TARGETS.get(target_name)
    if not target_info:
        return None
    target_dir = target_info["dir"]
    safe_name = re.sub(r'[\/:*?"<>|]', '_', filename)[:100]
    path = target_dir / safe_name
    with open(path, "w", encoding="utf-8", errors="replace") as f:
        f.write(content)
    return path

def status():
    """Show collection status"""
    with open(ARCHIVE_LOG, "r") as f:
        log = json.load(f)
    stats = {}
    for t in ["anthropic_leak", "tata_apple"]:
        count = sum(1 for r in log["collections"] if r.get("target") == t)
        stats[t] = count
    return {
        "total_findings": len(log["collections"]),
        "by_target": stats,
        "last_run": log.get("last_run"),
        "anthropic_files": len(list((INTEL_DIR/"anthropic_code").glob("*"))),
        "tata_files": len(list((INTEL_DIR/"tata_apple").glob("*"))),
    }

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "init":
        init()
    elif cmd == "status":
        s = status()
        print(f"Intel Collection Status: {json.dumps(s, indent=2)}")
    elif cmd == "record":
        src = sys.argv[2] if len(sys.argv) > 2 else "manual"
        tgt = sys.argv[3] if len(sys.argv) > 3 else "anthropic_leak"
        title = sys.argv[4] if len(sys.argv) > 4 else "unknown"
        url = sys.argv[5] if len(sys.argv) > 5 else ""
        record_finding(src, tgt, title, url)
