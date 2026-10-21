import http.client, json, random, re, io, sys, os

MODEL = os.environ.get("FID_MODEL", "qwen2.5:7b")
OUT = "D:/hermes/analysis/_fidelity_ab.txt"
random.seed(7)

FACTS = [("ZX-%02d" % i, "%0.1f" % (5 + i * 7.3)) for i in range(1, 13)]
FILL = ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau "
        "upsilon phi chi psi omega process buffer segment window channel offset gain drift").split()


def filler(n):
    return " ".join(random.choice(FILL) for _ in range(n))


def build_turns(n_turns=40):
    turns = []
    slots = [3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36]
    for t in range(n_turns):
        body = filler(55)
        if t in slots:
            f, v = FACTS[slots.index(t)]
            body += " 记录：校准常数 %s 的读数为 %s mmHg。" % (f, v)
        turns.append("[第%d轮] %s" % (t + 1, body))
    return turns


SYS_SUM_NAIVE = "你是会议记录员。把用户提供的多轮对话压缩成不超过 400 字的中文要点摘要，供后续问答使用。"
SYS_SUM_STRICT = ("你是会议记录员。把用户提供的多轮对话压缩成不超过 600 字的中文要点摘要，供后续问答使用。"
                  "要求：凡出现形如 ZX-nn 的编号及其数值，必须逐条原样保留，不得合并、省略或改写数字。")

SYS_QA = ("你只能依据给出的摘要回答问题，禁止使用摘要以外的知识。"
          "如果摘要中没有相关信息，只输出 UNKNOWN；如果有，只输出对应的数值（例如 47.3），不要输出别的字。")


def call(prompt, system, num_ctx=8192, temperature=0.0):
    body = json.dumps({
        "model": MODEL, "stream": False, "prompt": prompt, "system": system,
        "options": {"temperature": temperature, "num_ctx": num_ctx, "num_predict": 700},
    }).encode("utf-8")
    c = http.client.HTTPConnection("127.0.0.1", 11434, timeout=300)
    c.request("POST", "/api/generate", body, {"Content-Type": "application/json"})
    r = c.getresponse()
    data = json.loads(r.read().decode("utf-8"))
    c.close()
    return data.get("response", "")


def run_arm(tag, sys_sum):
    turns = build_turns()
    convo = "\n".join(turns)
    src_tokens = len(convo) / 1.8
    summary = call("对话如下：\n" + convo, sys_sum)
    kept = re.findall(r"ZX-\d\d", summary)
    hits, unknown, wrong, missing = [], [], [], []
    for f, v in FACTS:
        ans = call("摘要：\n" + summary + "\n\n问题：%s 的读数是多少？" % f, SYS_QA)
        a = ans.strip().split()[0] if ans.strip() else ""
        a = re.sub(r"[^0-9.UNKNOWN]", "", a)
        if a.startswith("UNKNOWN"):
            unknown.append(f)
        elif a and abs(float(a) - float(v)) < 0.05:
            hits.append(f)
        elif a:
            wrong.append((f, a, v))
        else:
            missing.append(f)
    return {"tag": tag, "convo_chars": len(convo), "src_tokens_est": int(src_tokens),
            "summary_chars": len(summary), "ratio": round(len(convo) / max(1, len(summary)), 2),
            "ids_in_summary": len(set(kept)), "hits": hits, "unknown": unknown, "wrong": wrong,
            "empty": missing, "summary": summary}


res = []
for tag, sysp in (("S1-naive", SYS_SUM_NAIVE), ("S2-fact-strict", SYS_SUM_STRICT)):
    r = run_arm(tag, sysp)
    res.append(r)
    lines = ["[%s] convo=%d chars (~%d tok) summary=%d chars ratio=%.2fx ids_in_summary=%d/12"
             % (r["tag"], r["convo_chars"], r["src_tokens_est"], r["summary_chars"], r["ratio"], r["ids_in_summary"]),
             "  hit=%d %s" % (len(r["hits"]), r["hits"]),
             "  unknown=%d %s" % (len(r["unknown"]), r["unknown"]),
             "  wrong=%d %s" % (len(r["wrong"]), r["wrong"]),
             "  empty=%d %s" % (len(r["empty"]), r["empty"]),
             "----- summary -----", r["summary"], ""]
    io.open(OUT, "a", encoding="utf-8").write("\n".join(lines) + "\n")
    print("[%s] hit=%d unknown=%d wrong=%d ratio=%.2f" % (r["tag"], len(r["hits"]), len(r["unknown"]), len(r["wrong"]), r["ratio"]), flush=True)

print("wrote", OUT)
