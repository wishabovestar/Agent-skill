"""
马尔可夫链研究需求预测器 v1.0
跟踪用户研究主题，预测下一步需要的研究内容
基于二阶马尔可夫链 + 衰减权重
"""
import json, os, re
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import math

# ===== 配置 =====
DATA_DIR = Path("D:/hermes/data/research_predictor")
DATA_DIR.mkdir(parents=True, exist_ok=True)
TRANSITION_FILE = DATA_DIR / "markov_transitions.json"
STATE_CACHE_FILE = DATA_DIR / "current_state.json"
KNOWLEDGE_DIRS = [
    Path("D:/hermes/data/book_knowledge"),
    Path("D:/hermes/data/physics_knowledge"),
    Path("D:/hermes/data/math_knowledge"),
]

# ===== 研究领域定义 =====
RESEARCH_DOMAINS = {
    "battery": {
        "name": "锂电池/预锂化",
        "keywords": ["battery", "锂", "预锂化", "prelithiation", "silicon", "硅负极", "正极", "cathode",
                     "电解液", "electrolyte", "SEI", "Li5FeO4", "LCO", "NCM", "固态电池"],
        "sub_topics": ["prelithiation_review", "prelithiation_paper", "anode_silicon",
                       "cathode_lco", "electrolyte", "battery_aging"],
        "agent": "伏安/程实",
    },
    "ceramics": {
        "name": "陶瓷材料",
        "keywords": ["陶瓷", "ceramic", "sintering", "烧结", "alumina", "氧化铝", "zirconia",
                     "氧化锆", "SiC", "MAX", "ferroelectric", "铁电", "dielectric"],
        "sub_topics": ["ceramics_sintering", "ceramics_mechanical", "ceramics_dielectric",
                       "ceramics_advanced"],
        "agent": "程实/构形",
    },
    "physics": {
        "name": "物理/固体物理",
        "keywords": ["physics", "物理", "solid state", "固体物理", "condensed matter", "凝聚态",
                     "DFT", "molecular dynamics", "分子动力学", "thermal", "热传导"],
        "sub_topics": ["physics_solid", "physics_computational"],
        "agent": "通量/算渊",
    },
    "math": {
        "name": "数学/统计",
        "keywords": ["math", "统计", "概率", "optimization", "优化", "Bayesian", "贝叶斯",
                     "Markov", "马尔可夫", "linear algebra", "线性代数"],
        "sub_topics": ["math_analysis", "probability", "optimization"],
        "agent": "算渊/通量",
    },
    "ml_ai": {
        "name": "机器学习/AI",
        "keywords": ["machine learning", "深度学习", "deep learning", "neural network", "神经网络",
                     "transformer", "LLM", "大模型", "agent", "reinforcement learning"],
        "sub_topics": ["deep_learning", "reinforcement_learning", "nlp"],
        "agent": "通量/算法",
    },
    "3d_cad": {
        "name": "3D建模/工程图纸",
        "keywords": ["3D", "CAD", "SolidWorks", "STEP", "STL", "图纸", "drawing", "DXF",
                     "tolerance", "公差", "DFM", "GD&T"],
        "sub_topics": ["ta_analysis", "dfm", "proj_drawing"],
        "agent": "构形/析微",
    },
}

# ===== 马尔可夫链模型 =====
class ResearchMarkovChain:
    def __init__(self):
        self.transitions = defaultdict(lambda: defaultdict(float))  # {prev_state: {next_state: weight}}
        self.domain_counts = defaultdict(int)  # {domain: count}
        self.total_transitions = 0
        self.decay_factor = 0.95  # 衰减因子（旧转移权重衰减）
        self._load()
    
    def _load(self):
        if TRANSITION_FILE.exists():
            with open(TRANSITION_FILE) as f:
                data = json.load(f)
            self.transitions = defaultdict(lambda: defaultdict(float), {
                k: defaultdict(float, v) for k, v in data.get("transitions", {}).items()
            })
            self.domain_counts = defaultdict(int, data.get("counts", {}))
            self.total_transitions = data.get("total", 0)
    
    def _save(self):
        with open(TRANSITION_FILE, "w") as f:
            json.dump({
                "transitions": {k: dict(v) for k, v in self.transitions.items()},
                "counts": dict(self.domain_counts),
                "total": self.total_transitions,
                "updated_at": datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2)
    
    def record_transition(self, prev_domain, next_domain):
        """记录领域转移"""
        self.transitions[prev_domain][next_domain] += 1.0
        self.domain_counts[next_domain] += 1
        self.total_transitions += 1
        # 衰减旧转移权重
        self._apply_decay()
        self._save()
    
    def _apply_decay(self):
        """衰减所有转移权重"""
        for prev in list(self.transitions.keys()):
            for nxt in list(self.transitions[prev].keys()):
                self.transitions[prev][nxt] *= self.decay_factor
                if self.transitions[prev][nxt] < 0.01:
                    del self.transitions[prev][nxt]
    
    def get_current_state(self):
        """获取当前研究状态"""
        if STATE_CACHE_FILE.exists():
            with open(STATE_CACHE_FILE) as f:
                return json.load(f)
        return {"current_domain": None, "recent_domains": [], "last_updated": None}
    
    def save_current_state(self, domain):
        """保存当前研究状态"""
        state = self.get_current_state()
        prev = state.get("current_domain")
        if prev and prev != domain:
            self.record_transition(prev, domain)
        
        recent = state.get("recent_domains", [])
        recent.append(domain)
        if len(recent) > 10:
            recent = recent[-10:]
        
        with open(STATE_CACHE_FILE, "w") as f:
            json.dump({
                "current_domain": domain,
                "previous_domain": prev,
                "recent_domains": recent,
                "last_updated": datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2)
    
    def predict_next(self, top_n=3):
        """预测下一个研究领域"""
        state = self.get_current_state()
        current = state.get("current_domain")
        if not current:
            return self._cold_start_recommendations(top_n)
        
        # 从转移矩阵获取预测
        predictions = []
        if current in self.transitions:
            for nxt, weight in self.transitions[current].items():
                # 计算置信度
                total = sum(self.transitions[current].values())
                confidence = weight / total if total > 0 else 0
                predictions.append((nxt, weight, confidence))
        
        # 按权重排序
        predictions.sort(key=lambda x: -x[1])
        
        # 如果预测不足，补充热门领域
        if len(predictions) < top_n:
            popular = sorted(self.domain_counts.items(), key=lambda x: -x[1])
            for domain, count in popular:
                if domain not in [p[0] for p in predictions]:
                    confidence = count / max(self.total_transitions, 1)
                    predictions.append((domain, count, min(confidence, 0.5)))
                    if len(predictions) >= top_n:
                        break
        
        results = []
        for domain, weight, conf in predictions[:top_n]:
            info = RESEARCH_DOMAINS.get(domain, {})
            results.append({
                "domain": domain,
                "name": info.get("name", domain),
                "keywords": info.get("keywords", [])[:5],
                "agent": info.get("agent", "通用"),
                "confidence": round(conf, 3),
                "weight": round(weight, 1),
            })
        return results
    
    def _cold_start_recommendations(self, top_n=3):
        """冷启动推荐（无历史数据时）"""
        # 按热度推荐
        popular = sorted(self.domain_counts.items(), key=lambda x: -x[1])
        if popular:
            results = []
            for domain, count in popular[:top_n]:
                info = RESEARCH_DOMAINS.get(domain, {})
                results.append({
                    "domain": domain,
                    "name": info.get("name", domain),
                    "keywords": info.get("keywords", [])[:5],
                    "agent": info.get("agent", "通用"),
                    "confidence": round(count / max(self.total_transitions, 1), 3),
                })
            return results
        
        # 完全冷启动：推荐所有领域
        return [{"domain": k, "name": v["name"], "keywords": v["keywords"][:5],
                 "agent": v["agent"], "confidence": 1.0/len(RESEARCH_DOMAINS)}
                for k, v in list(RESEARCH_DOMAINS.items())[:top_n]]
    
    def detect_domain(self, text):
        """从文本检测研究领域"""
        text_lower = text.lower()
        scores = {}
        for domain, info in RESEARCH_DOMAINS.items():
            score = 0
            for kw in info["keywords"]:
                if kw.lower() in text_lower:
                    score += 1
            if score > 0:
                scores[domain] = score
        if scores:
            return max(scores, key=scores.get)
        return None


# ===== 知识库扫描 =====
def scan_knowledge_base():
    """扫描知识库，统计各领域知识量"""
    stats = defaultdict(int)
    for base_dir in KNOWLEDGE_DIRS:
        if base_dir.exists():
            for f in base_dir.rglob("*.json"):
                if "_log" not in f.name and "routing" not in f.name:
                    stats[f.parent.name] += 1
    return dict(stats)


# ===== 研究建议生成 =====
def generate_recommendations(domain):
    """为指定领域生成研究建议"""
    suggestions = {
        "battery": [
            "预锂化最新综述论文 (arXiv)",
            "硅负极容量衰减机理",
            "Li5FeO4 补锂剂最新进展",
            "固态电解质界面研究",
            "电池老化模型与寿命预测",
        ],
        "ceramics": [
            "先进陶瓷烧结工艺比较 (SPS/闪烧)",
            "陶瓷基复合材料力学性能",
            "介电陶瓷 BaTiO3 最新研究",
            "陶瓷热导率提升策略",
            "MAX相陶瓷的制备与应用",
        ],
        "physics": [
            "固体物理Kittel教材关键章节",
            "DFT计算在材料科学中的应用",
            "分子动力学模拟最新进展",
            "拓扑绝缘体研究前沿",
        ],
        "math": [
            "贝叶斯统计在材料科学的应用",
            "凸优化理论与算法",
            "蒙特卡洛方法的工程应用",
            "统计学习理论综述",
        ],
        "ml_ai": [
            "LLM在材料科学的应用",
            "图神经网络用于晶体结构预测",
            "强化学习在实验设计中的应用",
            "AI Agent 最新架构综述",
        ],
        "3d_cad": [
            "GD&T标准 ASME Y14.5 最新版",
            "公差分析蒙特卡洛方法",
            "PDF图纸OCR识别进展",
            "参数化3D建模工作流",
        ],
    }
    return suggestions.get(domain, ["该领域通用研究建议"])


# ===== 主入口 =====
def analyze_user_input(text):
    """分析用户输入，更新状态，返回预测"""
    chain = ResearchMarkovChain()
    domain = chain.detect_domain(text)
    if domain:
        chain.save_current_state(domain)
    
    predictions = chain.predict_next(3)
    kb_stats = scan_knowledge_base()
    
    return {
        "detected_domain": domain,
        "domain_name": RESEARCH_DOMAINS.get(domain, {}).get("name", "未识别") if domain else "未识别",
        "next_predictions": predictions,
        "knowledge_stats": kb_stats,
        "recommendations": generate_recommendations(domain) if domain else [],
    }

def get_prediction_only():
    """仅获取预测（无需输入）"""
    chain = ResearchMarkovChain()
    predictions = chain.predict_next(3)
    # 附加上下文建议
    result = {"next_predictions": predictions, "knowledge_stats": scan_knowledge_base()}
    # 为每个预测添加具体建议
    for p in predictions:
        p["suggestions"] = generate_recommendations(p["domain"])
    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "record":
        chain = ResearchMarkovChain()
        domain = chain.detect_domain(" ".join(sys.argv[2:]))
        if domain:
            chain.save_current_state(domain)
            print(f"✅ 记录领域: {domain}")
    
    elif len(sys.argv) > 1 and sys.argv[1] == "predict":
        result = get_prediction_only()
        print(f"\n📊 知识库统计: {sum(result['knowledge_stats'].values())} 条")
        print(f"\n🔮 研究预测:")
        for i, p in enumerate(result["next_predictions"], 1):
            print(f"  {i}. {p['name']} (置信度: {p['confidence']:.0%})")
            print(f"     关键词: {', '.join(p['keywords'][:5])}")
            print(f"     建议: {p.get('suggestions', ['-'])[0]}")
    
    elif len(sys.argv) > 1:
        result = analyze_user_input(" ".join(sys.argv[1:]))
        print(f"📌 检测领域: {result['domain_name']}")
        print(f"\n🔮 下一步预测:")
        for p in result["next_predictions"]:
            print(f"  → {p['name']} ({p['confidence']:.0%})")
    
    else:
        print("用法: python research_predictor.py <用户输入>")
        print("       python research_predictor.py predict")
