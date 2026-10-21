#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""API-level platform tests + lock-holder identification. Never prints secrets."""
import json, os, re, subprocess, sys, socket, urllib.request, ssl, datetime

ROOT = r"D:\hermes\hermes-data\profiles"
PROFS = ["dong", "linshuo", "mybot", "qqbot2", "qqbot3", "qqbot4", "qqbot5", "wenming"]
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def env(path):
    d = {}
    if not os.path.isfile(path):
        return d
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        d[k.strip()] = v.strip()
    return d

def post(url, data, headers=None, timeout=12):
    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.status, r.read(400).decode("utf-8", "replace")
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:150]}"

print("=" * 78); print("API-LEVEL TESTS  " + str(datetime.datetime.now())); print("=" * 78)

# --- 1. who holds the locks ---
print("\n### 1. LOCK HOLDERS (PID 19876 weixin / PID 17216 feishu)\n")
try:
    r = subprocess.run(["wmic", "process", "get", "ProcessId,CommandLine"], capture_output=True)
    out = r.stdout.decode("gbk", errors="replace")
    for line in out.splitlines():
        if re.search(r"\b(19876|17216|17928|10576|23336|21440|17492|19420|4164)\b", line) and "wmic" not in line:
            print("  " + line.strip()[:190])
except Exception as e:
    print("  wmic failed:", e)

# --- 2. WeChat iLink direct API ---
print("\n### 2. WECHAT iLINK getupdates (直测)\n")
for p in PROFS:
    e = env(os.path.join(ROOT, p, ".env"))
    tok = e.get("WEIXIN_TOKEN", "")
    if not tok:
        print(f"  {p:9s} WEIXIN_TOKEN empty/absent -> 未配置或凭证缺失")
        continue
    url = (e.get("WEIXIN_BASE_URL") or "https://ilinkai.weixin.qq.com").rstrip("/")
    url = url + "/ilink/bot/getupdates"
    st, body = post(url, {"get_updates_buf": ""}, {"Authorization": "Bearer " + tok})
    verdict = "OK" if '"ret":0' in body or '"errcode":0' in body else "!!"
    print(f"  {p:9s} http={st} {verdict} body={body[:160]}")

# --- 3. QQ Bot access token per profile ---
print("\n### 3. QQ BOT access token (api.q.qq.com)\n")
for p in PROFS:
    e = env(os.path.join(ROOT, p, ".env"))
    aid, sec = e.get("QQ_APP_ID", ""), e.get("QQ_CLIENT_SECRET", "")
    if not aid or not sec:
        print(f"  {p:9s} QQ creds absent")
        continue
    st, body = post("https://api.q.qq.com/api/getAppAccessToken",
                    {"appId": aid, "clientSecret": sec})
    body_s = body if not isinstance(body, str) or len(body) < 200 else body[:200]
    print(f"  {p:9s} appid=...{aid[-4:]} http={st} body={body_s[:170]}")

# --- 4. DingTalk / Feishu credential validity ---
print("\n### 4. DINGTALK + FEISHU credential tests\n")
for p in PROFS:
    e = env(os.path.join(ROOT, p, ".env"))
    if e.get("DINGTALK_CLIENT_ID") and e.get("DINGTALK_CLIENT_SECRET"):
        st, body = post("https://api.dingtalk.com/v1.0/oauth2/accessToken",
                        {"appKey": e["DINGTALK_CLIENT_ID"], "appSecret": e["DINGTALK_CLIENT_SECRET"]})
        ok = "accessToken" in (body or "")
        print(f"  {p:9s} dingtalk http={st} {'OK' if ok else '!! ' + body[:150]}")
    if e.get("FEISHU_APP_ID") and e.get("FEISHU_APP_SECRET"):
        st, body = post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                        {"app_id": e["FEISHU_APP_ID"], "app_secret": e["FEISHU_APP_SECRET"]})
        ok = '"code":0' in (body or "")
        print(f"  {p:9s} feishu   http={st} {'OK' if ok else '!! ' + body[:150]}")

# --- 5. DNS / TCP reachability ---
print("\n### 5. DNS + TCP 443 reachability\n")
for host in ["ilinkai.weixin.qq.com", "api.sgroup.qq.com", "api.q.qq.com",
             "api.dingtalk.com", "open.feishu.cn"]:
    try:
        ip = socket.gethostbyname(host)
        try:
            s = socket.create_connection((host, 443), timeout=6); s.close(); tcp = "TCP OK"
        except Exception as ex:
            tcp = f"TCP FAIL ({type(ex).__name__})"
        print(f"  {host:28s} dns={ip:16s} {tcp}")
    except Exception as ex:
        print(f"  {host:28s} DNS FAIL ({type(ex).__name__})")
print("\nDONE")
