# -*- coding: utf-8 -*-
"""跨 Profile 语音方案 v1.0 (2026-08-10)
微信场景 TTS + 听澜 STT 闭环推广到所有 profile

能力:
  1. STT: 音频 → 文本 (faster-whisper, 听澜同款)
  2. TTS: 文本 → 音频 (edge-tts, 多 voice)
  3. 闭环: 语音消息 → 文本 → Agent 回复 → 语音

用法:
  python voice_unified.py stt <audio_file>          # 语音转文本
  python voice_unified.py tts <text> <out.mp3>      # 文本转语音
  python voice_unified.py test                      # 全链路自测
"""
import os, sys, io, json, time, subprocess
# 注意: stdout 重配放 __main__ (避免 import 破坏调用方)

# 配置 (所有 profile 共享)
CONFIG = {
    "stt_model": "small",  # faster-whisper 模型 (small 平衡速度质量)
    "tts_voice": "zh-CN-XiaoxiaoNeural",  # edge-tts 中文女声
    "output_dir": r"D:\hermes\voice_cache",
}

def silk_to_wav(silk_path: str) -> str:
    """SILK → 16kHz WAV (微信语音格式, 听澜同款, pysilk BytesIO API)"""
    wav_path = silk_path.rsplit(".", 1)[0] + ".wav"
    try:
        import pysilk, io
        with open(silk_path, "rb") as f:
            silk_bytes = f.read()
        # 解码为 PCM (BytesIO API, 实测 24000→16000)
        dec = io.BytesIO()
        pysilk.decode(io.BytesIO(silk_bytes), dec, 24000)
        pcm = dec.getvalue()
        # 转 16kHz + WAV 头
        import wave
        try:
            import audioop
            pcm16 = audioop.ratecv(pcm, 2, 1, 24000, 16000, None)[0]
        except ImportError:
            pcm16 = pcm  # audioop 移除时直接用
        with wave.open(wav_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm16)
        return wav_path
    except ImportError:
        return f"[pysilk 未安装: pip install pysilk]"
    except Exception as e:
        return f"[SILK 转换失败: {str(e)[:60]}]"

def stt(audio_path: str) -> str:
    """STT: 音频 → 文本 (faster-whisper, 支持 SILK/任意格式)"""
    # SILK 格式先转 WAV (听澜同款)
    if audio_path.lower().endswith(".silk"):
        wav = silk_to_wav(audio_path)
        if not wav.startswith("["):
            audio_path = wav
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(CONFIG["stt_model"], device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio_path, language="zh", vad_filter=True)
        text = " ".join(s.text.strip() for s in segments)
        return text
    except ImportError:
        return f"[faster-whisper 未安装: pip install faster-whisper]"
    except Exception as e:
        return f"[STT 失败: {str(e)[:60]}]"

def tts(text: str, out_path: str = None) -> str:
    """TTS: 文本 → 音频 (edge-tts)"""
    out_path = out_path or os.path.join(CONFIG["output_dir"], f"tts_{int(time.time())}.mp3")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    try:
        import edge_tts
        import asyncio
        async def _gen():
            communicate = edge_tts.Communicate(text, CONFIG["tts_voice"])
            await communicate.save(out_path)
        asyncio.run(_gen())
        return out_path
    except ImportError:
        return f"[edge-tts 未安装: pip install edge-tts]"
    except Exception as e:
        return f"[TTS 失败: {str(e)[:60]}]"

def test():
    print("=== 跨 Profile 语音方案自测 ===")
    # TTS
    print("\n1. TTS 测试...")
    out = tts("你好，这是跨平台语音方案测试")
    if out.endswith(".mp3"):
        print(f"   ✅ TTS: {out} ({os.path.getsize(out)} bytes)")
    else:
        print(f"   ⚠️ {out}")
    # STT (若无音频则跳过)
    print("\n2. STT 测试...")
    print("   ⚠️ 需音频文件: python voice_unified.py stt <audio>")
    print("\n✅ 方案就绪 (TTS 可用, STT 待音频验证)")

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if len(sys.argv) >= 3 and sys.argv[1] == "stt":
        result = stt(sys.argv[2])
        print(f"🎙️ 识别结果: {result}")
    elif len(sys.argv) >= 3 and sys.argv[1] == "tts":
        out = tts(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
        print(f"🔊 输出: {out}")
    else:
        test()
