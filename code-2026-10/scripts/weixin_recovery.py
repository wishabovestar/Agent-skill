#!/usr/bin/env python3
"""WeChat iLink恢复检测 - 每10分钟检查一次
静默模式: iLink异常则静默，恢复时输出通知
"""
import json, os, sys, time, hashlib, platform

HOME = "D:\\hermes\\hermes-data\\profiles\\mybot"
ENV_FILE = os.path.join(HOME, ".env")
STATE_FILE = os.path.join(HOME, "gateway_state.json")
CACHE_FILE = os.path.join(HOME, "scripts", ".weixin_status_cache")

# 读token
TOKEN = ""
with open(ENV_FILE) as f:
    for line in f:
        if line.startswith("WEIXIN_TOKEN="):
            TOKEN = line.split("=", 1)[1].strip()
            break

if not TOKEN:
    print("[weixin-hb] 无WEIXIN_TOKEN")
    sys.exit(0)

def _base_info():
    return {'sdk_version': '1.0.0', 'os_version': platform.platform(), 'device_model': 'Hermes'}

def _jd(o):
    return json.dumps(o, separators=(',', ':'), ensure_ascii=False)

def _hd(token, body):
    ts = str(int(time.time()))
    sign = hashlib.sha256((ts + body).encode()).hexdigest()
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'Timestamp': ts,
        'Signature': sign,
    }

# 读取上次状态
last_errcode = None
try:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            last_errcode = json.load(f).get("errcode")
except: pass

import urllib.request, ssl
ctx = ssl._create_unverified_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

try:
    body = _jd({"get_updates_buf": "", "base_info": _base_info()})
    headers = _hd(TOKEN, body)
    req = urllib.request.Request(
        "https://ilinkai.weixin.qq.com/ilink/bot/getupdates",
        data=body.encode(),
        headers=headers,
    )
    resp = urllib.request.urlopen(req, context=ctx, timeout=15)
    data = json.loads(resp.read())
    errcode = data.get("errcode", 0)
    
    # 写入缓存
    with open(CACHE_FILE, "w") as f:
        json.dump({"errcode": errcode, "ts": time.time()}, f)
    
    # 上次是-14(异常), 这次正常 → 恢复通知
    if last_errcode == -14 and errcode != -14:
        print(f"🎉 WeChat iLink已恢复! errcode={errcode}")
        print(f"   响应: {json.dumps(data, ensure_ascii=False)[:200]}")
    # 持续异常 → 静默
    # 首次检查 → 静默
    # 恢复正常后持续正常 → 静默
    
except Exception as e:
    # 网络错误 → 静默（可能是暂时性问题）
    pass
