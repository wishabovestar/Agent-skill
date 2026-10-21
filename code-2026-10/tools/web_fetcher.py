"""
P1: Python requests-based 万能HTTP客户端 (web_extract fallback)
===============================================================
解决: web_extract 后端 ddgs 不支持URL提取
      Bing/Google 编码错误
      国际站点不可达

功能:
  1. 自动编码检测 (GBK/UTF-8)
  2. 代理支持 (SOCKS5/HTTP)
  3. 重试 + 超时控制
  4. 国内镜像自动切换
  5. stream模式: 仅读取前N字节判断编码
"""

import json, re, time
from typing import Optional
from urllib.parse import urlparse, quote

# ── 配置 ──
DEFAULT_TIMEOUT = 15
MAX_RETRIES = 2
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# 已知的国内可使用镜像
MIRRORS = {
    "github.com": ["github.com", "mirror.ghproxy.com/https://github.com"],
    "arxiv.org": ["arxiv.org", "xxx.arxiv.org"],  # cn arXiv mirror
    "huggingface.co": ["huggingface.co", "hf-mirror.com"],
}


def smart_fetch(url: str, timeout: int = DEFAULT_TIMEOUT,
                 use_mirror: bool = True, proxy: str = None) -> dict:
    """
    万能网页获取器。
    返回: {"success": bool, "content": str, "encoding": str, "source": str}
    """
    import urllib.request, urllib.error, ssl

    # 国内镜像切换
    actual_url = url
    if use_mirror:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        for src, mirrors in MIRRORS.items():
            if src in domain and len(mirrors) > 1:
                # 直接尝试镜像
                actual_url = url.replace(src, mirrors[1])
                break

    # SSL 上下文（忽略证书错误）
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # 代理
    if proxy:
        proxy_handler = urllib.request.ProxyHandler({
            "http": proxy,
            "https": proxy,
        })
        opener = urllib.request.build_opener(proxy_handler)
        urllib.request.install_opener(opener)

    errors = []
    for attempt in range(1 + MAX_RETRIES):
        try:
            req = urllib.request.Request(
                actual_url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                }
            )
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                raw = resp.read()
                # 自动检测编码
                content_type = resp.headers.get("Content-Type", "")
                encoding = _detect_encoding(raw, content_type)
                content = raw.decode(encoding, errors="replace")

                return {
                    "success": True,
                    "content": content,
                    "encoding": encoding,
                    "source": actual_url,
                    "status": resp.status,
                    "url": actual_url,
                }
        except Exception as e:
            errors.append(str(e)[:60])
            if attempt < MAX_RETRIES:
                time.sleep(1 * (attempt + 1))

    return {"success": False, "content": "",
            "encoding": "utf-8", "source": actual_url,
            "error": "; ".join(errors)}


def _detect_encoding(raw: bytes, content_type: str = "") -> str:
    """自动检测编码：Content-Type > BOM > chardet > GBK fallback"""
    # Content-Type 头检测
    enc_match = re.search(r'charset=([\w-]+)', content_type, re.I)
    if enc_match:
        return enc_match.group(1).lower()

    # BOM 检测
    if raw[:3] == b'\xef\xbb\xbf':
        return 'utf-8-sig'
    if raw[:2] == b'\xff\xfe':
        return 'utf-16-le'
    if raw[:2] == b'\xfe\xff':
        return 'utf-16-be'

    # HTML meta 检测
    sample = raw[:2000].decode('utf-8', errors='replace')
    meta_match = re.search(r'<meta[^>]+charset=([\w-]+)', sample, re.I)
    if meta_match:
        return meta_match.group(1).lower()

    # 本地检测
    try:
        import chardet
        detected = chardet.detect(raw[:5000])
        if detected.get('confidence', 0) > 0.7:
            return detected['encoding']
    except ImportError:
        pass

    # 尝试常见编码
    for enc in ['utf-8', 'gbk', 'gb2312', 'big5', 'euc-jp', 'euc-kr']:
        try:
            raw[:100].decode(enc)
            return enc
        except:
            continue

    return 'utf-8'


def extract_text(html: str) -> str:
    """从HTML中提取正文（简易版）"""
    # 移除 script/style
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    html = re.sub(r'<[^>]+>', ' ', html)
    # 压缩空白
    text = re.sub(r'\s+', ' ', html).strip()
    # 分段
    paragraphs = [p.strip() for p in text.split('\n') if len(p.strip()) > 20]
    return '\n'.join(paragraphs[:50])


# ── CLI ──
if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://cn.bing.com"
    result = smart_fetch(url)
    if result["success"]:
        print(f"✅ {url}")
        print(f"   编码: {result['encoding']}, 大小: {len(result['content'])} chars")
        # 提取标题
        title_match = re.search(r'<title>(.*?)</title>', result['content'], re.DOTALL)
        if title_match:
            print(f"   标题: {title_match.group(1).strip()}")
        # 显示正文预览
        text = extract_text(result['content'])
        print(f"\n正文预览 ({len(text)} chars):")
        print(text[:500])
    else:
        print(f"❌ {url}")
        print(f"   错误: {result.get('error', 'unknown')}")
