# -*- coding: utf-8 -*-
import glob, io, json

for fp in sorted(glob.glob("D:/hermes/analysis/_pn/epmc_*.json")):
    d = json.load(io.open(fp, encoding="utf-8"))
    res = d.get("resultList", {}).get("result") or []
    if not res:
        print("NO_RESULT %s" % fp.split("epmc_")[-1])
        continue
    r = res[0]
    print("=" * 66)
    print("%s | PMID=%s PMCID=%s OA=%s inEPMC=%s" % (r.get("doi"), r.get("pmid"), r.get("pmcid"), r.get("isOpenAccess"), r.get("inEPMC")))
    print("JOURN %s %s | type=%s" % (r.get("journalInfo", {}).get("journal", {}).get("title"), r.get("pubYear"), r.get("pubType")))
    print("ABS len=%d" % len(r.get("abstractText") or ""))
    print("FULLTXT_URLS %s" % [u.get("url") for u in (r.get("fullTextUrlList", {}).get("fullTextUrl") or [])])
