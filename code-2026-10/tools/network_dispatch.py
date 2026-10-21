"""
调度工作流：检测内容能否直连收集，不能则通过10808代理
"""
import urllib.request, json, time, socket

PROXY = "socks5://127.0.0.1:10808"
TIMEOUT_DIRECT = 8
TIMEOUT_PROXY = 15

def try_direct(url):
    """尝试直连"""
    try:
        socket.setdefaulttimeout(TIMEOUT_DIRECT)
        r = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(r, timeout=TIMEOUT_DIRECT) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except:
        return None

def try_proxy(url):
    """通过10808代理"""
    try:
        p = urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY})
        o = urllib.request.build_opener(p)
        r = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with o.open(r, timeout=TIMEOUT_PROXY) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except:
        return None

def fetch(url, label=""):
    """智能调度：直连优先→代理fallback"""
    result = try_direct(url)
    if result:
        print(f"  ✅ [直连] {label}")
        return result
    result = try_proxy(url)
    if result:
        print(f"  ✅ [10808] {label}")
        return result
    print(f"  ❌ {label}: 直连+代理均不可达")
    return None

if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://arxiv.org"
    label = sys.argv[2] if len(sys.argv) > 2 else url[:40]
    fetch(url, label)
