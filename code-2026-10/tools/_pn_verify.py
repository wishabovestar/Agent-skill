# -*- coding: utf-8 -*-
import io, json, re, os

PT = "D:/hermes/analysis/_pn/"
ABS = json.load(io.open(PT + "abstracts.json", encoding="utf-8"))

def norm(s):
    s = s.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-").replace("\u00d7", "x")
    for e, c in [("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&"), ("&#x2265;", ">="), ("&#x2009;", " "), ("&#xd7;", "x"), ("&#xa9;", "(c)")]:
        s = s.replace(e, c)
    return re.sub(r"\s+", " ", s)

def full(fn):
    fp = PT + fn
    return norm(io.open(fp, encoding="utf-8", errors="replace").read()) if os.path.exists(fp) else ""

srcs = {
 "537": full("x_bp1.txt") + " || " + norm(ABS.get("10.1016/j.biopsych.2026.01.006", "")),
 "538": norm(ABS.get("10.1038/s41386-026-02498-9", "")),
 "539": norm(ABS.get("10.1016/j.neuroimage.2026.122100", "")),
 "540": full("x_bp2.txt") + " || " + norm(ABS.get("10.1016/j.biopsych.2026.03.997", "")),
 "541": norm(ABS.get("10.1016/j.euroneuro.2026.112847", "")),
 "542": norm(ABS.get("10.1016/j.neuroimage.2026.122044", "")),
}

CH = {
 "537": ["25 cohort studies", "13 countries", "1000 participants", "22,338", "23,861", "94,154", "striatum", "amygdala", "anterior cingulate"],
 "538": ["Group x Condition", "intranasal insulin", "resting-state functional connectivity"],
 "539": ["functional connectivity gradient", "supracallosal anterior cingulate cortex", "postcentral gyrus", "Decoding"],
 "540": ["n = 81", "n = 104", "10-minute", "cluster-level FWE", "10-mm sphere", "pFWE-SVC", "RMSSD", "SDRR", "insula", "hippocampus", "cerebellum"],
 "541": ["N=167", "SZ=32", "MDD=44", "AD=29", "HC=62", "N=152", "N=317", "N=291", "dorsomedial prefrontal"],
 "542": ["N = 849", "ABIDE", "Neurosynth", "oscillatory timing", "posterior visual-parietal-temporal"],
}
th = tm = 0
for cid, pats in CH.items():
    t = srcs[cid]
    hit = [p for p in pats if p in t]
    miss = [p for p in pats if p not in t]
    th += len(hit); tm += len(miss)
    print("%s hit=%d/%d MISS=%s" % (cid, len(hit), len(pats), miss if miss else "NONE"))
print("TOTAL hit=%d miss=%d" % (th, tm))
