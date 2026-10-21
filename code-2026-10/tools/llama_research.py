#!/usr/bin/env python3
"""llama-server研究助手 — 用8080端口(已验证正常)做深度研究
llama-server的qwen2.5:7b工作正常(之前密码检索验证), Ollama异常
用法: python llama_research.py <topic编号>
"""
import urllib.request, json, sys

LLAMA = 'http://localhost:8080/v1/completions'
MODEL = 'qwen2.5'

def ask(prompt, max_tokens=3000):
    payload = {
        'prompt': prompt, 'model': MODEL,
        'max_tokens': max_tokens, 'temperature': 0.3,
        'stop': ['<|endoftext|>']
    }
    req = urllib.request.Request(LLAMA, data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'})
    resp = json.loads(urllib.request.urlopen(req, timeout=900).read())
    return resp['choices'][0]['text'].strip()

def research(topic, outfile):
    prompt = f"""你是AI算法研究专家。请输出结构化中文markdown文档, 包含数学形式化定义、统一框架(信息论/谱理论/优化理论)、关键推导、参考文献(arXiv ID)。

研究主题: {topic}

请直接输出完整markdown文档内容(不用解释过程)。"""
    print(f"研究: {topic[:40]}...")
    result = ask(prompt)
    if len(result) < 100:
        print(f"⚠️ 输出过短({len(result)}字符), 重试...")
        result = ask(prompt, max_tokens=4000)
    with open(outfile, 'w', encoding='utf-8') as f:
        f.write(f"# 深度研究\n\n**生成**: 2026-08-05 | **模型**: llama-server qwen2.5:7b\n\n---\n\n{result}\n")
    print(f"✅ 已写入: {outfile} ({len(result)}字符)")

if __name__ == '__main__':
    topic_id = sys.argv[1] if len(sys.argv) > 1 else 'math'
    topics = {
        'math': (
            "注意力压缩算法(LSA-HI/CLI/SI, CSA/DSA, MQA/GQA/MLA, VarRate, StreamIndex, SnapKV, CLAA)的数学本质: 各自优化什么目标函数? 约束什么? 用信息论(熵/互信息/率失真), 谱理论(奇异值), 优化理论(拉格朗日)统一解释。给出LSA注意力集中度C的数学定义与阈值0.85的意义, VarRate变秩分配最优性的奇异值依据, StreamIndex FP32 256GB→6.21GB的数学依据。",
            r'D:/hermes/data/agent_knowledge/AI-agent-toolchain/math-principles-deep-dive.md'),
        'cs': (
            "注意力机制(LSA/CSA/FlashAttention/分块)的计算机原理: (1)为什么注意力是内存密集? GPU HBM带宽vs计算比, FlashAttention分块tiling消除HBM往返, IO复杂度 (2)复杂度: 全量O(N²) vs 稀疏O(N·k) vs 分块O(N²/B), top-k选择复杂度 (3)KV cache内存布局, PagedAttention (4)为什么top-k稀疏保留大部分质量? 注意力幂律分布? 与TF-IDF/BM25类比。RTX 5070实测: HI 32K加速31x, 64K内存0.32GB。",
            r'D:/hermes/data/agent_knowledge/AI-agent-toolchain/cs-principles-deep-dive.md'),
        'bio': (
            "算法与生物学原理映射: (1)人类视觉注意力(中央凹+周边+扫视)→稀疏注意力索引 (2)海马体记忆巩固→记忆分层 (3)遗忘曲线/突触修剪→KV淘汰 (4)工作记忆7±2→上下文窗口 (5)神经元稀疏激活→稀疏注意力 (6)蚁群/蜂群→分布式检索。每个映射给可操作改进建议, 设计2-3个可落地生物启发优化方案。已知A/B: 双焦点扫视cos+5.7%, 纯遗忘-4%, 间隔重复优于纯遗忘。",
            r'D:/hermes/data/agent_knowledge/AI-agent-toolchain/bio-principles-deep-dive.md'),
    }
    t, out = topics[topic_id]
    research(t, out)
