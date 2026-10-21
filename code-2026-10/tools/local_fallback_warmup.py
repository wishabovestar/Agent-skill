"""local_fallback_warmup.py — 本地兜底链的「冷加载首调用丢弃」固化模块。

背景（2026-10-20 实测定性）：Ollama 在模型刚被载入后的**第一次** generate 会走另一条采样分支，
表现为输出在 token 92 处提前 stop（eval_count=44 vs 常态 60），且只在 i=0 出现；预热后 10/10 完全一致。
因此任何把本地模型当作 Hermes 兜底链 / 批量评分器的脚本，都应先丢弃一次冷调用。

用法：
    from local_fallback_warmup import WarmClient
    c = WarmClient("qwen2.5:7b-ctx64k")   # 构造即预热（默认丢 1 次冷调用）
    txt = c.generate("用一句话解释什么叫热阻")

CLI：
    python local_fallback_warmup.py --model qwen2.5:7b-ctx64k            # 预热 + 3 次一致性校验
    python local_fallback_warmup.py --model qwen2.5:7b-ctx64k --runs 5
    python local_fallback_warmup.py --model qwen2.5:7b-ctx64k --no-warmup   # 对照：不丢弃冷调用

退出码：0 = 预热后各次输出完全一致；3 = 预热后仍不一致（判据可失败，不静默放行）。
"""

import argparse
import hashlib
import http.client
import json
import sys
import time

HOST, PORT = "127.0.0.1", 11434
PROBE = "写一段 60 词左右的英文，说明为什么可复现性在机器学习实验中很重要。"


def _post(payload, timeout=300):
    """直连 127.0.0.1，绕开 HTTP(S)_PROXY / socks5h 环境变量。"""
    body = json.dumps(payload).encode("utf-8")
    conn = http.client.HTTPConnection(HOST, PORT, timeout=timeout)
    conn.request("POST", "/api/generate", body, {"Content-Type": "application/json"})
    raw = conn.getresponse().read()
    conn.close()
    return json.loads(raw.decode("utf-8"))


def unload(model):
    """把模型从显存卸下，制造真正的冷加载（keep_alive=0 在本次请求后立即卸载）。"""
    return _post({"model": model, "prompt": "x", "stream": False, "keep_alive": 0,
                  "options": {"num_predict": 1}})



class WarmClient:
    """带冷启动丢弃 / 同 prompt 前缀预填的本地模型客户端。"""

    def __init__(self, model, num_ctx=8192, discard=1, temperature=0.7, verbose=False):
        self.model = model
        self.num_ctx = num_ctx
        self.temperature = temperature
        self.verbose = verbose
        self.warmup_ms = []
        self._primed = set()
        self.prefill_calls = 0
        for _ in range(max(0, discard)):
            t0 = time.time()
            _post({"model": model, "prompt": "warmup", "stream": False,
                   "options": {"num_predict": 1, "num_ctx": num_ctx, "temperature": 0}})
            self.warmup_ms.append(round((time.time() - t0) * 1000))

    def generate(self, prompt, num_predict=256, num_ctx=None, system=""):
        payload = {"model": self.model, "prompt": prompt, "stream": False,
                   "options": {"num_predict": num_predict,
                               "num_ctx": num_ctx or self.num_ctx,
                               "temperature": self.temperature}}
        if system:
            payload["system"] = system
        d = _post(payload)
        if self.verbose:
            sys.stderr.write("[gen] eval_count=%s done_reason=%s load_ms=%s total_ms=%s\n"
                             % (d.get("eval_count"), d.get("done_reason"),
                                d.get("load_duration", 0) // 1000000, d.get("total_duration", 0) // 1000000))
        return d.get("response", ""), d

    def generate_stable(self, prompt, num_predict=256, num_ctx=None):
        """同 prompt 先丢一次再取第二次。

        实测（2026-10-20）：仅用「别的 prompt」预热**不足以**消除首调用差异 —— 卸载重载后
        第一次对 PROBE 的调用仍稳定复现 eval_count=34/fp=be8a…，与预热与否无关；
        原因落在 prompt/KV 前缀缓存，而非单纯的权重冷加载。用**同一 prompt** 丢一次即可收敛。
        """
        self.generate(prompt, num_predict=num_predict, num_ctx=num_ctx)
        return self.generate(prompt, num_predict=num_predict, num_ctx=num_ctx)

    def prefill(self, prompt, num_ctx=None, system=""):
        """用**同一个 prompt** 跑 1 token，只为把该前缀灌进 KV 缓存；返回值丢弃。"""
        txt, d = self.generate(prompt, num_predict=1, num_ctx=num_ctx, system=system)
        self.prefill_calls += 1
        return d

    def generate_prefilled(self, prompt, num_predict=256, num_ctx=None, system=""):
        """生产用法：同一 prompt 的第一次调用前先 prefill（+1 次 1-token 调用），
        之后同 prompt 直接走缓存。相比 generate_stable，只在**首次**付出双份 prompt 计算，
        后续调用零额外开销 —— 这才是可以写进兜底链批量脚本的形状。"""
        h = hashlib.sha256((system + "\x00" + prompt).encode("utf-8")).hexdigest()[:16]
        if h not in self._primed:
            self.prefill(prompt, num_ctx, system)
            self._primed.add(h)
        return self.generate(prompt, num_predict=num_predict, num_ctx=num_ctx, system=system)



def fingerprint(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5:7b-ctx64k")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--no-warmup", action="store_true")
    ap.add_argument("--cold", action="store_true", help="先卸载模型，制造真正的冷加载")
    ap.add_argument("--temperature", type=float, default=0.0,
                    help="一致性判据只在 temp=0 下有意义；默认 0")
    ap.add_argument("--stable", action="store_true",
                    help="每次取样前先用同一 prompt 丢一次（推荐；实测这是唯一有效的收敛方式）")
    ap.add_argument("--prefill", action="store_true",
                    help="首调用前用同一 prompt 跑 1 token 灌 KV 前缀（生产用法，后续调用零额外开销）")
    args = ap.parse_args()

    if args.cold:
        unload(args.model)
        print("cold: model unloaded", flush=True)

    client = WarmClient(args.model, discard=0 if args.no_warmup else 1,
                        temperature=args.temperature, verbose=True)

    if client.warmup_ms:
        print("warmup(discarded) ms=%s" % client.warmup_ms, flush=True)

    fps, counts, reasons = [], [], []
    for i in range(args.runs):
        if args.stable:
            txt, d = client.generate_stable(PROBE, num_predict=200)
        elif args.prefill:
            txt, d = client.generate_prefilled(PROBE, num_predict=200)
        else:
            txt, d = client.generate(PROBE, num_predict=200)
        fp = fingerprint(txt)
        fps.append(fp)
        counts.append(d.get("eval_count"))
        reasons.append(d.get("done_reason"))
        print("run%d fp=%s eval_count=%s done_reason=%s chars=%d load_ms=%d"
              % (i, fp, d.get("eval_count"), d.get("done_reason"), len(txt),
                 d.get("load_duration", 0) // 1000000), flush=True)

    uniq = sorted(set(fps))
    print("distinct=%d/ %d  fps=%s" % (len(uniq), args.runs, fps), flush=True)
    if len(uniq) == 1:
        print("PASS 预热后输出逐字节一致")
        return 0
    print("FAIL 预热后仍出现 %d 个簇 → 该模型/参数下丢弃 1 次不足" % len(uniq))
    return 3


if __name__ == "__main__":
    sys.exit(main())
