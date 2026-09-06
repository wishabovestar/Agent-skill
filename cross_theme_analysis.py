# -*- coding: utf-8 -*-
"""R777-R806 跨档横切主题分析 (RSI 深度综合)"""
# side_effects: [只读]
import re, os, glob

base = r"D:\hermes\hermes-data\profiles\qqbot3\knowledge_base\research"
files = glob.glob(os.path.join(base, "*.md"))
files = [f for f in files if re.search(r"r((7[7-9]\d)|(8\d\d))_", os.path.basename(f))]

themes = {
    "验证": ["gate", "验证器", "双向断言", "外部", "oracle", "自评", "compliance", "rubric"],
    "缩放幂律": ["Kleiber", "Chinchilla", "幂律", "M^0", "孪生", "常量"],
    "压缩熵": ["压缩", "交叉熵", "cross-entropy", "熵", "香农"],
    "LLM极限": ["长尾", "数量级", "多步", "回写", "工具执行", "卸载", "abstain"],
    "结构约束": ["拓扑", "毛球", "不可能", "障壁", "不变量", "下界", "Poincare"],
    "记忆基因": ["基因", "lineage", "血统", "蒸馏", "锁"],
    "混合路由": ["混合", "路由", "本地", "云兜底", "subsumption"],
    "harness": ["harness", "Agency", "训练中心", "编排"],
    "语义哲学": ["Bar-Hillel", "ELIZA", "世界模型", "歧义", "brittleness"],
    "司法证据": ["法庭", "法医", "Daubert", "司法"],
    "架构分层": ["分层", "低层", "抑制", "安全"],
}

meta = {}
for f in files:
    m = re.search(r"r(\d+)_", os.path.basename(f))
    if not m:
        continue
    rid = int(m.group(1))
    try:
        txt = open(f, encoding="utf-8").read()
    except Exception:
        continue
    title = re.search(r"^# (.+)$", txt, re.M)
    meta[rid] = {"file": os.path.basename(f),
                 "title": title.group(1).strip()[:58] if title else os.path.basename(f),
                 "text": txt}

print(f"扫描: R{min(meta)}-R{max(meta)} 共 {len(meta)} 档")
print()
# 每档主题命中
cov = {}
for rid in sorted(meta):
    hits = [t for t, kws in themes.items() if any(kw.lower() in meta[rid]["text"].lower() for kw in kws)]
    cov[rid] = hits
    print(f"R{rid} [{meta[rid]['title'][:36]:<36}] -> {','.join(hits)}")

# 主题频次
print()
print("=== 主题频次 ===")
from collections import Counter
c = Counter()
for rid, hits in cov.items():
    for h in hits:
        c[h] += 1
for t, n in c.most_common():
    print(f"  {t}: {n} 档")

# 多主题枢纽档 (跨 3+ 主题)
print()
print("=== 枢纽档 (连接 >=3 主题) ===")
for rid, hits in cov.items():
    if len(hits) >= 3:
        print(f"  R{rid} {meta[rid]['title'][:40]} ({len(hits)}主题: {','.join(hits)})")
