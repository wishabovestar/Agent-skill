#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每周行业周报 · 生成 + 部署 (cron 用)

流程: 生成 industry_weekly -> 本地内容级校验 -> 上传 VPS -> 输出摘要
cron 以 no_agent=True 运行本脚本, stdout 会被原样投递给用户。
失败时以非零退出码 + 明确错误行结束。
"""
import datetime
import os
import subprocess
import sys

AN = r'D:/hermes/analysis'
OUT = r'D:/hermes/data/vps_report'
REMOTE = '/home/wwwroot/3DCEList/industry_weekly.html'
TITLE = 'AI / Agent 工具链与算法前沿'


def run(cmd, cwd=AN):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          cwd=cwd, encoding='utf-8', errors='replace')


def main():
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    lines = [f'📊 行业周报自动出刊 · {stamp}']

    # 1) 生成
    r1 = run(f'python "{AN}/industry_report_gen.py"')
    if r1.returncode != 0:
        lines.append('❌ 生成失败')
        lines.append((r1.stdout or '')[-500:])
        lines.append((r1.stderr or '')[-500:])
        print('\n'.join(lines))
        return 1

    # 2) 本地内容级校验 (不只看文件存在 —— 按 G1 教训)
    html_p = os.path.join(OUT, 'industry_weekly.html')
    if not os.path.exists(html_p):
        lines.append('❌ 未生成 industry_weekly.html')
        print('\n'.join(lines))
        return 1
    body = open(html_p, encoding='utf-8', errors='replace').read()
    checks = {
        '标题': TITLE in body,
        '口径节': '口径与局限' in body,
        'SVG图': '<svg' in body,
    }
    bad = [k for k, v in checks.items() if not v]
    if bad:
        lines.append('❌ 本地内容校验未过: ' + ', '.join(bad))
        print('\n'.join(lines))
        return 1
    size = os.path.getsize(html_p)
    lines.append(f'✅ 生成 OK（{size:,} B，内容级校验 3/3）')

    # 3) 部署
    r3 = run(f'python "{AN}/vps_ssh.py" upload "{html_p}" {REMOTE}')
    if '已上传' not in (r3.stdout or ''):
        lines.append('❌ 上传失败')
        lines.append((r3.stdout or '')[-300:])
        lines.append((r3.stderr or '')[-300:])
        print('\n'.join(lines))
        return 1
    lines.append('✅ 已部署 → ' + REMOTE)

    # 4) 远端内容级复核
    q = ("grep -c 'AI / Agent' " + REMOTE)
    r4 = run(f'python "{AN}/vps_ssh.py" exec "{q}"')
    hit = (r4.stdout or '').strip().splitlines()
    ok = any(x.strip().isdigit() and int(x.strip()) > 0 for x in hit)
    lines.append(('✅ 远端复核命中' if ok else '⚠️ 远端复核未命中（请人工确认）'))

    print('\n'.join(lines))
    return 0


if __name__ == '__main__':
    sys.exit(main())
