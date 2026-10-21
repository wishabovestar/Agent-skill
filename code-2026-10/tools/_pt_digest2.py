# -*- coding: utf-8 -*-
import io, json, os, re

PT = "D:/hermes/analysis/_pt/"
ABS = json.load(io.open(PT + "abstracts.json", encoding="utf-8"))
ABS = {k.replace("https://doi.org/", ""): v for k, v in ABS.items()}

META = {
    "100366": ("Neuroimage Reports", "2026-06-12", "Bango CI 等 9 人"),
    "100371": ("Neuroimage Reports", "2026-06-11", "van de Groep IH 等 3 人"),
    "100372": ("Neuroimage Reports", "2026-06-10", "Berginström N 等 6 人"),
    "100383": ("Neuroimage Reports", "2026-07-13", "Anderson SR 等 10 人"),
    "100397": ("Neuroimage Reports", "2026-08-13", "Modarres MH, Shirk SD"),
    "122121": ("NeuroImage", "2026-07-09", "Ye Q 等 6 人"),
    "4033":   ("Pain", "2026-06-16", "Miao Z 等 8 人"),
}
KEY = re.compile(r"(p\s*[=<>]|r\s*=|β|F\s*\(|t\s*\(|%|subjects|participants|patients|controls|n\s*=|ICC|AUC|accuracy|sensitivity|specificity)", re.I)

for tag, (jn, dt, au) in META.items():
    fp = PT + "x_%s.txt" % tag
    txt = io.open(fp, encoding="utf-8", errors="replace").read() if os.path.exists(fp) else ""
    ab = ""
    for k, v in ABS.items():
        if tag in k.replace(".", ""):
            ab = v
            break
    heads = []
    for ln in txt.splitlines():
        s = ln.strip()
        if 3 < len(s) < 90 and re.match(r"^(\d+(\.\d+)*\.?\s+)?[A-Z][A-Za-z ,\-\(\)/]{4,}$", s) and not s.endswith("."):
            if s not in heads:
                heads.append(s)
    sents = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", txt))
    picked = []
    for s in sents:
        if 60 < len(s) < 330 and KEY.search(s) and re.search(r"\d", s):
            picked.append(s.strip())
    seen, uniq = set(), []
    for s in picked:
        k = s[:50]
        if k not in seen:
            seen.add(k); uniq.append(s)
    out = []
    out.append("##### %s | %s | %s | %s" % (tag, jn, dt, au))
    out.append("[FULLTEXT=%s chars=%d]" % (bool(txt), len(txt)))
    out.append("[ABSTRACT %d chars] %s" % (len(ab), ab))
    out.append("[HEADS] " + " | ".join(heads[:26]))
    out.append("[NUM-SENTENCES n=%d, 取前 16]" % len(uniq))
    for s in uniq[:16]:
        out.append("  - " + s)
    d = "\n".join(out)
    io.open(PT + "dg_%s.txt" % tag, "w", encoding="utf-8", newline="\n").write(d)
    print("%s digest_chars=%d heads=%d nums=%d" % (tag, len(d), len(heads), len(uniq)))
