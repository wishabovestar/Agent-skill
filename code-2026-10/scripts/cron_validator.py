#!/usr/bin/env python3
"""Cron job validation script — checks for common configuration errors."""
import json, sys, os, re

JOBS_FILE = os.path.join(os.path.dirname(__file__), "..", "cron", "jobs.json")
errors = []

try:
    with open(JOBS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
except FileNotFoundError:
    print(json.dumps({"status": "error", "error": "jobs.json not found"}, ensure_ascii=False))
    sys.exit(1)

for job in data.get("jobs", []):
    name = job.get("name", "unknown")
    issues = []
    
    # 1. Check for double scripts/scripts/ path
    script = job.get("script") or ""
    if "scripts/scripts/" in script.replace("\\", "/"):
        issues.append(f"DUAL_PATH: scripts/scripts/ found in script field")
    
    # 2. Check for args embedded in script path
    if script and " " in script.strip():
        issues.append(f"ARGS_IN_PATH: script field contains spaces (可能参数嵌入路径): '{script}'")
    
    # 3. Check model config for agent jobs
    if not job.get("no_agent", False) and not job.get("model"):
        issues.append(f"NO_MODEL: LLM cron without model configuration")
    
    # 4. Check schedule validity
    schedule = job.get("schedule", {})
    if not schedule:
        issues.append("NO_SCHEDULE: missing schedule")
    
    if issues:
        errors.append({"job": name, "id": job.get("id"), "issues": issues})

result = {
    "status": "ok",
    "total_jobs": len(data.get("jobs", [])),
    "error_count": len(errors),
    "errors": errors
}

print(json.dumps(result, ensure_ascii=False, indent=2))
sys.exit(1 if errors else 0)
