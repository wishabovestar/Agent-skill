#!/usr/bin/env python3
"""本地Ollama研究助手 v3 — 生物原理研究
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
    sys_prompt_bio = """你是生物启发算法专家(计算神经科学+认知科学+算法设计)。输出结构化中文markdown:
- 生物机制→算法映射表
- 每个映射的可操作改进建议
- 可落地生物启发优化方案(可与现有算法正交组合)
- 参考文献"""
    research(
        "算法与生物学/自然界原理的系统映射: (1)人类视觉注意力(中央凹+周边+扫视) → 稀疏注意力索引 (2)海马体记忆巩固 → 记忆分层 (3)遗忘曲线/突触修剪 → KV淘汰 (4)工作记忆7±2 → 上下文窗口 (5)神经元稀疏激活1-5% → 稀疏注意力 (6)蚁群/蜂群 → 分布式检索。每个映射给出可操作算法改进建议, 设计2-3个可落地的生物启发优化方案(如视觉扫视机制的双焦点索引、基于遗忘曲线的衰减、基于稀疏激活的动态k选择)。已知A/B结果: 双焦点扫视提升cos +5.7%, 纯遗忘曲线损害精度-4%, 间隔重复优于纯遗忘",
        r'D:/hermes/data/agent_knowledge/AI-agent-toolchain/bio-principles-deep-dive.md',
        sys_prompt_bio)
