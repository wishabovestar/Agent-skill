import io, re, sys
p = r"D:/hermes/data/intel/redblue_借鉴.md"
with io.open(p, encoding="utf-8") as f:
    t = f.read()
titles = re.findall(r"^# 周红蓝.*$", t, re.M)
out = []
out.append("COUNT=%d" % len(titles))
for i, s in enumerate(titles, 1):
    out.append("%d. %s" % (i, s))
sys.stdout.write("\n".join(out) + "\n")
