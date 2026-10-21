#!/usr/bin/env python3
"""Google News RSS 链接解析器 (2026-09-19 验证: 11/11 成功)

背景: news.google.com/rss/articles/CBMi... 链接无法用 curl -L 解析 ——
      服务端返回 JS 外壳页(约 590KB), 真实 URL 不出现。
可行路径: ① 取文章页的 data-n-a-id / data-n-a-ts / data-n-a-sg
          ② POST https://news.google.com/_/DotsSplashUi/data/batchexecute
             body: f.req=[[["Fbv4je","[\\"garturlreq\\",...],\\"<id>\\",<ts>,\\"<sg>\\"]",null,"generic"]]]
          ③ 响应以 )]}' 开头, json 解析后 row[2] 再 json.loads -> [1] 即真实 URL

本机直连 news.google.com 会超时 → 全程经 VPS 中继 (vps_ssh.py exec curl)。
用法: python gn_link_resolver.py <gnews_url> [<gnews_url> ...]
      python gn_link_resolver.py --file urls.txt
"""
import json
import re
import subprocess
import sys
import os

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
REQ = ('[[["Fbv4je","[\\"garturlreq\\",[[\\"en-US\\",\\"US\\",'
       '[\\"FINANCE_TOP_INDICES\\",\\"WEB_TEST_1_0_0\\"],null,null,1,1,\\"US:en\\",'
       'null,180,null,null,null,null,null,0,null,null,[1608992183,723341000]],'
       '\\"en-US\\",\\"US\\",1,[2,3,4,8],1,0,\\"655000234\\",0,0,null,0],'
       '\\"%s\\",%s,\\"%s\\"]",null,"generic"]]]')
VPS = "D:/hermes/analysis/vps_ssh.py"


def _vps(cmd, timeout=280):
    r = subprocess.run([sys.executable, VPS, "exec", cmd], capture_output=True,
                       text=True, errors="ignore", timeout=timeout, cwd="D:/hermes/analysis")
    return r.stdout


def fetch_pages(links, chunk=8):
    """links: [(tag, url)] -> {tag: html}"""
    pages = {}
    for i in range(0, len(links), chunk):
        part = links[i:i + chunk]
        cmd = " ; ".join("echo '===ART:%s==='; curl -sL --max-time 25 -A '%s' '%s'" % (t, UA, u)
                         for t, u in part)
        out = _vps(cmd)
        segs = re.split(r"===ART:(\w+)===", out)
        for k in range(1, len(segs), 2):
            pages[segs[k]] = segs[k + 1]
    return pages


def resolve(pages):
    """pages: {tag: html} -> {tag: real_url}"""
    posts = []
    for tag, html in pages.items():
        mid = re.search(r'data-n-a-id="([^"]+)"', html)
        mts = re.search(r'data-n-a-ts="([^"]+)"', html)
        msg = re.search(r'data-n-a-sg="([^"]+)"', html)
        if not (mid and mts and msg):
            continue
        body = REQ % (mid.group(1), mts.group(1), msg.group(1))
        posts.append("echo '===DEC:%s===' ; curl -s --max-time 30 -A '%s' "
                     "-H 'Content-Type: application/x-www-form-urlencoded;charset=UTF-8' "
                     "--data-urlencode 'f.req=%s' "
                     "'https://news.google.com/_/DotsSplashUi/data/batchexecute'"
                     % (tag, UA, body))
    if not posts:
        return {}
    out = _vps(" ; ".join(posts))
    res = {}
    segs = re.split(r"===DEC:(\w+)===", out)
    for k in range(1, len(segs), 2):
        tag, body = segs[k], segs[k + 1].split(")]}'", 1)[-1].strip()
        try:
            for row in json.loads(body):
                if isinstance(row, list) and len(row) > 2 and isinstance(row[2], str):
                    inner = json.loads(row[2])
                    if isinstance(inner, list) and len(inner) > 1:
                        res[tag] = inner[1]
                        break
        except Exception as e:
            res[tag] = "PARSE_ERR " + str(e)[:60]
    return res


def main():
    args = sys.argv[1:]
    if args and args[0] == "--file":
        links = [(str(i), l.strip()) for i, l in enumerate(open(args[1], encoding="utf-8")) if l.strip()]
    else:
        links = [(str(i), u) for i, u in enumerate(args)]
    if not links:
        print(__doc__)
        return
    pages = fetch_pages(links)
    res = resolve(pages)
    for tag, url in links:
        print("%s\t%s" % (tag, res.get(tag, "UNRESOLVED")))


if __name__ == "__main__":
    main()
