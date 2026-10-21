# -*- coding: utf-8 -*-
import glob, io, json, os, re

files = sorted(glob.glob("D:/hermes/analysis/_pt/oa_*.json"))
print("n_files=%d" % len(files))
out = {}
for fp in files:
    d = json.load(io.open(fp, encoding="utf-8"))
    inv = d.get("abstract_inverted_index") or {}
    pos = []
    for w, ps in inv.items():
        for p in ps:
            pos.append((p, w))
    ab = " ".join(w for _, w in sorted(pos))
    out[d.get("doi")] = ab
    au = [a["author"]["display_name"] for a in d.get("authorships", [])]
    oa = d.get("best_oa_location") or {}
    print("=" * 70)
    print("DOI   %s" % d.get("doi"))
    print("TITLE %s" % d.get("title"))
    print("JOURN %s | %s | type=%s" % ((d.get("primary_location") or {}).get("source", {}).get("display_name"),
                                       (d.get("publication_date") or "")[:10], d.get("type")))
    print("AUTH  n=%d %s" % (len(au), "; ".join(au[:4]) + (" ..." if len(au) > 4 else "")))
    print("ABS   len=%d" % len(ab))
    print("OA    is_oa=%s status=%s pdf=%s" % (d.get("open_access", {}).get("is_oa"),
                                               (oa.get("license") or "-"), (oa.get("pdf_url") or "-")[:110]))
    print("CITED %s" % d.get("cited_by_count"))
    for loc in (d.get("locations") or [])[:4]:
        u = (loc.get("pdf_url") or loc.get("landing_page_url") or "")[:120]
        print("  LOC %s | %s | oa=%s" % ((loc.get("source") or {}).get("display_name"), u, loc.get("is_oa")))
json.dump(out, io.open("D:/hermes/analysis/_pt/abstracts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("SAVED abstracts.json total_chars=%d" % sum(len(v) for v in out.values()))
