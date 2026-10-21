# -*- coding: utf-8 -*-
import json, os, shutil, datetime

base = r"D:/hermes/data/intel"
log = os.path.join(base, "logs", "collection_log.json")
shutil.copy(log, log + ".bak")

data = json.load(open(log, encoding="utf-8"))
final = json.load(open(os.path.join(base, "logs", "_final_20260918.json"), encoding="utf-8"))

entry = {
    "id": "xuntian_20260918_2142",
    "timestamp": "2026-09-18T13:42:00Z",
    "type": "xuntian_intelligence_sweep",
    "round": 135,
    "targets": ["anthropic_mythos_oceanus", "tata_apple_leak", "apple_openai_lawsuit"],
    "model": "deepseek-v4-flash",
    "new_items": {"target1": len([c for c in final if c["t"] == 1]),
                  "target2": len([c for c in final if c["t"] == 2]),
                  "target3": len([c for c in final if c["t"] == 3])},
    "docket": {"case": "Apple Inc. v. Liu, 5:26-cv-07078", "prev_max": 158, "new_max": 159},
    "files": [
        "anthropic_code/collection_20260918_2142.md",
        "tata_apple/collection_20260918_2142.md",
        "tata_apple/docket_159_sept18_20260918.md",
    ],
    "items": [{"title": c["title"], "url": c["url"], "target": c["t"], "date": c["d"]} for c in final],
    "notes": "目标2 无9月新事件（回溯补档12条）；目标3 docket 增量 #159 程序性送达；目标1 新增11条（含9/17 LSVP 上线、9/3 Mythos 5.1 深度分析）",
}

data.setdefault("entries", []).append(entry)
data.setdefault("collections", []).append({
    "id": entry["id"], "timestamp": entry["timestamp"], "type": entry["type"],
    "targets": entry["targets"], "new_items": entry["new_items"],
})
data["last_run"] = entry["timestamp"]

json.dump(data, open(log, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("log entries:", len(data["entries"]), "collections:", len(data["collections"]))
print("last_run:", data["last_run"])
print("new_items:", entry["new_items"])

# verify archived files readable
for rel in entry["files"]:
    p = os.path.join(base, rel.replace("/", os.sep))
    txt = open(p, encoding="utf-8").read()
    print(f"OK {rel} {os.path.getsize(p)}B lines={txt.count(chr(10))+1}")
