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
CHECK_MODEL = ""  # P3 (2026-09-08): 复核用独立模型 — 首次用时从 tags 解析 (7b != 7b-clean)
CLOUD_MODEL = "deepseek-chat"  # DeepSeek API 官方模型名 (原 deepseek-v4-flash=平台名 → 400)
CLOUD_API = "https://api.deepseek.com/v1/chat/completions"

DEEPSEEK_KEY = ""
try:
    for line in open(r"D:\hermes\hermes-data\profiles\qqbot3\.env", encoding="utf-8"):
        if line.startswith("DEEPSEEK_API_KEY="):
            DEEPSEEK_KEY = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
            break
except Exception:
    pass

# ── v2 路由 (2026-09-08 — R901 四建议落地) ──
# ④ 三域配置化:
#   UNREACH (概念密度/深推理/新知) → 直云
#   STABLE (机械实现/结构化浅推理 — 本地能对域) → 本地强制
#   默认域 → 本地先跑 (①试错) + 质量信号/意图 fallback (②) + check (③)
UNREACH_PAT = re.compile(
    r"严格证明|推导出|奇异级数|模 3|局部密度|完整推理链|为什么.{10,}|最新|2026|研究|"
    r"综述|报告|长尾|罕见|冷门|数学定理|证明:|黎曼|费马|圆法|Vaughan|泛函|拓扑|"
    r"评估.{6,}|对比.{6,}和.{6,}|设计.{8,}架构", re.S)
STABLE_PAT = re.compile(
    r"^写 |修复|实现|函数|命令|配置|安装|卸载|报错|错误|bug|debug|tasklist|"
    r"简述证明|简单|列出|步骤|命令是|怎么用|怎么配|能不能|转换|格式", re.I)
# ② fallback 增强: 结构信号
STRUCT_NEED = re.compile(r"\d+\s*个|三个|要素|编号|状态机|四段", re.S)
# v2.2 (2026-09-08 R902): 浅证覆盖 — R901 稳定域实证 (偶素简述本地✅)
#   UNREACH 命中但属"简述/简单证明"且无深数学硬词 → 本地强制 (关 P1 能力闲置)
DEEP_HARD = re.compile(r"严格证明|黎曼|费马|Vaughan|圆法|泛函|拓扑|推导出|奇异级数|模 3|局部密度|完整推理链|数学定理", re.S)
SHALLOW = re.compile(r"简述证明|简单证明|简要证明|简单说明|简述一下|证明一下|简单解释|通俗解释", re.S)

# 原 CLOUD_HINTS 保留作默认域参考 (不再直接决定)
CLOUD_HINTS = re.compile(
    r"证明|推导|分析.{6,}|为什么.{8,}|解释.{10,}|代码|bug|debug|算法|数学|方程|物理定律|"
    r"光年|密度|质量|大小排序|比较.{4,}和|最新|2026|论文|研究|长尾|罕见|冷门|历史.{4,}年|"
    r"首都|人口|冠军|化学式|机理|综述|报告|总结.{20,}|评估|设计|架构|优化|论证|对比",
    re.S)
SHORT_SOCIAL = re.compile(r"^(你好|hi|hello|在吗|谢谢|再见|晚安|早安|哈哈|嗯|ok|好的|收到|早|晚|👍|好的谢谢|收到谢谢|好)\\W*$", re.I)
UNCERTAIN = re.compile(r"我不确定|不确定|不知道|无法确定|可能不是|我猜|也许.{0,6}(不是|不对)|没有把握|记不清|无法回答|抱歉，我不|难以理解|有些模糊|可能有些混淆|信息不完整", re.I)
# P2 修复 (R902 残余盲区 2026-09-08): 结构+意图信号增强
#   WHY 问句 → 答须含因果词 (缺因果=答非所问/软化跑偏检测 — R897 检索降级实证)
#   SOFT_ASK 软化句式: 澄清反问/上下文不足/开场软化 (黑名单追不完 → 结构兜底)
WHY = re.compile(r"为什么|为何|原因|理由|怎么会出现|怎么会这样", re.I)
CAUSAL = re.compile(r"因为|由于|所以|因此|原因|导致|源自|源于|取决于|为了|之所以|说明", re.I)
SOFT_ASK = re.compile(
    r"不清楚您的|不太清楚您|请提供更多|请补充|需要更多信息|信息不足|无法(判断|确认)您的|"
    r"您是指.{0,12}吗|请问您.{0,10}是|没有(足够|清晰|明确|一个清晰)的|"
    r"上下文.{0,4}(不清晰|不明确|不足|缺失)|您提到的.{0,20}(似乎|好像|可能).{0,10}(想问|想询问|询问)|"
    r"看起来.{0,15}(模糊|混淆|不清楚)|似乎是.{0,12}(想问|想询问)", re.I)


def classify(query):
    """v2.2: 三域判定 — 'local'(稳定/默认) 或 'cloud'(不可达)
    UNREACH 命中 → 浅证覆盖 (SHALLOW 无深数学硬词) → local, 否则 cloud"""
    q = query.strip()
    if not q or len(q) > 3000:
        return "cloud"
    if SHORT_SOCIAL.search(q):
        return "local"
    if UNREACH_PAT.search(q):
        if SHALLOW.search(q) and not DEEP_HARD.search(q):
            return "local"   # 浅证: 简述证明/简单证明 (R901 稳定域实证)
        return "cloud"
    return "local"   # STABLE + 默认域 → 本地先试错


def _quality_fail(prompt, reply):
    """② fallback 增强信号 — 返回失败原因(ASCII)或 None"""
    r = reply.strip()
    if r.startswith("[") and "err" in r:
        return "err"
    if len(r) < 12:
        return "short"
    if UNCERTAIN.search(r):
        return "uncertain"
    if SOFT_ASK.search(r):
        return "soft-ask"    # P2: 澄清/上下文不足/开场软化 — 本地没在答
    if STRUCT_NEED.search(prompt):
        # 要求列表/编号/骨架而输出无结构
        if not re.search(r"[1-9一二三][\.、)．)]|^\s*[-*•]|###|##|\d\)", r, re.M):
            return "no-struct"
    if WHY.search(prompt) and not CAUSAL.search(r):
        return "no-causal"   # P2: why 问句无因果论证 = 答非所问/跑偏
    return None


def _check_review(prompt, reply):
    """③ 交叉复核 P3: 独立复核模型 (7b 审 7b-clean 输出 — 真双模型)
    双重采样 — 任一 BAD 升云 (波动捕获)"""
    global CHECK_MODEL
    if not (60 <= len(reply.strip()) <= 300):
        return False
    if not CHECK_MODEL:
        try:
            tags = json.loads(urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=3).read()).get("models", [])
            names = [m.get("name", "") for m in tags]
            for cand in ("qwen2.5:7b", "qwen2.5:0.5b"):
                if cand in names and cand != LOCAL_MODEL:
                    CHECK_MODEL = cand
                    break
            if not CHECK_MODEL:
                CHECK_MODEL = LOCAL_MODEL
        except Exception:
            CHECK_MODEL = LOCAL_MODEL
    for _ in range(2):
        payload = {"model": CHECK_MODEL, "prompt": f"复核以下回答是否切题且无事实错误, 只答 OK 或 BAD:\n问:{prompt[:200]}\n答:{reply[:300]}",
                   "stream": False, "options": {"num_predict": 8, "temperature": 0.1}}
        req = urllib.request.Request(OLLAMA_URL + "/api/generate",
                                     data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        try:
            d = json.loads(urllib.request.urlopen(req, timeout=60).read())
            v = (d.get("response") or "").strip().upper()
            if "BAD" in v and "OK" not in v[:2]:
                return True
        except Exception:
            pass
    return False


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
    """v2: 三域路由 — UNREACH 直云; 其余本地先跑 →
    质量/意图信号 fail → 云兜底; 中段输出 check 复核"""
    query = messages[-1]["content"] if messages else ""
    if classify(query) == "cloud":
        reply = call_deepseek(messages)
        return reply, "cloud"
    # STABLE + 默认域 → 本地先试错 (①)
    reply = call_ollama(messages)
    if reply.startswith("[local_err"):
        reply2 = call_deepseek(messages)
        if not reply2.startswith("[cloud_err"):
            return reply2, "cloud-fallback(err)"
        return reply, "local(err)"
    reason = _quality_fail(query, reply)
    if reason:
        reply2 = call_deepseek(messages)
        if not reply2.startswith("[cloud_err"):
            return reply2, f"cloud-fallback({reason})"
        return reply, "local"
    # ③ check 复核 (中段输出 — 单次波动捕获)
    if _check_review(query, reply):
        reply2 = call_deepseek(messages)
        if not reply2.startswith("[cloud_err"):
            return reply2, "cloud-fallback(check)"
        return reply, "local"
    return reply, "local"


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
        # X-Route header 必须 latin-1 安全 (曾因中文 reason 崩溃 — 2026-09-08)
        used_safe = used.encode("ascii", "replace").decode("ascii")
        out = {"id": "mix-1", "object": "chat.completion", "model": f"local-first[{used_safe}]",
               "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}]}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Route", used_safe)
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
