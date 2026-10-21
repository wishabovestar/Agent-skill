"""Hermes compaction 尾部预算检查器：读当前 profile 配置 → 实算 tail 预算 → 给判据。

判据（可失败）：effective_tail_tokens < MIN_SAFE_TAIL(4096) ⇒ exit 3。
用途：换小窗口本地模型（Ollama）时先跑一次，避免 compaction 把可用的 verbatim 尾部压得过小。
"""
from __future__ import annotations

import argparse
import io
import os
import sys

sys.path.insert(0, os.path.join(os.environ.get("HERMES_ROOT", r"C:/Users/Administrator/AppData/Local/hermes"),
                                "hermes-agent"))

import yaml  # noqa: E402

from agent.context_compressor import ContextCompressor  # noqa: E402

MIN_SAFE_TAIL = 4096


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(
        os.environ.get("HERMES_HOME", r"D:/hermes/hermes-data/profiles/mybot"), "config.yaml"))
    ap.add_argument("--ctx", type=int, default=0, help="覆盖 context_length（默认取配置）")
    a = ap.parse_args()

    cfg = yaml.safe_load(io.open(a.config, encoding="utf-8"))
    model = (cfg.get("model") or {}).get("default", "?")
    provider = (cfg.get("model") or {}).get("provider", "")
    base_url = (cfg.get("model") or {}).get("base_url", "")
    ctx = a.ctx or int((cfg.get("model") or {}).get("ollama_num_ctx") or 0)
    comp = cfg.get("compression") or {}
    tail_mode = comp.get("tail_mode") or "lean"

    if not ctx:
        print("FAIL: 配置里没有 ollama_num_ctx，且未给 --ctx ⇒ 无法判定")
        return 3

    c = ContextCompressor(model=model, config_context_length=ctx, provider=provider, base_url=base_url,
                          api_key="dummy", threshold_percent=float(comp.get("threshold", 0.5)),
                          protect_last_n=int(comp.get("protect_last_n", 20)),
                          protect_first_n=int(comp.get("protect_first_n", 3)),
                          summary_target_ratio=float(comp.get("target_ratio", 0.15)),
                          tail_mode=tail_mode)
    tail = c.tail_token_budget
    soft = c._tail_soft_ceiling(tail)
    lines = [
        f"profile_config={a.config}",
        f"model={model} provider={provider} tail_mode={tail_mode} ctx={ctx}",
        f"threshold_tokens={c.threshold_tokens} ({c.threshold_percent:.0%} of window)",
        f"tail_token_budget={tail}  soft_ceiling={soft}  (= {soft / ctx:.1%} of window)",
        f"protect_last_n={c.protect_last_n}（实际计消息下限 = max(3, min(protect_last_n, 8)) = "
        f"{max(3, min(c.protect_last_n, 8))}）",
    ]
    if tail < MIN_SAFE_TAIL:
        lines.append(f"VERDICT: FAIL —— 尾部预算 {tail} < {MIN_SAFE_TAIL}，verbatim 尾部过小")
        rc = 3
    else:
        lines.append(f"VERDICT: OK —— 尾部预算 {tail} ≥ {MIN_SAFE_TAIL}；"
                     f"按 3.5 字/token 折合约 {int(tail * 3.5):,} 字符 verbatim")
        rc = 0
    io.open(r"D:/hermes/analysis/_compaction_floor_check.txt", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("wrote _compaction_floor_check.txt")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
