#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
baseline_sensitivity.py —— 技能基线的【组内同质性检验】与【权重敏感性分析】

【P1 ①② 的落地】
  r1270 自评缺口①:「本次只验证了『分组能拉开【组间】差距』⇒ 未验证『组内同质』」
  r1268 自评缺口②:「权重是我任意设定的 ⇒ 未做敏感性分析」

【分析一:组内同质性】
  若组内方差大 ⇒ 该组【不是同质类别】⇒ 分组阈值选得不好。
  判据:组内变异系数 CV = std/mean。CV 大 ⇒ 组内混杂。

【分析二:权重敏感性】
  ★ 关键问题:换个权重,【技能排名会不会变】?
  做法:随机抽 N 组权重(Dirichlet),重算 S,看【排名相关性】(Spearman ρ)。
  ★ 若 ρ 高 ⇒ 结论对权重不敏感 ⇒ 稳健;
  ★ 若 ρ 低 ⇒ 排名是【权重的产物】⇒ 不得当结论用。
"""
import io
import json
import os
import random
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.chdir(r"<PROFILE_ROOT>")

CAPS = {'code_blocks': 30, 'cmds': 40, 'tables': 60, 'refs': 40,
        'scripts': 15, 'sections': 25}
KEYS = list(CAPS.keys())
BASE_W = {'code_blocks': 0.15, 'cmds': 0.15, 'tables': 0.10,
          'refs': 0.25, 'scripts': 0.20, 'sections': 0.15}


def score(m, w):
    tot = 0.0
    for k in KEYS:
        tot += w[k] * min(1.0, (m.get(k, 0) or 0) / CAPS[k])
    tot += 0.02 * (1 if m.get('has_allowed') else 0)
    tot += 0.02 * (1 if m.get('has_version') else 0)
    return min(1.0, tot)


def spearman(a, b):
    """Spearman 秩相关(无并列处理,若并列用平均秩)。"""
    n = len(a)
    if n < 2:
        return None
    def rank(x):
        order = sorted(range(n), key=lambda i: x[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and x[order[j + 1]] == x[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    ra, rb = rank(a), rank(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = sum((x - ma) ** 2 for x in ra) ** 0.5
    db = sum((x - mb) ** 2 for x in rb) ** 0.5
    return num / (da * db) if da and db else None


def main():
    d = json.load(io.open('data/skill_baseline.json', encoding='utf-8'))['skills']
    items = [(k, v) for k, v in d.items() if 'S' in v]

    # ── 分析一:组内同质性 ──────────────────────────────────────
    import collections
    g = collections.defaultdict(list)
    for k, v in items:
        g[v.get('group', 'unknown')].append(v['S'])
    print('=' * 70)
    print('分析一:组内同质性(★ CV 大 ⇒ 组内混杂 ⇒ 分组阈值不佳)')
    print('=' * 70)
    print('  %-12s %5s %9s %9s %9s %8s' % ('group', 'n', 'mean', 'std', 'CV', '跨度'))
    for k, ss in sorted(g.items(), key=lambda x: -len(x[1])):
        n = len(ss)
        mu = sum(ss) / n
        var = sum((x - mu) ** 2 for x in ss) / n
        sd = var ** 0.5
        cv = sd / mu if mu else 0
        print('  %-12s %5d %9.4f %9.4f %9.3f %8.4f'
              % (k, n, mu, sd, cv, max(ss) - min(ss)))

    # ── 分析二:权重敏感性 ──────────────────────────────────────
    print()
    print('=' * 70)
    print('分析二:权重敏感性(★ Spearman ρ 高 ⇒ 排名稳健;低 ⇒ 排名是权重的产物)')
    print('=' * 70)
    base = [score(v, BASE_W) for _, v in items]
    random.seed(20260918)
    N = 300
    rhos = []
    for _ in range(N):
        raw = [random.expovariate(1.0) for _ in KEYS]
        s = sum(raw)
        w = dict(zip(KEYS, [x / s for x in raw]))
        alt = [score(v, w) for _, v in items]
        r = spearman(base, alt)
        if r is not None:
            rhos.append(r)
    rhos_sorted = sorted(rhos)
    n = len(rhos_sorted)
    print('  随机权重组数: %d (Dirichlet via expovariate)' % n)
    print('  Spearman ρ(相对基准权重):')
    print('    min  = %.4f' % rhos_sorted[0])
    print('    p05  = %.4f' % rhos_sorted[int(n * 0.05)])
    print('    p50  = %.4f' % rhos_sorted[n // 2])
    print('    mean = %.4f' % (sum(rhos_sorted) / n))
    print('    max  = %.4f' % rhos_sorted[-1])
    lo = sum(1 for r in rhos_sorted if r < 0.8)
    print('  ★ ρ < 0.8 的比例: %d/%d = %.1f%%' % (lo, n, lo / n * 100))
    print()
    if rhos_sorted[n // 2] >= 0.95:
        print('  ★ 判定: 排名【高度稳健】—— 换权重后排序基本不变。')
    elif rhos_sorted[n // 2] >= 0.8:
        print('  ★ 判定: 排名【中等稳健】—— 可作参考,不宜作为硬结论。')
    else:
        print('  ★ 判定: 排名【不稳健】—— ★ 它是权重的产物,【不得】当结论用。')
    print('=' * 70)


if __name__ == '__main__':
    main()
