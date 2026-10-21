"""Search for paper DOIs via Crossref - batch mode"""
import urllib.request, json

queries = [
    ("Fromm lithium oxidation Surface Science", "Li+O2"),
    ("Vogt AES lithium Surface Science 1992", "Li+O2"),
    ("Battezzati DSC lithium oxidation kinetics Acta", "Li+O2"),
    ("Wang lithium metal thermal stability Journal Electrochemical Society", "Li+O2"),
    ("Wahl lithium nitride Journal Materials Science 1987", "Li+N2"),
    ("Sangster Li-N phase diagram Journal Phase Equilibria 2002", "Li+N2"),
    ("Yamamoto Li3N crystal growth Journal Crystal Growth 1975", "Li+N2"),
    ("Johnson MD lithium amorphous silicon Journal Applied Physics 2010", "Li-Si"),
    ("Ding GITT lithium diffusion silicon anode Power Sources 2018", "Li-Si"),
    ("Kucuk EIS lithium transport silicon Physical Chemistry 2020", "Li-Si"),
]

found = 0
for query, cat in queries:
    url = f"https://api.crossref.org/works?query={urllib.request.quote(query)}&rows=5"
    try:
        data = json.loads(urllib.request.urlopen(url, timeout=15).read())
        items = data.get("message", {}).get("items", [])
        for item in items[:3]:
            doi = item.get("DOI", "?")
            title = item.get("title", ["?"])[0][:80]
            journal = item.get("container-title", ["?"])[0][:40]
            year = item.get("created", {}).get("date-parts", [[None]])[0][0]
            authors = item.get("author", [])
            author_str = ",".join([a.get("family", "?") for a in authors[:3]]) if authors else "?"
            print(f"Q: {query}")
            print(f"  DOI={doi} YR={year} AU={author_str}")
            print(f"  TI={title}")
            print(f"  JN={journal}")
            print()
            found += 1
    except Exception as e:
        pass

print(f"Total found: {found}")
