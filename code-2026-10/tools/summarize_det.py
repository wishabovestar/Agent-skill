"""把 determinism_probe 的 JSON 结果压成单行摘要（便于逐行取字面，避免输出折叠）。"""
import io
import json
import os
import sys

FILES = [
    "_det_probe_1.5b.json",
    "_det_ctrl_seed43.json",
    "_det_ctrl_temp09.json",
    "_det_probe_t07.json",
    "_det_probe_7b.json",
]


def one(d):
    """从单个 mode 结果里抽 (簇数, 首分歧offset, 样本hash前缀)。"""
    clusters = d.get("clusters") or d.get("cluster_count")
    if isinstance(clusters, list):
        n = len(clusters)
    elif isinstance(clusters, int):
        n = clusters
    else:
        n = "?"
    off = d.get("first_diff_offset", d.get("first_diff", "?"))
    hashes = d.get("hashes") or [c.get("hash") for c in (clusters if isinstance(clusters, list) else [])]
    h = (hashes[0][:12] + "…") if hashes and isinstance(hashes[0], str) else "?"
    return n, off, len(hashes) if hashes else 0, h


def main(out_path):
    lines = []
    for f in FILES:
        if not os.path.exists(f):
            lines.append(f"{f}: MISSING")
            continue
        d = json.load(io.open(f, encoding="utf-8"))
        head = (f"{f} | model={d.get('model')} temp={d.get('temperature')} "
                f"seed={d.get('seed')} runs={d.get('runs')} np={d.get('num_predict')}")
        lines.append(head)
        modes = d.get("modes") or {}
        for name, res in modes.items():
            if not isinstance(res, dict):
                lines.append(f"    {name}: raw={str(res)[:100]}")
                continue
            n, off, hn, h = one(res)
            verdict = "PASS(单簇)" if n == 1 else ("FAIL(多簇)" if isinstance(n, int) else "?")
            lines.append(f"    {name}: 簇数={n} {verdict} 首分歧offset={off} n_hash={hn} h0={h}")
    text = "\n".join(lines) + "\n"
    io.open(out_path, "w", encoding="utf-8").write(text)
    print(f"wrote {out_path}: {len(lines)} lines")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "_det_summary.txt")
