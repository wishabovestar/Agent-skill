import sys
print("EXE", sys.executable)
print("P0", sys.path[:3])
print("SP", [p for p in sys.path if "site-packages" in p])
