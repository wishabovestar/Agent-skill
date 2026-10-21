# -*- coding: utf-8 -*-
"""gpu_idle_reclaim_SAFE.py — 显存闲置回收 (安全版, 2026-10-10 重写)

为什么重写 (事故根因):
  旧版 gpu_idle_reclaim.py 在显存 >800MiB 时, 用
      nvidia-smi --query-compute-apps=pid  →  逐个 taskkill /F
  当"回收残留"。但在 WDDM 下这条命令【不区分图形/计算】, 会返回
  dwm.exe / explorer.exe / ShellHost / 游戏本体 等一切持有 GPU 上下文的进程;
  旧版兜底分支还会把 WS>100MB 的 python/pythonw (=Hermes 网关/调度器) 加进名单,
  连自己的调度器都杀 → 屏幕黑闪、游戏被强退、网关掉线, 且无 TDR/无转储/无 Event1000。
  (2026-10-10 实测: 作业启动到 dwm/explorer 死亡仅 0.9-2.4s, 6 次全部吻合。)

本安全版原则:
  1. 绝不按 nvidia-smi 的 PID 杀任何进程 (那条数据源在 WDDM 下不可信)。
  2. 只做"白名单"动作:
       a) ollama stop <驻留模型>              —— 有官方语义, 安全
       b) 停占用已知推理端口的 llama-server    —— 端口白名单, 相当于 gpu_ondemand.reap
  3. 任何未识别的显存占用 → 只告警, 不杀。
  4. 硬性拒绝: 进程名匹配 dwm/explorer/csrss/winlogon/sihost/ShellHost/
     StartMenuExperienceHost/SearchHost/TextInputHost/svchost/System/Registry
     一律跳过 (双保险, 即使将来误传 PID 也不动)。
"""
import subprocess, sys, time

# 已知推理服务端口 (只有这些端口上的进程才允许被停)
KNOWN_PORTS = (8123, 8188)          # gpu_ondemand.json 里的 uitars / bonsai
NEVER_KILL_NAMES = (
    'dwm', 'explorer', 'csrss', 'winlogon', 'sihost', 'shellhost',
    'startmenuexperiencehost', 'searchhost', 'textinputhost', 'shellexperiencehost',
    'svchost', 'system', 'registry', 'services', 'lsass', 'wininit',
    'awesun', 'sunlogin', 'oray',
)

def sh(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return r.stdout.strip()
    except Exception:
        return ''

def mem_used_mb():
    out = sh(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'])
    try:
        return float(out.split('\n')[0].strip())
    except Exception:
        return -1

def ollama_models():
    out = sh(['ollama', 'ps'], timeout=20)
    models = []
    for line in out.splitlines()[1:]:
        p = line.split()
        if p:
            models.append(p[0])
    return models

def _pid_names():
    """pid -> 小写进程名 (一次 CIM 枚举, 避免逐进程往返)"""
    out = sh(['powershell', '-NoProfile', '-Command',
              "Get-CimInstance Win32_Process | Select-Object ProcessId,Name | "
              "ConvertTo-Json -Compress"], timeout=25)
    import json
    try:
        data = json.loads(out) if out else []
    except Exception:
        return {}
    if isinstance(data, dict):
        data = [data]
    return {int(d.get('ProcessId')): str(d.get('Name', '')).lower() for d in data}

def pids_on_port(port):
    out = sh(['netstat', '-ano'], timeout=25)
    pids = set()
    for ln in out.splitlines():
        if 'LISTENING' in ln and f':{port} ' in ln + ' ':
            p = ln.split()[-1]
            if p.isdigit():
                pids.add(int(p))
    return pids

actions, warns = [], []
used = mem_used_mb()
if used < 0:
    sys.exit(0)                      # nvidia-smi 不可用 → 静默
if used <= 800:
    sys.exit(0)                      # 干净

# 1) ollama 驻留模型 → 官方 stop (安全)
for m in ollama_models():
    sh(['ollama', 'stop', m], timeout=30)
    actions.append(f'ollama stop {m}')
if actions:
    time.sleep(2)
    used = mem_used_mb()

# 2) 仍高 → 只停【已知推理端口】的占用者, 并按名字硬性过滤
if used > 800:
    names = _pid_names()
    for port in KNOWN_PORTS:
        for pid in pids_on_port(port):
            nm = names.get(pid, '')
            if nm in NEVER_KILL_NAMES:
                warns.append(f'⚠️ 跳过端口{port}上的受保护进程 {nm}({pid})')
                continue
            if 'llama' not in nm and 'python' not in nm:
                warns.append(f'⚠️ 跳过端口{port}未知进程 {nm}({pid}) — 未动')
                continue
            sh(['taskkill', '/PID', str(pid), '/F'], timeout=15)
            actions.append(f'停端口{port}占用者 {nm}({pid})')

# 3) 仍高但无可安全动作 → 只告警, 绝不盲杀
if used > 800 and not actions:
    warns.append(f'⚠️ 显存 {used:.0f}MiB 偏高但无白名单可回收项 — 仅告警, 未杀任何进程')

if actions or warns:
    print(' | '.join(actions + warns))
    print(f'GPU 显存: {used:.0f}MiB')
