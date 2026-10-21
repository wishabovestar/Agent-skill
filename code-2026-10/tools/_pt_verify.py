# -*- coding: utf-8 -*-
import io, json, os, re

PT = "D:/hermes/analysis/_pt/"
ABS = json.load(io.open(PT + "abstracts.json", encoding="utf-8"))
ABS = {k: v for k, v in ABS.items()}
def norm(s):
    s = s.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
    s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return re.sub(r"\s+", " ", s)

def src(tag):
    fp = PT + "x_%s.txt" % tag
    if os.path.exists(fp):
        return norm(io.open(fp, encoding="utf-8", errors="replace").read())
    for k, v in ABS.items():
        if tag in k.replace(".", ""):
            return norm(v)
    return ""

CHECKS = {
 "529": ("ax_ha", ["10.4%", "35.5%", "54.7%", "1.8x-2.6x", "2.7x-3.7x", "11 benchmarks", "3 model scales"]),
 "530": ("4033", ["80 patients", "80 age-", "4-8 Hz", "8-13 Hz", "13-30 Hz", "30-40 Hz", "AUC = 0.803", "ACC = 0.770", "0.765", "3 regions", "5 regions", "FDR-"]),
 "531": ("100383", ["184 participants", "40.57", "12.04", "46.7%", "16.49", "12.26", "4.02", "0.023", "-3.79", "0.002", "4.03", "0.022", "0.192", "0.028", "0.223", "0.010", "0.049, 0.328"]),
 "532": ("100372", ["Twenty-four women", "22 age-matched", "20-min", "20 independent components", "5 data sets", "1 voxel", "0.003", "0.008", "0.002"]),
 "533": ("122121", ["Ninety-seven", "96 movie clips", "126 social features", "44 most reliably", "superior temporal gyrus"]),
 "534": ("100366", ["6811", "2364", "4447", "12.04", "11.99", "78 tested", "74 distinct", "0.2 mm", "0.082", "0.090", "0.077", "0.073", "0.074", "0.06 to r = 0.82"]),
 "535": ("100371", ["ninety-eight", "18-27", "2.5 years", "580.35", "0.830", "4.58", "0.037", "12.66", "0.096", "2.348", "0.923", "2.54", "0.539, 4.157", "0.66", "0.672", "C-index"]),
 "536": ("100397", ["n = 10", "32-channel", "3 min", "eight frequency bands", "PCL-5", "homologous"]),
}
tot_h = tot_m = 0
for cid, (tag, pats) in CHECKS.items():
    t = norm(io.open(PT + tag + ".xml", encoding="utf-8", errors="replace").read()) if tag == "ax_ha" else src(tag)
    hit = [p for p in pats if p in t]
    miss = [p for p in pats if p not in t]
    tot_h += len(hit); tot_m += len(miss)
    print("%s src=%-8s hit=%d/%d MISS=%s" % (cid, tag, len(hit), len(pats), miss if miss else "NONE"))
print("TOTAL hit=%d miss=%d" % (tot_h, tot_m))
