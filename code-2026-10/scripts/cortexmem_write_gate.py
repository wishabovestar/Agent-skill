# -*- coding: utf-8 -*-
"""cortexmem_write_gate.py — mybot profile 写入侧门（P0-6 / 蓝图 v2 D13，2026-10-15）

为什么有这个文件
──────────────────────────────────────────────────────────────────────
mybot profile 此前【没有写闸件】⇒ 任何 *dropped*.jsonl 台账都不存在 ⇒
`check_gate_liveness.py <mybot> --glob "*dropped*.jsonl"` 恒报
`⚠️ NO_DATA`（exit 1）—— 无法区分「门在工作」与「门坏了」。
本件把写闸装进 mybot 自己的【唯一写入点】(`cortexmem.py::CortexMem.add()`)。

体系关系（不是替代，是分工；迁移自 qqbot3，复用 memlayer 算法，勿重写）
──────────────────────────────────────────────────────────────────────
  · 本门 = 写入判定闸。算法【不重写】，直接复用 `D:/hermes/data/memlayer/memgate.py`
    （v2 三角色 + 写入闸四项 + M1–M5 不变量 + 近重复 0.70；两个阈值各司其职：
     0.70 = 近乎同一条 ⇒ 拒收 ／ 0.50 = 太像 ⇒ 坍缩告警，禁止合并）。
  · qqbot3 `scripts/cortexmem_write_gate.py` 仅作【结构参考】（fail-open / log 默认 /
    env 回退三件套），其算法在本件由 memgate 承担。

三条安全通道（reason 即通道名，检查器按 reason>verdict>action 取通道）
──────────────────────────────────────────────────────────────────────
  assembly_gate      装配闸  ：type 不在允许集 / content 空 / 前缀指纹撞车但全文不同
                              （后者正是 qqbot3 P0-2 要防的「静默合并」）
  invariant_violation 不变量 ：候选写入使 M1–M5 由【成立 → 不成立】（新增违约才算）
  entry_gate_reject  逐条闸  ：v2 写入闸四项不全（证据等级/否证检查/来源指针/翻转条件）
  （另：near_duplicate 近重复 0.70 ⇒ 检查器归入「近重复通道」，不算非近重复拦截）

安全设计（逐条可核）
──────────────────────────────────────────────────────────────────────
1. ★ fail-open：门内部任何异常 ⇒ 放行。调用方 `cortexmem.add()` 侧亦包 try/except。
   「记忆写不进去」比「重复一条」危险得多。
2. ★ 默认 mode = log（只记录不拦截，action=reject_log）。真拦截需显式
   `CORTEXMEM_WRITE_GATE=suppress`。理由：mybot 侧无测试覆盖，直接 enforce 有
   静默丢内容的风险 ⇒ 先跑真实命中率，再决定 enforce（pre-registered A/B 的 A 臂）。
3. ★ 台账位置对齐 qqbot3 既有约定：`<profile>/knowledge_base/cortexmem/_write_dropped.jsonl`
   （profile 内 ⇒ 检查器的 profile 扫描能真的读到）。
4. ★ 观测失败不得影响主流程：所有落盘 try/except 全吞（同 adapter_cortexmem._record 纪律）。
5. ★ 完全可回退：`CORTEXMEM_WRITE_GATE=off` 即刻回到改造前行为（一行 env，不改文件）；
   另有 `CORTEXMEM_WG_DROPLEDGER=off` 只停台账、判定完全不变
   （命名范式对齐 harness/tools/write_gate.py 的 HERMES_WG_DROPLEDGER）。
6. ★ 放行路径【不写】台账：本文件只记拒收（台账名即 _write_dropped）。
   刻意不记 admit —— 检查器口径缺陷②已实测「无通道字段/admit 被算成拦截 ⇒ 假过线」，
   写 admit 行会自己给自己刷假过线。
7. ★ 写者自证（P0-6 收尾，2026-10-15）：每行附 `writer` / `writer_sha` / `writer_pid`
   —— 证据落在【记录内部】，不再依赖「文件名 ∈ 规范名 且同名唯一」（这两条都可伪造：
   手放一份同名副本，与门写的无法区分）。检查器侧：
   `check_gate_liveness.py --require-writer`（**默认关**）缺 writer_sha ⇒ 报「来源未自证」
   ⇒ 不构成过线证据；并把 writer_sha 与当前门模块 sha256[:16] 逐文件比对
   （不一致 ⇒ 台账来自旧版/异版门）。

用法
──────────────────────────────────────────────────────────────────────
  python cortexmem_write_gate.py --stats          # 门事件统计 + 停摆守卫
  python cortexmem_write_gate.py --report         # ⭐ 留存率明报（只读）：分母/分子/留存率/被拦率 + 按 reason 分组
  python cortexmem_write_gate.py --report --ledger <p> --counters <p> [--json]   # 指定台账（自检/复核用）
  python cortexmem_write_gate.py --selftest          # 只读自检（判定通道四项）
  python cortexmem_write_gate.py --selftest-report   # ⭐ 只读自检（留存率明报：合成台账 + 手算期望 + 必须能失败的反向对照）
  CORTEXMEM_WRITE_GATE=suppress                   # 切真拦截
side_effects: [写 knowledge_base/cortexmem/_write_dropped.jsonl,
               写 knowledge_base/cortexmem/_write_gate_counters.json（计数器，见「留存率明报」）]

留存率明报（2026-10-16 新增，对标 EHRBench「明报 KB 校验前后留存率」）
──────────────────────────────────────────────────────────────────────
  动机：此前只报【最终规模】与门事件数，报不出「分母 = 多少条写入尝试」⇒ 留存率不可追溯
        （论文口径：多数系统只报最终规模；本件明报 留存 = 分子/分母）。
  口径（两个分母都印出来，避免读者自己猜）：
    分母 attempts = 门在 log/suppress 下看到的 add() 调用数（含「精确同 nid 同文」跳过；
                     mode=off 的调用另记 off，不计入分母）
    分子 stored   = attempts − dropped（= 门未拒收的尝试；suppress 下即真落库）
      留存率 = stored / attempts      被拦率 = dropped / attempts
    · dropped = 判定为 reject 的次数；blocked = 真被拦下的次数（仅 suppress）；
    · 台账只记拒收（见安全设计 6），故 attempts 由【计数器】承载 ⇒
      `_write_gate_counters.json`（JSON 覆盖写，非 JSONL、非台账类命名，不会被 *dropped*.jsonl 扫到）。
    · 计数器缺失时退回【纯台账】口径：attempts = 台账 admit 行 + 拒收行（兼容含 admit 行的合成台账）。
  只读保证：--report / retention_report() 不写任何文件、不改判定、不加锁；
  每次写入后的摘要行走 stderr（不污染调用方 stdout），可用 CORTEXMEM_WG_SUMMARY=off|exit 关闭/改时机。
"""
import os, sys, json, time, hashlib, collections, atexit

# ── 自定位（防跨 profile 串档；与 cortexmem.py 同源推导）──────────────
_HERE = os.path.dirname(os.path.abspath(__file__))          # <profile>/scripts
PROFILE = os.path.basename(os.path.dirname(_HERE))          # <profile>
BASE = os.path.dirname(_HERE)                               # <profile>
DATA_DIR = os.environ.get("CORTEXMEM_WG_DATA") or os.path.join(BASE, "knowledge_base", "cortexmem")
DROPPED_LOG = os.path.join(DATA_DIR, "_write_dropped.jsonl")
# ⭐ 留存率明报用的【计数器】（attempts/admitted/dropped/blocked/by_reason…）。
#   ⚠️ 刻意【不叫】*dropped*.jsonl、且是 .json 覆盖写而非 JSONL 追加：
#      避免被 §1b/§4 的台账名扫描当成 name-ambiguous 台账污染（真台账只有 _write_dropped.jsonl）。
COUNTERS_LOG = os.path.join(DATA_DIR, "_write_gate_counters.json")
COUNTERS_SCHEMA = "wg_counters/1.0"

# ── 算法复用件（不重写）：memlayer/memgate.py ────────────────────────
MEMLAYER_DIR = os.environ.get("MEMLAYER_DIR") or r"D:/hermes/data/memlayer"
if MEMLAYER_DIR not in sys.path:
    sys.path.insert(0, MEMLAYER_DIR)
try:
    import memgate
except Exception:                                            # 缺失 ⇒ 降级为空壳（fail-open）
    memgate = None

VALID_MODES = ("off", "log", "suppress")
DEFAULT_MODE = "log"
NODE_TYPES = ("semantic", "episodic", "procedural", "tool_trace")

# ── 校准/边界常量（每条带出处；改前必须先有新的实测记录）───────────────
MIN_LEN = 24            # 短于此不判（对齐 qqbot3 write_gate MIN_LEN=24）
CHANNELS = ("entry_gate_reject", "invariant_violation", "assembly_gate")
NEARDUP_CHANNEL = "near_duplicate"
MAX_NEARDUP_SCAN = 3000  # 近重复扫描上限（取最近 N 节点；本机 mybot 库为空 ⇒ 远未触顶）


# ═══════════════ 模式与回退 ═══════════════
def mode():
    m = (os.environ.get("CORTEXMEM_WRITE_GATE") or DEFAULT_MODE).lower()
    return m if m in VALID_MODES else DEFAULT_MODE


def ledger_enabled():
    return os.environ.get("CORTEXMEM_WG_DROPLEDGER", "on").lower() != "off"


def counters_enabled():
    """计数器/摘要总开关（回退旋钮；off ⇒ 不留新文件、不打摘要，判定完全不变）。"""
    return os.environ.get("CORTEXMEM_WG_COUNTERS", "on").lower() != "off"


def summary_mode():
    """摘要时机：each（每次写入后，默认）| exit（进程退出时一行）| off（不打）。"""
    v = (os.environ.get("CORTEXMEM_WG_SUMMARY") or "each").lower()
    return v if v in ("each", "exit", "off") else "each"


def default_summary():
    """未设置 CORTEXMEM_WG_SUMMARY 时的出厂默认（自检断言用）。"""
    return "each" if not os.environ.get("CORTEXMEM_WG_SUMMARY") else summary_mode()


def enabled():
    return mode() != "off"


# ═══════════════ 台账落盘（只记拒收；观测失败不得影响主流程）═══════════════
def _norm_raw(s):
    return (s or "").strip()


def text_sha(text):
    """规范化全文指纹（对齐 qqbot3 P0-2 侧车字段口径）"""
    h = hashlib.md5(_norm_raw(text).encode("utf-8")).hexdigest()
    return h[:16]


# ── ⭐ 写者自证（P0-6 收尾）：把「谁写的」写进记录内部 ────────────────────
#   动机：检查器的来源判定此前只能到「basename ∈ 规范名 且同名唯一 ⇒ 判为门写的」，
#         而文件名与唯一性都可伪造（手放同名副本 ⇒ 与门写的不可区分）
#         ⇒ 真证据必须在记录内部：writer（模块名）/ writer_sha（写该行时本模块
#           sha256 前 16 位）/ writer_pid。
WRITER = os.path.splitext(os.path.basename(os.path.abspath(__file__)))[0]
_WRITER_SHA_CACHE = {}


def writer_sha(n=16):
    """写该行时【本模块】的 sha256 前 n 位（按 (mtime,size) 缓存；异常返回 None）。

    ⚠️ 自证的是【门模块】而非台账文件：台账是证据，门模块是被证明的对象。
    """
    try:
        p = os.path.abspath(__file__)
        st = os.stat(p)
        key = (p, st.st_mtime_ns, st.st_size, int(n))
        got = _WRITER_SHA_CACHE.get(key)
        if got is None:
            got = hashlib.sha256(open(p, "rb").read()).hexdigest()[:n]
            _WRITER_SHA_CACHE[key] = got
        return got
    except Exception:
        return None


def _drop_record(text, ntype, channel, detail, extra=None):
    """纯追加写一行台账。只由【门本体在拒收时】调用 —— 严禁手写。"""
    if not ledger_enabled():
        return None
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        row = {
            "t": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "iso": time.strftime("%Y-%m-%d %H:%M:%S"),
            "reason": channel,                 # ← 通道名（检查器优先取此字段）
            "verdict": "reject",
            "action": "reject_suppress" if mode() == "suppress" else "reject_log",
            "mode": mode(),
            "profile": PROFILE,
            "writer": WRITER,                  # ← 写者自证（P0-6 收尾）：模块名
            "writer_sha": writer_sha(),        #   写该行时本模块 sha256 前 16 位
            "writer_pid": os.getpid(),         #   写该行的进程 pid
            "ntype": ntype,
            "nid": (extra or {}).get("nid"),
            "sha": text_sha(text),
            "head": _norm_raw(text)[:80],
            "len": len(text or ""),
            "detail": detail[:6] if isinstance(detail, list) else [str(detail)[:200]],
            "sample": {"sha": text_sha(text), "head": _norm_raw(text)[:80],
                       "nid": (extra or {}).get("nid"), "ntype": ntype,
                       "channel": (extra or {}).get("channel"),
                       "len": len(text or "")},
        }
        if extra:
            for k, v in extra.items():
                if k not in row:
                    row[k] = v
        with open(DROPPED_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row
    except Exception:
        return None            # 观测失败不得影响主流程


# ═══════════════ 计数器（留存率明报的分母/分子来源）═══════════════
#   为什么需要：台账（_write_dropped.jsonl）刻意【只记拒收】——写 admit 行会让检查器把
#   admit 算成拦截（已实测的假过线）。但「留存率 = 落库/尝试」缺分母（总尝试数）。
#   故新增【独立计数器】文件：JSON 覆盖写、只存聚合计数（不存内容/不存逐条行）。
#   ★ 与台账解耦：CORTEXMEM_WG_COUNTERS=off 即可停计数器（判定与台账完全不变）。
def _counters_read(path=None):
    """读计数器（缺失/损坏/半写 ⇒ 归零空壳，绝不抛）。纯读，不创建文件。"""
    d = {"schema": COUNTERS_SCHEMA, "attempts": 0, "judged": 0, "admitted": 0,
         "dropped": 0, "blocked": 0, "skipped_exact": 0, "off": 0,
         "by_reason": {}, "by_mode": {}, "first_ts": None, "last_ts": None,
         "last_reason": None, "last_at": None}
    try:
        p = path or COUNTERS_LOG
        if os.path.exists(p):
            got = json.load(open(p, encoding="utf-8"))
            if isinstance(got, dict):
                for k, v in got.items():
                    if k in ("by_reason", "by_mode") and isinstance(v, dict):
                        d[k] = {str(a): int(b) for a, b in v.items()}
                    elif k in d and isinstance(v, (int, float)) and not isinstance(v, bool):
                        d[k] = int(v)
                    elif k in ("first_ts", "last_ts", "last_reason", "last_at") \
                            and (v is None or isinstance(v, str)):
                        d[k] = v
    except Exception:
        pass                     # 计数器读失败 ⇒ 视作空（明报会报「无计数器」而不会崩）
    return d


def _counters_bump(dropped=False, blocked=False, skipped_exact=False, off=False,
                   reason=None):
    """把一次 add() 尝试累加进计数器。★ 绝不抛、绝不改判定/返回值。

    口径：attempts ＝ 门在 log/suppress 下看到的 add() 调用（含精确同 nid 跳过）；
          judged   ⊆ attempts 中真正过 judge() 的；skipped_exact ⊆ 被精确命中跳过的；
          admitted ＋ dropped ＝ attempts；blocked ⊆ dropped 中真被拦的（仅 suppress）；
          off      ＝ mode=off 时的调用（另计，不进分母）。
    先读-改-写 + tmp/os.replace 原子换名；观测失败不得影响主流程。
    """
    if not counters_enabled():
        return None
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        c = _counters_read()
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        if off:
            c["off"] += 1
            c["by_mode"]["off"] = int(c["by_mode"].get("off", 0)) + 1
        else:
            c["attempts"] += 1
            c["by_mode"][mode()] = int(c["by_mode"].get(mode(), 0)) + 1
            if skipped_exact:
                c["skipped_exact"] += 1
            else:
                c["judged"] += 1
            if dropped:
                c["dropped"] += 1
                if blocked:
                    c["blocked"] += 1
                if reason:
                    c["by_reason"][str(reason)] = int(c["by_reason"].get(str(reason), 0)) + 1
            else:
                c["admitted"] += 1
            c["last_reason"] = str(reason) if reason else ("admit" if not dropped else None)
            c["last_at"] = now
        if not c.get("first_ts"):
            c["first_ts"] = now
        c["last_ts"] = now
        tmp = COUNTERS_LOG + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False)
        os.replace(tmp, COUNTERS_LOG)
        return c
    except Exception:
        return None            # 观测失败不得影响主流程


# ═══════════════ 每次写入后的单行摘要（stderr；不改返回值）═══════════════
_SUMMARY_ATEXIT = {"on": False}


def _emit(line):
    """一行摘要 → stderr（不污染调用方 stdout）；任何异常都吞。"""
    try:
        sys.stderr.write(line + "\n")
        sys.stderr.flush()
    except Exception:
        pass


def summary_line(counters_path=None):
    """一行摘要字符串；无尝试 ⇒ None。纯读，不写任何文件。"""
    try:
        c = _counters_read(counters_path)
        n = int(c.get("attempts") or 0)
        if n <= 0:
            return None
        dropped = int(c.get("dropped") or 0)
        stored = n - dropped
        return ("[write-gate] attempts=%d stored=%d retention=%.1f%% dropped=%d "
                "blocked=%d last=%s mode=%s"
                % (n, stored, 100.0 * stored / n, dropped,
                   int(c.get("blocked") or 0), c.get("last_reason") or "-", mode()))
    except Exception:
        return None


def _emit_summary():
    """每次写入后（summary_mode=each）输出一行摘要；只在有新增时打印。"""
    try:
        if not counters_enabled() or summary_mode() == "off":
            return
        if not _SUMMARY_ATEXIT["on"]:
            try:
                atexit.register(_atexit_summary)      # 进程退出时补一行（含 exit 模式）
                _SUMMARY_ATEXIT["on"] = True
            except Exception:
                pass
        if summary_mode() == "each":
            ln = summary_line()
            if ln:
                _emit(ln)
    except Exception:
        pass


def _atexit_summary():
    try:
        if counters_enabled() and summary_mode() != "off":
            ln = summary_line()
            if ln:
                _emit(ln + " (final@exit)")
    except Exception:
        pass


# ═══════════════ 通道① 装配闸 ═══════════════
def check_assembly(text, ntype, nodes, self_nid):
    """装配契约：节点要被装配进三层图的最低结构要求。返回 None=通过 / str=拒绝理由。"""
    if ntype not in NODE_TYPES:
        return ("装配闸: type=%r 不在允许集 %s ⇒ 无法装配进三层图"
                % (ntype, list(NODE_TYPES)))
    if not _norm_raw(text):
        return "装配闸: content 为空/纯空白 ⇒ 无内容可装配"
    ex = nodes.get(self_nid) if nodes else None
    if ex is not None and (ex.get("content") or "") != text:
        return ("装配闸: 前缀指纹撞车 (nid=%s 已存在, 全文不同) ⇒ 若写入即静默合并"
                "两条语义不同的记忆 (qqbot3 P0-2)" % self_nid)
    return None


# ═══════════════ 通道② 跨轮不变量 M1–M5（只算【新增】违约）═══════════════
def _as_entries(nodes):
    out = []
    for nid, n in (nodes or {}).items():
        out.append({"id": nid, "source_ptr": n.get("session_id"),
                    "reopen_if": n.get("reopen_if"), "support": n.get("support") or []})
    return out


def check_invariants(cand_entry, nodes):
    """候选写入使某条不变量从【成立→不成立】= 新增违约 ⇒ 该候选不得写入。"""
    if memgate is None:
        return []
    before = memgate.invariants(_as_entries(nodes))
    after = memgate.invariants(_as_entries(nodes) + [cand_entry])
    bad = [k for k, (ok, _) in after.items()
           if (not ok) and before.get(k, (True, ""))[0]]
    return bad


# ═══════════════ 通道③ 逐条写入闸四项 ═══════════════
def check_entry(text, entry_meta):
    entry = dict(entry_meta or {})
    entry.setdefault("text", text)
    if memgate is None:
        return None, None
    v = memgate.gate_safe(entry)
    if v.get("verdict") == "reject":
        return v, (v.get("reasons") or [])
    return v, None


# ═══════════════ 通道④ 近重复 0.70 ═══════════════
def check_near_dup(text, nodes):
    if memgate is None or len(_norm_raw(text)) < MIN_LEN:
        return None
    items = list((nodes or {}).items())
    if len(items) > MAX_NEARDUP_SCAN:
        items = sorted(items, key=lambda kv: (kv[1].get("last_access") or 0), reverse=True)[:MAX_NEARDUP_SCAN]
    texts = [(n.get("content") or "") for _, n in items]
    nd = memgate.near_dup(text, texts)
    return nd if (nd and nd.get("hit")) else None


# ═══════════════ 判定主体 ═══════════════
def judge(text, ntype, nodes, self_nid, entry_meta=None):
    """返回 dict(verdict, channel, detail, extra)。

    优先级（对齐 harness write_gate.py 的判定次序）：装配 > 不变量 > 逐条闸 > 近重复。
    """
    d = check_assembly(text, ntype, nodes, self_nid)
    if d:
        return {"verdict": "reject", "channel": "assembly_gate", "detail": [d],
                "extra": {"nid": self_nid}}

    cand_entry = dict(entry_meta or {})
    if cand_entry:
        if self_nid and not cand_entry.get("id"):
            cand_entry["id"] = self_nid
        cand_entry.setdefault("text", text)
        bad = check_invariants(cand_entry, nodes)
        if bad:
            return {"verdict": "reject", "channel": "invariant_violation",
                    "detail": ["不变量新增违约: " + ", ".join(bad)],
                    "extra": {"nid": self_nid, "invariants_newly_false": bad}}

    v, reasons = check_entry(text, entry_meta)
    if reasons:
        return {"verdict": "reject", "channel": "entry_gate_reject", "detail": reasons,
                "extra": {"nid": self_nid, "tier": (v or {}).get("tier")}}

    nd = check_near_dup(text, nodes)
    if nd:
        return {"verdict": "reject", "channel": NEARDUP_CHANNEL,
                "detail": ["近重复 J=%.3f ≥ %.2f vs %r" % (nd["J"], memgate.NEARDUP_J, nd["against"])],
                "extra": {"nid": self_nid, "sim": nd["J"], "hit_nid": None, "against": nd["against"]}}

    return {"verdict": "admit", "channel": None, "detail": ["放行"], "extra": {"nid": self_nid}}


def before_add(text, nodes, inverted=None, ntype=None, channel=None,
               self_nid=None, entry_meta=None):
    """写入前钩子。★ 任何情况下都不阻断写入，除非 mode()==suppress 且判定拒收。

    返回 (allow: bool, nid_hint: str|None, info: dict)
      allow=False ⇒ 调用方应【不新建节点】
    所有异常 → (True, None, {...}) 即放行（fail-open）。

    ★ self_nid 精确命中跳过：nid 已在库且全文相同 ⇒ 那是 add() 既有的「只升版不新增」
      分支，门不重复介入（否则会把本来就会去重的那类算成门收益，属虚增）。
    """
    info = {"mode": mode(), "judged": False, "channel": None}
    try:
        if not enabled():
            info["mode"] = "off"
            _counters_bump(off=True)          # 另计，不进分母（见「留存率明报」口径）
            return True, None, info
        if self_nid and nodes and self_nid in nodes \
                and (nodes[self_nid].get("content") or "") == text:
            info["skipped"] = "exact_nid_same_text"
            _counters_bump(skipped_exact=True)      # 算尝试（add() 真会走升版分支）
            _emit_summary()
            return True, None, info

        r = judge(text, ntype, nodes or {}, self_nid, entry_meta)
        info["judged"] = True
        info["channel"] = r["channel"]
        info["verdict"] = r["verdict"]
        if r["verdict"] != "reject":
            _counters_bump()                        # 放行 = 留存（分子）
            _emit_summary()
            return True, None, info

        extra = dict(r.get("extra") or {})
        extra["channel"] = channel
        _drop_record(text, ntype, r["channel"], r["detail"], extra)
        _blocked = (mode() == "suppress")
        _counters_bump(dropped=True, blocked=_blocked, reason=r["channel"])
        _emit_summary()
        if _blocked:
            return False, (extra.get("hit_nid") or self_nid), info
        return True, None, info          # log：只记录不拦截
    except Exception as e:                # ★ 兜底 fail-open
        info["error"] = type(e).__name__
        return True, None, info


def gated_add(mem, content, ntype=None, entry_meta=None, **kw):
    """card 指定的挂载入口：`gated_add(mem, content, ntype, entry_meta=...)`
    = before_add 判定 + mem.add()。off/suppress 语义与 before_add 一致。"""
    nid = None
    try:
        nid = mem._nid(content, ntype) if hasattr(mem, "_nid") else None
    except Exception:
        nid = None
    allow, hint, _info = before_add(content, getattr(mem, "state", {}).get("nodes"),
                                    ntype=ntype, self_nid=nid, entry_meta=entry_meta,
                                    channel=kw.pop("channel", None))
    if not allow:
        return hint
    return mem.add(content, ntype, **kw)


# ═══════════════ 观测：统计 + 停摆守卫 ═══════════════
def _rows(path=None):
    """读台账行（缺省读本 profile 的拒收台账）。纯读，不创建文件。"""
    out = []
    try:
        p = path or DROPPED_LOG
        if os.path.exists(p):
            for ln in open(p, encoding="utf-8"):
                ln = ln.strip()
                if ln:
                    try:
                        out.append(json.loads(ln))
                    except Exception:
                        continue
    except Exception:
        pass
    return out


def stall_check(window=200):
    """读台账尾部 window 条，判门是否失效/过宽（防「阈值落在退化值+无告警」）。"""
    rows = _rows()[-window:]
    if not rows:
        return {"status": "no_data", "n": 0, "note": "尚无门事件记录"}
    n = len(rows)
    chan = collections.Counter(r.get("reason") for r in rows)
    non_nd = sum(v for k, v in chan.items() if k and k != NEARDUP_CHANNEL)
    if non_nd == 0:
        return {"status": "🔴 frozen: 有拒收记录但非近重复通道恒 0 — 门可能只用了一条通道",
                "n": n, "channels": dict(chan)}
    return {"status": "✅ ok", "n": n, "channels": dict(chan), "non_near_dup": non_nd}


def stats():
    rows = _rows()
    print("台账: %s" % DROPPED_LOG)
    print("门事件 %d 条" % len(rows))
    print("  reason  :", dict(collections.Counter(r.get("reason") for r in rows)))
    print("  verdict :", dict(collections.Counter(r.get("verdict") for r in rows)))
    print("  action  :", dict(collections.Counter(r.get("action") for r in rows)))
    print("  mode    :", dict(collections.Counter(r.get("mode") for r in rows)))
    print("  停摆守卫:", stall_check())
    return {"n": len(rows)}


# ═══════════════ ⭐ 留存率明报（只读统计入口）═══════════════
#   对标 EHRBench 的实践：多数系统只报【最终规模】，报不出「KB 校验前后留存率」；
#   本函数把 分母(总写入尝试)/分子(实际留存)/留存率/被拦率 + 按 reason 分组 一次印全，
#   并印出台账绝对路径与首/末时间戳 ⇒ 每个数字都可被第三方按台账复核。
#   ★ 只读：不写任何文件、不改判定、不加锁（自检里用 sha256 前后比对证明）。
def _pct(n, d):
    return "n/a" if not d else "%.2f%%" % (100.0 * n / d)


def _first_last(rows, keys=("iso", "t")):
    """首/末时间戳（ISO 字典序 = 时间序）。"""
    xs = []
    for r in rows:
        for k in keys:
            if r.get(k):
                xs.append(str(r[k]))
                break
    return (min(xs), max(xs)) if xs else (None, None)


def _row_kind(r):
    """一行台账 → 'drop' | 'admit' | 'other'（检查器同款优先级 reason>verdict>action 的邻居口径）。

    · 本 profile 的台账只写 drop（安全设计 6）；但也认 admit 行 ⇒
      含 admit 行的合成/历史台账仍能算出「纯台账口径」的留存率。
    """
    a = str(r.get("action") or "").lower()
    v = str(r.get("verdict") or "").lower()
    if a.startswith("admit") or v == "admit":
        return "admit"
    if v == "reject" or a.startswith("reject") or a.startswith("abort"):
        return "drop"
    return "other"


def retention_report(ledger=None, counters=None, out=None, ts=None):
    """留存率明报（只读）。返回 dict（供调用方断言 / --json 复用）。

    口径：
      · 有计数器（attempts>0）⇒ 分母 = 计数器 attempts，分子 = attempts − dropped（自洽口径）；
      · 无计数器 ⇒ 退回纯台账口径：分母 = 台账 admit 行 + 拒收行，分子 = admit 行。
    两个口径的来源与时间窗都会印出来，且打印核对行（counter 内部自洽 + 台账行数对账）。
    """
    pr = out if callable(out) else print
    led = os.path.abspath(ledger if ledger else DROPPED_LOG)
    cnt = os.path.abspath(counters if counters else COUNTERS_LOG)
    now = ts or time.strftime("%Y-%m-%d %H:%M:%S")

    rows = _rows(led)
    drops = [r for r in rows if _row_kind(r) == "drop"]
    adms = [r for r in rows if _row_kind(r) == "admit"]
    c = _counters_read(cnt)
    has_c = int(c.get("attempts") or 0) > 0
    den_known = True          # 分母是否可知（台账只记拒收 ⇒ 不可知，不得报 0%）

    if has_c:
        attempts = int(c["attempts"])
        dropped = int(c["dropped"])
        stored = attempts - dropped
        src = "counters"
        blocked = int(c.get("blocked") or 0)
        skipped = int(c.get("skipped_exact") or 0)
        w_att = (c.get("first_ts"), c.get("last_ts"))
    else:
        attempts = len(adms) + len(drops)
        dropped = len(drops)
        stored = len(adms)
        src = "ledger"
        blocked = sum(1 for r in drops
                      if str(r.get("action") or "").lower().startswith("reject_suppress"))
        skipped = 0
        w_att = _first_last(rows)
        # ★ 安全设计 6：本 profile 台账【只记拒收】⇒ 无 admit 行时分母不可知。
        #   此时若硬报 retained/attempts 会把「未知」说成「0%」——即"只报最终规模"的反面错误。
        if not adms:
            den_known = False

    reasons = collections.Counter(str(r.get("reason") or "(missing)") for r in drops)
    actions = collections.Counter(str(r.get("action") or "(missing)") for r in rows)
    modes = collections.Counter(str(r.get("mode") or "(missing)") for r in rows)
    w_led = _first_last(rows)

    pr("═══ %s 写闸 · 留存率明报 (retention report) ═══════════════════════" % PROFILE)
    pr("统计时间        : %s" % now)
    pr("口径来源        : %s%s" % (src, "（计数器自洽口径）" if has_c else "（无计数器 ⇒ 纯台账口径）"))
    pr("台账(drops)     : %s" % led)
    pr("台账(counters)  : %s" % cnt)
    pr("时间窗(尝试)    : %s → %s" % (w_att[0] or "(无)", w_att[1] or "(无)"))
    pr("时间窗(台账行)  : %s → %s   (%d 行)" % (w_led[0] or "(无)", w_led[1] or "(无)", len(rows)))
    pr("─────────────────────────────────────────────────────────────────")
    if den_known:
        pr("分母 总写入尝试 : %d" % attempts)
        pr("分子 实际留存   : %d" % stored)
        pr("留存率          : %s   (%d/%d)" % (_pct(stored, attempts), stored, attempts))
        pr("被拦率          : %s   (%d/%d)" % (_pct(dropped, attempts), dropped, attempts))
    else:
        pr("分母 总写入尝试 : (未知)   ⚠ 台账只记拒收(安全设计 6) ⇒ 分母须计数器")
        pr("分子 实际留存   : (未知)")
        pr("留存率          : n/a（分母未知，不得报 0%）")
        pr("被拦率          : n/a（分母未知）  [已知拒收事件数 = %d 行]" % dropped)
    pr("  · 实际被拦(真丢): %d%s" % (blocked, "   ← mode=log ⇒ 只记不拦，拦截仅在 suppress 生效" if not blocked and dropped else ""))
    pr("  · 精确同 nid 跳过: %d (既有「同 nid 同文只升版」分支，门不介入，仍算尝试)" % skipped)
    pr("  · mode=off 调用  : %d (不计入分母)" % int(c.get("off") or 0))
    pr("─────────────────────────────────────────────────────────────────")
    pr("按 reason 分组（拒收事件；分母 = 台账拒收行 %d）:" % len(drops))
    if drops:
        for k, v in reasons.most_common():
            pr("  %-22s %5d   %s" % (k, v, _pct(v, len(drops))))
    else:
        pr("  (无拒收行)")
    pr("按 action 分组  : %s" % (dict(actions) or "{}"))
    pr("按 mode   分组  : %s" % (dict(modes) or "{}"))
    pr("按 reason 分组(计数器口径): %s" % (dict(c.get("by_reason") or {}) if has_c else "(无计数器)"))
    pr("─────────────────────────────────────────────────────────────────")
    if has_c:
        ok = (int(c.get("admitted") or 0) + int(c.get("dropped") or 0) == attempts)
        hist = len(drops) - dropped
        pr("核对: 计数器 attempts=%d = admitted %d + dropped %d %s"
           % (attempts, int(c.get("admitted") or 0), dropped, "✔" if ok else "✘(计数器自相矛盾)"))
        pr("      台账拒收行 %d = 计数器 dropped %d + 计数器启用前历史行 %d"
           % (len(drops), dropped, hist))
    else:
        if den_known:
            pr("核对: 台账 admit 行 %d + 拒收行 %d = 分母 %d（纯台账口径）"
               % (len(adms), len(drops), attempts))
        else:
            pr("核对: 台账 admit 行 0 ⇒ 拒收行 %d 只是【拒收事件数】，等于分母的唯一条件"
               "是『门看到过且全部被拒』——本 profile 无法证实 ⇒ 报 n/a（不报 0%%）" % len(drops))
    return {"schema": "wg_retention/1.0", "profile": PROFILE, "generated": now,
            "source": src, "ledger": led, "counters": cnt,
            "attempts_known": den_known,
            "attempts": attempts if den_known else None,
            "stored": stored if den_known else None, "dropped": dropped,
            "blocked": blocked, "skipped_exact": skipped,
            "retention_pct": (100.0 * stored / attempts) if (attempts and den_known) else None,
            "drop_rate_pct": (100.0 * dropped / attempts) if (attempts and den_known) else None,
            "ledger_drop_rows": len(drops), "ledger_admit_rows": len(adms),
            "reasons": {k: {"n": v, "pct": (100.0 * v / len(drops)) if drops else None}
                        for k, v in reasons.most_common()},
            "actions": dict(actions), "modes": dict(modes),
            "counters_by_reason": dict(c.get("by_reason") or {}),
            "window_attempt": {"first": w_att[0], "last": w_att[1]},
            "window_ledger": {"first": w_led[0], "last": w_led[1]}}


def _selftest_report():
    """留存率明报的【只读】自检：合成台账 + 手算期望 + 反向对照（必须能失败）。

    ⚠️ 全程在 tempfile.mkdtemp() 里造合成台账，并把模块级台账/计数器路径临时指过去；
       跑完恢复并删目录 ⇒ 不碰生产台账、不在 profile 树里留任何台账类文件。
    """
    import shutil
    import tempfile
    global DROPPED_LOG, COUNTERS_LOG
    ok_all = []
    work = tempfile.mkdtemp(prefix="wg_report_selftest_")
    old_led, old_cnt = DROPPED_LOG, COUNTERS_LOG

    def _mk(name, drop_reasons, counters=None):
        """造一份合成台账（+可选计数器），返回 (ledger_path, counters_path)。"""
        lp = os.path.join(work, name + "_ledger.jsonl")
        cp = os.path.join(work, name + "_counters.json")
        with open(lp, "w", encoding="utf-8") as f:
            for i, rz in enumerate(drop_reasons, 1):
                f.write(json.dumps({"t": "2026-01-0%dT00:00:%02d" % (1 + i % 8, i % 60),
                                    "iso": "2026-01-0%d 00:00:%02d" % (1 + i % 8, i % 60),
                                    "reason": rz, "verdict": "reject", "action": "reject_log",
                                    "mode": "log", "profile": PROFILE}, ensure_ascii=False) + "\n")
        if counters is not None:
            json.dump(counters, open(cp, "w", encoding="utf-8"), ensure_ascii=False)
        return lp, cp

    def T(name, cond, extra=""):
        ok_all.append(bool(cond))
        print(("  OK   " if cond else "  FAIL ") + name + ("   " + str(extra) if extra else ""))
        return bool(cond)

    try:
        # ── 用例①：合成台账 12 拒收 + 计数器 100 尝试 / 88 留存（手算：88/100 = 88.00%）──
        r1 = ["entry_gate_reject"] * 6 + ["assembly_gate"] * 2 + ["invariant_violation"] * 1 \
             + ["near_duplicate"] * 3
        c1 = {"schema": COUNTERS_SCHEMA, "attempts": 100, "judged": 100, "admitted": 88,
              "dropped": 12, "blocked": 0, "skipped_exact": 0, "off": 0,
              "by_reason": {"entry_gate_reject": 6, "assembly_gate": 2,
                            "invariant_violation": 1, "near_duplicate": 3},
              "by_mode": {"log": 100}, "first_ts": "2026-01-01T00:00:00",
              "last_ts": "2026-01-02T00:00:00"}
        lp1, cp1 = _mk("case1", r1, c1)
        R1 = retention_report(ledger=lp1, counters=cp1, out=lambda *a: None)
        # 手算期望（独立于脚本输出）：100 尝试 − 12 拒收 = 88 留存；88/100 = 88.00%；12/100 = 12.00%
        T("①分母 100 尝试 ⇒ attempts=100", R1["attempts"] == 100, R1["attempts"])
        T("①分子 88 留存   ⇒ stored=88", R1["stored"] == 88, R1["stored"])
        T("①留存率 = 88.00%（手算 88/100）", abs(R1["retention_pct"] - 88.0) < 1e-9, R1["retention_pct"])
        T("①被拦率 = 12.00%（手算 12/100）", abs(R1["drop_rate_pct"] - 12.0) < 1e-9, R1["drop_rate_pct"])
        T("①reason 分组计数 entry_gate_reject=6",
          R1["reasons"].get("entry_gate_reject", {}).get("n") == 6, R1["reasons"])
        T("①reason 分组占比 entry 6/12=50.00%",
          abs(R1["reasons"]["entry_gate_reject"]["pct"] - 50.0) < 1e-9)
        T("①reason 分组占比 near_duplicate 3/12=25.00%",
          abs(R1["reasons"]["near_duplicate"]["pct"] - 25.0) < 1e-9)
        T("①时间窗可追溯（首/末非空）",
          bool(R1["window_ledger"]["first"]) and bool(R1["window_ledger"]["last"]),
          R1["window_ledger"])

        # ── 用例②：反向对照 —— 纸面留存率完全不同的台账（10/100）必须给出不同数字 ──
        r2 = ["entry_gate_reject"] * 60 + ["assembly_gate"] * 30
        c2 = dict(c1); c2.update({"attempts": 100, "admitted": 10, "dropped": 90, "blocked": 90,
                                  "by_reason": {"entry_gate_reject": 60, "assembly_gate": 30},
                                  "by_mode": {"suppress": 100}})
        lp2, cp2 = _mk("case2", r2, c2)
        R2 = retention_report(ledger=lp2, counters=cp2, out=lambda *a: None)
        # 手算期望：100 尝试 − 90 拒收 = 10 留存；10/100 = 10.00%
        T("②反向对照: attempts=100 相同", R2["attempts"] == 100)
        T("②反向对照: stored=10（手算）", R2["stored"] == 10, R2["stored"])
        T("②反向对照: 留存率 = 10.00%（≠ ①的 88.00%）",
          abs(R2["retention_pct"] - 10.0) < 1e-9, R2["retention_pct"])
        T("②反向对照: 报告数字随台账改变（非缓存/硬编码）",
          abs(R1["retention_pct"] - R2["retention_pct"]) > 1.0)
        T("②反向对照: 被拦率 90.00% + 实际被拦 blocked=90", 
          abs(R2["drop_rate_pct"] - 90.0) < 1e-9 and R2["blocked"] == 90)
        T("②反向对照: reason 占比 60/90=66.67% / 30/90=33.33%",
          abs(R2["reasons"]["entry_gate_reject"]["pct"] - 100.0 * 60 / 90) < 1e-9
          and abs(R2["reasons"]["assembly_gate"]["pct"] - 100.0 * 30 / 90) < 1e-9)

        # ── 用例③：自检必须"能失败" —— 故意用错期望，断言必须判 FAIL ──
        T("③断言机制非空转：故意错的期望被判 FAIL",
          not (abs(R2["retention_pct"] - 88.0) < 1e-9), "R2=%.2f vs 错误期望 88.00" % R2["retention_pct"])

        # ── 用例④：纯台账口径（无计数器）—— 含 admit 行时也能算留存率 ──
        lp4 = os.path.join(work, "case4_ledger.jsonl")
        with open(lp4, "w", encoding="utf-8") as f:
            for i in range(3):
                f.write(json.dumps({"t": "2026-02-01T00:00:0%d" % i, "verdict": "admit",
                                    "action": "admit", "nid": "a%d" % i}, ensure_ascii=False) + "\n")
            for i in range(7):
                f.write(json.dumps({"t": "2026-02-01T00:01:0%d" % i, "reason": "entry_gate_reject",
                                    "verdict": "reject", "action": "reject_log"}, ensure_ascii=False) + "\n")
        R4 = retention_report(ledger=lp4, counters=os.path.join(work, "no_such_cnt.json"),
                              out=lambda *a: None)
        # 手算：分母 3+7=10，分子 3 ⇒ 30.00%
        T("④无计数器 ⇒ 纯台账口径 attempts=10 stored=3", R4["attempts"] == 10 and R4["stored"] == 3)
        T("④纯台账留存率 = 30.00%（手算 3/10）", abs(R4["retention_pct"] - 30.0) < 1e-9,
          R4["retention_pct"])
        T("④口径来源标记为 ledger", R4["source"] == "ledger")

        # ── 用例⑤：只读证明（跑报告前后台账 sha256 不变）──
        h_before = hashlib.sha256(open(lp1, "rb").read()).hexdigest()
        retention_report(ledger=lp1, counters=cp1, out=lambda *a: None)
        h_after = hashlib.sha256(open(lp1, "rb").read()).hexdigest()
        T("⑤只读：跑报告前后台账 sha256 不变", h_before == h_after, h_before[:16])

        # ── 用例⑥：摘要行（含反向对照：数字随计数器改变）──
        s1 = summary_line(cp1); s2 = summary_line(cp2)
        T("⑥摘要行出现 attempts=/stored=/retention=",
          bool(s1) and "attempts=100" in s1 and "stored=88" in s1 and "retention=88.0%" in s1, s1)
        T("⑥摘要行随计数器改变（attempts=100 stored=10 retention=10.0%）",
          bool(s2) and "stored=10" in s2 and "retention=10.0%" in s2, s2)

        # ── 用例⑦：默认行为未变 —— log 模式拒收仍放行 / suppress 才拦；且计数器同步 ──
        DROPPED_LOG = os.path.join(work, "case7_ledger.jsonl")
        COUNTERS_LOG = os.path.join(work, "case7_counters.json")
        os.environ.pop("CORTEXMEM_WRITE_GATE", None)
        allow_log, _, info_log = before_add("一条没有任何元数据的候选记忆 " * 2, {}, ntype="semantic", self_nid="z")
        T("⑦默认(log)：拒收判定成立但 allow=True（只记不拦）",
          allow_log is True and info_log.get("verdict") == "reject" and info_log.get("mode") == "log",
          info_log)
        c7 = _counters_read(COUNTERS_LOG)
        T("⑦默认(log)：计数器已记 attempts=1 dropped=1 blocked=0",
          c7["attempts"] == 1 and c7["dropped"] == 1 and c7["blocked"] == 0, 
          {k: c7[k] for k in ("attempts", "dropped", "blocked", "admitted")})
        T("⑦默认(log)：台账被追加 1 行", len(_rows(DROPPED_LOG)) == 1)
        os.environ["CORTEXMEM_WRITE_GATE"] = "suppress"
        allow_sup, hint, info_sup = before_add("一条没有任何元数据的候选记忆 " * 2, {}, ntype="semantic", self_nid="z")
        T("⑦suppress：真拦（allow=False）+ blocked=1",
          allow_sup is False and _counters_read(COUNTERS_LOG)["blocked"] == 1, info_sup.get("verdict"))
        os.environ["CORTEXMEM_WRITE_GATE"] = "off"
        allow_off, _, info_off = before_add("任意内容", {}, ntype="semantic", self_nid="z")
        T("⑦off：一律放行且 attempts 不增（另记 off=1）",
          allow_off is True and info_off.get("mode") == "off"
          and _counters_read(COUNTERS_LOG)["attempts"] == 2
          and _counters_read(COUNTERS_LOG)["off"] == 1)
        os.environ.pop("CORTEXMEM_WRITE_GATE", None)

        # ── 用例⑧：写入开关总闸 —— counters=off ⇒ 不留文件、不打摘要 ──
        os.environ["CORTEXMEM_WG_COUNTERS"] = "off"
        c8 = _counters_bump()
        T("⑧CORTEXMEM_WG_COUNTERS=off ⇒ 计数器不动（返回 None）", c8 is None)
        os.environ.pop("CORTEXMEM_WG_COUNTERS", None)
        T("⑧summary_mode 默认 each / 非法值回落 each",
          summary_mode() in ("each", "exit", "off") and default_summary() == "each")
        # ── 用例⑨：拒收-only 台账（无 admit 行、无计数器）⇒ 分母不可知，必须报 n/a 而非 0% ──
        lp9 = os.path.join(work, "case9_dropsonly.jsonl")
        with open(lp9, "w", encoding="utf-8") as f:
            for i in range(7):
                f.write(json.dumps({"t": "2026-03-0%dT00:00:00" % (i + 1),
                                    "reason": "entry_gate_reject", "verdict": "reject",
                                    "action": "reject_log"}, ensure_ascii=False) + "\n")
        R9 = retention_report(ledger=lp9, counters=os.path.join(work, "no_cnt9.json"),
                              out=lambda *a: None)
        T("⑨拒收-only 台账 ⇒ attempts_known=False（不把未知说成 0%）",
          R9["attempts_known"] is False and R9["attempts"] is None, R9["attempts"])
        T("⑨拒收-only 台账 ⇒ 留存率 = None（n/a）而非 0.0",
          R9["retention_pct"] is None and R9["drop_rate_pct"] is None, R9["retention_pct"])
        T("⑨拒收-only 台账 ⇒ 仍给出拒收事件数 7 与 reason 分组",
          R9["dropped"] == 7 and R9["reasons"]["entry_gate_reject"]["n"] == 7)

        # ── 用例⑩：真·默认行为未变回归 —— mode() 默认 log；log 下 add 语义（allow=True）──
        T("⑩默认 mode = log（只记不拦）", mode() == "log" and DEFAULT_MODE == "log", mode())
        T("⑩默认计数器开关 = on、摘要 = each、台账 = on",
          counters_enabled() is True and summary_mode() == "each" and ledger_enabled() is True)
        T("⑩门事件统计 stats() 仍可用（未破坏既有入口）", isinstance(stats(), dict))
    finally:
        DROPPED_LOG, COUNTERS_LOG = old_led, old_cnt
        try:
            shutil.rmtree(work, ignore_errors=True)
        except Exception:
            pass
    print("自检(留存率明报): %s  共 %d 项"
          % ("通过" if all(ok_all) else "未通过", len(ok_all)))
    return 0 if all(ok_all) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    def _argval(flag, default=None):
        a_ = sys.argv[1:]
        return a_[a_.index(flag) + 1] if flag in a_ and a_.index(flag) + 1 < len(a_) else default

    a = sys.argv[1:]
    if "--report" in a:
        # ⭐ 留存率明报（只读）：分母/分子/留存率/被拦率 + 按 reason 分组。默认读本 profile 台账。
        R = retention_report(ledger=_argval("--ledger"), counters=_argval("--counters"))
        if "--json" in a:
            print(json.dumps(R, ensure_ascii=False, indent=2))
    elif "--selftest-report" in a:
        # ⭐ 只读自检：合成台账 + 手算期望 + 反向对照（必须能失败）。全程在临时目录，不碰生产台账。
        print("留-试: 合成台账 + 手算期望 + 反向对照（只读，成品见 tempfile）")
        sys.exit(_selftest_report())
    elif "--stats" in a:
        stats()
    elif "--mode" in a:
        print("mode=%s  ledger_enabled=%s  data_dir=%s" % (mode(), ledger_enabled(), DATA_DIR))
    elif "--selftest" in a:
        # 只读自检：用内存假库驱动判定，不写任何数据文件。
        # ⚠️ 每项用【独立假库】：装配闸的前缀撞车判据 = nodes[self_nid] 存在且全文不同，
        #    假库若不按 self_nid 建键，会与后两项互相污染（首轮实测踩到）。
        P80 = "这是一条足够长的既有记忆前八十字符前缀" * 2
        P80 = P80[:80]
        lib_collide = {"z": {"content": P80 + "尾巴甲", "session_id": "s1"}}   # self_nid="z" 撞车
        lib_plain = {"n1": {"content": "既有节点内容 " * 3, "session_id": "s1"}}  # z 不在库
        checks = []
        checks.append(("装配闸·type 非法",
                       judge("x", "bogus", {}, "z")["channel"] == "assembly_gate"))
        checks.append(("装配闸·前缀撞车(nid 相同/全文不同)",
                       judge(P80 + "尾巴乙", "semantic", lib_collide, "z")["channel"] == "assembly_gate"))
        checks.append(("不变量·id 撞车 (M1 由真→假)",
                       judge("完全不同的内容 " * 3, "semantic", lib_plain, "z",
                             entry_meta={"id": "n1", "source_ptr": "s1", "reopen_if": "x",
                                         "support": ["a"]})["channel"] == "invariant_violation"))
        checks.append(("逐条闸·四项全缺",
                       judge("一条没有任何元数据的候选记忆 " * 2, "semantic", lib_plain, "z")["channel"] == "entry_gate_reject"))
        ok = all(v for _, v in checks)
        for name, v in checks:
            print(("  OK   " if v else "  FAIL ") + name)
        print("自检: %s" % ("通过" if ok else "未通过"))
        sys.exit(0 if ok else 1)
    else:
        print(__doc__)
