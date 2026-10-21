"""
Fetch Turing book list + final searches
"""
import subprocess, re, html, json, os
from pathlib import Path

def curl_fetch(url):
    try:
        r = subprocess.run(
            f'curl -sL "{url}" -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)" -m 20',
            shell=True, capture_output=True, text=True, timeout=25
        )
        return r.stdout
    except:
        return ""

# 1. Fetch Turing AI book list
print("=== 图灵AI图书 ===")
data = curl_fetch("https://www.ituring.com.cn/book?tab=book&sort=hot&category=ai")
books = re.findall(r'<a[^>]*href="(/book/\d+)"[^>]*class="[^"]*book-title[^"]*"[^>]*>(.*?)</a>', data, re.DOTALL)
for url, title in books[:15]:
    clean = re.sub(r'<[^>]+>', '', title).strip()
    print(f"  {html.unescape(clean)}")
    print(f"  https://www.ituring.com.cn{url}")
    print()

if not books:
    # Try simpler pattern
    titles = re.findall(r'class="book-title"[^>]*>\s*(.*?)\s*<', data, re.DOTALL)
    for t in titles[:15]:
        clean = re.sub(r'<[^>]+>', '', t).strip()
        clean = html.unescape(clean)
        if clean:
            print(f"  {clean}")
    print(f"\n(Page size: {len(data)} bytes)")

# 2. Try Google Books API for battery textbooks
print("\n=== Google Books: battery textbooks ===")
url = "https://www.googleapis.com/books/v1/volumes?q=lithium+ion+battery+textbook&maxResults=8&langRestrict=en"
data = curl_fetch(url)
try:
    j = json.loads(data)
    for item in j.get("items", []):
        info = item.get("volumeInfo", {})
        title = info.get("title", "")
        authors = ", ".join(info.get("authors", ["N/A"]))
        link = info.get("infoLink", "")
        year = info.get("publishedDate", "")[:4]
        print(f"  {title} ({year})")
        print(f"  By: {authors}")
        print(f"  {link}")
        print()
except:
    print(f"  API Error or blocked. Data: {data[:200]}")
