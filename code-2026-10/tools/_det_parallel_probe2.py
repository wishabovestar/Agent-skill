"""并发/批处理判读（预热后测量，避免把模型加载时间算进单发耗时）。

结论口径：
  ratio = 并发3耗时 / 单发耗时(中位数)
  ratio < 1.6 ⇒ 三请求真并行（批组成确实被改变）
  ratio > 2.2 ⇒ 后端串行（并发只是排队，mixed 模式并未改变批组成）
"""
import io
import json
import threading
import time
import urllib.request

URL = "http://127.0.0.1:11434/api/generate"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
P = ("You are a deterministic test harness. Reply with exactly 30 words about why fixed "
     "seeds matter for reproducible ML experiments. No preamble.")


def gen(prompt):
    body = json.dumps({"model": "qwen2.5:1.5b", "prompt": prompt, "stream": False,
                       "options": {"num_predict": 40, "seed": 42, "temperature": 0.0}}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with OPENER.open(req, timeout=180) as r:
        d = json.loads(r.read().decode())
    return time.time() - t0, d.get("load_duration", 0) / 1e9, d.get("eval_count", 0)


def main():
    out = []
    gen(P)  # 预热：把模型装进显存
    out.append("warmup done")
    singles = []
    for i in range(3):
        dt, ld, ec = gen(P + f" w{i}")
        singles.append(dt)
        out.append(f"single{i} wall={dt:.2f}s load={ld:.2f}s eval_count={ec}")
    med = sorted(singles)[1]
    out.append(f"single_median={med:.2f}s")

    for trial in range(2):
        t0 = time.time()
        th = [threading.Thread(target=lambda i=i: gen(P + f" c{i}")) for i in range(3)]
        [t.start() for t in th]
        [t.join() for t in th]
        t3 = time.time() - t0
        out.append(f"concurrent3 trial{trial} wall={t3:.2f}s ratio={t3 / med:.2f}")

    last = float(out[-1].split("ratio=")[1])
    out.append("判读: " + ("真并行 ⇒ mixed 模式确实改变了批组成" if last < 1.6
                           else ("串行 ⇒ mixed 模式未真正改变批组成，批不变性未被检验" if last > 2.2
                                 else "介于其间，需再测")))
    io.open("_det_parallel2.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
    print("wrote _det_parallel2.txt")


if __name__ == "__main__":
    main()
