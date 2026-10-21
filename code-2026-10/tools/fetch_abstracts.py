"""
Fetch arXiv paper abstracts for review
"""
import subprocess, re, html, sys

urls = [
    "https://arxiv.org/abs/2304.06817",
    "https://arxiv.org/abs/1712.09614",
    "https://arxiv.org/abs/2402.04511",
    "https://arxiv.org/abs/2604.26545",
    "https://arxiv.org/abs/2605.01806",
]

for url in urls:
    pid = url.split("/")[-1]
    r = subprocess.run(
        f'curl -sL "{url}" -H "User-Agent: Mozilla/5.0" -m 15',
        shell=True, capture_output=True, text=True, timeout=20
    )
    data = r.stdout
    
    # Extract title
    t = re.search(r"<h1 class=\"title mathjax\">(.*?)</h1>", data, re.DOTALL)
    title = ""
    if t:
        title = re.sub(r"<[^>]+>", "", t.group(1))
        title = html.unescape(title).strip().replace("\n", " ")

    # Extract abstract
    m = re.search(r"<blockquote class=\"abstract mathjax\">(.*?)</blockquote>", data, re.DOTALL)
    abstract = ""
    if m:
        text = re.sub(r"<[^>]+>", "", m.group(1))
        text = html.unescape(text).strip()
        abstract = re.sub(r"\s+", " ", text)[:800]
    
    print(f"\n{'='*50}")
    print(f"Paper: {pid}")
    if title:
        print(f"Title: {title}")
    if abstract:
        print(f"Abstract: {abstract}")
    print(f"{'='*50}")
