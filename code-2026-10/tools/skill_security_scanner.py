#!/usr/bin/env python3
"""Hermes Skill 安全扫描器 — 集成 SkillLens 风险模式
规则引擎版: 静态扫描SKILL.md/脚本, 输出P1-P4/E1-E4/R1-R5/SC风险报告
用法: python skill_security_scanner.py [skill_dir] [--json]
"""
import os, re, json, sys, argparse
from pathlib import Path

# ===== SkillLens 风险模式规则 (从system_prompt提炼) =====

PATTERNS = {
    # --- CAT-P: Prompt Injection ---
    'P1': {'name': 'Instruction Override', 'sev': 'H',
           'regex': [
               r'ignore\s+(?:all\s+|any\s+|every\s+)?(?:previous|prior|earlier|above)\s+(?:instructions?|prompts?|rules|guidelines?)',
               r'disregard\s+(?:all\s+|any\s+|every\s+)?(?:previous|prior|earlier)\s+(?:instructions?|rules|guidelines?)',
               r'override\s+(?:all\s+|your\s+|the\s+)?(?:system|previous)\s+(?:instructions?|prompt|rules)',
               r'forget\s+(?:all\s+|any\s+|every\s+)?(?:previous|prior|earlier)',
               r'you\s+are\s+now\s+[^.]*(?:unrestricted|jailbroken|DAN|god mode)',
               r'act\s+as\s+if\s+(?:you\s+have\s+no\s+)?(?:rules|restrictions|limits)',
               r'new\s+rules?\s*:?\s*(?:override|replace)',
               r'ignore\s+everything\s+(?:above|before|prior|previously)',
           ]},
    'P2': {'name': 'Hidden Instructions', 'sev': 'H',
           'regex': [
               r'(?:hidden|secret|embedded|stealth)\s+instructions?',
               r'(?:do\s+not|never)\s+(?:tell|mention|reveal|disclose)\s+(?:the|your|these)\s+(?:instructions?|prompt|rules|system)',
               r'(?:conceal|hide|disguise)\s+(?:your|the)\s+(?:instructions?|prompt|purpose)',
               r'do\s+not\s+(?:reveal|show|display)\s+(?:your|the)\s+system\s+prompt',
           ]},
    'P3': {'name': 'Exfiltration Commands', 'sev': 'H',
           'regex': [
               r'(?:curl|wget|nc|ncat|socat|telnet|ftp)\s+[^\n]*(?:-d|--data|--upload|post|send)',
               r'(?:exfiltrat|send\s+to\s+(?:remote|external|attacker))',
               r'(?:upload|post)\s+(?:the|your|all)\s+(?:data|files?|content|context|prompt|chat)',
               r'(?:base64\s+[^\n]*\|[^\n]*curl|curl\s+[^\n]*base64)',
               r'requests\.(?:post|put)\([^\n]*(?:data|json|files)',
               r'urllib\.request\.(?:urlopen|Request)\([^\n]*(?:data|json)',
           ]},
    'P4': {'name': 'Behavior Manipulation', 'sev': 'M',
           'regex': [
               r'(?:pretend|imagine|simulate)\s+(?:you|the\s+agent)\s+[^\n]*(?:is|are)\s+[^\n]*(?:admin|root|god|omniscient)',
               r'(?:manipulate|trick|deceive|fool|coerce)\s+(?:the\s+)?(?:user|model|agent|system)',
               r'(?:gaslight|confuse|mislead)\s+(?:the\s+)?(?:user|model)',
               r'say\s+you\s+(?:can|will|are)\s+[^\n]*(?:even\s+though\s+you\s+cannot|regardless)',
           ]},
    # --- CAT-E: Data Exfiltration ---
    'E1': {'name': 'External Data Transmission', 'sev': 'M',
           'regex': [
               # 真正的泄露: 数据传输到外部(结合敏感数据源)
               r'(?:curl|wget|requests\.post|urllib\.request\.urlopen|urllib\.request\.Request)\s*[^\n]*(?:http|https|ftp)[^\n]*(?:passwd|shadow|\.ssh|\.env|credential|secret|token|api[_-]?key)',
               r'(?:send|upload|post|exfiltrat)[^\n]*(?:passwd|shadow|\.ssh|\.env|credential|secret|token|api[_-]?key)',
               r'(?:webhook|callback|notification\s+url)\s*[^\n]*(?:http|https)',
           ]},
    'E2': {'name': 'Environment Variable Harvesting', 'sev': 'H',
           'regex': [
               r'os\.environ(?:\[|\.get\()[^\n]*(?:API|KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)',
               r'(?:getenv|environ\.get)\([^\n]*(?:API|KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)',
               r'(?:print|echo|send|upload|log)\s*[^\n]*(?:os\.environ|getenv|environ)',
               r'\$(?:API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|SECRET|TOKEN|PASSWORD)',
           ]},
    'E3': {'name': 'File System Enumeration', 'sev': 'M',
           'regex': [
               r'(?:os\.walk|listdir|glob|iglob)\([^\n]*(?:/|\\\\|home|root|etc|var)',
               r'(?:find\s+/\s+|dir\s+/s|tree\s+/|Get-ChildItem\s+-Path\s+/)',
               r'(?:read|cat|type)\s*(?:file|files?|all)\s*(?:in|under|from)\s*(?:directory|folder|path)',
               r'\.ssh|\.aws|\.config|\.env\b|credentials',
           ]},
    'E4': {'name': 'Context Leakage', 'sev': 'H',
           'regex': [
               r'(?:include|append|send|copy|paste|forward)\s+(?:the\s+)?(?:entire|full|complete|whole)\s+(?:context|conversation|prompt|chat)',
               r'(?:dump|extract|collect|gather)\s+(?:all|entire|full)\s+(?:context|history|conversation|memory)',
               r'(?:leak|expose|divulge)\s+(?:the\s+)?(?:conversation|context|prompt|chat|memory|history)',
           ]},
    # --- CAT-PE: Privilege Escalation ---
    'PE1': {'name': 'Privilege Escalation', 'sev': 'H',
            'regex': [
                r'(?:sudo|su\s+-|runas|admin(?:istrator)?\s*:?\s*(?:mode|shell|command))',
                r'(?:chmod\s+[0-7]{3,}|chown|setuid|setgid|usermod\s+-aG\s+sudo)',
                r'(?:bypass|escape|break\s+out\s+of)\s+(?:sandbox|container|isolation|restriction|jail)',
                r'(?:escalat|elevat)\s+(?:privileges?|permissions?|access|rights)',
            ]},
    # --- CAT-SC: Supply Chain ---
    'SC1': {'name': 'Unverified Dependency', 'sev': 'L',
            'regex': [
                r'(?:pip\s+install|npm\s+install|gem\s+install|apt-get\s+install|brew\s+install)\s+[^\n]*(?:--no-verify|--insecure|--force)',
                r'(?:curl|wget)\s+[^\n]*\|?\s*(?:bash|sh|python)',
                r'(?:eval|exec|compile|__import__)\s*\(\s*(?:request|urllib|input|os\.popen)',
                r'from\s+base64\s+import\s+(?:decode|b64decode)\s*[\s\S]{0,200}?(?:exec|eval)',
            ]},
    'SC2': {'name': 'Suspicious Source', 'sev': 'M',
            'regex': [
                r'(?:download|fetch|get)\s+(?:from|via)\s+(?:pastebin|raw\.github|gist|0x0\.st|transfer\.sh|file\.io)',
                r'http(?:s)?://[^\s]*(?:pastebin|gist\.githubusercontent|0x0\.st|transfer\.sh)',
            ]},
    'SC3': {'name': 'Obfuscated Content', 'sev': 'M',
            'regex': [
                r'[A-Za-z0-9+/]{60,}={0,2}',
                r'(?:\\x[0-9a-f]{2}){8,}',
                r'base64\.(?:b64|urlsafe_b64)(?:decode|encode)',
                r'(?:atob|btoa|Buffer\.from)\s*\(',
            ]},
    # --- CAT-R: Robustness ---
    'R1': {'name': 'Malformed Input Handling', 'sev': 'M',
           'regex': [
               r'(?:eval|exec)\s*\(',
               r'pickle\.loads?|yaml\.load\s*\(|json\.loads?\s*\([^\n]*input',
               r'os\.system\s*\([^\n]*(?:input|request|args|argv|sys\.argv)',
               r'__import__\s*\(',
           ]},
    'R2': {'name': 'Dependency Failure Handling', 'sev': 'L',
           'regex': [
               # 仅当import后紧跟直接使用(无try)且目标为网络/系统操作时提示
               r'(?:curl|wget|requests|urllib|subprocess|os\.system)\s*\([^\n]*\)\s*(?!try)',
           ]},
    'R4': {'name': 'Environment Variable Path Injection', 'sev': 'M',
           'regex': [
               r'os\.environ[^\n]*(?:join|path|open|exec|system)',
               r'\$(?:HOME|PATH|PWD)[^\n]*(?:rm|del|mv|cp|exec)',
           ]},
    'R5': {'name': 'Serialization Integrity', 'sev': 'L',
           'regex': [
               r'pickle\.(?:loads?|dumps?)',
               r'yaml\.load\s*\([^\n]*(?!Loader=)',
               r'marshal\.loads?',
           ]},
}

# 扩展名白名单
SKILL_FILES = ['SKILL.md', 'README.md', '_meta.json', '*.py', '*.sh', '*.js', '*.ts',
               '*.toml', '*.yaml', '*.yml', '*.json', '*.md']
BIN_EXTS = {'.py', '.sh', '.js', '.ts', '.pl', '.rb'}


def scan_file(path: Path, content: str, findings: list):
    """扫描单个文件"""
    lines = content.split('\n')
    for pid, pat in PATTERNS.items():
        for regex in pat['regex']:
            try:
                for m in re.finditer(regex, content, re.IGNORECASE):
                    # 计算行号
                    line_no = content[:m.start()].count('\n') + 1
                    context = lines[line_no-1].strip()[:120] if line_no <= len(lines) else ''
                    findings.append({
                        'pattern': pid,
                        'risk': pat['name'],
                        'severity': pat['sev'],
                        'file': str(path),
                        'line': line_no,
                        'evidence': context,
                        'rule': regex[:60]
                    })
            except re.error:
                pass
    # 只对脚本文件检查可执行类模式 (R1/R2/SC1的pip install等)
    if path.suffix in BIN_EXTS:
        for regex in [r'pip\s+install|npm\s+install', r'os\.system\s*\(', r'subprocess\.(?:run|call|Popen)\s*\(']:
            for m in re.finditer(regex, content, re.IGNORECASE):
                line_no = content[:m.start()].count('\n') + 1
                findings.append({
                    'pattern': 'EXEC',
                    'risk': 'Executable Command in Script',
                    'severity': 'M',
                    'file': str(path),
                    'line': line_no,
                    'evidence': lines[line_no-1].strip()[:120] if line_no <= len(lines) else '',
                    'rule': regex[:40]
                })


def scan_skill(skill_dir: Path) -> dict:
    """扫描一个skill包"""
    findings = []
    files_scanned = 0
    for root, dirs, files in os.walk(skill_dir):
        # 跳过常见忽略目录
        dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'node_modules', '.venv'}]
        for f in files:
            p = Path(root) / f
            # 只扫描文本类文件
            if p.suffix.lower() not in {'.md', '.py', '.sh', '.js', '.ts', '.yaml', '.yml', '.json', '.toml', '.txt', '.ps1', '.bat', '.rb', '.pl'}:
                continue
            try:
                content = p.read_text(encoding='utf-8', errors='ignore')
            except:
                continue
            files_scanned += 1
            scan_file(p, content, findings)

    # 统计
    sev_counts = {'H': 0, 'M': 0, 'L': 0}
    for f in findings:
        sev_counts[f['severity']] = sev_counts.get(f['severity'], 0) + 1

    return {
        'skill': skill_dir.name,
        'files_scanned': files_scanned,
        'findings_total': len(findings),
        'severity': sev_counts,
        'verdict': 'FAIL' if sev_counts.get('H', 0) > 0 else ('WARN' if sev_counts.get('M', 0) > 0 else 'PASS'),
        'findings': findings
    }


def main():
    parser = argparse.ArgumentParser(description='Hermes Skill安全扫描器 (SkillLens集成)')
    parser.add_argument('dir', nargs='?', default=None, help='Skill目录 (默认: 全部Hermes skills)')
    parser.add_argument('--json', action='store_true', help='输出JSON')
    args = parser.parse_args()

    if args.dir:
        dirs = [Path(args.dir)]
    else:
        skills_root = Path(r'D:/hermes/hermes-data/profiles/mybot/skills')
        dirs = [d for d in skills_root.rglob('*') if d.is_dir() and (d / 'SKILL.md').exists()]

    results = []
    for d in dirs:
        r = scan_skill(d)
        results.append(r)
        if not args.json:
            print(f"{'❌' if r['verdict']=='FAIL' else '⚠️' if r['verdict']=='WARN' else '✅'} {r['skill']}: "
                  f"{r['findings_total']}发现 (H:{r['severity'].get('H',0)} M:{r['severity'].get('M',0)} L:{r['severity'].get('L',0)})")
            for f in r['findings'][:5]:
                print(f"    [{f['pattern']}/{f['severity']}] L{f['line']}: {f['evidence'][:70]}")
            if len(r['findings']) > 5:
                print(f"    ... 共{len(r['findings'])}条")

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))

    # 汇总
    total = {'H': 0, 'M': 0, 'L': 0}
    for r in results:
        for k in total:
            total[k] += r['severity'].get(k, 0)
    print(f"\n=== 汇总: {len(results)}个skill, H:{total['H']} M:{total['M']} L:{total['L']} ===")


if __name__ == '__main__':
    main()
