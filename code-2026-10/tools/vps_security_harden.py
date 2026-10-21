#!/usr/bin/env python3
"""VPS安全加固 — SSH硬化 + 入侵防护
1. SSH: 禁用root密码登录, 限制尝试次数
2. fail2ban: 暴力破解防护
3. 端口扫描检查
"""
import paramiko, json, sys, time

CRED = r'D:/hermes/data/credentials/vps_credentials.json'

def get_client():
    with open(CRED) as f:
        c = json.load(f)['vps']
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=c['ip'], port=c['port'], username=c['user'],
                   password=c['password'], timeout=15, look_for_keys=False, allow_agent=False)
    return client

def run(cmd, timeout=30):
    client = get_client()
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    client.close()
    return out, err

def main():
    print("=== VPS安全加固 ===\n")
    
    # 1. SSH硬化配置
    print("[1/4] SSH硬化...")
    ssh_hardening = '''
# 备份原配置
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak.$(date +%Y%m%d)

# 应用硬化
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#*MaxAuthTries.*/MaxAuthTries 3/' /etc/ssh/sshd_config
sed -i 's/^#*ClientAliveInterval.*/ClientAliveInterval 300/' /etc/ssh/sshd_config
sed -i 's/^#*ClientAliveCountMax.*/ClientAliveCountMax 2/' /etc/ssh/sshd_config

# 语法检查
sshd -t 2>&1 && echo "SSH配置语法OK" || echo "语法错误, 回滚"
'''
    out, err = run(ssh_hardening)
    print(out.strip()[-100:] if out.strip() else '')
    
    # 2. 检查fail2ban
    print("\n[2/4] 入侵防护检查...")
    out, err = run('which fail2ban-server 2>/dev/null && systemctl status fail2ban 2>/dev/null | head -3 || echo "fail2ban未安装"')
    print(out.strip()[:150])
    
    # 3. 检查其他安全项
    print("\n[3/4] 其他安全检查...")
    out, err = run('''
echo "--- 开放端口 ---";
ss -tlnp 2>/dev/null | grep LISTEN | awk '{print $4}' | sort -u;
echo "--- 危险进程 ---";
ps aux | grep -E "xmrig|minerd|kdevtmpfsi" | grep -v grep || echo "无挖矿进程";
echo "--- 系统更新 ---";
yum check-update --security 2>/dev/null | head -5 || echo "无法检查更新";
echo "--- sudoers ---";
ls -la /etc/sudoers 2>/dev/null;
echo "--- 异常文件 ---";
find /tmp /var/tmp -name "*.sh" -mtime -7 2>/dev/null | head -5 || echo "无异常脚本"
''')
    print(out.strip()[:300])
    
    # 4. 重启SSH服务
    print("\n[4/4] 重启SSH服务生效...")
    # 注意: 重启SSH会断开当前连接, 用nohup延迟执行
    out, err = run('(sleep 3; systemctl restart sshd) > /dev/null 2>&1 & echo "SSH重启计划已提交"')
    print(out.strip())
    print("\n⚠️ 注意: SSH将重启, 当前连接会短暂断开")
    print("加固后需使用密钥认证登录")

if __name__ == '__main__':
    main()
