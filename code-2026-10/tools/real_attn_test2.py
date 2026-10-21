#!/usr/bin/env python3
"""候选4: 真实LLM注意力集中度验证 (llama-server + qwen2.5:7b Q4)
长上下文关键信息检索测试: 注意力集中 → 准确找到目标
"""
import urllib.request, json, time

def complete(prompt, max_tokens=60):
    payload = {
        'prompt': prompt,
        'model': 'qwen2.5',
        'max_tokens': max_tokens,
        'temperature': 0,
        'n_predict': max_tokens
    }
    req = urllib.request.Request('http://localhost:8080/v1/completions',
        data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=180) as resp:
        d = json.loads(resp.read().decode())
    return d.get('choices',[{}])[0].get('text','').strip()

# 填充文本 (与目标无关)
FILLERS = [
    "量子计算利用量子比特的叠加态和纠缠态进行计算。",
    "锂电池正极材料包括NCM、LFP和LCO。",
    "台风是热带海洋上的强烈气旋系统。",
    "蛋白质由氨基酸通过肽键连接而成。",
    "文艺复兴时期达芬奇创作了蒙娜丽莎。",
    "长江全长约6300公里流经11个省级行政区。",
    "机器学习梯度下降算法迭代更新参数。",
    "秦始皇建立了中国历史上第一个中央集权王朝。",
    "光合作用发生在叶绿体中。",
    "区块链是分布式账本技术。",
    "珠穆朗玛峰海拔8848.86米。",
    "DNA双螺旋结构由沃森和克里克提出。",
    "电动汽车续航取决于电池容量。",
    "唐诗宋词是中国古典文学瑰宝。",
    "火星是与地球环境最相似的行星之一。",
    "牛顿三大定律奠定了经典力学基础。",
    "光合作用产生氧气供生物呼吸。",
    "丝绸之路连接了东西方文明。",
    "黑洞是引力极强的天体。",
    "细胞是生物体结构和功能的基本单位。",
]

def build_ctx(n_paras, target):
    """n段填充 + 目标插在中间"""
    ctx = []
    for i in range(n_paras):
        if i == n_paras // 2:
            ctx.append(target)
        else:
            ctx.append(FILLERS[i % len(FILLERS)])
    return '\n'.join(ctx)

tests = [
    ("【关键信息】测试密码是：A1B2C3D4E5F6。", "密码是什么？", "A1B2C3D4E5F6"),
    ("【关键信息】秘密代码是：XYZ-987-ABC。", "秘密代码是什么？", "XYZ-987-ABC"),
]

print("="*60)
print("真实LLM注意力集中度验证 (qwen2.5:7b Q4, 投机解码)")
print("="*60)
for n_paras in [10, 30, 60, 120]:
    ok_count = 0
    total = 0
    ctx_chars = n_paras * 25
    for target, question, expected in tests:
        ctx = build_ctx(n_paras, target)
        prompt = f"{ctx}\n\n问题：{question}\n只回答目标信息，不要其他内容。答案："
        try:
            ans = complete(prompt, 40)
            ok = expected in ans
            if ok: ok_count += 1
            total += 1
            print(f"  {ctx_chars}字: {'✅' if ok else '❌'} → {ans[:40]!r}")
        except Exception as e:
            print(f"  {ctx_chars}字: ⚠️ {str(e)[:50]}")
        time.sleep(0.5)
    print(f"→ {ctx_chars}字上下文: 检索 {ok_count}/{total} 成功\n")
