# -*- coding: utf-8 -*-
"""CortexMem v1.0 — 高效记忆工具设计 (2026-08-11)
基于 D1-D5 研究的 14 工具亮点 + 多学科原理融合

设计原理映射:
  生理学:  海马体(Hippocampus) → 临时缓冲+巩固迁移
           突触可塑性(SNP)     → 权重动态调整
           睡眠巩固           → 离线蒸馏+剪枝
  计算机:  Cache层级          → 热/温/冷三级存储
           TLB/分页           → 高频记忆驻留
           写回(Write-back)   → 批量巩固
  数据库:  ACID事务           → 记忆原子写入
           聚簇索引           → 语义聚类存储
           MVCC              → 版本化记忆
  存储搜索: 倒排索引          → 关键词检索
           向量索引           → 语义检索
           图遍历             → 关联检索
  群论:    轨道压缩           → 相似记忆合并

架构: 三态(热/温/冷) + 三层图 + 双路检索(倒排+向量) + 睡眠巩固

用法:
  python cortexmem.py --init
  python cortexmem.py --add <text>
  python cortexmem.py --query <q>
  python cortexmem.py --sleep
  python cortexmem.py --sim
"""
# side_effects: [写数据文件]
import os, sys, io, json, math, random, time, hashlib, re
from collections import defaultdict, Counter
from datetime import datetime, timezone   # R989: 降层标记需要

# 注意: stdout 重配放 __main__ (避免 import 破坏调用方)
random.seed(42)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, "knowledge_base", "cortexmem")
STATE_FILE = os.path.join(DATA_DIR, "state.json")

# ═══ [P0-6 / D13 · 2026-10-15] 写入侧门：单一写入点钩子 ═══
# 四个写入者 (cortexmem_tool / cortexmem_daily / cortexmem_integrate / CLI) 自动覆盖。
# 判定与台账见 scripts/cortexmem_write_gate.py（三通道 entry_gate_reject /
# invariant_violation / assembly_gate + 近重复 0.70），台账落
# <profile>/knowledge_base/cortexmem/_write_dropped.jsonl。
# ★ fail-open: 模块缺失/导入失败 ⇒ _wg=None ⇒ add() 行为与改造前【完全一致】。
# ★ 回退: CORTEXMEM_WRITE_GATE=off（一行 env，不改代码）；默认 log（只记录不拦截）。
try:
    _SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
    if _SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, _SCRIPTS_DIR)
    import cortexmem_write_gate as _wg
except Exception:
    _wg = None

# ═══ 三态 (热/温/冷 = Cache 层级) ═══
HOT = "hot"        # 高频访问, 常驻 (TLB类比)
WARM = "warm"      # 中频, 快速索引
COLD = "cold"      # 低频, 压缩存储 (磁盘类比)

# ═══ 节点类型 (FluxMem 三层) ═══
SEMANTIC, EPISODIC, PROCEDURAL = "semantic", "episodic", "procedural"
TOOL_TRACE = "tool_trace"  # [AY2] 多模态: 工具轨迹记忆 (MemOS 借鉴 2026-08-14)

class CortexMem:
    def __init__(self):
        self.state = {"nodes": {}, "edges": [], "inverted": defaultdict(set),
                      "runs": 0, "consolidated": 0}
        self.load()

    def load(self):
        if os.path.exists(STATE_FILE):
            try:
                data = json.load(open(STATE_FILE, encoding="utf-8"))
                data["inverted"] = defaultdict(set, {k: set(v) for k, v in data.get("inverted", {}).items()})
                self.state = data
            except Exception:
                pass

    def save(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        data = dict(self.state)
        data["inverted"] = {k: list(v) for k, v in self.state["inverted"].items()}
        if os.path.exists(STATE_FILE):
            if os.path.exists(STATE_FILE + ".bak"):
                try: os.remove(STATE_FILE + ".bak")
                except OSError: pass
            os.rename(STATE_FILE, STATE_FILE + ".bak")
        json.dump(data, open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    def _words(self, text):
        return set(re.findall(r'[a-zA-Z]{3,}|[\u4e00-\u9fff]{1}', text.lower()))

    def _nid(self, text, ntype):
        return hashlib.md5(f"{ntype}:{text[:80]}".encode()).hexdigest()[:12]

    # ── [M1] 实体提取与链接 (Mem0 P0 借鉴) ──
    def _extract_entities(self, text: str) -> list:
        """提取实体: 大写词/引号词/常见实体模式"""
        entities = []
        # 英文大写词 (专名)
        entities += re.findall(r'\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*\b', text)
        # 中文引号内 (专名)
        entities += re.findall(r'["\u201c\u201d]([\u4e00-\u9fff]{2,8})["\u201c\u201d]', text)
        # 技术关键词 (白名单)
        tech = ["CortexMem", "FluxMem", "Mem0", "MemOS", "herdr", "MetaGPT",
                "Voyager", "HippoRAG", "Ollama", "Hermes", "Redis", "RTX",
                "OOM", "stdout", "GPU", "CUDA", "WSL", "VPS", "GitHub"]
        entities += [t for t in tech if t.lower() in text.lower()]
        # 【2026-10-18 D12 根因修】英语句首虚词被 `[A-Z][a-z]{2,}` 当成专名：
        # 实测 qqbot3 图 Top 实体 = Let(2143) / Now(1278) / All(843) / The(841)，
        # 582 个 ≤5 字符泛词吃掉 10408/18773 条边（55.4%）。中文实体照旧保留。
        _STOP_EN = {
            "Let", "Now", "All", "The", "This", "That", "These", "Those", "You", "Your",
            "Both", "Good", "Found", "Dispatched", "State", "Phase", "Profile", "Agent",
            "Here", "There", "Then", "Also", "But", "And", "With", "From", "Into", "Using",
            "Check", "Run", "Done", "Yes", "Not", "When", "While", "After", "Before",
            "Only", "New", "Old", "Next", "Last", "First", "Second", "Third", "Step",
            "Note", "Hint", "Result", "Test", "Code", "File", "Path", "Data", "Set",
            "Get", "Use", "Put", "See", "Try", "Must", "Need", "Should", "Would",
            "Could", "Will", "Can", "May", "Might", "Has", "Have", "Had", "Was",
            "Were", "Are", "Is", "Be", "It", "Its", "We", "Our", "My", "Me", "He",
            "She", "They", "Them", "His", "Her", "Their", "What", "Which", "Who",
            "Why", "How", "Where", "Okay", "Sure", "Great", "Perfect", "Please",
            "如下", "以下", "上述", "目前", "现在",
        }
        entities = [
            e for e in entities
            if e in tech                                  # 白名单技术词永不剔除
            or (not e.isascii())                          # 中文/含非 ASCII ⇒ 保留
            or (e not in _STOP_EN and len(e) >= 3)        # 英文：非虚词且 ≥3 字符
        ]
        # 去重保序
        seen, result = set(), []
        for e in entities:
            if e not in seen:
                seen.add(e)
                result.append(e)
        return result[:5]

    def _link_entities(self, nid, text):
        """实体链接: 实体 → 实体节点 + 关系边 (Mem0 _link_entities 借鉴)"""
        for ent in self._extract_entities(text):
            eid = self._nid("实体:" + ent, SEMANTIC)
            if eid not in self.state["nodes"]:
                self.state["nodes"][eid] = {
                    "id": eid, "type": SEMANTIC, "content": "实体:" + ent,
                    "state": WARM, "weight": 1.0, "access": 1, "version": 1,
                    "created": time.time(), "last_access": time.time(),
                    "entity": True,
                }
                for w in self._words(ent):
                    self.state["inverted"][w].add(eid)
            # 关系边 (nid → 实体)：带谓词类型（D12 修复尝试，2026-10-18）
            # ⚠️ 默认【关】：校准实测精度仅 ~1/3 明确可用（实体名本身质量不足，见
            #    analysis/reports/REL_TYPING_20261018.md）⇒ 需显式 CORTEXMEM_REL_TYPING=on 才启用。
            #    未启用时行为与改造前【完全一致】（type="mentions"）。
            _rtype, _ev = "mentions", ""
            if os.environ.get("CORTEXMEM_REL_TYPING", "off").lower() == "on":
                try:
                    _rt_dir = os.environ.get("REL_TYPING_DIR") or r"D:/hermes/analysis"
                    if _rt_dir not in sys.path:
                        sys.path.insert(0, _rt_dir)
                    from relation_typing import classify as _classify
                    _t, _cf, _e = _classify(text, ent)
                    if _cf >= 0.9:            # 只收「谓词与实体同句」的高置信判定
                        _rtype, _ev = _t, _e
                except Exception:
                    _rtype, _ev = "mentions", ""   # 抽取器坏 ⇒ 退回原行为，不阻断写入
            edge = {"from": nid, "to": eid, "type": _rtype}
            if _ev:
                edge["evidence"] = _ev
            if edge not in self.state["edges"]:
                self.state["edges"].append(edge)

    # [AH2] 主题词提取: bigram 2-gram (中文无词边界, 单字无效)
    @staticmethod
    def _topic_ngrams(text: str, min_len: int = 2) -> list:
        """从文本生成 2-gram 候选词 (过滤纯标点/数字片段)"""
        import re
        # 去标点/空白, 保留中日韩字符+字母数字
        cleaned = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", text)
        if len(cleaned) < min_len:
            return []
        grams = []
        for i in range(len(cleaned) - 1):
            g = cleaned[i:i + 2]
            if g.isdigit():
                continue
            grams.append(g)
        return grams

    @staticmethod
    def _topic_trigrams(text: str) -> set:
        """3-gram 验证集 (AI1: 边界噪音过滤)"""
        import re
        cleaned = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", text)
        if len(cleaned) < 3:
            return set()
        return {cleaned[i:i + 3] for i in range(len(cleaned) - 2)}

    def _semantic_common(self, contents, stop=None):
        """[AH2+AI1] 多文本共同主题词: bigram 交集 + 词边界验证"""
        stop = stop or {"的", "了", "是", "在", "和", "与", "及", "或", "第", "天", "次",
                        "个", "上", "下", "中", "后", "前", "新", "旧", "用", "做",
                        "进行", "完成", "处理", "问题", "数据", "内容", "一个", "我们",
                        "你们", "他们", "这个", "那个", "以及", "通过", "进行", "相关"}
        gram_sets = [set(self._topic_ngrams(c)) for c in contents]
        if not gram_sets:
            return []
        inter = set.intersection(*gram_sets)
        inter = {g for g in inter if g not in stop}
        # [AI1] 词边界验证: 真词必有标点/空格/开头/结尾邻接; 跨词残片 ("布参")
        # 总是被左右字包裹 (无边界证据) → 剔除
        import re as _re
        verified = set()
        for g in inter:
            for c in contents:
                # 在原文(含标点)中找 g 的所有出现, 检查是否有边界邻接
                for m in _re.finditer(_re.escape(g), c):
                    left = c[m.start() - 1] if m.start() > 0 else "␃"
                    right = c[m.end()] if m.end() < len(c) else "␃"
                    if (left in " ␃\n\t，。；：、？！.,;:!?（）()" or
                            right in " ␃\n\t，。；：、？！.,;:!?（）()"):
                        verified.add(g)
                        break
                if g in verified:
                    break
        return sorted(verified)[:5]

    # ── [AH3] 语义化提取: embedding medoid 语义句 (2026-09-06) ──
    # 从相似组内容选"语义最居中"句 = 组语义代表 (bge-m3 本地 embedding)
    # 失败自动降级: 交集词串 (原 AH2 行为 — 不丢功能)
    @staticmethod
    def _embed(text: str):
        """调 Ollama bge-m3 得 embedding (失败返回 None — 降级通道)"""
        import json, urllib.request
        try:
            payload = json.dumps({"model": "bge-m3", "input": [text[:500]]}).encode()
            req = urllib.request.Request("http://127.0.0.1:11434/api/embed",
                                         data=payload, headers={"Content-Type": "application/json"})
            d = json.loads(urllib.request.urlopen(req, timeout=20).read())
            embs = d.get("embeddings") or []
            return embs[0] if embs else None
        except Exception:
            return None

    @classmethod
    def _semantic_sentence(cls, contents, common):
        """语义核心句: 各内容 embedding → medoid (最居中=组语义代表)
        返回 (语义句, 是否embedding) — embedding 失败降级最长句"""
        import math
        vecs = []
        for c in contents:
            v = cls._embed(c)
            if v:
                vecs.append((c, v))
        if len(vecs) >= 2:
            # medoid: 与其他向量总 cosine 最大者
            best, best_score = None, -1e9
            for i, (c_i, v_i) in enumerate(vecs):
                score = 0.0
                for j, (c_j, v_j) in enumerate(vecs):
                    if i == j:
                        continue
                    na = math.sqrt(sum(x * x for x in v_i))
                    nb = math.sqrt(sum(x * x for x in v_j))
                    if na * nb > 0:
                        score += sum(x * y for x, y in zip(v_i, v_j)) / (na * nb)
                if score > best_score:
                    best, best_score = c_i, score
            if best:
                return best.strip()[:80], True
        # 降级: 最长句 (信息量代理) — 无 embedding 依赖
        longest = max(contents, key=len).strip()[:80] if contents else ""
        return longest, False

    # ── 写入: ACID 事务 (原子写入+版本) ──
    def add(self, text: str, ntype: str = SEMANTIC, state: str = WARM,
            session_id: str = None, sensitive: bool = False,
            velocity: str = "stable",
            channel: str = None, entry_meta: dict = None):
        """[X1] velocity 事实速度分级 (VoltMem 借鉴):
          stable  (稳定事实: 家乡/技术栈) → 抗污染, 权重稳定
          volatile(易变事实: 今日状态/临时值) → 新鲜度优先, 更新频繁
        """
        nid = self._nid(text, ntype)
        # ── [P0-6 / D13 · 2026-10-15] 写入侧门 (单一写入点；mode=log 只记录, suppress 才拦) ──
        # self_nid 传入: 「同 nid 同全文」由下面的既有分支处理，门只抓
        #   (a) 前缀指纹撞车但全文不同 (b) 不变量新增违约 (c) 逐条闸四项不全 (d) 近重复。
        if _wg is not None:
            try:
                _allow, _hint, _info = _wg.before_add(
                    text, self.state["nodes"], self.state.get("inverted"),
                    ntype=ntype, channel=channel, self_nid=nid, entry_meta=entry_meta)
                if not _allow:
                    return _hint          # 拒收：不新建节点 (仅 suppress 模式可达)
            except Exception:
                pass                      # ★ 门故障绝不阻断写入 (fail-open)
        now = time.time()
        if nid in self.state["nodes"]:
            node = self.state["nodes"][nid]
            node["access"] += 1
            node["version"] += 1  # MVCC 版本
            node["last_access"] = now
            if node.get("velocity") == "volatile":
                node["weight"] = min(1.0, node.get("weight", 0.6) + 0.05)  # 易变→更新即升权
            # [X2] graphiti 时间边: 更新时间线
            node.setdefault("_timeline", []).append(now)
            return nid
        w0 = 0.6 if ntype == SEMANTIC else (0.8 if ntype == PROCEDURAL else 0.5)
        self.state["nodes"][nid] = {
            "id": nid, "type": ntype, "content": text, "state": state,
            "weight": w0 * (0.8 if velocity == "volatile" else 1.0),
            "access": 1, "version": 1, "created": now, "last_access": now,
            "session_id": session_id,          # [N1] 会话作用域 (Mem0)
            "sensitive": sensitive,             # [N2] 敏感字段 (Mem0)
            "feedback": 0.0,                    # [N3] 反馈驱动 (MemOS)
            "history": [],                      # [N5] 版本历史 (Mem0)
            "velocity": velocity,               # [X1] 事实速度 (VoltMem)
            "_timeline": [now],                 # [X2] 时间边 (graphiti)
        }
        # 倒排索引 (聚簇)
        for w in self._words(text):
            self.state["inverted"][w].add(nid)
        # [M1] 实体链接 (Mem0 借鉴)
        self._link_entities(nid, text)
        return nid

    # ── [W1] mem_judge 冲突裁决 (engram 借鉴, 2026-08-13) ──
    def mem_judge(self, text: str, ntype: str = SEMANTIC,
                  sim_threshold: float = 0.6) -> dict:
        """新记忆与旧记忆冲突检测 + 裁决 (engram mem_judge 借鉴):
        保存前检查高相似节点 → 内容矛盾时记录裁决 (不静默覆盖)
        返回: {conflict: bool, new_nid, old_nids[], verdict}
        用法: 冲突时由调用方决定 (新覆盖旧 / 保留旧 / 并存)
        """
        from difflib import SequenceMatcher
        # 冲突检测: 与已有节点高相似
        old_hits = []
        for nid, node in self.state["nodes"].items():
            if node.get("type") == ntype:
                sim = SequenceMatcher(None, text[:50], node["content"][:50]).ratio()
                if sim >= sim_threshold:
                    old_hits.append({"id": nid, "sim": round(sim, 2),
                                     "old": node["content"][:40]})
        # 裁决记录
        verdict = {"ts": time.time()}
        new_nid = None
        if old_hits:
            # 矛盾判定: 新旧内容关键词集合差异大 (可能矛盾)
            new_words = set(self._words(text)) - set(["的", "了", "是", "在"])
            old_words = set(self._words(old_hits[0]["old"])) - set(["的", "了", "是", "在"])
            overlap = len(new_words & old_words) / max(1, len(new_words | old_words))
            conflict = overlap < 0.3 and len(new_words) > 2
            verdict = {"conflict": conflict, "ts": time.time(),
                       "old_ids": [h["id"] for h in old_hits],
                       "note": "冲突: 新旧内容语义分歧" if conflict else "相似: 内容高度重叠"}
            # 相似不矛盾 → 不新增 (去重); 矛盾 → 记录待裁决
            if not conflict:
                return {"conflict": False, "new_nid": old_hits[0]["id"],
                        "old_nids": [h["id"] for h in old_hits], "verdict": verdict}
            # 冲突: 写入新节点 + 记录裁决 (调用方决定覆盖)
            new_nid = self.add(text, ntype)
            self.state.setdefault("judgments", []).append({
                "new_nid": new_nid, "old_ids": [h["id"] for h in old_hits],
                "verdict": verdict, "text": text[:60]})
            self.save()
            return {"conflict": True, "new_nid": new_nid,
                    "old_nids": [h["id"] for h in old_hits], "verdict": verdict}
        # 无冲突 → 正常添加
        new_nid = self.add(text, ntype)
        self.save()  # [AD1 修复] 无冲突分支缺 save (新节点丢失)
        return {"conflict": False, "new_nid": new_nid, "old_nids": [],
                "verdict": verdict}

    # ── 三态提升/降级 (Cache 替换策略) ──
    # ══ [CoMem 借鉴 2026-09-16] 提升门: 曝光 ∧ 相对基线 ══
    # 原文 (arXiv 2609.15009v1 §3.3): ι_prom = 𝟙[(N_use(m) ≥ N_min) ∧ (R̄_m ≥ R̄)]
    #   N_use = 被成功检索的 episode 数 (统计下限, 防偶发激活)
    #   R̄_m   = 被使用时的平均任务得分 ;  R̄ = 环境级移动基线
    # 动机 (本机实测缺陷): 原实现用【生命周期累计 access】当近期活跃
    #   → 327 个 access>=8 节点中 322 个已闲置 34 天, 一次触碰即回 HOT
    # 设计要点:
    #   · 曝光信号取 _timeline (再加/重观察 = 被经验【再次确认】), 与 access
    #     (检索命中累计)【语义分离】—— 混淆二者正是原缺陷根因
    #   · 停摆守卫: 若全库放行数 < GATE_FREEZE_MIN 且存在候选 → 大声告警
    #     (防"阈值落在退化值+无告警"的静默失效; 见 sleep_memory_v2 教训)
    #   · 可回退: env CORTEXMEM_GATE=legacy 立即恢复旧规则
    # ★ 校准 (2026-09-16, 真实 14,458 节点实测):
    #   W=7  N=3 → 放行 0    🔴 停摆 (存储整体闲置 34 天)
    #   W=30 N=3 → 放行 13   (过苛)
    #   W=30 N=1 → 放行 69
    #   W=60 N=3 → 放行 262  ← 采用 (1.81%; 旧规则 1,869 = 12.9%, 收紧 7.1×)
    #   W>=60 起饱和 (全库 timeline 事件 P5-P99 均为 34 天前的单一批次)
    # ⚠️ 校准局限: 本库活动史为单一批次 → 窗口判别力有限;
    #    待积累 >=90 天连续活动后须重跑 scripts/cortexmem_comem_ab.py 重标定
    GATE_WINDOW_DAYS = 60     # 曝光窗口 (天) — 已校准
    GATE_N_MIN = 3            # 曝光下限 (窗口内强化事件数)
    GATE_FREEZE_MIN = 1       # 停摆守卫阈值
    _gate_warned = False

    def _gate_mode(self):
        import os
        return os.environ.get("CORTEXMEM_GATE", "comem").lower()

    def _recent_reinforce(self, node):
        """窗口内【强化事件】数 (_timeline = 再加/重观察时间戳)"""
        t = node.get("_timeline") or []
        if not isinstance(t, list):
            return 0
        cut = time.time() - self.GATE_WINDOW_DAYS * 86400
        return sum(1 for x in t if isinstance(x, (int, float)) and x >= cut)

    def _baseline_weight(self):
        """环境级移动基线 R̄ (全局平均权重)"""
        nodes = self.state["nodes"]
        if not nodes:
            return 1.0
        return sum(n.get("weight", 1.0) for n in nodes.values()) / len(nodes)

    def gate_profile(self):
        """提升门诊断画像 (全库决策分布; 防停摆自检)"""
        nodes = self.state["nodes"]
        base = self._baseline_weight()
        admit = rej_exp = rej_base = 0
        for nid, node in nodes.items():
            if self._recent_reinforce(node) < self.GATE_N_MIN:
                rej_exp += 1
                continue
            if node.get("weight", 1.0) < base:
                rej_base += 1
                continue
            if node["state"] in (COLD, WARM):
                admit += 1
        cand = sum(1 for n in nodes.values() if n["state"] in (COLD, WARM))
        frozen = (admit < self.GATE_FREEZE_MIN and cand > 0)
        return {"mode": self._gate_mode(), "total": len(nodes), "baseline_R": round(base, 4),
                "admit": admit, "reject_exposure": rej_exp, "reject_baseline": rej_base,
                "candidates": cand, "frozen": frozen,
                "window_days": self.GATE_WINDOW_DAYS, "n_min": self.GATE_N_MIN}

    def _promote(self, nid, force: bool = False):
        """★ CoMem 提升门 (2026-09-16 重构)

        force=True: 显式用户动作 (pin / feedback 喜欢) 绕过门 —— 用户意图优先于统计
        force=False: 自动路径 (检索命中) 走门
        """
        node = self.state["nodes"].get(nid)
        if not node:
            return
        if not force:
            if self._gate_mode() == "legacy":
                # 旧规则 (保留供回退/对照)
                if node["state"] == COLD and node.get("access", 0) >= 3:
                    node["state"] = WARM
                if node["state"] == WARM and node.get("access", 0) >= 8:
                    node["state"] = HOT
                return
            # ── CoMem 门: 曝光 ∧ 相对基线 ──
            if self._recent_reinforce(node) < self.GATE_N_MIN:
                return                       # 曝光不足 → 拒绝
            if node.get("weight", 1.0) < self._baseline_weight():
                return                       # 低于基线 → 拒绝
        if node["state"] == COLD:
            node["state"] = WARM
        elif node["state"] == WARM:
            node["state"] = HOT


    def _demote(self, nid):
        node = self.state["nodes"].get(nid)
        if not node:
            return
        if node["state"] == HOT and time.time() - node["last_access"] > 7*86400:
            node["state"] = WARM
        if node["state"] == WARM and time.time() - node["last_access"] > 21*86400:
            node["state"] = COLD

    # ── [N3] 反馈驱动检索 (MemOS 借鉴): 用户反馈修正权重 ──
    def feedback(self, nid: str, liked: bool) -> dict:
        """用户反馈: 喜欢 → 权重↑ / 不喜欢 → 权重↓"""
        if nid not in self.state["nodes"]:
            return {"error": "未找到"}
        node = self.state["nodes"][nid]
        delta = 0.15 if liked else -0.15
        node["weight"] = max(0.1, min(2.0, node["weight"] + delta))
        node["feedback"] += delta
        if liked:
            self._promote(nid, force=True)   # ★ 显式用户喜欢 → 绕过 CoMem 门
        else:
            node["state"] = COLD
        self.save()
        return {"nid": nid, "weight": round(node["weight"], 2),
                "feedback": round(node["feedback"], 2)}

    # ── [N5] 版本化 (Mem0 history 借鉴): 重写可回溯 ──
    def update(self, nid: str, new_text: str) -> dict:
        """更新记忆 → 旧版入 history, 版本号++"""
        if nid not in self.state["nodes"]:
            return {"error": "未找到"}
        node = self.state["nodes"][nid]
        node["history"].append({
            "content": node["content"], "version": node["version"],
            "time": time.time(),
        })
        # 更新倒排索引
        for w in self._words(node["content"]):
            self.state["inverted"][w].discard(nid)
        node["content"] = new_text
        node["version"] += 1
        for w in self._words(new_text):
            self.state["inverted"][w].add(nid)
        self.save()
        return {"nid": nid, "version": node["version"],
                "history_len": len(node["history"])}

    # ── [N4] 决策修复 (MemOS 借鉴): 检索失败自动修复查询 ──
    def query_repair(self, q: str, top_k: int = 3) -> dict:
        """检索失败 → 自动修复: 缩短查询/同义词/宽泛化"""
        results = self.query(q, top_k)
        if results:
            return {"repaired": False, "results": results}
        # 修复策略 1: 去掉停用词/短词
        q2 = " ".join([w for w in q.split() if len(w) > 1])
        results = self.query(q2, top_k)
        if results:
            return {"repaired": True, "strategy": "shorten", "results": results}
        # 修复策略 2: 实体查询 (提取实体→查实体节点)
        ents = self._extract_entities(q)
        if ents:
            ent_q = "实体:" + ents[0]
            results = self.query(ent_q, top_k)
            if results:
                return {"repaired": True, "strategy": "entity", "results": results}
        # 修复策略 3: 热门记忆兜底
        hot = [n for n in self.state["nodes"].values() if n["state"] == HOT][:top_k]
        results = [{"nid": n["id"], "content": n["content"][:50], "score": 0.1}
                   for n in hot]
        return {"repaired": True, "strategy": "hot_fallback", "results": results}

    # ── 检索: 双路 (倒排+图) + [N1] 会话过滤 + [N3] 反馈权重 ──
    def query(self, q: str, top_k: int = 5, session_id: str = None) -> list:
        q_words = self._words(q)
        if not q_words:
            return []
        # 路1: 倒排索引 (关键词精确)
        candidates = set()
        for w in q_words:
            candidates |= self.state["inverted"].get(w, set())
        # 路2: 图遍历 (关联扩展)
        scored = []
        for nid in candidates:
            node = self.state["nodes"].get(nid)
            if not node:
                continue
            sim = len(self._words(node["content"]) & q_words)
            if sim > 0:
                # [N1] 会话作用域过滤 (Mem0): 指定 session 只检索该会话
                if session_id and node.get("session_id") != session_id:
                    continue
                boost = {"hot": 1.5, "warm": 1.2, "cold": 1.0}[node["state"]]
                # [N3] 反馈权重 (MemOS)
                fb_boost = 1.0 if node.get("feedback", 0) >= 0 else 0.85
                score = sim * node["weight"] * boost * fb_boost * (1 + min(0.5, node["access"]*0.05))
                # [X1] VoltMem 速度分级: 易变事实→新鲜度敏感 (旧 volatile 快速衰减)
                if node.get("velocity") == "volatile":
                    age_days = (time.time() - node.get("last_access", time.time())) / 86400
                    score *= max(0.3, 1.0 - age_days * 0.15)  # 旧 volatile 降权 (新鲜优先)
                else:  # stable 抗污染
                    score *= 1.05
                # [M1] 实体提升: 查询含实体 → 实体相关节点加分 (Mem0 借鉴)
                q_entities = self._extract_entities(q)
                if node.get("entity"):
                    score *= 1.3
                elif q_entities and any(e.lower() in node["content"].lower() for e in q_entities):
                    score *= 1.2
                # [M2] 晶体技能提升: 成熟技能优先
                if node.get("crystal", 0) > 1:
                    score *= 1 + min(0.3, node["crystal"] * 0.05)
                scored.append((score, nid, node))
                self.state["nodes"][nid]["access"] += 1
                self._promote(nid)
        scored.sort(key=lambda x: -x[0])
        return [{"id": nid, "content": node["content"][:80], "type": node["type"],
                 "state": node["state"], "score": round(s, 3)} for s, nid, node in scored[:top_k]]

    # ══ [CoMem 借鉴 2026-09-16] 机制③: 多样性过滤检索 ══
    # 原文 (arXiv 2609.15009v1 §3.4 Parallel Dual-Stream Retrieval):
    #   "group semantically similar candidates into clusters, and then select
    #    the most representative entry from each cluster"
    # 动机: 单流 top-k 按分直取 → 返回【近似重复】条目, 浪费上下文
    #   原文证据: 共享记忆【常不如无记忆】(G-Memory 59.53 vs No-mem 67.78)
    # 本机 A/B (n=60 真实查询, bge-m3 真实 embedding, 见 cortexmem_comem_ab.py):
    #   基线冗余 0.5836 → 配置(0.60, 40) 冗余 0.5119 = ↓12.3% / 簇数 ↑5.6%
    #   扫描结论: 阈值 0.60 最优; 池 40 优于 20; 0.50 过松(不合并)、0.80 过紧
    # 降级准则: 多样性过滤是【加速器】(优化路径) 而非【门】(安全边界)
    #   → 按 fails-open 准则: embedding 不可用则原样返回单流结果
    COMEM_THRESH = 0.60
    COMEM_POOL = 40

    @staticmethod
    def _cosine(a, b):
        if not a or not b:
            return 0.0
        s = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return s / (na * nb) if na and nb else 0.0

    @classmethod
    def _cluster_embs(cls, embs, thresh):
        """单链层次聚类 → 簇标签 (O(n²), 池 ≤ 40 足够)"""
        n = len(embs)
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i in range(n):
            for j in range(i + 1, n):
                if cls._cosine(embs[i], embs[j]) >= thresh:
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[rj] = ri
        remap, out = {}, []
        for i in range(n):
            l = find(i)
            if l not in remap:
                remap[l] = len(remap)
            out.append(remap[l])
        return out

    def query_diverse(self, q: str, top_k: int = 5, session_id: str = None,
                      pool: int = None, thresh: float = None) -> list:
        """多样性过滤检索 (CoMem 机制③): 候选池 → 聚类 → 每簇取代表

        返回结构与 query() 一致 (加 cluster 字段供观察); 失败则降级为单流。
        """
        pool = pool or self.COMEM_POOL
        thresh = self.COMEM_THRESH if thresh is None else thresh
        cands = self.query(q, top_k=pool, session_id=session_id)
        if len(cands) <= top_k:
            for c in cands:
                c["cluster"] = 0
            return cands
        texts = [self.state["nodes"][c["id"]]["content"][:500] for c in cands]
        embs = [self._embed(t) for t in texts]
        if any(e is None for e in embs):
            for c in cands[:top_k]:
                c["cluster"] = -1        # -1 = 降级 (无多样性过滤)
            return cands[:top_k]
        labels = self._cluster_embs(embs, thresh)
        clusters = {}
        for idx, lab in enumerate(labels):
            clusters.setdefault(lab, []).append(idx)      # 池内已按分降序
        out, seen = [], set()
        order = sorted(clusters.keys(), key=lambda l: clusters[l][0])
        while len(out) < top_k and len(seen) < len(cands):
            for lab in order:
                for idx in clusters[lab]:
                    if idx not in seen:
                        c = dict(cands[idx])
                        c["cluster"] = lab
                        out.append(c)
                        seen.add(idx)
                        break
                if len(out) >= top_k:
                    break
        return out


    # ── [S2] turn_sync 即时同步 (Tablestore 借鉴: 每轮对话后增量写) ──
    def turn_sync(self, user_text: str, assistant_text: str = "",
                  session_id: str = "default", max_keep: int = 200):
        """每轮对话后调用: 即时记录本轮的语义要点 (不等每日巩固)
        参数:
          user_text: 用户本轮内容 (主记忆源)
          assistant_text: 助手回应摘要 (可空)
          max_keep: 单会话保留上限 (防膨胀)
        """
        if not user_text or len(user_text) < 8:
            return 0
        # 写入语义节点 (即时, 不等 sleep)
        self.add(user_text[:200], ntype=SEMANTIC, session_id=session_id)
        added = 1
        # 会话内去重控制: 相似内容不重复膨胀
        session_nodes = [n for n in self.state["nodes"].values()
                         if n.get("session_id") == session_id]
        if len(session_nodes) > max_keep:
            # ★ 2026-09-12 修复 (R988/R989 诊断): 原实现【硬删除】最久未访问节点
            #   与 tier_manager "低值 = 降层保留 (可追溯), 禁止静默删除" 纪律【冲突】
            # 修法: 改为【降层标记】而非删除 — 保留可追溯性, 由 tier 机制统一治理
            oldest = sorted(session_nodes, key=lambda n: n.get("last_access", 0))[:5]
            for n in oldest:
                for nid, node in list(self.state["nodes"].items()):
                    if node is n:
                        # 标记为 cold (降层), 不删; 加审计痕迹
                        node["tier"] = "cold"
                        node["demoted_at"] = datetime.now(timezone.utc).isoformat()
                        node["demote_reason"] = f"session_overflow(max_keep={max_keep})"
                        break
        self.save()
        return added

    # [AK1] 归档检索: 从 archive 检索已蒸馏归档的 episodic 组 (2026-08-13)
    def archive_query(self, q: str, top_k: int = 5) -> list:
        """归档检索: 匹配 topic/contents 关键词, 返回归档组"""
        q_grams = set(self._topic_ngrams(q))
        scored = []
        for a in self.state.get("archive", []):
            topic = a.get("topic", "")
            contents = a.get("contents", [])
            text = topic + " " + " ".join(contents)
            a_grams = set(self._topic_ngrams(text))
            sim = len(q_grams & a_grams)
            if sim > 0:
                scored.append({"score": sim, "topic": topic,
                               "contents": contents[:3],
                               "ts": a.get("ts", 0), "nids": a.get("nids", [])})
        scored.sort(key=lambda x: -x["score"])
        return scored[:top_k]

    # [AN1] 模板压缩: 同构消息 (数字/URL 归一化) >10 次 → 单模板节点 (2026-08-13)
    def compress_templates(self, min_count: int = 10) -> int:
        """识别 cron 同构消息模板 (如 2713x 微信二维码) → 合并为模板节点"""
        import re as _re
        episodic = {nid: n for nid, n in self.state["nodes"].items()
                    if n.get("type") == EPISODIC}

        def template(s):
            s2 = _re.sub(r"https?://\S+", "URL", s)
            s2 = _re.sub(r"\d+", "N", s2)
            return s2.strip()[:40]

        tpl_count = {}
        for nid, n in episodic.items():
            t = template(n["content"])
            tpl_count.setdefault(t, []).append(nid)
        compressed = 0
        for t, nids in tpl_count.items():
            if len(nids) >= min_count:
                # 模板节点 (代表 + 计数)
                rep = episodic[nids[0]]["content"][:60]
                tid = self._nid(f"模板[{len(nids)}次]: " + rep[:30], SEMANTIC)
                if tid not in self.state["nodes"]:
                    self.state["nodes"][tid] = {
                        "id": tid, "type": SEMANTIC, "content": f"模板[{len(nids)}次]: {rep}",
                        "state": WARM, "weight": 1.0, "access": len(nids),
                        "version": 1, "created": time.time(), "last_access": time.time(),
                        "velocity": "stable", "_timeline": [time.time()],
                        "_template": True, "_count": len(nids)}
                    for w in self._words(rep):
                        self.state["inverted"][w].add(tid)
                # 原 episodic 归档
                self.state.setdefault("archive", []).append({
                    "ts": time.time(), "nids": nids, "topic": rep[:20],
                    "contents": [episodic[nid]["content"][:60] for nid in nids[:3]],
                    "template": t})
                for nid in nids:
                    del self.state["nodes"][nid]
                compressed += len(nids)
        if compressed:
            self.save()
        return compressed

    # ── 睡眠巩固 (海马→新皮层迁移 + 蒸馏) ──
    def sleep(self):
        """离线巩固: 蒸馏程序技能 + 剪枝干扰 + 降级"""
        episodic = {nid: n for nid, n in self.state["nodes"].items() if n["type"] == EPISODIC}
        # 聚类 (群论轨道)
        clusters, used = [], set()
        for nid, node in episodic.items():
            if nid in used:
                continue
            cluster = [nid]
            node_grams = set(self._topic_ngrams(node["content"]))
            for nid2, node2 in episodic.items():
                if nid2 not in used and nid2 != nid:
                    # [AJ2] bigram 聚类 (单字 overlap 太弱, 16K 库仅 108 簇)
                    overlap = len(node_grams & set(self._topic_ngrams(node2["content"])))
                    if overlap >= 2:
                        cluster.append(nid2); used.add(nid2)
            used.add(nid)
            clusters.append(cluster)

        # 蒸馏: 3+ 相似 → 程序技能 (轨道稳定化) [M2: 晶体化升级]
        distilled = 0
        semanticized = 0  # [AB1] 2 相似 → 语义蒸馏 (缓解 episodic 失衡)
        for cluster in clusters:
            if len(cluster) >= 3:
                words = Counter()
                for cid in cluster:
                    words.update(self._words(self.state["nodes"][cid]["content"]))
                # [AH2] 语义化主题: bigram 交集 (非单字拼接)
                common = self._semantic_common([self.state["nodes"][cid]["content"]
                                                for cid in cluster])
                if common:
                    skill_text = "技能: " + " ".join(common)
                    nid = self._nid(skill_text, PROCEDURAL)
                    if nid in self.state["nodes"]:
                        # [M2] 晶体化: 技能命中 → 成熟度↑ (MemOS 技能晶体)
                        node = self.state["nodes"][nid]
                        node["crystal"] = node.get("crystal", 1) + 1
                        node["verified"] = node.get("verified", 0) + 1  # 使用验证
                        node["weight"] = min(2.0, node["weight"] + 0.1)
                    else:
                        self.add(skill_text, PROCEDURAL, HOT)
                        self.state["nodes"][self._nid(skill_text, PROCEDURAL)]["crystal"] = 1
                        self.state["nodes"][self._nid(skill_text, PROCEDURAL)]["verified"] = 0
                    distilled += 1
            elif len(cluster) == 2:
                # [AB1] 2 相似 episodic → 语义蒸馏 (共同主题 → semantic 节点)
                contents = [self.state["nodes"][cid]["content"] for cid in cluster]
                common = self._semantic_common(contents)
                if len(common) >= 1:
                    # [AH3] 语义化: 主题词 + embedding medoid 语义句 (非纯词串)
                    sem_sent, used_emb = self._semantic_sentence(contents, common)
                    sem_text = "主题: " + " ".join(common[:3])
                    if sem_sent:
                        sem_text += " | 实例: " + sem_sent
                    sid = self._nid(sem_text, SEMANTIC)
                    if sid not in self.state["nodes"]:
                        self.add(sem_text, SEMANTIC, WARM)
                        semanticized += 1
                    # [AJ2] 蒸馏后 episodic 归档 (移出主库瘦身, 可追溯不删除)
                    self.state.setdefault("archive", []).append({
                        "ts": time.time(), "nids": cluster,
                        "topic": " ".join(common[:3]),
                        "semantic": sem_sent if used_emb else None,  # [AH3] 语义句快照
                        "contents": [self.state["nodes"][cid]["content"][:80]
                                     for cid in cluster]})  # [AK1] 内容快照
                    for cid in cluster:
                        del self.state["nodes"][cid]

        # 剪枝: Ebbinghaus 遗忘曲线强度 (Cortex-Mem 借鉴)
        pruned = 0
        archived = 0
        for nid in list(self.state["nodes"].keys()):
            node = self.state["nodes"][nid]
            if node.get("pinned"):
                continue  # [O4] pinned 永不驱逐 (AgeMem 借鉴)
            strength = self.compute_strength(node)
            if strength < 0.02:
                del self.state["nodes"][nid]
                pruned += 1
            elif strength < 0.1:
                node["state"] = COLD
                archived += 1

        # 降级 (Cache)
        for nid in self.state["nodes"]:
            self._demote(nid)

        self.state["runs"] += 1
        self.state["consolidated"] += distilled + semanticized
        self.save()  # [AC1 修复] sleep 修改持久化 (原无 save 丢失)
        return {"distilled": distilled, "semanticized": semanticized,
                "clusters": len(clusters), "pruned": pruned, "archived": archived}

    # ── [O1] Ebbinghaus 遗忘曲线 (Cortex-Mem 借鉴) ──
    def compute_strength(self, node) -> float:
        """记忆强度: 权重 × 时间衰减 (Ebbinghaus 遗忘曲线)
        strength = weight × e^(-λ × Δt/τ)   (λ 遗忘率, τ 基准周期)
        """
        age_days = (time.time() - node.get("last_access", time.time())) / 86400
        # 遗忘率: 高频访问记忆衰减慢 (访问次数↑ → λ↓)
        lam = 0.05 / (1 + min(3.0, node.get("access", 1) * 0.1))
        # 反馈增强: 用户喜欢的记忆强度更高
        fb = 1.0 + max(0.0, node.get("feedback", 0))
        strength = node["weight"] * math.exp(-lam * age_days) * fb
        # 实体/技能晶体保护
        if node.get("crystal", 0) > 1:
            strength *= 1.5
        if node.get("entity"):
            strength *= 1.2
        return strength

    def stats(self):
        types = Counter(n["type"] for n in self.state["nodes"].values())
        states = Counter(n["state"] for n in self.state["nodes"].values())
        return {"nodes": len(self.state["nodes"]), "edges": len(self.state["edges"]),
                "types": dict(types), "states": dict(states),
                "runs": self.state["runs"], "consolidated": self.state["consolidated"]}

    # ── [O2] L0/L1/L2 渐进披露 (Cortex-Mem 借鉴) ──
    def disclose(self, q: str, top_k: int = 5) -> dict:
        """渐进披露: L0 粗筛(短) → L1 摘要(中) → L2 全文(需展开)
        L0: content[:60]  (快速定位)
        L1: content[:200] (结构化摘要)
        L2: 全文          (按需展开)
        """
        results = self.query(q, top_k)
        disclosed = []
        for r in results:
            content = r["content"]
            item = {
                "id": r["id"], "score": round(r["score"], 3),
                "L0": content[:60],                    # 粗筛
                "L1": content[:200] if len(content) > 60 else content,  # 摘要
                "has_L2": len(content) > 200,          # 是否需展开
            }
            disclosed.append(item)
        return {"count": len(disclosed), "items": disclosed,
                "tip": "需要细节请指定 expand=<id>"}

    def expand(self, nid: str) -> dict:
        """L2 展开: 返回全文"""
        if nid not in self.state["nodes"]:
            return {"error": "未找到"}
        n = self.state["nodes"][nid]
        return {"id": nid, "L2": n["content"], "type": n["type"],
                "state": n["state"], "weight": round(n["weight"], 2)}

    # ── [O3] LLM 结果缓存 LRU+TTL (Cortex-Mem 借鉴) + [T1] ANN 语义层 (prompt-cache 借鉴) ──
    def _semantic_sim(self, a: str, b: str) -> float:
        """字符级语义相似度 (Jaccard on bigrams, 零依赖近似余弦)"""
        if not a or not b:
            return 0.0
        ab = {a[i:i+2] for i in range(len(a)-1)}
        bb = {b[i:i+2] for i in range(len(b)-1)}
        if not ab or not bb:
            return 0.0
        inter = len(ab & bb)
        return inter / (len(ab) + len(bb) - inter) if inter else 0.0

    def cached_query(self, q: str, top_k: int = 5, ttl_sec: int = 3600,
                     sem_threshold: float = 0.55) -> dict:
        """带缓存查询: 相同查询 TTL 内直接返回 (精确键快路径)
        [T1] ANN 语义层: 精确未命中 → 语义近路径 (bigram Jaccard ≥ 阈值)
        LRU: 缓存超限淘汰最久未用
        """
        cache = self.state.setdefault("query_cache", {})
        key = f"{q}:{top_k}"
        now = time.time()
        # 快路径: 精确键 TTL 命中
        if key in cache and now - cache[key]["time"] < ttl_sec:
            cache[key]["last_use"] = now
            cache[key]["hits"] = cache[key]["hits"] + 1
            return {"cached": True, "semantic": False, "hits": cache[key]["hits"],
                    "results": cache[key]["results"]}
        # [T1] 语义近路径: 遍历缓存找语义相似查询 (ANN 近似)
        sem_hit = None
        best_sim = 0.0
        for k, v in cache.items():
            if now - v["time"] < ttl_sec:
                sim = self._semantic_sim(q, k.split(":")[0])
                if sim >= sem_threshold and sim > best_sim:
                    best_sim = sim
                    sem_hit = v
        if sem_hit:
            sem_hit["last_use"] = now
            return {"cached": True, "semantic": True, "sim": round(best_sim, 2),
                    "results": sem_hit["results"]}
        # 未命中 → 查询 + 缓存
        results = self.query(q, top_k)
        cache[key] = {"results": results, "time": now, "last_use": now,
                      "hits": 0}
        # LRU 淘汰: 缓存 > 50 条 → 删最久未用
        if len(cache) > 50:
            oldest = min(cache, key=lambda k: cache[k]["last_use"])
            del cache[oldest]
        self.save()
        return {"cached": False, "results": results}

    # ── [O4] pinned 永不驱逐 (AgeMem 借鉴) ──
    def pin(self, nid: str, pinned: bool = True) -> dict:
        """固定记忆: 永不归档/删除 (pinned)"""
        if nid not in self.state["nodes"]:
            return {"error": "未找到"}
        self.state["nodes"][nid]["pinned"] = pinned
        if pinned:
            self._promote(nid, force=True)   # ★ 显式用户动作 → 绕过 CoMem 门
        self.save()
        return {"nid": nid, "pinned": pinned}

    # ── [O4] 符号压缩 (TencentDB 借鉴) ──
    def compress(self, nid: str) -> dict:
        """符号化压缩: 长内容 → 结构化符号摘要 (省 token)
        例: "训练失败 OOM 3次, 修改max_length=96后成功"
          → "[训练:失败3→成功1] max_length≤96"
        """
        if nid not in self.state["nodes"]:
            return {"error": "未找到"}
        node = self.state["nodes"][nid]
        content = node["content"]
        if len(content) <= 100:
            return {"nid": nid, "compressed": False, "reason": "已足够短"}
        # 提取关键符号: 数字/百分比/技术词
        nums = re.findall(r'\d+(?:\.\d+)?%?', content)[:3]
        techs = [t for t in ["OOM", "GPU", "CUDA", "WSL", "RTX", "Redis", "token",
                             "max_length", "stdout", "VPS", "API"] if t in content]
        keys = content[:20].strip()
        symbol = f"[{keys}...|{'/'.join(techs[:3]) or '杂'}×{'/'.join(nums[:2]) or 'N'}]"
        node["content"] = symbol
        node["compressed"] = True
        # 保留原文在 history (可回溯)
        node.setdefault("history", []).append({"content": content, "version": node["version"],
                                                "time": time.time()})
        node["version"] += 1
        # 更新倒排
        for w in self._words(content):
            self.state["inverted"][w].discard(nid)
        for w in self._words(symbol):
            self.state["inverted"][w].add(nid)
        self.save()
        return {"nid": nid, "compressed": True, "symbol": symbol,
                "saved_chars": len(content) - len(symbol)}

    # ── 30 天模拟 ──
    def simulate_30d(self):
        n = 200
        strengths = [random.uniform(0.3, 0.9) for _ in range(n)]
        access = list(np_random_zipf(n))
        mx = max(access)
        access = [a/mx for a in access]
        for day in range(30):
            for i in range(n):
                s = strengths[i] * 0.99 + access[i] * 0.06  # 三态驻留
                if day % 7 == 6:
                    s = min(1.0, s * 1.12)  # 睡眠巩固
                strengths[i] = max(0.01, min(1.0, s))
        return sum(strengths) / n

def np_random_zipf(n):
    import numpy as np
    return list(np.random.zipf(1.5, n))

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    mem = CortexMem()
    if "--init" in sys.argv:
        audit = os.path.join(BASE, "knowledge_base", "audit")
        for f in os.listdir(audit)[:30]:
            if f.endswith(".md"):
                text = open(os.path.join(audit, f), encoding="utf-8", errors="replace").read()
                mem.add(f[:50], SEMANTIC)
                mem.add(text[:150], EPISODIC)
        mem.save()
        print(f"✅ CortexMem 初始化: {mem.stats()}")
    elif "--add" in sys.argv:
        i = sys.argv.index("--add")
        mem.add(" ".join(sys.argv[i+1:]))
        mem.save()
        print(f"✅ 添加: {mem.stats()['nodes']} 节点")
    elif "--query" in sys.argv:
        i = sys.argv.index("--query")
        q = " ".join(sys.argv[i+1:])
        for r in mem.query(q):
            print(f"  [{r['state']}/{r['type']}] {r['content'][:40]} (score={r['score']})")
    elif "--sleep" in sys.argv:
        r = mem.sleep()
        mem.save()
        print(f"🌙 睡眠巩固: {r} | {mem.stats()}")
    elif "--sim" in sys.argv:
        print(f"📊 CortexMem 30天保持率: {mem.simulate_30d():.3f} (基线 0.331)")
    else:
        print("用法: --init | --add <text> | --query <q> | --sleep | --sim")
