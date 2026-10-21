#!/usr/bin/env python3
"""Hindsight 风格记忆优化 — 事件提炼 + 经验学习。

每轮运行:
1. 读取最近会话中 assistant 的关键总结/决策
2. 用 LLM 提取可复用的经验模式
3. 写入 Hermes PLUR 记忆系统

用法:
  python hindsight_memory_optimizer.py        # 增量处理
  python hindsight_memory_optimizer.py --full # 全量回顾
"""

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
STATE_DB = HERMES_HOME / "state.db"
HINDSIGHT_STATE = HERMES_HOME / "memory" / "hindsight_state.json"
HINDSIGHT_STATE.parent.mkdir(parents=True, exist_ok=True)


def get_recent_sessions(limit: int = 20, since_id: int = 0):
    """读取最近会话中的 assistant 总结消息。"""
    if not STATE_DB.exists():
        print(f"⚠ 会话DB不存在: {STATE_DB}")
        return []

    conn = sqlite3.connect(str(STATE_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT m.session_id, m.id, m.content, m.timestamp, s.title
            FROM messages m
            JOIN sessions s ON m.session_id = s.id
            WHERE m.role = 'assistant'
              AND m.id > ?
              AND (m.content LIKE '%总结%' OR m.content LIKE '%完成%' OR m.content LIKE '%修复%')
            ORDER BY m.id DESC
            LIMIT ?
        """, (since_id, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def load_state():
    """加载处理进度状态。"""
    if HINDSIGHT_STATE.exists():
        return json.loads(HINDSIGHT_STATE.read_text())
    return {"last_processed_msg_id": 0, "engrams_created": 0, "updated_at": None}


def save_state(state: dict):
    """保存处理进度。"""
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    HINDSIGHT_STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def _load_deepseek_key() -> str:
    """从 .env 文件读取 DeepSeek API Key。"""
    import re
    for env_path in [
        Path(os.environ.get("HERMES_HOME", "")) / ".env",
        Path.home() / ".hermes" / ".env",
        Path(os.environ.get("HOME", "C:/Users/Administrator")) / "AppData/Local/hermes/.env"
    ]:
        if env_path.exists():
            text = env_path.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'^DEEPSEEK_API_KEY=(\S+)', text, re.MULTILINE)
            if m:
                return m.group(1)
    return os.environ.get("DEEPSEEK_API_KEY", "")


def call_llm_for_engram(content: str, title: str) -> str:
    """调用本地/远程 LLM 从会话总结中提取经验模式。"""
    prompt = f"""从以下 AI 助手的总结中，提取可复用的经验/模式/决策（一句话，中文）:

会话主题: {title}
总结内容: {content[:2000]}

输出格式: {{"engram": "一句话描述", "category": "workflow|config|debug|preference|knowledge", "priority": 1-5}}
"""
    api_key = _load_deepseek_key()
    if not api_key:
        return json.dumps({"engram": "No API key available", "category": "error", "priority": 1})
    try:
        r = subprocess.run(
            ["python", "-c", f"""
import json, urllib.request, os
os.environ["DEEPSEEK_API_KEY"] = {json.dumps(api_key)}
data = {{
    "model": "deepseek-v4-flash",
    "messages": [{{"role": "user", "content": {json.dumps(prompt)}}}],
    # ⚠️ deepseek-v4-flash 是【推理模型】: 先产 reasoning_tokens。
    #    max_tokens=200 会被推理吃干净 ⇒ content 为空串 ⇒ JSON 解析失败(2026-10-14 实测:
    #    reasoning_tokens=200, finish_reason='length', content 长度 0)。
    #    实测 max_tokens=600 稳定(190 推理 + ~50 正文)，此处留足余量。
    "max_tokens": 1200
}}
req = urllib.request.Request(
    "https://api.deepseek.com/v1/chat/completions",
    data=json.dumps(data).encode(),
    headers={{"Content-Type": "application/json",
              "Authorization": "Bearer " + os.environ["DEEPSEEK_API_KEY"]}}
)
try:
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read())
    print(result["choices"][0]["message"]["content"])
except Exception as e:
    print(json.dumps({{"engram": str(e)[:80], "category": "error", "priority": 1}}))
"""],
            capture_output=True, text=True, timeout=35
        )
        return r.stdout.strip()
    except Exception as e:
        return json.dumps({"engram": f"LLM call failed: {str(e)[:50]}", "category": "error", "priority": 1})


def create_plur_engram(engram_text: str, category: str, priority: int, source: str):
    """写入本地 Hindsight 经验库 (替代PLUR)."""
    eng_dir = HERMES_HOME / "memory" / "hindsight_engrams"
    eng_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"{ts}_{category}_p{priority}.json"
    (eng_dir / fname).write_text(
        json.dumps({
            "engram": engram_text,
            "category": category,
            "priority": priority,
            "source": source,
            "created_at": datetime.now(timezone.utc).isoformat()
        }, ensure_ascii=False, indent=2)
    )
    return True


def run_optimization(full: bool = False):
    """执行主流程。"""
    state = load_state()
    since_id = 0 if full else state["last_processed_msg_id"]
    
    sessions = get_recent_sessions(limit=50 if full else 20, since_id=since_id)
    if not sessions:
        print("✓ 无新会话需要处理")
        return True

    print(f"处理 {len(sessions)} 个会话...")
    new_max_id = state["last_processed_msg_id"]
    created = 0
    failed = 0

    for sess in sessions:
        msg_id = sess["id"]
        if msg_id > new_max_id:
            new_max_id = msg_id

        print(f"  [{sess['session_id'][:12]}] {sess.get('title','?')[:40]}...")
        
        result_str = call_llm_for_engram(sess["content"], sess.get("title", ""))
        try:
            result = json.loads(result_str)
        except json.JSONDecodeError:
            print(f"    ⚠ LLM返回解析失败: {result_str[:100] or '(空返回)'}")
            failed += 1
            continue

        engram = result.get("engram", "").strip()
        if engram and len(engram) > 5:
            ok = create_plur_engram(
                engram_text=engram,
                category=result.get("category", "knowledge"),
                priority=result.get("priority", 3),
                source=f"session:{sess['session_id']}"
            )
            if ok:
                created += 1
                print(f"    ✅ [{result.get('category','?')}] {engram[:60]}")
            else:
                print(f"    ⚠ 写入失败")
                failed += 1

    # ⚠️ 失败即不推进进度 —— 否则这批会话永久不再重试(原实现无论成败都推走)。
    if failed == 0:
        state["last_processed_msg_id"] = new_max_id
    else:
        print(f"  ⚠️ {failed} 条失败 ⇒ 【不推进】last_processed_msg_id，下轮重试")
    state["engrams_created"] += created
    save_state(state)

    print(f"✓ 完成: 新增 {created} 条经验模式, 失败 {failed} 条, 总计 {state['engrams_created']}")
    # ⚠️ 全批失败 = 真故障，必须非零退出(原实现恒 return True ⇒ cron 永远报 ok)
    if sessions and created == 0 and failed == len(sessions):
        print(f"❌ 本批 {len(sessions)} 条全部失败 —— 疑似 LLM/凭据/参数故障")
        return False
    return True


if __name__ == "__main__":
    full = "--full" in sys.argv
    sys.exit(0 if run_optimization(full) else 1)
