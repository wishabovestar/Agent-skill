#!/usr/bin/env python3
"""本地Ollama研究助手 v2 — 多主题顺序研究
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
    resp = json.loads(urllib.request.urlopen(req, timeout=900).read())
    return resp['message']['content']

def research(topic, outfile, system_prompt):
    print(f"研究: {topic[:50]}...")
    result = ask(topic, system=system_prompt)
    with open(outfile, 'w', encoding='utf-8') as f:
        f.write(f"# {outfile.split('/')[-1].replace('.md','')}\n\n**生成**: 2026-08-05 | **模型**: qwen2.5:7b\n\n---\n\n{result}\n")
    print(f"✅ 已写入: {outfile} ({len(result)}字符)")

if __name__ == '__main__':
    sys_prompt_cs = """你是计算机系统与算法专家。输出结构化中文markdown:
- 计算机体系结构原理 (内存层次/HBM带宽/算术强度)
- 算法复杂度分析表
- 工程实现对比
- 实测数据引用"""
    research(
        "注意力机制(LSA/CSA/FlashAttention/分块)背后的计算机原理: (1)为什么注意力是内存密集而非计算密集? GPU HBM带宽vs计算比, FlashAttention分块+tiling如何消除HBM往返, IO复杂度公式 (2)复杂度: 全量O(N²) vs 稀疏O(N·k) vs 分块O(N²/B), top-k选择算法复杂度 (3)KV cache内存布局, PagedAttention分页 (4)为什么top-k稀疏保留大部分质量? 注意力幂律分布? 与TF-IDF/BM25稀疏性类比。RTX 5070 12GB实测: HI稀疏32K加速31x, 64K内存0.32GB",
        r'D:/hermes/data/agent_knowledge/AI-agent-toolchain/cs-principles-deep-dive.md',
        sys_prompt_cs)
