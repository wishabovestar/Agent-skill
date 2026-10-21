import io, re, sys
p = r"D:/hermes/data/intel/redblue_借鉴.md"
with io.open(p, encoding="utf-8") as f:
    lines = f.read().splitlines()
out = []
for i, s in enumerate(lines):
    if s.startswith("# 周红蓝对抗") or s.startswith("> 日期") or s.startswith("> 运行日") or s.startswith(">日期"):
        out.append("%d| %s" % (i+1, s))
        # also grab next non-empty line if it looks like a date
sys.stdout.write("\n".join(out) + "\n")
