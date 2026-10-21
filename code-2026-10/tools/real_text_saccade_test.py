#!/usr/bin/env python3
"""真实文本验证双焦点扫视 — 用llama-server生成的真实文本token分布
方法: 生成真实文本 → 用LLM的logits近似token重要性 → 模拟KV分布
验证: 双焦点扫视 vs 单焦点 在真实文本分布上的信息覆盖
"""
import urllib.request, json, time
import numpy as np

def llama_generate(prompt, max_tokens=500):
    payload = {'prompt': prompt, 'model': 'qwen2.5', 'max_tokens': max_tokens, 'temperature': 0.7}
    req = urllib.request.Request('http://localhost:8080/v1/completions',
        data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    resp = json.loads(urllib.request.urlopen(req, timeout=180).read())
    return resp['choices'][0]['text']

def simulate_importance(text, window=16):
    """用文本的字符熵近似token重要性 (真实信息密度代理)"""
    chars = list(text)
    n = len(chars)
    # 滑动窗口字符频率 → 信息熵 (低重复=高信息=重要)
    importance = np.zeros(n)
    for i in range(n):
        start = max(0, i - window)
        chunk = chars[start:i+1]
        unique = len(set(chunk))
        importance[i] = unique / max(1, len(chunk))  # 多样性=信息量
    return importance

def single_focus(importance, k):
    """单焦点: 全局top-k"""
    return np.argsort(importance)[-k:]

def dual_saccade(importance, k):
    """双焦点: 近端(后1/4) + 远端(前3/4) 各取k/2"""
    n = len(importance)
    split = n * 3 // 4
    k_half = k // 2
    near = np.argsort(importance[split:])[-k_half:] + split
    far = np.argsort(importance[:split])[-k_half:]
    return np.concatenate([near, far])

if __name__ == '__main__':
    print("=== 真实文本验证双焦点扫视 ===\n")
    
    prompt = """请写一篇关于锂电池技术的科普文章，内容包括：工作原理、正极材料比较、能量密度、循环寿命、安全性、未来发展趋势。约500字。"""
    text = llama_generate(prompt)
    print(f"生成文本: {len(text)} 字符\n")
    
    importance = simulate_importance(text)
    n = len(importance)
    
    # 总信息量
    total_info = importance.sum()
    
    for k_ratio in [0.1, 0.2, 0.3]:
        k = max(10, int(n * k_ratio))
        idx_s = single_focus(importance, k)
        idx_d = dual_saccade(importance, k)
        
        info_s = importance[idx_s].sum() / total_info
        info_d = importance[idx_d].sum() / total_info
        
        print(f"k={k} ({k_ratio*100:.0f}%): 单焦点覆盖={info_s*100:.1f}% | 双焦点覆盖={info_d*100:.1f}% | 增益={ (info_d-info_s)*100:+.1f}%")
    
    print("\n=== 结论 ===")
    print("真实文本分布下双焦点 vs 单焦点的信息覆盖对比")
