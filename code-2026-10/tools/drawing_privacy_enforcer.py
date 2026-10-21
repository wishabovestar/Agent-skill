#!/usr/bin/env python3
"""
Hermes 图纸外发强制脱敏包装器 (Drawing Privacy Enforcement)
============================================================
所有图纸相关文本在外发前必须经过此管道:
  1. 检查泄漏 (图号/客户/人名/尺寸/公差)
  2. 若检出泄漏 → 自动脱敏 (v1元数据 + v2值Token化)
  3. 输出安全文本 + 会话映射表

用法:
  python drawing_privacy_enforcer.py --text "图纸文本..."     # 单条文本脱敏
  python drawing_privacy_enforcer.py --file <path>            # 文件脱敏
  python drawing_privacy_enforcer.py --check "文本"           # 只检查不脱敏

集成: pdf-reader / 3d-model-agent / engineering-drawing-ocr 工作流外发前强制调用
"""
import sys, os, json, subprocess, re
from pathlib import Path

GUARD = Path(r"D:/hermes/analysis/drawing_privacy_guard.py")
DRAWING_PATTERNS = {
    "图号": re.compile(r"\b\d{3,4}-\d{4,6}(?:-\d{2})?\b"),
    "公司": re.compile(r"Apple|Tesla|Samsung|LG|CATL|BYD|Panasonic", re.I),
    "人名": re.compile(r"\b(?:John|Jane|Michael|Robert|David|James|William|Mary)\s+[A-Z][a-z]+\b|\bDesigner\b|\bEngineer\b", re.I),
    "直径": re.compile(r"[ØΦ]\d+\.?\d*"),
    "尺寸": re.compile(r"\b\d{2,3}\.\d{3}\b"),  # 10.600 / 4.510 格式
}

def check_leaks(text: str) -> list[str]:
    """本地快速泄漏检测"""
    leaks = []
    for name, pattern in DRAWING_PATTERNS.items():
        if pattern.search(text):
            leaks.append(name)
    # 额外: 已知图号
    if "613-39859" in text or "CELL_ASSY" in text:
        leaks.append("图号(已知)")
    return leaks

def enforce(text: str, session_id: str = None) -> dict:
    """强制脱敏管道"""
    leaks = check_leaks(text)
    if not leaks:
        return {"leaked": False, "text": text, "leaks": [], "session": session_id}

    # 有泄漏 → 调用主脱敏引擎
    cmd = [sys.executable, str(GUARD), "--pipeline", text]
    if session_id:
        cmd = [sys.executable, str(GUARD), "--pipeline", text, "--session", session_id]
    
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, encoding="utf-8")
        output = r.stdout
        # 提取Token化文本
        tokenized = re.search(r"Token化文本:\n(.+)", output)
        session = re.search(r"会话ID: (\S+)", output)
        result_text = tokenized.group(1) if tokenized else text
        
        # 兜底: 强制清理主引擎未识别的人名模式 ("by John Smith", "John Smith, Apple")
        result_text = re.sub(
            r"\b(?:by|By)\s+(?:John|Jane|Michael|Robert|David|James|William|Mary|Thomas|Richard|Charles|Joseph)\s+[A-Z][a-z]+\b",
            "[Designer]", result_text)
        result_text = re.sub(
            r"\b(?:John|Jane|Michael|Robert|David|James|William|Mary|Thomas|Richard|Charles|Joseph)\s+[A-Z][a-z]+\b",
            "[Designer]", result_text)
        
        return {
            "leaked": True,
            "text": result_text,
            "leaks": leaks,
            "session": session.group(1) if session else session_id,
            "raw_output": output[:500],
        }
    except Exception as e:
        return {"leaked": True, "text": text, "leaks": leaks, "error": str(e)}

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return

    mode = sys.argv[1]
    if mode == "--text":
        text = sys.argv[2]
        session = sys.argv[4] if len(sys.argv) > 4 and sys.argv[3] == "--session" else None
        result = enforce(text, session)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif mode == "--check":
        text = sys.argv[2]
        leaks = check_leaks(text)
        print(json.dumps({"leaks": leaks, "safe": not leaks}, ensure_ascii=False))
    elif mode == "--file":
        path = Path(sys.argv[2])
        text = path.read_text(encoding="utf-8")
        result = enforce(text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(__doc__)

if __name__ == "__main__":
    main()
