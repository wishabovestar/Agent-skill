import io, json, sys
sys.path.insert(0, r"C:/Users/Administrator/AppData/Local/hermes/hermes-agent")
from agent.context_compressor import ContextCompressor, estimate_tokens_rough  # noqa: E402

FACTS = [(3,"ZX-01","47.3"),(6,"ZX-02","18.9"),(9,"ZX-03","92.4"),(12,"ZX-04","5.6"),(15,"ZX-05","73.1"),
         (18,"ZX-06","31.8"),(21,"ZX-07","66.2"),(24,"ZX-08","9.4"),(27,"ZX-09","84.7"),(30,"ZX-10","22.5")]
WORDS = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau".split()


def fill(n, seed):
    out, x = [], seed
    for _ in range(n):
        x = (x * 1103515245 + 12345) % 2147483648
        out.append(WORDS[x % len(WORDS)])
    return " ".join(out)


def build():
    msgs, facts = [], {t: (f, v) for t, f, v in FACTS}
    for t in range(36):
        body = fill(320, 1000 + t)
        if t in facts:
            f, v = facts[t]
            body += " NOTE: calibration constant %s = %s mmHg, recorded on turn %d." % (f, v, t)
        msgs.append({"role": "user", "content": "[turn %d] %s" % (t, body)})
        msgs.append({"role": "assistant", "content": "Acknowledged turn %d. %s" % (t, fill(60, 2000 + t))})
    return msgs


def arm(floor, msgs):
    import os
    os.environ["HERMES_TAIL_FLOOR_TOKENS"] = str(floor)
    c = ContextCompressor(model="deepseek-flash", config_context_length=131072, provider="custom",
                          base_url="https://api.deepseek.com/v1", api_key="dummy")
    c._tail_token_budget = None
    budget = c.tail_token_budget
    cut = c._find_tail_cut_by_tokens(msgs, 0, budget)
    kept = msgs[cut:]
    text = "\n".join(m["content"] for m in kept)
    dropped = "\n".join(m["content"] for m in msgs[:cut])
    toks = sum(estimate_tokens_rough(m["content"]) for m in kept)
    hit = [f for _, f, _ in FACTS if f in text]
    return {"floor": floor, "budget": budget, "cut": cut, "kept_msgs": len(kept), "kept_tokens": toks,
            "kept": hit, "dropped_facts": [f for _, f, _ in FACTS if f not in hit],
            "dropped_chars": len(dropped), "text": text}


def main():
    msgs = build()
    a, b = arm(0, msgs), arm(24000, msgs)
    lines = ["msgs=%d facts=%d" % (len(msgs), len(FACTS))]
    for r in (a, b):
        lines.append("floor_env=%-6d budget=%-6d cut=%d/%d kept_msgs=%d kept_tokens=%d facts_in_tail=%d/10 %s"
                     % (r["floor"], r["budget"], r["cut"], len(msgs), r["kept_msgs"], r["kept_tokens"],
                        len(r["kept"]), r["kept"]))
    lines.append("dropped_chars: A=%d B=%d" % (a["dropped_chars"], b["dropped_chars"]))
    io.open("D:/hermes/analysis/_floor_ab.txt", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    for tag, r in (("A", a), ("B", b)):
        io.open("D:/hermes/analysis/_floor_ab_kept_%s.txt" % tag, "w", encoding="utf-8").write(r["text"])
    print("wrote _floor_ab.txt")


main()
