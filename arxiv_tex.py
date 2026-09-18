#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""arxiv_tex.py — 取 arXiv 论文的【TeX 源码】而非 PDF(借鉴 Karpathy read-arxiv-paper)

★ 来源(r1190): karpathy/nanochat 的 `.claude/skills/read-arxiv-paper/SKILL.md`:
    "The goal is to fetch the **TeX Source** of the paper (**not the PDF!**)"

★ 本机动机(🟢 实测):
    · Dream-RSI 那份 PDF 让 read_file 报 `NeedsOcrError: page 24` ⇒ 只能降级 pymupdf
    · 同一篇:PDF 抽取 106,454 字符 vs TeX 86,081 字符 ⇒ ★ TeX 更短但信息更全
    · PDF 里有 **1,040 行孤立页码**噪声;TeX 里 0
    · TeX 独有:tikzpicture 5(图的构造代码)· equation/align 13 · label 24 · \\ref 14

功能:
    1. 归一化 URL(/abs/、/pdf/、裸 id、带版本 ⇒ 统一成 id)
    2. 下载 https://arxiv.org/src/<id> (gzip) 到缓存(★ 已存在则不重下)
    3. 解包
    4. ★ 定位 entrypoint(\\documentclass 所在的主 .tex)
    5. ★ 递归展开 \\input / \\include(可选)
    6. 汇总成单个文本(供阅读),并给结构统计

用法:
    python arxiv_tex.py 2609.14858                 # 下载+解包+汇总
    python arxiv_tex.py 2609.14858 --stats         # 只给结构统计
    python arxiv_tex.py 2609.14858 --flatten       # 展开 \\input 后输出单文件
    python arxiv_tex.py --id-file ids.txt          # 批量(★ 内置间隔)
"""
import argparse
import glob
import gzip
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CACHE = os.path.join(os.path.expanduser("~"), ".cache", "arxiv_tex")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
DELAY = 3.0   # ★ 批量下载间隔(秒), 保守避让

RE_ID = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")
RE_INPUT = re.compile(r"\\(?:input|include)\s*\{([^}]+)\}")


def norm_id(s):
    """归一化: 接受 URL / 裸 id / 带版本 ⇒ 返回 (base_id, version or '')"""
    m = RE_ID.search(s or "")
    if not m:
        return None, None
    return m.group(1), (m.group(2) or "")


def fetch_src(arxiv_id, force=False):
    """下载 /src/ 到缓存。返回 (tar_path, from_cache)"""
    os.makedirs(CACHE, exist_ok=True)
    tar = os.path.join(CACHE, "%s.tar.gz" % arxiv_id)
    if os.path.exists(tar) and os.path.getsize(tar) > 0 and not force:
        return tar, True
    url = "https://arxiv.org/src/%s" % arxiv_id
    # 用 curl(本机既有依赖), 走既有代理策略
    cmd = ["curl", "-sL", "--max-time", "120", "-A", UA, "-o", tar, url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=140)
        if r.returncode != 0 or not os.path.exists(tar) or os.path.getsize(tar) == 0:
            return None, False
    except Exception:
        return None, False
    return tar, False


def unpack(tar, arxiv_id):
    """解包到 CACHE/<id>/。支持 .tar.gz 与【单文件 .tex.gz】(arXiv 两种形态)"""
    dst = os.path.join(CACHE, arxiv_id)
    if os.path.isdir(dst) and glob.glob(os.path.join(dst, "**", "*.tex"), recursive=True):
        return dst
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(dst, exist_ok=True)
    # 先试 tar
    try:
        with tarfile.open(tar, "r:*") as tf:
            tf.extractall(dst)
        if glob.glob(os.path.join(dst, "**", "*.tex"), recursive=True):
            return dst
    except Exception:
        pass
    # 再试【单个 gzip 压缩的 .tex】—— arXiv 常见
    try:
        with gzip.open(tar, "rb") as f:
            data = f.read()
        io.open(os.path.join(dst, "main.tex"), "wb").write(data)
        return dst
    except Exception:
        pass
    return dst


def find_entrypoint(root):
    """★ 定位主 .tex: 含 \\documentclass 的那个"""
    cands = []
    for p in glob.glob(os.path.join(root, "**", "*.tex"), recursive=True):
        try:
            t = io.open(p, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        if "\\documentclass" in t:
            cands.append((len(t), p))
    if not cands:
        return None
    cands.sort(reverse=True)
    return cands[0][1]


def flatten(tex_path, seen=None, depth=0):
    """★ 递归展开 \\input / \\include"""
    if seen is None:
        seen = set()
    if depth > 8 or tex_path in seen or not os.path.exists(tex_path):
        return ""
    seen.add(tex_path)
    d = os.path.dirname(tex_path)
    out = []
    txt = io.open(tex_path, encoding="utf-8", errors="replace").read()
    # 按 \\input 切段, 递归拼接
    pos = 0
    for m in RE_INPUT.finditer(txt):
        out.append(txt[pos:m.start()])
        tgt = m.group(1).strip()
        for cand in (tgt, tgt + ".tex", os.path.join(d, tgt), os.path.join(d, tgt + ".tex")):
            if os.path.exists(cand):
                out.append(flatten(cand, seen, depth + 1))
                break
        pos = m.end()
    out.append(txt[pos:])
    return "".join(out)


STAT_PATS = [
    ("tikzpicture(图的构造代码)", r"begin\{tikzpicture\}"),
    ("figure 环境", r"begin\{figure"),
    ("equation/align", r"begin\{(?:equation|align|gather)"),
    ("label", r"\\label\{"),
    ("\\ref 交叉引用", r"\\ref\{"),
    ("\\cite", r"\\cite\{"),
    ("tabular 表格", r"begin\{tabular"),
    ("\\newcommand", r"\\newcommand"),
    ("\\input/\\include", r"\\(?:input|include)\s*\{"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("id_or_url", nargs="?")
    ap.add_argument("--id-file", help="每行一个 id")
    ap.add_argument("--stats", action="store_true", help="只给结构统计")
    ap.add_argument("--flatten", action="store_true", help="展开 \\input 后输出单文件")
    ap.add_argument("--out", help="输出文件(flatten/stats 用)")
    ap.add_argument("--force", action="store_true", help="忽略缓存重下")
    a = ap.parse_args()

    ids = []
    if a.id_file:
        ids = [l.strip() for l in io.open(a.id_file, encoding="utf-8") if l.strip()]
    elif a.id_or_url:
        ids = [a.id_or_url]
    else:
        ap.print_help()
        return 1

    for i, raw in enumerate(ids):
        aid, ver = norm_id(raw)
        if not aid:
            print("  🔴 无法解析: %s" % raw[:60])
            continue
        tag = aid + (ver or "")
        print("─" * 74)
        print("  %s" % tag)
        if i:
            time.sleep(DELAY)          # ★ 批量间隔

        tar, cached = fetch_src(aid + (ver or ""), a.force)
        if not tar:
            print("     🔴 /src/ 取失败(可能无 TeX 源; 也可能是扫描件)")
            continue
        print("     tar: %.1f KB %s" % (os.path.getsize(tar) / 1024.0,
                                        "(缓存)" if cached else "(新下载)"))

        root = unpack(tar, aid + (ver or ""))
        texs = glob.glob(os.path.join(root, "**", "*.tex"), recursive=True)
        ep = find_entrypoint(root)
        print("     .tex 文件: %d | entrypoint: %s" % (len(texs), os.path.basename(ep) if ep else "未找到"))
        if not ep:
            continue

        body = flatten(ep) if a.flatten else "".join(
            io.open(p, encoding="utf-8", errors="replace").read() for p in texs)
        full = ("".join(io.open(p, encoding="utf-8", errors="replace").read() for p in texs)
                if a.flatten else body)
        print("     正文展开: %d 字符" % len(body))

        if a.stats or not a.flatten:
            print("     ── 结构统计(TeX 独有)──")
            for name, pat in STAT_PATS:
                n = len(re.findall(pat, full))
                if n:
                    print("        %-26s %4d" % (name, n))

        if a.out:
            # ★ 修正:批量时若各 id 共用同一 --out 会互相覆盖(r1190 实测)。
            #   规则:单 id ⇒ 用原路径;多 id ⇒ 在文件名里插入 id。
            outp = a.out
            if len(ids) > 1:
                d, b = os.path.split(a.out)
                stem, ext = os.path.splitext(b)
                outp = os.path.join(d or ".", "%s_%s%s" % (stem, tag, ext))
            io.open(outp, "w", encoding="utf-8", newline="\n").write(body)
            print("     → 写出 %s (%d 字符)" % (outp, len(body)))

    print("─" * 74)
    print("  缓存目录: %s" % CACHE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
