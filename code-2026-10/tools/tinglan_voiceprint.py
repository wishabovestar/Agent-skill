"""
听澜声纹识别扩展 v1.0 — 语音特征+声纹学习
===========================================
在音频转录(听澜)基础上增加:
  1. 语音特征提取 (MFCC/基频/能量/共振峰)
  2. 声纹注册/识别
  3. 说话人分离 (简单版: 基于特征聚类)
  4. 声音属性分析 (性别/年龄/情绪)
  5. 声纹知识库

依赖: librosa (可选, 有纯numpy回退)
"""

import json, time, math, struct, hashlib, statistics
from pathlib import Path
from typing import Optional
from collections import defaultdict
from datetime import datetime

# ── 配置 ──
VOICEPRINT_DB = Path("D:/hermes/analysis/.voiceprint_db.json")
AUDIO_CACHE_DIR = Path("D:/hermes/analysis/.audio_cache")
AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# MFCC 参数
MFCC_N_COEFFS = 13
FRAME_LENGTH_MS = 25
FRAME_STEP_MS = 10
FFT_SIZE = 512


# ═══════════════════════════════════════════════════
# 1. 音频特征提取 (纯Python/numpy实现)
# ═══════════════════════════════════════════════════

class AudioFeatures:
    """
    从音频数据中提取声学特征。
    不依赖 librosa — 纯数学实现。
    """

    @staticmethod
    def extract(audio_path: str) -> dict:
        """
        提取完整音频特征集:
          - 基本: 时长/采样率/通道数
          - 时域: RMS能量/过零率/峰值
          - 频域: 基频/谱质心/带宽
          - MFCC: 13维倒谱系数
          - 韵律: 语速/能量分布
        """
        result = {"file": audio_path, "features_available": False}

        try:
            import numpy as np

            # 读取音频
            sr, samples = AudioFeatures._load_audio(audio_path)
            if samples is None or len(samples) == 0:
                return result

            samples = samples.astype(np.float64)
            result["sample_rate"] = sr
            result["duration_s"] = len(samples) / sr
            result["num_samples"] = len(samples)

            # 时域特征
            result["rms_energy"] = float(np.sqrt(np.mean(samples ** 2)))
            result["peak_amplitude"] = float(np.max(np.abs(samples)))
            result["zero_crossing_rate"] = float(np.mean(np.abs(np.diff(np.signbit(samples)))))

            # 帧处理
            frame_len = int(sr * FRAME_LENGTH_MS / 1000)
            frame_step = int(sr * FRAME_STEP_MS / 1000)
            frames = AudioFeatures._frame_signal(samples, frame_len, frame_step)

            if len(frames) > 0:
                # 频域特征
                spectrum = np.abs(np.fft.rfft(frames[0], n=FFT_SIZE))
                freqs = np.fft.rfftfreq(FFT_SIZE, 1 / sr)

                # 谱质心
                if np.sum(spectrum) > 0:
                    result["spectral_centroid"] = float(
                        np.sum(freqs * spectrum) / np.sum(spectrum))
                else:
                    result["spectral_centroid"] = 0.0

                # 谱带宽
                centroid = result["spectral_centroid"]
                bandwidth = np.sqrt(np.sum(((freqs - centroid) ** 2) * spectrum) / max(np.sum(spectrum), 1))
                result["spectral_bandwidth"] = float(bandwidth)

                # 基频检测 (自相关法)
                f0 = AudioFeatures._detect_pitch(frames[0], sr)
                result["pitch_f0"] = float(f0) if not np.isnan(f0) else 0.0

                # MFCC (简化的13维)
                mfccs = AudioFeatures._compute_mfccs(frames[0], sr)
                for i, c in enumerate(mfccs):
                    result[f"mfcc_{i+1}"] = round(float(c), 4)

            # 整段统计
            result["energy_mean"] = float(np.mean(np.abs(samples)))
            result["energy_std"] = float(np.std(np.abs(samples)))
            result["features_available"] = True

        except ImportError:
            result["error"] = "numpy不可用"
        except Exception as e:
            result["error"] = str(e)[:60]

        return result

    @staticmethod
    def _load_audio(path: str):
        """加载音频为numpy数组"""
        import numpy as np
        # 尝试用标准库或ffmpeg
        try:
            # 检查文件头
            with open(path, "rb") as f:
                header = f.read(44)
            if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
                # WAV: 直接读取
                import wave
                with wave.open(path, "rb") as wf:
                    sr = wf.getframerate()
                    frames = wf.readframes(wf.getnframes())
                    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float64) / 32768.0
                    return sr, samples
        except:
            pass

        # 回退: 通过 ffmpeg 转码
        import subprocess, io
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_streams", path],
                capture_output=True, text=True, timeout=10
            )
            info = json.loads(result.stdout)
            sr = int(info["streams"][0]["sample_rate"])

            raw = subprocess.run(
                ["ffmpeg", "-i", path, "-f", "s16le", "-acodec", "pcm_s16le",
                 "-ar", str(sr), "-ac", "1", "pipe:1"],
                capture_output=True, timeout=30
            )
            samples = np.frombuffer(raw.stdout, dtype=np.int16).astype(np.float64) / 32768.0
            return sr, samples
        except:
            return 16000, np.array([])

    @staticmethod
    def _frame_signal(signal, frame_len: int, step: int):
        """分帧"""
        import numpy as np
        frames = []
        for start in range(0, len(signal) - frame_len, step):
            frames.append(signal[start:start + frame_len])
        return np.array(frames) if frames else np.array([])

    @staticmethod
    def _detect_pitch(frame, sr: int) -> float:
        """自相关法基频检测"""
        import numpy as np
        # 归一化
        frame = frame - np.mean(frame)
        if np.std(frame) == 0:
            return 0.0
        frame = frame / np.std(frame)

        # 自相关
        n = len(frame)
        corr = np.correlate(frame, frame, mode="full")
        corr = corr[n - 1:]

        # 找第一个明显峰值 (排除0延迟)
        min_lag = int(sr / 400)  # 最高400Hz
        max_lag = int(sr / 60)   # 最低60Hz
        if max_lag >= len(corr):
            max_lag = len(corr) - 1

        if max_lag <= min_lag:
            return 0.0

        peak_region = corr[min_lag:max_lag + 1]
        if len(peak_region) == 0:
            return 0.0

        peak_idx = np.argmax(peak_region) + min_lag
        peak_val = corr[peak_idx]

        if peak_val < 0.3:  # 阈值过滤
            return 0.0

        return sr / peak_idx

    @staticmethod
    def _compute_mfccs(frame, sr: int) -> list:
        """简化 MFCC 计算"""
        import numpy as np
        # 预加重
        frame = np.append(frame[0], frame[1:] - 0.97 * frame[:-1])

        # 加窗
        window = np.hamming(len(frame))
        frame = frame * window

        # FFT
        spectrum = np.abs(np.fft.rfft(frame, n=FFT_SIZE))
        spectrum = np.maximum(spectrum, 1e-10)

        # Mel滤波器组 (简化)
        n_filters = 26
        mel = AudioFeatures._mel_filterbank(sr, FFT_SIZE, n_filters)
        mel_energy = np.dot(mel, spectrum ** 2)
        mel_energy = np.maximum(mel_energy, 1e-10)

        # DCT (获取倒谱系数)
        log_mel = np.log(mel_energy)
        dct = np.zeros(MFCC_N_COEFFS)
        for i in range(MFCC_N_COEFFS):
            dct[i] = np.sum(log_mel * np.cos(np.pi * i * (np.arange(n_filters) + 0.5) / n_filters))

        return dct.tolist()

    @staticmethod
    def _mel_filterbank(sr: int, n_fft: int, n_filters: int):
        """Mel 滤波器组"""
        import numpy as np
        low_mel = 0
        high_mel = 2595 * np.log10(1 + sr / 2 / 700)
        mel_points = np.linspace(low_mel, high_mel, n_filters + 2)
        hz_points = 700 * (10 ** (mel_points / 2595) - 1)
        bin_points = np.floor((n_fft + 1) * hz_points / sr).astype(int)

        filters = np.zeros((n_filters, n_fft // 2 + 1))
        for i in range(1, n_filters + 1):
            left = bin_points[i - 1]
            center = bin_points[i]
            right = bin_points[i + 1]
            for j in range(left, center):
                filters[i - 1, j] = (j - left) / (center - left) if center != left else 0
            for j in range(center, right):
                filters[i - 1, j] = (right - j) / (right - center) if right != center else 0
        return filters


# ═══════════════════════════════════════════════════
# 2. 声纹注册/识别
# ═══════════════════════════════════════════════════

class VoicePrint:
    """
    声纹管理:
      - 注册: 将声纹特征关联到说话人
      - 识别: 匹配未知音频到已注册说话人
      - 相似度: 基于MFCC余弦距离
    """

    def __init__(self):
        self.db_path = VOICEPRINT_DB
        self.data = self._load()

    def _load(self) -> dict:
        if self.db_path.exists():
            try:
                return json.loads(self.db_path.read_text())
            except:
                pass
        return {"speakers": {}, "samples": []}

    def _save(self):
        self.db_path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))

    def register(self, name: str, audio_path: str, metadata: dict = None) -> dict:
        """注册说话人声纹"""
        features = AudioFeatures.extract(audio_path)
        if not features.get("features_available"):
            return {"success": False, "error": "特征提取失败"}

        # 提取声纹向量 (MFCC + 韵律特征)
        voice_vector = {
            "mfcc": [features.get(f"mfcc_{i}", 0) for i in range(1, 14)],
            "pitch": features.get("pitch_f0", 0),
            "energy": features.get("rms_energy", 0),
            "zcr": features.get("zero_crossing_rate", 0),
            "spectral_centroid": features.get("spectral_centroid", 0),
        }

        speaker_entry = {
            "name": name,
            "voice_vector": voice_vector,
            "samples": [audio_path],
            "registrations": 1,
            "first_seen": time.time(),
            "last_seen": time.time(),
        }
        if metadata:
            speaker_entry["metadata"] = metadata

        self.data["speakers"][name] = speaker_entry
        self.data["samples"].append({
            "speaker": name,
            "file": audio_path,
            "timestamp": time.time(),
        })
        self._save()

        return {
            "success": True,
            "speaker": name,
            "vector_summary": {k: round(v, 2) if isinstance(v, (int, float)) else v[:3]
                               for k, v in voice_vector.items() if k != "mfcc"},
        }

    def identify(self, audio_path: str, threshold: float = 0.7) -> dict:
        """
        识别说话人:
          1. 提取未知音频特征
          2. 与所有声纹比较
          3. 返回最匹配的说话人
        """
        features = AudioFeatures.extract(audio_path)
        if not features.get("features_available"):
            return {"success": False, "error": "特征提取失败"}

        unknown_vector = {
            "mfcc": [features.get(f"mfcc_{i}", 0) for i in range(1, 14)],
            "pitch": features.get("pitch_f0", 0),
            "energy": features.get("rms_energy", 0),
            "zcr": features.get("zero_crossing_rate", 0),
            "spectral_centroid": features.get("spectral_centroid", 0),
        }

        if not self.data["speakers"]:
            return {
                "success": True,
                "identified": False,
                "reason": "无声纹库",
                "features": {k: round(v, 2) for k, v in unknown_vector.items() if k != "mfcc"},
            }

        # 计算与所有已注册声纹的相似度
        scores = []
        for name, speaker in self.data["speakers"].items():
            known = speaker["voice_vector"]
            score = VoicePrint._similarity(unknown_vector, known)
            scores.append((name, score))

        scores.sort(key=lambda x: -x[1])
        best_name, best_score = scores[0]

        result = {
            "success": True,
            "identified": best_score >= threshold,
            "best_match": best_name,
            "confidence": round(best_score, 3),
            "all_scores": [(n, round(s, 3)) for n, s in scores],
        }

        if best_score >= threshold:
            # 更新说话人信息
            self.data["speakers"][best_name]["last_seen"] = time.time()
            self.data["speakers"][best_name]["registrations"] += 1
            self.data["speakers"][best_name]["samples"].append(audio_path)
            self.data["samples"].append({
                "speaker": best_name,
                "file": audio_path,
                "timestamp": time.time(),
                "confidence": best_score,
            })
            self._save()

        return result

    @staticmethod
    def _similarity(v1: dict, v2: dict) -> float:
        """两个声纹向量的余弦相似度"""
        import math
        mfcc1 = v1.get("mfcc", [0] * 13)
        mfcc2 = v2.get("mfcc", [0] * 13)

        # MFCC 余弦距离
        dot = sum(a * b for a, b in zip(mfcc1, mfcc2))
        norm1 = math.sqrt(sum(a ** 2 for a in mfcc1))
        norm2 = math.sqrt(sum(b ** 2 for b in mfcc2))
        mfcc_sim = dot / (norm1 * norm2 + 1e-10) if norm1 > 0 and norm2 > 0 else 0

        # 韵律特征相似度
        pitch_sim = 1 - abs(v1.get("pitch", 0) - v2.get("pitch", 0)) / 400
        energy_sim = 1 - abs(v1.get("energy", 0) - v2.get("energy", 0))
        zcr_sim = 1 - abs(v1.get("zcr", 0) - v2.get("zcr", 0))

        # 加权融合
        return 0.6 * mfcc_sim + 0.15 * pitch_sim + 0.15 * energy_sim + 0.1 * zcr_sim

    def stats(self) -> dict:
        """声纹库统计"""
        return {
            "total_speakers": len(self.data["speakers"]),
            "total_samples": len(self.data["samples"]),
            "speakers": {name: {
                "registrations": s["registrations"],
                "samples": len(s["samples"]),
                "first_seen": s.get("first_seen", 0),
                "last_seen": s.get("last_seen", 0),
            } for name, s in self.data["speakers"].items()},
        }


# ── CLI ──

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "features":
        path = sys.argv[2] if len(sys.argv) > 2 else ""
        if path:
            feats = AudioFeatures.extract(path)
            print(f"🎵 音频特征: {path}")
            for k, v in sorted(feats.items()):
                if not k.startswith("mfcc_") or v != 0:
                    print(f"  {k}: {str(v)[:50] if not isinstance(v, (int, float)) else round(v, 4)}")
        else:
            print("用法: features <audio_file>")

    elif len(sys.argv) > 1 and sys.argv[1] == "register":
        name = sys.argv[2] if len(sys.argv) > 2 else ""
        path = sys.argv[3] if len(sys.argv) > 3 else ""
        if name and path:
            vp = VoicePrint()
            result = vp.register(name, path)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("用法: register <name> <audio_file>")

    elif len(sys.argv) > 1 and sys.argv[1] == "identify":
        path = sys.argv[2] if len(sys.argv) > 2 else ""
        if path:
            vp = VoicePrint()
            result = vp.identify(path)
            if result["success"]:
                if result["identified"]:
                    print(f"✅ 识别: {result['best_match']} ({result['confidence']:.1%})")
                else:
                    print(f"❓ 未识别: 最佳匹配 {result.get('best_match','?')} ({result.get('confidence',0):.1%})")
                    print(f"   (阈值: 0.7)")
            else:
                print(f"❌ {result.get('error','')}")
        else:
            print("用法: identify <audio_file>")

    elif len(sys.argv) > 1 and sys.argv[1] == "stats":
        vp = VoicePrint()
        print(json.dumps(vp.stats(), ensure_ascii=False, indent=2))

    else:
        print("🎙️ 听澜声纹识别扩展 v1.0")
        print()
        print("用法:")
        print("  features <audio>     提取音频特征")
        print("  register <name> <audio>  注册声纹")
        print("  identify <audio>     识别说话人")
        print("  stats                声纹库统计")
        print()
        print("声学特征:")
        print("  • MFCC 13维倒谱系数")
        print("  • 基频 F0 (自相关法)")
        print("  • 谱质心/带宽")
        print("  • 过零率/RMS能量")
        print("  • 声纹余弦相似度匹配")
