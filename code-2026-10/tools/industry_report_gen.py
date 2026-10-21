#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI/Agent 工具链与算法前沿 · 行业周报生成器

数据源（本地 scout 产物, 非 VPS 单节点）:
  - D:/hermes/data/agent_knowledge/算法/xuntian_github_scout_<date>.json   (GitHub scout)
  - D:/hermes/data/agent_knowledge/算法/trending_<date>.json               (trending 榜)
  - D:/hermes/data/agent_knowledge/algorithm/<方向>/<date>.json            (分方向 arXiv+repos)
输出: industry_weekly.html + industry_weekly.md

⭐ 与 vps_report_gen.py 共用 SVG 手绘风格, 但数据源有【外部可核性】(GitHub/arXiv 公开),
   故本报告可对外发布; 局限节仍如实标注。
"""
import json, os, glob, re, datetime
from collections import Counter

ROOT = 'D:/hermes/data/agent_knowledge'
OUT = 'D:/hermes/data/vps_report'
os.makedirs(OUT, exist_ok=True)


def latest(pat):
    fs = sorted(glob.glob(pat))
    return fs[-1] if fs else None


# ---------- SVG ----------
def svg_bars(pairs, w=680, h=180, color='#2563eb'):
    if not pairs:
        return '<svg width="%d" height="%d"></svg>' % (w, h)
    mx = max(x[1] for x in pairs) or 1
    n = len(pairs); bw = max(3, (w - 40) / n * 0.72); gap = (w - 40) / n
    o = ['<svg width="%d" height="%d" style="font:10px sans-serif">' % (w, h)]
    for k in range(5):
        y = 20 + (h - 55) * k / 4
        o.append('<line x1="34" y1="%.1f" x2="%d" y2="%.1f" stroke="#e5e7eb"/>' % (y, w - 6, y))
        o.append('<text x="2" y="%.1f" fill="#9ca3af">%d</text>' % (y + 3, int(mx * (1 - k / 4))))
    for i, (lab, val) in enumerate(pairs):
        bh = (h - 55) * val / mx; x = 36 + i * gap; y = h - 35 - bh
        o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" rx="2"><title>%s: %s</title></rect>'
                 % (x, y, bw, bh, color, lab, val))
        o.append('<text x="%.1f" y="%d" fill="#6b7280" text-anchor="middle">%s</text>' % (x + bw / 2, h - 20, lab))
    o.append('</svg>')
    return ''.join(o)


def svg_hbars(pairs, w=680, rowh=24, color='#059669'):
    if not pairs:
        return '<svg width="%d" height="%d"></svg>' % (w, 12)
    h = 14 + rowh * len(pairs); mx = max(x[1] for x in pairs) or 1
    o = ['<svg width="%d" height="%d" style="font:11px sans-serif">' % (w, h)]
    for i, (lab, val) in enumerate(pairs):
        y = 6 + i * rowh; bw = (w - 330) * val / mx
        o.append('<text x="0" y="%d" fill="#374151">%s</text>' % (y + 12, lab[:36]))
        o.append('<rect x="250" y="%d" width="%.1f" height="13" fill="%s" rx="2"><title>%s: %s</title></rect>'
                 % (y, bw, color, lab, val))
        o.append('<text x="%.1f" y="%d" fill="#6b7280">%s</text>' % (258 + bw, y + 12, val))
    o.append('</svg>')
    return ''.join(o)


def md_bar(val, mx, width=26):
    return '█' * max(1, int(round(val / mx * width))) if mx else ''


# ---------- 载入 ----------
scout_p = latest(ROOT + '/算法/xuntian_github_scout_*.json')
trend_p = latest(ROOT + '/算法/trending_*.json')
scout = json.load(open(scout_p, encoding='utf-8')) if scout_p else {}
trend = json.load(open(trend_p, encoding='utf-8')) if trend_p else []
DATE = scout.get('date', datetime.date.today().isoformat())

DIRS = ['数学原理', '机器学习', '深度学习', '算法原理', '计算机原理', '神经算法CNN_LLM', '热点项目']
per_dir = {}
for dn in DIRS:
    p = f'{ROOT}/algorithm/{dn}/{DATE}.json'
    if os.path.exists(p):
        per_dir[dn] = json.load(open(p, encoding='utf-8'))

# ---------- 整形 ----------
new_all = scout.get('new_all', []) or []
top = sorted(new_all, key=lambda x: -(x.get('score') or 0))[:15]
langs = Counter((x.get('language') or 'N/A') for x in new_all)
lang_pairs = [(k, v) for k, v in langs.most_common(8)]
tr = sorted(trend, key=lambda x: -(x.get('period_gain') or 0))[:12]
tr_pairs = [(x['repo'], x.get('period_gain') or 0) for x in tr]
dir_pairs = [(dn, len(d.get('new_papers') or [])) for dn, d in per_dir.items()]

# 主题聚类（用 keywords 归并仓库名/描述）
THEMES = {
    'agent harness': r'harness',
    'agent 记忆/上下文': r'memory|context|mcp',
    '多智能体/编排': r'multi[- ]?agent|orchestrat|swarm',
    '技能/skills': r'skill',
    '编码 agent': r'coding|copilot|code agent',
    'RAG/检索': r'\brag\b|retriev|vector',
    '强化学习/RL': r'\brl\b|reinforcement',
    '微调/训练': r'fine.?tun|train|lora',
    '推理/部署': r'inference|serving|deploy|quantiz',
}
theme_ct = Counter()
for x in new_all:
    blob = ((x.get('full_name') or '') + ' ' + (x.get('description') or '')).lower()
    for tn, rx in THEMES.items():
        if re.search(rx, blob):
            theme_ct[tn] += 1
theme_pairs = [(k, v) for k, v in theme_ct.most_common(9)]

# ---------- Markdown ----------
M = []
M.append('# AI / Agent 工具链与算法前沿 · 周报\n')
M.append('> 数据日 **%s** ｜ scout `%s` ｜ 生成 %s\n'
         % (DATE, scout.get('scout', '-'), datetime.datetime.now().isoformat(timespec='seconds')))
M.append('> 数据源：GitHub Search API（%d 条查询）+ arXiv 元数据。**全部为公开可复核来源。**\n'
         % scout.get('queries_total', 0))
M.append('## 1. 本周扫描概览\n')
M.append('| 指标 | 值 |')
M.append('|:--|--:|')
M.append('| 查询数 | %s |' % scout.get('queries_total', '-'))
M.append('| 历史已见仓库（去重池） | %s |' % f"{scout.get('seen_repos', 0):,}")
M.append('| 本轮候选池 | %s |' % scout.get('pool', '-'))
M.append('| 去重后仓库 | %s |' % scout.get('unique_repos', '-'))
M.append('| **新发现** | **%s**（agent 向 %s / 算法向 %s）|'
         % (scout.get('new_count', '-'), scout.get('agent_new_count', '-'), scout.get('algo_new_count', '-')))
M.append('| trending 榜条目 | %s |\n' % scout.get('trending_count', '-'))
M.append('## 2. 新晋项目 Top 15（按相关度×热度）\n')
M.append('| # | 仓库 | ★ | 语言 | 相关度 | 描述 |')
M.append('|--:|:--|--:|:--|--:|:--|')
for i, x in enumerate(top, 1):
    desc = (x.get('description') or '')[:56].replace('|', '/')
    M.append('| %d | [%s](%s) | %s | %s | %s | %s |'
             % (i, x['full_name'], x.get('url', 'https://github.com/' + x['full_name']),
                f"{x.get('stars', 0):,}", x.get('language') or '-', x.get('relevance', '-'), desc))
M.append('')
M.append('## 3. 语言分布（新发现）\n')
mx = max((v for _, v in lang_pairs), default=1)
M.append('```')
for k, v in lang_pairs:
    M.append('%-12s %s %d' % (k, md_bar(v, mx), v))
M.append('```\n')
M.append('## 4. 主题聚类（新发现按关键词归并）\n')
mxt = max((v for _, v in theme_pairs), default=1)
M.append('```')
for k, v in theme_pairs:
    M.append('%-16s %s %d' % (k, md_bar(v, mxt), v))
M.append('```\n')
M.append('## 5. Trending 榜（按周期新增星数）\n')
M.append('| # | 仓库 | 周期新增 ★ | 总 ★ | 语言 |')
M.append('|--:|:--|--:|--:|:--|')
for i, x in enumerate(tr, 1):
    M.append('| %d | [%s](https://github.com/%s) | %s | %s | %s |'
             % (i, x['repo'], x['repo'], f"{x.get('period_gain', 0):,}",
                f"{x.get('stars', 0):,}", x.get('lang') or '-'))
M.append('')
M.append('## 6. 分方向 arXiv 新论文\n')
M.append('| 方向 | 仓库 | 新仓库 | 论文 | 新论文 |')
M.append('|:--|--:|--:|--:|--:|')
for dn, d in per_dir.items():
    M.append('| %s | %d | %d | %d | **%d** |' % (dn, len(d.get('repos') or []), len(d.get('new_repos') or []),
                                                len(d.get('papers') or []), len(d.get('new_papers') or [])))
M.append('')
for dn, d in list(per_dir.items())[:4]:
    ps = (d.get('new_papers') or d.get('papers') or [])[:3]
    if not ps:
        continue
    M.append('**%s · 抽样 3 篇**\n' % dn)
    for p in ps:
        t = (p.get('title') or '')[:88]
        aid = (p.get('id') or '').rstrip('/').split('/')[-1]
        M.append('- %s  `%s`  (%s)' % (t, aid, p.get('published', '')))
    M.append('')
M.append('## 7. ⚠️ 口径与局限\n')
M.append('- **来源**：GitHub Search API + arXiv 元数据，均为**公开可复核**来源；每条均可回溯到仓库/论文 ID。')
M.append('- **非全量**：scout 按预置关键词与星数阈值筛选（如 `agent harness created:>2026-09-11 stars:>80`），'
         '**未命中的项目不在样本内**，故本报告的"新发现"是**条件采样**而非"本周全部新项目"。')
M.append('- **相关度与评分为主观权重**：`relevance`/`score` 由 scout 的关键词权重表算出，不是客观指标。')
M.append('- **arXiv 侧**：`arxiv_via_proxy` 字段表明本轮抓取是否经代理；未做全文精读，仅有元数据（标题/作者/摘要）。')
M.append('- **不可作为投资/选型唯一依据**：星数与周期增量可被刷量影响，请结合代码质量与实际使用判断。')
md = '\n'.join(M)
open(f'{OUT}/industry_weekly.md', 'w', encoding='utf-8').write(md)

# ---------- HTML ----------
H = ['<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>AI/Agent 工具链与算法前沿 · 周报</title><style>',
     'body{font:14px/1.7 system-ui,-apple-system,"Segoe UI",sans-serif;max-width:820px;margin:0 auto;padding:28px;color:#111827;background:#fff}',
     'h1{font-size:24px;border-bottom:2px solid #2563eb;padding-bottom:8px}h2{font-size:17px;margin-top:28px;color:#1f2937}',
     'table{border-collapse:collapse;width:100%;font-size:13px}td,th{border:1px solid #e5e7eb;padding:5px 8px;text-align:left}th{background:#f9fafb}',
     '.kpi{display:flex;flex-wrap:wrap;gap:12px;margin:14px 0}.kpi div{flex:1;min-width:120px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:10px 12px}',
     '.kpi b{display:block;font-size:20px;color:#2563eb}.kpi span{font-size:12px;color:#6b7280}',
     '.warn{background:#fffbeb;border-left:3px solid #f59e0b;padding:10px 14px;font-size:13px;border-radius:4px}',
     'code{background:#f3f4f6;padding:1px 5px;border-radius:3px;font-size:12px}svg{max-width:100%;height:auto}a{color:#2563eb;text-decoration:none}',
     '</style></head><body>']
H.append('<h1>AI / Agent 工具链与算法前沿 · 周报</h1>')
H.append('<p style="color:#6b7280;font-size:12px">数据日 <b>%s</b> ｜ scout <code>%s</code> ｜ 生成 %s ｜ 来源 GitHub Search API + arXiv（公开可核）</p>'
         % (DATE, scout.get('scout', '-'), datetime.datetime.now().isoformat(timespec='seconds')))
H.append('<div class="kpi">')
H.append('<div><span>查询数</span><b>%s</b></div>' % scout.get('queries_total', 0))
H.append('<div><span>去重仓库</span><b>%s</b></div>' % scout.get('unique_repos', 0))
H.append('<div><span>新发现</span><b>%s</b></div>' % scout.get('new_count', 0))
H.append('<div><span>agent 向</span><b>%s</b></div>' % scout.get('agent_new_count', 0))
H.append('<div><span>算法向</span><b>%s</b></div>' % scout.get('algo_new_count', 0))
H.append('<div><span>trending</span><b>%s</b></div>' % scout.get('trending_count', 0))
H.append('</div>')
H.append('<h2>新晋项目 Top 15</h2><table><tr><th>#</th><th>仓库</th><th>★</th><th>语言</th><th>相关度</th><th>描述</th></tr>')
for i, x in enumerate(top, 1):
    H.append('<tr><td>%d</td><td><a href="%s">%s</a></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
             % (i, x.get('url', '#'), x['full_name'], f"{x.get('stars', 0):,}",
                x.get('language') or '-', x.get('relevance', '-'), (x.get('description') or '')[:70]))
H.append('</table>')
H.append('<h2>语言分布</h2>' + svg_hbars(lang_pairs, color='#7c3aed'))
H.append('<h2>主题聚类</h2>' + svg_hbars(theme_pairs))
H.append('<h2>Trending 榜（周期新增 ★）</h2>' + svg_hbars(tr_pairs[:10], color='#dc2626'))
H.append('<h2>分方向 arXiv 新论文数</h2>' + svg_bars(dir_pairs))
H.append('<h2>⚠️ 口径与局限</h2><div class="warn">')
H.append('<b>条件采样</b>：scout 按预置关键词+星数阈值筛选，未命中的项目不在样本内，"新发现"不等于"本周全部新项目"。<br>')
H.append('<b>评分主观</b>：<code>relevance</code>/<code>score</code> 由关键词权重表算出，非客观指标。<br>')
H.append('<b>arXiv 侧仅有元数据</b>（标题/作者/摘要），未做全文精读。<br>')
H.append('<b>星数可被刷量</b>，请结合代码质量判断，勿作为投资/选型唯一依据。')
H.append('</div>')
H.append('<p style="margin-top:28px;color:#9ca3af;font-size:12px">生成器 <code>industry_report_gen.py</code> · 数据源 <code>agent_knowledge/</code></p>')
H.append('</body></html>')
open(f'{OUT}/industry_weekly.html', 'w', encoding='utf-8').write(''.join(H))

print('scout =', scout_p)
print('trend =', trend_p)
print('方向 =', list(per_dir.keys()))
print('新发现 =', len(new_all), '| trending =', len(trend))
print('generated:')
for f in ('industry_weekly.md', 'industry_weekly.html'):
    p = os.path.join(OUT, f)
    print('  ', p, os.path.getsize(p), 'B')
