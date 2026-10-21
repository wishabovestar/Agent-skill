#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""VPS数据采集+分析脚本 — Python2.7兼容版 (CentOS7)
数据源: v2ray access.log (历史) + trojan journald (实时)
输出: JSON报表 (供推广站使用)
脱敏: 客户端IP→hash前6位, 不存PII
"""
import re, json, os, datetime
from collections import Counter

DB = '/home/wwwroot/3DCEList/stats.json'

# v2ray access.log格式: 2020/07/31 18:44:22 tcp:IP:34528 accepted tcp:www.google.com:443 [direct]
V2RAY_RE = re.compile(r'^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}) tcp:(\S+):(\d+) accepted tcp:(\S+):(\d+)')

def hash_ip(ip):
    """脱敏: IP→短hash (只保留统计维度)"""
    try:
        return 'x' + format(abs(hash(ip)) % 0xFFFFFF, '06x')
    except:
        return 'x000000'

def analyze_v2ray(path):
    """分析v2ray历史日志"""
    stats = {
        'total_connections': 0,
        'unique_ips': set(),
        'domains': Counter(),
        'hourly': Counter(),
        'daily': Counter(),
        'ports': Counter(),
    }
    if not os.path.exists(path):
        return stats
    with open(path, 'rb') as f:
        for raw in f:
            try:
                line = raw.decode('utf-8', errors='ignore')
            except:
                line = raw
            m = V2RAY_RE.match(line)
            if not m:
                continue
            ts, ip, sport, domain, dport = m.groups()
            stats['total_connections'] += 1
            stats['unique_ips'].add(hash_ip(ip))
            stats['domains'][domain] += 1
            stats['ports'][dport] += 1
            try:
                dt = datetime.datetime.strptime(ts, '%Y/%m/%d %H:%M:%S')
                stats['hourly'][dt.hour] += 1
                stats['daily'][dt.strftime('%Y-%m-%d')] += 1
            except:
                pass
    return stats

def analyze_trojan():
    """分析trojan journald日志 (最近连接)"""
    try:
        out = os.popen("journalctl -u trojan --since '24 hours ago' --no-pager 2>/dev/null | grep 'disconnected' | tail -200").read()
    except:
        return {'recent_24h': 0, 'total_bytes': 0}
    
    total_bytes = 0
    count = 0
    for line in out.splitlines():
        m = re.search(r'(\d+) bytes received, (\d+) bytes sent', line)
        if m:
            total_bytes += int(m.group(1)) + int(m.group(2))
            count += 1
    return {'recent_24h': count, 'total_bytes_24h': total_bytes}

def build_report():
    v = analyze_v2ray('/var/log/v2ray/access.log')
    t = analyze_trojan()
    
    report = {
        'generated': datetime.datetime.now().isoformat(),
        'v2ray_historical': {
            'total_connections': v['total_connections'],
            'unique_clients': len(v['unique_ips']),
            'top_domains': [{'domain': d, 'count': c} for d, c in v['domains'].most_common(10)],
            'top_hours': [{'hour': h, 'count': c} for h, c in sorted(v['hourly'].items())],
            'daily': [{'date': d, 'count': c} for d, c in list(v['daily'].items())[-30:]],
            'top_ports': [{'port': p, 'count': c} for p, c in v['ports'].most_common(5)],
        },
        'trojan_realtime': t,
        'compliance': {
            'data_scope': 'connection_metrics_only',
            'pii_stored': 'none',
            'ip_hashed': True,
            'storage': 'vps_local_only',
        }
    }
    return report

if __name__ == '__main__':
    report = build_report()
    with open(DB, 'w') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("OK stats generated: %s" % DB)
    print("total_connections: %s" % report['v2ray_historical']['total_connections'])
    print("unique_clients: %s" % report['v2ray_historical']['unique_clients'])
    print("24h_active: %s" % report['trojan_realtime']['recent_24h'])
    top = report['v2ray_historical']['top_domains'][:3]
    for d in top:
        print("  top: %s (%s)" % (d['domain'], d['count']))
