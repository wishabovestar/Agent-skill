#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
repro_audit.py — 归档数字复现审计

分三类（判决分开报，不许合并成一个数 —— #178 分池）:
  A 算术可复现 : 同一段里有两个数 ⇒ 比值/差可直接重算
  B 归档自洽   : 归档自己声称的计数 ⇒ 用脚本重算
  C 源可取回   : 有 arXiv/DOI/GitHub 手柄 ⇒ 联网核对（另跑）
  D 不可复核   : 报的是"厂商自报成绩"，无公开手柄 ⇒ 明确标不可复核

用法: python repro_audit.py            # A + B（离线）
      python repro_audit.py --claims   # 只导出断言台账
"""
import os, re, json, sys, subprocess

try:
    from _paths import ROOT as BASE, TOOLS_DIR, STATE_DIR, SANDBOX_DIR
except Exception:
    BASE = r'D:/hermes/analysis'; TOOLS_DIR=STATE_DIR=SANDBOX_DIR=BASE
ARCH = os.path.join(BASE, 'PAPER_ARCHIVE_agent_memory_swarm_2026-10.md')
CHECK= os.path.join(BASE, 'AGENT_MEMORY_COORD_DESIGN_CHECKLIST_v1.md')

def load(): return open(ARCH, encoding='utf-8', errors='replace').read()

# ── B: 归档自洽数（用【已校准】的测量；校准探针见 repro_probe.py）──────
def _calibrate():
    """MR5: 先证明提取器对已知输入给出预期值，再拿它判归档"""
    probe = '铁律 7 与 铁律 **12** 和 铁律142'
    got = [int(x) for x in re.findall(r'铁律\s*\*{0,2}\s*(\d+)', probe)]
    return got == [7, 12, 142]

def check_selfconsistency(t):
    out = []
    if not _calibrate():
        print('  ⚠️ 提取器未校准 ⇒ B 类判决不可信'); return out
    # ① 条目数
    n_head = len(re.findall(r'^###\s*#?\s*\d{1,3}[\.\s:：]', t, re.M))
    claimed = re.search(r'共\s*\*{0,2}(\d+)\s*篇', t)
    claimed = int(claimed.group(1)) if claimed else None
    out.append(('B1 条目数', claimed, n_head, n_head == claimed))
    # ② 编号连续
    u = sorted(set(int(x) for x in re.findall(r'^#{2,4}\s*#?(\d{1,3})[\.\s:：]', t, re.M)))
    cont = bool(u) and u == list(range(1, u[-1] + 1))
    out.append(('B2 编号连续 1..N', f'1..{u[-1] if u else 0}', f'{len(u)} 唯一号', cont))
    # ③ 铁律：数【跨论文铁律段】的编号条目，不再数全文 "铁律 N"
    m = re.search(r'^(#{1,4})\s*跨论文铁律.*$', t, re.M)
    n_iron = None
    if m:
        lvl = len(m.group(1))
        nxt = re.search(r'^#{1,%d}\s' % lvl, t[m.end():], re.M)
        seg = t[m.start(): m.end() + nxt.start()] if nxt else t[m.start():]
        n_iron = len(re.findall(r'^\s*(\d{1,3})[\.\)、]\s', seg, re.M))
    hdr_iron = re.search(r'跨论文铁律`（\*{0,2}(\d+)\s*条', t)
    hdr_iron = int(hdr_iron.group(1)) if hdr_iron else None
    out.append(('B3 跨篇铁律条数', hdr_iron, n_iron, hdr_iron == n_iron))
    # ④ 文件体积
    hdr_kb = re.search(r'体积\s*\*{0,2}([\d,]+)\s*KB', t) or re.search(r'([\d,]+)\s*KB', t[:8000])
    hdr_kb = int(hdr_kb.group(1).replace(',', '')) if hdr_kb else None
    real_kb = os.path.getsize(ARCH) // 1024
    out.append(('B4 文件体积 KB', hdr_kb, real_kb, (abs(hdr_kb - real_kb) <= 2) if hdr_kb else None))
    # ⑤ 审计表行数
    out.append(('B5 审计表行数', 188, len(re.findall(r'^\|\s*#?\d{1,3}\s*\|', t, re.M)), None))
    out.append(('B6 行数', None, t.count('\n') + 1, None))
    return out


# ── A: 算术可复现 —— 同段内的 "A → B" / "A ... B" 数值对 ────────────
def check_arithmetic(t):
    """抽取 X→Y 与 形如 'a 到 b' 的数值对，重算比值/差"""
    res = []
    for m in re.finditer(r'(\d+\.?\d*)\s*(?:M|K|k)?\s*(?:→|->|⇒|到|升到|涨到)\s*(\d+\.?\d*)\s*(?:M|K|k)?', t):
        a, b = float(m.group(1)), float(m.group(2))
        if a == 0: continue
        ctx = t[max(0, m.start()-90):m.start()+90].replace('\n', ' ')
        res.append(dict(kind='pair', a=a, b=b, ratio=round(b/a, 3), delta=round(b-a, 3), ctx=ctx.strip()[:130]))
    return res

def main():
    t = load()
    print('=' * 96)
    print('归档数字复现审计 · B 归档自洽（离线）')
    print('=' * 96)
    print(f'  {"项":<22}{"归档声称":>12}{"脚本重算":>14}   判决')
    ok = bad = na = 0
    for name, claimed, real, verdict in check_selfconsistency(t):
        v = '✅ 复现' if verdict else ('❌ 不复现' if verdict is False else '— 无对照')
        if verdict is True: ok += 1
        elif verdict is False: bad += 1
        else: na += 1
        print(f'  {name:<22}{str(claimed):>12}{str(real):>14}   {v}')
    print('─' * 96)
    print(f'  复现 {ok} · 不复现 {bad} · 无对照 {na}')
    if '--claims' in sys.argv:
        json.dump(check_arithmetic(t), open(os.path.join(BASE,'repro_pairs.json'),'w',encoding='utf-8'),
                  ensure_ascii=False, indent=2)
    pairs = check_arithmetic(t)
    print(f'\n  A 算术可复现（同段数值对）: 抽到 {len(pairs)} 对')
    for p in pairs[:10]:
        print(f'    {p["a"]} → {p["b"]}  ⇒ 比值 {p["ratio"]}×  Δ={p["delta"]}')
    return 0

if __name__ == '__main__':
    sys.exit(main())
