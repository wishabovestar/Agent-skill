#!/usr/bin/env python3
"""多引擎OCR对比工具 — PaddleOCR + EasyOCR 双引擎"""
import json, sys, os

# ─── PaddleOCR ───
try:
    from paddleocr import PaddleOCR
    pg = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False, use_gpu=False)
    def paddle_ocr(img_path):
        r = pg.ocr(img_path, cls=True)
        lines = []
        if r and r[0]:
            for item in r[0]:
                box, (text, conf) = item[0], item[1]
                y = (box[0][1] + box[2][1]) / 2
                x = (box[0][0] + box[2][0]) / 2
                lines.append({"y": round(y), "x": round(x), "text": text, "conf": conf})
        lines.sort(key=lambda x: (x["y"], x["x"]))
        return lines
    PADDLE_OK = True
except:
    PADDLE_OK = False

# ─── EasyOCR ───
try:
    import easyocr
    eg = easyocr.Reader(['ch_sim', 'en'], gpu=False)
    def easy_ocr(img_path):
        r = eg.readtext(img_path)
        lines = []
        for box, text, conf in r:
            y = (box[0][1] + box[2][1]) / 2
            x = (box[0][0] + box[2][0]) / 2
            lines.append({"y": round(y), "x": round(x), "text": text, "conf": round(conf, 3)})
        lines.sort(key=lambda x: (x["y"], x["x"]))
        return lines
    EASY_OK = True
except:
    EASY_OK = False

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"用法: python {sys.argv[0]} <图片路径> [--engine paddle|easy|all]")
        sys.exit(1)
    
    engine = sys.argv[2] if len(sys.argv) > 2 else "all"
    img_path = sys.argv[1]
    if not os.path.exists(img_path):
        print(f"文件不存在: {img_path}")
        sys.exit(1)
    
    results = {}
    if engine in ("paddle", "all") and PADDLE_OK:
        results["paddle"] = paddle_ocr(img_path)
    if engine in ("easy", "all") and EASY_OK:
        results["easy"] = easy_ocr(img_path)
    
    print(json.dumps(results, ensure_ascii=False, indent=2))
