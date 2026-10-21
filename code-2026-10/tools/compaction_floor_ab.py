"""compaction 尾部下界两档对照（走生产代码路径，不重写选择逻辑）。

臂 A：默认 lean（tail = 10,000）
臂 B：HERMES_TAIL_FLOOR_TOKENS=24000（窗口 16k + 回溯 8k 的示意几何下界）

测三件事：
  1) 尾部实际 token / 覆盖多少条消息
  2) 10 条埋入事实中，有几条落在 verbatim 尾部（其余只能靠摘要）
  3) 裸尾部的模型召回（不接摘要，仅作覆盖上限的上界参考）
"""
from __future__ import annotations

import io
import json
import os
import random
import sys

HERMES = r"C:/Users/Administrator/AppData/Local/hermes/hermes-agent"
sys.path.insert(0, HERMES)
try:
    import ruamel.yaml  # noqa: F401  上游链要它；Hermes 自带的 3.14 没装，直接跳过那一遍
except ModuleNotFoundError as _e:
    print("FAIL: ruamel.yaml 不可用（该解释器不是 hermes venv）:", _e, file=sys.stderr, flush=True)
    raise SystemExit(3)

from agent.context_compressor import ContextCompressor, estimate_tokens_rough  # noqa: E402

CTX = 131072
TURNS = 36
FACTS = [(3, "ZX-01", "47.3"), (6, "ZX-02", "18.9"), (9, "ZX-03", "92.4"), (12, "ZX-04", "5.6"),
         (15, "ZX-05", "73.1"), (18, "ZX-06", "31.8"), (21, "ZX-07", "66.2"), (24, "ZX-08", "9.4"),
         (27, "ZX-09", "84.7"), (30, "ZX-10", "22.5")]
FILLER_WORDS = ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi "
                "rho sigma tau upsilon phi chi psi omega process buffer segment metric sample window "
                "pipeline review staging release monitor trace").split()


def filler(n_words: int, seed: int) -> str:
    rnd = random.Random(seed)
    return " ".join(rnd.choice(FILLER_WORDS) for _ in range(n_words))


def build() -> tuple[list[dict], dict[int, tuple[str, str]]]:
    rnd = random.Random(7)
    by_turn = {t: (fid, val) for t, fid, val in FACTS}
    msgs: list[dict] = []
    for t in range(TURNS):
        body = filler(320, 1000 + t)
        if t in by_turn:
            fid, val = by_turn[t]
            body += f" NOTE: calibration constant {fid} = {val} mmHg, recorded on turn {t}."
        msgs.append({"role": "user", "content": f"[turn {t}] {body}"})
        msgs.append({"role": "assistant", "content": f"Acknowledged turn {t}. " + filler(60, 2000 + t)
                     + f" Running tally id {rnd.randint(10000, 99999)}."})
    return msgs, by_turn


def arm(floor: int) -> dict:
    os.environ["HERMES_TAIL_FLOOR_TOKENS"] = str(floor) if floor else "0"
    c = ContextCompressor(model="deepseek-flash", config_context_length=CTX, provider="custom",
                          base_url="https://api.deepseek.com/v1", api_key="dummy")
    c._tail_token_budget = None  # 清缓存，按新 env 重算
    budget = c.tail_token_budget
    msgs, by_turn = build()
    cut = c._find_tail_cut_by_tokens(msgs, 0, budget)
    kept = msgs[cut:]
    kept_text = "\n".join(m["content"] for m in kept)
    dropped_text = "\n".join(m["content"] for m in msgs[:cut])
    kept_tokens = sum(estimate_tokens_rough(m["content"]) for m in kept)
    facts_in_tail = [fid for t, fid, _ in FACTS if fid in kept_text]
    return {"floor_env": floor, "budget": budget, "cut_idx": cut, "kept_msgs": len(kept),
            "kept_tokens": kept_tokens, "total_msgs": len(msgs),
            "facts_in_tail": facts_in_tail, "facts_dropped": [f for _, f, _ in FACTS if f not in facts_in_tail],
            "kept_text": kept_text, "dropped_chars": len(dropped_text)}


def main() -> int:
    a = arm(0)
    b = arm(24000)
    lines = [f"ctx={CTX} turns={TURNS} facts={len(FACTS)}"]
    for r in (a, b):
        lines.append(f"臂 floor_env={r['floor_env']:>6} → tail_budget={r['budget']:>6} "
                     f"cut_idx={r['cut_idx']}/{r['total_msgs']} kept_msgs={r['kept_msgs']} "
                     f"kept_tokens={r['kept_tokens']} "
                     f"事实在尾部={len(r['facts_in_tail'])}/10 {r['facts_in_tail']}")
    lines.append(f"被丢进摘要区的字符数：A={a['dropped_chars']} B={b['dropped_chars']}")
    io.open(r"D:/hermes/analysis/_floor_ab.json", "w", encoding="utf-8").write(
        json.dumps({"A": {k: v for k, v in a.items() if k != "kept_text"},
                    "B": {k: v for k, v in b.items() if k != "kept_text"}}, ensure_ascii=False, indent=1))
    io.open(r"D:/hermes/analysis/_floor_ab.txt", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    # 供模型召回实验使用
    for tag, r in (("A", a), ("B", b)):
        io.open(rf"D:/hermes/analysis/_floor_ab_kept_{tag}.txt", "w", encoding="utf-8").write(r["kept_text"])
    print("wrote _floor_ab.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
