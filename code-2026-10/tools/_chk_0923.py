import sys
try:
    import socks
    print("PySocks OK")
except Exception as e:
    print("PySocks MISSING:", e)
import os
for f in ["socks_http_bridge.py","web_fetcher.py","search_fallback.py","xuntian_search.py","source_engine.py","bypass_engine.py"]:
    print(f, "exists" if os.path.exists(f) else "missing")
