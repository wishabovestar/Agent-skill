"""
Check Turing book site HTML structure
"""
import subprocess, re

url = "https://www.ituring.com.cn/book?tab=book&sort=hot&category=ai"
r = subprocess.run(
    'curl -sL "' + url + '" -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)" -m 20',
    shell=True, capture_output=True, text=True, timeout=25
)
data = r.stdout
print(f"Page size: {len(data)} bytes")

# Find book-related sections
sections = re.findall(r'<div[^>]*class="[^"]*book[^"]*"[^>]*>.*?</div>', data, re.DOTALL)
print(f"Found {len(sections)} book divs")

# Show first book div
if sections:
    for s in sections[:3]:
        print("---BOOK DIV---")
        # Extract links
        links = re.findall(r'href="([^"]+)"[^>]*>(.*?)<', s, re.DOTALL)
        for href, text in links[:5]:
            text = re.sub(r'<[^>]+>', '', text).strip()
            if text and len(text) > 5:
                print(f"  {href} -> {text[:80]}")
        print()
else:
    # Look for any title-like content
    titles = re.findall(r'<a[^>]*href="(/book/\d+)"[^>]*>(.*?)</a>', data, re.DOTALL)
    print(f"Found {len(titles)} book links")
    for href, text in titles[:10]:
        text = re.sub(r'<[^>]+>', '', text).strip()
        if text:
            print(f"  {href} -> {text[:80]}")
