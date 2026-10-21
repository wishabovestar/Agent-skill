import subprocess, os, json, io
OUT = "_dsrepo"
os.makedirs(OUT, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
def get(url, path, extra=None):
    cmd = ["curl","-sSL","-m","90","--ssl-no-revoke","-A",UA,"-H","Accept: application/vnd.github+json"]
    if extra: cmd += extra
    cmd += [url,"-o",os.path.join(OUT,path),"-w","%{http_code} %{size_download}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout.strip(), os.path.join(OUT,path)

repos = ["DeepInfer","deepseek-recipe"]
for r in repos:
    s1,_ = get(f"https://api.github.com/repos/deepseek-ai/{r}", f"{r}_meta.json")
    s2,p2 = get(f"https://api.github.com/repos/deepseek-ai/{r}", f"{r}_tree.json", ["-H","Accept: application/vnd.github+json"])
    s3,_ = get(f"https://raw.githubusercontent.com/deepseek-ai/{r}/main/README.md", f"{r}_README.md")
    s4,_ = get(f"https://raw.githubusercontent.com/deepseek-ai/{r}/master/README.md", f"{r}_README_master.md")
    print(r, "meta", s1, "| readme-main", s3, "| readme-master", s4)

for r in repos:
    p = os.path.join(OUT,f"{r}_meta.json")
    t = io.open(p,encoding="utf-8",errors="ignore").read()
    try:
        d = json.loads(t)
        print(f"\n[{r}]", d.get("full_name"), "| stars", d.get("stargazers_count"), "| forks", d.get("forks_count"),
              "| lang", d.get("language"), "| size", d.get("size"), "KB | created", d.get("created_at"),
              "| pushed", d.get("pushed_at"), "| license", (d.get("license") or {}).get("spdx_id"),
              "| desc:", (d.get("description") or "")[:150])
    except Exception as e:
        print(r, "meta parse fail", e, t[:200])

s = get("https://api.github.com/repos/deepseek-ai/DeepInfer/git/trees/main?recursive=1", "DeepInfer_treefull.json")[0]
s = get("https://api.github.com/repos/deepseek-ai/deepseek-recipe/git/trees/main?recursive=1", "recipe_treefull.json")[0]
print("trees", s)
