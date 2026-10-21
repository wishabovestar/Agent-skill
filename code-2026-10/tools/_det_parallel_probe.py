"""回答两个推断性问题，结果单行落盘：
1) temp0.9 两个簇的首个分歧字符 offset（JSON 里没存，从 texts 重算）
2) Ollama 是否把并发请求并进同一 batch：并发 3 的耗时 / 单发耗时
   ratio≈1 → 真并行（批组成被改变）；ratio≈3 → 后端串行（mixed 模式没测到批不变性）
"""
import io
import json
import time
import urllib.request

URL = "http://127.0.0.1:11434/api/generate"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def gen(prompt, n=40, seed=42, temp=0.0):
    body = json.dumps({"model": "qwen2.5:1.5b", "prompt": prompt, "stream": False,
                       "options": {"num_predict": n, "seed": seed, "temperature": temp}}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with OPENER.open(req, timeout=180) as r:
        d = json.loads(r.read().decode())
    return time.time() - t0, d.get("response", "")


def main():
    out = []
    d = json.load(io.open("_det_ctrl_temp09.json", encoding="utf-8"))
    texts = d["modes"]["sequential"]["texts"]
    a, b = texts[0], texts[1]
    off = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), min(len(a), len(b)))
    out.append(f"temp0.9 首分歧 offset={off} (len_a={len(a)} len_b={len(b)})")

    p = "You are a deterministic test harness. Reply with exactly 30 words about why fixed seeds matter for reproducible ML experiments. No preamble."
    t1, r1 = gen(p)
    out.append(f"single wall={t1:.2f}s out_len={len(r1)}")
    t0 = time.time()
    import threading
    res = []

    def worker(i):
        res.append(gen(p + f" copy {i}")[0])
    th = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
    [t.start() for t in th]
    [t.join() for t in th]
    t3 = time.time() - t0
    out.append(f"concurrent3 wall={t3:.2f}s each={['%.2f' % x for x in res]} ratio_vs_single={t3 / t1:.2f}")
    out.append("判读: ratio<1.6 ⇒ 真并行(批组成会变，mixed 有效) ; ratio>2.2 ⇒ 串行(mixed 未真正改变批组成)")

    io.open("_det_parallel.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
    print("wrote _det_parallel.txt")


if __name__ == "__main__":
    main()
