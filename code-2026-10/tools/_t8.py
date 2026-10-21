import sys, os
_site_dir = r"C:/Users/Administrator/AppData/Local/hermes/hermes-agent/venv/Lib/site-packages"
import site as _site
_site.addsitedir(_site_dir)
sys.path.insert(0, r"C:/Users/Administrator/AppData/Local/hermes/hermes-agent")
from agent.context_compressor import ContextCompressor  # noqa: E402

floor = os.environ.get("HERMES_TAIL_FLOOR_TOKENS", "<unset>")
out = ["floor_env=%s" % floor]
for ctx in (32768, 65536, 131072, 1048576):
    c = ContextCompressor(model="deepseek-flash", config_context_length=ctx, provider="custom",
                          base_url="https://api.deepseek.com/v1", api_key="dummy")
    out.append("ctx=%-8d tail=%d" % (ctx, c.tail_token_budget))
print("\n".join(out))
