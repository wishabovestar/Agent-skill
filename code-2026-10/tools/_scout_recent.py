import glob, os, re

for d in [r"D:/hermes/data/intel/anthropic_code", r"D:/hermes/data/intel/tata_apple"]:
    print("#####", os.path.basename(d))
    files = sorted(glob.glob(os.path.join(d, "collection_2026091*.md")))[-3:]
    for f in files:
        t = open(f, encoding="utf-8", errors="ignore").read()
        urls = re.findall(r'https?://[^\s\)\]\>"\']+', t)
        heads = [l.strip() for l in t.splitlines() if l.startswith("#") or l.strip().startswith("| 仓库")]
        print("  FILE:", os.path.basename(f), "urls:", len(urls))
        for h in heads[:14]:
            print("    H:", h[:105])
        for u in urls[:14]:
            print("    U:", u[:105])
