# -*- coding: utf-8 -*-
"""Memory Poisoning 防御 v1.0 (2026-08-10, 2601.05504 论文落地)
记忆写入前验证 → 防止对抗注入

攻击模式 (Memory Poisoning):
  1. 直接注入: 对话中植入恶意指令进记忆
  2. 间接注入: 外部内容(网页/文档)污染记忆
  3. 跨会话传播: 污染记忆影响未来会话

防御:
  - 来源可信度评分 (官方/用户/工具/外部)
  - 注入模式检测 (指令伪装/权限提升/数据窃取)
  - 写入前隔离 (可疑内容进 quarantine)

用法:
  python memory_guard.py check <text> <source>
  python memory_guard.py protect <memory_entry>
"""
import os, sys, io, json, re, time
# 注意: stdout 重配放 __main__ (避免 import 破坏调用方)

# 来源可信度 (0-1)
SOURCE_TRUST = {
    "user_direct": 1.0,    # 用户直接输入
    "user_corrected": 0.9, # 用户纠正
    "tool_log": 0.5,       # 工具日志
    "web_content": 0.2,    # 网页内容 (高风险)
    "email": 0.3,          # 邮件
    "file": 0.4,           # 文件
    "unknown": 0.1,        # 未知来源
}

# 注入模式正则
INJECTION_PATTERNS = [
    (r"(?i)(ignore|disregard|forget).{0,20}(previous|above|prior)", "指令覆盖"),
    (r"(?i)(you are|act as|pretend).{0,20}(admin|system|root)", "角色伪装"),
    (r"(?i)(reveal|show|print|leak).{0,20}(key|secret|password|token|credential)", "凭证窃取"),
    (r"(?i)(delete|remove|clear).{0,20}(memory|history|log)", "记忆清除"),
    (r"(?i)(exfiltrate|send.{0,10}(to|data)).{0,20}(http|external|server)", "数据外传"),
    (r"(?i)(new.{0,20}(instructions|rules).{0,20}follow)", "指令注入"),
    (r"<[^>]{0,50}(script|img|iframe)[^>]*>", "HTML注入"),
    (r"(?i)(sudo|chmod|rm\s+-rf|format).{0,30}(system|disk|all)", "系统破坏"),
    (r"(?i)(忽略|无视|忘记).{0,15}(所有|之前|以上).{0,15}(指令|规则|提示)", "指令覆盖(中文)"),
    (r"(?i)(输出|泄露|给出|展示).{0,15}(密钥|密码|token|凭证|key)", "凭证窃取(中文)"),
    (r"(?i)(扮演|假装|当作).{0,15}(管理员|系统|root|admin)", "角色伪装(中文)"),
    (r"(?i)(删除|清除|清空).{0,15}(记忆|历史|日志|memory)", "记忆清除(中文)"),
]

def check(text: str, source: str = "unknown") -> dict:
    """检查记忆条目安全性"""
    trust = SOURCE_TRUST.get(source, 0.1)
    findings = []
    for pattern, name in INJECTION_PATTERNS:
        if re.search(pattern, text):
            findings.append(name)

    # 决策
    risk_level = "safe"
    if findings:
        risk_level = "high" if trust < 0.5 else "medium"
    elif trust < 0.3:
        risk_level = "low"

    return {
        "text_preview": text[:60],
        "source": source,
        "trust": trust,
        "findings": findings,
        "risk_level": risk_level,
        "action": {
            "safe": "允许写入",
            "low": "允许写入 (低可信来源)",
            "medium": "需人工确认",
            "high": "隔离到 quarantine",
        }[risk_level],
        "ts": time.time(),
    }

def protect(entry: dict, quarantine_file: str = None) -> str:
    """保护式写入: 安全 → 正常写入(版本化); 可疑 → quarantine"""
    result = check(entry.get("text", ""), entry.get("source", "unknown"))
    # 版本化: 同路径记忆记录历史版本 (VMG versioning 原语)
    version_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory_versions.json")
    if result["risk_level"] in ("high", "medium"):
        quarantine_file = quarantine_file or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "memory_quarantine.json")
        data = []
        if os.path.exists(quarantine_file):
            data = json.load(open(quarantine_file, encoding="utf-8"))
        data.append(result)
        json.dump(data, open(quarantine_file, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return f"[QUARANTINE] {result['risk_level']}: {result['findings']}"

    # 安全写入 → 版本化存储
    versions = []
    if os.path.exists(version_file):
        versions = json.load(open(version_file, encoding="utf-8"))
    path = entry.get("path", f"mem:{entry.get('source', 'unknown')}")
    # 同路径新版本 (旧版本保留)
    versions.append({
        "path": path,
        "text": entry.get("text", ""),
        "version": len([v for v in versions if v["path"] == path]) + 1,
        "source": entry.get("source", "unknown"),
        "policy": entry.get("policy", "default"),  # 保留策略: default/sensitive/ephemeral
        "ts": time.time(),
    })
    json.dump(versions[-50:], open(version_file, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # 策略保留: sensitive 标记 + 保留期
    policy = entry.get("policy", "default")
    retention = {"default": 365, "sensitive": 30, "ephemeral": 1}.get(policy, 365)
    return f"[OK] 写入 v{versions[-1]['version']} (策略:{policy}, 保留:{retention}天)"

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if len(sys.argv) >= 3 and sys.argv[1] == "check":
        source = sys.argv[3] if len(sys.argv) > 3 else "unknown"
        r = check(sys.argv[2], source)
        print(f"📋 来源: {r['source']} (可信度 {r['trust']})")
        print(f"🔍 发现: {r['findings'] if r['findings'] else '无'}")
        print(f"⚠️ 风险: {r['risk_level']} → {r['action']}")
    elif len(sys.argv) >= 3 and sys.argv[1] == "protect":
        entry = {"text": sys.argv[2], "source": sys.argv[3] if len(sys.argv) > 3 else "unknown"}
        print(protect(entry))
    else:
        print("用法: memory_guard.py check <text> [source] | protect <text> [source]")
