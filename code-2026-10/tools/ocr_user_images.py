#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对用户实际图片运行OCR管道"""
import sys
sys.path = [p for p in sys.path if "hermes-agent" not in p]

import json
from pathlib import Path

# 导入管道中的类
from ocr_pipeline import ChartOCRPipeline, ImagePreprocessor, MultiPassOCR, DomainCorrector

IMG1 = r"D:\Program Data\We Chat\xwechat_files\wxid_gi4t5c2ng82m41_4faa\temp\RWTemp\2026-07\503bfebef3adc31e82057dec6aa402bd\0027c51ba222caea00123beb1553a227.jpg"
IMG2 = r"D:\Program Data\We Chat\xwechat_files\wxid_gi4t5c2ng82m41_4faa\temp\RWTemp\2026-07\503bfebef3adc31e82057dec6aa402bd\868d81ff0207f11300b73041fadf4130.jpg"

OUTPUT_DIR = Path(__file__).resolve().parent

def process_image(img_path, label):
    print(f"\n{'█'*60}")
    print(f"█  处理图片 {label}: {Path(img_path).name}")
    print(f"{'█'*60}")
    
    pipeline = ChartOCRPipeline(scale_factor=2.0, lang="eng", verbose=True)
    result = pipeline.run(img_path)
    
    # 保存结果
    out_json = OUTPUT_DIR / f"ocr_user_{label}_result.json"
    out_txt = OUTPUT_DIR / f"ocr_user_{label}_report.txt"
    
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write(f"=== 图片 {label} OCR结果 ===\n\n")
        f.write("--- 全文 ---\n")
        f.write(result["ocr"]["merged_text"])
        f.write("\n\n--- 结构化数据 ---\n")
        for k, v in result["structured_data"].items():
            f.write(f"  {k}: {v}\n")
        f.write(f"\n--- 领域纠错 ({result['corrections']['count']}处) ---\n")
        for c in result["corrections"]["applied"]:
            f.write(f"  {c}\n")
        f.write(f"\n--- 置信度 ---\n")
        f.write(f"  OCR综合置信度: {result['ocr']['overall_confidence']:.1f}%\n")
        f.write(f"  质量评分: {result['quality_report']['total_score']:.1f}/100\n")
        f.write(f"  等级: {result['quality_report']['grade']}\n")
    
    print(f"\n[输出] 图片{label} OCR结果已保存")
    print(f"  JSON: {out_json}")
    print(f"  报告: {out_txt}")
    
    return result

# 处理两张图片
r1 = process_image(IMG1, "1")
r2 = process_image(IMG2, "2")

# 汇总
print(f"\n{'='*60}")
print(f"  两张图片OCR完成！")
print(f"{'='*60}")
print(f"\n图片1 质量评分: {r1['quality_report']['total_score']:.1f}/100 ({r1['quality_report']['grade']})")
print(f"图片2 质量评分: {r2['quality_report']['total_score']:.1f}/100 ({r2['quality_report']['grade']})")
print(f"\n图片1 文本预览 (前500字):")
print(r1["ocr"]["merged_text"][:500])
print(f"\n图片2 文本预览 (前500字):")
print(r2["ocr"]["merged_text"][:500])
