import json, os, subprocess, sys, time, ctypes

STATE = r'D:\hermes\hermes-data\gateway_state.json'
EXE = r'C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.exe'
VBS = r'D:\hermes\hermes-data\gateway-service\Hermes_Gateway_76bff4d2.vbs'
TASK = 'Hermes_Gateway_76bff4d2'
k = ctypes.windll.kernel32


def alive(pid):
    if not pid or pid <= 0:
        return False
    h = k.OpenProcess(0x1000, False, int(pid))
    if not h:
        return None  # 无法判定（elevated）
    code = ctypes.c_ulong()
    ok = k.GetExitCodeProcess(h, ctypes.byref(code))
    k.CloseHandle(h)
    return bool(ok) and code.value == 259


def state():
    try:
        return json.load(open(STATE, encoding='utf-8'))
    except Exception:
        return {}


d0 = state()
pid0 = d0.get('pid')
print("BEFORE pid=%s alive=%s platforms=%d" % (pid0, alive(pid0), len(d0.get('platforms', {}))))

print("STEP1 stop (drain) ...")
r = subprocess.run([EXE, '-p', 'default', 'gateway', 'stop'], capture_output=True, text=True, timeout=180)
print("  rc=%s out=%s err=%s" % (r.returncode, (r.stdout or '').strip()[:160], (r.stderr or '').strip()[:160]))

t0 = time.time()
while time.time() - t0 < 60:
    time.sleep(3)
    a = alive(pid0)
    if a is False:
        break
print("  old pid alive=%s after %.0fs" % (alive(pid0), time.time() - t0))

print("STEP2 start via scheduled task ...")
ps = ('powershell.exe -NoProfile -Command "Start-ScheduledTask -TaskName %s; '
      '(Get-ScheduledTaskInfo -TaskName %s).LastTaskResult"' % (TASK, TASK))
r = subprocess.run(ps, shell=True, capture_output=True, text=True, timeout=120)
print("  rc=%s out=%s err=%s" % (r.returncode, (r.stdout or '').strip()[:120], (r.stderr or '').strip()[:160]))

print("STEP3 wait for new pid + platform recovery (window 420s) ...")
t0 = time.time()
last = None
while time.time() - t0 < 420:
    time.sleep(10)
    d = state()
    pid = d.get('pid')
    pl = d.get('platforms', {})
    st = {v.get('state') for v in pl.values()}
    line = "  +%03ds pid=%s n=%d states=%s" % (time.time() - t0, pid, len(pl), sorted(st))
    if line != last:
        print(line, flush=True)
        last = line
    if pid and pid != pid0 and len(pl) >= 9 and st <= {'connected', 'retrying'} and 'retrying' not in st:
        print("RECOVERED pid=%s in %.0fs" % (pid, time.time() - t0))
        break
else:
    print("WINDOW_ELAPSED (未全绿，按实际状态交付)")

d = state()
print("\nAFTER pid=%s" % d.get('pid'))
for kk, v in sorted(d.get('platforms', {}).items()):
    print("  %-24s %-12s %s" % (kk, v.get('state'), (v.get('error_message') or '')[:70]))
