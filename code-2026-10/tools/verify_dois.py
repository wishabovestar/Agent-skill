"""网络恢复后 - 精确检索文献DOI"""
import urllib.request, json, os

# 精确搜索词（作者+年份+关键词）
SEARCHES = [
    # Li+O2 反应
    ("Fromm 1976 lithium oxidation Surface Science", "Li+O2"),
    ("Vogt 1992 AES lithium oxidation", "Li+O2"),
    ("Battezzati 1991 DSC lithium oxidation kinetics", "Li+O2"),
    ("Wang 2015 lithium metal thermal stability JECS", "Li+O2"),
    
    # Li+N2 反应
    ("Wahl 1987 lithium nitride formation kinetics", "Li+N2"),
    ("Sangster 2002 Li-N phase diagram assessment", "Li+N2"),
    ("Yamamoto 1975 Li3N crystal growth thin film", "Li+N2"),
    
    # Li-Si 扩散
    ("Johnson 2010 lithium diffusion amorphous silicon MD", "Li-Si"),
    ("Tritsaris 2014 lithium insertion silicon DFT Nano Letters", "Li-Si"),
    ("Ding 2018 GITT lithium diffusion silicon anode", "Li-Si"),
    ("Kucuk 2020 EIS lithium transport silicon", "Li-Si"),
]

results = {}
print("文献DOI检索结果")
print("="*60)

for query, category in SEARCHES:
    url = f"https://api.crossref.org/works?query={urllib.request.quote(query)}&rows=3"
    try:
        data = json.loads(urllib.request.urlopen(url, timeout=15).read())
        items = data.get("message", {}).get("items", [])
        if items:
            best = items[0]
            doi = best.get("DOI", "?")
            title = best.get("title", ["?"])[0]
            journal = best.get("container-title", ["?"])[0]
            year = best.get("created", {}).get("date-parts", [[None]])[0][0]
            authors = []
            for a in best.get("author", [])[:3]:
                g = a.get("given", "")
                f = a.get("family", "?")
                authors.append(f"{g[0] if g else ''}. {f}" if g else f)
            score = data.get("message", {}).get("search-results", {}).get("query", {}).get("search-terms", "")
            
            # Check relevance by title
            title_lower = title.lower()
            relevant = True
            if "lithium" not in title_lower and "li" not in title_lower:
                relevant = False
            if category == "Li+O2" and "oxygen" not in title_lower and "oxidation" not in title_lower and "oxide" not in title_lower:
                relevant = False
            if category == "Li+N2" and "nitrid" not in title_lower and "li3n" not in title_lower:
                relevant = False
            if category == "Li-Si" and "silicon" not in title_lower and "si " not in title_lower:
                relevant = False
            
            status = "✅ 主题相关" if relevant else "⚠️ 关键词匹配但主题可能不符"
            print(f"\n{status}")
            print(f"  Query: {query}")
            print(f"  DOI: {doi}")
            print(f"  Title: {title[:100]}")
            print(f"  Journal: {journal} ({year})")
            print(f"  Authors: {', '.join(authors)}")
            print(f"  URL: https://doi.org/{doi}")
            results[query] = {
                "doi": doi, "title": title, "journal": journal,
                "year": year, "authors": authors, "url": f"https://doi.org/{doi}",
                "relevant": relevant
            }
        else:
            print(f"\n❌ No results: {query}")
    except Exception as e:
        print(f"\n❌ Error for {query}: {e}")

# Save results
os.makedirs("D:/hermes/data", exist_ok=True)
path = "D:/hermes/data/literature_doi_verified.json"
with open(path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"\n{'='*60}")
print(f"✅ 已保存至 {path}")
print(f"   共检索 {len(SEARCHES)} 个查询, 找到 {sum(1 for v in results.values() if v.get('relevant'))} 个相关结果")
