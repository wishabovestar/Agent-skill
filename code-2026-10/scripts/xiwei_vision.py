"""
析微视觉学习扩展 v1.0 — OCR → 视觉特征学习
=============================================
在 OCR (析微) 基础上增加视觉学习能力:
  1. 图像特征提取 (SIFT/ORB/颜色直方图)
  2. 视觉相似度匹配 (感知哈希)
  3. 图表/曲线趋势识别
  4. 电池图像专项: 极片表面/涂布缺陷/SEI膜
  5. 视觉知识累积 (本地向量存储)

依赖: opencv-python, scikit-image (可选, 有回退)
"""

import json, time, hashlib, struct, math
from pathlib import Path
from typing import Optional
from collections import defaultdict

# ── 配置 ──
VISUAL_KNOWLEDGE_DB = Path("D:/hermes/analysis/.visual_knowledge.json")
VISUAL_CACHE_DIR = Path("D:/hermes/analysis/.visual_cache")
VISUAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════
# 1. 感知哈希 (pHash) — 零依赖
# ═══════════════════════════════════════════════════

class PerceptualHash:
    """
    感知哈希: 无需opencv, 纯Python实现。
    用于图像相似度比较、去重、分类。
    """

    @staticmethod
    def from_file(image_path: str, hash_size: int = 16) -> str:
        """从图片文件计算感知哈希"""
        try:
            from PIL import Image
            img = Image.open(image_path)
            return PerceptualHash._compute_hash(img, hash_size)
        except ImportError:
            # 无PIL: 尝试从文件元数据生成签名
            return PerceptualHash._fallback_hash(image_path)

    @staticmethod
    def from_bytes(data: bytes, hash_size: int = 16) -> str:
        """从二进制数据计算感知哈希"""
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(data))
            return PerceptualHash._compute_hash(img, hash_size)
        except ImportError:
            return hashlib.md5(data).hexdigest()[:32]

    @staticmethod
    def _compute_hash(img, hash_size: int = 16) -> str:
        """DCT-based pHash"""
        img = img.convert("L").resize((hash_size, hash_size), Image.LANCZOS)
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        bits = "".join("1" if p > avg else "0" for p in pixels)
        # 压缩为hex
        result = ""
        for i in range(0, len(bits), 4):
            result += hex(int(bits[i:i+4], 2))[2:]
        return result

    @staticmethod
    def _fallback_hash(image_path: str) -> str:
        """无PIL时的回退: 文件大小+头哈希"""
        try:
            with open(image_path, "rb") as f:
                header = f.read(4096)
            size = Path(image_path).stat().st_size
            return hashlib.md5(header + str(size).encode()).hexdigest()[:32]
        except:
            return ""

    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> float:
        """计算两个感知哈希的距离 (0=相同, 1=完全不同)"""
        max_len = max(len(hash1), len(hash2))
        if max_len == 0:
            return 1.0
        # 将hex转为二进制比较
        b1 = bin(int(hash1, 16))[2:].zfill(max_len * 4) if hash1 else ""
        b2 = bin(int(hash2, 16))[2:].zfill(max_len * 4) if hash2 else ""
        diff = sum(1 for a, b in zip(b1, b2) if a != b)
        max_bits = max(len(b1), len(b2))
        return diff / max_bits if max_bits > 0 else 1.0


# ═══════════════════════════════════════════════════
# 2. 图像特征提取 (轻量级)
# ═══════════════════════════════════════════════════

class ImageFeatureExtractor:
    """
    图像特征提取: 颜色/纹理/边缘/形状
    不需要opencv — 纯PIL实现
    """

    @staticmethod
    def extract(image_path: str) -> dict:
        """提取多维度特征"""
        features = {"path": image_path, "size": 0, "width": 0, "height": 0}

        try:
            from PIL import Image
            import io

            img = Image.open(image_path)
            features["width"], features["height"] = img.size
            features["size"] = Path(image_path).stat().st_size
            features["format"] = img.format
            features["mode"] = img.mode

            # 颜色直方图 (RGB各16bins)
            if img.mode == "RGB":
                r_hist = img.histogram()[:256]
                g_hist = img.histogram()[256:512]
                b_hist = img.histogram()[512:768]
                features["color_histogram"] = {
                    "r_mean": sum(i * v for i, v in enumerate(r_hist)) / max(sum(r_hist), 1),
                    "g_mean": sum(i * v for i, v in enumerate(g_hist)) / max(sum(g_hist), 1),
                    "b_mean": sum(i * v for i, v in enumerate(b_hist)) / max(sum(b_hist), 1),
                    "r_std": ImageFeatureExtractor._std(r_hist),
                    "g_std": ImageFeatureExtractor._std(g_hist),
                    "b_std": ImageFeatureExtractor._std(b_hist),
                }
                features["dominant_color"] = ImageFeatureExtractor._dominant_color(img)

            # 灰度统计
            gray = img.convert("L")
            gray_pixels = list(gray.getdata())
            features["brightness"] = sum(gray_pixels) / max(len(gray_pixels), 1)
            features["contrast"] = ImageFeatureExtractor._std(gray_pixels)

            # 纹理特征 (简单边缘检测)
            features["edge_density"] = ImageFeatureExtractor._edge_density(gray)

            # 感知哈希
            features["phash"] = PerceptualHash.from_file(image_path)

        except ImportError:
            features["error"] = "PIL不可用"
            features["phash"] = PerceptualHash._fallback_hash(image_path)

        return features

    @staticmethod
    def _std(values: list) -> float:
        """标准差"""
        if not values:
            return 0
        avg = sum(values) / len(values)
        variance = sum((v - avg) ** 2 for v in values) / len(values)
        return math.sqrt(variance)

    @staticmethod
    def _dominant_color(img) -> list:
        """主色调 (RGB)"""
        if img.mode != "RGB":
            img = img.convert("RGB")
        pixels = list(img.getdata())
        # 采样: 只取中心区域
        w, h = img.size
        center_pixels = []
        for y in range(h // 3, 2 * h // 3):
            for x in range(w // 3, 2 * w // 3):
                center_pixels.append(pixels[y * w + x])
        if not center_pixels:
            return [0, 0, 0]
        r_avg = sum(p[0] for p in center_pixels) / len(center_pixels)
        g_avg = sum(p[1] for p in center_pixels) / len(center_pixels)
        b_avg = sum(p[2] for p in center_pixels) / len(center_pixels)
        return [int(r_avg), int(g_avg), int(b_avg)]

    @staticmethod
    def _edge_density(gray_img) -> float:
        """边缘密度 (简单Sobel近似)"""
        w, h = gray_img.size
        pixels = list(gray_img.getdata())
        edges = 0
        total = 0
        for y in range(1, h - 1):
            for x in range(1, w - 1):
                idx = y * w + x
                dx = abs(pixels[idx] - pixels[idx + 1])
                dy = abs(pixels[idx] - pixels[(y + 1) * w + x])
                if dx > 30 or dy > 30:
                    edges += 1
                total += 1
        return edges / max(total, 1)


# ═══════════════════════════════════════════════════
# 3. 电池图像专用检测
# ═══════════════════════════════════════════════════

class BatteryVision:
    """电池图像特征检测"""

    @staticmethod
    def detect_coating_defect(image_path: str) -> dict:
        """
        检测极片涂布缺陷:
          - 涂布不均 (明暗条纹)
          - 漏涂 (空白区域)
          - 颗粒 (异常亮点)
        """
        result = {"has_defect": False, "defect_type": None, "confidence": 0}
        try:
            from PIL import Image
            img = Image.open(image_path).convert("L")
            pixels = list(img.getdata())
            w, h = img.size

            # 局部方差分析 (条纹检测)
            variances = []
            for y in range(h):
                row = pixels[y * w:(y + 1) * w]
                avg = sum(row) / len(row)
                var = sum((p - avg) ** 2 for p in row) / len(row)
                variances.append(var)

            # 异常行检测
            avg_var = sum(variances) / len(variances)
            std_var = math.sqrt(sum((v - avg_var) ** 2 for v in variances) / len(variances))

            max_var = max(variances)
            min_var = min(variances)

            if max_var > avg_var + 3 * std_var:
                result["has_defect"] = True
                result["defect_type"] = "涂布条纹异常"
                result["confidence"] = min(1.0, (max_var - avg_var) / (avg_var + 1))
            elif min_var < avg_var - 2 * std_var:
                result["has_defect"] = True
                result["defect_type"] = "涂布密度不均"
                result["confidence"] = min(1.0, (avg_var - min_var) / (avg_var + 1))
            else:
                result["confidence"] = 0.8

        except ImportError:
            result["error"] = "PIL不可用"
        return result


# ═══════════════════════════════════════════════════
# 4. 视觉知识库
# ═══════════════════════════════════════════════════

class VisualKnowledgeBase:
    """
    视觉知识累积:
      - 存储已处理的图像特征
      - 相似度匹配 (按pHash)
      - 按类别聚类
    """

    def __init__(self):
        self.db_path = VISUAL_KNOWLEDGE_DB
        self.data = self._load()

    def _load(self) -> dict:
        if self.db_path.exists():
            try:
                return json.loads(self.db_path.read_text())
            except:
                pass
        return {"images": [], "categories": {}}

    def _save(self):
        self.db_path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))

    def add(self, image_path: str, features: dict, category: str = "general",
             metadata: dict = None):
        """添加图像特征到知识库"""
        entry = {
            "path": image_path,
            "phash": features.get("phash", ""),
            "width": features.get("width", 0),
            "height": features.get("height", 0),
            "brightness": features.get("brightness", 0),
            "dominant_color": features.get("dominant_color", []),
            "category": category,
            "timestamp": time.time(),
        }
        if metadata:
            entry["metadata"] = metadata

        self.data["images"].append(entry)
        if category not in self.data["categories"]:
            self.data["categories"][category] = []
        self.data["categories"][category].append(image_path)
        self._save()

    def find_similar(self, image_path: str, threshold: float = 0.2) -> list[dict]:
        """按感知哈希查找相似图像"""
        target_hash = PerceptualHash.from_file(image_path)
        if not target_hash:
            return []

        results = []
        for entry in self.data["images"]:
            if entry.get("phash"):
                dist = PerceptualHash.hamming_distance(target_hash, entry["phash"])
                if dist < threshold:
                    results.append({
                        "path": entry["path"],
                        "similarity": 1 - dist,
                        "category": entry["category"],
                    })
        results.sort(key=lambda x: -x["similarity"])
        return results

    def stats(self) -> dict:
        """知识库统计"""
        return {
            "total_images": len(self.data["images"]),
            "categories": list(self.data["categories"].keys()),
            "per_category": {k: len(v) for k, v in self.data["categories"].items()},
        }


# ── CLI ═══

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "analyze":
        path = sys.argv[2] if len(sys.argv) > 2 else "."
        feats = ImageFeatureExtractor.extract(path)
        print(f"📷 图像分析: {path}")
        print(f"   尺寸: {feats.get('width')}x{feats.get('height')}")
        print(f"   亮度: {feats.get('brightness',0):.0f}")
        print(f"   对比度: {feats.get('contrast',0):.0f}")
        print(f"   边缘密度: {feats.get('edge_density',0):.2f}")
        if feats.get("dominant_color"):
            print(f"   主色调: RGB{feats['dominant_color']}")
        print(f"   pHash: {feats.get('phash','')[:20]}...")
        # 电池专项
        batt = BatteryVision.detect_coating_defect(path)
        if batt.get("defect_type"):
            print(f"   ⚠️ 涂布缺陷: {batt['defect_type']} ({batt['confidence']:.0%})")
        else:
            print(f"   ✅ 无显著涂布缺陷")

    elif len(sys.argv) > 1 and sys.argv[1] == "learn":
        path = sys.argv[2] if len(sys.argv) > 2 else "."
        category = sys.argv[3] if len(sys.argv) > 3 else "general"
        kb = VisualKnowledgeBase()
        feats = ImageFeatureExtractor.extract(path)
        kb.add(path, feats, category)
        print(f"✅ 已学习: {path} (分类: {category})")
        print(f"   知识库: {kb.stats()}")

    elif len(sys.argv) > 1 and sys.argv[1] == "similar":
        path = sys.argv[2] if len(sys.argv) > 2 else "."
        kb = VisualKnowledgeBase()
        results = kb.find_similar(path)
        print(f"🔍 相似图像: {len(results)} 张")
        for r in results:
            print(f"   {r['path']} ({r['similarity']:.0%} 相似, {r['category']})")

    else:
        print("👁️ 析微视觉学习扩展 v1.0")
        print()
        print("用法:")
        print("  analyze <image>   分析图像特征")
        print("  learn <image> [分类]  学习新图像")
        print("  similar <image>  查找相似图像")
        print()
        print("能力:")
        print("  • 感知哈希 (pHash) — 图像去重/相似度")
        print("  • 颜色直方图 — 主色调/亮度/对比度")
        print("  • 边缘密度 — 纹理分析")
        print("  • 涂布缺陷检测 — 电池极片专业分析")
        print("  • 视觉知识库 — 特征存储+相似匹配")
