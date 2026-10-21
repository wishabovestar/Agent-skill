#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整图表OCR智能流水线
========================
预处理 + 多遍OCR + 领域纠错 + 表格提取 + 质量评分

功能模块：
  - ImagePreprocessor  : 自适应二值化、CLAHE、超分辨率、去噪、自动最佳组合选择
  - MultiPassOCR       : PSM 3/4/6 多模式OCR + 投票/合并 + 置信度
  - DomainCorrector    : 电池领域纠错字典 + 数值合理性检查 + 正则模式匹配
  - TableExtractor     : 表格线检测、单元格分割、逐格OCR、DataFrame重建
  - ChartOCRPipeline   : 主流水线，串联全部模块，输出JSON+DataFrame+质量评分

作者：通量（Python 数据科学专家）
日期：2026-07-08
"""

import sys
# 修复：排除 hermes-agent venv 中损坏的 PIL，使用系统 site-packages
sys.path = [p for p in sys.path if "hermes-agent" not in p]

import os
import re
import json
import math
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image, ImageEnhance, ImageFilter
import cv2
import pytesseract
from pytesseract import Output

warnings.filterwarnings("ignore")

# ============================================================
# 0. 全局配置
# ============================================================

# Tesseract 路径（Windows）
pytesseract.pytesseract.tesseract_cmd = r"C:/Program Files/Tesseract-OCR/tesseract.exe"

# 输出目录
OUTPUT_DIR = Path(__file__).resolve().parent

# 电池领域参数合理范围
BATTERY_CONSTRAINTS = {
    "efficiency": (0.0, 100.0),       # 效率（%）
    "capacity": (500.0, 4000.0),      # 容量（mAh/g）
    "voltage": (0.0, 5.0),            # 电压（V）
    "current_density": (0.0, 10000.0),# 电流密度（mA/g）
    "cycle": (1, 10000),             # 循环次数
}

# ============================================================
# 1. ImagePreprocessor 类
# ============================================================

class ImagePreprocessor:
    """图像预处理：二值化 + CLAHE + 超分辨率 + 去噪，自动选择最佳组合。

    针对图表/表格OCR场景优化，去除背景噪声，增强文字对比度，
    并自动评估多种预处理组合的清晰度，选择边缘最清晰的结果。
    """

    def __init__(self, scale_factor: float = 2.0):
        """
        Args:
            scale_factor: 超分辨率缩放倍数（默认2x）
        """
        self.scale_factor = scale_factor

    # ----------------------------------------------------------
    # 1.1 自适应二值化（3种方法）
    # ----------------------------------------------------------

    @staticmethod
    def binarize_otsu(gray: np.ndarray) -> np.ndarray:
        """Otsu 全局阈值二值化。

        Args:
            gray: 灰度图 (H, W), uint8

        Returns:
            二值图 (H, W), uint8 (0/255)
        """
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binary

    @staticmethod
    def binarize_sauvola(gray: np.ndarray, window: int = 25, k: float = 0.2, r: float = 128.0) -> np.ndarray:
        """Sauvola 局部自适应二值化。

        阈值公式：T = mean * (1 + k * (std / r - 1))

        Args:
            gray: 灰度图 (H, W), uint8, 值域 [0, 255]
            window: 局部窗口大小
            k: 灵敏度参数（典型值 0.2~0.5）
            r: 动态范围参数（128 for 8-bit）

        Returns:
            二值图 (H, W), uint8 (0/255)
        """
        gray_f = gray.astype(np.float64)
        mean = cv2.blur(gray_f, (window, window))
        mean_sq = cv2.blur(gray_f ** 2, (window, window))
        std = np.sqrt(np.maximum(mean_sq - mean ** 2, 0.0))

        threshold = mean * (1.0 + k * (std / r - 1.0))
        binary = np.where(gray_f > threshold, 255, 0).astype(np.uint8)
        return binary

    @staticmethod
    def binarize_adaptive_mean(gray: np.ndarray, block_size: int = 21, c: int = 5) -> np.ndarray:
        """OpenCV 自适应均值二值化。

        Args:
            gray: 灰度图 (H, W), uint8
            block_size: 邻域大小（奇数）
            c: 从均值中减去的常数

        Returns:
            二值图 (H, W), uint8 (0/255)
        """
        if block_size % 2 == 0:
            block_size += 1
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
            cv2.THRESH_BINARY, block_size, c
        )
        return binary

    def all_binarizations(self, gray: np.ndarray) -> dict[str, np.ndarray]:
        """生成3种二值化结果。

        Args:
            gray: 灰度图

        Returns:
            {'otsu': ..., 'sauvola': ..., 'adaptive_mean': ...}
        """
        return {
            "otsu": self.binarize_otsu(gray),
            "sauvola": self.binarize_sauvola(gray),
            "adaptive_mean": self.binarize_adaptive_mean(gray),
        }

    # ----------------------------------------------------------
    # 1.2 CLAHE 对比度增强
    # ----------------------------------------------------------

    @staticmethod
    def apply_clahe(gray: np.ndarray, clip_limit: float = 2.0, tile_grid_size: int = 8) -> np.ndarray:
        """CLAHE (Contrast Limited Adaptive Histogram Equalization)。

        Args:
            gray: 灰度图 (H, W), uint8
            clip_limit: 对比度限制阈值
            tile_grid_size: 瓦片大小

        Returns:
            增强后的灰度图 (H, W), uint8
        """
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_grid_size, tile_grid_size))
        return clahe.apply(gray)

    # ----------------------------------------------------------
    # 1.3 超分辨率（多种插值方法）
    # ----------------------------------------------------------

    @staticmethod
    def super_resolve(image: np.ndarray, scale: float, method: str = "lanczos") -> np.ndarray:
        """使用多种插值方法进行超分辨率放大。

        Args:
            image: 输入图像 (H, W) 或 (H, W, 3)
            scale: 缩放倍数
            method: 'lanczos' | 'bicubic' | 'bilinear' | 'nearest'

        Returns:
            放大后的图像
        """
        h, w = image.shape[:2]
        new_h, new_w = int(h * scale), int(w * scale)

        if "lanczos" in method:
            interp = cv2.INTER_LANCZOS4
        elif "bicubic" in method:
            interp = cv2.INTER_CUBIC
        elif "bilinear" in method:
            interp = cv2.INTER_LINEAR
        else:
            interp = cv2.INTER_NEAREST

        return cv2.resize(image, (new_w, new_h), interpolation=interp)

    @staticmethod
    def pil_super_resolve(image: np.ndarray, scale: float, method: str = "lanczos") -> np.ndarray:
        """使用 PIL 超分辨率（支持更多插值方法）。

        Args:
            image: 输入图像 (H, W) 或 (H, W, 3)
            scale: 缩放倍数
            method: 'lanczos' | 'bicubic' | 'bilinear' | 'hamming' | 'box'

        Returns:
            放大后的图像
        """
        pil_image = Image.fromarray(image)
        h, w = image.shape[:2]
        new_h, new_w = int(h * scale), int(w * scale)

        resample_map = {
            "lanczos": Image.Resampling.LANCZOS,
            "bicubic": Image.Resampling.BICUBIC,
            "bilinear": Image.Resampling.BILINEAR,
            "hamming": Image.Resampling.HAMMING,
            "box": Image.Resampling.BOX,
        }
        resample = resample_map.get(method, Image.Resampling.LANCZOS)
        resized = pil_image.resize((new_w, new_h), resample=resample)
        return np.array(resized)

    # ----------------------------------------------------------
    # 1.4 去噪
    # ----------------------------------------------------------

    @staticmethod
    def bilateral_denoise(image: np.ndarray, d: int = 9, sigma_color: float = 75.0, sigma_space: float = 75.0) -> np.ndarray:
        """双边滤波去噪（保边去噪）。

        Args:
            image: 输入图像 (H, W) 或 (H, W, 3), uint8
            d: 像素邻域直径
            sigma_color: 颜色空间标准差
            sigma_space: 坐标空间标准差

        Returns:
            去噪后的图像
        """
        return cv2.bilateralFilter(image, d, sigma_color, sigma_space)

    @staticmethod
    def median_denoise(image: np.ndarray, ksize: int = 3) -> np.ndarray:
        """中值滤波去噪（对椒盐噪声有效）。

        Args:
            image: 输入图像
            ksize: 核大小（奇数）

        Returns:
            去噪后的图像
        """
        if ksize % 2 == 0:
            ksize += 1
        return cv2.medianBlur(image, ksize)

    # ----------------------------------------------------------
    # 1.5 边缘清晰度指标
    # ----------------------------------------------------------

    @staticmethod
    def edge_sharpness_score(image: np.ndarray) -> float:
        """基于拉普拉斯方差的边缘清晰度指标。

        值越大表示边缘越清晰，适合文字OCR。

        Args:
            image: 灰度图 (H, W), uint8

        Returns:
            清晰度分数
        """
        laplacian = cv2.Laplacian(image, cv2.CV_64F)
        score = laplacian.var()
        return float(score)

    @staticmethod
    def tenengrad_score(image: np.ndarray) -> float:
        """Tenengrad 清晰度指标（基于 Sobel 梯度）。

        Args:
            image: 灰度图 (H, W), uint8

        Returns:
            Tenengrad 分数
        """
        gx = cv2.Sobel(image, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(image, cv2.CV_64F, 0, 1, ksize=3)
        magnitude = np.sqrt(gx ** 2 + gy ** 2)
        score = magnitude.mean()
        return float(score)

    # ----------------------------------------------------------
    # 1.6 自动选择最佳预处理组合
    # ----------------------------------------------------------

    def auto_select_best(
        self,
        image: np.ndarray,
        verbose: bool = True,
    ) -> dict[str, Any]:
        """自动评估多种预处理组合，选出边缘最清晰的结果。

        流水线：
          灰度化 → CLAHE → 超分辨率 → 二值化(3选1) → 去噪 → 清晰度评分
          同时包含"无预处理"原始图像作为基准对比。

        Args:
            image: 输入图像 (H, W, 3) BGR 或 (H, W) 灰度
            verbose: 是否打印详细信息

        Returns:
            {
                'best_image': np.ndarray,    # 最佳预处理结果
                'best_score': float,          # 清晰度分数
                'best_combination': str,      # 最佳组合描述
                'all_scores': list[dict],     # 所有组合的评分
                'gray': np.ndarray,           # 原始灰度图
            }
        """
        # 转为灰度
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        # CLAHE 增强
        enhanced = self.apply_clahe(gray)

        # 超分辨率插值方法
        sr_methods = ["lanczos", "bicubic", "bilinear"]

        # 二值化方法
        bin_methods: list[tuple[str, callable]] = [
            ("otsu", self.binarize_otsu),
            ("sauvola", self.binarize_sauvola),
            ("adaptive_mean", self.binarize_adaptive_mean),
        ]

        # 去噪开关
        denoise_opts = [True, False]

        all_scores: list[dict] = []
        best_image = None
        best_score = -1.0
        best_combo = ""

        # ---- 基准：无预处理（仅灰度） ----
        es_raw = self.edge_sharpness_score(gray)
        ts_raw = self.tenengrad_score(gray)
        combined_raw = es_raw * 0.6 + ts_raw * 0.4
        all_scores.append({
            "sr": "none",
            "binarize": "none",
            "denoise": False,
            "laplacian_var": round(es_raw, 4),
            "tenengrad": round(ts_raw, 4),
            "combined": round(combined_raw, 4),
        })
        if combined_raw > best_score:
            best_score = combined_raw
            best_image = gray
            best_combo = "no_preprocessing (原始灰度)"

        # 遍历所有组合
        for sr_name in sr_methods:
            # 超分辨率
            upscaled = self.pil_super_resolve(enhanced, self.scale_factor, method=sr_name)

            for bin_name, bin_func in bin_methods:
                # 二值化
                binary = bin_func(upscaled)

                for denoise in denoise_opts:
                    if denoise:
                        # 去噪后二值化可能被破坏，对二值图用中值滤波
                        processed = self.median_denoise(binary, ksize=3)
                    else:
                        processed = binary

                    # 评估清晰度
                    es = self.edge_sharpness_score(processed)
                    ts = self.tenengrad_score(processed)
                    # 综合得分 = 拉普拉斯方差 × 0.6 + Tenengrad × 0.4
                    combined = es * 0.6 + ts * 0.4

                    combo_desc = f"SR={sr_name} | bin={bin_name} | denoise={denoise}"

                    all_scores.append({
                        "sr": sr_name,
                        "binarize": bin_name,
                        "denoise": denoise,
                        "laplacian_var": round(es, 4),
                        "tenengrad": round(ts, 4),
                        "combined": round(combined, 4),
                    })

                    if combined > best_score:
                        best_score = combined
                        best_image = processed
                        best_combo = combo_desc

        if verbose:
            print(f"\n{'='*60}")
            print(f"  [预处理] 自动选择最佳组合")
            print(f"{'='*60}")
            print(f"  评估组合数: {len(all_scores)}")
            print(f"  最佳组合:   {best_combo}")
            print(f"  最佳得分:   {best_score:.2f}")

            # 显示前5名
            sorted_scores = sorted(all_scores, key=lambda x: x["combined"], reverse=True)
            print(f"\n  Top 5 组合:")
            for i, s in enumerate(sorted_scores[:5]):
                print(f"    {i+1}. SR={s['sr']:10s} bin={s['binarize']:14s} "
                      f"denoise={str(s['denoise']):5s} → {s['combined']:.2f}")

        return {
            "best_image": best_image,
            "best_score": best_score,
            "best_combination": best_combo,
            "all_scores": all_scores,
            "gray": gray,
        }

    def preprocess(self, image: np.ndarray, verbose: bool = True) -> np.ndarray:
        """一键预处理：自动选择并返回最佳预处理图像。

        Args:
            image: 输入图像 (H, W, 3) BGR
            verbose: 是否打印详细信息

        Returns:
            最佳预处理后的二值图
        """
        result = self.auto_select_best(image, verbose=verbose)
        return result["best_image"]


# ============================================================
# 2. MultiPassOCR 类
# ============================================================

class MultiPassOCR:
    """多遍OCR引擎：PSM 3/4/6 三种模式 + 投票/合并 + 字符级置信度。

    工作原理：
      1. 对同一张预处理图像，分别用 PSM 3, 4, 6 跑 OCR
      2. 获取每遍结果的逐词/逐字符置信度
      3. 通过投票合并多遍结果（保留高置信度结果）
      4. 输出合并后的文本 + 置信度标注
    """

    PSM_MODES = {
        3: "Fully automatic page segmentation (PSM 3)",
        4: "Assume a single column of text (PSM 4)",
        6: "Assume a uniform block of text (PSM 6)",
    }

    def __init__(self, lang: str = "eng", oem: int = 3):
        """
        Args:
            lang: OCR 语言（eng, chi_sim+eng 等）
            oem: OCR Engine Mode (3 = LSTM only, 默认)
        """
        self.lang = lang
        self.oem = oem

    def ocr_single(
        self,
        image: np.ndarray,
        psm: int,
        get_data: bool = True,
    ) -> dict[str, Any]:
        """单遍OCR。

        Args:
            image: 输入图像（灰度或二值）
            psm: Page Segmentation Mode (3/4/6)
            get_data: 是否获取详细数据（词级置信度）

        Returns:
            {
                'text': str,
                'conf': float,          # 平均置信度
                'words': list[dict],    # 词级数据 [{text, conf, bbox}]
                'psm': int,
            }
        """
        config = f"--oem {self.oem} --psm {psm}"

        # 基本文本
        text = pytesseract.image_to_string(image, lang=self.lang, config=config)

        # 详细数据（词级）
        words = []
        avg_conf = 0.0

        if get_data:
            try:
                data = pytesseract.image_to_data(
                    image, lang=self.lang, config=config,
                    output_type=Output.DICT,
                )
                confs = []
                for i in range(len(data["text"])):
                    word_conf = int(data["conf"][i])
                    word_text = data["text"][i].strip()
                    if word_text and word_conf >= 0:
                        words.append({
                            "text": word_text,
                            "conf": word_conf,
                            "bbox": {
                                "x": data["left"][i],
                                "y": data["top"][i],
                                "w": data["width"][i],
                                "h": data["height"][i],
                            },
                        })
                        confs.append(word_conf)

                avg_conf = float(np.mean(confs)) if confs else 0.0
            except Exception:
                avg_conf = 0.0

        return {
            "text": text.strip(),
            "conf": avg_conf,
            "words": words,
            "psm": psm,
        }

    def ocr_multipass(
        self,
        image: np.ndarray,
        psm_list: list[int] | None = None,
        verbose: bool = True,
    ) -> dict[str, Any]:
        """多遍OCR + 投票合并。

        Args:
            image: 输入图像
            psm_list: PSM 模式列表，默认 [3, 4, 6]
            verbose: 是否打印详细信息

        Returns:
            {
                'merged_text': str,         # 合并后的最佳文本
                'overall_conf': float,      # 综合置信度
                'passes': list[dict],       # 各遍结果
                'low_conf_regions': list,   # 低置信度区域
            }
        """
        if psm_list is None:
            psm_list = [3, 4, 6]

        passes = []
        for psm in psm_list:
            result = self.ocr_single(image, psm)
            passes.append(result)

        # 投票合并：逐行对齐多遍结果，保留最高置信度的行
        merged_lines = self._vote_merge(passes)

        # 综合置信度 = 各遍平均置信度的加权平均
        confs = [p["conf"] for p in passes if p["conf"] > 0]
        overall_conf = float(np.mean(confs)) if confs else 0.0

        # 低置信度区域
        low_conf_regions = self._find_low_confidence(passes, threshold=50)

        if verbose:
            print(f"\n{'='*60}")
            print(f"  [多遍OCR] PSM模式: {psm_list}")
            print(f"{'='*60}")
            for p in passes:
                print(f"  PSM {p['psm']:1d} | 置信度: {p['conf']:5.1f}% | "
                      f"单词数: {len(p['words']):3d} | "
                      f"文本预览: {p['text'][:60]}...")
            print(f"\n  综合置信度: {overall_conf:.1f}%")
            print(f"  低置信度区域: {len(low_conf_regions)} 处")
            print(f"  合并文本:\n{merged_lines[:500]}")

        return {
            "merged_text": merged_lines,
            "overall_conf": overall_conf,
            "passes": passes,
            "low_conf_regions": low_conf_regions,
        }

    def _vote_merge(self, passes: list[dict]) -> str:
        """投票合并多遍OCR文本。

        策略：
        1. 将各遍结果按行分割
        2. 对每行使用编辑距离找最佳匹配
        3. 取最高置信度对应的行

        Args:
            passes: 多遍OCR结果列表

        Returns:
            合并后的文本
        """
        # 简单策略：取平均置信度最高的那遍作为主结果
        # 然后在其他遍中找到补充文本
        if not passes:
            return ""

        # 按置信度排序
        sorted_passes = sorted(passes, key=lambda x: x["conf"], reverse=True)

        # 主文本
        primary_text = sorted_passes[0]["text"]

        # 如果有高置信度的补充行，追加
        all_lines = []
        seen_lines = set()

        for p in sorted_passes:
            for line in p["text"].split("\n"):
                line_stripped = line.strip()
                if line_stripped and line_stripped not in seen_lines:
                    all_lines.append(line_stripped)
                    seen_lines.add(line_stripped)

        return "\n".join(all_lines)

    def _find_low_confidence(
        self, passes: list[dict], threshold: float = 50.0
    ) -> list[dict]:
        """找出低置信度区域供人工复核。

        Args:
            passes: 多遍OCR结果
            threshold: 置信度阈值（低于此值标记）

        Returns:
            低置信度区域列表
        """
        low_conf = []
        for p in passes:
            for w in p["words"]:
                if w["conf"] < threshold:
                    low_conf.append({
                        "psm": p["psm"],
                        "text": w["text"],
                        "conf": w["conf"],
                        "bbox": w["bbox"],
                    })
        return low_conf


# ============================================================
# 3. DomainCorrector 类
# ============================================================

class DomainCorrector:
    """电池领域纠错器：字典纠错 + 数值合理性检查 + 正则模式匹配。

    针对电池研究文献/测试报告中常见的OCR错误进行后处理：
      - 缩写展开（FCE → First Cycle Efficiency）
      - 常见错字纠正（config → configuration）
      - 数值合理性检查（效率不能 >100%）
      - 单位模式识别和标准化
    """

    # 电池领域纠错字典
    CORRECTION_DICT: dict[str, str] = {
        # 电化学术语
        "FCE": "First Cycle Efficiency",
        "ICE": "Initial Coulombic Efficiency",
        "CE": "Coulombic Efficiency",
        "PL": "Pre-lithiation",
        "Prelith": "Pre-lithiation",
        "SEI": "Solid Electrolyte Interphase",
        "CEI": "Cathode Electrolyte Interphase",
        "OCV": "Open Circuit Voltage",
        "EIS": "Electrochemical Impedance Spectroscopy",
        "CV": "Cyclic Voltammetry",
        "GCD": "Galvanostatic Charge-Discharge",
        "SOC": "State of Charge",
        "DOD": "Depth of Discharge",
        "NMC": "LiNiₓMnᵧCo₂O₂ (NMC)",
        "LFP": "LiFePO₄ (LFP)",
        "LCO": "LiCoO₂ (LCO)",
        "NCA": "LiNiCoAlO₂ (NCA)",
        "GITT": "Galvanostatic Intermittent Titration Technique",
        "XRD": "X-ray Diffraction",
        "XPS": "X-ray Photoelectron Spectroscopy",
        "SEM": "Scanning Electron Microscopy",
        "TEM": "Transmission Electron Microscopy",
        "DOE": "Design of Experiment",
        "DFT": "Density Functional Theory",
        "DEC": "Diethyl Carbonate",
        "EC": "Ethylene Carbonate",
        "DMC": "Dimethyl Carbonate",
        "EMC": "Ethyl Methyl Carbonate",
        "FEC": "Fluoroethylene Carbonate",
        "VC": "Vinylene Carbonate",
        "LiPF6": "LiPF₆",
        "PVDF": "Polyvinylidene Fluoride",
        "NMP": "N-Methyl-2-pyrrolidone",

        # OCR常见错误纠正
        "config": "configuration",
        "configs": "configurations",
        "posttreatment": "post-treatment",
        "pretreatment": "pre-treatment",
        "postannealing": "post-annealing",
        "coprecipitation": "co-precipitation",
        "codoping": "co-doping",
        "prelithiation": "Pre-lithiation",
        "Prelithiation": "Pre-lithiation",
        "prelithiated": "pre-lithiated",

        # 希腊字母替换（tesseract常见错误）
        "a-MnO2": "α-MnO₂",
        "B-Ni(OH)2": "β-Ni(OH)₂",
        "y-Fe2O3": "γ-Fe₂O₃",
        "delta-MnO2": "δ-MnO₂",
        "LiNi0": "LiNi₀",
        "LiCoO2": "LiCoO₂",
        "MnO2": "MnO₂",
        "TiO2": "TiO₂",
        "SiO2": "SiO₂",
        "Fe2O3": "Fe₂O₃",
        "Co3O4": "Co₃O₄",
        "Li2O": "Li₂O",
        "LiOH": "LiOH",
        "Li2CO3": "Li₂CO₃",
    }

    # 正则模式：数值 + 单位
    VALUE_UNIT_PATTERNS: list[tuple[str, str]] = [
        # (正则, 描述)
        (r"(\d+\.?\d*)\s*(mAh/g|mAh·g⁻¹|mA h g-1|mAh g-1)", "比容量"),
        (r"(\d+\.?\d*)\s*(%)", "百分比"),
        (r"(\d+\.?\d*)\s*(V)\b", "电压"),
        (r"(\d+\.?\d*)\s*(mA/g|mA·g⁻¹|mA g-1)", "电流密度"),
        (r"(\d+\.?\d*)\s*(°C|℃)", "温度"),
        (r"(\d+\.?\d*)\s*(h|hours?|hrs?)", "时间"),
        (r"(\d+\.?\d*)\s*(cycles?|圈)", "循环次数"),
        (r"(\d+\.?\d*)\s*(nm|μm|mm|cm)", "尺寸"),
        (r"(\d+\.?\d*)\s*(wt%|wt\.%|weight%)", "质量分数"),
        (r"(\d+\.?\d*)\s*(S/cm|S·cm⁻¹)", "电导率"),
    ]

    def __init__(self):
        self.corrections_made: list[dict] = []
        self.numerical_warnings: list[dict] = []

    def correct_text(self, text: str, aggressive: bool = False) -> str:
        """对OCR文本进行领域纠错。

        Args:
            text: OCR原始文本
            aggressive: 是否进行激进纠错（更多替换）

        Returns:
            纠错后的文本
        """
        self.corrections_made = []
        corrected = text

        # 步骤1：词典纠错（针对完整单词/缩写）
        # 注意：先匹配长词/复合词，再匹配短词，避免短词覆盖长词部分
        # 对常见复合缩写（如 EC/DEC, EC/DMC/EMC）做保护性替换
        compound_patterns = [
            (r"\bEC/DEC\b", "EC/DEC (Ethylene Carbonate/Diethyl Carbonate)"),
            (r"\bEC/DMC\b", "EC/DMC (Ethylene Carbonate/Dimethyl Carbonate)"),
            (r"\bEC/EMC\b", "EC/EMC (Ethylene Carbonate/Ethyl Methyl Carbonate)"),
        ]
        for pattern_str, replacement in compound_patterns:
            corrected = re.sub(pattern_str, replacement, corrected)

        for wrong, correct in self.CORRECTION_DICT.items():
            # 使用单词边界匹配，避免部分匹配
            # 但跳过已在复合词中展开的缩写（如 EC/DEC 中的 EC）
            if wrong in ("EC", "DEC", "DMC", "EMC"):
                # 对于复合缩写中的组分，只在独立出现时替换
                pattern = re.compile(r"(?<!/)\b" + re.escape(wrong) + r"\b(?!/)")
            else:
                pattern = re.compile(r"\b" + re.escape(wrong) + r"\b")
            matches = pattern.findall(corrected)
            if matches:
                corrected = pattern.sub(correct, corrected)
                self.corrections_made.append({
                    "type": "dict",
                    "original": wrong,
                    "corrected": correct,
                    "count": len(matches),
                })

        # 步骤2：数值合理性检查
        corrected = self._check_numerical_reasonableness(corrected)

        # 步骤3：提取并规范化数值+单位
        corrected = self._normalize_units(corrected)

        # 步骤4：激进模式 - 额外纠正
        if aggressive:
            corrected = self._aggressive_corrections(corrected)

        return corrected

    def _check_numerical_reasonableness(self, text: str) -> str:
        """检查数值是否在电池领域的合理范围内。

        Args:
            text: 文本

        Returns:
            可能被标记的文本（添加警告标记）
        """
        self.numerical_warnings = []

        # 检查效率值
        efficiency_pattern = re.compile(
            r"(?:ICE|CE|FCE|efficiency|Efficiency|库仑效率|首效)\s*[:=]?\s*(\d+\.?\d*)\s*%",
            re.IGNORECASE,
        )
        for match in efficiency_pattern.finditer(text):
            val = float(match.group(1))
            if val < 0 or val > 100:
                self.numerical_warnings.append({
                    "type": "efficiency_out_of_range",
                    "value": val,
                    "context": match.group(0),
                    "message": f"效率值 {val}% 超出合理范围 [0, 100]%",
                })

        # 检查比容量
        capacity_pattern = re.compile(
            r"(?:capacity|容量|discharge|charge)\s*[:=]?\s*(\d+\.?\d*)\s*(?:mAh/g|mAh·g⁻¹)",
            re.IGNORECASE,
        )
        for match in capacity_pattern.finditer(text):
            val = float(match.group(1))
            lo, hi = BATTERY_CONSTRAINTS["capacity"]
            if val < lo or val > hi:
                self.numerical_warnings.append({
                    "type": "capacity_out_of_range",
                    "value": val,
                    "context": match.group(0),
                    "message": f"比容量 {val} mAh/g 超出合理范围 [{lo}, {hi}] mAh/g",
                })

        return text

    def _normalize_units(self, text: str) -> str:
        """规范化数值+单位表示。

        例如: "1300 mAh/g" → "1300 mAh·g⁻¹"
        """
        # 比容量标准化
        text = re.sub(r"(\d+\.?\d*)\s*mAh/g", r"\1 mAh·g⁻¹", text)
        text = re.sub(r"(\d+\.?\d*)\s*mA h g-1", r"\1 mAh·g⁻¹", text)
        text = re.sub(r"(\d+\.?\d*)\s*mAh g-1", r"\1 mAh·g⁻¹", text)

        # 电流密度标准化
        text = re.sub(r"(\d+\.?\d*)\s*mA/g", r"\1 mA·g⁻¹", text)

        # 电导率标准化
        text = re.sub(r"(\d+\.?\d*)\s*S/cm", r"\1 S·cm⁻¹", text)

        return text

    def _aggressive_corrections(self, text: str) -> str:
        """激进纠错：针对常见OCR字符混淆。

        Tesseract常见混淆：
          - 0 ↔ O, 1 ↔ l/I, 2 ↔ Z, 5 ↔ S, 8 ↔ B
          - 仅在非纯数字上下文中纠正
        """
        # 不在数字开头的 l/I 替换
        # 此策略较激进，仅在 aggressive=True 时启用
        corrections = [
            (r"(?<!\d)1(?!\d)(?=[a-zA-Z]{2,})", "l"),   # 1ike → like
            (r"(?<!\d)0(?!\d)(?=[a-zA-Z]{2,})", "O"),   # 0pen → Open
        ]

        for pattern_str, replacement in corrections:
            text = re.sub(pattern_str, replacement, text)

        return text

    def extract_structured_data(self, text: str) -> dict[str, Any]:
        """从文本中提取结构化电池数据。

        Args:
            text: OCR文本

        Returns:
            结构化数据字典
        """
        structured: dict[str, Any] = {}

        # 提取效率
        eff_match = re.search(
            r"(?:ICE|CE|FCE|efficiency|Efficiency|库仑效率|首效|效率)\s*[:=]?\s*(\d+\.?\d*)\s*%",
            text, re.IGNORECASE,
        )
        if eff_match:
            structured["efficiency_percent"] = float(eff_match.group(1))

        # 提取比容量
        cap_matches = re.findall(
            r"(\d+\.?\d*)\s*(?:mAh/g|mAh·g⁻¹|mAh g-1|mA h g-1)",
            text, re.IGNORECASE,
        )
        if cap_matches:
            structured["capacities_mAh_g"] = [float(m) for m in cap_matches]

        # 提取电压
        volt_matches = re.findall(
            r"(\d+\.?\d*)\s*V\b", text,
        )
        if volt_matches:
            structured["voltages_V"] = [float(m) for m in volt_matches]

        # 提取电流密度
        curr_matches = re.findall(
            r"(\d+\.?\d*)\s*(?:mA/g|mA·g⁻¹|mA g-1)",
            text, re.IGNORECASE,
        )
        if curr_matches:
            structured["current_densities_mA_g"] = [float(m) for m in curr_matches]

        # 提取温度
        temp_matches = re.findall(
            r"(\d+\.?\d*)\s*(?:°C|℃)", text,
        )
        if temp_matches:
            structured["temperatures_C"] = [float(m) for m in temp_matches]

        # 提取循环数
        cycle_matches = re.findall(
            r"(\d+)\s*(?:cycles?|圈)", text, re.IGNORECASE,
        )
        if cycle_matches:
            structured["cycles"] = [int(m) for m in cycle_matches]

        return structured


# ============================================================
# 4. TableExtractor 类
# ============================================================

class TableExtractor:
    """表格提取器：检测表格线 → 分割单元格 → 逐格OCR → 重建DataFrame。

    适用于科学图表中的表格（带水平和垂直边框线）。
    """

    def __init__(self, ocr_engine: MultiPassOCR | None = None):
        """
        Args:
            ocr_engine: MultiPassOCR 实例（用于单元格OCR）
        """
        self.ocr_engine = ocr_engine or MultiPassOCR()

    def detect_table_lines(
        self,
        image: np.ndarray,
        min_line_length_ratio: float = 0.3,
    ) -> tuple[np.ndarray, np.ndarray]:
        """检测表格的水平和垂直线。

        Args:
            image: 灰度图或二值图 (H, W), uint8
            min_line_length_ratio: 最小线长比例（相对于图像尺寸）

        Returns:
            (horizontal_lines_mask, vertical_lines_mask)
        """
        h, w = image.shape[:2]

        # 二值化（如果输入不是二值图）
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # 确保是二值图
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # 检测水平线
        h_kernel_len = max(int(w * 0.05), 20)
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_kernel_len, 1))
        h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)

        # 检测垂直线
        v_kernel_len = max(int(h * 0.05), 20)
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_kernel_len))
        v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)

        return h_lines, v_lines

    def find_cells(
        self,
        h_lines: np.ndarray,
        v_lines: np.ndarray,
        image_shape: tuple | None = None,
        min_area_ratio: float = 0.001,
        max_area_ratio: float = 0.9,
    ) -> list[dict]:
        """通过水平和垂直线交点分割单元格。

        Args:
            h_lines: 水平线掩码
            v_lines: 垂直线掩码
            image_shape: 图像形状 (h, w)，用于过滤全图轮廓
            min_area_ratio: 最小单元格面积比例
            max_area_ratio: 最大单元格面积比例（排除全图轮廓）

        Returns:
            单元格列表 [{'bbox': (x, y, w, h), 'area': int}]
        """
        # 合并水平和垂直线
        table_mask = cv2.bitwise_or(h_lines, v_lines)

        # 检查是否有实际的线条被检测到
        if np.sum(table_mask) == 0:
            # 没有检测到表格线
            return []

        # 查找轮廓（单元格是白色背景区域）
        contours, _ = cv2.findContours(
            cv2.bitwise_not(table_mask), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
        )

        h, w = image_shape if image_shape else (table_mask.shape[0], table_mask.shape[1])
        total_area = h * w
        min_area = total_area * min_area_ratio
        max_area = total_area * max_area_ratio

        cells = []
        for contour in contours:
            x, y, cw, ch = cv2.boundingRect(contour)
            area = cw * ch
            # 过滤太小区域和全图轮廓
            if min_area < area < max_area and cw > 20 and ch > 10:
                cells.append({
                    "bbox": (x, y, cw, ch),
                    "area": area,
                })

        # 按位置排序（从上到下，从左到右）
        cells.sort(key=lambda c: (c["bbox"][1], c["bbox"][0]))

        return cells

    def ocr_cell(
        self,
        image: np.ndarray,
        bbox: tuple[int, int, int, int],
        padding: int = 3,
    ) -> str:
        """对单个单元格进行OCR。

        Args:
            image: 完整图像（灰度/二值）
            bbox: (x, y, w, h)
            padding: 单元格内边距

        Returns:
            OCR识别的文本
        """
        x, y, w, h = bbox
        # 加padding避免切到文字边缘
        x1 = max(x - padding, 0)
        y1 = max(y - padding, 0)
        x2 = min(x + w + padding, image.shape[1])
        y2 = min(y + h + padding, image.shape[0])

        cell_img = image[y1:y2, x1:x2]

        # 确保不是空的
        if cell_img.size == 0:
            return ""

        # 用PSM 6（假设为均匀文本块）OCR
        config = f"--oem 3 --psm 6"
        text = pytesseract.image_to_string(cell_img, lang="eng", config=config)
        return text.strip()

    def extract_table(
        self,
        image: np.ndarray,
        verbose: bool = True,
    ) -> pd.DataFrame:
        """完整表格提取流程。

        Args:
            image: 输入图像（BGR或灰度）
            verbose: 是否打印详细信息

        Returns:
            重建的DataFrame
        """
        # 灰度化
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # 步骤1：检测线条
        h_lines, v_lines = self.detect_table_lines(gray)

        # 步骤2：找单元格
        cells = self.find_cells(h_lines, v_lines, image_shape=gray.shape[:2])

        if verbose:
            print(f"\n{'='*60}")
            print(f"  [表格提取]")
            print(f"{'='*60}")
            print(f"  检测到 {len(cells)} 个有效单元格")

        # 如果图形检测失败（<5个单元格），回退到文本解析
        if len(cells) < 5:
            if verbose:
                print(f"  单元格不足，切换到文本解析模式")
            return self._parse_table_from_text(gray, verbose=verbose)

        # 步骤3：按行分组（相近y坐标的归为同一行）
        rows = self._group_cells_by_row(cells)

        # 步骤4：对每行按x排序
        table_data = []
        for row_idx, row_cells in enumerate(rows):
            row_cells.sort(key=lambda c: c["bbox"][0])  # 按x排序
            row_data = []
            for col_idx, cell in enumerate(row_cells):
                text = self.ocr_cell(image, cell["bbox"])
                row_data.append(text)
            table_data.append(row_data)

        # 步骤5：构建DataFrame
        if not table_data:
            return pd.DataFrame()

        # 对齐列数（取最大列数）
        max_cols = max(len(row) for row in table_data)
        aligned_data = []
        for row in table_data:
            while len(row) < max_cols:
                row.append("")
            aligned_data.append(row[:max_cols])

        # 尝试将第一行作为表头
        if len(aligned_data) > 1:
            columns = aligned_data[0]
            df = pd.DataFrame(aligned_data[1:], columns=columns)
        else:
            df = pd.DataFrame(aligned_data)

        if verbose:
            print(f"  重建表格: {df.shape[0]} 行 × {df.shape[1]} 列")
            print(f"\n  预览:\n{df.head(10).to_string()}")

        return df

    @staticmethod
    def _parse_table_from_text(
        image: np.ndarray,
        verbose: bool = True,
    ) -> pd.DataFrame:
        """从OCR文本中解析表格数据（回退方案）。

        对完整图像运行OCR，检测表格行（由数字列组成的行），
        解析为DataFrame。

        Args:
            image: 灰度图
            verbose: 是否打印详细信息

        Returns:
            解析出的DataFrame
        """
        # 对全图跑OCR（PSM 6 适合块状文本）
        full_text = pytesseract.image_to_string(image, lang="eng", config="--psm 6")
        lines = full_text.strip().split("\n")

        if verbose:
            print(f"  全图OCR获取 {len(lines)} 行文本，开始解析表格...")

        # 策略：找到包含多个数字的"数据行"（至少3个数字）
        # 这些行很可能是表格的数据行
        table_lines = []
        header_line = ""
        header_idx = -1

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue

            # 检测数字（含小数点）
            numbers = re.findall(r"\d+\.?\d*", stripped)

            # 如果有足够数字 → 数据行
            if len(numbers) >= 3:
                if header_idx < 0 and i > 0:
                    # 前一行可能是表头
                    header_line = lines[i - 1].strip()
                    header_idx = i - 1
                table_lines.append(stripped)
            # 检测表头关键词
            elif re.search(
                r"(?:Sample|ICE|Charge|Discharge|Capacity|Efficiency|"
                r"Irreversible|Cycle|CE\b|Voltage|Current|mAh)",
                stripped, re.IGNORECASE,
            ):
                if header_idx < 0:
                    header_line = stripped
                    header_idx = i

        if verbose:
            print(f"  识别到 {len(table_lines)} 行表格数据")

        if len(table_lines) < 2:
            # 太少数据行，返回纯文本
            return pd.DataFrame({"ocr_text": [full_text]})

        # 解析表头
        if header_line and header_idx >= 0:
            # 将表头拆分为列名
            # 移除表格前缀（如 "Table 1."）
            header_clean = re.sub(r"^Table\s*\d+[\.:]\s*", "", header_line, flags=re.IGNORECASE)

            # 智能列拆分策略：
            # 1. 先用数据行的列数推断实际列数
            # 2. 对表头按推断列数进行split

            # 先分析数据行以确定列结构
            sample_data_parts = []
            for tline in table_lines[:3]:  # 看前3行数据
                if tline.strip() == header_line.strip():
                    continue
                parts = TableExtractor._smart_split_line(tline)
                sample_data_parts.append(parts)

            if sample_data_parts:
                # 使用数据行中最常见的列数
                col_counts = [len(p) for p in sample_data_parts]
                most_common_cols = max(set(col_counts), key=col_counts.count)

                # 对表头按相同策略拆分
                header_parts = TableExtractor._smart_split_line(header_clean)
                if len(header_parts) < most_common_cols:
                    header_parts = re.split(r"\s{2,}|\t|\|", header_clean)
                    header_parts = [h.strip() for h in header_parts if h.strip()]
                columns = header_parts
            else:
                columns = re.split(r"\s{2,}|\t|\|", header_clean)
                columns = [c.strip() for c in columns if c.strip()]
        else:
            columns = [f"Col_{j}" for j in range(10)]

        # 解析数据行
        data_rows = []
        for line in table_lines:
            # 跳过表头行本身
            if line.strip() == header_line.strip():
                continue
            # 使用智能拆分
            cells = TableExtractor._smart_split_line(line)
            if cells:
                data_rows.append(cells)

        # 对齐列数
        if data_rows:
            max_cols = max(len(row) for row in data_rows)
            max_cols = max(max_cols, len(columns))
            # 扩展columns
            while len(columns) < max_cols:
                columns.append(f"Col_{len(columns)}")
            columns = columns[:max_cols]
            # 扩展data_rows
            for row in data_rows:
                while len(row) < max_cols:
                    row.append("")
            df = pd.DataFrame(data_rows, columns=columns)
        else:
            df = pd.DataFrame(columns=columns)

        # 尝试数值转换
        for col in df.columns:
            try:
                df[col] = pd.to_numeric(df[col])
            except (ValueError, TypeError):
                pass  # 保留为字符串

        if verbose:
            print(f"  重建表格: {df.shape[0]} 行 × {df.shape[1]} 列")
            print(f"\n  预览:\n{df.to_string()}")

        return df

    @staticmethod
    def _smart_split_line(line: str) -> list[str]:
        """智能拆分表格行：优先用多空格，回退单空格拆分。

        策略：数字之间用单空格拆分（如 "78.5 1320.4 1036.5"），
        文本之间优先保留多词单元（如 "1st Charge"）。

        Args:
            line: 表格行文本

        Returns:
            拆分后的单元格列表
        """
        # 先用连续多空格拆分
        parts = re.split(r"\s{2,}|\t|\|", line.strip())
        if len(parts) >= 2:
            return [p.strip() for p in parts if p.strip()]

        # 回退：用单空格拆分
        parts = re.split(r"\s+", line.strip())
        return [p.strip() for p in parts if p.strip()]

    def _group_cells_by_row(
        self,
        cells: list[dict],
        y_tolerance: int = 10,
    ) -> list[list[dict]]:
        """将单元格按行分组（y坐标相近的归为同一行）。

        Args:
            cells: 单元格列表
            y_tolerance: y坐标容差（像素）

        Returns:
            按行分组后的单元格列表
        """
        if not cells:
            return []

        # 已按y排序
        rows = []
        current_row = [cells[0]]
        current_y = cells[0]["bbox"][1]

        for cell in cells[1:]:
            y = cell["bbox"][1]
            if abs(y - current_y) <= y_tolerance:
                current_row.append(cell)
            else:
                rows.append(current_row)
                current_row = [cell]
                current_y = y

        if current_row:
            rows.append(current_row)

        return rows


# ============================================================
# 5. ChartOCRPipeline 主流水线
# ============================================================

class ChartOCRPipeline:
    """完整图表OCR智能流水线。

    流程：
      (1) 加载图像
      (2) 预处理（ImagePreprocessor）
      (3) 多遍OCR（MultiPassOCR）
      (4) 领域纠错（DomainCorrector）
      (5) 表格提取（TableExtractor）
      (6) 质量评分
      (7) 输出（JSON + DataFrame + 报告）
    """

    def __init__(
        self,
        scale_factor: float = 2.0,
        lang: str = "eng",
        verbose: bool = True,
    ):
        """
        Args:
            scale_factor: 超分辨率倍数
            lang: OCR 语言
            verbose: 是否打印详细信息
        """
        self.scale_factor = scale_factor
        self.lang = lang
        self.verbose = verbose

        # 初始化各模块
        self.preprocessor = ImagePreprocessor(scale_factor=scale_factor)
        self.ocr_engine = MultiPassOCR(lang=lang)
        self.corrector = DomainCorrector()
        self.table_extractor = TableExtractor(ocr_engine=self.ocr_engine)

        # 结果存储
        self.raw_image: np.ndarray | None = None
        self.preprocessed_image: np.ndarray | None = None
        self.ocr_result: dict | None = None
        self.corrected_text: str = ""
        self.dataframe: pd.DataFrame | None = None
        self.structured_data: dict = {}
        self.quality_report: dict = {}

    def load_image(self, image_path: str | Path) -> np.ndarray:
        """加载图像。

        Args:
            image_path: 图像路径

        Returns:
            BGR图像 (H, W, 3)
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"图像不存在: {path}")

        image = cv2.imread(str(path))
        if image is None:
            raise ValueError(f"无法读取图像: {path}")

        if self.verbose:
            h, w = image.shape[:2]
            print(f"\n{'='*60}")
            print(f"  [加载图像] {path.name}")
            print(f"{'='*60}")
            print(f"  尺寸: {w}×{h} 像素")
            print(f"  通道: {image.shape[2] if len(image.shape) == 3 else 1}")

        self.raw_image = image
        return image

    def run(self, image_path: str | Path) -> dict[str, Any]:
        """运行完整OCR流水线。

        Args:
            image_path: 图像路径

        Returns:
            完整结果字典
        """
        print("\n" + "█" * 60)
        print("█  图表OCR智能流水线 — 启动")
        print("█" * 60)

        # ---- 步骤1：加载图像 ----
        image = self.load_image(image_path)

        # ---- 步骤2：预处理 ----
        preprocess_result = self.preprocessor.auto_select_best(image, verbose=self.verbose)
        self.preprocessed_image = preprocess_result["best_image"]

        # ---- 步骤3：多遍OCR ----
        self.ocr_result = self.ocr_engine.ocr_multipass(
            self.preprocessed_image,
            psm_list=[3, 4, 6],
            verbose=self.verbose,
        )

        # ---- 步骤4：领域纠错 ----
        raw_text = self.ocr_result["merged_text"]
        self.corrected_text = self.corrector.correct_text(raw_text)

        if self.verbose:
            print(f"\n{'='*60}")
            print(f"  [领域纠错]")
            print(f"{'='*60}")
            print(f"  纠错数: {len(self.corrector.corrections_made)}")
            for c in self.corrector.corrections_made:
                print(f"    {c['original']} → {c['corrected']} (x{c['count']})")
            if self.corrector.numerical_warnings:
                print(f"  数值警告: {len(self.corrector.numerical_warnings)}")
                for w in self.corrector.numerical_warnings:
                    print(f"    ⚠ {w['message']}")

        # ---- 步骤5：提取结构化数据 ----
        self.structured_data = self.corrector.extract_structured_data(self.corrected_text)

        if self.verbose:
            print(f"\n  结构化数据:")
            for key, val in self.structured_data.items():
                print(f"    {key}: {val}")

        # ---- 步骤6：表格提取 ----
        self.dataframe = self.table_extractor.extract_table(image, verbose=self.verbose)

        # ---- 步骤7：质量评分 ----
        self.quality_report = self._compute_quality_score()

        if self.verbose:
            self._print_quality_report()

        # ---- 步骤8：组装结果 ----
        result = {
            "image_path": str(image_path),
            "image_size": {
                "width": image.shape[1],
                "height": image.shape[0],
            },
            "preprocessing": {
                "best_combination": preprocess_result["best_combination"],
                "best_score": preprocess_result["best_score"],
                "top5_combinations": sorted(
                    preprocess_result["all_scores"],
                    key=lambda x: x["combined"], reverse=True,
                )[:5],
            },
            "ocr": {
                "merged_text": self.ocr_result["merged_text"],
                "corrected_text": self.corrected_text,
                "overall_confidence": self.ocr_result["overall_conf"],
                "pass_confidence": [p["conf"] for p in self.ocr_result["passes"]],
                "low_confidence_regions": self.ocr_result["low_conf_regions"],
            },
            "corrections": {
                "count": len(self.corrector.corrections_made),
                "items": self.corrector.corrections_made,
                "numerical_warnings": self.corrector.numerical_warnings,
            },
            "structured_data": self.structured_data,
            "table": self._dataframe_to_dict(),
            "quality_report": self.quality_report,
        }

        return result

    def _compute_quality_score(self) -> dict[str, Any]:
        """计算综合质量评分（0-100）。

        评分维度：
          1. OCR置信度（50分）：平均置信度 / 100 * 50
          2. 文本完整性（20分）：非空行比例 * 20
          3. 数值合理性（15分）：无警告满分，每个警告扣3分
          4. 表格质量（15分）：有表格结构满分，否则0

        Returns:
            质量报告
        """
        # 维度1：OCR置信度
        ocr_conf = self.ocr_result["overall_conf"] if self.ocr_result else 0
        score_conf = min(ocr_conf / 100 * 50, 50)

        # 维度2：文本完整性
        if self.ocr_result:
            lines = [l for l in self.ocr_result["merged_text"].split("\n") if l.strip()]
            total_lines = len(self.ocr_result["merged_text"].split("\n"))
            completeness = len(lines) / max(total_lines, 1)
        else:
            completeness = 0
        score_completeness = completeness * 20

        # 维度3：数值合理性
        num_warnings = len(self.corrector.numerical_warnings)
        score_reasonableness = max(15 - num_warnings * 3, 0)

        # 维度4：表格质量
        df = self.dataframe
        if df is not None and df.shape[0] > 0 and df.shape[1] > 1:
            score_table = 15
        elif df is not None and df.shape[0] > 0:
            score_table = 8
        else:
            score_table = 0

        total = score_conf + score_completeness + score_reasonableness + score_table

        return {
            "total_score": round(total, 1),
            "grade": self._score_to_grade(total),
            "dimensions": {
                "ocr_confidence": round(score_conf, 1),
                "text_completeness": round(score_completeness, 1),
                "numerical_reasonableness": round(score_reasonableness, 1),
                "table_quality": round(score_table, 1),
            },
            "low_confidence_count": len(self.ocr_result["low_conf_regions"]) if self.ocr_result else 0,
            "numerical_warnings_count": num_warnings,
        }

    @staticmethod
    def _score_to_grade(score: float) -> str:
        """分数到等级映射。"""
        if score >= 90:
            return "A (优秀)"
        elif score >= 75:
            return "B (良好)"
        elif score >= 60:
            return "C (合格)"
        elif score >= 40:
            return "D (较差)"
        else:
            return "F (失败)"

    def _print_quality_report(self):
        """打印质量报告。"""
        qr = self.quality_report
        print(f"\n{'='*60}")
        print(f"  [质量评分]")
        print(f"{'='*60}")
        print(f"  综合得分: {qr['total_score']}/100  →  {qr['grade']}")
        print(f"  ─────────────────────────────")
        print(f"  OCR置信度:      {qr['dimensions']['ocr_confidence']:5.1f}/50")
        print(f"  文本完整性:     {qr['dimensions']['text_completeness']:5.1f}/20")
        print(f"  数值合理性:     {qr['dimensions']['numerical_reasonableness']:5.1f}/15")
        print(f"  表格质量:       {qr['dimensions']['table_quality']:5.1f}/15")
        print(f"  ─────────────────────────────")
        print(f"  低置信度区域:   {qr['low_confidence_count']} 处需人工复核")
        print(f"  数值警告:       {qr['numerical_warnings_count']} 处")

    def _dataframe_to_dict(self) -> dict:
        """DataFrame 转可序列化字典。"""
        df = self.dataframe
        if df is None:
            return {"rows": 0, "columns": 0, "data": []}

        return {
            "rows": df.shape[0],
            "columns": df.shape[1],
            "columns_list": list(df.columns) if hasattr(df.columns, 'tolist') else list(df.columns),
            "data": df.values.tolist() if hasattr(df, 'values') else [],
        }

    def export_results(self, output_dir: str | Path | None = None):
        """导出结果到JSON文件。

        Args:
            output_dir: 输出目录，默认为脚本所在目录
        """
        if output_dir is None:
            output_dir = OUTPUT_DIR

        out_path = Path(output_dir)

        # 运行流水线需要先有结果
        if self.ocr_result is None:
            print("⚠ 尚未运行流水线，请先调用 run()")
            return

        # 导出JSON结果
        json_path = out_path / "ocr_pipeline_result.json"
        result = {
            "ocr_text": self.corrected_text,
            "raw_text": self.ocr_result["merged_text"],
            "structured_data": self.structured_data,
            "quality_report": self.quality_report,
            "corrections": self.corrector.corrections_made,
            "low_confidence_regions": [
                {"text": r["text"], "conf": r["conf"], "bbox": r["bbox"]}
                for r in self.ocr_result["low_conf_regions"]
            ],
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n[JSON] 已导出: {json_path}")

        # 导出DataFrame为CSV
        if self.dataframe is not None and self.dataframe.shape[0] > 0:
            csv_path = out_path / "ocr_table_result.csv"
            self.dataframe.to_csv(csv_path, index=False, encoding="utf-8-sig")
            print(f"[CSV]  已导出: {csv_path}")

        # 保存预处理结果图像
        if self.preprocessed_image is not None:
            preproc_path = out_path / "ocr_preprocessed.png"
            cv2.imwrite(str(preproc_path), self.preprocessed_image)
            print(f"[图像] 已导出: {preproc_path}")

        # 保存文本报告
        report_path = out_path / "ocr_report.txt"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("=" * 60 + "\n")
            f.write("  图表OCR智能流水线 — 分析报告\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"质量评分: {self.quality_report['total_score']}/100 "
                    f"({self.quality_report['grade']})\n\n")
            f.write("─" * 60 + "\n")
            f.write("  纠错后的OCR文本\n")
            f.write("─" * 60 + "\n")
            f.write(self.corrected_text + "\n\n")
            f.write("─" * 60 + "\n")
            f.write("  结构化数据\n")
            f.write("─" * 60 + "\n")
            for key, val in self.structured_data.items():
                f.write(f"  {key}: {val}\n")
            f.write("\n─" * 60 + "\n")
            f.write("  低置信度区域（需人工复核）\n")
            f.write("─" * 60 + "\n")
            for r in self.ocr_result["low_conf_regions"]:
                f.write(f"  [{r['conf']:3d}%] {r['text']} @ "
                        f"({r['bbox']['x']},{r['bbox']['y']})\n")
        print(f"[报告] 已导出: {report_path}")


# ============================================================
# 6. 辅助函数：生成合成测试图像
# ============================================================

def generate_alpha173_test_image(output_path: str | Path) -> str:
    """生成模拟 Alpha 173 电池测试图表（用于测试OCR流水线）。

    Args:
        output_path: 输出路径

    Returns:
        图像路径
    """
    from PIL import Image, ImageDraw, ImageFont

    w, h = 1200, 900
    img = Image.new("RGB", (w, h), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 尝试加载中文字体，否则回退到默认
    font_paths = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    font_title = None
    font_body = None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font_title = ImageFont.truetype(fp, 28)
                font_body = ImageFont.truetype(fp, 20)
                font_small = ImageFont.truetype(fp, 16)
                break
            except Exception:
                continue

    if font_body is None:
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_small = font_body

    # ---- 标题 ----
    title = "Alpha 173 — Battery Test Results"
    draw.text((30, 20), title, fill=(0, 0, 0), font=font_title)

    # ---- 样本信息 ----
    info_lines = [
        "Sample ID: Alpha-173",
        "Material: Si/C Composite (Si: 15 wt%)",
        "Electrolyte: 1M LiPF6 in EC/DEC (1:1 v/v) + 5% FEC",
        "Configuration: CR2032 coin cell, Li metal counter electrode",
        "Voltage range: 0.01–1.5 V (vs. Li/Li+)",
        "Current density: 100 mA/g for formation, 200 mA/g for cycling",
        "Post-treatment: Ar 160C pre-lithiation (Li foil, calendaring)",
        "Note: DOE analysis for optimization of Pre-lithiation conditions",
    ]
    y = 70
    for line in info_lines:
        draw.text((30, y), line, fill=(50, 50, 50), font=font_body)
        y += 30

    # ---- 分隔线 ----
    y += 10
    draw.line([(30, y), (w - 30, y)], fill=(0, 0, 0), width=2)
    y += 20

    # ---- 表格 ----
    table_title = "Table 1. Electrochemical Performance Summary"
    draw.text((30, y), table_title, fill=(0, 0, 0), font=font_title)
    y += 45

    # 表格数据
    table_data = [
        ["Sample", "ICE (%)", "1st Charge (mAh/g)", "1st Discharge (mAh/g)",
         "Irreversible (mAh/g)", "CE after 50 cycles (%)"],
        ["Alpha-173-1", "78.5", "1320.4", "1036.5", "283.9", "99.2"],
        ["Alpha-173-2", "81.2", "1298.1", "1054.3", "243.8", "99.5"],
        ["Alpha-173-3", "76.8", "1345.7", "1033.8", "311.9", "98.8"],
        ["Alpha-173-4", "79.9", "1312.0", "1048.5", "263.5", "99.1"],
        ["Alpha-173-5", "80.3", "1287.6", "1034.2", "253.4", "99.4"],
        ["Alpha-173-6", "77.2", "1338.9", "1034.1", "304.8", "98.9"],
        ["Average", "79.0", "1317.1", "1040.2", "276.9", "99.2"],
        ["Std Dev", "1.8", "23.4", "9.4", "27.7", "0.3"],
    ]

    col_widths = [140, 90, 180, 190, 180, 200]
    x_start = 40

    # 表格线
    row_height = 35
    table_y_start = y

    # 画表格
    for row_idx, row in enumerate(table_data):
        row_y = table_y_start + row_idx * row_height
        x_pos = x_start

        # 行背景（交替色）
        if row_idx == 0:
            fill_color = (220, 230, 241)  # 表头蓝底
        elif row_idx % 2 == 0:
            fill_color = (245, 245, 245)
        else:
            fill_color = (255, 255, 255)

        # 画行背景
        draw.rectangle(
            [x_start, row_y, x_start + sum(col_widths), row_y + row_height],
            fill=fill_color,
        )

        for col_idx, cell_text in enumerate(row):
            # 单元格文本
            if row_idx == 0:
                draw.text((x_pos + 5, row_y + 5), cell_text, fill=(0, 0, 0), font=font_small)
            else:
                draw.text((x_pos + 5, row_y + 5), cell_text, fill=(30, 30, 30), font=font_body)

            # 垂直线
            draw.line(
                [(x_pos, row_y), (x_pos, row_y + row_height)],
                fill=(180, 180, 180), width=1,
            )
            x_pos += col_widths[col_idx]

        # 水平线
        draw.line(
            [(x_start, row_y), (x_start + sum(col_widths), row_y)],
            fill=(180, 180, 180), width=1,
        )

        # 最后一行水平线
        if row_idx == len(table_data) - 1:
            draw.line(
                [(x_start, row_y + row_height),
                 (x_start + sum(col_widths), row_y + row_height)],
                fill=(180, 180, 180), width=1,
            )

    # 右边界垂直线
    right_x = x_start + sum(col_widths)
    table_y_end = table_y_start + len(table_data) * row_height
    draw.line(
        [(right_x, table_y_start), (right_x, table_y_end)],
        fill=(180, 180, 180), width=1,
    )

    # ---- 底部注释 ----
    y = table_y_end + 20
    draw.line([(30, y), (w - 30, y)], fill=(0, 0, 0), width=2)
    y += 20

    notes = [
        "Notes:",
        "- ICE (Initial Coulombic Efficiency) = 1st discharge / 1st charge x 100%",
        "- Pre-lithiation (PL) was performed at 160C under Ar atmosphere",
        "- FCE (First Cycle Efficiency) is statistically lower for PL samples (p<0.001)",
        "- Post-treatment analysis shows LiOH/Li2CO3 formation on surface",
        "- Low confidence values marked for manual review",
    ]
    for note in notes:
        draw.text((30, y), note, fill=(80, 80, 80), font=font_small)
        y += 24

    # 保存
    out_path = str(Path(output_path))
    img.save(out_path, "JPEG", quality=95)
    print(f"[生成] 合成测试图像: {out_path}")
    return out_path


# ============================================================
# 7. 主函数：测试与验证
# ============================================================

def main():
    """主函数：在 Alpha 173 测试图像上运行完整流水线。"""
    print("\n" + "█" * 60)
    print("█  图表OCR智能流水线 — Alpha 173 验证测试")
    print("█" * 60)

    # 1. 生成合成测试图像（模拟 Alpha 173 电池测试图表）
    test_image_path = str(OUTPUT_DIR / "alpha173_test_chart.jpg")
    if not os.path.exists(test_image_path):
        test_image_path = generate_alpha173_test_image(test_image_path)

    # 2. 运行基础OCR（改进前：直接用Tesseract + PSM 3）
    print("\n" + "=" * 60)
    print("  [基准测试] 改进前：直接Tesseract OCR (PSM 3)")
    print("=" * 60)

    raw_img = cv2.imread(test_image_path)
    if raw_img is not None:
        gray = cv2.cvtColor(raw_img, cv2.COLOR_BGR2GRAY)
        baseline_text = pytesseract.image_to_string(gray, lang="eng", config="--psm 3")
        baseline_conf = MultiPassOCR().ocr_single(gray, psm=3)["conf"]
        print(f"  文本长度: {len(baseline_text)} 字符")
        print(f"  置信度:   {baseline_conf:.1f}%")
        print(f"  文本预览:\n{baseline_text[:400]}")
    else:
        baseline_text = ""
        baseline_conf = 0.0
        print("  ⚠ 无法加载图像进行基准测试")

    # 3. 运行完整流水线
    print("\n" + "=" * 60)
    print("  [改进测试] 完整OCR智能流水线")
    print("=" * 60)

    pipeline = ChartOCRPipeline(scale_factor=2.0, lang="eng", verbose=True)
    result = pipeline.run(test_image_path)

    # 4. 导出结果
    pipeline.export_results()

    # 5. 对比分析
    print("\n" + "█" * 60)
    print("█  改进前后对比分析")
    print("█" * 60)

    print(f"\n{'指标':30s} {'改进前':>15s} {'改进后':>15s} {'提升':>10s}")
    print("-" * 75)

    # OCR置信度对比
    improved_conf = result["ocr"]["overall_confidence"]
    conf_delta = improved_conf - baseline_conf
    print(f"{'OCR置信度':30s} {baseline_conf:14.1f}% {improved_conf:14.1f}% {conf_delta:+9.1f}%")

    # 文本长度对比
    baseline_len = len(baseline_text.strip().split("\n"))
    improved_len = len(result["ocr"]["merged_text"].split("\n"))
    print(f"{'文本行数':30s} {baseline_len:15d} {improved_len:15d} {improved_len-baseline_len:+10d}")

    # 纠错数量
    print(f"{'领域纠错数':30s} {'N/A':>15s} {result['corrections']['count']:15d} {'--':>10s}")

    # 结构化数据提取
    struct_count = len(result["structured_data"])
    print(f"{'结构化字段数':30s} {'0':>15s} {struct_count:15d} {struct_count:+10d}")

    # 质量评分
    quality = result["quality_report"]["total_score"]
    print(f"{'质量评分':30s} {'N/A':>15s} {quality:14.1f}/100 {'--':>10s}")

    print("-" * 75)

    # 6. 最终总结
    print(f"\n{'='*60}")
    print(f"  流水线验证完成！")
    print(f"  输出文件:")
    print(f"    - 测试图像:   {test_image_path}")
    print(f"    - JSON结果:   {OUTPUT_DIR / 'ocr_pipeline_result.json'}")
    print(f"    - CSV表格:    {OUTPUT_DIR / 'ocr_table_result.csv'}")
    print(f"    - 预处理图:   {OUTPUT_DIR / 'ocr_preprocessed.png'}")
    print(f"    - 文本报告:   {OUTPUT_DIR / 'ocr_report.txt'}")
    print(f"{'='*60}")

    return result


# ============================================================
# 8. 程序入口
# ============================================================

if __name__ == "__main__":
    main()
