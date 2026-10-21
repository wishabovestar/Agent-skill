#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
hermes_dashboard.py -- Hermes 实时看板 (无 shell 版)

设计约束（重要）: 本机 Hermes 客户端的审批通道不可用, 因此本看板**绝不调用
subprocess / powershell**。所有数据来自:
  * ctypes  (内存 / CPU / uptime / 进程数)   —— 进程内, 零审批
  * winreg  (WER 策略 / LocalDumps)          —— 零审批
  * sqlite3 (cron/executions.db)             —— 零审批
  * 本地文件 (看门狗日志 / 状态 / cron jobs.json) —— 零审批

用法:
  python hermes_dashboard.py                 # 生成 widget HTML (内嵌快照)
  python hermes_dashboard.py --serve         # 起本地 HTTP 服务 127.0.0.1:8787
  python hermes_dashboard.py --print         # 只打印 JSON 快照
"""

import os, re, json, time, ctypes, sqlite3, shutil, glob, sys, datetime
from ctypes import wintypes

ROOT = r"D:\hermes"
AN = os.path.join(ROOT, "analysis")
HD = os.path.join(ROOT, "hermes-data")
WIDGET = os.path.join(AN, "hermes_dashboard_widget.html")
PORT = 8787

LOGS = {
    "explorer": os.path.join(AN, "explorer_watchdog.log"),
    "obs": os.path.join(AN, "explorer_watchdog.obs.log"),
    "state": os.path.join(AN, "explorer_watchdog.state"),
    "lock": os.path.join(AN, "explorer_watchdog.lock"),
    "flicker": os.path.join(AN, "flicker_events.log"),
    "gw": os.path.join(AN, "gw_guard.log"),
}
CRON_DB = os.path.join(HD, "cron", "executions.db")
CRON_JOBS = os.path.join(HD, "cron", "jobs.json")
CRON_HEARTBEAT = os.path.join(HD, "cron", "ticker_heartbeat")

# ------------------------------------------------------------------ ctypes host
class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

def _ft(v):
    return (v.dwHighDateTime << 32) | v.dwLowDateTime

def _sample_cpu():
    k = ctypes.windll.kernel32
    idle, kern, user = FILETIME(), FILETIME(), FILETIME()
    if not k.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user)):
        return None
    return (_ft(idle), _ft(kern), _ft(user))

def _delta_cpu(a, b):
    if not a or not b:
        return None
    di, dk, du = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    total = dk + du
    if total <= 0:
        return None
    return max(0.0, min(100.0, 100.0 * (1.0 - di / total)))

def proc_count():
    try:
        k = ctypes.windll.psapi
        arr = (wintypes.DWORD * 4096)()
        need = wintypes.DWORD()
        if not k.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(need)):
            return None
        return need.value // ctypes.sizeof(wintypes.DWORD)
    except Exception:
        return None

def collect_host(cpu_prev=None):
    out = {}
    try:
        m = MEMORYSTATUSEX(); m.dwLength = ctypes.sizeof(m)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            out["mem_pct"] = float(m.dwMemoryLoad)
            out["mem_used_gb"] = round((m.ullTotalPhys - m.ullAvailPhys) / 2**30, 2)
            out["mem_total_gb"] = round(m.ullTotalPhys / 2**30, 2)
            out["commit_used_gb"] = round((m.ullTotalPageFile - m.ullAvailPageFile) / 2**30, 2)
            out["commit_total_gb"] = round(m.ullTotalPageFile / 2**30, 2)
    except Exception as e:
        out["mem_err"] = str(e)
    try:
        ms = ctypes.windll.kernel32.GetTickCount64()
        out["uptime_s"] = ms // 1000
    except Exception:
        out["uptime_s"] = None
    try:
        d = shutil.disk_usage("D:\\")
        out["disk_free_gb"] = round(d.free / 2**30, 1)
        out["disk_total_gb"] = round(d.total / 2**30, 1)
    except Exception:
        pass
    out["proc_count"] = proc_count()
    cur = _sample_cpu()
    if cpu_prev:
        out["cpu_pct"] = round(_delta_cpu(cpu_prev, cur) or 0.0, 1)
    out["_cpu_sample"] = cur
    return out

# ------------------------------------------------------------------ files
def tail(path, n=40, maxbytes=400000):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > maxbytes:
                f.seek(size - maxbytes)
                f.readline()
            data = f.read().decode("utf-8", "replace")
        return data.splitlines()[-n:]
    except Exception:
        return []

def mtime_age(path):
    try:
        return round(time.time() - os.path.getmtime(path), 1)
    except Exception:
        return None

def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}

def read_reg(root, path, name):
    try:
        import winreg
        with winreg.OpenKey(root, path) as k:
            v, _ = winreg.QueryValueEx(k, name)
            return v
    except Exception:
        return None

# ------------------------------------------------------------------ collectors
def collect_cron():
    out = {"jobs": [], "executions": [], "heartbeat_age_s": mtime_age(CRON_HEARTBEAT)}
    j = read_json(CRON_JOBS, {})
    for job in (j.get("jobs") or []):
        out["jobs"].append({
            "id": job.get("id"), "name": job.get("name"),
            "sched": job.get("schedule_display") or (job.get("schedule") or {}).get("display", ""),
            "enabled": bool(job.get("enabled")), "state": job.get("state"),
            "next": job.get("next_run_at"), "last": job.get("last_run_at"),
            "status": job.get("last_status"), "error": (job.get("last_error") or "")[:160],
            "deliver": job.get("deliver"), "done": (job.get("repeat") or {}).get("completed"),
            "streak": job.get("failure_streak") or 0,
        })
    try:
        c = sqlite3.connect(f"file:{CRON_DB}?mode=ro", uri=True)
        cur = c.execute("""SELECT job_id,status,claimed_at,started_at,finished_at,error,
                                  delivery_outcome FROM executions
                           ORDER BY COALESCE(finished_at,started_at,claimed_at) DESC LIMIT 12""")
        for r in cur:
            out["executions"].append({"job_id": r[0], "status": r[1], "claimed": r[2],
                                      "started": r[3], "finished": r[4],
                                      "error": (r[5] or "")[:160],
                                      "delivery": r[6]})
        c.close()
    except Exception as e:
        out["exec_err"] = str(e)
    return out

def _today():
    return datetime.datetime.now().strftime("%Y-%m-%d")

def collect_watchdog():
    out = {}
    st = read_json(LOGS["state"], {})
    out["restarts"] = st.get("restarts")
    out["observations"] = st.get("observations")
    out["last_pid"] = st.get("last_pid")
    try:
        out["resident_pid"] = int(open(LOGS["lock"]).read().strip())
    except Exception:
        out["resident_pid"] = None
    el = tail(LOGS["explorer"], 400)
    out["explorer_last"] = [l for l in el if "heartbeat" not in l][-8:]
    out["heartbeat_last"] = el[-1] if el else ""
    # who owns the shell?  the watchdog logs the parent of every new explorer
    parent = ""
    for l in reversed(el):
        m = re.search(r"parent(?:-of-new)?=([\w.]+)#?(\d*)", l)
        if m:
            parent = m.group(1)
            break
    if not parent:
        for l in reversed(tail(LOGS["obs"], 400)):
            m = re.search(r"parent=([\w.]+)", l)
            if m:
                parent = m.group(1)
                break
    out["shell_parent"] = parent
    out["shell_owner"] = ("Winlogon(系统自愈)" if "userinit" in parent else
                          ("看门狗(非系统)" if "powershell" in parent else ("未知" if not parent else parent)))
    # gw_guard actions
    gw = tail(LOGS["gw"], 300)
    out["gw_last"] = gw[-10:]
    # profile status: last mention per profile in gw_guard.log
    profs = {}
    for l in gw:
        m = re.search(r"^\s*(?:\[[\d\-: ]+\]\s*)?([A-Za-z0-9_]+)\s+(UP|DEAD|STARTING|STOPPED|RUNNING|DOWN)\b", l)
        if m:
            profs[m.group(1)] = {"status": m.group(2), "line": l.strip()[-150:]}
        m2 = re.search(r"RESTARTED\s+([A-Za-z0-9_]+)", l)
        if m2:
            profs.setdefault(m2.group(1), {})["restarted_line"] = l.strip()[-150:]
    out["gateways"] = profs
    return out

def collect_flicker():
    out = {"dwm_exits_today": 0, "shell_crashes_today": 0, "events": [], "last": ""}
    fl = tail(LOGS["flicker"], 900, maxbytes=900000)
    today = _today()
    for l in fl:
        if "DWM-EXIT" in l and today in l:
            out["dwm_exits_today"] += 1
        if ("SHELL-CRASH" in l or "POPUP" in l) and today in l:
            out["shell_crashes_today"] += 1
    ev = [l for l in fl if re.match(r"^(DWM-EXIT|SHELL-CRASH|POPUP|MONITOR|TDR)\b", l.strip())]
    out["events"] = ev[-14:]
    out["last"] = ev[-1] if ev else ""
    return out

def collect_wer():
    hklm = 0x80000002
    out = {}
    out["policies_disabled"] = read_reg(hklm, r"SOFTWARE\Policies\Microsoft\Windows\Windows Error Reporting", "Disabled")
    out["wersvc_start"] = read_reg(hklm, r"SYSTEM\CurrentControlSet\Services\WerSvc", "Start")
    out["telemetry_gate"] = read_reg(hklm, r"SOFTWARE\Microsoft\Windows\Windows Error Reporting", "ChangeDumpTypeByTelemetryLevel")
    ld = r"SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps"
    try:
        import winreg
        with winreg.OpenKey(hklm, ld) as k:
            out["localdump_keys"] = [winreg.EnumKey(k, i) for i in range(winreg.QueryInfoKey(k)[0])]
    except Exception:
        out["localdump_keys"] = []
    dumpdir = os.path.join(AN, "dumps")
    try:
        out["dumps"] = len([f for f in os.listdir(dumpdir) if os.path.isfile(os.path.join(dumpdir, f))])
    except Exception:
        out["dumps"] = 0
    return out

def collect_profiles():
    base = os.path.join(HD, "profiles")
    out = []
    try:
        for d in sorted(os.listdir(base)):
            p = os.path.join(base, d)
            if not os.path.isdir(p):
                continue
            sd = os.path.join(p, "state.db")
            out.append({"name": d, "state_age_s": mtime_age(sd) if os.path.exists(sd) else None,
                        "has_state": os.path.exists(sd)})
    except Exception:
        pass
    return out

def collect(cpu_prev=None):
    snap = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "generated_ts": time.time(),
        "host": collect_host(cpu_prev),
        "cron": collect_cron(),
        "wd": collect_watchdog(),
        "flicker": collect_flicker(),
        "wer": collect_wer(),
        "profiles": collect_profiles(),
        "source": "no-shell (ctypes/winreg/sqlite/file)",
    }
    return snap

# ------------------------------------------------------------------ render
HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>Hermes 实时看板</title>
<style>
  * { box-sizing: border-box; }
  body { color: var(--foreground); font-family: var(--app-font, ui-monospace, "Cascadia Mono", Consolas, monospace);
         font-size: 12.5px; line-height: 1.45; margin: 0; }
  .hdr { display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; margin-bottom:10px; }
  .hdr h1 { font-size:15px; margin:0; font-weight:600; letter-spacing:.02em; }
  .badge { border:1px solid var(--border); border-radius:999px; padding:1px 9px; font-size:11px; color:var(--muted-foreground); }
  .live { color:var(--accent); border-color:var(--accent); }
  .btn { border:1px solid var(--border); background:transparent; color:var(--foreground);
         border-radius:6px; padding:2px 10px; font:inherit; font-size:11px; cursor:pointer; }
  .btn:hover { border-color:var(--accent); color:var(--accent); }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(310px,1fr)); gap:10px; align-items:start; }
  .card { border:1px solid var(--border); border-radius:10px; padding:9px 11px; background:var(--card); }
  .card h2 { font-size:11.5px; margin:0 0 7px; font-weight:600; color:var(--muted-foreground);
             text-transform:uppercase; letter-spacing:.09em; }
  table { width:100%; border-collapse:collapse; }
  td, th { text-align:left; padding:2px 6px 2px 0; vertical-align:top; }
  th { color:var(--muted-foreground); font-weight:500; font-size:11px; }
  .k { color:var(--muted-foreground); }
  .v { font-variant-numeric:tabular-nums; }
  .bar { height:5px; border-radius:3px; background:var(--border); overflow:hidden; margin-top:3px; }
  .bar > i { display:block; height:100%; background:var(--accent); }
  .ok { color:var(--accent); } .bad { color:#e5534b; } .warn { color:#d29922; }
  .mono { font-variant-numeric:tabular-nums; }
  .log { white-space:pre-wrap; word-break:break-all; color:var(--muted-foreground); font-size:11px; }
  .kpi { display:flex; gap:18px; flex-wrap:wrap; }
  .kpi div { min-width:88px; }
  .kpi b { display:block; font-size:17px; font-weight:600; font-variant-numeric:tabular-nums; }
  .kpi span { font-size:10.5px; color:var(--muted-foreground); text-transform:uppercase; letter-spacing:.07em; }
  .tag { border:1px solid var(--border); border-radius:4px; padding:0 5px; font-size:10.5px; }
</style></head><body>
<div class="hdr">
  <h1>Hermes 实时看板</h1>
  <span id="mode" class="badge">快照</span>
  <span class="badge">快照时间 <span id="gen">-</span></span>
  <span class="badge">本地时间 <span id="clock">-</span></span>
  <button class="btn" data-hermes-send="刷新 hermes 实时看板">刷新</button>
</div>
<div id="root"></div>
<script>
const SNAPSHOT = __SNAPSHOT__;
const LIVE_URL = "http://127.0.0.1:8787/metrics";
const esc = s => String(s==null?"-":s).replace(/[&<>]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const pct = (a,b) => (!b||b<=0) ? 0 : Math.max(0,Math.min(100,100*a/b));
function hms(sec){ if(sec==null) return "-"; sec=Math.floor(sec);
  const d=Math.floor(sec/86400), h=Math.floor(sec%86400/3600), m=Math.floor(sec%3600/60);
  return (d?d+"d ":"")+h+"h "+m+"m"; }
function ago(s){ if(s==null) return "-"; s=Math.floor(s);
  if(s<60) return s+"s"; if(s<3600) return Math.floor(s/60)+"m"+(s%60)+"s"; 
  if(s<86400) return Math.floor(s/3600)+"h"+Math.floor(s%3600/60)+"m"; return Math.floor(s/86400)+"d"+Math.floor(s%86400/3600)+"h"; }

function render(S){
  if(!S || !S.host) { document.getElementById('root').innerHTML = '<div class="card">无数据</div>'; return; }
  document.getElementById('gen').textContent = S.generated_at || '-';
  const h=S.host, w=S.wd||{}, f=S.flicker||{}, c=S.cron||{}, wer=S.wer||{};
  const gate = Object.entries(w.gateways||{});
  const up = gate.filter(([n,v])=>["UP","RUNNING"].includes(v.status)).length;
  const down = gate.filter(([n,v])=>["DEAD","STOPPED","DOWN"].includes(v.status)).length;
  const ownerBad = !String(w.shell_owner||'').includes('Winlogon');
  const jobs = (c.jobs||[]), execs=(c.executions||[]);
  let H = '';

  H += '<div class="kpi card" style="margin-bottom:10px">'
    + '<div><b>'+hms(h.uptime_s)+'</b><span>uptime</span></div>'
    + '<div><b>'+esc(h.cpu_pct)+'%</b><span>cpu</span><div class="bar"><i style="width:'+esc(h.cpu_pct)+'%"></i></div></div>'
    + '<div><b>'+esc(h.mem_pct)+'%</b><span>内存 '+esc(h.mem_used_gb)+'/'+esc(h.mem_total_gb)+'G</span><div class="bar"><i style="width:'+esc(h.mem_pct)+'%"></i></div></div>'
    + '<div><b>'+esc(h.commit_used_gb)+'G</b><span>提交 '+esc(h.commit_total_gb)+'G</span></div>'
    + '<div><b>'+esc(h.disk_free_gb)+'G</b><span>D: 可用</span></div>'
    + '<div><b>'+esc(h.proc_count)+'</b><span>进程</span></div>'
    + '</div>';

  H += '<div class="grid">';

  // gateways
  H += '<div class="card"><h2>网关机群 · UP '+up+' / DOWN '+down+'</h2><table>';
  if(!gate.length) H += '<tr><td class="k">gw_guard.log 无记录</td></tr>';
  for(const [n,v] of gate){
    const cls = ["UP","RUNNING"].includes(v.status)?'ok':(["DEAD","DOWN","STOPPED"].includes(v.status)?'bad':'warn');
    H += '<tr><td class="k">'+esc(n)+'</td><td class="'+cls+'">'+esc(v.status)+'</td>'
       + '<td class="log">'+esc((v.line||'').slice(0,90))+'</td></tr>';
  }
  H += '</table></div>';

  // watchdogs
  H += '<div class="card"><h2>看门狗</h2><table>'
    + '<tr><td class="k">resident pid</td><td class="v">'+esc(w.resident_pid)+'</td></tr>'
    + '<tr><td class="k">重启次数</td><td class="v">'+esc(w.restarts)+'</td></tr>'
    + '<tr><td class="k">观测计数</td><td class="v">'+esc(w.observations)+'</td></tr>'
    + '<tr><td class="k">外壳所有者</td><td class="'+(ownerBad?'bad':'ok')+'">'+esc(w.shell_owner)+'</td></tr>'
    + '<tr><td class="k">最近心跳</td><td class="log">'+esc((w.heartbeat_last||'').slice(0,88))+'</td></tr>'
    + '</table></div>';

  // black screen / DWM
  H += '<div class="card"><h2>黑屏 / DWM 健康</h2><table>'
    + '<tr><td class="k">DWM 退出(今日)</td><td class="v '+(f.dwm_exits_today>0?'bad':'ok')+'">'+esc(f.dwm_exits_today)+'</td></tr>'
    + '<tr><td class="k">外壳崩溃(今日)</td><td class="v">'+esc(f.shell_crashes_today)+'</td></tr>'
    + '<tr><td class="k">WER 策略Disabled</td><td class="v">'+esc(wer.policies_disabled)+'</td></tr>'
    + '<tr><td class="k">WerSvc Start</td><td class="v">'+esc(wer.wersvc_start)+'</td></tr>'
    + '<tr><td class="k">LocalDumps 键</td><td class="v">'+esc((wer.localdump_keys||[]).length)+'</td></tr>'
    + '<tr><td class="k">已存转储</td><td class="v">'+esc(wer.dumps)+'</td></tr>'
    + '</table><div class="log" style="margin-top:6px">'+esc(f.last||'')+'</div></div>';

  // cron
  H += '<div class="card"><h2>Cron 任务 · ticker '+ago(c.heartbeat_age_s)+'前</h2><table>'
    + '<tr><th>任务</th><th>计划</th><th>状态</th><th>下次</th></tr>';
  for(const j of jobs){
    const st = j.enabled ? esc(j.status) : '暂停';
    const cls = (j.status==='ok')?'ok':(j.enabled?'warn':'k');
    H += '<tr><td>'+esc(j.name)+'</td><td class="k">'+esc(j.sched)+'</td>'
       + '<td class="'+cls+'">'+st+(j.streak?' x'+j.streak:'')+'</td>'
       + '<td class="k">'+esc((j.next||'').replace('T',' ').slice(5,16))+'</td></tr>';
  }
  H += '</table>';
  if(execs.length){
    H += '<div style="margin-top:7px" class="k">最近执行</div><table>';
    for(const e of execs.slice(0,5)){
      const cls = e.status==='completed'?'ok':(e.status==='failed'?'bad':'warn');
      H += '<tr><td class="'+cls+'">'+esc(e.status)+'</td><td class="k">'
         + esc((e.finished||e.started||e.claimed||'').replace('T',' ').slice(5,19))+'</td>'
         + '<td class="log">'+esc((e.error||e.delivery||'').slice(0,60))+'</td></tr>';
    }
    H += '</table>';
  }
  H += '</div>';

  // profiles
  H += '<div class="card"><h2>Hermes Profile</h2><table><tr><th>profile</th><th>state.db 新鲜度</th></tr>';
  for(const p of (S.profiles||[])){
    H += '<tr><td>'+esc(p.name)+'</td><td class="'+(p.state_age_s!=null&&p.state_age_s<900?'ok':'warn')+'">'
       + (p.has_state? ago(p.state_age_s)+'前' : '无') + '</td></tr>';
  }
  H += '</table><div class="k" style="margin-top:6px">数据源: '+esc(S.source||'')+'</div></div>';

  // event stream
  H += '<div class="card" style="grid-column:1/-1"><h2>事件流 (看门狗)</h2>'
    + '<div class="log">' + (w.explorer_last||[]).map(esc).join('<br>') + '</div></div>';

  H += '<div class="card" style="grid-column:1/-1"><h2>Flicker / Shell 事件</h2>'
    + '<div class="log">' + (f.events||[]).map(esc).join('<br>') + '</div></div>';

  H += '<div class="card" style="grid-column:1/-1"><h2>gw_guard 动作</h2>'
    + '<div class="log">' + (w.gw_last||[]).map(esc).join('<br>') + '</div></div>';

  H += '</div>';
  document.getElementById('root').innerHTML = H;
}

function clock(){ const d=new Date(); document.getElementById('clock').textContent =
  d.toLocaleTimeString('zh-CN',{hour12:false}); 
  if(document.getElementById('mode').textContent==='快照'){
    const t=document.getElementById('gen').textContent;
  }
}
setInterval(clock,1000); clock();

async function poll(){
  try{
    const ctl = new AbortController(); const to=setTimeout(()=>ctl.abort(),1500);
    const r = await fetch(LIVE_URL,{signal:ctl.signal,cache:'no-store'}); clearTimeout(to);
    if(!r.ok) throw 0;
    const S = await r.json();
    render(S);
    const m=document.getElementById('mode'); m.textContent='实时'; m.className='badge live';
  }catch(e){
    const m=document.getElementById('mode'); m.textContent='快照'; m.className='badge';
  }
}
render(SNAPSHOT);
poll();
setInterval(poll, 3000);
</script></body></html>
"""

def render_html(snapshot):
    return HTML.replace("__SNAPSHOT__", json.dumps(snapshot, ensure_ascii=False))

# ------------------------------------------------------------------ serve
def serve():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    prev = _sample_cpu()
    state = {"snap": None, "at": 0}

    def fresh():
        now = time.time()
        if state["snap"] is None or now - state["at"] > 2.5:
            state["snap"] = collect(prev)
            state["at"] = now
        return state["snap"]

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass
        def _send(self, code, body, ctype):
            b = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        def do_GET(self):
            if self.path.startswith("/metrics"):
                self._send(200, json.dumps(fresh(), ensure_ascii=False), "application/json; charset=utf-8")
            elif self.path.startswith("/events"):
                s = fresh()
                self._send(200, json.dumps(s["flicker"], ensure_ascii=False), "application/json; charset=utf-8")
            else:
                self._send(200, render_html(fresh()), "text/html; charset=utf-8")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"dashboard on http://127.0.0.1:{PORT}/  (ctrl-c to stop)")
    srv.serve_forever()

if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve()
    elif "--print" in sys.argv:
        s = collect(_sample_cpu())
        s["host"].pop("_cpu_sample", None)
        print(json.dumps(s, ensure_ascii=False, indent=1))
    else:
        s = collect(_sample_cpu())
        s["host"].pop("_cpu_sample", None)
        open(WIDGET, "w", encoding="utf-8").write(render_html(s))
        print("widget written:", WIDGET, os.path.getsize(WIDGET), "bytes")
