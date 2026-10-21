#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""VPS Sentinel — 远程部署单位常驻守护进程
功能:
  1. 心跳: 定期写入 /var/hermes_agent/heartbeat.json
  2. 监控: 服务状态/资源 → 异常检测
  3. 命令队列: 执行 /var/hermes_agent/commands/*.cmd
  4. 紧急告警: 检测异常 → 写alert + 推送通知(Telegram/Webhook)
架构: 本地Hermes定期间断SSH轮询, 本进程VPS端常驻
"""
import json, os, time, subprocess, datetime, glob, shutil

BASE = '/var/hermes_agent'
HEARTBEAT = os.path.join(BASE, 'heartbeat.json')
CMDS = os.path.join(BASE, 'commands')
ALERTS = os.path.join(BASE, 'alerts')
DONE = os.path.join(BASE, 'done')
LOG = os.path.join(BASE, 'sentinel.log')

# 告警推送配置 (可选: Telegram bot)
TG_TOKEN = os.environ.get('TG_TOKEN', '')
TG_CHAT = os.environ.get('TG_CHAT', '')

# 监控阈值
MEM_THRESHOLD_MB = 400     # 内存使用超过400MB告警
DISK_THRESHOLD_PCT = 90    # 磁盘使用超过90%告警
SERVICES = {
    'sshd': 'systemctl is-active sshd',
    'nginx': 'systemctl is-active nginx 2>/dev/null || pgrep -f nginx > /dev/null && echo active || echo inactive',
    'trojan': 'pgrep -x trojan > /dev/null && echo active || echo inactive',
    'mysql': 'systemctl is-active mysqld 2>/dev/null || pgrep mysqld > /dev/null && echo active || echo inactive',
}

def log(msg):
    line = "[%s] %s" % (datetime.datetime.now().isoformat(), msg)
    with open(LOG, 'a') as f:
        f.write(line + "\n")
    print(line)

def ensure_dirs():
    for d in [BASE, CMDS, ALERTS, DONE]:
        if not os.path.exists(d):
            os.makedirs(d, mode=0o755)

def get_services():
    result = {}
    for name, cmd in SERVICES.items():
        try:
            out = subprocess.check_output(cmd, shell=True).decode().strip()
            result[name] = 'active' if 'active' in out else ('active' if out == 'active' else 'inactive')
        except:
            result[name] = 'unknown'
    return result

def get_resources():
    r = {}
    try:
        out = subprocess.check_output("free -m | head -2 | tail -1", shell=True).decode().split()
        r['mem_used_mb'] = int(out[2]); r['mem_total_mb'] = int(out[1])
    except: pass
    try:
        out = subprocess.check_output("df -P / | tail -1", shell=True).decode().split()
        r['disk_used_pct'] = int(out[4].rstrip('%'))
    except: pass
    try:
        out = subprocess.check_output("cat /proc/loadavg", shell=True).decode().split()
        r['load1'] = out[0]
    except: pass
    return r

def write_heartbeat():
    hb = {
        'ts': datetime.datetime.now().isoformat(),
        'host': 'vps-node',
        'services': get_services(),
        'resources': get_resources(),
    }
    tmp = HEARTBEAT + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(hb, f)
    os.rename(tmp, HEARTBEAT)
    return hb

def check_anomalies(hb):
    alerts = []
    res = hb.get('resources', {})
    if res.get('mem_used_mb', 0) > MEM_THRESHOLD_MB:
        alerts.append('HIGH_MEMORY: %sMB' % res['mem_used_mb'])
    if res.get('disk_used_pct', 0) > DISK_THRESHOLD_PCT:
        alerts.append('HIGH_DISK: %s%%' % res['disk_used_pct'])
    for svc, state in hb.get('services', {}).items():
        if state != 'active':
            alerts.append('SERVICE_DOWN: %s' % svc)
    return alerts

def write_alert(alerts):
    for a in alerts:
        alert_file = os.path.join(ALERTS, 'alert_%d_%s.json' % (int(time.time()), a.split(':')[0]))
        data = {'ts': datetime.datetime.now().isoformat(), 'alert': a, 'acked': False}
        with open(alert_file, 'w') as f:
            json.dump(data, f)
        log('ALERT: %s' % a)
        notify(a)

def notify(alert):
    """紧急通知: Telegram Bot (如配置)"""
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        text = "[VPS-SENTINEL] %s %s" % (datetime.datetime.now().isoformat(), alert)
        import urllib2
        url = "https://api.telegram.org/bot%s/sendMessage" % TG_TOKEN
        data = urllib2.urlopen(url, "chat_id=%s&text=%s" % (TG_CHAT, text), timeout=10)
    except Exception as e:
        log('notify failed: %s' % str(e))

def execute_commands():
    """执行命令队列: commands/*.cmd → done/"""
    for cmd_file in glob.glob(os.path.join(CMDS, '*.cmd')):
        try:
            with open(cmd_file) as f:
                cmd = f.read().strip()
            log('EXEC: %s' % cmd[:80])
            # 执行 (超时保护 - py2完全兼容)
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            try:
                out, err = proc.communicate()
                status = 'ok'
            except Exception:
                try: proc.kill()
                except: pass
                out, err = b'', b'error'
                status = 'error'
            # 结果写入done
            done_file = os.path.join(DONE, os.path.basename(cmd_file).replace('.cmd', '.json'))
            result = {'cmd': cmd, 'status': status,
                      'output': (out + err).decode('utf-8', errors='replace')[:4000],
                      'ts': datetime.datetime.now().isoformat()}
            with open(done_file, 'w') as f:
                json.dump(result, f)
            os.remove(cmd_file)
            log('DONE: %s (%s)' % (os.path.basename(cmd_file), status))
        except Exception as e:
            log('cmd failed: %s' % str(e))

def main():
    ensure_dirs()
    log('Sentinel started (interval=%ss)' % INTERVAL)
    while True:
        try:
            hb = write_heartbeat()
            alerts = check_anomalies(hb)
            if alerts:
                write_alert(alerts)
            execute_commands()
        except Exception as e:
            log('cycle error: %s' % str(e))
        time.sleep(INTERVAL)

INTERVAL = 60  # 60秒一轮

if __name__ == '__main__':
    main()
