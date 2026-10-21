import sqlite3, datetime

db = "D:/hermes/hermes-data/state.db"
conn = sqlite3.connect(db)
cur = conn.cursor()

cur.execute("SELECT COUNT(*), SUM(input_tokens), SUM(output_tokens), SUM(reasoning_tokens), SUM(cache_read_tokens), SUM(cache_write_tokens), SUM(estimated_cost_usd), SUM(api_call_count) FROM sessions WHERE input_tokens > 0 OR output_tokens > 0")
r = cur.fetchone()

print(f"会话总数: {r[0]}")
print(f"Input tokens:  {r[1] or 0:,}")
print(f"Output tokens: {r[2] or 0:,}")
print(f"Reasoning:     {r[3] or 0:,}")
print(f"合计:          {(r[1] or 0) + (r[2] or 0) + (r[3] or 0):,}")
print(f"Cache read:    {r[4] or 0:,}")
print(f"Cache write:   {r[5] or 0:,}")
print(f"预估费用:      ${r[6] or 0:.6f} USD")
print(f"API 调用次数:  {r[7] or 0:,}")

# Per day
cur.execute("SELECT started_at, input_tokens, output_tokens, reasoning_tokens, estimated_cost_usd FROM sessions WHERE input_tokens > 0 ORDER BY started_at ASC")
rows = cur.fetchall()
days = {}
for ts, inp, out, reas, cost in rows:
    if ts:
        d = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        days.setdefault(d, [0,0,0,0.0])
        days[d][0] += (inp or 0)
        days[d][1] += (out or 0)
        days[d][2] += (reas or 0)
        days[d][3] += (cost or 0.0)

print("\n按日统计:")
for d in sorted(days.keys(), reverse=True)[:14]:
    inp, out, reas, cost = days[d]
    print(f"  {d}  输入:{inp:>10,}  输出:{out:>10,}  推理:{reas:>10,}  合计:{inp+out+reas:>12,}  ${cost:.6f}")

# Per model
cur.execute("SELECT model, COUNT(*), SUM(input_tokens), SUM(output_tokens), SUM(reasoning_tokens), SUM(cache_read_tokens), SUM(cache_write_tokens), SUM(estimated_cost_usd), SUM(api_call_count) FROM sessions WHERE input_tokens > 0 GROUP BY model")
print("\n按模型:")
for r in cur.fetchall():
    m, cnt, inp, out, reas, cr, cw, cost, api = r
    print(f"  {m or 'unknown'}: {cnt}会话, {api or 0}API调用")
    print(f"    输入={inp or 0:,}  输出={out or 0:,}  推理={reas or 0:,}  缓存读={cr or 0:,}  缓存写={cw or 0:,}")
    print(f"    费用=${cost or 0:.6f}")

# Per source
cur.execute("SELECT source, COUNT(*), SUM(input_tokens), SUM(output_tokens), SUM(estimated_cost_usd) FROM sessions WHERE input_tokens > 0 GROUP BY source")
print("\n按平台:")
for r in cur.fetchall():
    src, cnt, inp, out, cost = r
    print(f"  {src or 'unknown':15s}  {cnt:3d}会话  输入:{inp or 0:>10,}  输出:{out or 0:>10,}  费用:${cost or 0:.6f}")

conn.close()
