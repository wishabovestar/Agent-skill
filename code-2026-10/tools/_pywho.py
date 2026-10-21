import sys
print("EXE", sys.executable)
print("VER", sys.version)
try:
    import ruamel.yaml as y; print("RUAMEL", y.__file__)
except Exception as e: print("NO_RUAMEL", e)
