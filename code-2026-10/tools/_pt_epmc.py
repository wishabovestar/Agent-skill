import glob, io, json
for fp in sorted(glob.glob("D:/hermes/analysis/_pt/epmc_*.json")):
    d = json.load(io.open(fp, encoding="utf-8"))
    r = (d.get("resultList") or {}).get("result") or []
    if not r:
        print("%s -> NO_RESULT" % fp.split("epmc_")[-1]); continue
    x = r[0]
    print("=" * 60)
    print("DOI %s" % x.get("doi"))
    print("PMID %s PMCID %s OA=%s inEPMC=%s" % (x.get("pmid"), x.get("pmcid"), x.get("isOpenAccess"), x.get("inEPMC")))
    print("JOURNAL %s | %s" % ((x.get("journalInfo") or {}).get("journal", {}).get("title"), x.get("pubYear")))
    print("TITLE %s" % (x.get("title") or "")[:130])
    ab = x.get("abstractText") or ""
    print("ABS_LEN %d" % len(ab))
