import io, re, sys

txt = io.open('_pn/x_enp.txt', encoding='utf-8', errors='replace').read()
flat = re.sub(r'\s+', ' ', txt)
flat_n = flat.replace('–', '-').replace('−', '-')

CHECKS = [
    ("110 (2026) 112847", "期刊卷期"),
    ("N=167", "静息 N"),
    ("N=152", "任务 N"),
    ("N=317", "mega 静息"),
    ("N=291", "mega 任务"),
    ("p=0.009", "复现 SZ/AD/HC"),
    ("xmax=48, ymax=43, zmax=56", "peak 48/43/56"),
    ("adjusted R2=0.25", "R2 0.25"),
    ("p=0.029", "含 MDD dmPFC"),
    ("xmax=51, ymax=86, zmax=58", "peak 51/86/58"),
    ("adjusted R2=0.13", "R2 0.13"),
    ("p=0.003", "去离群点"),
    ("p=0.12", "whole-DMN ns"),
    ("p<0.001", "mega / 组间"),
    ("xmax=45, ymax=87, zmax=40", "mega peak"),
    ("adjusted R2=0.47", "R2 0.47"),
    ("p=0.014", "LON 单独"),
    ("adjusted R2=0.24", "R2 0.24"),
    ("xmax=45, ymax=88, zmax=40", "mega LON peak"),
    ("adjusted R2=0.41", "R2 0.41"),
    ("p=0.004", "mega SFS rmPFC"),
    ("xmax=45, ymax=90, zmax=44", "mega SFS peak"),
    ("adjusted R2=0.35", "R2 0.35"),
    ("p=0.016", "任务均值"),
    ("R2=0.06", "任务 R2 0.06"),
    ("p=0.013", "任务 LON"),
    ("R2=0.16", "任务 R2 0.16"),
    ("p=0.018", "含 MDD PCC"),
    ("R2=0.05", "任务 R2 0.05"),
    ("p's>0.05", "阴性表述"),
    ("Unexpectedly, no associations were found between SFS scores", "SFS 单独无关联原文句"),
    ("18-55", "年龄分层下界"),
    ("56-80", "年龄分层上界"),
    ("CC BY", "许可"),
    ("Publisher's PDF", "版本"),
]

hit = miss = 0
lines = []
for s, tag in CHECKS:
    ok = (s in flat) or (s in flat_n)
    hit += ok
    miss += (not ok)
    lines.append(("HIT " if ok else "MISS") + " | %-45s | %s" % (s, tag))

out = "541 全文数字核验：HIT=%d MISS=%d / 共 %d\n" % (hit, miss, len(CHECKS)) + "\n".join(lines)
io.open('_pn/verify541.txt', 'w', encoding='utf-8').write(out)
print(out)
print("x_enp.txt chars =", len(txt))
