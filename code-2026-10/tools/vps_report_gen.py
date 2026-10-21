#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VPS 流量情报周报生成器 (方案 B 基础设施)

输入: stats.json (由 VPS 上的 /usr/local/bin/vps_stats.py 每小时采集)
输出: report.html (可托管到站点) + weekly_report.md
依赖: 仅标准库 —— 图表用内联 SVG 手绘, 免 matplotlib

⭐ 设计原则
- 合规优先: 报告只呈现【聚合指标】, 永不列原始 IP; 附合规声明
- 口径可核: 每条数字标注来源字段与观测窗口; 单节点数据不冒充市场数据
"""
import json, os, sys, datetime

SRC = sys.argv[1] if len(sys.argv) > 1 else 'D:/hermes/data/vps_report/stats.json'
OUT = os.path.dirname(SRC)
d = json.load(open(SRC, encoding='utf-8'))
v = d['v2ray_historical']
t = d['trojan_realtime']
GEN = d.get('generated', '')


# ---------- SVG 手绘 ----------
def svg_bars(pairs, w=680, h=180, color='#2563eb', unit=''):
    """pairs: [(label, value)] -> 竖向柱状图 SVG"""
    if not pairs:
        return '<svg width="%d" height="%d"></svg>' % (w, h)
    mx = max(x[1] for x in pairs) or 1
    n = len(pairs)
    bw = max(3, (w - 40) / n * 0.72)
    gap = (w - 40) / n
    out = ['<svg width="%d" height="%d" style="font:10px sans-serif">' % (w, h)]
    # 网格
    for k in range(5):
        y = 20 + (h - 55) * k / 4
        out.append('<line x1="34" y1="%.1f" x2="%d" y2="%.1f" stroke="#e5e7eb"/>' % (y, w - 6, y))
        out.append('<text x="2" y="%.1f" fill="#9ca3af">%s</text>' % (y + 3, int(mx * (1 - k / 4))))
    for i, (lab, val) in enumerate(pairs):
        bh = (h - 55) * val / mx
        x = 36 + i * gap
        y = h - 35 - bh
        out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" rx="2"><title>%s: %s%s</title></rect>'
                   % (x, y, bw, bh, color, lab, val, unit))
        out.append('<text x="%.1f" y="%d" fill="#6b7280" text-anchor="middle">%s</text>' % (x + bw / 2, h - 20, lab))
    out.append('</svg>')
    return ''.join(out)


def svg_hbars(pairs, w=680, rowh=26, color='#059669', unit=''):
    h = 14 + rowh * len(pairs)
    if not pairs:
        return '<svg width="%d" height="%d"></svg>' % (w, h)
    mx = max(x[1] for x in pairs) or 1
    out = ['<svg width="%d" height="%d" style="font:11px sans-serif">' % (w, h)]
    for i, (lab, val) in enumerate(pairs):
        y = 6 + i * rowh
        bw = (w - 300) * val / mx
        out.append('<text x="0" y="%d" fill="#374151">%s</text>' % (y + 12, lab[:34]))
        out.append('<rect x="240" y="%d" width="%.1f" height="14" fill="%s" rx="2"><title>%s: %s%s</title></rect>'
                   % (y, bw, color, lab, val, unit))
        out.append('<text x="%.1f" y="%d" fill="#6b7280">%s</text>' % (248 + bw, y + 12, val))
    out.append('</svg>')
    return ''.join(out)


def md_bar(val, mx, width=28):
    return '█' * max(1, int(round(val / mx * width))) if mx else ''


# ---------- 数据整形 ----------
hours = sorted(v['top_hours'], key=lambda x: x['hour'])
hour_pairs = [('%d' % h['hour'], h['count']) for h in hours]
# ⚠️ vps_stats.py 是 Python2, daily 来自 dict 迭代 ⇒ 无序。必须按日期排序后再取窗口。
daily = sorted(v['daily'], key=lambda x: x['date'])
day_pairs = [(x['date'][5:], x['count']) for x in daily[-21:]]
dom_pairs = [(x['domain'], x['count']) for x in v['top_domains']]
port_pairs = [(x['port'], x['count']) for x in v['top_ports']]
peak_hour = max(hours, key=lambda x: x['count'])
obs_start, obs_end = (daily[0]['date'], daily[-1]['date']) if daily else ('-', '-')
obs_days = len(daily)

# ---------- Markdown ----------
M = []
M.append('# VPS 流量情报周报\n')
M.append('> 生成时间戳（采集器）：`%s`　｜　报告生成：%s\n' % (GEN, datetime.datetime.now().isoformat(timespec='seconds')))
M.append('## 1. 概览\n')
M.append('| 指标 | 值 |')
M.append('|:--|--:|')
M.append('| 观测窗口 | %s ~ %s |' % (obs_start, obs_end))
M.append('| 总连接数（历史累积） | %s |' % f"{v['total_connections']:,}")
M.append('| 独立客户端（IP 哈希计） | %s |' % v['unique_clients'])
M.append('| 峰值时段 | %02d:00（%s 次） |' % (peak_hour['hour'], f"{peak_hour['count']:,}"))
M.append('| 实时连接（近 24h） | %s |' % t['recent_24h'])
M.append('| 实时字节（近 24h） | %s |\n' % f"{t['total_bytes_24h']:,}")
M.append('## 2. 时段分布（0–23 时）\n')
mx = max(x[1] for x in hour_pairs)
M.append('```')
for lab, val in hour_pairs:
    M.append('%02s时 %s %s' % (lab, md_bar(val, mx), f'{val:,}'))
M.append('```\n')
M.append('## 3. 日趋势（近 21 天）\n')
mx2 = max(x[1] for x in day_pairs) if day_pairs else 1
M.append('```')
for lab, val in day_pairs:
    M.append('%s %s %s' % (lab, md_bar(val, mx2, 24), f'{val:,}'))
M.append('```\n')
M.append('## 4. Top 域名\n')
M.append('| # | 域名 | 连接数 | 占比 |')
M.append('|--:|:--|--:|--:|')
tot = v['total_connections'] or 1
for i, (dm, c) in enumerate(dom_pairs, 1):
    M.append('| %d | `%s` | %s | %.1f%% |' % (i, dm, f'{c:,}', c / tot * 100))
M.append('')
M.append('## 5. 目标端口分布\n')
M.append('| 端口 | 连接数 | 占比 | 备注 |')
M.append('|--:|--:|--:|:--|')
NOTE = {'5228': 'Google GCM/MTalk 推送', '443': 'HTTPS', '80': 'HTTP'}
for p, c in port_pairs:
    M.append('| %s | %s | %.1f%% | %s |' % (p, f'{c:,}', c / tot * 100, NOTE.get(p, '—')))
M.append('')
M.append('## 6. 合规声明\n')
for k, val in d['compliance'].items():
    M.append('- **%s**: `%s`' % (k, val))
M.append('- 本报告仅含**聚合指标**；原始 IP 仅存哈希，不落盘明文，不出 VPS。\n')
M.append('## 7. ⚠️ 口径与局限（必读）\n')
M.append('- **单节点样本**：全部数据来自**一台 VPS**，不代表任何市场或行业总体。')
M.append('- **历史窗口**：观测期为 `%s ~ %s`（v2ray 归档日志），**非近期**；实时侧（trojan 近 24h）当前为 `%s`。' % (obs_start, obs_end, t['recent_24h']))
M.append('- **流量成分**：Top 域名被 `mtalk.google.com` 等 Android 推送通道主导，反映的是**终端后台保活**，不是"上网偏好"。')
M.append('- **不可外推**：59 个哈希客户端的样本量不支持任何统计推断；请勿将本报告当作行业情报使用。')
M.append('- 本报告的定位是 **运营自监控**，不是可售情报产品（详见项目台账 `vps_resume_20261013.md`）。')

md = '\n'.join(M)
open(os.path.join(OUT, 'weekly_report.md'), 'w', encoding='utf-8').write(md)

# ---------- HTML ----------
H = []
H.append('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">')
H.append('<title>VPS 流量情报周报</title><style>')
H.append('body{font:14px/1.7 system-ui,-apple-system,"Segoe UI",sans-serif;max-width:760px;margin:0 auto;padding:28px;color:#111827;background:#fff}')
H.append('h1{font-size:24px;border-bottom:2px solid #2563eb;padding-bottom:8px}h2{font-size:17px;margin-top:28px;color:#1f2937}')
H.append('table{border-collapse:collapse;width:100%;font-size:13px}td,th{border:1px solid #e5e7eb;padding:5px 8px;text-align:left}th{background:#f9fafb}')
H.append('.kpi{display:flex;flex-wrap:wrap;gap:12px;margin:14px 0}.kpi div{flex:1;min-width:130px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:10px 12px}')
H.append('.kpi b{display:block;font-size:20px;color:#2563eb}.kpi span{font-size:12px;color:#6b7280}')
H.append('.warn{background:#fffbeb;border-left:3px solid #f59e0b;padding:10px 14px;font-size:13px;border-radius:4px}')
H.append('.ok{background:#f0fdf4;border-left:3px solid #22c55e;padding:10px 14px;font-size:13px;border-radius:4px}')
H.append('code{background:#f3f4f6;padding:1px 5px;border-radius:3px;font-size:12px}svg{max-width:100%;height:auto}')
H.append('</style></head><body>')
H.append('<h1>VPS 流量情报周报</h1>')
H.append('<p style="color:#6b7280;font-size:12px">采集器时间戳 <code>%s</code>　·　报告生成 %s</p>' % (GEN, datetime.datetime.now().isoformat(timespec='seconds')))
H.append('<div class="kpi">')
H.append('<div><span>观测窗口</span><b style="font-size:13px">%s<br>~ %s</b></div>' % (obs_start, obs_end))
H.append('<div><span>总连接</span><b>%s</b></div>' % f"{v['total_connections']:,}")
H.append('<div><span>独立客户端</span><b>%s</b></div>' % v['unique_clients'])
H.append('<div><span>峰值时段</span><b>%02d:00</b></div>' % peak_hour['hour'])
H.append('<div><span>近 24h 连接</span><b>%s</b></div>' % t['recent_24h'])
H.append('</div>')
H.append('<h2>时段分布（0–23 时）</h2>' + svg_bars(hour_pairs))
H.append('<h2>日趋势</h2>' + svg_bars(day_pairs, color='#7c3aed'))
H.append('<h2>Top 域名</h2>' + svg_hbars(dom_pairs))
H.append('<h2>目标端口</h2>' + svg_hbars(port_pairs, color='#dc2626'))
H.append('<h2>合规声明</h2><div class="ok">')
H.append('仅聚合指标；原始 IP 仅存哈希、不落盘明文、不出 VPS。<br>' + '<br>'.join('<code>%s</code>: %s' % (k, val) for k, val in d['compliance'].items()))
H.append('</div>')
H.append('<h2>⚠️ 口径与局限（必读）</h2><div class="warn">')
H.append('<b>单节点样本</b>：全部数据来自一台 VPS，不代表任何市场或行业总体。<br>')
H.append('<b>历史窗口</b>：观测期 <code>%s ~ %s</code>，非近期；实时侧（近 24h）当前为 <code>%s</code>。<br>' % (obs_start, obs_end, t['recent_24h']))
H.append('<b>流量成分</b>：Top 域名被 <code>mtalk.google.com</code> 等 Android 推送通道主导，反映终端后台保活，不是"上网偏好"。<br>')
H.append('<b>不可外推</b>：59 个哈希客户端的样本量不支持统计推断，请勿当作行业情报使用。')
H.append('</div>')
H.append('<p style="margin-top:28px;color:#9ca3af;font-size:12px">生成器 <code>vps_report_gen.py</code> · 数据源 <code>stats.json</code></p>')
H.append('</body></html>')
html = ''.join(H)
open(os.path.join(OUT, 'report.html'), 'w', encoding='utf-8').write(html)

print('✅ 已生成:')
print('  ', os.path.join(OUT, 'weekly_report.md'), os.path.getsize(os.path.join(OUT, 'weekly_report.md')), 'B')
print('  ', os.path.join(OUT, 'report.html'), os.path.getsize(os.path.join(OUT, 'report.html')), 'B')
