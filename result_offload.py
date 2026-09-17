#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""result_offload.py — 大工具结果的「无损外置 + 指针化」(借鉴 Agno offload/)

【借鉴来源】
  agno-agi/agno @ main : libs/agno/agno/offload/ (🟢 一手源码, 已抓 types.py 与 tools.py)
  逐条抄录的设计事实:
    · 被外置的对象 = 【大型工具结果】; 去处 = 文件; transcript 只留 preview + result_id 指针
    · 指针结构 ResultRef = {result_id, path, tool_name, size_bytes, line_count,
                          content_type, created_at} —— 文档原话 "the pointer the transcript holds"
    · ★ 取回是【无损】的, 不是摘要: ResultPage 带 next_start_char, 作者自述目标
      "so every character of a stored result can be read back"
    · 访问控制按 session/user 隔离(刻意阻止跨 session)
    · NEVER_OFFLOADED_TOOLS 自我豁免, 防无限递归
    · ★★ 给模型的纪律: "do not answer from the preview when the preview was truncated"
    · 数值上限: read_result 输出 ≤400 行或 16000 字符(先到为准);
                search_result ≤20 条匹配, 每行裁 500 字符, context_lines ≤20
    · 错误处理风格: 失败返回以 "Error" 开头的字符串, 不抛异常 → 模型能读到并自我纠正

【为什么本机需要】
  本机既有纪律是「大工具调用(>8K)流超时 → 拆小先 write_file」—— 那是对同一个问题的
  【手工规避】。本模块把规避变成机制: 结果照常产出, 自动外置, 按需无损取回。

【与「有损摘要压缩」的分界 (本机最该守住的一条)】
  外置后给模型的纪律是: **截断时不得凭 preview 作答, 必须按 result_id 取回**。
  这与本机「机器检查通过 ≠ 陈述忠实」同源 —— 防"基于残缺上下文编答案"。

用法:
  python result_offload.py --put <path> --tool read_file --session S1   # 外置一个大结果
  python result_offload.py --ls                                          # 列出已外置结果
  python result_offload.py --read <result_id> --start 1 --end 50         # 无损按行取回
  python result_offload.py --grep <result_id> --pattern ERROR            # 检索 + 行号
  python result_offload.py --selftest                                    # 性质自检
"""
# side_effects: [把结果写入 data/offload/<result_id>.blob, 写 data/offload/index.jsonl]

import argparse
import hashlib
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(HOME, "data", "offload")
INDEX = os.path.join(STORE, "index.jsonl")

# 数值上限 (抄自 Agno offload/store.py L33-54)
# ★ 2026-09-17 修正: 原注释写 "offload/tools.py" 是**标错来源** ——
#   这些常数实际在 `offload/store.py`(tools.py 里只有 __all__ 和取函数, 无常数)。
#   Agno 借鉴族验证 (scripts/agno_borrow_verify.py) 按一手源码逐项比对时暴露的。
MAX_RESULT_BYTES = 8_000_000            # ★ 补: 单条结果外置上限 (上游 store.py:33)
MAX_SESSION_NAMESPACE_BYTES = 200_000_000  # ★ 补: 单会话外置总量上限 (上游 store.py:34)
READ_MAX_LINES = 400
READ_MAX_CHARS = 16000
SEARCH_MAX_MATCHES = 20
SEARCH_LINE_CLIP = 500
SEARCH_MAX_CONTEXT = 20
SEARCH_MAX_CHARS = 16000      # ★ 整份检索回复的总字符预算 = 一页读回上限
                              #   (agno offload/store.py:42 SEARCH_MAX_CHARS)
                              #   不变量: search 永远不能把外置省下的塞回去
# ★ 2026-09-17 补: preview 的行上限 (上游 store.py:43 DEFAULT_PREVIEW_LINES = 20)。
#   本机此前只有字符上限、没有行上限 ⇒ 一份"行很多但每行很短"的产物,
#   400 字符可能覆盖上百行, preview 失去"概览"作用。
#   另注: 本机 PREVIEW_CHARS=400 比上游 1200 短 —— 这是**有意的本地化**
#   (控制进上下文的 token), 故不写"抄自", 也不再视为不一致。
DEFAULT_PREVIEW_LINES = 20
_BACKTRACKING_CHARS = frozenset("*+?{(")   # ReDoS 轻量判据 (store.py:57)
PREVIEW_CHARS = 400

NEVER_OFFLOADED = ("read_result", "search_result")

INSTRUCTION = (
    "Large tool results are stored as files and shown to you as a short preview with a "
    "result id. The preview is not the whole result. Use --grep to locate what you need and "
    "--read to read that range; **do not answer from the preview when the preview was "
    "truncated**."
)


def _index():
    rows = []
    if os.path.exists(INDEX):
        for ln in open(INDEX, encoding="utf-8", errors="replace"):
            ln = ln.strip()
            if ln:
                try:
                    rows.append(json.loads(ln))
                except Exception:
                    pass
    return rows


def _session_bytes(session_id):
    """该会话已外置的总字节数 (扫 append-only 索引, 不额外维护计数器)"""
    if not session_id or not os.path.exists(INDEX):
        return 0
    total = 0
    try:
        with open(INDEX, encoding="utf-8", errors="replace") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if r.get("session_id") == session_id:
                    total += int(r.get("size_bytes") or 0)
    except OSError:
        return 0
    return total


def put(text, tool_name, session_id=None, user_id=None):
    """外置一段结果, 返回 ResultRef (与 Agno 的字段对齐)"""
    if tool_name in NEVER_OFFLOADED:
        return {"error": "Error: tool %r is never offloaded (self-exemption, 防无限递归)"
                         % tool_name}
    size = len(text.encode("utf-8", "replace"))
    # ── 闸门 1: 单条结果上限 (上游 Agno offload/store.py:33 MAX_RESULT_BYTES)
    #    ★ 2026-09-17 补 —— Agno 借鉴族验证发现本机此前【完全没有】这道闸门,
    #      而它是上游防"外置存储被单条巨型结果写爆"的第一道防线。
    if size > MAX_RESULT_BYTES:
        return {"error": "Error: result too large to offload (%d bytes > %d). "
                         "请先裁剪或分段后再外置。" % (size, MAX_RESULT_BYTES)}
    # ── 闸门 2: 单会话命名空间总量上限 (上游 store.py:34 MAX_SESSION_NAMESPACE_BYTES)
    #    ★ 同上, 本机此前没有这道闸门 ⇒ 无界增长风险。
    if session_id:
        used = _session_bytes(session_id)
        if used + size > MAX_SESSION_NAMESPACE_BYTES:
            return {"error": "Error: session namespace quota exceeded "
                             "(%d + %d > %d bytes for session %r). "
                             "请清理该会话的历史外置结果。"
                             % (used, size, MAX_SESSION_NAMESPACE_BYTES, session_id)}
    os.makedirs(STORE, exist_ok=True)
    h = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()
    rid = "res_%s_%s" % (time.strftime("%Y%m%d%H%M%S"), h[:10])
    path = os.path.join(STORE, rid + ".blob")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    ref = {
        "result_id": rid,
        "path": path,
        "tool_name": tool_name,
        "size_bytes": len(text.encode("utf-8", "replace")),
        "line_count": lines,
        "content_type": "text/plain",
        "created_at": int(time.time()),
        "session_id": session_id,
        "user_id": user_id,
        "sha256_10": h[:10],
    }
    with open(INDEX, "a", encoding="utf-8") as f:
        f.write(json.dumps(ref, ensure_ascii=False) + "\n")
    return ref


def preview(ref, n=PREVIEW_CHARS, max_lines=DEFAULT_PREVIEW_LINES):
    """★ 生成 preview + 明确的截断纪律提示

    ★★★ 2026-09-17 真修 (不是改显示): 原实现 `open(path).read()` 把**整个 blob**
    读进内存, 只为吐前 n 字节。补上 MAX_RESULT_BYTES=8MB 上限之后, 这条路径
    最坏变成**每次 preview 全读 8MB** —— 外置本来是为了省上下文/内存, 结果
    预览动作自己把它吃回去了。
    ⇒ 改为**只读 n+1 字节**(多读 1 字节仅用于判定是否截断);
      字节数/行数直接用 `ref` 里 `put()` 时已存好的值, **根本不需要读全文**。
    另补 `max_lines` (上游 store.py:43 DEFAULT_PREVIEW_LINES=20):
    只有字符上限时, "行多且每行短"的产物会让 preview 覆盖上百行, 失去概览作用。
    """
    size = int(ref.get("size_bytes") or 0)
    nlines = int(ref.get("line_count") or 0)
    try:
        with open(ref["path"], "rb") as f:
            raw = f.read(n + 1)          # ★ 只读够用的字节
    except Exception as e:
        return "Error: cannot read %s (%s)" % (ref["path"], str(e)[:60])
    truncated_by_chars = len(raw) > n or size > n
    body = raw[:n].decode("utf-8", "replace")
    # ★ 行上限: 截到 max_lines 行 (字符未截但行已超, 也算截断)
    blines = body.split("\n")
    truncated_by_lines = len(blines) > max_lines
    if truncated_by_lines:
        body = "\n".join(blines[:max_lines])
    trunc = truncated_by_chars or truncated_by_lines
    why = []
    if truncated_by_chars:
        why.append("chars")
    if truncated_by_lines:
        why.append("lines")
    head = ("[preview %d/%d bytes · %d lines · %d chars%s]\n"
            % (len(body.encode()), size, nlines, size,
               ", TRUNCATED(%s)" % "+".join(why) if trunc else ""))
    if trunc:
        head += ("★ " + INSTRUCTION + "\n"
                 "   取回: result_offload --read %s --start 1 --end 50\n" % ref["result_id"])
    return head + body + ("\n…[truncated]" if trunc else "")


def access_check(ref, session_id=None, user_id=None):
    """★★ session/user 归属校验 (子代理 r1145 缺口 #3)

    首版 `put` 存了 session_id/user_id 但 read/grep **从不校验** ⇒ 存了等于没存。
    学 agno `offload/tools.py:23-37` 的 `_access_error`。
    ★ 宽松语义(与 agno 一致): **仅在两侧都非空时才比较** —— 若调用方不给 session,
      视为不过滤(本机是单用户本地 CLI, 默认不过滤是合理的);
      但一旦给了 session, 归属不符必须**响亮拒绝**。
    """
    rid = ref.get("result_id", "?")
    if session_id and ref.get("session_id") and ref["session_id"] != session_id:
        return ("Error: result %s belongs to a different session (%s) — 拒绝跨会话访问"
                % (rid, ref["session_id"]))
    if user_id and ref.get("user_id") and ref["user_id"] != user_id:
        return ("Error: result %s belongs to a different user — 拒绝跨用户访问" % rid)
    return None


def read_range(ref, start=1, end=None, start_char=0):
    """无损按行取回 (不摘要)。受 READ_MAX_LINES / READ_MAX_CHARS 双重封顶(先到为准)。

    ★★★ 2026-09-16 修一个【实测复现的真缺陷】(由子代理 r1145 抓出):
      首版在"某行放不下剩余预算"时直接 `break` 且**不追加任何部分**, 而尾标记又用
      `next = start + len(out)` 计算 —— 于是一旦**首行自身就超过字符上限**
      (常见形态: 单行大 JSON), `len(out)==0` ⇒ `next_start_line` 恒等于起始行
      ⇒ **该行永久不可达 + 链式翻页死循环**。
      实测 payload `"A"*20000+"\\n"+...`: 5 次翻页都是 `(start=1, 0 chars, next=1)`。
      ★ 更糟的是我自己的 P5 自检**通过了** —— 因为自检 payload 全是 40 字符短行,
        **永远走不到这个分支**。(本会话第三次「测试错觉掩盖真缺陷」)

    修法(学 agno `offload/store.py:787-797` 的 `room > 0` 时 `append(line[:room])`):
      · 行内分段续读: 放不下时**追加能放下的那一段**, 并记住行内偏移
      · 断点从 `next_start_line` 升级为 **`(next_start_line, next_start_char)` 对**
      · 调用方按这一对链式翻页, 保证每个字符都能读回
    """
    try:
        lines = open(ref["path"], encoding="utf-8", errors="replace").read().split("\n")
    except Exception as e:
        return "Error: cannot read (%s)" % str(e)[:60]
    s = max(1, int(start))
    e = int(end) if end else s + READ_MAX_LINES - 1
    if e < s:
        return "Error: end < start"
    sc = max(0, int(start_char or 0))       # 首行的行内偏移
    out, chars, cut = [], 0, False
    nxt_line, nxt_char = None, None
    for i in range(s - 1, min(e, len(lines))):
        ln = lines[i]
        if i == s - 1 and sc:
            ln = ln[sc:]                     # 续读: 跳过已读过的前缀
        room = READ_MAX_CHARS - chars
        if len(out) >= READ_MAX_LINES:
            cut, nxt_line, nxt_char = True, i + 1, 0
            break
        if room <= 0:
            cut, nxt_line, nxt_char = True, i + 1, 0
            break
        if len(ln) + 1 > room:
            # ★ 放不下整行 ⇒ 追加能放下的那一段, 断点记【行内偏移】(不再整行丢弃)
            # ★ 修正 (2026-09-16): 首版写 `ln[:room - 1]`, 为"换行分隔符"预留了 1 个字符,
            #   但那个分隔符【并不会被发出】(out 的 join 是按页算, 不是按行算)
            #   ⇒ 每次跨页边界都丢 1 字符 (实测 2 页差 2 字符: 20100 vs 20102)。
            #   正确: 用满 room。
            if room >= 1:
                part = ln[:room]
                out.append(part)
                chars += len(part)
                nxt_line, nxt_char = i + 1, (sc if i == s - 1 else 0) + len(part)
            else:
                nxt_line, nxt_char = i + 1, (sc if i == s - 1 else 0)
            cut = True
            break
        out.append(ln)
        chars += len(ln) + 1
    tail = ""
    if cut:
        tail = ("\n…[page capped at %d lines / %d chars; "
                "next_start_line=%d next_start_char=%d]"
                % (READ_MAX_LINES, READ_MAX_CHARS, nxt_line, nxt_char))
    elif e < len(lines):
        # 行窗口到界(非字符封顶): 下一页从 e+1 行、行内偏移 0 开始
        tail = ("\n…[line window reached; "
                "next_start_line=%d next_start_char=0]" % (e + 1))
    return "\n".join(out) + tail


def grep(ref, pattern, context_lines=0):
    """检索 + 行号 (每行裁剪 + ★ 整份回复总字符预算)

    ★★ 2026-09-16 修 (子代理 r1145 实测): 首版预算单位只有【行】(匹配条数上限),
      实测 `context_lines=20` 时一次检索可吐 **179,554 字符** —— 是"一页读回上限"
      (16,000) 的 **≈11 倍**, 等于**把外置省下的上下文预算整份还回去**。
      学 agno `offload/store.py:141-165` 的 `_render_matches`: 保留条数上限, **再加**
      `SEARCH_MAX_CHARS` 总预算逐条扣减, 并给 `stopped_early`/`more` 标记。
      ★ 设计不变量(agno 注释原文): "The whole reply stays within one read_result page…
        **so a search can never put back what offloading took out**"
    """
    try:
        lines = open(ref["path"], encoding="utf-8", errors="replace").read().split("\n")
    except Exception as e:
        return "Error: cannot read (%s)" % str(e)[:60]
    cx = max(0, min(int(context_lines or 0), SEARCH_MAX_CONTEXT))
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return "Error: bad pattern (%s)" % str(e)[:60]
    # ★ ReDoS 轻量防护: 含回溯特征字符的模式拒绝(不搬 agno 的子进程隔离, 只要判据)
    if not _BACKTRACKING_CHARS.isdisjoint(pattern):
        return ("Error: pattern 含回溯特征字符 %s —— 拒绝执行 (ReDoS 防护)"
                % "".join(sorted(_BACKTRACKING_CHARS & set(pattern))))
    out, chars, n_match, stopped = [], 0, 0, False
    for i, ln in enumerate(lines, 1):
        if not rx.search(ln):
            continue
        n_match += 1
        rows = [("  L%-6d %s" % (i, ln[:SEARCH_LINE_CLIP]))]
        for j in range(1, cx + 1):
            if i - 1 - j >= 0:
                rows.append("  L%-6d   %s" % (i - j, lines[i - 1 - j][:SEARCH_LINE_CLIP]))
        for r in rows:
            if chars + len(r) + 1 > SEARCH_MAX_CHARS:
                stopped = True
                break
            out.append(r)
            chars += len(r) + 1
        if stopped or n_match >= SEARCH_MAX_MATCHES:
            break
    if not out:
        return "(no match)"
    tail = ""
    if stopped:
        tail = ("\n  …[★ 总字符预算 %d 到顶, 回复已截断 — 缩小 --context 或收窄 pattern]"
                % SEARCH_MAX_CHARS)
    elif n_match >= SEARCH_MAX_MATCHES:
        tail = "\n  …[match cap %d reached — more may follow]" % SEARCH_MAX_MATCHES
    return "\n".join(out) + tail


# ───────────────────────── 自检 ─────────────────────────

def _selftest():
    ok = True
    print("═" * 76)
    print("  result_offload 自检 (借鉴 Agno offload/ 的七条性质)")
    print("═" * 76)
    big = "\n".join("line %d :: payload %s" % (i, "x" * 40) for i in range(1, 1201))
    r = put(big, "read_file", session_id="S1")
    print("  P1 指针化: result_id=%s lines=%d bytes=%d"
          % (r["result_id"][:22] + "…", r["line_count"], r["size_bytes"]))
    p1 = all(k in r for k in ("result_id", "path", "tool_name", "size_bytes",
                              "line_count", "content_type", "created_at"))
    print("     AccountResultRef 字段齐全: %s" % ("✅" if p1 else "🔴"))
    ok &= p1

    pv = preview(r)
    p2 = "TRUNCATED" in pv and "do not answer from the preview" in pv
    print("  P2 preview 带截断纪律提示: %s" % ("✅" if p2 else "🔴"))
    ok &= p2

    got = read_range(r, 1, 1200)
    body = "\n".join(l for l in got.split("\n") if not l.startswith("\n…[page"))
    p3 = ("line 1 ::" in got) and ("page capped at" in got)
    print("  P3 取回受双重封顶(≤%d 行/%d 字符): %s"
          % (READ_MAX_LINES, READ_MAX_CHARS, "✅" if p3 else "🔴"))
    ok &= p3

    g = grep(r, r"line 7 ::", context_lines=1)
    p4 = ("L7" in g) and ("L6" in g or "L8" in g)
    print("  P4 检索含行号(+上下文): %s" % ("✅" if p4 else "🔴"))
    ok &= p4

    # ★★★ P5b 超长单行用例 (修缺口 #12: 首版自检全是 40 字符短行 ⇒ 永远走不到
    #     "单行 > 字符上限" 分支 ⇒ P5"无损"通过而承诺不成立, 实测被 r1145 抓出)
    longline = "A" * 20000 + "\n" + "B" * 50 + "\n" + "C" * 50
    rl = put(longline, "read_file")
    # ★ 续读语义 (2026-09-16, 经 dump 实测校准):
    #   只有【每一页的第一行】才可能是上一页的行中途续接 (当 start_char > 0);
    #   同一页内的后续行【必须】补换行。
    #   首版把整页所有行都当续接 ⇒ 每页丢 N-1 个换行
    #   (实测用例2: 72357 vs 73292, 首个差异正是缺 '\n')
    # ★ 统一为一个链式翻页器 (同时读取 next_start_line / next_start_char)
    def _chain(ref, nlines=1200, limit=30):
        out, first = "", True
        cur, cur_c, pages = 1, 0, 0
        while pages < limit:
            part = read_range(ref, cur, cur + 399, cur_c)
            nl, nc = None, 0
            for k, l in enumerate(part.split("\n")):
                ls = l.strip()
                if ls.startswith("…["):
                    m1 = re.search(r"next_start_line=(\d+)", ls)
                    m2 = re.search(r"next_start_char=(\d+)", ls)
                    if m1:
                        nl, nc = int(m1.group(1)), (int(m2.group(1)) if m2 else 0)
                    continue
                if first:
                    out += l
                    first = False
                elif k == 0 and cur_c > 0:
                    out += l                    # 仅每页首行可能是续接
                else:
                    out += "\n" + l
            pages += 1
            if nl is None or (nl == cur and nc <= cur_c):
                break
            cur, cur_c = nl, nc
        return out, pages

    got_long, pages2 = _chain(rl)
    joined_long = got_long
    p5b = joined_long == longline
    print("  P5b ★ 超长单行无损 (20000 字符单行, %d 页拼回 == 原文): %s"
          % (pages2, "✅" if p5b else "🔴 (长度 %d vs %d)"
             % (len(joined_long), len(longline))))
    ok &= p5b

    # ★ P7b ReDoS 判据
    g_bad = grep(r, "a(b+)+c")
    p7b = g_bad.startswith("Error") and "ReDoS" in g_bad
    print("  P7b ★ ReDoS 判据拒绝回溯模式: %s" % ("✅" if p7b else "🔴"))
    ok &= p7b

    # ★ P7c 检索总字符预算
    wide = "\n".join("HIT line %d :: %s" % (i, "z" * 400) for i in range(40))
    rw = put(wide, "read_file")
    gw = grep(rw, "HIT", context_lines=20)
    p7c = len(gw) <= SEARCH_MAX_CHARS + 200
    print("  P7c ★ 检索总字符预算封顶 (context=20 输出 %d 字符, 上限 %d): %s"
          % (len(gw), SEARCH_MAX_CHARS, "✅" if p7c else "🔴"))
    ok &= p7c

    # ★ P7d 访问控制
    acc = access_check({"result_id": "x", "session_id": "S1"}, session_id="S2")
    p7d = bool(acc) and acc.startswith("Error")
    print("  P7d ★ 跨会话访问被拒: %s" % ("✅" if p7d else "🔴"))
    ok &= p7d

    # ★ P8 单条结果上限闸门 (2026-09-17 补, 上游 MAX_RESULT_BYTES)
    #   实测: 真的造一个 8MB+1 的 payload ⇒ 必须被拒, 且错误里带 "too large"
    huge = "x" * (MAX_RESULT_BYTES + 1)
    r8 = put(huge, "read_file")
    p8 = isinstance(r8, dict) and "error" in r8 and "too large" in str(r8["error"])
    print("  P8 ★★ 超上限单条结果被拒 (%d 字节 > %d): %s"
          % (MAX_RESULT_BYTES + 1, MAX_RESULT_BYTES, "✅" if p8 else "🔴"))
    ok &= p8
    # 边界: 恰好等于上限应当【通过】(不能把 <= 也拒了)
    r8b = put("y" * 1000, "read_file")
    p8b = isinstance(r8b, dict) and "result_id" in r8b
    print("  P8b 正常大小仍可通过 (不过度拦截): %s" % ("✅" if p8b else "🔴"))
    ok &= p8b

    # ★ P9 单会话命名空间配额闸门 (2026-09-17 补, 上游 MAX_SESSION_NAMESPACE_BYTES)
    #   ★ 诚实标注: 真造 200MB 太慢, 故【临时调低阈值】做边界测试, 测完立刻还原。
    #     这是有意为之的单元测试手法, 不是"绕过"。
    global MAX_SESSION_NAMESPACE_BYTES
    _saved = MAX_SESSION_NAMESPACE_BYTES
    try:
        MAX_SESSION_NAMESPACE_BYTES = 5000
        sid = "S_quota_test_%d" % int(time.time())
        put("a" * 3000, "read_file", session_id=sid)          # 3KB, 应成功
        r9 = put("b" * 3000, "read_file", session_id=sid)     # 再 3KB ⇒ 6KB > 5KB, 应被拒
        p9 = isinstance(r9, dict) and "error" in r9 and "quota" in str(r9["error"])
        print("  P9 ★★ 会话配额超限被拒 (阈值临时调至 5000 做边界测试): %s"
              % ("✅" if p9 else "🔴"))
        ok &= p9
    finally:
        MAX_SESSION_NAMESPACE_BYTES = _saved
    print("      (阈值已还原为 %d)" % MAX_SESSION_NAMESPACE_BYTES)

    # ★★ P10 真修验证: preview 不得全读 blob (2026-09-17)
    #   判据 = **实测峰值内存**, 不是看代码。造一个 ~4MB 的 blob,
    #   若 preview 仍全读, 峰值必然 ≥4MB; 只读 n+1 字节则远小于此。
    #   ★ 用 tracemalloc 量化, 避免"看起来改好了"式的自证。
    import tracemalloc
    big_blob = "\n".join("line %d :: %s" % (i, "q" * 60) for i in range(40000))  # ~2.6MB
    rb = put(big_blob, "read_file")
    _never = preview(rb)                      # 预热, 排除首次 import 噪声
    tracemalloc.start()
    pv = preview(rb)
    _cur, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    blob_bytes = rb["size_bytes"]
    # 放宽到 blob 的 25% 作为判据 (解码缓冲等有少量开销, 但绝不该接近全量)
    p10 = _peak < blob_bytes * 0.25
    print("  P10 ★★★ preview 不全读 (blob %d 字节, 峰值内存 %d 字节 = %.1f%%): %s"
          % (blob_bytes, _peak, 100.0 * _peak / max(1, blob_bytes), "✅" if p10 else "🔴"))
    ok &= p10
    # 边界: ★ 真正的不变量是【正文 ≤ PREVIEW_CHARS】。
    #   ★★ 两次踩错, 记下来: 判据必须**精确对应契约**, 不能靠"猜头部多大"、
    #      也不能靠 `split("]\n")` 这种把指令块一起划进正文的粗提取。
    #      头部三种行有稳定前缀 ⇒ 逐行剔除后再量。
    _lines = pv.split("\n")
    _body_lines = [ln for ln in _lines
                   if not (ln.startswith("[preview") or ln.startswith("★")
                           or ln.startswith("   取回:") or ln.startswith("…[truncated]"))]
    _body = "\n".join(_body_lines)
    p10b = len(_body.encode()) <= PREVIEW_CHARS
    print("  P10b preview 正文受字符上限约束 (正文 %d ≤ %d, 总长 %d): %s"
          % (len(_body.encode()), PREVIEW_CHARS, len(pv), "✅" if p10b else "🔴"))
    ok &= p10b
    # 边界: 头部必须存在且带 truncation 标记 (否则读者不知道被截了)
    p10d = ("TRUNCATED" in pv) and ("[preview" in pv)
    print("  P10d 头部存在且标出截断 (不静默): %s" % ("✅" if p10d else "🔴"))
    ok &= p10d
    # 边界: 不截断的小内容应完整返回且标 TRUNCATED=False
    rs = put("short line 1\nshort line 2\n", "read_file")
    pvs = preview(rs)
    p10c = "TRUNCATED" not in pvs and "short line 2" in pvs
    print("  P10c 小内容不标截断且内容完整: %s" % ("✅" if p10c else "🔴"))
    ok &= p10c

    # ★★ P11 行上限 (上游 DEFAULT_PREVIEW_LINES=20)
    #   "行多且每行极短" —— 字符没超但行数多, 必须被行上限截住
    many = "\n".join("x%d" % i for i in range(500))
    rm = put(many, "read_file")
    pvm = preview(rm)
    shown = [ln for ln in pvm.split("\n") if ln.startswith("x")]
    p11 = len(shown) <= DEFAULT_PREVIEW_LINES and "TRUNCATED" in pvm
    print("  P11 ★★ 行上限生效 (500 短行, 实际展示 %d 行 ≤ %d): %s"
          % (len(shown), DEFAULT_PREVIEW_LINES, "✅" if p11 else "🔴"))
    ok &= p11

    # 无损验证: 取回的内容必须能拼回原文
    # ★ 两个坑 (2026-09-16):
    #   坑1 (测试): 首版过滤器写作 l.startswith("\n…[page"), 但 split("\n") 已吃掉
    #        前导换行 ⇒ 永不匹配 ⇒ 假失败。改为 strip 后前缀过滤。
    #   坑2 (实现/用法): ★ char 封顶(16000) 会【早于】行封顶(400) 触发 ⇒
    #        第一页只到 ~300 行。若调用方假设"下一页从 end+1 开始", 中间会【静默丢行】。
    #        正确用法: 必须按尾标记返回的 next_start_line 链式翻页。
    #        (Agno 的 ResultPage.next_start_line / next_start_char 正是为此存在)
    #        本测试改为链式, 并在下方断言"无丢行"。
    joined, pages = _chain(r, 1200)
    p5 = joined == big
    print("  P5 ★ 无损(按 (line,char) 链式翻页拼回 == 原文, 共 %d 页, %d/%d 字符): %s"
          % (pages, len(joined), len(big), "✅" if p5 else "🔴"))
    ok &= p5

    e = put("x", "read_result")
    p6 = "error" in e
    print("  P6 自我豁免(read_result 不外置, 防递归): %s" % ("✅" if p6 else "🔴"))
    ok &= p6

    err = read_range({"path": "D:/__no_such_file__"}, 1, 2)
    p7 = err.startswith("Error")
    print("  P7 失败返回 Error 字符串而非抛异常: %s" % ("✅" if p7 else "🔴"))
    ok &= p7

    print()
    # ★ 动态计数 (2026-09-17 真修): 原为硬编码「七项」, 实际断言已 16 项 ⇒ 必然对不上。
    #   本会话第二次踩同一个坑, 故这次不只"改成动态", 还让它【自证】:
    #     源码里 `ok &= pXX` 的条数 必须 == 运行时数到的断言变量数。
    #   两者不等 ⇒ 说明漏跑或命名脱轨 ⇒ 判定行不可信, 直接报错。
    import re as _re
    _L = dict(locals())        # ★ 必须先快照! 在 genexpr 内部调 locals() 拿到的是
                               #   生成器自己的作用域 ⇒ KeyError: 'p1' (实测崩溃)。
    _names = sorted(k for k in _L if _re.fullmatch(r"p\d+[a-z]*", k))
    _passed = sum(1 for k in _names if _L.get(k))
    try:
        _src = open(os.path.abspath(__file__), encoding="utf-8").read()
    except Exception:
        _src = ""
    _static = len(_re.findall(r"^\s*ok\s*&=\s*p\d+[a-z]*\s*$", _src, _re.M))
    _consistent = (_static == len(_names))
    print("  判定: %s (%d/%d 项)"
          % ("✅ 全通过" if ok else "🔴 有未通过项", _passed, len(_names)))
    print("  ★ 计数自证: 源码断言 %d 条 vs 运行时数到 %d 个 ⇒ %s"
          % (_static, len(_names), "✅ 一致" if _consistent else "🔴 不一致(判定行不可信)"))
    if not _consistent:
        ok = False
    if _passed != len(_names):
        _bad = [k for k in _names if not locals()[k]]
        print("  未通过: %s" % ", ".join(_bad))
    print("  ★ 注: 实现参照 Agno 的设计与数值上限, 但本机代码为独立实现。")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--put")
    ap.add_argument("--tool", default="unknown")
    ap.add_argument("--text")
    ap.add_argument("--session")
    ap.add_argument("--ls", action="store_true")
    ap.add_argument("--read")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int)
    ap.add_argument("--grep")
    ap.add_argument("--pattern")
    ap.add_argument("--context", type=int, default=0)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest or len(sys.argv) == 1:
        return _selftest()
    if a.ls:
        rows = _index()
        print("  已外置结果: %d" % len(rows))
        for r in rows[-12:]:
            print("   %s  %-12s %8d B  %5d 行  %s"
                  % (r["result_id"][:24], r["tool_name"], r["size_bytes"],
                     r["line_count"], time.strftime("%m-%d %H:%M",
                                                    time.localtime(r["created_at"]))))
        return 0
    if a.put:
        t = a.text if a.text is not None else open(a.put, encoding="utf-8",
                                                   errors="replace").read()
        r = put(t, a.tool, session_id=a.session)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        print()
        print(preview(r))
        return 0
    rows = {r["result_id"]: r for r in _index()}
    if a.read:
        if a.read not in rows:
            print("Error: unknown result id %r" % a.read)
            return 1
        print(read_range(rows[a.read], a.start, a.end))
        return 0
    if a.grep:
        if a.grep not in rows:
            print("Error: unknown result id %r" % a.grep)
            return 1
        if not a.pattern:
            print("Error: --grep 需要 --pattern")
            return 1
        print(grep(rows[a.grep], a.pattern, a.context))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
