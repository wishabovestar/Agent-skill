"""
Scan knowledge base for math/AI/CS/algorithm papers and Turing books
"""
import json, os, glob

print("="*60)
print("1. math_knowledge — 数学/算法概念+论文")
print("="*60)

math_root = "D:/hermes/data/math_knowledge"
for subdir in ["concepts", "papers", "algorithms", "theorems", "code"]:
    d = os.path.join(math_root, subdir)
    if os.path.isdir(d):
        files = glob.glob(os.path.join(d, "*.json"))
        if files:
            print(f"\n  [{subdir}] {len(files)} items:")
            for f in sorted(files)[:10]:
                with open(f, encoding="utf-8") as fh:
                    data = json.load(fh)
                name = data.get("name") or data.get("title") or ""
                domain = data.get("domain","")[:40]
                print(f"    - {name[:70]}  [{domain}]")

print("\n" + "="*60)
print("2. book_knowledge/turing — 图灵系列图书 (25本)")
print("="*60)

turing_root = "D:/hermes/data/book_knowledge/turing"
for cat in ["computer_science", "programming", "ai_ml", "math_stats", "electronics"]:
    d = os.path.join(turing_root, cat)
    if os.path.isdir(d):
        files = glob.glob(os.path.join(d, "*.json"))
        if files:
            print(f"\n  [{cat}] {len(files)} books:")
            for f in sorted(files):
                with open(f, encoding="utf-8") as fh:
                    d2 = json.load(fh)
                print(f"    - {d2.get('title','')[:70]}  ({d2.get('author','')[:30]})")

print("\n" + "="*60)
print("3. book_knowledge — AI/ML/CS相关论文")
print("="*60)

cs_kw = [
    "neural", "network", "deep learning", "machine learning", "AI", "artificial",
    "reinforcement", "transformer", "attention", "graph", "optimization", "algorithm",
    "computer", "software", "program", "data structure", "complexity", "ML", "LLM",
    "language model", "diffusion", "CNN", "LSTM", "BERT", "GAN",
    "computational", "theorem", "proof", "formal", "verification", "lean",
    "category", "functor", "monad", "type theory", "quantum",
    "cryptography", "encoding", "information theory", "Bayesian",
    "causal", "anomaly detection", "image restoration", "deepfake",
    "GUI agent", "safety", "fine-tuning", "AI-driven",
    "person re-identification", "stance analysis",
]

lit_root = "D:/hermes/data/book_knowledge/literature"
for subdir in os.listdir(lit_root):
    d = os.path.join(lit_root, subdir)
    if os.path.isdir(d):
        files = glob.glob(os.path.join(d, "*.json"))
        found = []
        for f in files:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            t = data.get("title","")
            ab = data.get("abstract","") or ""
            note = data.get("note","") or ""
            for kw in cs_kw:
                if kw.lower() in t.lower() or kw.lower() in ab.lower() or kw.lower() in note.lower():
                    found.append((data.get("title","")[:90], data.get("url","")[:80]))
                    break
        if found:
            print(f"\n  [{subdir}] CS/AI相关 ({len(found)}/{len(files)}):")
            for title, url in found[:5]:
                print(f"    - {title}")
                print(f"      {url}")
            if len(found) > 5:
                print(f"      ... and {len(found)-5} more")
