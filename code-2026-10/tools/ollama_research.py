#!/usr/bin/env python3
"""本地Ollama研究助手 — 直接调用Ollama API做深度研究
绕开delegation模型路由问题(400错误)
用法: python ollama_research.py "研究问题" 输出文件
"""
import urllib.request, json, sys, time

OLLAMA = 'http://localhost:11434/api/chat'
MODEL = 'qwen2.5:7b'

def ask(prompt, max_tokens=4000, system=None):
    payload = {
        'model': MODEL,
        'messages': [],
        'stream': False,
        'options': {'num_predict': max_tokens, 'temperature': 0.3}
    }
    if system:
        payload['messages'].append({'role': 'system', 'content': system})
    payload['messages'].append({'role': 'user', 'content': prompt})
    req = urllib.request.Request(OLLAMA, data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'})
    resp = json.loads(urllib.request.urlopen(req, timeout=600).read())
    return resp['message']['content']

def research(topic, outfile):
    system = """你是AI算法研究专家。输出结构化中文markdown: 
- 数学形式化定义
- 统一框架(信息论/谱理论/优化理论)
- 关键推导
- 参考文献(arXiv ID)"""
    print(f"研究: {topic}")
    result = ask(f"深度研究: {topic}\n\n要求输出结构化markdown文档。", system=system)
    with open(outfile, 'w', encoding='utf-8') as f:
        f.write(f"# {topic}\n\n**生成**: 2026-08-05 | **模型**: qwen2.5:7b\n\n---\n\n{result}\n")
    print(f"✅ 已写入: {outfile} ({len(result)}字符)")

if __name__ == '__main__':
    # 数学原理
    research(
        "注意力压缩算法(LSA-HI/CLI/SI, CSA/DSA, MQA/GQA/MLA, VarRate, StreamIndex, SnapKV, CLAA)的数学本质: 各自优化什么目标函数? 约束什么? 能否用信息论(熵/互信息/率失真), 谱理论(奇异值), 优化理论(拉格朗日)统一解释? 给出LSA注意力集中度C的数学定义与阈值意义, VarRate变秩分配最优性的奇异值依据, StreamIndex FP32 256GB→6.21GB的数学依据",
        r'D:/hermes/data/agent_knowledge/AI-agent-toolchain/math-principles-deep-dive.md')
