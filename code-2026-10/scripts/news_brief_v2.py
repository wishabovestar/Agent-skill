# -*- coding: utf-8 -*-
"""新闻早报 v2（no_agent 版）—— 唯一已实测可用的源：
   新浪滚动 / IT之家 RSS / arXiv cs.AI / HN front_page / 广期所碳酸锂 LC0(新浪行情)
   已废弃：Bing News RSS（返首页 HTML，<item>=0）、Google News（直连超时）
   输出：stdout 即投递正文（markdown），全部数字来自本次实抓。
"""
import ssl, sys, io, json, re, time, urllib.request
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                     urllib.request.HTTPSHandler(context=CTX))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
FAIL = []


def fetch(url, timeout=25, referer=None, tries=2, enc=None):
    for i in range(tries):
        try:
            h = {"User-Agent": UA, "Accept": "*/*"}
            if referer:
                h["Referer"] = referer
            with OPENER.open(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                FAIL.append("%s: %s" % (url.split("/")[2], type(e).__name__))
            time.sleep(2)
    return None


sina, ith, ax, hn, price = [], [], [], [], ""
today = datetime.now()

# 1) 新浪滚动（综合/国内）
raw = fetch("https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2515&k=&num=30&page=1")
if raw:
    try:
        for it in (json.loads(raw.decode("utf-8", "ignore")).get("result", {}).get("data") or []):
            t = (it.get("title") or "").strip()
            if t:
                sina.append(t)
    except Exception:
        FAIL.append("sina: parse")
else:
    FAIL.append("sina: fetch")

# 2) IT之家 RSS（科技）
raw = fetch("https://www.ithome.com/rss/")
if raw:
    try:
        root = ET.fromstring(raw)
        for it in root.iter("item"):
            t = re.sub(r"\s+", " ", (it.findtext("title") or "")).strip()
            if t:
                ith.append(t)
    except Exception:
        FAIL.append("ithome: parse")
else:
    FAIL.append("ithome: fetch")

# 3) arXiv cs.AI 最新
raw = fetch("http://export.arxiv.org/rss/cs.AI")
if raw:
    try:
        root = ET.fromstring(raw)
        for it in list(root.iter("item"))[:12]:
            t = re.sub(r"\s+", " ", (it.findtext("title") or "")).strip()
            if t:
                ax.append(t)
    except Exception:
        FAIL.append("arxiv: parse")
else:
    FAIL.append("arxiv: fetch")

# 4) HN 首页（技术热度）
raw = fetch("https://hn.algolia.com/api/v1/search?tags=front_page")
if raw:
    try:
        for it in (json.loads(raw.decode("utf-8", "ignore")).get("hits") or [])[:10]:
            if it.get("title"):
                hn.append("%s（%s 分）" % (it["title"], it.get("points")))
    except Exception:
        FAIL.append("hn: parse")
else:
    FAIL.append("hn: fetch")

# 5) 广期所碳酸锂主连 LC0
raw = fetch("https://hq.sinajs.cn/list=nf_LC0", referer="https://finance.sina.com.cn")
if raw:
    try:
        txt = raw.decode("gbk", "ignore")
        f = txt.split('"')[1].split(",")
        o, hi, lo, last, pre = (float(f[2]), float(f[3]), float(f[4]),
                                float(f[8]), float(f[10]))
        oi, vol = int(float(f[13])), int(float(f[14]))
        pct = (last - pre) / pre * 100 if pre else 0.0
        price = ("**碳酸锂主连 LC0**（%s）：最新 **%s** 元/吨，昨结 %s，"
                 "**%+.2f%%**；日内 %s–%s；持仓 **%s 手**，成交 %s 手"
                 % (f[1][:2] + ":" + f[1][2:4], format(int(last), ","), format(int(pre), ","),
                    pct, format(int(lo), ","), format(int(hi), ","),
                    format(oi, ","), format(vol, ",")))
    except Exception as e:
        FAIL.append("LC0: parse %s" % type(e).__name__)
        price = "**碳酸锂 LC0**：抓取异常（%s）" % type(e).__name__
else:
    FAIL.append("LC0: fetch")

# ---- 组装 ----
L = ["## 新闻早报 · %s" % today.strftime("%Y-%m-%d %H:%M"), ""]
L.append("### 一、锂电 / 商品")
L.append(price if price else "**未获取到**（新浪行情不可达）")
L.append("")
L.append("### 二、科技（IT之家 RSS %d 条）" % len(ith))
for t in ith[:12]:
    L.append("- " + t)
L.append("")
L.append("### 三、产业 / 宏观（新浪滚动 %d 条）" % len(sina))
for t in sina[:12]:
    L.append("- " + t)
L.append("")
L.append("### 四、技术热度（HN 首页）")
for t in hn[:8]:
    L.append("- " + t)
L.append("")
L.append("### 五、arXiv cs.AI 最新 %d 篇" % len(ax))
for t in ax[:8]:
    L.append("- " + t)
L.append("")

# ---- 六、算法与论文（读 cron 产物；缺失即报，不静默）----
import glob as _glob
import io as _io
import os as _os
import json as _json


def _latest(pat):
    fs = sorted(_glob.glob(pat), key=_os.path.getmtime)
    return fs[-1] if fs else None


_PROF = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
AK = "D:/hermes/data/agent_knowledge/algorithm"          # 夜巡 / A线 / 白日梦台账
COUT = _PROF + "/cron/output"                             # 睡眠报告


L.append("### 六、算法与论文")
_alg = []

# 1) 夜巡（arXiv 新投稿）
_f = _latest(AK + "/night_watch_*.json")
if not _f:
    FAIL.append("night_watch: 无产物")
    _alg.append("- 夜巡：**未获取到**（无 JSON 产物）")
else:
    try:
        _d = _json.load(_io.open(_f, encoding="utf-8"))
        _rows = _d.get("rows") or []
        _new = [r for r in _rows if "New" in ((r.get("sec") or ""))]
        _hot = sorted([r for r in _new if (r.get("B") or 0) >= 15],
                      key=lambda r: -(r.get("B") or 0))
        _date = _os.path.basename(_f).replace("night_watch_", "").replace(".json", "")
        _alg.append("- 夜巡（%s）：去重 %d 条 · 新投稿 %d · B≥15 **%d 条**"
                    % (_date, len(_rows), len(_new), len(_hot)))
        for _r in _hot[:3]:
            _alg.append("  - %s %s" % (_r.get("B"), (_r.get("title") or "")[:58]))
    except Exception as _e:
        FAIL.append("night_watch: %s" % type(_e).__name__)
        _alg.append("- 夜巡：解析失败（%s）" % type(_e).__name__)

# 2) A 线增量
_f = _latest(AK + "/a_incremental_*.json")
if not _f:
    FAIL.append("a_incremental: 无产物")
    _alg.append("- A 线增量：**未获取到**（无 JSON 产物）")
else:
    try:
        _d = _json.load(_io.open(_f, encoding="utf-8"))
        _it = _d.get("items") or []
        _good = [x for x in _it if (x.get("score") or 0) >= 4]
        _alg.append("- A 线增量（%s，近窗）：取回 %d · 新增 %d · 过阈 **%d**"
                    % (_d.get("date"), _d.get("fetched", 0), _d.get("fresh", 0), len(_good)))
        for _x in sorted(_good, key=lambda x: -(x.get("score") or 0))[:3]:
            _alg.append("  - %s %s" % (_x.get("score"), (_x.get("title") or "")[:58]))
    except Exception as _e:
        FAIL.append("a_incremental: %s" % type(_e).__name__)
        _alg.append("- A 线增量：解析失败（%s）" % type(_e).__name__)

# 3) 白日梦跨域接受率
_f = AK + "/dream_accept_ledger.json"
try:
    _n = _json.load(_io.open(_f, encoding="utf-8")).get("nights") or []
except Exception:
    _n = []
if not _n:
    FAIL.append("daydream: 无台账")
    _alg.append("- 白日梦：**未获取到**（无台账）")
else:
    _x = _n[-1]
    _alg.append("- 白日梦（%s）：试 %d 收 %d · 空谈 %d/跨天 %d"
                % (_x.get("date"), _x.get("attempted", 0), _x.get("accepted", 0),
                   (_x.get("rej") or {}).get("ungrounded", 0),
                   (_x.get("rej") or {}).get("dup_prev", 0)))
    if len(_n) >= 3:
        _t = _n[-3:]
        _alg.append("  三晚合计 %d/%d 接受" % (sum(i.get("accepted", 0) for i in _t),
                                             sum(i.get("attempted", 0) for i in _t)))

# 4) 睡眠整合（MEMORY 占用）
_f = _latest(COUT + "/sleep_consolidation_*.json")
try:
    _d = _json.load(_io.open(_f, encoding="utf-8")) if _f else {}
    _s = _d.get("stage1_memory") or {}
    _m = _d.get("stage1_migration") or {}
    if _s:
        _alg.append("- 睡眠（%s）：MEMORY **%s%%**（%s/%s）· 待迁 %d 条 / 可释放 %s 字符"
                    % (_os.path.basename(_f).replace("sleep_consolidation_", "").replace(".json", ""),
                       _s.get("pct"), _s.get("chars"), _s.get("limit"),
                       len(_m.get("candidates") or []), _m.get("chars_freed")))
    else:
        _alg.append("- 睡眠：产物无 stage1_memory")
except Exception as _e:
    FAIL.append("sleep: %s" % type(_e).__name__)
    _alg.append("- 睡眠：解析失败（%s）" % type(_e).__name__)

L.extend(_alg)
L.append("")

# ---- 七、疫情（WHO Disease Outbreak News · 近 30 日）----
L.append("### 七、疫情（WHO DON）")
try:
    _u = ("https://www.who.int/api/news/diseaseoutbreaknews"
          "?$orderby=PublicationDateAndTime%20desc&$top=20")
    _b = fetch(_u, timeout=30, tries=2)
    _v = []
    if _b:
        _v = (_json.loads(_b.decode("utf-8", "replace")) or {}).get("value") or []
    if not _v:
        FAIL.append("WHO DON: 0 条")
        L.append("- **未获取到**（API 返空列表）")
    else:
        import datetime as _dt
        _now = _dt.datetime.now(_dt.timezone.utc)
        _rows = []
        for _it in _v:
            _ts = _it.get("PublicationDateAndTime") or _it.get("PublicationDate") or ""
            try:
                _d = _dt.datetime.strptime(_ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=_dt.timezone.utc)
            except Exception:
                continue
            _rows.append((_d, _it))
        _rows.sort(key=lambda x: -x[0].timestamp())
        _recent = [x for x in _rows if (_now - x[0]).days <= 30]
        _oldest = _rows[-1][0].strftime("%Y-%m-%d") if _rows else "—"
        L.append("- 近 30 日通报 **%d 条**（API 取回 %d，最早 %s）；最新：%s"
                 % (len(_recent), len(_rows), _oldest,
                    _rows[0][0].strftime("%m-%d") if _rows else "—"))
        if not _recent:
            L.append("  - 近 30 日无新通报（最新一条在 30 日窗之外）")
        for _d, _it in _recent[:4]:
            _t = (_it.get("Title") or "").strip()
            _slug = _it.get("ItemDefaultUrl") or ""
            _url = ("https://www.who.int/emergencies/disease-outbreak-news/item/"
                    + _slug.rstrip("/").split("/")[-1]) if _slug else ""
            L.append("  - %s %s%s" % (_d.strftime("%m-%d"), _t[:64],
                                      ("  " + _url) if _url else ""))
except Exception as _e:
    FAIL.append("WHO DON: %s" % type(_e).__name__)
    L.append("- **未获取到**（%s）" % type(_e).__name__)
L.append("")

# 空列表不得计为“实抓成功”（arXiv RSS 常回 200 但 0 条）
for _nm, _seq in (("sina", sina), ("ithome", ith), ("arxiv", ax), ("hn", hn)):
    if not _seq:
        FAIL.append("%s: 0 条（解析成功但为空）")
        FAIL[-1] = FAIL[-1] % _nm

if FAIL:
    L.append("> ⚠️ 本次失败源：%s" % "；".join(sorted(set(FAIL))))
    L.append("> 疫情段（WHO DON）取自官方 API，仅列 30 日内通报。")
else:
    L.append("> 全部源实抓成功。")
print("\n".join(L))
