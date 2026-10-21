#!/usr/bin/env python3
"""VPS用户名探测 — 尝试常见用户名, 输出脱敏
"""
import paramiko, json, sys

CRED = r'D:/hermes/data/credentials/vps_credentials.json'
with open(CRED) as f:
    c = json.load(f)['vps']

USERS = ['root', 'ubuntu', 'admin', 'user', 'deploy', 'ec2-user', 'centos']

for user in USERS:
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=c['ip'], port=c['port'], username=user,
            password=c['password'], timeout=8, look_for_keys=False,
            allow_agent=False, banner_timeout=8, auth_timeout=8)
        stdin, stdout, stderr = client.exec_command('whoami && uname -a', timeout=10)
        out = stdout.read().decode('utf-8', errors='replace').strip()
        print(f"✅ 用户名 {user} 成功! 输出: {out}")
        client.close()
        sys.exit(0)
    except paramiko.AuthenticationException:
        print(f"  ❌ {user}: 认证失败")
    except Exception as e:
        print(f"  ⚠️ {user}: {type(e).__name__}")
