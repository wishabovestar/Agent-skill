#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agent_handoff.py — Swarm 式【显式交接协议】本地化 (2026-09-17, 借鉴 openai/swarm)

【借鉴来源】openai/swarm @ main (⭐21,986, 未归档; ★ 官方已声明被 OpenAI Agents SDK 取代,
  Swarm 自我定位 "educational / experimental sample framework")
  · swarm/types.py  : `AgentFunction = Callable[[], Union[str, "Agent", dict]]`
  · swarm/core.py   : `handle_function_result` 的 3 分支 match + `if result.agent: ...`
  · swarm/core.py   : `if __CTX_VARS_NAME__ in func.__code__.co_varnames` (零配置 DI)

【Swarm 的单一核心洞见】
  ★ **交接不需要任何专门机制** —— 它只是「**工具函数返回了一个 Agent**」。
  别的框架要图/状态机/专用 API; Swarm 用类型里的一个 Union 表达同一件事。核心仅 ~14KB。

【本机为什么需要它】
  本机有 27 个 agent 角色 (agent_cluster/registry.json) 与 `context_from` 作业链,
  但 `next_agent|handoff_to|delegate_to` 全库 0 命中 ⇒ **交接是隐式的、靠人写 prompt**,
  没有协议、没有目标校验、没有轨迹。

【★ 与上游的三处【有意偏离】(不是照抄)】
  1. **`max_turns` 默认有限** —— Swarm 默认 `float("inf")`; 本机不能这样
     (本会话刚处理完 agent 反复循环类的故障)。
  2. **交接目标必须存在于 registry** —— Swarm 不校验; 本机 27 角色有据可查, 拼错要立刻报。
  3. **防环** —— Swarm 无环检测; 本机首次落地就加 (与 2 一起构成 fail-closed 边界)。

【纪律】函数入参 deepcopy (学 Swarm 的无副作用语义); 失败返回结构化 error 而不抛异常
  (学 Swarm `handle_tool_calls` 的 fail-soft)。
"""
import copy
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(BASE, "agent_cluster", "registry.json")

# ★ 与 Swarm 对齐: 这个形参名出现在函数签名里 ⇒ 自动注入 context (零配置 DI)
CTX_VARS_NAME = "context_variables"
# ★★ 偏离 1: 默认有限 (Swarm 默认 inf)
DEFAULT_MAX_HOPS = 8


@dataclass
class AgentSpec:
    """对应 Swarm 的 `Agent` —— 只保留本机用得到的字段"""
    name: str
    instruction: str = ""
    # 该角色可用的工具: 名字 → 可调用对象
    tools: Dict[str, Callable] = field(default_factory=dict)


@dataclass
class HandoffResult:
    """对应 Swarm 的 `Result` —— ★ 三字段语义完全一致"""
    value: str = ""
    next_agent: Optional[AgentSpec] = None      # ★ 非空 = 发生了交接
    context_variables: Dict[str, Any] = field(default_factory=dict)


def load_registry() -> Dict[str, dict]:
    """读本机 27 角色清单 —— 它的存在是本机相对 Swarm 的加强点"""
    try:
        d = json.load(open(REGISTRY, encoding="utf-8"))
        ag = d.get("agents", {})
        return ag if isinstance(ag, dict) else {}
    except Exception:
        return {}


def normalize_result(raw, caller_name: str) -> HandoffResult:
    """★★★ Swarm `handle_function_result` 的本地化版 (3 分支 match)

    上游:
        case Result():  return result
        case Agent():   return Result(value=json.dumps({"assistant": agent.name}), agent=agent)
        case _:         return Result(value=str(result))

    ★ 本地加强: 交接时把 `{"assistant": <name>}` 作为 value 回传 —— 让调用方/日志
      知道"已交接给谁" (上游靠这条 tool 消息让 LLM 感知交接)。
    """
    if isinstance(raw, HandoffResult):
        return raw
    if isinstance(raw, AgentSpec):
        return HandoffResult(
            value=json.dumps({"assistant": raw.name}, ensure_ascii=False),
            next_agent=raw,
        )
    try:
        return HandoffResult(value=str(raw))
    except Exception:
        return HandoffResult(value="Error: result not castable to string (%s)" % type(raw).__name__)


def call_with_ctx(func: Callable, args: dict, ctx: dict) -> Any:
    """★★ 零配置 DI (学 Swarm `core.py`)

    上游: `if __CTX_VARS_NAME__ in func.__code__.co_varnames: args[__CTX_VARS_NAME__] = context_variables`
    ⇒ **不在签名里写 `context_variables` 就不注入**, 不污染 args。
    """
    args = dict(args)
    try:
        varnames = func.__code__.co_varnames
    except AttributeError:
        varnames = ()
    if CTX_VARS_NAME in varnames:
        args[CTX_VARS_NAME] = ctx
    return func(**args)


def resolve_agent(name: str, tools: Optional[Dict[str, Callable]] = None,
                  registry: Optional[Dict[str, dict]] = None) -> AgentSpec:
    """按 registry 解析出 AgentSpec; 工具可显式给, 也可由调用方注册。

    ★ 为什么加这个函数 (2026-09-17 自检暴露的真实缺口):
      首版要求调用方**手工构造**交接目标, 结果自检里出现 `AgentSpec(name="x")` 忘了带 tools
      ⇒ 第二步立刻 `tool_missing`。上游 Swarm 也有同样问题(handoff 目标必须自备函数),
      但 Swarm 的目标通常是**模块顶层已构造好的 Agent 实例**, 不易漏。
      本机角色在 registry 里有据可查 ⇒ 提供解析器, 让"名字 → 规格"有唯一入口。

    返回的 AgentSpec.tools 为传入的 dict (可为空); 角色名不存在时**返回 None**,
    由调用方决定 fail-soft 还是报错 (不在本函数里抛)。
    """
    reg = registry if registry is not None else load_registry()
    if reg and name not in reg:
        return None
    entry = (reg or {}).get(name, {}) or {}
    desc = entry.get("role") or entry.get("description") or ""
    return AgentSpec(name=name, instruction=str(desc), tools=dict(tools or {}))


def run_chain(start: AgentSpec, steps: List[dict], context_variables: Optional[dict] = None,
              max_hops: int = DEFAULT_MAX_HOPS, known_agents: Optional[set] = None,
              dry_run: bool = False) -> dict:
    """沿【交接链】执行, 返回带轨迹的结果。

    steps: [{"agent": "<name>", "tool": "<tool>", "args": {...}}, ...]
           —— ★ 每一步说"当前谁、调哪个工具"; 工具**返回 AgentSpec 即交接**。
    返回: {"ok", "final", "trace":[{hop, sender, tool, value, handoff_to}], "stopped_by"}
    """
    ctx = copy.deepcopy(context_variables or {})       # ★ 无副作用 (学 Swarm)
    known = known_agents if known_agents is not None else set(load_registry().keys())
    trace: List[dict] = []
    seen: List[str] = []                                # ★ 偏离 3: 防环

    active = start
    for hop, st in enumerate(steps, 1):
        if hop > max_hops:                              # ★ 偏离 1
            return {"ok": False, "final": None, "trace": trace,
                    "stopped_by": "max_hops (%d)" % max_hops}
        tool_name = st.get("tool")
        if tool_name not in active.tools:
            # ★ fail-soft (学 Swarm): 返回结构化 error, 不抛异常
            trace.append({"hop": hop, "sender": active.name, "tool": tool_name,
                          "value": "Error: tool %r not found on agent %r"
                                   % (tool_name, active.name),
                          "handoff_to": None, "is_error": True})
            return {"ok": False, "final": None, "trace": trace,
                    "stopped_by": "tool_missing"}
        raw = ("[dry-run]" if dry_run
               else call_with_ctx(active.tools[tool_name], st.get("args") or {}, ctx))
        norm = normalize_result(raw, active.name)
        ctx.update(norm.context_variables)
        nxt = norm.next_agent
        trace.append({"hop": hop, "sender": active.name, "tool": tool_name,
                      "value": norm.value, "handoff_to": (nxt.name if nxt else None),
                      "is_error": False})
        if nxt is None:
            return {"ok": True, "final": norm.value, "trace": trace, "stopped_by": "no_handoff"}
        # ★ 偏离 2: 目标必须在 registry
        if known and nxt.name not in known:
            trace.append({"hop": hop, "sender": active.name, "tool": tool_name,
                          "value": "Error: handoff target %r not in registry" % nxt.name,
                          "handoff_to": nxt.name, "is_error": True})
            return {"ok": False, "final": None, "trace": trace,
                    "stopped_by": "unknown_agent"}
        # ★ 偏离 3: 防环
        if nxt.name in seen:
            trace.append({"hop": hop, "sender": active.name, "tool": tool_name,
                          "value": "Error: handoff cycle detected -> %r" % nxt.name,
                          "handoff_to": nxt.name, "is_error": True})
            return {"ok": False, "final": None, "trace": trace, "stopped_by": "cycle"}
        seen.append(active.name)
        active = nxt
    return {"ok": True, "final": trace[-1]["value"] if trace else None,
            "trace": trace, "stopped_by": "steps_exhausted"}


def _selftest() -> int:
    print("=" * 78)
    print("  agent_handoff 自检 (Swarm 式交接协议 + 本机三处有意偏离)")
    print("=" * 78)
    ok = True

    # ── P1: 返回 str / AgentSpec 的归一化
    r1 = normalize_result("plain", "a")
    c1 = (r1.value == "plain" and r1.next_agent is None)
    print("  P1  返回 str 不触发交接: %s" % ("✅" if c1 else "🔴"))
    ok &= c1

    a2 = AgentSpec(name="billing")
    r2 = normalize_result(a2, "triage")
    c2 = (r2.next_agent is a2 and json.loads(r2.value)["assistant"] == "billing")
    print("  P2 ★★ 返回 AgentSpec ⇒ 交接, 且 value 带 {\"assistant\": name}: %s"
          % ("✅" if c2 else "🔴"))
    ok &= c2

    # ── P3: 零配置 DI (形参名)
    seen = {}

    def with_ctx(x, context_variables=None):
        seen["has"] = context_variables is not None
        return "ok"

    def without_ctx(x):
        seen["has"] = "NOT_INJECTED"
        return "ok"

    call_with_ctx(with_ctx, {"x": 1}, {"k": "v"})
    d1 = seen["has"] is True
    call_with_ctx(without_ctx, {"x": 1}, {"k": "v"})
    d2 = seen["has"] == "NOT_INJECTED"
    c3 = d1 and d2
    print("  P3 ★★ 零配置 DI: 签名有 context_variables 才注入 (有=%s 无=%s): %s"
          % (d1, d2, "✅" if c3 else "🔴"))
    ok &= c3

    # ── P4: registry 目标校验
    known = {"searcher", "coder", "analyst"}
    t_ok = AgentSpec(name="coder", tools={"go": lambda: AgentSpec(name="analyst")})
    res = run_chain(t_ok, [{"tool": "go"}], known_agents=known)
    c4 = res["ok"] and res["trace"][0]["handoff_to"] == "analyst"
    print("  P4  合法交接通过 (searcher→coder→analyst): %s" % ("✅" if c4 else "🔴"))
    ok &= c4

    t_bad = AgentSpec(name="coder", tools={"go": lambda: AgentSpec(name="typo_agent")})
    res = run_chain(t_bad, [{"tool": "go"}], known_agents=known)
    c5 = (not res["ok"]) and res["stopped_by"] == "unknown_agent"
    print("  P5 ★★ 交接目标不在 registry ⇒ 拒绝 (stopped_by=%s): %s"
          % (res["stopped_by"], "✅" if c5 else "🔴"))
    ok &= c5

    # ── P6: 防环
    # ★ 首版这里失败(报 tool_missing 而非 cycle) —— 是**测试写错**: 交接目标
    #   `AgentSpec(name="searcher")` 没带 tools ⇒ 第二步就找不到工具。
    #   代码行为是对的(fail-soft 捕获)。这里让交接目标带上同样的 tools。
    searcher_full = AgentSpec(name="searcher")
    searcher_full.tools = {"loop": lambda: searcher_full}   # 自环
    t_cyc = searcher_full
    res = run_chain(t_cyc, [{"tool": "loop"}, {"tool": "loop"}, {"tool": "loop"}],
                    known_agents=known)
    c6 = (not res["ok"]) and res["stopped_by"] == "cycle"
    print("  P6 ★★ 交接环被检出 (stopped_by=%s): %s" % (res["stopped_by"], "✅" if c6 else "🔴"))
    ok &= c6

    # ── P7: max_hops 上限真的生效 (偏离 Swarm 的 inf)
    # ★ 第二版才写对: 首版用**自环** ⇒ 环检测先于上限触发, 我拿 `or cycle` 放宽断言,
    #   那等于**没验证 max_hops**。正确做法: 用**无环的 5 角色链** + cap=3。
    chain = {n: AgentSpec(name=n) for n in ("searcher", "coder", "analyst", "writer", "reviewer")}
    order = ["searcher", "coder", "analyst", "writer", "reviewer"]
    for i, n in enumerate(order[:-1]):
        chain[n].tools = {"n": (lambda nx=order[i + 1]: chain[nx])}
    chain[order[-1]].tools = {"n": lambda: "end"}           # 末端不再交接
    res = run_chain(chain["searcher"], [{"tool": "n"}] * 20, max_hops=3,
                    known_agents=set(order))
    c7 = (not res["ok"]) and res["stopped_by"].startswith("max_hops")
    print("  P7 ★★ max_hops 真生效 (无环 5 角色链, steps=20, cap=3 ⇒ %s, 走了 %d 跳): %s"
          % (res["stopped_by"], len(res["trace"]), "✅" if c7 else "🔴"))
    ok &= c7

    # ── P7b: 同一无环链给足上限 ⇒ 正常走完到末端
    res = run_chain(chain["searcher"], [{"tool": "n"}] * 20, max_hops=20,
                    known_agents=set(order))
    c7b = res["ok"] and res["stopped_by"] == "no_handoff" and len(res["trace"]) == 5
    print("  P7b 同一链给足上限 ⇒ 走满 5 跳正常收尾 (跳数=%d, %s): %s"
          % (len(res["trace"]), res["stopped_by"], "✅" if c7b else "🔴"))
    ok &= c7b

    # ── P8: 工具缺失 fail-soft (不抛异常)
    t_nf = AgentSpec(name="searcher", tools={})
    res = run_chain(t_nf, [{"tool": "nope"}], known_agents=known)
    c8 = (not res["ok"]) and res["stopped_by"] == "tool_missing" and res["trace"][0]["is_error"]
    print("  P8  工具缺失 ⇒ 结构化 error 不抛异常: %s" % ("✅" if c8 else "🔴"))
    ok &= c8

    # ── P9: 无副作用 (入参不被改)
    ctx_in = {"a": 1}

    def mut(context_variables=None):
        context_variables["a"] = 999
        context_variables["b"] = 2
        return "done"

    t_m = AgentSpec(name="searcher", tools={"m": mut})
    run_chain(t_m, [{"tool": "m"}], context_variables=ctx_in, known_agents=known)
    c9 = ctx_in == {"a": 1}
    print("  P9 ★ 入参不被修改 (deepcopy 语义, ctx_in=%s): %s"
          % (ctx_in, "✅" if c9 else "🔴"))
    ok &= c9

    # ── P10: 轨迹带 sender (可追溯)
    res = run_chain(t_ok, [{"tool": "go"}], known_agents=known)
    c10 = all("sender" in x for x in res["trace"]) and res["trace"][0]["sender"] == "coder"
    print("  P10 ★ 轨迹每步带 sender (可追溯): %s" % ("✅" if c10 else "🔴"))
    ok &= c10

    # ── P11: dry_run 不真的执行
    called = {"n": 0}

    def side():
        called["n"] += 1
        return "x"

    t_d = AgentSpec(name="searcher", tools={"s": side})
    run_chain(t_d, [{"tool": "s"}], dry_run=True, known_agents=known)
    c11 = called["n"] == 0
    print("  P11 dry_run 不执行工具 (调用次数=%d): %s" % (called["n"], "✅" if c11 else "🔴"))
    ok &= c11

    # ── P12: 真 registry 可加载且角色数 > 0
    reg = load_registry()
    c12 = len(reg) > 0
    print("  P12 本机 registry 可加载 (%d 个角色): %s" % (len(reg), "✅" if c12 else "🔴"))
    ok &= c12

    # ── P13: resolve_agent (把"交接目标忘带工具"这个真实坑固化成 API)
    names = list(reg.keys())
    good = resolve_agent(names[0], tools={"t": lambda: "x"}, registry=reg) if names else None
    bad = resolve_agent("definitely_not_a_role_xyz", registry=reg)
    c13 = (good is not None and good.name == names[0] and "t" in good.tools and bad is None)
    print("  P13 ★ resolve_agent 命中真实角色且解析未知角色为 None: %s"
          % ("✅" if c13 else "🔴"))
    ok &= c13
    res_unknown = run_chain(AgentSpec(name="searcher", tools={"h": lambda: None}),
                            [{"tool": "h"}], known_agents={"searcher"})
    c13b = res_unknown["ok"] and res_unknown["stopped_by"] == "no_handoff"
    print("  P13b 返回 None ⇒ 不交接, 正常结束: %s" % ("✅" if c13b else "🔴"))
    ok &= c13b

    print()
    print("  判定: %s (%d 项)" % ("✅ 全通过" if ok else "🔴 有未通过项", 15))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_selftest())
