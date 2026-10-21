import sys
sys.path.insert(0, r"C:/Users/Administrator/AppData/Local/hermes/hermes-agent")
try:
    import hermes_cli.config as c
    print("CONFIG_OK")
except Exception as e:
    import traceback; traceback.print_exc()
print([p for p in sys.path if "site-packages" in p][:2])
