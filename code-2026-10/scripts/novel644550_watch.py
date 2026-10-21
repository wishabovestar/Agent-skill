# -*- coding: utf-8 -*-
"""小说 644550 更新看门狗（no_agent cron 用）。

规则：
  - 抓目录页 → 取最大章号；与 state 里的 last_max 比对
  - 有新章：抓正文 → 追加到 novel644550_full.txt → stdout 打一行通知（cron 会发给用户）
  - 无新章：stdout 全空 → cron 不发任何消息（看门狗模式）
  - 抓取失败：不污染通知，只在 log 里记；连续失败 3 次才 stdout 报警一次

本机 python 的 ssl 对 ixdzs8 抛 UNEXPECTED_EOF ⇒ 一律走 curl --ssl-no-revoke。
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime

BOOK = "644550"
BASE = "https://ixdzs8.com/read/%s/" % BOOK
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

WORK = r"D:/hermes/analysis/_novel644550"
STATE = os.path.join(WORK, "_watch_state.json")
LOG = os.path.join(WORK, "_watch_log.txt")
FULL = os.path.join(WORK, "novel644550_full.txt")
JAR = os.path.join(WORK, "_cookies.txt")


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("%s\t%s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg))


def get(url, referer=None, tries=3):
    cmd = ["curl", "-sS", "--ssl-no-revoke", "-m", "45", "-A", UA,
           "-c", JAR, "-b", JAR, "-H", "Accept-Language: zh-CN,zh;q=0.9"]
    if referer:
        cmd += ["-e", referer]
    cmd.append(url)
    err = b""
    for i in range(tries):
        p = subprocess.run(cmd, capture_output=True)
        if p.stdout:
            for enc in ("utf-8", "gbk"):
                try:
                    return p.stdout.decode(enc)
                except Exception:  # noqa: BLE001
                    pass
            return p.stdout.decode("utf-8", "replace")
        err = p.stderr
        time.sleep(2 * (i + 1))
    raise RuntimeError("empty body: %s" % err[:160])


def toc():
    html = get(BASE)
    nums = sorted({int(n) for n in re.findall(r"/read/%s/p(\d+)\.html" % BOOK, html)})
    titles = {}
    for n in nums:
        m = re.search(r'/read/%s/p%d\.html"[^>]*>\s*([^<]{0,90})<' % (BOOK, n), html)
        titles[n] = m.group(1).strip() if m else ""
    return nums, titles


def chapter(num):
    url = "https://ixdzs8.com/read/%s/p%d.html" % (BOOK, num)
    html = get(url, BASE)
    # JS challenge：页面里带 token，必须带 ?challenge=<token> 再取一次
    for _ in range(4):
        m = re.search(r'let\s+token\s*=\s*"([^"]+)"', html)
        if not (m and "正在验证浏览器" in html):
            break
        html = get(url + "?challenge=" + urllib.parse.quote(m.group(1)), BASE)
    if "正在验证浏览器" in html:
        raise RuntimeError("CHALLENGE_UNSOLVED p%d" % num)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    title = re.sub(r"<[^>]+>", "", h1.group(1)).strip() if h1 else "第%d章" % num
    art = re.search(r'<article[^>]*class="[^"]*page-content[^"]*"[^>]*>(.*?)</article>', html, re.S)
    seg = art.group(1) if art else "\n".join(re.findall(r"<p[^>]*>(.*?)</p>", html, re.S))
    seg = re.sub(r"<script.*?</script>|<style.*?</style>", "", seg, flags=re.S)
    seg = re.sub(r"<br\s*/?>|</p>", "\n", seg)
    seg = re.sub(r"<[^>]+>", "", seg)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'), ("&lt;", "<"),
                 ("&gt;", ">"), ("&#39;", "'"), ("&ldquo;", "“"), ("&rdquo;", "”")):
        seg = seg.replace(a, b)
    lines = [x.strip() for x in seg.split("\n") if x.strip() and not x.strip().startswith("爱下电子书")]
    # 章节页正文常把标题也放进去一行，去掉避免 full.txt 出现重复标题
    while lines and lines[0] == title:
        lines = lines[1:]
    body = "\n".join(lines)
    # ⚠️ 判据必须能失败：2026-10-19 09:00 那次把反爬页「請稍等，正在進行安全驗證…」当正文写进了 full.txt。
    for bad in ("安全驗證", "正在進行安全驗證", "請稍等", "正在验证浏览器", "Just a moment"):
        if bad in body:
            raise RuntimeError("ANTIBOT_PAGE p%d (%s)" % (num, bad))
    if len(body) < 400:
        raise RuntimeError("TOO_SHORT p%d (%d chars)" % (num, len(body)))
    return title, body


def main():
    verbose = "--verbose" in sys.argv
    st = {"last_max": 0, "total_chars": 0, "fails": 0}
    if os.path.exists(STATE):
        try:
            st.update(json.load(open(STATE, encoding="utf-8")))
        except Exception:  # noqa: BLE001
            pass

    try:
        nums, titles = toc()
    except Exception as e:  # noqa: BLE001
        st["fails"] = int(st.get("fails", 0)) + 1
        log("TOC FAIL(%d) %s" % (st["fails"], e))
        json.dump(st, open(STATE, "w", encoding="utf-8"))
        if verbose:
            print("[verbose] toc failed:", e)
        if st["fails"] >= 3:
            print("⚠️ 小说 %s 目录连续 %d 次抓取失败，请检查站点是否改版。" % (BOOK, st["fails"]))
        return 0

    st["fails"] = 0
    mx = nums[-1]
    if verbose:
        print("[verbose] toc max=%d last_max=%d missing=%s"
              % (mx, st["last_max"], [x for x in range(nums[0], mx + 1) if x not in nums]))

    if mx <= st["last_max"]:
        json.dump(st, open(STATE, "w", encoding="utf-8"))
        log("no update (max=%d)" % mx)
        return 0

    new_nums = list(range(st["last_max"] + 1, mx + 1)) if st["last_max"] else [mx]
    got, failed = [], []
    for n in new_nums:
        try:
            t, body = chapter(n)
        except Exception as e:  # noqa: BLE001
            failed.append(n)
            log("chapter p%d FAIL %s" % (n, e))
            continue
        got.append((n, t or titles.get(n, ""), body))

    if got:
        mode = "a" if os.path.exists(FULL) else "w"
        with open(FULL, mode, encoding="utf-8") as f:
            for n, t, body in got:
                f.write("\n\n" + (t or "第%d章" % n) + "\n\n" + body)
        added = sum(len(b) for _, _, b in got)
        st["total_chars"] = int(st.get("total_chars", 0)) + added
        # ⚠️ 只沿连续成功的章节推进 last_max：若中间有失败章，跳过它会让那章永久丢失
        base = int(st.get("last_max", 0))
        ok = {n for n, _, _ in got}
        nl = base
        while (nl + 1) in ok:
            nl += 1
        if not base:
            nl = max(ok)
        st["last_max"] = nl
        json.dump(st, open(STATE, "w", encoding="utf-8"))
        log("updated to p%d chapters=%d chars=+%d out_of_order=%s"
            % (nl, len(got), added, [n for n in sorted(ok) if n > nl]))
        heads = "、".join("%d %s" % (n, t) for n, t, _ in got if n <= nl) or "（见 log）"
        print("📖 小说 %s 更新 %d 章（至第 %d 章）：%s\n全文已追加到 %s（累计 %d 字）"
              % (BOOK, len([n for n in ok if n <= nl]), nl, heads, FULL, st["total_chars"]))
    if failed:
        print("⚠️ 小说 %s 有 %d 章抓取失败：%s" % (BOOK, len(failed), failed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
