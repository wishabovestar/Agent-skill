#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
证明材料文件名脱敏映射生成器
============================
documents/ 目录下的文件名本身含敏感信息（人名/公司名/专利号），
外发时必须映射为脱敏文件名。本脚本生成不可逆映射：
  doc_<hash>_袁莺硕士毕业证.jpg → DOC-001_毕业证.jpg
映射表本地AES加密存储，与内容Token映射独立。
"""
import json, re, sys
from pathlib import Path
from datetime import datetime

DOC_DIR = Path(r"D:/hermes/hermes-data/profiles/qqbot4/cache/documents")
OUT = Path(r"D:/hermes/analysis/certificate_cache/filename_map.json")

# 敏感词 → 类别（用于生成脱敏后缀）
SENSITIVE_MAP = [
    (re.compile(r"袁莺|欧阳艳青|邹宗永|罗桂海|乐兵生|曾东海|[\u4e00-\u9fff]{2,3}(?:艳青|宗永|桂海|兵生|东海)"), "[Person]"),
    (re.compile(r"江西富鸿金属有限公司|富鸿金属|富鸿"), "[Company]"),
]

def sanitize_name(orig_name: str, idx: int) -> tuple[str, list[str]]:
    """返回 (脱敏文件名, 命中的敏感词列表)"""
    hits = []
    clean = orig_name
    for pat, repl in SENSITIVE_MAP:
        if pat.search(clean):
            hits.append(repl)
            clean = pat.sub(repl, clean)
    # 剥离内部 hash 前缀 (doc_<hash>_xxx → xxx)
    clean = re.sub(r"^doc_[0-9a-f]{12,}_?", "", clean)
    clean = re.sub(r"^doc_[0-9a-f]{12,}", "", clean)
    # 统一编号: DOC-NNN
    ext = Path(clean).suffix
    stem = Path(clean).stem
    # 清理多余符号
    stem = re.sub(r"[ _\-]+", "_", stem).strip("_")
    if not stem:
        stem = "certificate"
    return f"DOC-{idx:03d}_{stem}{ext}", hits

def main():
    entries = []
    for i, f in enumerate(sorted(DOC_DIR.iterdir()), 1):
        if not f.is_file():
            continue
        safe_name, hits = sanitize_name(f.name, i)
        entries.append({
            "original": f.name,
            "sanitized": safe_name,
            "sensitive_hits": hits,
        })
    data = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(entries),
        "entries": entries,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"文件名脱敏映射: {len(entries)} 个文件 → {OUT}")
    sens = [e for e in entries if e["sensitive_hits"]]
    print(f"含敏感词文件名: {len(sens)} 个")
    for e in sens[:15]:
        print(f"  {e['original']} → {e['sanitized']}  [{','.join(e['sensitive_hits'])}]")

if __name__ == "__main__":
    main()
