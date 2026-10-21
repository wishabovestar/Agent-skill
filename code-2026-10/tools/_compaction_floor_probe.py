"""实测 Hermes lean 模式的 tail 预算：直接实例化 ContextCompressor 读属性，而不是手算公式。"""
import io
import sys

sys.path.insert(0, r"C:/Users/Administrator/AppData/Local/hermes/hermes-agent")

from agent.context_compressor import (  # noqa: E402
    ContextCompressor, LEAN_TAIL_FLOOR_TOKENS, LEAN_TAIL_CAP_TOKENS, TAIL_MAX_CONTEXT_FRACTION,
)

out = [f"constants: FLOOR={LEAN_TAIL_FLOOR_TOKENS} CAP={LEAN_TAIL_CAP_TOKENS} MAX_FRACTION={TAIL_MAX_CONTEXT_FRACTION}"]

for ctx in (32768, 65536, 131072, 262144, 1000000):
    c = ContextCompressor(model="deepseek-flash", config_context_length=ctx, provider="custom",
                          base_url="https://api.deepseek.com/v1", api_key="dummy")
    try:
        cl = c.context_length
    except Exception as exc:  # noqa: BLE001
        cl = f"<{type(exc).__name__}: {exc}>"
    out.append(f"ctx_in={ctx:>8} context_length={cl:>8} tail_budget={c.tail_token_budget:>6} "
               f"soft_ceiling={c._tail_soft_ceiling(c.tail_token_budget):>6} "
               f"threshold_tokens={c.threshold_tokens:>8} threshold_pct={c.threshold_percent}")

# legacy 模式对照
c = ContextCompressor(model="deepseek-flash", config_context_length=131072, provider="custom",
                      base_url="https://api.deepseek.com/v1", api_key="dummy", tail_mode="legacy")
out.append(f"legacy ctx=131072 tail_budget={c.tail_token_budget} soft_ceiling={c._tail_soft_ceiling(c.tail_token_budget)}")
io.open(r"D:/hermes/analysis/_compaction_floor_probe.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
print("wrote _compaction_floor_probe.txt")
