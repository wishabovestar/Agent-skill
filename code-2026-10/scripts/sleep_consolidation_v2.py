#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
睡眠记忆巩固 v2 — 接【真数据源】
================================
旧版 (v1) 的问题：
  · Stage 1 只扫 Redis db1 —— 而那个库是空的（dbsize=0），81 天恒为 0，纯空转
  · Stage 2 的"建议"是写死的字符串常量，不是任何分析产物
  · 无论发生什么，最后都写 status:"ok" —— 把空转伪装成成功

v2 改为读真实在用存储：
  · Hermes MEMORY.md / USER.md      （当前记忆，含预算占用）
  · memory_cache.json              （facts / consolidations）
  · KB hermes_kb.db                （实体/关系/孤点）
  · MEMORY.md 历史备份             （⭐ 记忆完整性：与最近备份比，检测丢段/缩水）

输出：（1）真实统计数字；（2）由统计推导的建议；（3）诚实 status。
只读，不改任何东西。
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import difflib
from datetime import datetime
from pathlib import Path

PROFILE = Path("D:/hermes/hermes-data/profiles/mybot")
MEM_DIR = PROFILE / "memories"
MEMORY_MD = MEM_DIR / "MEMORY.md"
USER_MD = MEM_DIR / "USER.md"
MEM_CACHE = MEM_DIR / "memory_cache.json"
KB_DB = Path("D:/hermes/data/kb/hermes_kb.db")
OUTPUT_DIR = PROFILE / "cron/output"

# ⭐ 完整性基线（2026-10-19 改）：用每日 git 快照，而不是"最近的那个 MEMORY.md.bak_*"文件。
#   病根: 文件备份自从 2026-10-14 瘦身之后再没生成过 ⇒ 基线永远停在 bak_before_slim，
#   于是每天都报"丢失 L0/L1/L2 三段"（那是有意瘦身删掉的标题）—— 持续 4 天的固定噪声。
#   改后基线 = 最近一个【内容与当前不同】的 git 快照（memory_git_snapshot 每天 03:00 提交），
#   既能抓到真丢失，也不会把历史瘦身一直翻出来。
GIT_REPO = Path("D:/hermes/data/memory_git")
GIT_FILE = "MEMORY.md"


CHARS_LIMITS = {"MEMORY.md": 2200, "USER.md": 1375}   # 与 Hermes 一致
DUP_RATIO = 0.85
SHRINK_ALERT = 0.85          # 相对备份缩水 >15% 报警
ENTRY_DELIMITER = "\n§\n"    # ⚠️ 权威条目分隔符（见 skill hermes-memory-store-mechanics §3）


def official_char_count(raw: str) -> int:
    """Hermes `memory` 工具的【权威】字符计数。
    ⚠️ 不能用 len(raw)：必须先把 \r\n 归一 → 按 \n§\n 切 → 逐条 strip → 重 join 再算长度。
    否则与工具报的数字对不上（本档 2026-10-13/10-14 两次踩过：字节≠字符，CR 也会差）。
    """
    raw = raw.replace("\r\n", "\n")
    entries = [e for e in (x.strip() for x in raw.split(ENTRY_DELIMITER)) if e]
    return len(ENTRY_DELIMITER.join(entries)), entries


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ──────────────────────────────────────── 解析
def parse_sections(text):
    """按 ## 标题切段 → {section: [lines]}"""
    secs, cur = {}, "__head__"
    secs[cur] = []
    for ln in text.splitlines():
        m = re.match(r'^##\s+(.*)$', ln)
        if m:
            cur = m.group(1).strip()
            secs.setdefault(cur, [])
        else:
            secs[cur].append(ln)
    return secs


def parse_entries(text):
    """把正文切成条目（以 § 或空行分隔，跳过标题）"""
    body = "\n".join(l for l in text.splitlines() if not l.startswith("#"))
    parts = re.split(r'\n\s*§\s*\n|\n\s*\n', body)
    return [p.strip() for p in parts if len(p.strip()) > 15]


# ⭐ v3：memory 应只留"跨任务恒真事实"；带流程/命令/坑信号的条目属于 skill。
PROC_MARKERS = ("skill", "脚本", "流程", "步骤", "命令", "铁律", "坑", "路径", "台账",
                "cron", "hook", "管道", "备份", ".py", "闸", "hermes config", "lib")


# 本条同时含【环境事实】（本机/端口/GPU）⇒ 不能整条迁走，只能拆分
FACT_MARKERS = ("本机", "端口", "版本", "gpu", "rtx", "记忆权威", "配额", "字符", "凭据")


def migration_candidates(entries, limit=6):
    """挑可迁到 skill 的条目，并区分【整条可迁】与【混合需拆分】。

    ⚠️ 2026-10-21 实测教训：只数流程信号会把「本机 Ollama/GPU + 三坑+流程见 skill」
    这类混合条目标成可整条迁走（那会丢环境事实）⇒ 必须带 kind。
    """
    out = []
    for e in entries:
        low = e.lower()
        hits = sum(1 for m in PROC_MARKERS if m in low)
        if hits < 2:
            continue
        fact = sum(1 for m in FACT_MARKERS if m in low)
        out.append({"chars": len(e), "hits": hits, "fact_hits": fact,
                    "kind": "mixed" if fact else "whole", "head": e[:60]})
    out.sort(key=lambda x: (-x["chars"], -x["hits"]))
    return out[:limit]


def orphan_merge_pairs(names, ratio=0.82, limit=5):
    """孤点里名字高度相似的，可能是同一实体的两种写法（可合并成一条再连边）。"""
    out = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            r = difflib.SequenceMatcher(None, names[i], names[j]).ratio()
            if r >= ratio:
                out.append({"ratio": round(r, 3), "a": names[i][:50], "b": names[j][:50]})
    out.sort(key=lambda x: -x["ratio"])
    return out[:limit]


def near_dups(entries):
    out = []
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            r = difflib.SequenceMatcher(None, entries[i], entries[j]).ratio()
            if r >= DUP_RATIO:
                out.append({"i": i, "j": j, "ratio": round(r, 3),
                            "a": entries[i][:70], "b": entries[j][:70]})
    return out


def latest_backup():
    baks = sorted(MEM_DIR.glob("MEMORY.md.*"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    baks = [b for b in baks if b.stat().st_size > 100 and not b.name.endswith(".lock")]
    return baks[0] if baks else None


def _git(args, timeout=30):
    """跑 git，返回 (rc, bytes)。任何异常都返回 (1, b'')。"""
    try:
        r = subprocess.run(["git", "-C", str(GIT_REPO)] + args,
                           capture_output=True, timeout=timeout)
        return r.returncode, r.stdout
    except Exception:
        return 1, b""


def git_baseline(cur_text):
    """⭐ 完整性基线 = 最近一个内容与当前【不同】的 git 快照。

    返回 (label, text) 或 (None, None)。
    为什么不是直接 HEAD~1：今天 03:00 的快照可能已经等于当前文件
    （改记忆发生在 00:43，早于 03:00 提交）⇒ 拿 HEAD~1 当基线会把
    "今天的正常增删"误报成丢段。逐条向下找第一个真正不同的快照才对。
    """
    if not (GIT_REPO / ".git").exists():
        return None, None
    rc, out = _git(["log", "--format=%H %ad", "--date=short", "--", GIT_FILE])
    if rc != 0 or not out.strip():
        return None, None
    cur_norm = cur_text.replace("\r\n", "\n").strip()
    for ln in out.decode("utf-8", "replace").splitlines():
        parts = ln.split()
        if len(parts) < 2:
            continue
        h, date = parts[0], parts[1]
        rc2, blob = _git(["show", f"{h}:{GIT_FILE}"])
        if rc2 != 0:
            continue
        txt = blob.decode("utf-8", "replace")
        if txt.replace("\r\n", "\n").strip() != cur_norm:
            label = f"git快照 {date} ({h[:8]})"
            return label, txt
    return None, None


# ──────────────────────────────── Stage 1: 真实记忆合并分析
def stage1():
    r = {
        "sources_found": [],
        "memory": {}, "user": {}, "kb": {}, "cache": {},
        "integrity": {}, "near_duplicates": [], "findings": [], "errors": [],
    }

    for tag, p in (("memory", MEMORY_MD), ("user", USER_MD)):
        if not p.exists():
            r["errors"].append(f"{p.name} 不存在")
            continue
        r["sources_found"].append(p.name)
        txt = p.read_text(encoding="utf-8", errors="replace")
        n, ents = official_char_count(txt)      # ⚠️ 用权威公式，不是 len(txt)
        lim = CHARS_LIMITS.get(p.name, 2000)
        secs = parse_sections(txt)
        r[tag] = {
            "path": str(p),
            "chars": n,                       # 权威计数（与 memory 工具一致）
            "chars_raw": len(txt),            # 原始文件长度，仅作对照
            "limit": lim,
            "pct": round(100.0 * n / lim, 1),
            "entries": len(ents),
            "sections": {k: sum(1 for x in v if x.strip()) for k, v in secs.items()},
            "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
        }
        if n > lim:
            r["findings"].append(f"{p.name} 超出预算 {n-lim} 字符（{r[tag]['pct']}%）")
        elif r[tag]["pct"] > 90:
            r["findings"].append(f"{p.name} 已用 {r[tag]['pct']}%，接近上限，建议把可复用条目迁到 skill")

    mem_txt = MEMORY_MD.read_text(encoding="utf-8", errors="replace") if MEMORY_MD.exists() else ""
    ents = parse_entries(mem_txt)
    r["near_duplicates"] = near_dups(ents)
    r["migration_candidates"] = migration_candidates(ents)
    if r["migration_candidates"] and r.get("memory"):
        whole = [x for x in r["migration_candidates"] if x["kind"] == "whole"]
        mixed = [x for x in r["migration_candidates"] if x["kind"] == "mixed"]
        # 只把【整条可迁】计入保守释放量；混合条目按 0 计入（需人工拆分，不虚报）
        freed = sum(x["chars"] for x in whole)
        r["migration"] = {"candidates": r["migration_candidates"],
                          "whole": len(whole), "mixed": len(mixed),
                          "chars_freed": freed,
                          "pct_after": round(100.0 * (r["memory"]["chars"] - freed)
                                             / r["memory"]["limit"], 1)}
        r["findings"].append(
            f"MEMORY 迁移候选 {len(r['migration_candidates'])} 条"
            f"（整条可迁 {len(whole)} / 混合需拆分 {len(mixed)}）；"
            f"保守释放 {freed} 字符（{r['memory']['pct']}% → {r['migration']['pct_after']}%）")
    if r["near_duplicates"]:
        r["findings"].append(f"MEMORY 内检出 {len(r['near_duplicates'])} 对近似重复条目")

    # ⭐ 记忆完整性：与【昨日 git 快照】比（2026-10-19 改；文件备份降为兜底）
    if MEMORY_MD.exists():
        cur = MEMORY_MD.read_text(encoding="utf-8", errors="replace")
        label, old, src = None, None, None
        label, old = git_baseline(cur)
        if old is not None:
            src = "git"
        else:
            bak = latest_backup()
            if bak:
                label, src = bak.name, "file"
                old = bak.read_text(encoding="utf-8", errors="replace")
        if old is not None:
            cs = set(parse_sections(cur).keys())
            os_ = set(parse_sections(old).keys())
            lost = sorted(os_ - cs)
            added = sorted(cs - os_)
            lc, lo = len(cur), len(old)
            r["integrity"] = {
                "backup": label,
                "baseline_src": src,
                "chars_now": lc, "chars_backup": lo,
                "delta": lc - lo,
                "lost_sections": lost,
                "added_sections": added,
                "lines_removed": sum(1 for l in difflib.unified_diff(
                    old.splitlines(), cur.splitlines(), lineterm='', n=0)
                    if l.startswith('-') and not l.startswith('---')),
                "lines_added": sum(1 for l in difflib.unified_diff(
                    old.splitlines(), cur.splitlines(), lineterm='', n=0)
                    if l.startswith('+') and not l.startswith('+++')),
            }
            if lost:
                r["findings"].append(
                    f"⚠️ 记忆完整性: 相对 {label} 丢失 {len(lost)} 个段: {', '.join(lost)}")
            # 纯字符缩水不告警 —— 有意编辑(如瘦身)与意外丢失在字符数上不可区分，
            # 结构性丢失已由 lost_sections 覆盖。这里只作信息记录。
            if lo > 0 and lc < lo * SHRINK_ALERT and not lost:
                r["integrity"]["note_shrink"] = (
                    f"字符数 {lo} → {lc}（-{100*(1-lc/lo):.0f}%），段数未减 ⇒ 判为有意编辑")

    if MEM_CACHE.exists():
        r["sources_found"].append("memory_cache.json")
        try:
            d = json.loads(MEM_CACHE.read_text(encoding="utf-8"))
            r["cache"] = {
                "facts": len(d.get("facts", [])),
                "consolidations": len(d.get("consolidations", [])),
                "stale_facts": sum(1 for f in d.get("facts", []) if f.get("access_count", 0) == 0),
            }
            if r["cache"].get("stale_facts"):
                r["findings"].append(
                    f"memory_cache: {r['cache']['stale_facts']} 条 fact 从未被访问（access_count=0）")
        except Exception as e:
            r["errors"].append(f"memory_cache.json 解析失败: {e}")

    if KB_DB.exists():
        r["sources_found"].append("hermes_kb.db")
        try:
            c = sqlite3.connect(str(KB_DB))
            c.row_factory = sqlite3.Row
            ent = c.execute("select count(*) from entities").fetchone()[0]
            rel = c.execute("select count(*) from relationships").fetchone()[0]
            byt = {x[0]: x[1] for x in c.execute(
                "select entity_type,count(*) from entities group by 1 order by 2 desc")}
            orph = c.execute(
                "select count(*) from entities e where not exists"
                "(select 1 from relationships r where r.source_id=e.id or r.target_id=e.id)"
            ).fetchone()[0]
            r["kb"] = {"entities": ent, "relationships": rel, "by_type": byt,
                       "orphans": orph,
                       "orphan_pct": round(100.0 * orph / ent, 1) if ent else 0}
            if orph:
                r["findings"].append(f"KB: {orph} 个孤点（无任何关系，占 {r['kb']['orphan_pct']}%）")
                # ⭐ v3：孤点里名字近似的优先合并（先合并再连边，比逐条补关系省事）
                names = [x[0] for x in c.execute(
                    "select name from entities e where not exists"
                    "(select 1 from relationships r where r.source_id=e.id or r.target_id=e.id)"
                    " limit 80")]
                r["kb"]["sample_orphans"] = names[:12]
                r["kb"]["merge_pairs"] = orphan_merge_pairs(names)
                if r["kb"]["merge_pairs"]:
                    r["findings"].append(
                        f"KB: 孤点中检出 {len(r['kb']['merge_pairs'])} 对近名实体，可先合并")
            c.close()
        except Exception as e:
            r["errors"].append(f"KB 读取失败: {e}")

    return r


# ──────────────────────────────── Stage 2: Dreaming（由真实统计推导）
def stage2(st1):
    s = []
    mem, integ, kb = st1.get("memory", {}), st1.get("integrity", {}), st1.get("kb", {})

    if integ.get("lost_sections"):
        s.append(("🔴 记忆完整性", [
            f"检测到段丢失: {', '.join(integ['lost_sections'])}",
            f"备份 {integ['backup']}（{integ['chars_backup']} 字符）→ 现在 {integ['chars_now']} 字符",
            f"建议: 人工确认是否有意删除；如是误删，从 {integ['backup']} 恢复对应段",
        ]))
    if mem.get("pct", 0) > 90:
        s.append(("🟡 容量", [
            f"MEMORY.md 已用 {mem['pct']}%（{mem['chars']}/{mem['limit']}）",
            "建议: 把【任务相关流程】迁到 skill（memory 应只留跨任务恒真事实）",
        ]))
    mig = st1.get("migration") or {}
    if mig.get("candidates"):
        items = [f"[{m['kind']}] {m['chars']} 字符（流程 {m['hits']} / 事实 {m['fact_hits']}）: "
                 f"{m['head']}…" for m in mig["candidates"]]
        items.append(f"仅按【整条可迁】{mig['whole']} 条保守估算：占用 {mem.get('pct')}% → "
                     f"**{mig['pct_after']}%**（释放 {mig['chars_freed']} 字符）；"
                     f"另 {mig['mixed']} 条为混合，需拆分（事实留、流程迁）")
        s.append(("🟡 迁移候选（memory → skill）", items))
    if kb.get("orphans") and not kb.get("merge_pairs"):
        art = sum(1 for x in (kb.get("sample_orphans") or []) if "arxiv:" in x.lower())
        s.append(("🟢 孤点合并", [
            f"近名合并 0 对（抽样 {len(kb.get('sample_orphans') or [])} 个孤点，"
            f"其中 {art} 个是带 arXiv 号的论文实体）",
            "→ 论文实体名字天然不相似，合并规则无效；应改为按 arXiv 号/主题连 RELATED_TO"]))
    if kb.get("merge_pairs"):
        s.append(("🟢 孤点合并", [
            f"{x['ratio']}: {x['a']}  ⇄  {x['b']}" for x in kb["merge_pairs"]]))
    if st1.get("near_duplicates"):
        s.append(("🟡 去重", [f"{len(st1['near_duplicates'])} 对近似条目，考虑合并"]))
    if kb.get("orphans"):
        s.append(("🟢 知识库", [
            f"{kb['orphans']} 个孤点（{kb['orphan_pct']}%）—— 未被任何关系引用",
            "建议: 补 RELATED_TO 或在归档条目中显式引用",
        ]))
    if st1.get("cache", {}).get("stale_facts"):
        s.append(("🟢 缓存", [f"{st1['cache']['stale_facts']} 条 fact 从未访问，可降级"]))
    if not s:
        s.append(("✅ 无异常", ["各项指标正常，无需动作"]))
    return s


def main():
    print("=" * 62)
    print("🧠 睡眠记忆巩固 v3 — 真数据源 + 迁移候选/孤点合并 (MEMORY.md / USER.md / KB)")
    print(f"   执行时间: {datetime.now().isoformat(timespec='seconds')}")
    print("=" * 62)

    log("Stage 1: 记忆分析（真数据源）...")
    st1 = stage1()
    m = st1.get("memory", {})
    log(f"  数据源: {', '.join(st1['sources_found']) or '(无)'}")
    if m:
        log(f"  MEMORY.md: {m['chars']} 字符 / {m['limit']} = {m['pct']}% · "
            f"{m['entries']} 条目 · {len(m['sections'])} 段")
    if st1["integrity"]:
        i = st1["integrity"]
        log(f"  完整性 vs {i['backup']}: {i['chars_backup']} → {i['chars_now']} 字符"
            f" (Δ{i['delta']:+d}) · 丢段 {len(i['lost_sections'])}")
    if st1["kb"]:
        log(f"  KB: {st1['kb']['entities']} 实体 / {st1['kb']['relationships']} 关系 / "
            f"孤点 {st1['kb']['orphans']}")
    for f in st1["findings"]:
        log(f"  → {f}")

    log("Stage 2: Dreaming（由统计推导建议）...")
    suggestions = stage2(st1)

    dreaming_output = OUTPUT_DIR / f"dreaming_{datetime.now().strftime('%Y%m%d')}.md"
    dreaming_output.parent.mkdir(parents=True, exist_ok=True)
    L = [f"# 🧠 睡眠巩固 Dreaming 报告 ({datetime.now().strftime('%Y-%m-%d')})", ""]
    L += ["## Stage 1: 记忆分析（真数据源）", "",
          f"- 数据源: {', '.join(st1['sources_found']) or '(无)'}"]
    if m:
        L += [f"- MEMORY.md: **{m['chars']}** / {m['limit']} 字符（{m['pct']}%）· {m['entries']} 条目"]
    if st1.get("user"):
        u = st1["user"]
        L += [f"- USER.md: {u['chars']} / {u['limit']} 字符（{u['pct']}%）"]
    if st1["integrity"]:
        i = st1["integrity"]
        L += ["", "### ⚠️ 记忆完整性",
              f"- 对比基线 `{i['backup']}`（来源: {i.get('baseline_src', '?')}）",
              f"- 字符: {i['chars_backup']} → {i['chars_now']}（**Δ{i['delta']:+d}**）",
              f"- 增行 {i['lines_added']} / 删行 {i['lines_removed']}",
              f"- 丢失段: **{', '.join(i['lost_sections']) or '无'}**",
              f"- 新增段: {', '.join(i['added_sections']) or '无'}"]
    if st1["kb"]:
        k = st1["kb"]
        L += ["", "### 知识库",
              f"- 实体 {k['entities']} · 关系 {k['relationships']} · 孤点 {k['orphans']}（{k['orphan_pct']}%）"]
    if (st1.get("migration") or {}).get("candidates"):
        mg = st1["migration"]
        L += ["", "### 迁移候选（memory → skill）",
              f"- 整条可迁 **{mg['whole']}** 条 / 混合需拆分 **{mg['mixed']}** 条",
              f"- 保守释放 **{mg['chars_freed']}** 字符 ⇒ 占用 {m['pct']}% → **{mg['pct_after']}%**"]
        for x in mg["candidates"]:
            L += [f"- [{x['kind']}] {x['chars']} 字符 · 流程 {x['hits']} / 事实 {x['fact_hits']}: "
                  f"{x['head']}…"]
    if (st1.get("kb") or {}).get("merge_pairs"):
        L += ["", "### 孤点合并候选"]
        for x in st1["kb"]["merge_pairs"]:
            L += [f"- {x['ratio']}: {x['a']}  ⇄  {x['b']}"]
    if st1["near_duplicates"]:
        L += ["", "### 近似重复条目"]
        for d in st1["near_duplicates"][:8]:
            L += [f"- {d['ratio']}: {d['a']}  ⇄  {d['b']}"]
    L += ["", "## Stage 2: Dreaming 建议（由上述统计推导）", ""]
    for title, items in suggestions:
        L += [f"### {title}"] + [f"- {x}" for x in items] + [""]
    L += ["---", "*自动生成于睡眠巩固 v3（只读分析，不修改任何存储）*"]
    dreaming_output.write_text("\n".join(L), encoding="utf-8")
    log(f"  Dreaming 报告: {dreaming_output}")

    if st1["errors"] and not st1["sources_found"]:
        status = "error"
    elif st1.get("integrity", {}).get("lost_sections"):
        status = "warning"
    elif st1["findings"]:
        status = "ok_with_findings"
    else:
        status = "ok"

    report = {
        "version": "v3",
        "timestamp": datetime.now().isoformat(),
        "algorithms": ["Sleep Memory Consolidation v2 (arXiv 2606.03979, 接真数据源)",
                       "Daydreaming Context Denoising (arXiv 2604.19258)"],
        "sources_found": st1["sources_found"],
        "stage1_memory": st1["memory"],
        "stage1_user": st1["user"],
        "stage1_kb": st1["kb"],
        "stage1_cache": st1["cache"],
        "stage1_integrity": st1["integrity"],
        "stage1_near_duplicates": len(st1["near_duplicates"]),
        "stage1_migration": st1.get("migration", {}),
        "stage1_orphan_merge": (st1.get("kb") or {}).get("merge_pairs", []),
        "findings": st1["findings"],
        "suggestions": [{"title": t, "items": i} for t, i in suggestions],
        "stage2_dreaming": {"output_file": str(dreaming_output)},
        "errors": st1["errors"],
        "status": status,
    }
    rp = OUTPUT_DIR / f"sleep_consolidation_{datetime.now().strftime('%Y%m%d')}.json"
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"✅ 睡眠巩固 v3 完成 · status={status}")
    print(f"   发现 {len(st1['findings'])} 条 · 建议 {sum(len(i) for _, i in suggestions)} 条")
    print(f"   报告: {rp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
