import json
new = json.load(open("D:/hermes/analysis/new_all.json", encoding="utf-8"))
algo = json.load(open("D:/hermes/data/agent_knowledge/算法/algo_ext_2026-10-06.json", encoding="utf-8"))["repos"]
trending = json.load(open("D:/hermes/analysis/trending_parsed.json", encoding="utf-8"))

# agent-first (exclude algo) top
AGENT_FIRST = __import__("re").compile(r"agent|mcp|skill|claude|code assist|harness|gateway|memory", 2)
ALGO_RE = __import__("re").compile(r"deep.?learn|neural|transformer|llm|quantiz|fine.?tun|mixture|moe|attention|inference|diffusion|reinforcement|embedding|vector|rag|machine.?learn|training|gpt", 2)
def is_algo(x):
    algot = {"deep-learning","llm","transformer","quantization","fine-tuning","mixture-of-experts","attention","neural-network","neural-networks","reinforcement-learning","inference-engine","vector-search","rag","large-language-model","diffusion-models","machine-learning","openai","llm-agent","pytorch"}
    if set(t.lower() for t in (x["topics"] or [])) & algot: return True
    return bool(ALGO_RE.search(x["full_name"]+" "+x["desc"]))
agent_new=[x for x in new if not is_algo(x)]
agent_new.sort(key=lambda z:-z["score"])

print("### AGENT TOP12 ###")
for x in agent_new[:12]:
    print(f"{x['score']}|{x['stars']}|{x['full_name']}|{x['created']}|{x['url']}|{x['desc'][:150]}|hits={','.join(x['hits'][:6])}|topics={','.join((x['topics'] or [])[:6])}")
print("\n### ALGO TOP12 ###")
for x in algo[:12]:
    print(f"{x['score']}|{x['stars']}|{x['full_name']}|{x['created']}|{x['url']}|{x['desc'][:150]}|topics={','.join((x['topics'] or [])[:6])}")
print("\n### TRENDING TOP12 ###")
for t in sorted(trending, key=lambda z:-(z.get("stars") or 0))[:12]:
    print(f"{t['stars']}|+{t['period_gain']}|{t['repo']}|{t['period']}|{t['desc'][:110]}")
