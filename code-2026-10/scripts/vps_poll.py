#!/usr/bin/env python3
"""本地Hermes轮询端 — 定期间断式SSH沟通 (时间感知版)
功能:
  1. 拉取VPS心跳 (检查服务状态)
  2. 拉取告警 (紧急事件)
  3. 上传命令队列 (VPS执行)
  4. 拉取命令执行结果
智能调度:
  - 睡眠时段 (23:00-07:00): 巡检正常→完全静默; 紧急告警→仍推送
  - 非睡眠时段: 正常反馈 (cron间隔已延长到30分钟)
"""
import paramiko, json, os, sys, datetime, glob

CRED = r'D:/hermes/data/credentials/vps_credentials.json'
KEY = r'D:/hermes/data/credentials/vps_keys/vps_ed25519'
LOCAL_DONE = r'D:/hermes/data/vps_comm/done'
LOCAL_OUT = r'D:/hermes/data/vps_comm/output'

# 睡眠时段配置
SLEEP_START_HOUR = 23   # 23:00 开始睡眠
SLEEP_END_HOUR = 7      # 07:00 结束睡眠

def is_sleep_time(now=None):
    """判断是否在睡眠时段"""
    now = now or datetime.datetime.now()
    h = now.hour
    if SLEEP_START_HOUR <= h or h < SLEEP_END_HOUR:
        return True
    return False

def get_client():
    with open(CRED) as f:
        c = json.load(f)['vps']
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=c['ip'], port=c['port'], username=c['user'],
                   key_filename=KEY, timeout=15, look_for_keys=False, allow_agent=False)
    return client

def run(client, cmd, timeout=30):
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    return out, err

def fetch_heartbeat(client):
    out, _ = run(client, 'cat /var/hermes_agent/heartbeat.json 2>/dev/null || echo "{}"')
    try:
        return json.loads(out)
    except:
        return {}

def fetch_alerts(client):
    out, _ = run(client, 'ls /var/hermes_agent/alerts/ 2>/dev/null')
    return [a for a in out.strip().split('\n') if a] if out.strip() else []

def fetch_done(client):
    """拉取VPS命令执行结果"""
    out, _ = run(client, 'ls /var/hermes_agent/done/*.json 2>/dev/null')
    files = [f for f in out.strip().split('\n') if f] if out.strip() else []
    results = []
    os.makedirs(LOCAL_DONE, exist_ok=True)
    for f in files:
        out2, _ = run(client, 'cat %s && rm %s' % (f, f))
        try:
            data = json.loads(out2)
            results.append(data)
            # 本地备份
            name = os.path.basename(f)
            with open(os.path.join(LOCAL_DONE, name), 'w') as lf:
                json.dump(data, lf, ensure_ascii=False, indent=2)
        except:
            pass
    return results

def push_command(client, cmd, name=None):
    """上传命令到VPS队列"""
    if not name:
        name = 'cmd_%d' % int(datetime.datetime.now().timestamp())
    cmd_file = '/var/hermes_agent/commands/%s.cmd' % name
    # 用SFTP写命令
    sftp = client.open_sftp()
    with sftp.open(cmd_file, 'w') as f:
        f.write(cmd)
    sftp.close()
    return name

def check_alert_actions(alerts):
    """告警处理: 返回需要本地Hermes介入的事件"""
    actions = []
    for a in alerts:
        # 读取告警详情
        actions.append(a)
    return actions

def poll(interval_min=5, quiet_mode='auto'):
    """执行一次轮询 (间断式, 时间感知)
    quiet_mode: auto=睡眠静默/正常反馈, force_silent=强制静默, force_report=强制报告
    """
    now = datetime.datetime.now()
    sleep_time = is_sleep_time(now)
    
    # 决策: 是否输出反馈
    if quiet_mode == 'force_silent':
        silent = True
    elif quiet_mode == 'force_report':
        silent = False
    else:
        silent = sleep_time  # auto: 睡眠时段静默
    
    print("[%s] VPS轮询开始... (睡眠时段=%s, 静默=%s)" % (
        now.isoformat(), sleep_time, silent))
    client = get_client()
    try:
        # 1. 心跳
        hb = fetch_heartbeat(client)
        services = hb.get('services', {})
        res = hb.get('resources', {})
        down = [s for s, st in services.items() if st != 'active']
        
        # 2. 告警 (紧急事件)
        alerts = fetch_alerts(client)
        
        # 3. 命令结果
        done = fetch_done(client)
        
        # 紧急度判断
        has_critical = bool(down) or bool(alerts)
        
        # 输出策略
        if silent and not has_critical:
            # 睡眠 + 正常 → 完全静默 (不输出反馈)
            print("  [静默] 巡检正常, 睡眠时段不推送")
            return {'silent': True, 'services': services, 'alerts': alerts, 'done_count': len(done)}
        
        if not silent:
            print("  心跳: 服务=%d个 异常=%s 内存=%sMB/%sMB" % (
                len(services), down or '无', res.get('mem_used_mb', '?'), res.get('mem_total_mb', '?')))
            if alerts:
                print("  ⚠️ 告警: %d条 → %s" % (len(alerts), alerts))
            else:
                print("  告警: 无")
            if done:
                print("  命令结果: %d条" % len(done))
                for d in done:
                    print("    [%s] %s" % (d.get('status'), d.get('cmd', '')[:60]))
        
        # 4. 紧急处理 (无论是否静默都执行)
        if has_critical:
            print("  🚨 [紧急] 服务异常=%s 告警=%s" % (down or '无', alerts or '无'))
            for a in alerts:
                print("  🔴 需要本地介入: %s" % a)
        
        return {'silent': silent, 'services': services, 'alerts': alerts, 'done_count': len(done)}
    finally:
        client.close()
        print("  [断开] 轮询完成\n")

if __name__ == '__main__':
    # 支持: poll (执行一次) 或 poll-loop (持续, 用于测试)
    mode = sys.argv[1] if len(sys.argv) > 1 else 'poll'
    if mode == 'poll':
        # 可选第2参数: auto/silent/report
        quiet = sys.argv[2] if len(sys.argv) > 2 else 'auto'
        qmap = {'auto': 'auto', 'silent': 'force_silent', 'report': 'force_report'}
        poll(quiet_mode=qmap.get(quiet, 'auto'))
    elif mode == 'push':
        cmd = sys.argv[2]
        name = push_command(get_client(), cmd)
        print("命令已推送: %s" % name)
