# -*- coding: utf-8 -*-
import glob, io, json, re

files = sorted(glob.glob("D:/hermes/analysis/_pn/oa_*.json"))
out = {}
for fp in files:
    d = json.load(io.open(fp, encoding="utf-8"))
    inv = d.get("abstract_inverted_index") or {}
    pos = []
    for w, ps in inv.items():
        for p in ps:
            pos.append((p, w))
    ab = " ".join(w for _, w in sorted(pos))
    doi = (d.get("doi") or "").replace("https://doi.org/", "")
    out[doi] = ab
    au = [a["author"]["display_name"] for a in d.get("authorships", [])]
    oa = d.get("best_oa_location") or {}
    srcs = [((l.get("source") or {}).get("display_name") or "-") for l in (d.get("locations") or [])[:5]]
    print("=" * 68)
    print("DOI   %s" % doi)
    print("TITLE %s" % (d.get("title") or "")[:150])
    print("JOURN %s | %s" % (((d.get("primary_location") or {}).get("source") or {}).get("display_name"), (d.get("publication_date") or "")[:10]))
    print("AUTH  n=%d | %s" % (len(au), "; ".join(au[:3]) + (" ..." if len(au) > 3 else "")))
    print("ABS   len=%d | OA=%s lic=%s" % (len(ab), d.get("open_access", {}).get("is_oa"), (oa.get("license") or "-")))
    print("LOCS  %s" % " | ".join(srcs))
    print("PMC?  %s" % [ (l.get("landing_page_url") or "") for l in (d.get("locations") or []) if "pmc" in ((l.get("landing_page_url") or "") + (l.get("source") or {}).get("display_name", "")).lower() ])
json.dump(out, io.open("D:/hermes/analysis/_pn/abstracts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("SAVED total_chars=%d" % sum(len(v) for v in out.values()))
