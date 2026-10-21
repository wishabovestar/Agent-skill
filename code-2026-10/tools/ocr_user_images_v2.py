#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对用户实际图片运行OCR管道 - 修正版"""
import sys
sys.path = [p for p in sys.path if "hermes-agent" not in p]

import os
import json
from pathlib import Path

# 设置自定义tessdata路径（中文数据）
os.environ["TESSDATA_PREFIX"] = os.path.expanduser("~/tessdata_custom")
import pytesseract
# 让pytesseract使用我们的自定义路径
pytesseract.pytesseract.tesseract_cmd = r"C:/Program Files/Tesseract-OCR/tesseract.exe"

from ocr_pipeline import ChartOCRPipeline

IMG1 = r"D:\Program Data\We Chat\xwechat_files\wxid_gi4t5c2ng82m41_4faa\temp\RWTemp\2026-07\503bfebef3adc31e82057dec6aa402bd\0027c51ba222caea00123beb1553a227.jpg"
IMG2 = r"D:\Program Data\We Chat\xwechat_files\wxid_gi4t5c2ng82m41_4faa\temp\RWTemp\2026-07\503bfebef3adc31e82057dec6aa402bd\868d81ff0207f11300b73041fadf4130.jpg"

OUTPUT_DIR = Path(__file__).resolve().parent

def process_image(img_path, label, lang="chi_sim+eng"):
    print(f"\n{'█'*60}")
    print(f"█  处理图片 {label}: {Path(img_path).name} (lang={lang})")
    print(f"{'█'*60}")
    
    pipeline = ChartOCRPipeline(scale_factor=2.0, lang=lang, verbose=True)
    result = pipeline.run(img_path)
    
    # 保存结果
    out_json = OUTPUT_DIR / f"ocr_user_{label}_result.json"
    out_txt = OUTPUT_DIR / f"ocr_user_{label}_report.txt"
    
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write(f"=== 图片 {label} OCR结果 (lang={lang}) ===\n\n")
        f.write("--- 全文 ---\n")
        f.write(result["ocr"]["merged_text"])
        f.write("\n\n--- 结构化数据 ---\n")
        for k, v in result["structured_data"].items():
            f.write(f"  {k}: {v}\n")
        f.write(f"\n--- 领域纠错 ({result['corrections']['count']}处) ---\n")
        corrections = result["corrections"].get("applied", result["corrections"].get("details", []))
        for c in corrections:
            f.write(f"  {c}\n")
        f.write(f"\n--- 置信度 ---\n")
        f.write(f"  OCR综合置信度: {result['ocr']['overall_confidence']:.1f}%\n")
        f.write(f"  质量评分: {result['quality_report']['total_score']:.1f}/100\n")
        f.write(f"  等级: {result['quality_report']['grade']}\n")
    
    print(f"\n[输出] 图片{label} OCR结果已保存")
    print(f"  JSON: {out_json}")
    print(f"  报告: {out_txt}")
    
    return result

# 先用中英文混合处理
print("="*60)
print("先用 chi_sim+eng 处理两张图片")
print("="*60)

r1 = process_image(IMG1, "1", lang="chi_sim+eng")

# 检查tesseract是否支持chi_sim
import pytesseract as pt
langs = pt.get_languages()
print(f"\n可用语言: {langs}")

if "chi_sim" in langs:
    r2 = process_image(IMG2, "2", lang="chi_sim+eng")
else:
    print("\n⚠ chi_sim 不可用，用 eng 处理图片2")
    r2 = process_image(IMG2, "2", lang="eng")

# 汇总
print(f"\n{'='*60}")
print(f"  两张图片OCR完成！")
print(f"{'='*60}")

for label, r in [("1", r1), ("2", r2)]:
    print(f"\n--- 图片{label} OCR结果 ---")
    text = r["ocr"]["merged_text"]
    print(f"  质量评分: {r['quality_report']['total_score']:.1f}/100 ({r['quality_report']['grade']})")
    print(f"  置信度: {r['ocr']['overall_confidence']:.1f}%")
    print(f"  文本长度: {len(text)} 字")
    print(f"  文本预览 (前800字):")
    print(text[:800])
