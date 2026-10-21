"""算 _det_t09_r8 的簇内计数与跨模式首个分歧位置（数值落盘，避免折叠）。"""
import hashlib
import io
import json

d = json.load(io.open("_det_t09_r8.json", encoding="utf-8"))
out = [f"model={d['model']} temp={d['temperature']} seed={d['seed']} runs={d['runs']}"]
rep = {}
for mode, res in d["modes"].items():
    texts = res["texts"]
    groups = {}
    for t in texts:
        groups.setdefault(hashlib.sha256(t.encode()).hexdigest()[:16], []).append(t)
    sizes = sorted((len(v) for v in groups.values()), reverse=True)
    out.append(f"{mode}: n={len(texts)} 簇={len(groups)} 各簇样本数={sizes} wall={res.get('wall_s')}")
    for h, v in groups.items():
        out.append(f"   {h} x{len(v)} len={len(v[0])} head={v[0][:48]!r}")
    rep[mode] = list(groups.values())[0][0]

names = list(rep)
for i in range(len(names)):
    for j in range(i + 1, len(names)):
        a, b = rep[names[i]], rep[names[j]]
        off = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), None)
        out.append(f"跨模式 {names[i]} vs {names[j]}: 首分歧offset={off} "
                   f"({'文本相同' if off is None and a == b else '文本不同'})")

io.open("_det_t09_detail.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
print("wrote _det_t09_detail.txt")
