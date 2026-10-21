#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""easyocr 补充OCR 失败的证明材料"""
import os, sys
from pathlib import Path

DOC_DIR = Path(r"D:/hermes/hermes-data/profiles/qqbot4/cache/documents")
OUT_DIR = Path(r"D:/hermes/hermes-data/profiles/qqbot4/cache/ocr")

FAILED_HASHES = {
    "03989eb1cb36", "1071fa51a13d", "20af0058608f", "3d9fe79f654e",
    "45c90c182431", "4b7250097f58", "5dd045d9c0d7", "8b808147a55b",
    "fcd342ab216e", "de26b9445559", "bf82ed850a97", "3cebee30f76a", "f15a88694481",
}

def main():
    import easyocr
    reader = easyocr.Reader(["ch_sim", "en"], gpu=False, verbose=False)
    done, failed = 0, 0
    for doc in sorted(DOC_DIR.iterdir()):
        if not doc.is_file():
            continue
        name = doc.name
        if not name.startswith("doc_"):
            continue
        hash_part = name.split("_")[1] if len(name.split("_")) > 1 else None
        if hash_part not in FAILED_HASHES:
            continue
        out_txt = OUT_DIR / f"img_{hash_part}.txt"
        print(f"[{done+failed+1}] {name}")
        try:
            if doc.suffix.lower() == ".pdf":
                import fitz
                pdf = fitz.open(doc)
                text = ""
                for i, page in enumerate(pdf):
                    pix = page.get_pixmap(dpi=200)
                    img_tmp = OUT_DIR / f"_tmp_{hash_part}_{i}.png"
                    pix.save(img_tmp)
                    res = reader.readtext(str(img_tmp), detail=0, paragraph=True)
                    text += "\n".join(res) + "\n"
                    img_tmp.unlink(missing_ok=True)
            else:
                res = reader.readtext(str(doc), detail=0, paragraph=True)
                text = "\n".join(res)
            out_txt.write_text(text, encoding="utf-8")
            if len(text.strip()) > 5:
                done += 1
                print(f"  ✓ {len(text)} chars")
            else:
                failed += 1
                print(f"  ✗ 内容过少")
        except Exception as e:
            failed += 1
            print(f"  ✗ {e}")
    print(f"\neasyocr完成: 成功{done} 失败{failed}")

if __name__ == "__main__":
    main()
