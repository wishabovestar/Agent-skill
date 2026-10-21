import json, os, re

BASE = r"D:/hermes/hermes-data/profiles/mybot/skills"
usage = json.load(open(os.path.join(BASE, ".usage.json"), encoding="utf-8"))

# curated semantic clusters by keyword matching against skill name/path/description
clusters = {
    "GitHub操作":      ["github", "gh ", "pr ", "pull request", "issues"],
    "PDF/OCR/文档":    ["pdf", "ocr", "docx", "scanned", "drawing", "engineering-drawing", "xlsx", "excel", "document"],
    "笔记/知识管理":   ["obsidian", "note", "knowledge", "wiki", "llm-wiki"],
    "LLM部署/推理":    ["llm", "vllm", "llama", "serving", "inference", "local-model", "local-llm", "deployment"],
    "音乐/音频":       ["music", "song", "audio", "audiocraft", "songwriting"],
    "设计/视觉/UI":    ["design", "sketch", "excalidraw", "p5js", "manim", "ui", "svg", "diagram", "creative"],
    "研究/论文":       ["research", "paper", "arxiv", "survey", "literature", "academic"],
    "邮件/通信":       ["email", "himalaya", "gmail", "teams", "meeting"],
    "编码Agent/CLI":   ["codex", "opencode", "claude-code", "coding agent", "cli"],
    "Agent集群/编排":  ["agent", "orchestrator", "dispatcher", "delegate", "multi-agent", "cluster"],
    "微信/QQ/平台连接": ["wechat", "weixin", "qq", "platform", "gateway", "connection"],
    "电池/热工/材料":  ["battery", "lithium", "electrode", "thermal", "k-value", "pre-lithiation", "cell"],
    "数据/图表":       ["data", "chart", "excel-data", "visualization", "generator"],
    "安全/审计":       ["security", "audit", "privacy", "credential", "sandbox", "redact"],
}

# collect all skill names on disk (recursive dirs + symlink names)
disk_skills = set()
for root, dirs, files in os.walk(BASE):
    parts = [p for p in root.split(os.sep) if p not in ("", ".")]
    if any(p.startswith(".") for p in parts):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        continue
    for d in list(dirs):
        if d.startswith("."):
            continue
        disk_skills.add(d)

def get_desc(name):
    for root, dirs, files in os.walk(BASE):
        parts = [p for p in root.split(os.sep) if p not in ("", ".")]
        if any(p.startswith(".") for p in parts):
            continue
        for d in list(dirs):
            if d == name:
                md = os.path.join(root, d, "SKILL.md")
                if os.path.exists(md):
                    try:
                        txt = open(md, encoding="utf-8", errors="replace").read(2000)
                        m = re.search(r"description:\s*[\"']?(.*?)[\"']?\n", txt)
                        if m:
                            return m.group(1)[:200]
                    except Exception:
                        pass
    return ""

print("=== SEMANTIC CLUSTER ANALYSIS (name/desc keyword match) ===\n")
for cname, kws in clusters.items():
    members = []
    for s in sorted(disk_skills):
        desc = get_desc(s).lower()
        blob = (s + " " + desc).lower()
        if any(k in blob for k in kws):
            u = usage.get(s, {})
            members.append((s, u.get("use_count", "?"), u.get("last_used_at", "never")[:10] if u.get("last_used_at") else "never"))
    if len(members) >= 2:
        print(f"[{cname}] ({len(members)} members)")
        for m in members:
            print(f"    {m[0]:40s} uses={m[1]:<5} last={m[2]}")
        print()
