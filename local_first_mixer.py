#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地优先 + 云兜底 混合推理代理 (2026-09-04, R789 落地)
OpenAI 兼容端点 http://127.0.0.1:8800/v1/chat/completions
流程: query → 本地可解答判定 → qwen2.5:7b-clean (Ollama)
      低置信/超限 → deepseek-v4-flash (云) 兜底
支持: 非流式 + SSE 流式转发
配置: 各 profile model.base_url=http://127.0.0.1:8800/v1
"""
# side_effects: [无写入]
import json
import re
import urllib.request
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OLLAMA_URL = "http://127.0.0.1:11434"
LOCAL_MODEL = "qwen2.5:7b-clean"
CLOUD_MODEL = "deepseek-v4-flash"
CLOUD_API = "https://api.deepseek.com/v1/chat/completions"

DEEPSEEK_KEY = ""
try:
    for line in open(r"D:\hermes\hermes-data\profiles\qqbot3\.env", encoding="utf-8"):
        if line.startswith("DEEPSEEK_API_KEY="):
            DEEPSEEK_KEY = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
            break
except Exception:
    pass

# ── 本地可解答判定 (规则快判 — 零额外 LLM 成本) ──
CLOUD_HINTS = re.compile(
    r"证明|推导|分析.{6,}|为什么.{8,}|解释.{10,}|代码|bug|debug|算法|数学|方程|物理定律|"
    r"光年|密度|质量|大小排序|比较.{4,}和|最新|2026|论文|研究|长尾|罕见|冷门|历史.{4,}年|"
    r"首都|人口|冠军|化学式|机理|综述|报告|总结.{20,}|评估|设计|架构|优化|论证|对比",
    re.S)
SHORT_SOCIAL = re.compile(r"^(你好|hi|hello|在吗|谢谢|再见|晚安|早安|哈哈|嗯|ok|好的|收到|早|晚|👍|好的谢谢|收到谢谢|好)\W*$", re.I)
UNCERTAIN = re.compile(r"我不确定|不确定|不知道|无法确定|可能不是|我猜|也许.{0,6}(不是|不对)|没有把握|记不清", re.I)


def classify(query):
    """返回 'local' 或 'cloud'"""
    q = query.strip()
    if not q or len(q) > 3000:
        return "cloud"
    if SHORT_SOCIAL.search(q):
        return "local"
    if CLOUD_HINTS.search(q):
        return "cloud"
    return "local"


def call_ollama(messages, stream=False):
    payload = {"model": LOCAL_MODEL, "messages": messages, "stream": stream}
    req = urllib.request.Request(OLLAMA_URL + "/v1/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        if stream:
            return urllib.request.urlopen(req, timeout=300)
        d = json.loads(urllib.request.urlopen(req, timeout=300).read())
        return d["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[local_err: {e}]"


def call_deepseek(messages, stream=False):
    if not DEEPSEEK_KEY:
        return "[cloud_err: 无 key]"
    payload = {"model": CLOUD_MODEL, "messages": messages, "stream": stream, "max_tokens": 4000}
    req = urllib.request.Request(CLOUD_API, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {DEEPSEEK_KEY}"})
    for attempt in range(2):
        try:
            if stream:
                return urllib.request.urlopen(req, timeout=300)
            d = json.loads(urllib.request.urlopen(req, timeout=300).read())
            content = d["choices"][0]["message"]["content"].strip()
            if content:
                return content
        except Exception as e:
            if attempt == 1:
                return f"[cloud_err: {e}]"
        # 空响应/异常 → 重试一次
        import time
        time.sleep(2)
    return "[cloud_err: 空响应]"


def needs_cloud_fallback(reply):
    """本地回复质量检测: 不确定词/空/极短 → 云兜底"""
    r = reply.strip()
    if r.startswith("[") and "err" in r:
        return True
    if len(r) < 12:
        return True
    if UNCERTAIN.search(r):
        return True
    return False


def route(messages):
    query = messages[-1]["content"] if messages else ""
    route_name = classify(query)
    if route_name == "local":
        reply = call_ollama(messages)
        if needs_cloud_fallback(reply):
            reply2 = call_deepseek(messages)
            if not reply2.startswith("[cloud_err"):
                return reply2, "cloud-fallback"
            return reply, "local"
        return reply, "local"
    reply = call_deepseek(messages)
    return reply, "cloud"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send_sse(self, chunks):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for c in chunks:
            self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        except Exception:
            body = {}
        messages = body.get("messages", [])
        stream = body.get("stream", False)
        # 判定并调用
        query = messages[-1]["content"] if messages else ""
        rname = classify(query)
        if stream:
            # 流式: 本地/云都转 SSE — 简化: 非流式取整再单块 SSE (功能等价)
            reply, used = route(messages)
            choice = {"index": 0, "message": {"role": "assistant", "content": reply},
                      "finish_reason": "stop"}
            self._send_sse([{"id": "x", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"role": "assistant", "content": reply}, "finish_reason": None}]},
                            {"id": "x", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}])
            return
        reply, used = route(messages)
        out = {"id": "mix-1", "object": "chat.completion", "model": f"local-first[{used}]",
               "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}]}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Route", used)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/health"):
            data = json.dumps({"status": "ok", "mode": "local-first", "local": LOCAL_MODEL, "cloud": CLOUD_MODEL}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    print(f"混合推理代理启动: 本地={LOCAL_MODEL} (Ollama) + 云={CLOUD_MODEL} (deepseek) @ :8800")
    srv = ThreadingHTTPServer(("127.0.0.1", 8800), Handler)
    srv.serve_forever()
