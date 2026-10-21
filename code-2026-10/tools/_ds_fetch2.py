import subprocess, os
OUT="_dsrepo"; UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
def get(url,path):
    r=subprocess.run(["curl","-sSL","-m","90","--ssl-no-revoke","-A",UA,url,"-o",os.path.join(OUT,path),"-w","%{http_code} %{size_download}"],capture_output=True,text=True)
    print(path, r.stdout.strip())
B="https://raw.githubusercontent.com/deepseek-ai/DeepInfer/main/"
for f in ["examples/README.md","eval/README.md","scripts/build.sh","deepinfer/__init__.py"]:
    get(B+f, "DI_"+f.replace("/","_"))
R="https://raw.githubusercontent.com/deepseek-ai/deepseek-recipe/main/"
for f in ["docs/streaming.md","docs/tokenizer.md","Cargo.toml"]:
    get(R+f, "RC_"+f.replace("/","_"))
get("https://huggingface.co/api/models/deepseek-ai/DeepSeek-V4.1-Flash-1017","hf_v41.json")
