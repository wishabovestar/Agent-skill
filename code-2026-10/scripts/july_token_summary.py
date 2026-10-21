# -*- coding: utf-8 -*-
"""7月 (2026-07-01~31) token 消耗汇总 — 按模型 (epoch时间戳)"""
import sys, io, sqlite3, collections
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB = "D:/hermes/hermes-data/profiles/qqbot3/state.db"
JUL_START = int(datetime(2026,7,1,tzinfo=timezone.utc).timestamp())
JUL_END = int(datetime(2026,8,1,tzinfo=timezone.utc).timestamp())

print("="*70)
print("2026年7月 token 消耗汇总 (按模型, epoch时间戳)")
print(f"  范围: 2026-07-01 ~ 07-31 (epoch {JUL_START} ~ {JUL_END})")

# ── 方式1: session input/output tokens (每session聚合) ──
conn = sqlite3.connect(DB)
rows = conn.execute("""
    SELECT model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
    FROM sessions 
    WHERE started_at >= ? AND started_at < ?
""", (JUL_START, JUL_END)).fetchall()
conn.close()

by_sess = collections.Counter(); inp=collections.Counter(); outp=collections.Counter()
cache_r=collections.Counter(); cache_w=collections.Counter()
for model, i, o, cr, cw in rows:
    m = model or "unknown"
    by_sess[m]+=1; inp[m]+=(i or 0); outp[m]+=(o or 0)
    cache_r[m]+=(cr or 0); cache_w[m]+=(cw or 0)

print(f"\n【session聚合】7月session数: {sum(by_sess.values())}")
print(f"{'模型':<26} {'会话':>5} | {'输入tok':>10} | {'输出tok':>10} | {'总tok':>12}")
TOT=0
for m in sorted(by_sess, key=lambda x:-(inp[x]+outp[x])):
    t=inp[m]+outp[m]; TOT+=t
    print(f"  {m:<26} {by_sess[m]:>5} | {inp[m]:>10,} | {outp[m]:>10,} | {t:>12,}")
print(f"  {'合计':<26} {sum(by_sess.values()):>5} | {sum(inp.values()):>10,} | {sum(outp.values()):>10,} | {TOT:>12,}")

# ── 方式2: message token_count (更细粒度, 若存在) ──
conn = sqlite3.connect(DB)
mrows = conn.execute("""
    SELECT s.model, m.token_count FROM messages m 
    JOIN sessions s ON m.session_id = s.id
    WHERE m.timestamp >= ? AND m.timestamp < ? AND m.token_count IS NOT NULL AND m.token_count > 0
""", (JUL_START, JUL_END)).fetchall()
conn.close()

print(f"\n【message聚合】7月有效token消息数: {len(mrows):,}")
if mrows:
    m_tok = collections.Counter(); m_cnt = collections.Counter()
    for model, tc in mrows:
        m = model or "unknown"
        m_tok[m]+=tc; m_cnt[m]+=1
    print(f"{'模型':<26} {'消息':>7} | {'tokens':>12} | {'占比':>6}")
    MT=sum(m_tok.values())
    for m in sorted(m_tok, key=lambda x:-m_tok[x]):
        print(f"  {m:<26} {m_cnt[m]:>7,} | {m_tok[m]:>12,} | {m_tok[m]/MT*100:>5.1f}%")
    print(f"  {'合计':<26} {sum(m_cnt.values()):>7,} | {MT:>12,}")
else:
    print("  (messages无 token_count, 以session聚合为准)")

# 说明
print(f"\n⚠️ 数据库记录从 7/16 开始 (7/1-15 无数据)")
print(f"   => 上述为 7/16~7/31 实测, 7/1-15 不可得或为0")
print(f"   => 完整7月 = 1-15(未知) + 16-31(上表)")
