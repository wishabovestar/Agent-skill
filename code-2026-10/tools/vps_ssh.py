#!/usr/bin/env python3
"""VPS SSH管理工具 — paramiko, 凭据从本地credentials读
用法: python vps_ssh.py <命令> [args]
  命令: test | exec "<cmd>" | info | upload <local> <remote>
输出自动脱敏: IP→VPS-IP, 密码不显示
"""
import paramiko, json, sys, os, socket

CRED = r'D:/hermes/data/credentials/vps_credentials.json'
KEY = r'D:/hermes/data/credentials/vps_keys/vps_ed25519'

def load_cred():
    with open(CRED) as f:
        return json.load(f)['vps']

def get_client():
    c = load_cred()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    # 仅密钥认证 (SSH已硬化: PasswordAuthentication no)
    client.connect(
        hostname=c['ip'], port=c['port'], username=c['user'],
        key_filename=KEY, timeout=15, look_for_keys=False,
        allow_agent=False, disabled_algorithms={'pubkeys': ['rsa-sha2-512', 'rsa-sha2-256']} if False else None)
    return client

def run(cmd, timeout=30):
    client = get_client()
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    client.close()
    return out, err

def sanitize(text):
    """脱敏: 替换IP和敏感模式"""
    c = load_cred()
    text = text.replace(c['ip'], 'VPS-IP-N')
    return text

if __name__ == '__main__':
    action = sys.argv[1] if len(sys.argv) > 1 else 'test'
    
    if action == 'test':
        out, err = run('echo SSH_OK && uname -a && uptime')
        print(sanitize(out))
        if err: print('ERR:', sanitize(err)[:200])
        print('✅ SSH连接成功 (凭据来自本地credentials)')
    
    elif action == 'info':
        out, err = run('''echo "=== OS ==="; cat /etc/os-release 2>/dev/null | head -3; 
echo "=== CPU ==="; nproc; lscpu 2>/dev/null | grep "Model name" | head -1;
echo "=== MEM ==="; free -h | head -2;
echo "=== DISK ==="; df -h / | tail -1;
echo "=== NET ==="; ip addr show 2>/dev/null | grep "inet " | grep -v 127.0.0.1 | head -3;
echo "=== APPS ==="; which nginx python3 node docker 2>/dev/null''')
        print(sanitize(out))
    
    elif action == 'exec':
        cmd = sys.argv[2]
        out, err = run(cmd, timeout=60)
        print(sanitize(out))
        if err: print('ERR:', sanitize(err)[:300])
    
    elif action == 'upload':
        local, remote = sys.argv[2], sys.argv[3]
        c = load_cred()
        sftp = paramiko.SFTPClient.from_transport(get_client().get_transport())
        sftp.put(local, remote)
        sftp.close()
        print(f'✅ 已上传: {local} → {remote}')
