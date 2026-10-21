import sys
sys.path.insert(0, r"C:/Users/Administrator/AppData/Local/hermes/hermes-agent")
from agent.context_compressor import ContextCompressor, estimate_tokens_rough  # noqa: E402
print("T5_OK", ContextCompressor.__name__, estimate_tokens_rough("abc"))
