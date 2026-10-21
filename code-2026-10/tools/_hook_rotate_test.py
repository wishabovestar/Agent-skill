"""guard hook 轮转/自保的实测：小阈值下灌 60 次，检查轮转链，并计时。"""
import io
import json
import os
import shutil
import statistics
import subprocess
import sys
import time

HOOK = r"D:/hermes/hermes-data/profiles/mybot/scripts/tool_arg_guard_hook.py"
TMP = r"D:/hermes/analysis/_hook_rotate_lab"
shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP)
LEDGER = os.path.join(TMP, "ledger.jsonl")
env = dict(os.environ, TOOL_GUARD_LEDGER=LEDGER, TOOL_GUARD_LEDGER_MAX="2000", TOOL_GUARD_LEDGER_KEEP="3")
payload = json.dumps({"hook_event_name": "pre_tool_call", "tool_name": "terminal",
                      "tool_input": {"command": "ls -la " + "x" * 40}})

out = []
times = []
for i in range(60):
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, HOOK], input=payload.encode(), env=env,
                       capture_output=True, timeout=30)
    times.append(time.perf_counter() - t0)
    if p.returncode != 0:
        out.append(f"i={i} rc={p.returncode} err={p.stderr.decode()[:120]}")
out.append(f"60 次调用 rc 全 0: {not out}")
times_sorted = sorted(times)
out.append(f"单次耗时 ms: median={statistics.median(times)*1000:.1f} p90={times_sorted[int(.9*len(times))]*1000:.1f} max={max(times)*1000:.1f}")
for name in ["ledger.jsonl", "ledger.jsonl.1", "ledger.jsonl.2", "ledger.jsonl.3", "ledger.jsonl.slow"]:
    path = os.path.join(TMP, name)
    if os.path.exists(path):
        n = sum(1 for _ in io.open(path, encoding="utf-8"))
        out.append(f"  {name}: {os.path.getsize(path)} B / {n} 行")
    else:
        out.append(f"  {name}: (不存在)")
p = subprocess.run([sys.executable, HOOK, "--status"], env=env, capture_output=True, text=True, timeout=30)
out.append("--- --status 输出 ---")
out.append(p.stdout.strip())
# 慢盘自保：直接制造 slow 标记，验证后续写入被跳过
io.open(os.path.join(TMP, "ledger.jsonl.slow"), "w", encoding="utf-8").write("test\tforced\n")
before = os.path.getsize(LEDGER)
subprocess.run([sys.executable, HOOK], input=payload.encode(), env=env, capture_output=True, timeout=30)
out.append(f"冷却期内写入被跳过: {os.path.getsize(LEDGER) == before}（{before} B 不变）")
io.open(r"D:/hermes/analysis/_hook_rotate_test.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
print("wrote _hook_rotate_test.txt")
