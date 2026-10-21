"""Fix: add datetime import to chart generator"""
with open("D:/hermes/analysis/chart_generator.py", "r", encoding="utf-8") as f:
    c = f.read()

old = 'import json, sys, os'
new = 'import json, sys, os, datetime'
c = c.replace(old, new)

# Also fix the format call - datetime is now imported as module
old2 = '.format(datetime.now().strftime'
new2 = '.format(datetime.datetime.now().strftime'
c = c.replace(old2, new2)

with open("D:/hermes/analysis/chart_generator.py", "w", encoding="utf-8") as f:
    f.write(c)
print("✅ Fixed datetime import")
