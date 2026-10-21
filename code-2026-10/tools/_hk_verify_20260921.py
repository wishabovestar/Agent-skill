# -*- coding: utf-8 -*-
"""P0 闭环验证: 记忆用量 / 技能恢复 / registry / .bak 归档 / 路径-文档一致性"""
import json, io, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
P = r"D:/hermes/hermes-data/profiles/mybot/skills"
A = r"C:/Users/Administrator/.agents/skills"
ok = lambda b: "PASS" if b else "FAIL"

print("== 1. 记忆用量 ==")
t = open(r"D:/hermes/hermes-data/profiles/mybot/memories/MEMORY.md", encoding="utf-8").read()
n = len(t.rstrip("\n"))
print(f"  MEMORY {n}/2200 = {100.0*n/2200:.1f}%  (审计前 2171 = 98.7%)  {ok(n <= 1870)} ≤85%目标")
print(f"  含 '+Hermes gateway' 拼接污染: {'YES-FAIL' if 'dump+Hermes' in t else 'NO-PASS'}")
u = open(r"D:/hermes/hermes-data/profiles/mybot/memories/USER.md", encoding="utf-8").read()
print(f"  USER {len(u.rstrip(chr(10)))}/1375 = {100.0*len(u.rstrip(chr(10)))/1375:.1f}%")
print(f"  §块数={t.count('§')+1}  记忆引用技能:")
for name in ("lsa-hi-sparse-attention", "attention-ab-validation", "vps-remote-management"):
    hit = [os.path.join(r, name) for r, d, f in os.walk(P)
           if os.path.basename(r) == name and "SKILL.md" in f
           and not any(x.startswith(".") for x in os.path.relpath(r, P).split(os.sep))]
    print(f"    {name:28s} active={bool(hit)} {ok(bool(hit))}")

print("\n== 2. usage.json registry ==")
uu = json.load(open(os.path.join(P, ".usage.json"), encoding="utf-8"))
for name in ("attention-ab-validation", "vps-remote-management"):
    e = uu[name]
    print(f"  {name:28s} state={e['state']} pinned={e['pinned']} archived_at={e['archived_at']} {ok(e['state']=='active' and e['pinned'])}")

print("\n== 3. .bak 技能目录归档 ==")
for base, tag in ((P, "profile"), (A, "source")):
    left = []
    for root, dirs, files in os.walk(base):
        if any(x.startswith(".") for x in os.path.relpath(root, base).split(os.sep) if x not in (".", "")):
            dirs[:] = []
            continue
        left += [d for d in dirs if ".bak" in d]
    print(f"  {tag}: 残留 .bak 目录 {left if left else 'NONE'} {ok(not left)}")

print("\n== 4. 文档-实际一致性 (路径存在性) ==")
paths = {
    "vps_ssh.py": r"D:/hermes/analysis/vps_ssh.py",
    "vps_poll.py": r"D:/hermes/analysis/vps_poll.py",
    "vps_sentinel.py": r"D:/hermes/analysis/vps_sentinel.py",
    "vps_credentials.json": r"D:/hermes/data/credentials/vps_credentials.json",
    "vps_ed25519 key": r"D:/hermes/data/credentials/vps_keys/vps_ed25519",
    "drawing_privacy_enforcer.py": r"D:/hermes/analysis/drawing_privacy_enforcer.py",
    "socks_http_bridge.py": r"D:/hermes/analysis/socks_http_bridge.py",
    "user_profiler.py": r"D:/hermes/analysis/user_profiler.py",
    "security_sandbox.py": r"D:/hermes/analysis/security_sandbox.py",
}
for label, p in paths.items():
    print(f"  {label:30s} {'exists' if os.path.exists(p) else 'MISSING'} {ok(os.path.exists(p))}")

print("\n== 5. 备份文件 ==")
for p in (r"D:/hermes/hermes-data/profiles/mybot/memories/MEMORY.md.pre_housekeeping_20260921.bak",
          r"D:/hermes/hermes-data/profiles/mybot/memories/USER.md.pre_housekeeping_20260921.bak",
          r"D:/hermes/hermes-data/profiles/mybot/skills/.usage.json.pre_housekeeping_20260921.bak"):
    print(f"  {os.path.basename(p):52s} {os.path.getsize(p) if os.path.exists(p) else 'MISSING'} {ok(os.path.exists(p))}")
