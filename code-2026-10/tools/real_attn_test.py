#!/usr/bin/env python3
"""候选4: 真实LLM注意力集中度验证 (qwen2.5:7b via Ollama)
方法: 长文本信息检索测试 — 在长上下文中插入目标信息, 验证模型能否找到
(注意力集中时: 长上下文检索准确率保持; 分散时: 下降)
"""
import urllib.request, json, time, random

OLLAMA = 'http://localhost:11434'
MODEL = 'qwen2.5:7b'

def chat(prompt, context_len=0):
    payload = {
        'model': MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'stream': False,
        'options': {'num_ctx': max(8192, context_len), 'temperature': 0}
    }
    req = urllib.request.Request(f'{OLLAMA}/api/chat', 
        data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as resp:
        d = json.loads(resp.read().decode())
    return d.get('message', {}).get('content', '').strip()

def build_long_context(n_paragraphs=16, target=None):
    """构造长上下文: 15段无关文本 + 1段目标信息"""
    filler = [
        "量子计算利用量子比特的叠加态和纠缠态进行计算，量子比特可以同时处于0和1的状态。",
        "锂电池的正极材料包括NCM、LFP和LCO，其中NCM三元材料能量密度较高。",
        "台风是发生在热带海洋上的强烈气旋系统，中心风速达到12级以上。",
        "蛋白质是由氨基酸通过肽键连接而成的大分子，具有四级结构。",
        "文艺复兴时期达芬奇创作了蒙娜丽莎和最后的晚餐等著名作品。",
        "长江是中国最长的河流，全长约6300公里，流经11个省级行政区。",
        "机器学习中的梯度下降算法通过迭代更新参数来最小化损失函数。",
        "秦始皇统一六国后建立了中国历史上第一个中央集权的封建王朝。",
        "光合作用发生在叶绿体中，将二氧化碳和水转化为有机物和氧气。",
        "区块链是一种分布式账本技术，具有去中心化和不可篡改的特点。",
        "珠穆朗玛峰海拔8848.86米，是世界上海拔最高的山峰。",
        "DNA双螺旋结构由沃森和克里克在1953年提出。",
        "电动汽车的续航里程取决于电池容量和能量密度。",
        "唐诗宋词是中国古典文学的瑰宝，李白和杜甫是唐代最杰出的诗人。",
        "火星是太阳系中与地球环境最相似的行星之一。",
    ]
    ctx = []
    for i in range(n_paragraphs):
        if target and i == n_paragraphs - 3:  # 目标在前3段
            ctx.append(target)
        else:
            ctx.append(filler[i % len(filler)])
    return '\n'.join(ctx)

print("=" * 60)
print("候选4: 真实LLM注意力集中度验证 (qwen2.5:7b)")
print("=" * 60)

# 测试: 不同上下文长度下, 目标信息检索准确率
test_cases = [
    ("【关键信息】测试密码是：A1B2C3D4E5F6，请记住。", "密码是什么？", "A1B2C3D4E5F6"),
    ("【关键信息】秘密代码是：XYZ-987-ABC，请记住。", "秘密代码是什么？", "XYZ-987-ABC"),
    ("【关键信息】验证码是：Q7W8E9，请记住。", "验证码是什么？", "Q7W8E9"),
]

for n_paras in [4, 8, 16, 32]:
    successes = 0
    for target, question, expected in test_cases:
        ctx = build_long_context(n_paras, target)
        prompt = f"{ctx}\n\n问题：{question}\n只回答目标信息，不要其他内容。"
        try:
            answer = chat(prompt, context_len=max(8192, len(ctx)*3))
            ok = expected.lower() in answer.lower()
            if ok: successes += 1
            print(f"  上下文{n_paras*25}字: {'✅' if ok else '❌'} 回答: {answer[:50]}")
        except Exception as e:
            print(f"  上下文{n_paras*25}字: ⚠️ 错误 {str(e)[:40]}")
        time.sleep(1)
    print(f"→ {n_paras*25}字上下文: 检索成功率 {successes}/3")
    print()
