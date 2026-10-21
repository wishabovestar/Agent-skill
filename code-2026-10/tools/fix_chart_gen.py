"""Fix CJK font and numpy issues in chart_generator.py"""
with open("D:/hermes/analysis/chart_generator.py", "r", encoding="utf-8") as f:
    c = f.read()

# Fix 1: Add CJK font support after matplotlib imports
old1 = """import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np"""

new1 = """import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
# CJK font fallback
import os as _os
for _fp in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simsun.ttc",
            "C:/Windows/Fonts/msyhbd.ttc", "/usr/share/fonts",
            "/System/Library/Fonts"]:
    if _os.path.exists(_fp):
        try:
            plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimSun", "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            break
        except:
            pass"""

c = c.replace(old1, new1)

# Fix 2: Heatmap numpy comparison
old2 = 'color="white" if val > (np.max(matrix)+np.min(matrix))/2 else "black",'
new2 = 'color="white" if np.max(matrix) != np.min(matrix) and val > (np.max(matrix)+np.min(matrix))/2 else "black",'
c = c.replace(old2, new2)

with open("D:/hermes/analysis/chart_generator.py", "w", encoding="utf-8") as f:
    f.write(c)
print("✅ Fixed CJK + numpy issues")
