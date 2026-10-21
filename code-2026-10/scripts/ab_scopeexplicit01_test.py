# -*- coding: utf-8 -*-
"""
AB-SCOPEEXPLICIT-01 — 「任务显式写清目标/允许动作/边界」
=========================================================
队列规格(总闸第十六条): 显式边界 vs 隐含边界, 在环境异常时行为差异。判据: 隐含边界是否失效。

本机对应物(analysis/security_sandbox.py 真实生产代码, 只调用 check_file_access, 不做任何文件 IO):
  显式边界 = 写路径白名单 WRITE_ALLOWED_PATHS  → 未列即拒(默认拒)
  隐含边界 = 读路径黑名单 BLOCKED_READ_PATTERNS → 未列即放(默认放)

★ 关键设计: 变形样本【不是】从黑名单里摘出来的, 而是"同一个秘密文件的另一种写法"
  (Windows 尾点/尾空格等义写法、*.env 变体、扩展长度前缀)。所以命中率不是构造性的。

★ 正对照: 每个黑名单/白名单的标准形态都在样本里, 必须先确认它们被拦下,
  否则"变形样本也拦下了"不能算有效(可能整个检查器没在跑)。
"""
import os, sys, json, importlib.util, re
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SS = r"D:/hermes/analysis/security_sandbox.py"
OUT = r"D:/hermes/data/ab_scopeexplicit01_results.json"

spec = importlib.util.spec_from_file_location("security_sandbox", SS)
sandbox = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sandbox)


def chk(path, mode):
    r = sandbox.check_file_access(path, mode)
    return bool(r.get("allowed")), r.get("reason", "")


# ── 组1: 隐含边界(读黑名单) 标准形态 = 正对照, 必须 deny ────────────────
READ_CONTROL = [
    ("D:/hermes/data/.env", "标准 .env"),
    ("D:/hermes/data/keys/id_rsa", "标准 SSH 私钥"),
    ("D:/hermes/data/.aws/credentials", "标准 AWS 凭证"),
    ("D:/hermes/data/x/.git/config", "标准 .git/config"),
    ("D:/hermes/data/.kube/config", "标准 kubeconfig"),
    ("D:/hermes/data/known_hosts", "标准 known_hosts"),
]

# ── 组2: 隐含边界 变形形态 = 同一秘密文件的其他写法, 期望仍 deny ─────────
READ_VARIANT = [
    ("D:/hermes/data/.env.local", ".env 加后缀(常见多环境写法)"),
    ("D:/hermes/data/prod.env", "名字以 .env 结尾但前缀不是分隔符"),
    ("D:/hermes/data/aws.env", "项目级 env 文件"),
    ("D:/hermes/data/.env.", "Windows 尾点等义写法"),
    ("D:/hermes/data/.env ", "Windows 尾空格等义写法"),
    ("D:/hermes/data/.ENV", "大写变体"),
    ("D:/hermes/data/server.key", "标准 .key(对照内)"),
    ("D:/hermes/data/server.key.bak", ".key 加备份后缀"),
    ("D:/hermes/data/tls.pem.old", ".pem 加后缀"),
    ("D:/hermes/data/config.json.key", "json+key 组合"),
    ("D:/hermes/data/keys/id_rsa.bak", "私钥备份"),
    ("\\\\?\\D:\\hermes\\data\\.env", "扩展长度前缀 \\\\?\\"),
    ("D:/hermes/data/sub/../.env", "路径归一化后仍是 .env"),
]

# ── 组3: 显式边界(写白名单) 越界标准形态 = 必须 deny ───────────────────
WRITE_BYPASS = [
    ("C:/Windows/System32/evil.dll", "系统目录"),
    ("D:/hermes/analysis/../../Windows/evil.dll", "穿越出白名单"),
    ("D:/hermes/analysis/../other/x.py", "平级越界"),
    ("D:/hermes/analysisx/x.py", "前缀同形但非子目录"),
    ("C:/Users/Administrator/AppData/Local/hermes_evil/x.py", "前缀同形 hermes_evil"),
    ("\\\\?\\D:\\Windows\\evil.dll", "扩展长度前缀越界"),
    ("D:/hermes/data/../../etc/passwd", "向上穿越"),
]

# ── 组4: 显式边界的真实运维写盘路径 = 期望 allow(白名单是否与环境对齐) ──
WRITE_REAL = [
    ("D:/hermes/hermes-data/profiles/mybot/skills/foo/SKILL.md", "profile 技能目录"),
    ("D:/hermes/hermes-data/profiles/mybot/knowledge_base/x.db", "profile 知识库"),
    ("D:/hermes/hermes-data/profiles/mybot/cache/scratch/x.py", "profile 沙盒目录"),
    ("D:/hermes/shared-skills/foo/SKILL.md", "全 profile 共享技能目录"),
    ("D:/hermes/analysis/x.py", "白名单内(正对照)"),
]


def run_group(items, mode):
    rows = []
    for p, label in items:
        allowed, reason = chk(p, mode)
        rows.append({"path": p, "label": label, "allowed": allowed,
                     "reason": reason, "denied": not allowed})
    return rows


def pct(a, b):
    return (100.0 * a / b) if b else 0.0


def main():
    rc = run_group(READ_CONTROL, "read")
    rv = run_group(READ_VARIANT, "read")
    wb = run_group(WRITE_BYPASS, "write")
    wr = run_group(WRITE_REAL, "write")

    read_control_hit = pct(sum(1 for r in rc if r["denied"]), len(rc))
    implicit_gap = pct(sum(1 for r in rv if r["allowed"]), len(rv))     # 变形样本被放行 = 失效
    explicit_gap = pct(sum(1 for r in wb if r["allowed"]), len(wb))     # 越界被放行 = 失效
    overblock = pct(sum(1 for r in wr if r["denied"]), len(wr))         # 真实路径被拦 = 误拦

    checks = [
        ("正对照: 读黑名单标准形态全拦截", read_control_hit >= 100.0,
         "%d/%d = %.0f%%" % (sum(1 for r in rc if r["denied"]), len(rc), read_control_hit)),
        ("正对照: 写白名单内路径放行", any(r["allowed"] for r in wr if "白名单内" in r["label"]),
         "D:/hermes/analysis/x.py allowed=%s" % next((r["allowed"] for r in wr if "白名单内" in r["label"]), None)),
        ("显式边界(白名单)在变形越界下不失守", explicit_gap <= 0.0,
         "explicit_gap=%.0f%% (%d 样本)" % (explicit_gap, len(wb))),
        ("显式边界优于隐含边界(差异真实存在)", explicit_gap < implicit_gap,
         "explicit %.0f%% vs implicit %.0f%% (差 %.0fpp)" % (explicit_gap, implicit_gap, implicit_gap - explicit_gap)),
    ]
    passed = all(ok for _, ok, _ in checks)

    out = {
        "test": "AB-SCOPEEXPLICIT-01",
        "title": "显式边界(写白名单) vs 隐含边界(读黑名单) 在变形输入下的行为差异",
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "engine": SS,
        "n_units": {"read_control": len(rc), "read_variant": len(rv),
                    "write_bypass": len(wb), "write_real": len(wr)},
        "read_control_hit_pct": read_control_hit,
        "implicit_gap_pct": implicit_gap,
        "explicit_gap_pct": explicit_gap,
        "overblock_on_real_paths_pct": overblock,
        "read_control": rc, "read_variant": rv,
        "write_bypass": wb, "write_real": wr,
        "checks": [{"name": n, "ok": o, "evidence": e} for n, o, e in checks],
        "verdict": "PASS" if passed else "FAIL",
        "note": "仅调用 check_file_access 的纯路径判定, 未对任何样本路径做文件读写; 生产 security_sandbox.py 未修改",
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))

    print("=== AB-SCOPEEXPLICIT-01: explicit (write allowlist) vs implicit (read blocklist) ===")
    print("read control  : %d/%d denied (%.0f%%)" % (sum(1 for r in rc if r["denied"]), len(rc), read_control_hit))
    print("read variants : %d/%d LEAKED (implicit gap %.0f%%)" % (sum(1 for r in rv if r["allowed"]), len(rv), implicit_gap))
    for r in rv:
        if r["allowed"]:
            print("    LEAK  %-46s  %s" % (r["label"], r["path"]))
    print("write bypass  : %d/%d LEAKED (explicit gap %.0f%%)" % (sum(1 for r in wb if r["allowed"]), len(wb), explicit_gap))
    for r in wb:
        if r["allowed"]:
            print("    LEAK  %-46s  %s" % (r["label"], r["path"]))
    print("write real    : %d/%d BLOCKED (overblock %.0f%%)" % (sum(1 for r in wr if r["denied"]), len(wr), overblock))
    for r in wr:
        if r["denied"]:
            print("    OVERBLOCK  %-44s  %s" % (r["label"], r["path"]))
    print()
    for n, o, e in checks:
        print("  [%s] %s — %s" % ("PASS" if o else "FAIL", n, e))
    print("\nVERDICT: %s -> %s" % (out["verdict"], OUT))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
