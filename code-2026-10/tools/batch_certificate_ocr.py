#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量OCR 证明材料 → 输出txt到指定目录 (图片:tesseract, PDF:pymupdf)"""
import os, sys, subprocess
from pathlib import Path

DOC_DIR = Path(r"D:/hermes/hermes-data/profiles/qqbot4/cache/documents")
OUT_DIR = Path(r"D:/hermes/hermes-data/profiles/qqbot4/cache/ocr")
TESSERACT = r"C:/Program Files/Tesseract-OCR/tesseract.exe"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def ocr_image(img_path: Path, out_txt: Path) -> bool:
    cmd = [TESSERACT, str(img_path), str(out_txt.with_suffix("")), "-l", "chi_sim+eng", "--psm", "3"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        return out_txt.exists() and out_txt.stat().st_size > 10
    except Exception as e:
        print(f"  OCR失败 {img_path.name}: {e}")
        return False

def ocr_pdf(pdf_path: Path, out_txt: Path) -> bool:
    try:
        import fitz
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        # 若PDF无文本层（扫描件），渲染页面为图片后OCR
        if len(text.strip()) < 20:
            text = ""
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=200)
                img_path = out_txt.with_suffix(f".p{i}.png")
                pix.save(img_path)
                tmp = out_txt.with_suffix(f".p{i}_tmp")
                subprocess.run([TESSERACT, str(img_path), str(tmp), "-l", "chi_sim+eng", "--psm", "3"],
                               capture_output=True, timeout=120)
                if tmp.exists():
                    text += tmp.read_text(encoding="utf-8", errors="replace") + "\n"
                    tmp.unlink(missing_ok=True)
                img_path.unlink(missing_ok=True)
        out_txt.write_text(text, encoding="utf-8")
        return len(text.strip()) > 10
    except Exception as e:
        print(f"  PDF失败 {pdf_path.name}: {e}")
        return False

def main():
    # 已有OCR的hash跳过
    existing = set()
    for f in OUT_DIR.glob("img_*.txt"):
        existing.add(f.stem.replace("img_", ""))

    done, failed = 0, 0
    for doc in sorted(DOC_DIR.iterdir()):
        if not doc.is_file():
            continue
        # doc_<hash>_name.ext → hash
        name = doc.name
        hash_part = None
        if name.startswith("doc_"):
            hash_part = name.split("_")[1] if len(name.split("_")) > 1 else None
        if hash_part and hash_part in existing:
            continue
        out_txt = OUT_DIR / f"img_{hash_part}.txt"
        print(f"[{done+failed+1}] {doc.name}")
        if doc.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
            ok = ocr_image(doc, out_txt)
        elif doc.suffix.lower() == ".pdf":
            ok = ocr_pdf(doc, out_txt)
        else:
            print(f"  跳过: 不支持类型 {doc.suffix}")
            continue
        if ok:
            done += 1
        else:
            failed += 1
            print(f"  ✗ 失败: {doc.name}")
    print(f"\n完成: 成功{done} 失败{failed}")

if __name__ == "__main__":
    main()
