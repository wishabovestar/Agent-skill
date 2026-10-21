# -*- coding: utf-8 -*-
"""解析：split attractor 元数据 / Nature 配体页 / warp.dev 博客索引"""
import sys, io, json, re, html
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
D = Path("D:/hermes/analysis/_x5")

def detag(t):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    return re.sub(r"[ \t]+", " ", t)

L = []
# Crossref 标题查
d = json.loads((D / "cr_split2.json").read_text(encoding="utf-8"))["message"]
L.append(f"### Crossref title query: total={d.get('total-results')}")
for it in (d.get("items") or [])[:5]:
    ttl = ((it.get("title") or [""])[0])[:95]
    jnl = (it.get("container-title") or [""])[0]
    dtp = it.get("published", {}).get("date-parts")
    L.append("- %s | %s | %s | %s" % (it.get("DOI"), ttl, jnl, dtp))
L.append("")

# Nature 搜索页：抽结果链接
s = detag((D / "nat_search.html").read_text(encoding="utf-8", errors="ignore"))
raw = (D / "nat_search.html").read_text(encoding="utf-8", errors="ignore")
links = sorted(set(re.findall(r'href="(/articles/[a-z0-9\-\.]+)"', raw)))
L.append(f"### nature.com search '/articles/' links: {len(links)}")
L.append("; ".join(links[:12]))
i = s.find("split attractor")
L.append("### search text around hit: " + (re.sub(r"\s+", " ", s[max(0,i-200):i+400]) if i > 0 else "### NO HIT 'split attractor'"))
L.append("")

# Nature 配体正文页
raw = (D / "nat_ligand.html").read_text(encoding="utf-8", errors="ignore")
t = detag(raw)
L.append(f"### Nature ligand page: raw={len(raw)} detag={len(t)}")
for kw in ["11.3", "257", "18 lead", "frustrated", "tenfold", "Supplementary"]:
    L.append(f"  kw {kw!r} count={t.count(kw)}")
# 抽 abstract 段
m = re.search(r"Abstract(.{300,4000}?)(?:Access through your institution|Similar content)", t, re.S)
L.append("ABSTRACT_BLOCK: " + (re.sub(r"\s+", " ", m.group(1))[:2200] if m else "NOT FOUND"))
# 图注
caps = re.findall(r"(Fig\.\s*\d+[^\n]{40,400})", t)
L.append(f"FIGCAPS({len(caps)}): " + " || ".join(c[:200] for c in caps[:6]))

# warp.dev 博客索引：找 self-improv
w = (D / "warp_w2.html").read_text(encoding="utf-8", errors="ignore")
wt = detag(w)
L.append("")
L.append("### warp.dev/blog: self-improv hits")
for m in re.finditer(r"[^\n]{0,120}(self-improv|agent)[^\n]{0,120}", wt, re.I):
    s2 = re.sub(r"\s+", " ", m.group(0)).strip()
    if len(s2) > 30:
        L.append("  · " + s2[:200])
L.append("### warp blog links: " + "; ".join(sorted(set(re.findall(r'href="(/blog/[a-z0-9\-]+)"', w)))[:25]))

out = "\n".join(L)
Path("D:/hermes/analysis/_x5_meta2.txt").write_text(out, encoding="utf-8")
print("WROTE", len(out), "chars")
