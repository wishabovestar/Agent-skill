"""
巡天 Hugging Face 知识采集器 v2 (hf-mirror 镜像版)
聚焦: 高星(likes) / 热门(downloads) / 关注激增(最近更新+趋势)

HF API 直连在国内被阻断(WinError 10061), 改用官方镜像 hf-mirror.com
API 结构相同: /api/models?sort=likes|downloads|lastModified&limit=N
             /api/trending

输出: knowledge_base/open-source-models/huggingface-{category}/ 的 JSON 条目
"""
import json, urllib.request, ssl, time, hashlib, os, sys

# ★ r1185: 走带【跳转后复核】的 curl (curl_guarded)
import sys as _cg_sys
_cg_sys.path.insert(0, r'D:\hermes\hermes-data\profiles\qqbot3\scripts')
import curl_guarded as cg


sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# 镜像优先, 原生HF作为fallback(需代理)
MIRROR = "https://hf-mirror.com"
NATIVE = "https://huggingface.co"
OUT_DIR = r"D:\hermes\hermes-data\profiles\qqbot3\knowledge_base\open-source-models\huggingface"
REGISTRY = r"D:\hermes\hermes-data\profiles\qqbot3\knowledge_base\registry.json"

UA = {"User-Agent": "Mozilla/5.0 (xuntian-HF-collector)"}

def fetch(url, timeout=25):
    """用 curl 子进程获取(已验证urllib被镜像连接复用问题), 先镜像后原生"""
    import subprocess
    for base in [MIRROR, NATIVE]:
        full = url.replace(MIRROR, base).replace(NATIVE, base)
        try:
            r = cg.run(
                ["curl", "-skL", "--max-time", str(timeout), "-A", "Mozilla/5.0", full],
                capture_output=True, timeout=timeout+10
            )
            if r.returncode == 0 and r.stdout.strip():
                return json.loads(r.stdout.decode('utf-8', errors='replace')), base
        except Exception:
            continue
    return None, None

def collect(collection, sort, limit, domain_tag):
    """采集一类: 返回 entries"""
    url = f"{MIRROR}/api/{collection}?sort={sort}&limit={limit}"
    data, base = fetch(url)
    if data is None:
        return []
    entries = []
    for it in data:
        tid = it.get("modelId") or it.get("id") or ""
        if not tid:
            continue
        likes = it.get("likes", 0)
        downloads = it.get("downloads", 0)
        eid = hashlib.sha256(tid.encode()).hexdigest()[:10]
        entries.append({
            "id": f"kb_{eid}",
            "source": "huggingface",
            "url": f"https://huggingface.co/{tid}",
            "title": tid,
            "domain": "open-source-models",
            "relevance_score": min(10, 1 + int(likes/100)),
            "summary_cn": f"[HF-{sort}] {tid} — likes={likes}, downloads={downloads}",
            "implementation_status": "collected",
            "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "tags": ["huggingface", collection, sort]
        })
    return entries

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("=== 巡天 Hugging Face 采集 (hf-mirror) ===\n")
    all_entries = []

    # 1. 趋势 (weekly trending - 关注激增)
    trend_url = f"{MIRROR}/api/trending"
    try:
        trend, base = fetch(trend_url)
        if not trend:                      # ★ 修复(r1192): fetch 失败返回 (None,None)
            raise RuntimeError("fetch 返回空(镜像与原生都失败)")
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        for it in trend.get("recentlyTrending", []):
            r = it.get("repoData", {})
            tid = r.get("id", "")
            if not tid: continue
            all_entries.append({
                "id": f"kb_{hashlib.sha256(tid.encode()).hexdigest()[:10]}",
                "source": "huggingface", "url": f"https://huggingface.co/{tid}",
                "title": tid, "domain": "open-source-models",
                "relevance_score": 8,
                "summary_cn": f"[HF-TRENDING] {tid} (本周关注激增)",
                "implementation_status": "collected", "collected_at": now,
                "tags": ["huggingface","trending"]
            })
        print(f"  ① 趋势(关注激增): {len(trend.get('recentlyTrending',[]))} 条")
    except Exception as e:
        print(f"  ① 趋势 FAIL: {e}")

    # 2-4. 高星 / 热门 / 最近更新
    cats = [
        ("高星(likes)",      "models",   "likes",        15),
        ("热门(downloads)",  "models",   "downloads",    15),
        ("最近更新(激增)",   "models",   "lastModified", 15),
        ("热门数据集",       "datasets", "downloads",    10),
    ]
    for label, coll, sort, lim in cats:
        es = collect(coll, sort, lim, "open-source-models")
        print(f"  {label}: +{len(es)}")
        all_entries += es

    # 去重
    seen, dedup = set(), []
    for e in all_entries:
        if e["title"] not in seen:
            seen.add(e["title"]); dedup.append(e)

    print(f"\n总 {len(all_entries)} → 去重后 {len(dedup)}\n")

    # 写入
    for e in dedup:
        fpath = os.path.join(OUT_DIR, f"{e['id']}.json")
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(e, f, ensure_ascii=False, indent=2)

    # 打印高星 top
    print("=== 高星模型 Top (likes) ===")
    likes_sorted = [e for e in all_entries if "likes" in e.get("tags",[])]
    for e in likes_sorted[:10]:
        print(f"  {e['title']}")

    # 更新 registry
    try:
        reg = {}
        if os.path.exists(REGISTRY):
            with open(REGISTRY, encoding="utf-8") as f:
                reg = json.load(f)
        reg.setdefault("hf_counts", {})
        # ★ 修复(r1192): 原来【无条件】写 total=len(dedup) ⇒ 一次网络失败就把上次
        #   成功的计数覆盖成 0(下游看板会误判采集量骤降)。现在 0 条目时【不覆盖】。
        if len(dedup) > 0:
            reg["hf_counts"]["total"] = len(dedup)
            reg["hf_counts"]["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            note = "✅ registry.json 更新: %d 条目" % len(dedup)
        else:
            reg["hf_counts"]["last_failed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            note = ("🔴 0 条目 ⇒ 【不覆盖】registry.hf_counts.total(保持 %s)"
                    % reg["hf_counts"].get("total", "?"))
        with open(REGISTRY, "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False, indent=2)
        print("\n" + note)
    except Exception as e:
        print(f"  registry FAIL: {e}")

    # ★ 修复(r1192): 原来无条件打印 ✅ 且 main() 无退出码 ⇒ 静默失效。
    if len(dedup) == 0:
        print(f"\n🔴 HF采集【失败/空】→ {OUT_DIR} (0 文件; registry.total 未覆盖)")
        return 1
    print(f"\n✅ HF采集完成 → {OUT_DIR} ({len(dedup)} 文件)")
    return 0

if __name__ == "__main__":
    import sys as _s
    _s.exit(main())
