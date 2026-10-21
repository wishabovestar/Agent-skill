import json, os, subprocess, sys, time

STATE = r'D:\hermes\hermes-data\gateway_state.json'
EXE = r'C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.exe'
TASK = 'Hermes_Gateway_76bff4d2'


def state():
    try:
        return json.load(open(STATE, encoding='utf-8'))
    except Exception:
        return {}


pid0 = state().get('pid')
print("BEFORE pid=%s" % pid0, flush=True)

r = subprocess.run([EXE, '-p', 'default', 'gateway', 'stop'], capture_output=True, text=True, timeout=240)
print("STOP rc=%s %s" % (r.returncode, ((r.stdout or '') + (r.stderr or '')).strip()[:200]), flush=True)

t0 = time.time()
while time.time() - t0 < 90 and state().get('pid') == pid0:
    time.sleep(3)
print("old pid cleared after %.0fs (state pid=%s)" % (time.time() - t0, state().get('pid')), flush=True)

ps = 'powershell.exe -NoProfile -Command "Start-ScheduledTask -TaskName %s"' % TASK
r = subprocess.run(ps, shell=True, capture_output=True, text=True, timeout=120)
print("START rc=%s %s" % (r.returncode, ((r.stdout or '') + (r.stderr or '')).strip()[:160]), flush=True)

t0 = time.time()
while time.time() - t0 < 300:
    time.sleep(8)
    d = state()
    if d.get('pid') and d.get('pid') != pid0 and len(d.get('platforms', {})) >= 9:
        print("NEW pid=%s after %.0fs" % (d.get('pid'), time.time() - t0), flush=True)
        # 再等 40s 让适配器全部写状态
        time.sleep(40)
        break
d = state()
print("FINAL pid=%s gateway_state=%s" % (d.get('pid'), d.get('gateway_state')), flush=True)
for k, v in sorted(d.get('platforms', {}).items()):
    print("  %-24s %-12s %s" % (k, v.get('state'), (v.get('error_message') or '')[:60]), flush=True)
