"""Fetch paper metadata from Crossref API"""
import urllib.request, json

DOIS = {
    "10.1149/2.0031509jes": "Wang - Li oxidation thermal stability",
    "10.1063/1.3474999": "Johnson - Li in a-Si MD simulation",
    "10.1021/nl501066m": "Tritsaris - Li in Si DFT+MD",
}

# Also try to search for the missing papers
SEARCHES = [
    "lithium+oxidation+Fromm+1976+Surface+Science",
    "Vogt+lithium+oxidation+AES+1992",
    "Li3N+Wahl+1987+Journal+Materials+Science",
    "Li3N+Yamamoto+1975+Crystal+Growth",
    "Li+Si+diffusion+GITT+Ding+2018+Power+Sources",
    "Li+Si+EIS+Kucuk+2020+Physical+Chemistry",
    "lithium+oxidation+DSC+Battezzati+1991+Acta",
    "Sangster+Li-N+phase+2002",
]

results = {}

# Fetch confirmed DOIs
for doi, label in DOIS.items():
    url = f"https://api.crossref.org/works/{doi}"
    try:
        data = json.loads(urllib.request.urlopen(url, timeout=10).read())["message"]
        title = data.get("title", ["?"])[0]
        journal = data.get("container-title", ["?"])[0]
        url_link = data.get("URL", "?")
        year = "?"
        if data.get("published-print"):
            year = data["published-print"].get("date-parts", [[None]])[0][0]
        elif data.get("created"):
            year = data["created"].get("date-parts", [[None]])[0][0]
        authors = []
        for a in data.get("author", [])[:4]:
            g = a.get("given", "")
            f = a.get("family", "?")
            if g:
                authors.append(f"{g[0]}. {f}")
            else:
                authors.append(f)
        cited = data.get("is-referenced-by-count", 0)
        results[doi] = {
            "title": title, "journal": journal, "url": url_link,
            "year": year, "authors": authors, "cited": cited
        }
        print(f"✅ {doi}: {title[:60]}...")
    except Exception as e:
        print(f"❌ {doi}: {e}")

# Search for missing papers
for q in SEARCHES:
    url = f"https://api.crossref.org/works?query={q}&rows=1"
    try:
        data = json.loads(urllib.request.urlopen(url, timeout=10).read())
        items = data.get("message", {}).get("items", [])
        if items:
            item = items[0]
            doi = item.get("DOI", "?")
            title = item.get("title", ["?"])[0]
            journal = item.get("container-title", ["?"])[0]
            url_link = item.get("URL", "?")
            year = item.get("created", {}).get("date-parts", [[None]])[0][0]
            print(f"🔍 Found: {doi}")
            print(f"   Title: {title[:80]}")
            print(f"   Journal: {journal} ({year})")
            results[doi] = {
                "title": title, "journal": journal, "url": url_link,
                "year": year, "found_by": q[:40]
            }
        else:
            print(f"❌ Search: {q} -> no results")
    except Exception as e:
        print(f"❌ Search: {q} -> {e}")

# Save for later use
import os
os.makedirs("D:/hermes/data", exist_ok=True)
with open("D:/hermes/data/crossref_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"\n✅ Saved {len(results)} records to crossref_results.json")
