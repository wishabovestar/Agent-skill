#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scan_redirect_sinks_v5.py — 重定向汇聚点扫描 (第五版: 变量传递闭包)

★ 五层失明实测史(全是被真实代码打出来的):
  v1  `curl[^\\n]*?-L`          漏 列表形式 / 组合短选项 / 跨行 / 范围只 5 目录
  v2  AST List/Tuple 的 elts    漏 IfExp 分支常量
  v3  walk 递归收 str 常量      漏 curl 与 -L 在【不同语句】
  v4  跨语句变量 token 并集     漏 ★★ 变量【再传递】: cmd += [flags,...] 里 flags 是 Name
  v5  ★ 变量传递闭包(不动点迭代) ⇒ tokens[X] 反复并入其右侧出现的所有 Name 的 tokens

判据(最终):
  对每个被 subprocess.* 使用的命令行变量(或内联容器):
    闭包展开其 token 集; 若含 "curl" 且含 L 标志 ⇒ ★ 命中。
"""
import ast
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = r"D:\hermes\hermes-data\profiles\qqbot3"
SCAN_DIRS = ["scripts", "cron", "skills", "data"]
SKIP_DIRS = ("__pycache__", ".venv", ".git", "node_modules", "site-packages")
SKIP_SELF = {"scan_redirect_sinks.py", "scan_redirect_sinks_v2.py", "scan_redirect_sinks_v3.py",
             "scan_redirect_sinks_v4.py", "scan_redirect_sinks_v5.py",
             "patch_smart_fetcher.py", "redirect_e2e.py"}

RE_SHORTOPT = re.compile(r"^-[A-Za-z]{1,10}$")
RE_LONG_L = re.compile(r"^--location(-trusted)?$")
RE_MAXREDIRS = re.compile(r"^--max-redirs(=?(\d+))?$")
SUBPROC_FNS = {"run", "Popen", "call", "check_call", "check_output"}


def tok_follows(t):
    t = (t or "").strip()
    if not t.startswith("-"):
        return False
    if t.startswith("--no-location"):
        return False
    if RE_LONG_L.match(t):
        return True
    m = RE_MAXREDIRS.match(t)
    if m:
        return not (m.group(2) == "0")
    if RE_SHORTOPT.match(t) and "L" in t[1:]:
        return True
    return False


def strs_in(node):
    return [s.value for s in ast.walk(node)
            if isinstance(s, ast.Constant) and isinstance(s.value, str)]


def names_in(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def closure(root, vt, nbrs):
    """★ 变量级闭包(不动点): 从变量 root 出发, 沿"右侧引用了哪些变量"的边遍历,
    并集所有途经变量的 token 集。

    ★ 修复记录(v5 的错误): 早先版本用【token 字符串】去查 nbrs(key 是【变量名】)
      ⇒ nbrs.get("curl") 永远 None ⇒ 闭包恒为单点 ⇒ 变量再传递(cmd+= [flags,...])全部漏。
      v5 实测: smart_fetcher.py 仍漏, 而覆盖统计正常 ⇒ 定位到闭包本身。
    """
    seen, stack, toks = {root}, [root], set()
    while stack:
        v = stack.pop()
        toks |= vt.get(v, set())
        for n in nbrs.get(v, ()):
            if n not in seen:
                seen.add(n)
                stack.append(n)
    return toks


res = []
covered = []
files = 0
parse_fail = []

for d in SCAN_DIRS:
    p = os.path.join(BASE, d)
    if not os.path.isdir(p):
        continue
    for root, dirs, fs in os.walk(p):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for fn in fs:
            if not fn.endswith(".py") or fn in SKIP_SELF:
                continue
            fp = os.path.join(root, fn)
            rel = os.path.relpath(fp, BASE)
            try:
                txt = open(fp, encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            files += 1
            try:
                tree = ast.parse(txt)
            except SyntaxError as e:
                parse_fail.append((rel, str(e)[:46]))
                continue

            # 变量表: name -> tokens;  并记录该变量右侧出现的 Name(用于闭包)
            vt = {}
            nbrs = {}
            for node in ast.walk(tree):
                tgt = None
                rhs = None
                if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                        and isinstance(node.targets[0], ast.Name):
                    tgt, rhs = node.targets[0].id, node.value
                elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
                    tgt, rhs = node.target.id, node.value
                if tgt is None:
                    continue
                vt.setdefault(tgt, set()).update(strs_in(rhs))
                nbrs.setdefault(tgt, set()).update(names_in(rhs))

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                f = node.func
                fname = f.attr if isinstance(f, ast.Attribute) else (
                    f.id if isinstance(f, ast.Name) else "")
                if fname not in SUBPROC_FNS or not node.args:
                    continue
                a0 = node.args[0]
                if isinstance(a0, ast.Name):
                    base, src = set(vt.get(a0.id, ())), a0.id
                    rootvar = a0.id
                elif isinstance(a0, (ast.List, ast.Tuple)):
                    base, src = set(strs_in(a0)), "<inline>"
                    rootvar = None
                else:
                    continue
                if not any("curl" in t for t in base):
                    continue
                # ★ 变量传参 ⇒ 变量级闭包; 内联容器 ⇒ 只要 walk 收集(已覆盖 IfExp)
                toks = closure(rootvar, vt, nbrs) if rootvar else base
                flags = sorted({t for t in toks if tok_follows(t)})
                covered.append((rel, node.lineno, src, len(toks)))
                if flags:
                    res.append((rel, node.lineno, src, ",".join(flags), " ".join(sorted(toks))[:62]))


def dedup(rows):
    seen, out = set(), []
    for r in rows:
        k = (r[0], r[1])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


R = dedup(sorted(res, key=lambda r: (r[0], r[1])))
Cv = dedup(covered)

# ★ 标注每处是否【已复核】(r1185): 扫描器原来的问题是不区分 已修/未修,
#   导致"命中 15 处"看不出还剩几处真缺口。此处读文件内容判断。
GUARD_TOKENS = ("redirect_guard", "_guard_final_url", "curl_guarded",
                "check_redirect_chain", "url_effective", "safe_curl", "cg.run")


def _guard_status(rel):
    p = os.path.join(BASE, rel)
    try:
        t = open(p, encoding="utf-8", errors="replace").read()
    except Exception:
        return "?"
    hit = [g for g in GUARD_TOKENS if g in t]
    return "✅已复核(%s)" % hit[0] if hit else "🔴未复核"


def annotate(rows):
    out = []
    for r in rows:
        out.append(r + (_guard_status(r[0]),))
    return out


R = annotate(R)

print("=" * 84)
print("  重定向汇聚点扫描 v5 (变量传递闭包)  扫了 %d 个 .py" % files)
print("=" * 84)
print("\n  ── ★ 命中: 命令行变量闭包内含 curl 且含 L 标志 ──")
for rel, ln, src, flags, ev, gs in R:
    print("     %-40s:%-4d [%s] L=%-9s %s" % (rel[:40], ln, src, flags, gs))
if not R:
    print("     (无)")
unguarded = [r for r in R if r[5].startswith("🔴")]
print("\n  ★★ 真缺口(仍无复核): %d 处" % len(unguarded))
for rel, ln, src, flags, ev, gs in unguarded:
    print("     %-40s:%-4d L=%s" % (rel[:40], ln, flags))
print("\n  ── 覆盖: 含 curl 的命令行调用点共 %d 处(命中 %d, 其余 %d 不使用 -L)──"
      % (len(Cv), len(R), len(Cv) - len(R)))
if parse_fail:
    print("\n  ── 未解析 %d 个 ──" % len(parse_fail))

print("\n" + "=" * 84)
print("  自检(精确): smart_fetcher.py")
print("=" * 84)
SF = os.path.join("scripts", "smart_fetcher.py")
sf = [r for r in R if r[0] == SF]
print("     命中 %d 处 %s" % (len(sf), [(r[1], r[3]) for r in sf]))
print("     判定: %s" % ("✅ 命中真实调用点(v1–v4 全漏)" if sf else "🔴 仍漏"))
