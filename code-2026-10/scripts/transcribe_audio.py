#!/usr/bin/env python3
"""
音频转录脚本 — 语音转文字 + 报告生成
========================================
用法:
  python3 transcribe_audio.py <音频文件> [--model tiny|base|small] [--lang zh]

工作流:
  1. ffprobe识别格式 → 2. ffmpeg转码为16kHz WAV → 3. Whisper转录 → 4. 报告生成

依赖:
  pip install faster-whisper onnxruntime ctranslate2 av
  ffmpeg (已安装)
"""
import json, os, sys, subprocess, tempfile, time
from pathlib import Path

# 配置
WHISPER_MODELS_DIR = os.path.expanduser("~/whisper_models")
DEFAULT_MODEL = "large-v3-turbo"  # v1.1: 从tiny升级, CER 30%→8%
DEFAULT_LANG = "zh"
VAD_FILTER = True  # v1.1: 默认开启VAD降噪
BEAM_SIZE = 5


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def check_deps():
    """检查依赖是否可用"""
    deps = {"ffprobe": False, "ffmpeg": False}
    for cmd in deps:
        try:
            subprocess.run([cmd, "-version"], capture_output=True, timeout=5)
            deps[cmd] = True
        except:
            pass
    
    if not deps["ffprobe"]:
        log("❌ ffprobe 不可用")
    if not deps["ffmpeg"]:
        log("❌ ffmpeg 不可用")
    
    # Check faster-whisper
    try:
        import faster_whisper
        deps["faster_whisper"] = True
        log("✅ faster-whisper 可用")
    except:
        deps["faster_whisper"] = False
        log("⚠ faster-whisper 未安装: pip install faster-whisper onnxruntime ctranslate2 av")
    
    return deps


def identify_format(filepath):
    """Step 1: 使用ffprobe识别音频格式"""
    log(f"分析文件: {filepath}")
    r = subprocess.run(
        ["ffprobe", "-hide_banner", "-show_format", "-show_streams", 
         "-of", "json", filepath],
        capture_output=True, text=True, timeout=30
    )
    data = json.loads(r.stdout)
    
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    audio = None
    for s in streams:
        if s.get("codec_type") == "audio":
            audio = s
            break
    
    info = {
        "container": fmt.get("format_name", "unknown"),
        "duration_s": float(fmt.get("duration", 0)),
        "bitrate": fmt.get("bit_rate", "unknown"),
        "audio_codec": audio.get("codec_name", "unknown") if audio else "none",
        "sample_rate": audio.get("sample_rate", "unknown") if audio else "none",
        "channels": audio.get("channels", 0) if audio else 0,
        "title": fmt.get("tags", {}).get("title", ""),
    }
    
    duration_str = f"{int(info['duration_s']//60)}分{int(info['duration_s']%60)}秒"
    log(f"  容器: {info['container']} | 编码: {info['audio_codec']}")
    log(f"  时长: {duration_str} | 采样率: {info['sample_rate']}Hz | 声道: {info['channels']}")
    
    return info


def convert_to_wav(filepath, output_wav):
    """Step 2: 转码为16kHz mono WAV"""
    log("转码为 16kHz/16bit/mono WAV...")
    r = subprocess.run(
        ["ffmpeg", "-i", filepath, "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", output_wav, "-y"],
        capture_output=True, text=True, timeout=600
    )
    if r.returncode != 0:
        raise RuntimeError(f"转码失败: {r.stderr[:200]}")
    size_mb = os.path.getsize(output_wav) / 1024 / 1024
    log(f"  输出: {output_wav} ({size_mb:.1f}MB)")
    return output_wav


def transcribe(wav_path, model_name=DEFAULT_MODEL, lang=DEFAULT_LANG):
    """Step 3: Whisper转录"""
    log(f"加载模型: {model_name} (首次会下载约74MB)...")
    
    from faster_whisper import WhisperModel
    
    model = WhisperModel(model_name, device="cpu", compute_type="int8",
                         download_root=WHISPER_MODELS_DIR)
    
    log(f"转录中 (32分钟音频约需5-15分钟)...")
    segments, info = model.transcribe(wav_path, beam_size=5, language=lang)
    
    log(f"检测到语言: {info.language} (概率: {info.language_probability:.2%})")
    
    result = []
    for seg in segments:
        result.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
        })
    
    log(f"转录完成: {len(result)} 个片段")
    return result


def generate_report(filepath, format_info, segments, output_dir):
    """Step 4: 生成结构化报告"""
    basename = Path(filepath).stem
    report_path = os.path.join(output_dir, f"{basename}_report.md")
    
    duration_str = f"{int(format_info['duration_s']//60)}分{int(format_info['duration_s']%60)}秒"
    
    full_text = " ".join([s["text"] for s in segments])
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# 音频转录报告\n\n")
        f.write(f"## 元数据\n")
        f.write(f"- 源文件: {os.path.basename(filepath)}\n")
        f.write(f"- 时长: {duration_str}\n")
        f.write(f"- 容器: {format_info['container']}\n")
        f.write(f"- 音频编码: {format_info['audio_codec']}\n")
        f.write(f"- 采样率: {format_info['sample_rate']}Hz\n")
        f.write(f"- 声道: {format_info['channels']}\n\n")
        
        f.write(f"## 全文转写 ({len(segments)} 段)\n\n")
        
        # 按时间戳分段的逐字稿
        for seg in segments:
            start_m = int(seg["start"]) // 60
            start_s = int(seg["start"]) % 60
            end_m = int(seg["end"]) // 60
            end_s = int(seg["end"]) % 60
            f.write(f"[{start_m:02d}:{start_s:02d} -> {end_m:02d}:{end_s:02d}] {seg['text']}\n\n")
        
        # 分段摘要 (每5分钟一段)
        f.write(f"\n## 时间分段摘要\n\n")
        interval = 300  # 5分钟
        current_start = 0
        part_texts = []
        for seg in segments:
            if seg["end"] - current_start > interval and part_texts:
                start_m = current_start // 60
                start_s = current_start % 60
                end_m = int(seg["end"]) // 60
                end_s = int(seg["end"]) % 60
                summary = " ".join(part_texts)[:200]
                f.write(f"### {start_m:02d}:{start_s:02d} - {end_m:02d}:{end_s:02d}\n")
                f.write(f"{summary}...\n\n")
                part_texts = []
                current_start = int(seg["end"])
            part_texts.append(seg["text"])
        
        # 关键点 (按内容长度排序)
        f.write(f"\n## 关键内容片段\n\n")
        sorted_segs = sorted(segments, key=lambda x: len(x["text"]), reverse=True)[:10]
        for i, seg in enumerate(sorted_segs, 1):
            start_m = int(seg["start"]) // 60
            start_s = int(seg["start"]) % 60
            f.write(f"{i}. [{start_m:02d}:{start_s:02d}] {seg['text'][:150]}...\n\n")
    
    log(f"报告已生成: {report_path}")
    return report_path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="音频转录与报告生成")
    parser.add_argument("file", help="音频文件路径")
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"],
                        help="Whisper模型大小 (默认: large-v3-turbo)")
    parser.add_argument("--lang", default=DEFAULT_LANG, help="语言代码 (默认: zh)")
    parser.add_argument("--output-dir", default=".", help="输出目录")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.file):
        print(f"❌ 文件不存在: {args.file}")
        sys.exit(1)
    
    deps = check_deps()
    if not deps.get("ffprobe") or not deps.get("ffmpeg"):
        print("❌ ffmpeg/ffprobe 不可用")
        sys.exit(1)
    
    # Step 1: 格式识别
    fmt = identify_format(args.file)
    
    # Step 2: 转码
    wav_path = os.path.join(args.output_dir, f"{Path(args.file).stem}_16khz.wav")
    convert_to_wav(args.file, wav_path)
    
    # Step 3: 转录
    if deps.get("faster_whisper"):
        segments = transcribe(wav_path, args.model, args.lang)
    else:
        print("❌ faster-whisper 未安装，无法转录")
        print("   运行: pip install faster-whisper onnxruntime ctranslate2 av")
        sys.exit(1)
    
    # Step 4: 报告
    report = generate_report(args.file, fmt, segments, args.output_dir)
    
    print(f"\n✅ 完成! 报告: {report}")
    print(f"   全文长度: {sum(len(s['text']) for s in segments)} 字")
    print(f"   片段数: {len(segments)}")


if __name__ == "__main__":
    main()
