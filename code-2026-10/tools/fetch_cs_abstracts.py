"""
Fetch abstracts of CS/AI/math relevant papers from knowledge base
"""
import subprocess, re, html

urls = [
    # ML for Science
    "https://arxiv.org/abs/2605.17334",  # Causal Anomaly Detection for Battery
    "https://arxiv.org/abs/2607.06645",  # BatteryMat ML+DFT
    "https://arxiv.org/abs/2606.30967",  # Computed materials proposals
    # LLM/AI Safety
    "https://arxiv.org/abs/2607.15267",  # Pretraining Data Poisoning
    "https://arxiv.org/abs/2607.15081",  # DataShield LLM safety
    # AI Agents
    "https://arxiv.org/abs/2607.15193",  # Plover GUI Agents
    "https://arxiv.org/abs/2607.15246",  # ARMOR++ deepfake attacks
    # Computer Vision
    "https://arxiv.org/abs/2607.15097",  # QuReC image restoration
    "https://arxiv.org/abs/2607.15220",  # Person Re-ID
    # Categorical ML
    "https://arxiv.org/abs/2607.15107",  # LINCS categorical ML
    # AI for Science
    "https://arxiv.org/abs/2607.15164",  # Industrialization of Research
    # Math
    "https://arxiv.org/abs/2607.15256",  # Finite-rank corrections (numerical analysis)
    # NLP
    "https://arxiv.org/abs/2607.15240",  # TikStance
    # Physics for CS
    "https://arxiv.org/abs/2607.15122",  # Fluidic hysterons
]

for url in urls:
    pid = url.split("/")[-1]
    r = subprocess.run(
        f'curl -sL "{url}" -H "User-Agent: Mozilla/5.0" -m 15',
        shell=True, capture_output=True, text=True, timeout=20
    )
    data = r.stdout
    t = re.search(r"<h1 class=\"title mathjax\">(.*?)</h1>", data, re.DOTALL)
    title = ""
    if t:
        title = re.sub(r"<[^>]+>", "", t.group(1))
        title = html.unescape(title).strip().replace("\n", " ")
    m = re.search(r"<blockquote class=\"abstract mathjax\">(.*?)</blockquote>", data, re.DOTALL)
    abstract = ""
    if m:
        text = re.sub(r"<[^>]+>", "", m.group(1))
        text = html.unescape(text).strip()
        abstract = re.sub(r"\s+", " ", text)[:500]
    print(f"--- {pid} ---")
    if title:
        print(f"T: {title[:100]}")
    if abstract:
        print(f"A: {abstract}")
    print()
