#!/usr/bin/env python3
"""
Hermes Token Tracker — 实时Token消耗采集 + 统计 + 成本推算
A: 解析agent.log历史数据
B: cron定期采集（增量模式）
C: 提供结构化数据给算渊Agent
"""
import json, os, re, sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter, defaultdict

# ── 路径 ──
HOME = Path(os.path.expanduser("~/AppData/Local/hermes"))
PROFILE = HOME / "profiles" / "mybot"
AGENT_LOG = PROFILE / "logs" / "agent.log"
OUTPUT_DIR = PROFILE / "token_stats"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# DeepSeek pricing (as of 2026-07)
PRICING = {
    "deepseek-v4-flash": {
        "input_cache_hit": 0.0028,    # /1M tokens
        "input_cache_miss": 0.14,
        "output": 0.28,
    },
    "deepseek-v4-pro": {
        "input_cache_hit": 0.007,
        "input_cache_miss": 0.50,
        "output": 1.50,
    },
    "unknown": {  # fallback
        "input_cache_hit": 0.01,
        "input_cache_miss": 0.20,
        "output": 0.50,
    },
}

# Token estimation (chars / 4 = approx tokens)
CHARS_PER_TOKEN = 4

# ── Log Parsers ──

def parse_turn_entries(log_path: Path) -> list[dict]:
    """
    解析 agent.log 中的 API call 记录（含真实Token计数）。
    格式: 'API call #N: model=... provider=... in=... out=... total=... latency=... cache=...'
    """
    results = []
    if not log_path.exists():
        return results
    
    text = log_path.read_text(encoding="utf-8", errors="replace")
    
    # Primary pattern: API call records (含真实in/out tokens + cache信息)
    pattern = re.compile(
        r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d+)\s+\S+\s+'
        r'\[([^\]]+)\]\s+\S+\.\S+:\s+API call #(\d+):'
        r'\s+model=(\S+)'
        r'\s+provider=(\S+)'
        r'\s+in=(\d+)'
        r'\s+out=(\d+)'
        r'\s+total=(\d+)'
        r'\s+latency=([\d.]+)s'
        r'\s+cache=(\d+)/(\d+)\s+\((\d+)%\)'
    )
    
    for match in pattern.finditer(text):
        timestamp_str = match.group(1)
        session_id = match.group(2)
        call_num = int(match.group(3))
        model = match.group(4)
        provider = match.group(5)
        input_tokens = int(match.group(6))
        output_tokens = int(match.group(7))
        total_tokens = int(match.group(8))
        latency = float(match.group(9))
        cache_hit = int(match.group(10))
        cache_total = int(match.group(11))
        cache_pct = int(match.group(12))
        
        try:
            ts = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S,%f")
        except:
            ts = datetime.now()
        
        # 从session_id反推平台 (session_id前缀带平台信息)
        platform = "unknown"
        if session_id.startswith("20") and len(session_id) > 10:
            # Regular session format, check source from context
            platform = "tui"  # default
        if "weixin" in session_id.lower():
            platform = "weixin"
        
        results.append({
            "timestamp": ts.isoformat(),
            "date": ts.strftime("%Y-%m-%d"),
            "hour": ts.hour,
            "session": session_id,
            "call_num": call_num,
            "model": model,
            "provider": provider,
            "platform": platform,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "latency_seconds": latency,
            "cache_hit_tokens": cache_hit,
            "cache_total_tokens": cache_total,
            "cache_hit_rate": cache_pct,
        })
    
    # Secondary pattern: archive logs (agent.log.1, .2) use different format
    if not results:
        # Fallback: look for "in=" pattern
        alt_pattern = re.compile(
            r'model=(\S+)\s+provider=(\S+)\s+in=(\d+)\s+out=(\d+)\s+total=(\d+)'
            r'\s+latency=([\d.]+)s\s+cache=(\d+)/(\d+)\s+\((\d+)%\)'
        )
        for match in alt_pattern.finditer(text):
            results.append({
                "timestamp": "unknown",
                "date": "unknown",
                "model": match.group(1),
                "provider": match.group(2),
                "input_tokens": int(match.group(3)),
                "output_tokens": int(match.group(4)),
                "total_tokens": int(match.group(5)),
                "latency_seconds": float(match.group(6)),
                "cache_hit_tokens": int(match.group(7)),
                "cache_total_tokens": int(match.group(8)),
                "cache_hit_rate": int(match.group(9)),
            })
    
    return results


def parse_inbound_messages(log_path: Path) -> list[dict]:
    """Parse inbound message records for per-session counts"""
    results = []
    if not log_path.exists():
        return results
    
    text = log_path.read_text(encoding="utf-8", errors="replace")
    
    pattern = re.compile(
        r'inbound message: platform=(\S+)\s+user=(\S+)\s+chat=(\S+)\s+msg=\'(.*?)\''
        r'(?:\s+reply_to_id=(\S+))?'
    )
    
    for match in pattern.finditer(text[:500000]):  # Limit to first 500KB
        results.append({
            "platform": match.group(1),
            "user": match.group(2),
            "msg": match.group(4)[:80],
        })
    
    return results


# ── Statistics ──

def compute_statistics(turns: list[dict]) -> dict:
    """Compute comprehensive statistics from REAL token data"""
    if not turns:
        return {"error": "no data"}
    
    # Per-platform
    by_platform = defaultdict(lambda: {"count": 0, "models": Counter(), 
                                        "input_tokens": 0, "output_tokens": 0, 
                                        "total_tokens": 0, "cache_hits": 0,
                                        "cache_total": 0, "cost_usd": 0.0})
    for t in turns:
        p = t.get("platform", "unknown")
        by_platform[p]["count"] += 1
        by_platform[p]["models"][t["model"]] += 1
        by_platform[p]["input_tokens"] += t.get("input_tokens", 0)
        by_platform[p]["output_tokens"] += t.get("output_tokens", 0)
        by_platform[p]["total_tokens"] += t.get("total_tokens", 0)
        by_platform[p]["cache_hits"] += t.get("cache_hit_tokens", 0)
        by_platform[p]["cache_total"] += t.get("cache_total_tokens", 0)
    
    # Per-model
    by_model = defaultdict(lambda: {"count": 0, "input": 0, "output": 0, "total": 0, "cache": 0})
    for t in turns:
        m = t["model"]
        by_model[m]["count"] += 1
        by_model[m]["input"] += t.get("input_tokens", 0)
        by_model[m]["output"] += t.get("output_tokens", 0)
        by_model[m]["total"] += t.get("total_tokens", 0)
        by_model[m]["cache"] += t.get("cache_hit_tokens", 0)
    
    # Per-day
    by_date = defaultdict(lambda: {"count": 0, "tokens": 0})
    for t in turns:
        d = t.get("date", "unknown")
        by_date[d]["count"] += 1
        by_date[d]["tokens"] += t.get("total_tokens", 0)
    
    # Per-hour
    by_hour = Counter(t.get("hour", 0) for t in turns)
    
    # Overall
    total_input = sum(t.get("input_tokens", 0) for t in turns)
    total_output = sum(t.get("output_tokens", 0) for t in turns)
    total_all = sum(t.get("total_tokens", 0) for t in turns)
    total_cache = sum(t.get("cache_hit_tokens", 0) for t in turns)
    total_latency = sum(t.get("latency_seconds", 0) for t in turns)
    
    avg_cache_rate = round(total_cache / max(1, total_input) * 100, 1)
    avg_latency = round(total_latency / max(1, len(turns)), 1)
    
    unique_sessions = len(set(t["session"] for t in turns))
    
    return {
        "total_api_calls": len(turns),
        "unique_sessions": unique_sessions,
        "real_tokens": {
            "total_input": total_input,
            "total_output": total_output,
            "total_all": total_all,
            "avg_per_call": total_all // max(1, len(turns)),
        },
        "cache": {
            "total_hit_tokens": total_cache,
            "total_eligible_input": total_input,
            "avg_hit_rate_pct": avg_cache_rate,
        },
        "performance": {
            "total_latency_seconds": round(total_latency, 1),
            "avg_latency_per_call_s": avg_latency,
        },
        "by_model": {m: dict(v) for m, v in by_model.items()},
        "by_platform": {p: {
            "count": v["count"],
            "models": dict(v["models"].most_common()),
            "input_tokens": v["input_tokens"],
            "output_tokens": v["output_tokens"],
            "total_tokens": v["total_tokens"],
            "cache_hit_rate_pct": round(v["cache_hits"] / max(1, v["cache_total"]) * 100, 1),
        } for p, v in by_platform.items()},
        "by_date": {d: {"count": v["count"], "tokens": v["tokens"]} 
                     for d, v in sorted(by_date.items())},
        "by_hour": {str(h): by_hour.get(h, 0) for h in range(24)},
        "date_range": {
            "first": turns[0]["date"],
            "last": turns[-1]["date"],
        },
    }


def estimate_cost(stats: dict) -> dict:
    """Estimate API cost from REAL token data"""
    total_req = stats.get("total_api_calls", 0)
    real_tokens = stats.get("real_tokens", {})
    input_total = real_tokens.get("total_input", 0)
    output_total = real_tokens.get("total_output", 0)
    
    per_model = {}
    total_cost = 0.0
    
    for model, data in stats.get("by_model", {}).items():
        pricing = PRICING.get(model, PRICING["unknown"])
        inp = data.get("input", 0)
        out = data.get("output", 0)
        
        # Use real cache rate from data, or default 60%
        cache_rate = stats.get("cache", {}).get("avg_hit_rate_pct", 60) / 100
        
        input_cost = inp / 1e6 * (
            cache_rate * pricing["input_cache_hit"] +
            (1 - cache_rate) * pricing["input_cache_miss"]
        )
        output_cost = out / 1e6 * pricing["output"]
        
        model_cost = input_cost + output_cost
        total_cost += model_cost
        
        per_model[model] = {
            "requests": data["count"],
            "input_tokens": inp,
            "output_tokens": out,
            "cache_rate_pct": round(cache_rate * 100, 1),
            "input_cost_usd": round(input_cost, 4),
            "output_cost_usd": round(output_cost, 4),
            "total_cost_usd": round(model_cost, 4),
        }
    
    return {
        "assumptions": {
            "pricing_source": "DeepSeek官方2026-07",
        },
        "per_model": per_model,
        "total_cost_usd": round(total_cost, 4),
        "yearly_projection_usd": round(total_cost * 365 / max(1, _get_date_span_days(stats)), 2),
    }


def _get_date_span_days(stats: dict) -> int:
    dr = stats.get("date_range", {})
    if not dr or "first" not in dr or "last" not in dr:
        return 1
    try:
        f = datetime.strptime(dr["first"], "%Y-%m-%d")
        l = datetime.strptime(dr["last"], "%Y-%m-%d")
        return max(1, (l - f).days + 1)
    except:
        return 1


# ── Delta mode (for cron) ──

def load_last_checkpoint() -> int:
    cp = OUTPUT_DIR / "checkpoint.txt"
    if cp.exists():
        try:
            return int(cp.read_text().strip())
        except:
            return 0
    return 0


def save_checkpoint(size_bytes: int):
    (OUTPUT_DIR / "checkpoint.txt").write_text(str(size_bytes))


def run_delta_scan() -> dict:
    """扫描日志增量部分"""
    last_pos = load_last_checkpoint()
    current_size = AGENT_LOG.stat().st_size if AGENT_LOG.exists() else 0
    
    if current_size <= last_pos:
        return {"status": "no_new_data", "last_pos": last_pos}
    
    # Read only the new part
    with open(AGENT_LOG, "r", encoding="utf-8", errors="replace") as f:
        f.seek(last_pos)
        new_text = f.read()
    
    # Simple count of new turns
    turn_count = new_text.count("conversation turn:")
    msg_count = new_text.count("inbound message:")
    
    save_checkpoint(current_size)
    
    return {
        "status": "ok",
        "new_bytes": current_size - last_pos,
        "new_turns": turn_count,
        "new_messages": msg_count,
        "new_text_chars": len(new_text),
    }


# ── Console Output ──

def format_report(stats: dict, cost: dict):
    """Format statistics for display"""
    lines = []
    lines.append("═" * 55)
    lines.append("📊 Hermes Token消耗报告 (Agent.log真实数据)")
    dr = stats.get("date_range", {})
    lines.append(f"   周期: {dr.get('first', '?')} → {dr.get('last', '?')}")
    lines.append(f"   API调用: {stats.get('total_api_calls', 0)}")
    lines.append(f"   会话数: {stats.get('unique_sessions', 0)}")
    
    rt = stats.get("real_tokens", {})
    lines.append(f"   输入Tokens: {rt.get('total_input', 0):,}")
    lines.append(f"   输出Tokens: {rt.get('total_output', 0):,}")
    lines.append(f"   总计Tokens: {rt.get('total_all', 0):,}")
    lines.append(f"   平均每次: {rt.get('avg_per_call', 0):,} tokens")
    lines.append("")
    
    c = stats.get("cache", {})
    lines.append(f"💾 缓存命中率: {c.get('avg_hit_rate_pct', 0):.1f}%")
    lines.append(f"⚡ 平均延迟: {stats.get('performance', {}).get('avg_latency_per_call_s', 0):.1f}s")
    lines.append("")
    
    lines.append("📈 按模型:")
    for model, data in stats.get("by_model", {}).items():
        inp = data.get("input", 0)
        out = data.get("output", 0)
        pct = data["count"] / max(1, stats.get("total_api_calls", 1)) * 100
        lines.append(f"   {model:25s}: {data['count']:4d} 次 ({pct:.0f}%) | 输入: {inp//1000:>5}K 输出: {out//1000:>5}K")
    lines.append("")
    
    lines.append("💰 成本估算:")
    for model, data in cost.get("per_model", {}).items():
        lines.append(f"   {model:25s}: ${data['total_cost_usd']:.4f} (输入${data['input_cost_usd']:.4f}+输出${data['output_cost_usd']:.4f})")
    lines.append(f"   ─────────────────────────────────────")
    lines.append(f"   {'总计':>25s}: ${cost.get('total_cost_usd', 0):.4f}")
    lines.append(f"   {'年化预估':>25s}: ${cost.get('yearly_projection_usd', 0):.2f}")
    lines.append("")
    
    lines.append("⏰ 时段热力:")
    hours = stats.get("by_hour", {})
    for h in range(0, 24, 3):
        chunk_sum = sum(int(hours.get(str(i), 0)) for i in range(h, min(h+3, 24)))
        block = "█" * (chunk_sum // 3 + 1) if chunk_sum > 0 else "·"
        lines.append(f"   {h:02d}:00-{min(h+2,23):02d}:00 |{block}| {chunk_sum}")
    lines.append("")
    
    lines.append("📋 近7天趋势:")
    bd = stats.get("by_date", {})
    dates = list(bd.keys())[-7:]
    for d in dates:
        v = bd[d]
        bar = "▓" * min(v["count"], 40)
        lines.append(f"   {d} |{bar}| {v['count']} 次 ({v['tokens']//1000}K tokens)")
    
    lines.append("═" * 55)
    return "\n".join(lines)


# ── Main ──

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "report"
    
    if action == "report":
        # Full analysis of all logs
        print("🔍 扫描 agent.log...")
        
        # Check rotated logs too
        all_turns = []
        for log_file in sorted(AGENT_LOG.parent.glob("agent.log*"), reverse=True):
            turns = parse_turn_entries(log_file)
            all_turns.extend(turns)
            if log_file == AGENT_LOG:
                print(f"   {log_file.name}: {len(turns)} 条turn记录")
            else:
                print(f"   {log_file.name}: {len(turns)} 条turn记录 (历史)")
        
        all_turns.sort(key=lambda x: x["timestamp"])
        
        if not all_turns:
            print("  未找到turn记录，尝试解析inbound messages...")
            msgs = parse_inbound_messages(AGENT_LOG)
            print(f"  找到 {len(msgs)} 条inbound消息")
            
        stats = compute_statistics(all_turns)
        cost = estimate_cost(stats)
        
        # Save report
        report = {
            "generated_at": datetime.now().isoformat(),
            "statistics": stats,
            "cost_estimate": cost,
        }
        report_path = OUTPUT_DIR / f"token_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        
        print(format_report(stats, cost))
        print(f"\n报告已保存: {report_path}")
        
    elif action == "delta":
        # Incremental scan for cron
        result = run_delta_scan()
        print(json.dumps(result, ensure_ascii=False))
        
    elif action == "daily":
        # Daily summary
        result = run_delta_scan()
        turns_24h = result.get("new_turns", 0)
        msgs_24h = result.get("new_messages", 0)
        est_tokens = result.get("new_text_chars", 0) // CHARS_PER_TOKEN
        
        report = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "turns_24h": turns_24h,
            "messages_24h": msgs_24h,
            "estimated_tokens": est_tokens,
        }
        report_path = OUTPUT_DIR / f"daily_{datetime.now().strftime('%Y%m%d')}.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        
        print(f"📊 日统计完成 | 请求: {turns_24h} | 消息: {msgs_24h} | Token估算: {est_tokens}")
        
    elif action == "insights":
        # Output structured data for 算渊 Agent
        all_turns = []
        for log_file in sorted(AGENT_LOG.parent.glob("agent.log*"), reverse=True):
            all_turns.extend(parse_turn_entries(log_file))
        stats = compute_statistics(all_turns)
        cost = estimate_cost(stats)
        print(json.dumps({
            "source": "TokenTracker",
            "timestamp": datetime.now().isoformat(),
            "total_requests": stats["total_requests"],
            "by_model": stats["by_model"],
            "by_platform": stats["by_platform"],
            "cost_usd": cost["total_cost_usd"],
            "yearly_projection": cost["yearly_projection_usd"],
            "estimated_tokens": stats["estimated_tokens"],
            "by_hour": stats["by_hour"],
        }, ensure_ascii=False, indent=2))
    
    elif action == "reset":
        # Reset checkpoint
        save_checkpoint(0)
        print("✅ Checkpoint reset")
    
    else:
        print(f"用法: {sys.argv[0]} [report|delta|daily|insights|reset]")
        print("  report   - 全量分析agent.log")
        print("  delta    - 增量扫描（cron用）")
        print("  daily    - 日统计")
        print("  insights - 输出结构化数据（算渊Agent用）")
        print("  reset    - 重置增量检查点")


if __name__ == "__main__":
    main()
