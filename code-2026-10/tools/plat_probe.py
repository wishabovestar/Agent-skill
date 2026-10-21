import json, os, ssl, urllib.request, urllib.error, socket, time

ENV = {}
for p in ['mybot', 'qqbot2', 'qqbot3', 'qqbot4', 'qqbot5', 'dong']:
    f = r'D:/hermes/hermes-data/profiles/%s/.env' % p
    if not os.path.exists(f):
        continue
    for line in open(f, encoding='utf-8', errors='replace'):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        ENV.setdefault(p, {})[k.strip()] = v.strip().strip('"').strip("'")

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

def post(url, payload, headers=None, timeout=25):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return r.status, r.read(600).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read(300).decode('utf-8', 'replace')
    except Exception as e:
        return None, '%s: %s' % (type(e).__name__, str(e)[:120])

def get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return r.status, r.read(600).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read(300).decode('utf-8', 'replace')
    except Exception as e:
        return None, '%s: %s' % (type(e).__name__, str(e)[:120])

print("=== 1. QQ (每个 profile 各自的 appid) ===")
for p in ['mybot', 'qqbot2', 'qqbot3', 'qqbot4', 'qqbot5', 'dong']:
    e = ENV.get(p, {})
    aid, sec = e.get('QQ_APP_ID'), e.get('QQ_CLIENT_SECRET')
    if not (aid and sec):
        print("  %-8s SKIP (无凭据)" % p); continue
    st, body = post('https://bots.qq.com/app/getAppAccessToken', {'appId': aid, 'clientSecret': sec})
    ok = '"access_token"' in body
    print("  %-8s appid=%s… http=%s  %s" % (p, aid[:6], st, 'TOKEN_OK' if ok else body[:110].replace('\n', ' ')))

print("\n=== 2. Feishu (mybot) ===")
e = ENV['mybot']
st, body = post('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
                {'app_id': e.get('FEISHU_APP_ID'), 'app_secret': e.get('FEISHU_APP_SECRET')})
try:
    j = json.loads(body); print("  http=%s code=%s msg=%s token=%s" % (st, j.get('code'), j.get('msg'), 'YES' if j.get('tenant_access_token') else 'NO'))
except Exception:
    print("  http=%s %s" % (st, body[:160]))

print("\n=== 3. DingTalk (mybot) ===")
st, body = post('https://api.dingtalk.com/v1.0/oauth2/accessToken',
                {'appKey': e.get('DINGTALK_CLIENT_ID'), 'appSecret': e.get('DINGTALK_CLIENT_SECRET')})
try:
    j = json.loads(body); print("  http=%s token=%s expireIn=%s err=%s" % (st, 'YES' if j.get('accessToken') else 'NO', j.get('expireIn'), j.get('message')))
except Exception:
    print("  http=%s %s" % (st, body[:160]))

print("\n=== 4. Weixin iLink (mybot) ===")
tok = e.get('WEIXIN_TOKEN')
if not tok:
    print("  SKIP (无 WEIXIN_TOKEN)")
else:
    for url in ['https://ilinkai.weixin.qq.com/ilink/bot/getupdates']:
        st, body = post(url, {}, headers={'Authorization': 'Bearer ' + tok})
        print("  POST %s http=%s %s" % (url.split('/ilink')[1], st, body[:200].replace('\n', ' ')))

print("\n=== 5. Photon 本地 sidecar ===")
for path in ['/', '/health', '/healthz']:
    st, body = get('http://127.0.0.1:8789' + path, timeout=6)
    print("  GET %-8s -> %s %s" % (path, st, (body or '')[:80].replace('\n', ' ')))
    if st:
        break

print("\n=== 6. 端口监听 ===")
for port in (8789, 8080, 11434):
    s = socket.socket(); s.settimeout(1.2)
    r = s.connect_ex(('127.0.0.1', port)); s.close()
    print("  127.0.0.1:%-5d %s" % (port, 'OPEN' if r == 0 else 'closed'))
