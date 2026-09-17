#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""skill_spec_audit.py — 用 Agno 的「Agent Skills Spec」实测本机技能库

【规范来源】
  agno-agi/agno @ main : libs/agno/agno/skills/validator.py (🟢 已取一手源码)
  常量逐条抄录:
    MAX_SKILL_NAME_LENGTH = 64
    MAX_DESCRIPTION_LENGTH = 1024
    MAX_COMPATIBILITY_LENGTH = 500
    ALLOWED_FIELDS = {name, description, license, allowed-tools, metadata, compatibility}
  名称规则: 非空 / ≤64 / 全小写 / 不以 - 开头或结尾 / 不含连续 -- /
            只允许字母数字与 - / ★ 目录名必须等于技能名 / NFKC 归一化后比较

【为什么要做】
  本机有 195 个活跃技能且刚做过"description 质量审计", 但【没有】按一份公开规范逐字段卡过。
  Agno 这份是可直接复用的外部标准 ⇒ 用它做一次独立数值审计 (不靠自评)。

用法: python skill_spec_audit.py [--json]
"""
# side_effects: [--json 时写 data/skill_spec_audit.json]

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SK = os.path.join(HOME, "skills")

MAX_NAME = 64
MAX_DESC = 1024
MAX_COMPAT = 500
ALLOWED = {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}

# ★★★ 2026-09-17 本地化判读 (真修)
# ──────────────────────────────────────────────────────────────────────
# Agno 的规范白名单只有 6 个字段; 而 Hermes 的 SKILL.md 惯例使用一批自有扩展。
# 照搬白名单 ⇒ 196 个技能里 162 个被判"违例"(82.7%), 而它们**本来工作正常**。
# ★ 首次审计时脚本自己在末尾注了一句"此项属规范差异而非缺陷" —— 但**统计口径没改**,
#   82.7% 这个数字照旧报出来, 读的人只会看到"大面积不合规"。
# ⇒ 真修: 把"白名单外字段"拆成两类, 只有【真正无法解释的字段】才算违例。
#   · 本机扩展 (Hermes 惯例, 有约定含义) ⇒ 单列计数, 不进违例
#   · 未知字段 ⇒ 记违例 (可能是拼写错误或上游带来的脏字段)
HERMES_EXTS = {
    "version", "author", "platforms", "side_effects", "allowed_tools",
    # ★ 2026-09-17: `dependencies` 与 `depends_on` 是同义扩展 —— 首版只收了后者,
    #   把 12 个用前者的技能误判成"未知字段"。★ 是我自己引入的不一致。
    "depends_on", "dependencies", "out_of_scope", "triggers", "created_by",
    "setup", "type", "title", "environments", "required_credential_files",
    "authors", "credentials", "lifecycle", "prerequisites", "tags", "rank",
    "category", "related_skills", "priority", "entrypoint", "requires",
}
# ★★★ 2026-09-17 更正 (差点改错 10 个文件)
# ──────────────────────────────────────────────────────────────────────
# 首版把 `depends_on` 与 `dependencies` 当成【同义字段】并报"命名分裂 43:10"。
# 实际核对**值**后发现语义完全不同:
#   · depends_on   (本机 43 个) = **[research] / [ocr-and-documents, pdf] / [network-resilience, arxiv]` → **技能名**
#   · dependencies (本机 10 个) = `[vllm, torch, transformers]` / `[llama-cpp-python>=0.2.0]` → **pip 包**
# ★ 而且去查**上游源码**证实: Hermes 自带的 optional-skills 就写
#   `dependencies: [llama-cpp-python>=0.2.0]` —— 那是**上游约定字段**, 本机 10 个是忠实跟随。
# ⇒ 两者【不是同义】, 报"命名分裂"是错的; 按那个结论去重命名会**把 pip 包混进技能依赖列表**。
# ⇒ 教训: **判定"同义"必须比对值, 不能只看名字**; 且先查上游约定再动手。
SYNONYM_GROUPS = []   # 暂无可确证的同义组

# 上游 optional-skills 约定字段 (不是 Hermes 自研扩展, 但同属合法)
UPSTREAM_FIELDS = {"dependencies", "author", "license", "compatibility"}


def parse_frontmatter(t):
    m = re.match(r"^---\s*\n(.*?)\n---", t, re.S)
    if not m:
        return None
    fields = {}
    for ln in m.group(1).split("\n"):
        mm = re.match(r"^([A-Za-z_][\w\-]*)\s*:\s*(.*)$", ln)
        if mm:
            fields[mm.group(1)] = mm.group(2).strip().strip('"\'')
    return fields


def check(name, dirname, fm):
    errs = []
    n = fm.get("name", "")
    if not n:
        errs.append("name 缺失")
    else:
        nn = unicodedata.normalize("NFKC", n.strip())
        if len(nn) > MAX_NAME:
            errs.append("name 超 %d 字符 (%d)" % (MAX_NAME, len(nn)))
        if nn != nn.lower():
            errs.append("name 非全小写")
        if nn.startswith("-") or nn.endswith("-"):
            errs.append("name 以 - 开头/结尾")
        if "--" in nn:
            errs.append("name 含连续 --")
        if not all(c.isalnum() or c == "-" for c in nn):
            errs.append("name 含非法字符(仅允许字母数字与 -)")
        # ★ 目录名必须等于技能名
        dn = unicodedata.normalize("NFKC", dirname)
        if dn != nn:
            errs.append("目录名 %r ≠ 技能名 %r" % (dn, nn))
    d = fm.get("description", "")
    if not d:
        errs.append("description 缺失")
    elif len(d) > MAX_DESC:
        errs.append("description 超 %d 字符 (%d)" % (MAX_DESC, len(d)))
    c = fm.get("compatibility", "")
    if c and len(c) > MAX_COMPAT:
        errs.append("compatibility 超 %d 字符" % MAX_COMPAT)
    extra = [k for k in fm if k not in ALLOWED]
    # ★ 本地化判读: 拆成【本机扩展】与【真未知】
    exts = [k for k in extra if k in HERMES_EXTS]
    unknown = [k for k in extra if k not in HERMES_EXTS]
    if unknown:
        errs.append("frontmatter 含未知字段: %s" % ", ".join(unknown[:4]))
    return errs, exts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    rows, tag = [], Counter()
    for root, dirs, files in os.walk(SK):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if "SKILL.md" not in files:
            continue
        p = os.path.join(root, "SKILL.md")
        try:
            t = open(p, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        fm = parse_frontmatter(t)
        if fm is None:
            rows.append((os.path.relpath(p, HOME), ["无 YAML frontmatter"], []))
            continue
        errs, fx = check(fm.get("name", os.path.basename(root)), os.path.basename(root), fm)
        rows.append((os.path.relpath(p, HOME), errs, fx))
        for e in errs:
            tag[e.split("(")[0].strip()] += 1

    bad = [r for r in rows if r[1]]
    with_ext = [r for r in rows if r[2]]
    print("═" * 78)
    print("  Agent Skills Spec 合规审计 (规范源: agno/skills/validator.py)")
    print("═" * 78)
    print("  技能总数: %d | ✅ 纯合规: %d | 🟡 用本机扩展: %d | 🔴 真违例: %d (%.1f%%)" %
          (len(rows), len(rows) - len(bad) - len([r for r in rows if r[2] and not r[1]]),
           len([r for r in rows if r[2]]), len(bad),
           100.0 * len(bad) / max(1, len(rows))))
    print()
    if tag:
        print("  ── 违例类型分布 ──")
        for k, v in tag.most_common():
            print("     %-44s %d" % (k, v))
        print()
    print("  ── 违例清单 (前 20) ──")
    for path, errs, _fx in bad[:20]:
        print("     %-56s %s" % (path[:56], " | ".join(errs)[:80]))
    if len(bad) > 20:
        print("     …还有 %d 个" % (len(bad) - 20))
    print()
    print("  ★ 该规范是外部标准 (Agno 实现), 用于独立数值审计, 非本机自评。")
    # ★ 命名分裂报告 (同义字段多名字)
    if SYNONYM_GROUPS:
        print()
        print("  ── 命名分裂 (同义字段多个名字 — 文档层不一致, 非运行时缺陷) ──")
        for grp in SYNONYM_GROUPS:
            cnt = {g: 0 for g in grp}
            for p, _e, _x in rows:
                try:
                    t2 = open(os.path.join(HOME, p), encoding="utf-8", errors="replace").read()
                except Exception:
                    continue
                fm2 = parse_frontmatter(t2)
                if not fm2:
                    continue
                for g in grp:
                    if g in fm2:
                        cnt[g] += 1
            tot = sum(cnt.values())
            name = " vs ".join("%s=%d" % (k, v) for k, v in cnt.items())
            if all(cnt.values()):
                print("     ⚠️ %s (共 %d 个技能) ⇒ 建议统一到一个名字" % (name, tot))
            else:
                print("     ✅ %s (共 %d 个技能)" % (name, tot))
    print("  ★ 2026-09-17 本地化判读: Hermes 自有的 %d 个扩展字段 (version/author/" % len(HERMES_EXTS))
    print("    platforms/side_effects/...) **已从违例中剔除** —— 它们有约定含义、")
    print("    在 Hermes 里工作正常, 只是不在 Agno 那份 6 字段白名单里。")
    print("    ⇒ 只看 🔴 真违例; 🟡 是「用本机扩展但无其他问题」, 不是缺陷。")

    if a.json:
        out = os.path.join(HOME, "data", "skill_spec_audit.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"total": len(rows), "violations": len(bad),
                       "using_local_extensions": len(with_ext),
                       "by_type": dict(tag),
                       "rows": [{"path": p, "errors": e, "local_exts": x}
                                for p, e, x in rows]},
                      f, ensure_ascii=False, indent=2)
        print("\n  ✅ 已存: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
