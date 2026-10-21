#!/usr/bin/env python3
"""
听澜 — 音频识别与通话报告生成 Agent
============================================
将通话录音(MP3/WAV/M4A)转录为文字，自动结构化整理为：
  摘要 → 待办事项 → 期限和内容 → 完整对话记录
支持中英文混杂语音识别。

用法:
  python tinglan.py call.mp3                        # 基本识别+报告
  python tinglan.py call.wav --lang zh              # 指定语言中文优先
  python tinglan.py call.m4a --output report.md     # 输出到文件
  python tinglan.py call.mp3 --verbose              # 显示详细过程
"""

import argparse
import json
import os
import re
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════
#  依赖管理 — 首次运行自动安装
# ═══════════════════════════════════════════════════════════
REQUIRED_PACKAGES = {
    "faster_whisper": "faster-whisper",
}

SILK_V3_DECODER_URL = "https://github.com/kn007/silk-v3-decoder/raw/master/silk_v3_decoder.exe"


def check_dependencies() -> bool:
    """检查并提示安装依赖"""
    missing = []
    for import_name, pkg_name in REQUIRED_PACKAGES.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg_name)
    
    # 检查 silk 解码器
    silk_decoder_ready = False
    for d in [os.path.join(os.path.dirname(__file__), "bin"),
              os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin"),
              os.path.expanduser("~/.hermes/bin")]:
        p = os.path.join(d, "silk_v3_decoder.exe") if sys.platform == "win32" else os.path.join(d, "silk_v3_decoder")
        if os.path.exists(p):
            silk_decoder_ready = True
            global SILK_DECODER_PATH
            SILK_DECODER_PATH = p
            break
    
    if missing:
        print("=" * 60)
        print("  ❌ 缺少语音识别依赖")
        print("=" * 60)
        print()
        for pkg in missing:
            print(f"    pip install {pkg}")
        print()
        print("  (如果pip报错，试试 pip3 或在 venv 中安装)")
        print("=" * 60)
        return False
    
    if not silk_decoder_ready:
        print("  ⚠️  SILK解码器未安装 (用于微信 .silk 语音)")
        print("     不影响普通 MP3/WAV/M4A 处理")
    
    return True


SILK_DECODER_PATH = ""


# ═══════════════════════════════════════════════════════════
#  音频预处理 (ffmpeg)
# ═══════════════════════════════════════════════════════════

def convert_to_wav(input_path: str, output_dir: str = "audio_cache") -> str:
    """用 ffmpeg 将任意音频转为 16kHz WAV (Whisper 标准输入)"""
    os.makedirs(output_dir, exist_ok=True)
    base = Path(input_path).stem
    ext = Path(input_path).suffix.lower()
    
    # ── SILK 格式（微信语音）特殊处理 ──
    if ext == ".silk":
        return _convert_silk_to_wav(input_path, output_dir)
    
    wav_path = os.path.join(output_dir, f"{base}_16k.wav")
    
    # 检查 ffmpeg
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("❌ 需要 ffmpeg: https://ffmpeg.org/download.html")
        print("   或: winget install ffmpeg")
        sys.exit(1)
    
    if os.path.exists(wav_path):
        print(f"  ⏩ 使用缓存: {wav_path}")
        return wav_path
    
    print(f"  🎵 转换音频: {Path(input_path).name} → 16kHz WAV")
    result = subprocess.run([
        "ffmpeg", "-i", input_path,
        "-ar", "16000",           # 采样率 16kHz
        "-ac", "1",               # 单声道
        "-sample_fmt", "s16",     # 16位PCM
        "-y",                     # 覆盖
        wav_path
    ], capture_output=True, text=True, timeout=300)
    
    if result.returncode != 0:
        print(f"  ❌ 转换失败: {result.stderr[:200]}")
        sys.exit(1)
    
    duration = _get_audio_duration(wav_path)
    print(f"  ✅ 转换完成: {duration//60}分{duration%60:02d}秒")
    return wav_path


def _get_audio_duration(wav_path: str) -> float:
    """获取音频时长(秒)"""
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
        wav_path
    ], capture_output=True, text=True, timeout=10)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0


# ── SILK 解码（微信语音）────────────────────────────

def _convert_silk_to_wav(silk_path: str, output_dir: str = "audio_cache") -> str:
    """将微信 SILK 语音转为 WAV（优先 pysilk，回退 silk_v3_decoder + ffmpeg）"""
    base = Path(silk_path).stem
    wav_path = os.path.join(output_dir, f"{base}_16k.wav")
    
    if os.path.exists(wav_path):
        print(f"  ⏩ 使用缓存: {wav_path}")
        return wav_path
    
    print(f"  🎵 解码 SILK (微信语音): {Path(silk_path).name}")
    
    # ── 方案A: pysilk (纯Python，已安装) ──
    try:
        import pysilk
        # pysilk 解码: pysilk.decode(input_path, output_path, sample_rate)
        pysilk.decode(silk_path, wav_path, 16000)
        if os.path.exists(wav_path):
            print(f"  ✅ pysilk 解码成功")
            return wav_path
    except Exception as e:
        print(f"  ⚠️  pysilk 解码失败: {e}")
    
    # ── 方案B: silk_v3_decoder (外部工具) ──
    decoder = SILK_DECODER_PATH
    if not decoder:
        for d in [os.path.join(Path(__file__).parent, "bin"),
                  os.path.expanduser("~/.hermes/bin"),
                  os.path.dirname(silk_path)]:
            cand = os.path.join(d, "silk_v3_decoder.exe" if sys.platform == "win32" else "silk_v3_decoder")
            if os.path.exists(cand):
                decoder = cand
                break
    
    if decoder:
        pcm_path = os.path.join(output_dir, f"{base}.pcm")
        result = subprocess.run([decoder, silk_path, pcm_path, "-2"],
                                capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            subprocess.run(["ffmpeg", "-f", "s16le", "-ar", "16000", "-ac", "1",
                          "-i", pcm_path, "-y", wav_path], capture_output=True, timeout=60)
            if os.path.exists(pcm_path):
                os.unlink(pcm_path)
            print(f"  ✅ silk_v3_decoder 解码完成")
            return wav_path
        print(f"  ❌ silk_v3_decoder 失败")
    
    # ── 方案C: ffmpeg 直接尝试 ──
    try:
        result = subprocess.run(["ffmpeg", "-i", silk_path, "-ar", "16000", "-ac", "1",
                               "-sample_fmt", "s16", "-y", wav_path],
                               capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and os.path.exists(wav_path):
            print(f"  ✅ ffmpeg 直接解码成功")
            return wav_path
    except:
        pass
    
    print("  ❌ 无法解码 SILK 文件")
    print("  已安装 pysilk 但仍失败，尝试: pip install --upgrade pysilk")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════
#  语音识别 (faster-whisper)
# ═══════════════════════════════════════════════════════════

def transcribe(wav_path: str, language: str = "auto",
               model_size: str = "medium", verbose: bool = False) -> Dict:
    """
    使用 faster-whisper 进行语音识别。
    
    model_size: tiny / base / small / medium / large-v2 / large-v3
    language: auto / zh / en / ja 等
    """
    from faster_whisper import WhisperModel
    
    # 选择模型
    model_name = model_size
    if language == "zh":
        model_name = f"{model_size}"  # 中文模型无需特殊指定
    
    print(f"  🧠 加载模型: {model_name} (首次运行会下载~1.5GB)")
    
    # 使用 CPU (INT8 量化加速)
    try:
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
    except Exception:
        # 回退到 float32
        model = WhisperModel(model_name, device="cpu", compute_type="float32")
    
    # 设置语言
    lang = None if language == "auto" else language
    
    print(f"  📝 开始识别...")
    segments, info = model.transcribe(wav_path, language=lang, beam_size=5,
                                      vad_filter=True,  # 自动滤除静音段
                                      vad_parameters=dict(min_silence_duration_ms=500))
    
    # 收集结果
    result = {
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "segments": [],
        "full_text": "",
    }
    
    texts = []
    for seg in segments:
        seg_data = {
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
        }
        result["segments"].append(seg_data)
        texts.append(seg.text.strip())
        
        if verbose:
            start_m = int(seg.start // 60)
            start_s = int(seg.start % 60)
            print(f"    [{start_m:02d}:{start_s:02d}] {seg.text.strip()}")
    
    result["full_text"] = " ".join(texts)
    
    # 统计
    duration = result["duration"]
    print(f"  ✅ 识别完成!")
    print(f"     语言: {result['language']} (置信度: {result['language_probability']:.1%})")
    print(f"     时长: {int(duration//60)}分{int(duration%60):02d}秒")
    print(f"     段落: {len(result['segments'])} 段")
    
    return result


# ═══════════════════════════════════════════════════════════
#  结构化分析
# ═══════════════════════════════════════════════════════════

def analyze_conversation(transcript: Dict) -> Dict:
    """
    结构化分析通话内容，提取:
    - 摘要
    - 待办事项
    - 期限
    """
    text = transcript["full_text"]
    
    # ── 提取待办事项规则 ──
    todo_patterns = [
        (r"(需要|要|得|必须|务必|请|麻烦)\s*(.*?)(。|$)", "任务"),
        (r"安排\s*(.*?)(。|$)", "任务"),
        (r"跟进\s*(.*?)(。|$)", "任务"),
        (r"确认\s*(.*?)(。|$)", "确认"),
        (r"发送|发给|发到\s*(.*?)(。|$)", "发送"),
        (r"准备好|完成|做完\s*(.*?)(。|$)", "交付"),
        (r"检查|核实|核对\s*(.*?)(。|$)", "检查"),
        (r"通知|告知|告诉\s*(.*?)(。|$)", "通知"),
        (r"问一下|问下|问问\s*(.*?)(。|$)", "询问"),
        (r"采购|买|购买\s*(.*?)(。|$)", "采购"),
    ]
    
    # ── 提取期限规则 ──
    deadline_patterns = [
        r"(今天|明天|后天|下周|下周一|下周二|下周三|下周四|下周五|下周六|下周日)",
        r"(\d{1,2})月(\d{1,2})日",
        r"(周[一二三四五六日])",
        r"(本[周月])([底末])",
        r"(下个?[周月])",
        r"(\d+)\s*(天|小时|分钟)\s*(内|后|之内|之后)",
    ]
    
    # ── 提取摘要 ──
    segments = transcript["segments"]
    
    # 找关键信息密度高的段落（开场+结尾+长时间段）
    key_segments = []
    if segments:
        # 第一段（开场）
        key_segments.append(segments[0]["text"])
        # 最后一段（总结）
        if len(segments) > 2:
            key_segments.append(segments[-1]["text"])
        # 最长的段（核心内容）
        longest = max(segments, key=lambda s: len(s["text"]))
        if longest not in segments[:1] and longest not in segments[-1:]:
            key_segments.append(longest["text"])
    
    # ── 提取待办事项 ──
    todos = []
    seen = set()
    for s in segments:
        t = s["text"]
        for pattern, category in todo_patterns:
            matches = re.findall(pattern, t)
            for m in matches:
                if isinstance(m, tuple):
                    item = m[1].strip()
                else:
                    item = m.strip()
                if item and len(item) > 3 and item not in seen:
                    seen.add(item)
                    # 尝试附上上下文时间
                    start_m = int(s["start"] // 60)
                    start_s = int(s["start"] % 60)
                    todos.append({
                        "item": item,
                        "category": category,
                        "timestamp": f"[{start_m:02d}:{start_s:02d}]",
                    })
    
    # 去重
    unique_todos = []
    seen_items = set()
    for t in todos:
        key = t["item"][:20]
        if key not in seen_items:
            seen_items.add(key)
            unique_todos.append(t)
    todos = unique_todos[:15]  # 最多15条
    
    # ── 提取期限 ──
    deadlines = []
    for s in segments:
        for pattern in deadline_patterns:
            matches = re.findall(pattern, s["text"])
            for m in matches:
                if isinstance(m, tuple):
                    m = "".join(m)
                m = m.strip()
                if m and m not in [d["time"] for d in deadlines]:
                    # 找到对应的待办事项
                    related = [t["item"] for t in todos if any(w in t["item"] for w in s["text"].split()[:5])]
                    deadlines.append({
                        "time": m,
                        "context": s["text"][:80],
                        "related_todos": related[:3],
                    })
    
    # ── 生成摘要 ──
    summary_parts = []
    if key_segments:
        summary_parts.append("核心内容: " + " | ".join([k[:120] for k in key_segments[:3]]))
    
    # 按类别统计待办
    categories = {}
    for t in todos:
        cat = t["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(t["item"])
    
    if categories:
        cat_summary = []
        for cat, items in categories.items():
            cat_summary.append(f"{cat}({len(items)}项)")
        summary_parts.append(f"涉及: {', '.join(cat_summary)}")
    
    if deadlines:
        summary_parts.append(f"期限: {'; '.join([d['time'] for d in deadlines[:5]])}")
    
    return {
        "summary": "\n".join(summary_parts) if summary_parts else "内容分析完成",
        "todos": todos,
        "deadlines": deadlines,
        "n_todos": len(todos),
        "n_deadlines": len(deadlines),
    }


# ═══════════════════════════════════════════════════════════
#  报告生成
# ═══════════════════════════════════════════════════════════

def generate_report(transcript: Dict, analysis: Dict, 
                    input_file: str) -> str:
    """生成结构化报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    duration = transcript["duration"]
    
    lines = []
    lines.append(f"# 🎙️ 通话分析报告")
    lines.append(f"")
    lines.append(f"**源文件:** {Path(input_file).name}")
    lines.append(f"**识别时间:** {now}")
    lines.append(f"**通话时长:** {int(duration//60)}分{int(duration%60):02d}秒")
    lines.append(f"**识别语言:** {transcript['language']} (置信度 {transcript['language_probability']:.1%})")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")
    
    # 摘要
    lines.append(f"## 📋 摘要")
    lines.append(f"")
    lines.append(f"{analysis['summary']}")
    lines.append(f"")
    
    # 待办事项
    lines.append(f"## ✅ 待办事项 ({analysis['n_todos']})")
    lines.append(f"")
    if analysis["todos"]:
        for i, t in enumerate(analysis["todos"]):
            lines.append(f"{i+1}. **[{t['category']}]** {t['item']}  {t['timestamp']}")
    else:
        lines.append(f"未识别出明确待办事项")
    lines.append(f"")
    
    # 期限
    lines.append(f"## ⏰ 时限 ({analysis['n_deadlines']})")
    lines.append(f"")
    if analysis["deadlines"]:
        for d in analysis["deadlines"]:
            lines.append(f"- **{d['time']}** — {d['context'][:60]}...")
    else:
        lines.append(f"未识别出明确期限")
    lines.append(f"")
    
    # 完整记录
    lines.append(f"---")
    lines.append(f"## 💬 完整对话记录")
    lines.append(f"")
    for seg in transcript["segments"]:
        start_m = int(seg["start"] // 60)
        start_s = int(seg["start"] % 60)
        lines.append(f"[{start_m:02d}:{start_s:02d}] {seg['text']}")
    lines.append(f"")
    
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════

def process_audio(input_path: str, output_path: Optional[str] = None,
                  language: str = "auto", model_size: str = "medium",
                  verbose: bool = False) -> str:
    """完整流水线: 音频→报告"""
    
    print("=" * 60)
    print("🎙️  听澜 — 音频识别与通话报告生成")
    print("=" * 60)
    print()
    
    if not os.path.exists(input_path):
        print(f"❌ 文件不存在: {input_path}")
        sys.exit(1)
    
    # Step 1: 转 WAV
    print("[1/4] 🎵 音频预处理...")
    wav_path = convert_to_wav(input_path)
    print()
    
    # Step 2: 语音识别
    print("[2/4] 🧠 语音识别...")
    if not check_dependencies():
        sys.exit(1)
    transcript = transcribe(wav_path, language, model_size, verbose)
    print()
    
    # Step 3: 结构化分析
    print("[3/4] 🔍 结构化分析...")
    analysis = analyze_conversation(transcript)
    print(f"      发现 {analysis['n_todos']} 条待办, {analysis['n_deadlines']} 个期限")
    print()
    
    # Step 4: 生成报告
    print("[4/4] 📄 生成报告...")
    report = generate_report(transcript, analysis, input_path)
    
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"  ✅ 已保存: {output_path}")
    else:
        # 输出到控制台
        print()
        print(report)
    
    print()
    print("=" * 60)
    print(f"✅ 处理完成! {'报告已保存' if output_path else ''}")
    print("=" * 60)
    
    return report


def main():
    parser = argparse.ArgumentParser(
        description="听澜 — 音频识别与通话报告生成 Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例:
              python tinglan.py call.mp3                          # 基本识别+报告
              python tinglan.py call.wav --lang zh               # 中文优先
              python tinglan.py call.m4a -o report.md            # 保存到文件
              python tinglan.py call.mp3 --model large-v3        # 高精度模式
              python tinglan.py call.mp3 --verbose               # 显示详细过程
        """),
    )
    parser.add_argument("input", help="音频文件 (MP3/WAV/M4A/OGG/SILK)")
    parser.add_argument("-o", "--output", help="输出报告路径 (默认打印到控制台)")
    parser.add_argument("--lang", default="auto", 
                        choices=["auto", "zh", "en", "ja"],
                        help="语言偏好 (默认: 自动检测)")
    parser.add_argument("--model", default="medium",
                        choices=["tiny", "base", "small", "medium", "large-v3"],
                        help="Whisper模型尺寸 (默认: medium)")
    parser.add_argument("--verbose", action="store_true",
                        help="显示详细识别过程")
    
    args = parser.parse_args()
    
    try:
        process_audio(
            input_path=args.input,
            output_path=args.output,
            language=args.lang,
            model_size=args.model,
            verbose=args.verbose,
        )
    except KeyboardInterrupt:
        print("\n\n⏹️  已取消")
    except Exception as e:
        print(f"\n❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
