import io, json, sys
site_dir = r"C:/Users/Administrator/AppData/Local/hermes/hermes-agent/venv/Lib/site-packages"
import site as _site
_site.addsitedir(site_dir)
sys.path.insert(0, r"C:/Users/Administrator/AppData/Local/hermes/hermes-agent")
from agent.context_compressor import ContextCompressor, estimate_tokens_rough  # noqa: E402

FACTS = [(6,"ZX-01","47.3"),(12,"ZX-02","18.9"),(18,"ZX-03","92.4"),(24,"ZX-04","5.6"),(30,"ZX-05","73.1"),
         (36,"ZX-06","31.8"),(42,"ZX-07","66.2"),(48,"ZX-08","9.4"),(51,"ZX-09","84.7"),(54,"ZX-10","22.5")]
WORDS = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau".split()


def fill(n, seed):
    out, x = [], seed
    for _ in range(n):
        x = (x * 1103515245 + 12345) % 2147483648
        out.append(WORDS[x % len(WORDS)])
    return " ".join(out)


def build():
    msgs, facts = [], {t: (f, v) for t, f, v in FACTS}
    for t in range(60):
        body = fill(900, 1000 + t)
        if t in facts:
            f, v = facts[t]
            body += " NOTE: calibration constant %s = %s mmHg, recorded on turn %d." % (f, v, t)
        msgs.append({"role": "user", "content": "[turn %d] %s" % (t, body)})
        msgs.append({"role": "assistant", "content": "Acknowledged turn %d. %s" % (t, fill(60, 2000 + t))})
    return msgs


msgs = build()
tag = sys.argv[1]
c = ContextCompressor(model="deepseek-flash", config_context_length=131072, provider="custom",
                      base_url="https://api.deepseek.com/v1", api_key="dummy")
budget = c.tail_token_budget
cut = c._find_tail_cut_by_tokens(msgs, 0, budget)
kept = msgs[cut:]
text = "\n".join(m["content"] for m in kept)
toks = sum(estimate_tokens_rough(m["content"]) for m in kept)
hit = [f for _, f, _ in FACTS if f in text]
res = {"tag": tag, "budget": budget, "cut": cut, "kept_msgs": len(kept), "kept_tokens": toks,
       "facts_in_tail": hit, "dropped_facts": [f for _, f, _ in FACTS if f not in hit]}
io.open("D:/hermes/analysis/_floor_arm_%s.json" % tag, "w", encoding="utf-8").write(json.dumps(res, ensure_ascii=False))
io.open("D:/hermes/analysis/_floor_ab_kept_%s.txt" % tag, "w", encoding="utf-8").write(text)
print("ARM", tag, res["budget"], len(hit))
