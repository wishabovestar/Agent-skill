#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
claim_trace_check.py —— 结论-证据可追溯性检查器

【为什么存在】
r1245(RSIAgent 验证器拆解)明确指出它【缺失】的一层:
   "没有任何『验证器陈述的证据 ↔ 它自己探针原始输出』的一致性/出处校验"
而本机已实测两个同族失效:
   ① 机器检查通过 ≠ 陈述忠实(≈43%)
   ② 自洽 ≠ 可信(自洽满分但 AUROC 0.70)

本脚本补这一层:给定【一份声称】+【一份原始 transcript】,
机械核验声称里的每个【可核事实】(数字/路径/命令/引文)是否真能在原始材料里找到。

【判定】
  TRACEABLE   声称中的该事实在 transcript 里有出处
  UNTRACEABLE 找不到 ⇒ ★ 这不是"错",而是"无法追溯" ⇒ 按 r1245 三分纪律
              降级为 UNVERIFIED,★ 不得当作 PASS
【输出】退出码:0=全部可追溯 · 1=存在不可追溯项 · 2=用法错

用法:
  python claim_trace_check.py --claim <声称文件> --transcript <原始文件> [--json]
"""
import argparse
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')


# ── 1. 从声称里抽出【可核事实】 ──────────────────────────────────────
# 只抽机械可枚举的形态;语言理解型不进这里(参见 r1240 的双路结论)
RE_NUM = re.compile(r'\d[\d,]*\.?\d*')                       # 数字(含千分位)
RE_PATH = re.compile(r'(?:[A-Za-z]:[\\/][^\s"\'<>|,;)]+|/[A-Za-z0-9_.\-/]{3,})')  # 路径
RE_CMD = re.compile(r'`([^`\n]{3,120})`')                     # 反引号里的命令/标识
RE_QUOTE = re.compile(r'[「"“]([^」"”\n]{6,200})[」"”]')        # 引号里的引文

# ★ 已知限制(实测获得,见 r1262 第七节):
#   ① 本检查器【无法区分「我引的原文」与「我的中文转述」】——
#      实测 r1259 的 35 项不可追溯里有 25 项属此类(如「饱和」「盯瓶颈假设」是翻译,非原文)。
#   ② 从 v1 起:剔除 YAML frontmatter 与标题行(它们不是对证据源的声称)。
#   ③ ★ 引文里的装饰标记(★/【】/**)必须先剥离,否则永远匹配不到原文。
#   ④ rid 编号(r1244 等)不是对证据源的声称 ⇒ 排除。
_DECOR = re.compile(r'[★☆🔴🟡🟢①②③④⑤⑥⑦⑧⑨⑩\[\]【】*`_~]')
_RIDLIKE = re.compile(r'^r?\d{4}$')


def clean_quote(s):
    """★ 已知限制③:剥离装饰标记后再比对(实测 25/35 假阴性源于此)。"""
    return _DECOR.sub('', s).strip()


def is_ignorable_num(v):
    """★ 已知限制④:rid 编号、纯年份/版本等不是对证据源的声称。"""
    if _RIDLIKE.match(v):
        return True
    return False


def strip_frontmatter(text):
    """★ 缺陷修正①:YAML frontmatter 是元数据,不是关于 transcript 的【声称】
    ⇒ 必须剔除,否则标题/rid/tags 全被判为"不可追溯"(实测产生大量假阴性)。"""
    if text.startswith('---'):
        end = text.find('\n---', 3)
        if end != -1:
            rest = text[end + 4:]
            nl = rest.find('\n')
            return rest[nl + 1:] if nl != -1 else ''
    return text


def extract_facts(claim_text):
    """返回 [(kind, value, lineno)] —— 只取机械可核的形态。"""
    facts = []
    for i, line in enumerate(claim_text.split('\n'), 1):
        # 跳过明显的表格分隔/装饰行,减少噪声
        if re.match(r'^\s*[|\-:=+ ]+\s*$', line):
            continue
        # ★ 跳过标题行(章节名不是对 transcript 的声称)
        if re.match(r'^\s*#{1,6}\s', line):
            continue
        for m in RE_PATH.finditer(line):
            v = m.group(0).rstrip('.,;:')
            # ★ 缺陷修正②:路径须含目录分隔符且首段像目录名(避免只取到 /charter.py 这种后缀碎片)
            if (len(v) >= 6 and not v.startswith('//')
                    and re.match(r'^(?:[A-Za-z]:[\\/]|/)', v)
                    and v.count('/') + v.count('\\') >= 2):
                facts.append(('path', v, i))
        for m in RE_CMD.finditer(line):
            v = m.group(1).strip()
            if v and not v.startswith(('http://', 'https://')):
                facts.append(('cmd', v, i))
        for m in RE_QUOTE.finditer(line):
            v = m.group(1).strip()
            # ★ 已知限制③:剥离装饰标记(★/【】/**)后再比对
            v = clean_quote(v)
            if len(v) >= 6:
                facts.append(('quote', v, i))
        for m in RE_NUM.finditer(line):
            v = m.group(0)
            # ★ 已知限制④:rid 编号不是对证据源的声称
            if is_ignorable_num(v):
                continue
            # 过滤明显的序数/编号噪声
            if len(v) >= 2 and not re.match(r'^\d{1,2}$', v):
                facts.append(('num', v, i))
    return facts


def norm(s):
    """归一化:去空白差异、统一分隔符、去尾标点。"""
    s = s.replace('\\', '/')
    s = re.sub(r'\s+', '', s)
    return s.strip('.,;:`\'"()[]{}')


# ── 2. 可追溯性判定 ─────────────────────────────────────────────────
def check(claim_path, transcript_paths):
    """★ 缺陷修正③:支持【多个】证据源 —— 一份声称常同时引用论文原文与源码拆解,
    单 transcript 会把来自第二个源的正确事实误判为"不可追溯"(实测 r1259 vs rsia.txt 即如此)。"""
    raw_claim = io.open(claim_path, encoding='utf-8', errors='replace').read()
    claim = strip_frontmatter(raw_claim)

    raws = []
    for tp in transcript_paths:
        raws.append(io.open(tp, encoding='utf-8', errors='replace').read())
    hay = norm('\n'.join(raws))
    total_chars = sum(len(x) for x in raws)

    facts = extract_facts(claim)
    # 去重(同一事实多次出现只报一次,保留首次行号)
    seen = {}
    for kind, val, ln in facts:
        k = (kind, norm(val))
        if k not in seen:
            seen[k] = (kind, val, ln)
    uniq = list(seen.values())

    ok, miss = [], []
    for kind, val, ln in uniq:
        nv = norm(val)
        if not nv:
            continue
        if nv in hay:
            ok.append((kind, val, ln))
        else:
            # 数字做一次宽松匹配(容忍千分位/小数位差异)
            if kind == 'num':
                alt = nv.replace(',', '')
                if alt in hay.replace(',', ''):
                    ok.append((kind, val, ln))
                    continue
            miss.append((kind, val, ln))

    total = len(ok) + len(miss)
    rate = (len(ok) / total * 100) if total else 100.0
    return {
        'claim': os.path.abspath(claim_path),
        'transcripts': [os.path.abspath(p) for p in transcript_paths],
        'transcript_chars': total_chars,
        'facts_total': total,
        'traceable': len(ok),
        'untraceable': len(miss),
        'trace_rate_pct': round(rate, 2),
        'verdict': 'TRACEABLE' if not miss else 'PARTIAL',
        'untraceable_items': [
            {'kind': k, 'value': v[:120], 'claim_line': ln} for k, v, ln in miss[:60]
        ],
    }


def main():
    ap = argparse.ArgumentParser(description='结论-证据可追溯性检查器')
    ap.add_argument('--claim', required=True, help='声称/结论文件')
    ap.add_argument('--transcript', required=True, action='append',
                    help='原始 transcript / 原始输出(可重复指定多个证据源)')
    ap.add_argument('--json', action='store_true', help='输出 JSON')
    a = ap.parse_args()

    for p in [a.claim] + a.transcript:
        if not os.path.isfile(p):
            sys.stderr.write('用法错: 文件不存在 %s\n' % p)
            return 2

    r = check(a.claim, a.transcript)

    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print('=' * 62)
        print('结论-证据可追溯性检查  (补 RSIAgent 缺失的一层)')
        print('=' * 62)
        print('  声称      : %s' % os.path.basename(r['claim']))
        print('  证据源    : %d 个,共 %d 字符' % (len(r['transcripts']), r['transcript_chars']))
        for tp in r['transcripts']:
            print('              - %s' % os.path.basename(tp))
        print('-' * 62)
        print('  可核事实  : %d' % r['facts_total'])
        print('  ├ 可追溯  : %d' % r['traceable'])
        print('  └ 不可追溯: %d' % r['untraceable'])
        print('  可追溯率  : %.2f%%' % r['trace_rate_pct'])
        print('  ★ 判定    : %s' % r['verdict'])
        if r['untraceable_items']:
            print('-' * 62)
            print('  ★ 不可追溯项(★ 按三分纪律 ⇒ 应降级为 UNVERIFIED,不得 PASS):')
            for it in r['untraceable_items'][:25]:
                print('    L%-5d [%s] %s' % (it['claim_line'], it['kind'], it['value']))
            if len(r['untraceable_items']) > 25:
                print('    … 另 %d 项' % (len(r['untraceable_items']) - 25))
        print('=' * 62)

    return 0 if r['untraceable'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
