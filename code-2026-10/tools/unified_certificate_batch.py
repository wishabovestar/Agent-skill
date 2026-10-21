#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
证明材料统一脱敏批量处理
========================
处理范围:
  1. qqbot4/cache/ocr/*.txt — 54个证明材料的OCR文本
  2. 微信原始缓存 docx (薪酬证明/录用清单) + PDF (银行流水)
  3. 图纸PDF文本层 (mybot/qqbot3 613-39859-02)

输出:
  D:/hermes/analysis/certificate_cache/sanitized/   脱敏文本
  D:/hermes/analysis/certificate_cache/batch_report_*.json  汇总报告
  D:/hermes/analysis/certificate_cache/filename_map.json    文件名映射
"""
import sys, json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))
from certificate_privacy_guard import create_session, check_for_leaks

CACHE = Path(r"D:/hermes/analysis/certificate_cache")
SANITIZED = CACHE / "sanitized"
SANITIZED.mkdir(parents=True, exist_ok=True)

def extract_docx(path: Path) -> str:
    from docx import Document
    doc = Document(path)
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)

def extract_pdf(path: Path) -> str:
    import fitz
    doc = fitz.open(path)
    return "\n".join(page.get_text() for page in doc)

def main():
    session_id, cipher, mapper, tokenizer = create_session(f"unified_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    results = []

    # 1. OCR文本
    ocr_dir = Path(r"D:/hermes/hermes-data/profiles/qqbot4/cache/ocr")
    for f in sorted(ocr_dir.glob("img_*.txt")):
        text = f.read_text(encoding="utf-8", errors="replace")
        tokenized = tokenizer.tokenize(text)
        out = SANITIZED / f"{f.stem}_sanitized.txt"
        out.write_text(tokenized, encoding="utf-8")
        leaks = check_for_leaks(tokenized)
        results.append({"source": "ocr", "file": f.name, "orig": len(text), "safe": len(tokenized), "leaks": leaks, "out": str(out)})

    # 2. 微信docx + pdf
    wx_dir = Path(r"D:/Program Data/We Chat/xwechat_files/wxid_gi4t5c2ng82m41_4faa/msg/file")
    wx_targets = []
    for d in ["2026-06", "2026-07", "2026-08"]:
        p = wx_dir / d
        if not p.exists():
            continue
        for f in p.iterdir():
            n = f.name
            if "周雄" in n or "流水" in n or "交易" in n or "证明" in n or "录用" in n:
                wx_targets.append(f)
    for f in sorted(set(wx_targets)):
        try:
            if f.suffix.lower() == ".docx":
                text = extract_docx(f)
            elif f.suffix.lower() == ".pdf":
                text = extract_pdf(f)
            else:
                continue
            tokenized = tokenizer.tokenize(text)
            out = SANITIZED / f"wx_{f.stem[:40]}_sanitized.txt"
            out.write_text(tokenized, encoding="utf-8")
            leaks = check_for_leaks(tokenized)
            results.append({"source": "wechat", "file": f.name, "orig": len(text), "safe": len(tokenized), "leaks": leaks, "out": str(out)})
        except Exception as e:
            results.append({"source": "wechat", "file": f.name, "error": str(e)})

    # 3. 图纸PDF文本层（仅文本层，扫描页由drawing_privacy_guard管道负责）
    for pdf_path in [Path(r"D:/hermes/hermes-data/profiles/mybot/cache/documents/doc_8904b387f583_613-39859-02-CELL_ASSY.pdf")]:
        if pdf_path.exists():
            text = extract_pdf(pdf_path)
            if len(text.strip()) > 50:
                tokenized = tokenizer.tokenize(text)
                out = SANITIZED / "drawing_613_39859_text_sanitized.txt"
                out.write_text(tokenized, encoding="utf-8")
                results.append({"source": "drawing", "file": pdf_path.name, "orig": len(text), "safe": len(tokenized), "leaks": check_for_leaks(tokenized), "out": str(out)})

    mapper.save_mapping(session_id)
    report = {"session": session_id, "generated": datetime.now().isoformat(),
              "total": len(results), "total_stats": tokenizer.stats, "results": results}
    report_file = CACHE / f"unified_report_{session_id}.json"
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # 汇总打印
    print(f"会话: {session_id}")
    print(f"文件总数: {len(results)}")
    print(f"总统计: {tokenizer.stats}")
    leaky = [r for r in results if r.get("leaks")]
    errs = [r for r in results if r.get("error")]
    print(f"泄漏: {len(leaky)}, 错误: {len(errs)}")
    for r in leaky:
        print(f"  ⚠ LEAK: {r['file']} → {r['leaks']}")
    for r in errs:
        print(f"  ✗ ERR: {r['file']} → {r['error']}")
    print(f"报告: {report_file}")

if __name__ == "__main__":
    main()
