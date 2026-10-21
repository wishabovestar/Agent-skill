#!/usr/bin/env python3
"""PaddleOCR wrapper for technical drawing OCR"""
import json, sys
from paddleocr import PaddleOCR
from PIL import Image

ocr = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False, use_gpu=False)

def paddle_ocr(img_path):
    result = ocr.ocr(img_path, cls=True)
    lines = []
    if result and result[0]:
        for item in result[0]:
            box = item[0]
            text = item[1][0]
            conf = item[1][1]
            y_center = (box[0][1] + box[2][1]) / 2
            x_center = (box[0][0] + box[2][0]) / 2
            lines.append({"y": round(y_center), "x": round(x_center), "text": text, "conf": round(conf, 3)})
    lines.sort(key=lambda x: (x["y"], x["x"]))
    return lines

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python paddle_ocr.py <图片路径>')
        sys.exit(1)
    result = paddle_ocr(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
