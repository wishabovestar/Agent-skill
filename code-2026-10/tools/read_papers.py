"""
Read all book_knowledge papers and output for review synthesis
"""
import json, os, glob

categories = {
    "prelithiation_review": "预锂化综述",
    "prelithiation_paper": "预锂化研究论文",
    "cathode_lco": "正极补锂研究",
    "anode_silicon": "硅负极研究",
    "battery_aging": "电池老化/寿命",
    "electrolyte": "电解液/界面",
}

battery_kw = ["lithium", "battery", "prelithiation", "pre-lithiation", "anode", "cathode",
              "electrode", "electrolyte", "SEI", "Si-", "Li-", "cell", "silicon",
              "electrochem", "cycle", "degradation", "aging", "NMC", "graphite",
              "solid-state", "interfacial", "plating", "stripping", "thermal runaway",
              "calendaring", "manufacturing", "DFT", "ion", "metal", "capacity"]

for subdir, label in categories.items():
    base = f"D:/hermes/data/book_knowledge/literature/{subdir}"
    files = glob.glob(os.path.join(base, "*.json"))
    print(f"\n{'='*60}")
    print(f"  {label} ({len(files)} 篇)")
    print(f"{'='*60}")
    
    for f in sorted(files):
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        t = d.get("title", "")[:120]
        y = d.get("year", 0)
        a = d.get("author", "")[:60]
        u = d.get("url", "")[:100]
        ab = (d.get("abstract", "") or "")[:500]
        n = (d.get("note", "") or "")[:200]
        
        # Check if battery-related
        is_battery = any(k.lower() in t.lower() or k.lower() in ab.lower() for k in battery_kw)
        if not is_battery and subdir in ["prelithiation_review"]:
            continue
        
        print(f"\n  ── {t}")
        print(f"     年份:{y}  来源:{a}")
        print(f"     {u}")
        if n:
            print(f"     {n}")
        if ab and len(ab.strip()) > 20:
            ab_clean = ab.replace("\n", " ").replace("  ", " ")
            print(f"     {ab_clean[:300]}")
