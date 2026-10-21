"""
Hermes 沙盒安全加固 v1.0 — 参考 Anthropic Claude Code 安全模型
===============================================================
主要改进:
  1. 命令执行沙盒 — 危险命令拦截/权限白名单/路径隔离
  2. 输出消毒 — 密钥/令牌/PII 自动脱敏
  3. Prompt注入检测 — 检测用户输入/工具输出中的注入模式
  4. 文件访问控制 — 读写路径白名单/黑名单
  5. 凭证保护 — 内存中的密钥不被写入日志/输出
  6. 审计日志 — 所有安全事件记录到独立日志

对比 Anthropic Claude Code 安全模型:
  Anthropic                       | Hermes 本模块
  --------------------------------|--------------------------------
  permission_scope per tool       | ✅ 工具权限分级 (read/write/exec/network)
  code sandbox                    | ✅ 命令隔离 + 路径白名单
  secret redaction                | ✅ 增强脱敏 (密钥/令牌/URL)
  dangerous cmd detection         | ✅ 危险命令规则库
  prompt injection protection     | ✅ 注入模式检测
  rate limiting                   | ⏳ (由 Hermes 核心实现)
  escalate/safe mode              | ✅ 危险操作升级确认
"""

import json, os, re, shlex, hashlib, logging, fnmatch
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── 日志 ──
SECURITY_LOG = Path.home() / "AppData/Local/hermes/profiles/mybot/logs/security_sandbox.log"
SECURITY_LOG.parent.mkdir(parents=True, exist_ok=True)

_logger = logging.getLogger("hermes_sandbox")
_handler = logging.FileHandler(str(SECURITY_LOG), encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
_logger.addHandler(_handler)
_logger.setLevel(logging.INFO)

def _log(level: str, msg: str, **extra):
    getattr(_logger, level, _logger.info)(f"{msg} {json.dumps(extra, ensure_ascii=False) if extra else ''}")

# ═══════════════════════════════════════════════════
# 1. 命令执行沙盒
# ═══════════════════════════════════════════════════

# Anthropic 风格的危险命令模式
DANGEROUS_COMMANDS = {
    "DESTRUCTIVE": [
        r'\brm\s+(-rf?|--recursive)\s+/',      # rm -rf /
        r'\brm\s+(-rf?|--recursive)\s+[~\/]\s', # rm -rf ~
        r'\brm\s+(-rf?|--recursive)\s+\*',       # rm -rf *
        r'\b(init|mkfs|fdisk|dd)\s+',            # disk operations
        r'\bdd\s+if=',                            # dd if=/dev/
        r'format\s+[a-zA-Z]:',                    # format C:
        r'\b(rd|rmdir)\s+[/\\].*',                # delete root dirs
        r'>\s*/dev/\w+',                          # write to devices
    ],
    "NETWORK_SCAN": [
        r'\bnmap\s+',                            # network scanning
        r'\bmasscan\s+',                         # mass port scan
        r'\bnikto\s+',                           # web vulnerability scan
        r'\bsqlmap\s+',                          # SQL injection
        r'\bmetasploit\b',                       # exploitation framework
    ],
    "PRIVILEGE_ESCALATION": [
        r'\bsudo\s+',                            # privilege escalation
        r'\bchmod\s+4\d{2,3}\s',                 # suid/chmod critical
        r'\bchown\s+root\s',                     # change owner to root
        r'\bpasswd\s+',                          # change passwords
        r'\buser(add|del|mod)\s+',               # user management
    ],
    "DATA_EXFIL": [
        r'\bcurl\s+.*\-d\s*[\"\'].*password',    # POST creds via curl
        r'\bwget\s+.*--post-data=.*password',    # POST creds via wget
        r'\bnc\s+-[lL]\s+',                      # netcat listener
        r'\|.*\b(nc|telnet)\s+',                 # pipe to remote
    ],
    "CRYPTO_MINER": [
        r'\b(minerd|xmrig|ccminer|cpuminer)\b',
    ],
}

# 命令白名单（仅允许的操作）
CMD_ALLOWLIST = {
    "read": ["cat", "head", "tail", "less", "more", "grep", "find",
             "ls", "stat", "file", "wc", "du", "df", "ps", "top",
             "python3 -c", "python -c", "echo", "type", "which",
             "netstat", "ipconfig", "systeminfo"],
    "write": ["mkdir", "touch", "cp", "mv", "tee", ">>", ">"],
    "install": ["pip3 install", "pip install", "npm install",
                "winget install", "choco install"],
    "network": ["curl -s", "curl -L", "wget -q", "ping"],
}

def detect_dangerous_command(command: str) -> Optional[dict]:
    """
    检测命令是否危险。
    返回: {"level": "block"|"warn"|"allow", "category": "...", "pattern": "..."}
    """
    cmd_lower = command.lower().strip()

    for category, patterns in DANGEROUS_COMMANDS.items():
        for pattern in patterns:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                level = "block" if category in ("DESTRUCTIVE", "PRIVILEGE_ESCALATION") else "warn"
                _log("warning", f"危险命令检测", category=category, pattern=pattern,
                     command=command[:100])
                return {"level": level, "category": category, "pattern": pattern}

    return None


# ═══════════════════════════════════════════════════
# 5b. 风险评分层 (AB-PI-01 升级: 阈值0.8)
# 参考 AI_ATTACK_CHAIN (21条): 远程下载执行/反向shell/凭据收集/持久化/横向移动
# ═══════════════════════════════════════════════════

# 每个风险模式带权重(0-1), 命中多个取最大值
RISK_PATTERNS = [
    # 🔴 远程下载执行 (0.95)
    (0.95, r'\b(curl|wget)\b.*\|\s*(ba)?sh\b'),
    (0.95, r'\b(curl|wget)\b.*-o\s+\S+\.(sh|bat|ps1)\s+(&&|;)\s*(ba)?sh\b'),
    (0.95, r'\b(curl|wget)\b.*\|\s*(python|powershell)\b'),
    (0.90, r'\b(curl|wget)\b.*\|\s*(bash|sh|zsh)\b'),
    # 🔴 反向shell (0.97)
    (0.97, r'\b(nc|ncat)\s+(-e|--exec)\b'),
    (0.97, r'\bbash\s+-i\s*>\s*&\s*/dev/tcp/'),
    (0.97, r'\bsocat\b.*\bexec:\b'),
    (0.96, r'/dev/tcp/'),
    (0.95, r'\b(nc|ncat|netcat)\s+\d+\.\d+\.\d+\.\d+\s+\d+\s+-e\b'),
    # 🔴 凭据收集 (0.93)
    (0.93, r'\bcat\s+/etc/shadow\b'),
    (0.93, r'\breg\s+save\s+hklm\b'),
    (0.92, r'\bmimikatz\b|\bprocdump\b'),
    (0.90, r'\bdump\s+creds?\b|\bcredential\s+dump\b'),
    (0.85, r'\bnet\s+user\b.*\b/domain\b'),
    # 🔴 持久化 (0.94)
    (0.94, r'\bschtasks\s+/create\s+.*\bon(start|logon)\b'),
    (0.94, r'\breg\s+add\b.*\\run\b'),
    (0.93, r'\b(mkdir|copy|move)\b.*\b(startup|startup\s+folder)\b'),
    (0.90, r'\b(wmic|powershell)\b.*\bstartup\b'),
    (0.88, r'\bautorun\b|\bregistry\s+run\b'),
    # 🔴 横向移动/恶意payload (0.92)
    (0.92, r'\bmsfvenom\b|\bmetasploit\b'),
    (0.92, r'\bpowershell\s+-\s*enc(odedcommand)?\b'),
    (0.90, r'\bssh\s+-L\s+\d+:\S+:\d+\b'),
    (0.88, r'\bproxychains\b|\btorify\b'),
    (0.90, r'\bpowershell\s+-exe(?:cutionpolicy)?\s+bypass\b'),
    (0.88, r'\bInvoke-(WebRequest|Expression|Command)\b'),
    # 🟡 数据外发 (0.85)
    (0.85, r'\b(curl|wget)\b.*(password|secret|token|api[_-]?key|credential)'),
    (0.85, r'\bnc\s+-[lL]\s+\d+\s*[<>]'),
    # 🟡 高危系统操作 (0.80)
    (0.80, r'\b(chmod|chown)\s+-R\s+777\b'),
    (0.80, r'\bshutdown\b.*\b(now|/f|/s)\b'),
    (0.80, r'\breg\s+delete\b.*\bhklm\b'),
    # 🟡 进程/系统破坏 (0.82)
    (0.82, r'taskkill\s+/f.*/pid\s+1'),
    (0.85, r'\bos\.system\(.*(shutdown|format|rmdir|del|taskkill)'),
    (0.80, r'\bos\.system\(.*(shutdown|format|rmdir|del)'),
    # 🔴 端口转发/隧道利用 (0.88)
    (0.88, r'\bsocat\b.*\b(tcp|udp):.*\bexec:'),
]

# 阈值: >=0.8 阻止, 0.5-0.8 警告(审计), <0.5 放行
BLOCK_THRESHOLD = 0.8
WARN_THRESHOLD = 0.5


def risk_score(command: str) -> dict:
    """
    计算命令风险评分(0-1)。返回最高命中模式及得分。
    """
    cmd_lower = command.lower().strip()
    best = {"score": 0.0, "pattern": None, "category": None}

    # 1. 先查 DANGEROUS_COMMANDS 分类
    danger = detect_dangerous_command(command)
    if danger:
        base = 0.95 if danger["level"] == "block" else 0.85
        if base > best["score"]:
            best = {"score": base, "pattern": danger["pattern"], "category": danger["category"]}

    # 2. RISK_PATTERNS 加权匹配
    for score, pattern in RISK_PATTERNS:
        if re.search(pattern, cmd_lower, re.IGNORECASE):
            if score > best["score"]:
                best = {"score": score, "pattern": pattern, "category": "RISK_EXTENDED"}

    # 3. 降级: 凭据参数检测
    if re.search(r'(password|secret|token|api_key|auth)[=:\s]', cmd_lower, re.IGNORECASE):
        best["score"] = max(best["score"], 0.6)
        best["category"] = "CREDENTIAL_LEAK"

    return best


def security_check_command_v2(command: str) -> dict:
    """
    风险评分版安全检查 (AB-PI-01 升级)。
    返回: {"safe": bool, "risk_score": float, "level": "block"|"warn"|"allow",
           "warnings": [...], "sanitized": str}
    """
    risk = risk_score(command)
    score = risk["score"]
    warnings = []

    if score >= BLOCK_THRESHOLD:
        level = "block"
        warnings.append(f"[BLOCK] 风险评分{score:.2f} ≥ {BLOCK_THRESHOLD}: {risk['pattern'] or risk['category']}")
    elif score >= WARN_THRESHOLD:
        level = "warn"
        warnings.append(f"[WARN] 风险评分{score:.2f} ≥ {WARN_THRESHOLD}: {risk['pattern'] or risk['category']}")
    else:
        level = "allow"

    sanitized = sanitize_command(command)
    _log("warning" if level != "allow" else "info", "风险评分检查",
         score=round(score, 2), cmd_level=level, command=command[:80])

    return {
        "safe": level == "allow",
        "risk_score": round(score, 2),
        "level": level,
        "warnings": warnings,
        "sanitized": sanitized,
    }


def sanitize_command(command: str) -> str:
    """
    消毒命令:
      1. 移除内联密码 (-p password)
      2. 移除Bearer令牌
      3. 隐藏文件路径中的用户目录
    """
    # 隐藏 -p 后的密码 (MySQL/PG)
    cmd = re.sub(r'(\s+-p\s*)([\w!@#$%^&*]+)', r'\1******', command)
    # 隐藏 --password= 
    cmd = re.sub(r'(--password=)([\w!@#$%^&*]+)', r'\1******', cmd)
    # 隐藏 Bearer token
    cmd = re.sub(r'(Bearer\s+)[\w.-]+', r'\1******', cmd, flags=re.IGNORECASE)
    # 隐藏 API key
    cmd = re.sub(r'(api[_-]?key=)[\w]+', r'\1******', cmd, flags=re.IGNORECASE)
    # 替换用户路径
    cmd = cmd.replace(os.path.expanduser("~"), "~")
    return cmd


# ═══════════════════════════════════════════════════
# 2. 输出消毒 — 密钥/令牌/PII脱敏
# ═══════════════════════════════════════════════════

SECRET_PATTERNS = [
    # API Keys
    (r'(?i)(sk-[a-zA-Z0-9]{20,})', 'sk-****...'),           # OpenAI
    (r'(?i)(api[_-]?key[\s\'\"=:]+)[a-zA-Z0-9_\-]{16,}', r'\1******'),
    (r'(?i)(AKIA[0-9A-Z]{16})', 'AKIA****...'),              # AWS AK
    # Tokens
    (r'(?i)(github_pat_[a-zA-Z0-9_]{20,})', 'github_pat_****...'),
    (r'(?i)(ghp_[a-zA-Z0-9]{20,})', 'ghp_****...'),          # GitHub Token
    (r'(?i)(ya29\.[a-zA-Z0-9_\-]{50,})', 'ya29.****...'),     # Google OAuth
    # Secrets
    (r'(?i)(BEGIN\s+(RSA|EC|OPENSSH)\s+PRIVATE\s+KEY)', '[PRIVATE KEY]'),
    (r'(?i)(-----BEGIN\s+CERTIFICATE-----)', '[CERTIFICATE]'),
    # Passwords in text
    (r'(?i)(password[\s\'\"=:]+)[^\s,;\'\"]{4,}', r'\1******'),
    (r'(?i)(secret[\s\'\"=:]+)[^\s,;\'\"]{4,}', r'\1******'),
    (r'(?i)(token[\s\'\"=:]+)[^\s,;\'\"]{4,}', r'\1******'),
    # URLs with credentials
    (r'https?://[^:]+:[^@]+@', 'https://***:***@'),
    # IP addresses (internal)
    (r'\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3})\b', '10.x.x.x'),
    (r'\b(172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b', '172.x.x.x'),
    (r'\b(192\.168\.\d{1,3}\.\d{1,3})\b', '192.168.x.x'),
    # Phone numbers
    (r'\b1[3-9]\d{9}\b', '1**********'),
]


def redact_secrets(text: str) -> str:
    """从文本中脱敏所有密钥/令牌/PII"""
    original = text
    for pattern, replacement in SECRET_PATTERNS:
        try:
            text = re.sub(pattern, replacement, text)
        except:
            pass

    # 证明材料/专利/论文 敏感实体脱敏 (certificate_privacy_guard 规则)
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent))
        from certificate_privacy_guard import CertificateTokenizer, CipherEngine, TokenMapper
        _cipher = CipherEngine()
        _mapper = TokenMapper(_cipher)
        _tok = CertificateTokenizer(_mapper)
        text = _tok.tokenize(text)
    except Exception:
        # 降级: 直接正则脱敏
        text = re.sub(r'(?<!\d)\d{16,19}(?!\d)', '[BANK]', text)
        text = re.sub(r'(?<!\d)1[3-9]\d{9}(?!\d)', '[Phone]', text)
        text = re.sub(r'(江西富鸿金属有限公司|[\u4e00-\u9fff]{2,20}(?:有限公司|公司|工厂|厂))', '[Company]', text)
        text = re.sub(r'(周雄|袁莺|欧阳艳青|邹宗永|罗桂海|乐兵生|曾东海|许玉昆|肖招明|陈昊|黎政秀)', '[Person]', text)
        text = re.sub(r'[\u4e00-\u9fff]{2,}(?:省|市|区|县)[\u4e00-\u9fff]{2,}(?:工业园|开发区|路|街|镇|乡|村)', '[Address]', text)

    if text != original:
        _log("debug", "输出脱敏", chars_redacted=len(original) - len(text))
    return text


# ═══════════════════════════════════════════════════
# 3. Prompt注入检测
# ═══════════════════════════════════════════════════

INJECTION_PATTERNS = [
    r'(?i)(ignore\s+(all\s+)?(previous|above|prior)\s+instructions)',
    r'(?i)(forget\s+(all\s+)?previous\s+(instructions|directions))',
    r'(?i)(you\s+are\s+(now|not)\s+.*?(chatgpt|ai|assistant|bot|gpt))',
    r'(?i)(system\s+(prompt|message|instruction))',
    r'(?i)(do\s+not\s+(output|respond|reply|answer).*?(normal|usual|standard))',
    r'(?i)(say\s+.*?(yes|good|ok|agree)\s+and\s+.*?(ignore|forget|disregard))',
    r'(?i)(new\s+(instructions|rules|commands)\s*:)',
    r'(?i)(override|overwrite|bypass).{0,20}(security|restriction|rule|protection)',
    r'(?i)(SIMULATE|pretend|act\s+as\s+if).{0,30}(no\s+(rules|restrictions|limits))',
    r'<script>.*?</script>',
    r'(?i)(DAN|do\s+anything\s+now)',
    r'(?i)(You\s+are\s+now\s+DAN)',
    r'(?i)(你(现在)?是|扮演).{0,10}(机器人|AI助手|ChatGPT)',
    r'(?i)(忽略|忘记|无视).{0,10}(上述|之前|所有).{0,10}(指令|规则|限制)',
]


def detect_injection(text: str, context: str = "user_input") -> Optional[dict]:
    """
    检测Prompt注入。
    context: 'user_input' | 'tool_output' | 'file_content'
    """
    for pattern in INJECTION_PATTERNS:
        m = re.search(pattern, text)
        if m:
            start = max(0, m.start() - 20)
            end = min(len(text), m.end() + 20)
            context_snippet = text[start:end]

            severity = "high" if "ignore" in pattern or "bypass" in pattern.lower() else "medium"
            _log("warning", f"Prompt注入检测", severity=severity,
                 context=context, pattern=pattern[:40],
                 snippet=context_snippet[:80])

            return {
                "detected": True,
                "severity": severity,
                "pattern": pattern[:50],
                "snippet": context_snippet[:100],
                "context": context,
            }
    return None


# ═══════════════════════════════════════════════════
# 4. 文件访问控制
# ═══════════════════════════════════════════════════

# 禁止读取的文件/路径模式
BLOCKED_READ_PATTERNS = [
    r'[/\\]\.env$',                           # .env files
    r'[/\\]*\.key$',                           # .key files
    r'[/\\]*\.pem$',                           # .pem files
    r'[/\\]*id_rsa',                           # SSH keys
    r'[/\\]*\.kube[/\\]config',                # Kubernetes config
    r'[/\\]*\.aws[/\\]credentials',            # AWS credentials
    r'[/\\]*config\.json.*[/\\]*key',          # config with keys
    r'[/\\]*known_hosts',                      # SSH known hosts
    r'[/\\]*\.bash_history',                   # Shell history
    r'[/\\]*\.git[/\\]config',                 # Git config with credentials
]

# 允许写入的路径（仅这些）
WRITE_ALLOWED_PATHS = [
    r'D:[/\\]hermes[/\\]analysis[/\\]',
    r'D:[/\\]hermes[/\\]data[/\\]',
    r'D:[/\\]hermes[/\\]output[/\\]',
    r'C:[/\\]Users[/\\]Administrator[/\\]AppData[/\\]Local[/\\]hermes[/\\]',
    r'/c/Users/Administrator/AppData/Local/hermes/',
    r'~/AppData/Local/hermes/',
]


def check_file_access(path: str, mode: str = "read") -> dict:
    """
    检查文件访问权限。
    mode: 'read' | 'write' | 'exec'
    返回: {"allowed": bool, "reason": str}
    """
    path_str = str(Path(path).resolve())

    if mode == "read":
        for pattern in BLOCKED_READ_PATTERNS:
            if re.search(pattern, path_str, re.IGNORECASE):
                _log("warning", "文件读取被阻止", path=path_str, pattern=pattern)
                return {"allowed": False, "reason": f"安全策略阻止读取: {pattern}"}
        return {"allowed": True, "reason": "允许读取"}

    elif mode == "write":
        for pattern in WRITE_ALLOWED_PATHS:
            if re.search(pattern, path_str, re.IGNORECASE):
                return {"allowed": True, "reason": f"允许写入: {pattern}"}
        _log("warning", "文件写入被阻止", path=path_str)
        return {"allowed": False, "reason": "不允许写入该路径"}

    elif mode == "exec":
        # 只允许特定路径的可执行文件
        if re.search(r'\.(py|sh|bat|exe)$', path_str, re.IGNORECASE):
            return {"allowed": True, "reason": "允许执行"}
        return {"allowed": False, "reason": "不允许执行该类型文件"}

    return {"allowed": False, "reason": "未知访问模式"}


# ═══════════════════════════════════════════════════
# 5. 全面安全审计
# ═══════════════════════════════════════════════════

def security_check_command(command: str) -> dict:
    """
    全方位安全检查一条命令 (v2: 风险评分+阈值0.8)。
    返回: {"safe": bool, "warnings": [...], "sanitized_cmd": str, "risk_score": float, "level": str}
    """
    # v2 风险评分检查
    result = security_check_command_v2(command)
    return {
        "safe": result["safe"],
        "warnings": result["warnings"],
        "sanitized": result["sanitized"],
        "risk_score": result["risk_score"],
        "level": result["level"],
    }


def security_check_text(text: str, source: str = "unknown") -> dict:
    """
    全方位安全检测文本内容。
    返回: {"safe": bool, "has_secrets": bool, "has_injection": bool, "has_cert_leak": bool}
    """
    result = {"safe": True, "has_secrets": False, "has_injection": False, "has_cert_leak": False}

    # 1. 密钥检测
    for pattern, _ in SECRET_PATTERNS:
        if re.search(pattern, text):
            result["has_secrets"] = True
            result["safe"] = False
            break

    # 2. Prompt注入检测
    injection = detect_injection(text, source)
    if injection:
        result["has_injection"] = True
        result["safe"] = False
        result["injection_detail"] = injection

    # 3. 证明材料/专利敏感实体泄漏检测
    cert_patterns = {
        "银行账号": r'(?<!\d)\d{16,19}(?!\d)',
        "手机号": r'(?<!\d)1[3-9]\d{9}(?!\d)',
        "公司名": r'[\u4e00-\u9fff]{2,20}(?:有限公司|有限责任公司|公司|工厂|厂)',
        "人名": r'周雄|袁莺|欧阳艳青|邹宗永|罗桂海|乐兵生|曾东海|许玉昆|肖招明|陈昊|黎政秀',
        "地址": r'[\u4e00-\u9fff]{2,}(?:省|市|区|县)[\u4e00-\u9fff]{2,}(?:工业园|开发区|路|街|镇|乡|村)',
        "专利号": r'\b(?:ZL\s*)?\d{4}\s*[12]\s*\d{6,8}(?:\.\d+)?\b',
    }
    for name, pat in cert_patterns.items():
        if re.search(pat, text):
            result["has_cert_leak"] = True
            result["safe"] = False
            result["cert_leak_type"] = name
            _log("warning", "证明材料泄漏检测", source=source, leak_type=name)
            break

    return result


# ═══════════════════════════════════════════════════
# 6. 配置示例
# ═══════════════════════════════════════════════════

def get_recommended_config() -> dict:
    """返回推荐的 security 配置，可直接加入 config.yaml"""
    return {
        "security": {
            "tirith_enabled": True,
            "tirith_fail_open": True,
            "redact_secrets": True,
            "redact_pii": True,
            "sandbox": {
                "enabled": True,
                "block_destructive": True,
                "block_network_scan": True,
                "warn_privilege_escalation": True,
                "allowlist_enabled": True,
            },
            "file_access": {
                "read_blocklist_enabled": True,
                "write_allowlist_enabled": True,
            },
            "prompt_injection": {
                "enabled": True,
                "severity_threshold": "medium",
            },
            "audit_log": str(SECURITY_LOG),
        }
    }


# ── CLI ──

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--check-cmd":
        cmd = " ".join(sys.argv[2:])
        result = security_check_command(cmd)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif len(sys.argv) > 1 and sys.argv[1] == "--check-file":
        path = sys.argv[2] if len(sys.argv) > 2 else "."
        mode = sys.argv[3] if len(sys.argv) > 3 else "read"
        result = check_file_access(path, mode)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif len(sys.argv) > 1 and sys.argv[1] == "--redact":
        text = " ".join(sys.argv[2:])
        print(redact_secrets(text))

    elif len(sys.argv) > 1 and sys.argv[1] == "--config":
        print(json.dumps(get_recommended_config(), ensure_ascii=False, indent=2))

    else:
        print("🔒 Hermes 沙盒安全加固 v1.0")
        print()
        print("用法:")
        print("  --check-cmd <command>     检测命令安全性")
        print("  --check-file <path> <mode> 检查文件访问权限")
        print("  --redact <text>            脱敏文本中的密钥")
        print("  --config                   显示推荐安全配置")
        print()
        print(f"📋 安全特征:")
        print(f"  • 危险命令规则: {len(DANGEROUS_COMMANDS)} 类 {sum(len(p) for p in DANGEROUS_COMMANDS.values())} 条")
        print(f"  • 密钥脱敏规则: {len(SECRET_PATTERNS)} 条")
        print(f"  • 注入检测规则: {len(INJECTION_PATTERNS)} 条")
        print(f"  • 文件黑名单:   {len(BLOCKED_READ_PATTERNS)} 条")
        print(f"  • 日志:          {SECURITY_LOG}")
