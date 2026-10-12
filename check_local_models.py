#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_local_models.py — 本机模型校验（真实推理，非探活）
对每个已装 Ollama 模型发同一提示，测: 状态/延迟/吞吐/乱码率/是否答对。
乱码判据: U+FFFD 占比 + 控制符占比 + 罕见高位字符占比 + 最大重复串。
"""
import json, re, time, sys, urllib.request

OLLAMA = 'http://127.0.0.1:11434'
PROMPT = '用一句中文回答：1+1 等于几？只输出答案句。'
SEED = 42
# ⭐ MR6 翻转条件: 本报告的"0 乱码"结论在什么情况下失效
REOPEN_IF = ('若任一模型在【领域长提示 × 多变温度 × 多轮】下出现 garbage>0.02 或 max_rep>=8，'
             '则本报告的"全部可用、0 乱码"结论失效，须重测。')

def post(path, payload, t=300):
    req = urllib.request.Request(OLLAMA + path, data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=t) as r:
        b = r.read().decode('utf-8', 'replace')
    return json.loads(b), time.time() - t0

def garbage_ratio(s):
    if not s: return 1.0
    bad = sum(1 for c in s if c == '\ufffd' or (ord(c) < 32 and c not in '\n\t') or 0xE000 <= ord(c) <= 0xF8FF)
    return bad / len(s)

def calibrate():
    """MR5 negative/positive control: 乱码检测器必须先在【已知】输入上给出预期值。
    没有这一步，"garbage=0.00" 无从判断是"真干净"还是"检测器坏了"。"""
    bad  = ('\ufffd\ufffd\ufffd\x01\x02\ue000\ue001' * 4)
    good = '涂层设备精度不足。操作参数设置不当。原材料性能不稳定。'
    gb, gg = garbage_ratio(bad), garbage_ratio(good)
    ok = (gb > 0.9) and (gg == 0.0)
    print(f'  [MR5 校准] 已知乱码 garbage={gb:.2f}(期望>0.90) | 已知正常 garbage={gg:.2f}(期望0.00)'
          f'  ⇒ ' + ('✅ 检测器已校准' if ok else '❌ 校准失败，garbage 指标不可信'))
    return ok

def max_repeat(s):
    best, cur = 1, 1
    for i in range(1, len(s)):
        cur = cur + 1 if s[i] == s[i-1] else 1
        best = max(best, cur)
    return best

def test_generate(model, prompt=PROMPT, seed=SEED):
    r = {'model': model, 'ok': False}
    try:
        d, dt = post('/api/generate', {'model': model, 'prompt': prompt, 'stream': False,
                                       'seed': seed, 'options': {'temperature': 0}})
        out = d.get('response', '') or ''
        r.update(ok=True, latency_s=round(dt, 2), out=out.strip()[:120],
                 eval_count=d.get('eval_count'), eval_dur_ns=d.get('eval_duration'),
                 garbage=round(garbage_ratio(out), 4), max_rep=max_repeat(out), n_chars=len(out))
        if d.get('eval_count') and d.get('eval_duration'):
            r['tok_per_s'] = round(d['eval_count'] / (d['eval_duration'] / 1e9), 1)
    except Exception as e:
        r['err'] = str(e)[:180]
    return r

def test_embed(model):
    r = {'model': model, 'ok': False}
    try:
        d, dt = post('/api/embed', {'model': model, 'input': '极片涂布厚度均匀性'})
        embs = d.get('embeddings') or []
        r.update(ok=True, latency_s=round(dt, 2), dim=(len(embs[0]) if embs else 0),
                 n=len(embs), nonzero=(sum(1 for x in embs[0] if x != 0) if embs else 0))
    except Exception as e:
        r['err'] = str(e)[:180]
    return r

def main():
    # ⭐ MR5: 先校准检测器，再谈结果（否则 garbage=0.00 无法解释）
    if not calibrate():
        print('  ⚠️ 检测器未校准 ⇒ 后续 garbage 指标仅作参考')
    models = [m['name'] for m in json.loads(
        urllib.request.urlopen(OLLAMA + '/api/tags', timeout=10).read())['models']]
    print('=' * 84)
    print(f'本机模型校验 — {len(models)} 个，逐个真跑')
    print('=' * 84)
    results = []
    for m in models:
        if 'bge' in m or 'embed' in m:
            r = test_embed(m)
            verdict = ('✅ 可用' if r.get('ok') and r.get('dim') else '❌ 失败')
            print(f'\n[{m}]  {verdict}')
            print(f'    {r}')
        else:
            r = test_generate(m)
            if not r.get('ok'):
                verdict = '❌ 调用失败'
            elif r['garbage'] > 0.02 or r['max_rep'] >= 8:
                verdict = f"❌ 乱码/退化 (garbage={r['garbage']}, max_rep={r['max_rep']})"
            else:
                verdict = '✅ 可用'
            print(f'\n[{m}]  {verdict}')
            print(f'    延迟 {r.get("latency_s")}s | 输出 {r.get("n_chars")} 字 | '
                  f'速度 {r.get("tok_per_s")} tok/s | garbage {r.get("garbage")}')
            print(f'    输出: {r.get("out","")!r}')
            if r.get('err'): print(f'    err: {r["err"]}')
        results.append(r)
    # 7b vs 7b-clean 对照（记忆里"7b 乱码"的核验）
    print('\n' + '=' * 84)
    print('对照: qwen2.5:7b vs qwen2.5:7b-clean（同提示同种子 temperature=0）')
    print('=' * 84)
    for m in ['qwen2.5:7b', 'qwen2.5:7b-clean']:
        if m in models:
            r = test_generate(m, prompt='简述锂电池极片涂布厚度不均的三种常见成因，每行一条。', seed=SEED)
            print(f'\n[{m}] ok={r.get("ok")} garbage={r.get("garbage")} max_rep={r.get("max_rep")} '
                  f'速度={r.get("tok_per_s")} tok/s')
            print(f'  {r.get("out","")!r}')
    json.dump(results, open(r'D:/hermes/analysis/local_models_report.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print(f'\n报告 → D:/hermes/analysis/local_models_report.json')
    return 0

if __name__ == '__main__':
    sys.exit(main())
