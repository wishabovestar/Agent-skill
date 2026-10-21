#!/usr/bin/env python3
"""验证SSH密钥登录 + 禁用密码认证
"""
import paramiko, json, os, sys

CRED = r'D:/hermes/data/credentials/vps_credentials.json'
PRIV_KEY = r'D:/hermes/data/credentials/vps_keys/vps_ed25519'

def main():
    with open(CRED) as f:
        c = json.load(f)['vps']
    
    # 1. 验证密钥登录
    print("=== 1. 密钥登录验证 ===")
    try:
        v = paramiko.SSHClient()
        v.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        v.connect(hostname=c['ip'], port=c['port'], username=c['user'],
                  key_filename=PRIV_KEY, timeout=10, look_for_keys=False, allow_agent=False)
        _, out, _ = v.exec_command('echo KEY_AUTH_OK && whoami')
        print(f"  ✅ {out.read().decode().strip()}")
        v.close()
    except Exception as e:
        print(f"  ❌ 密钥登录失败: {e}")
        return False
    
    # 2. 询问是否禁用密码 (此处先验证, 不禁用——由用户确认)
    print("\n=== 2. 密钥认证就绪 ===")
    print("✅ 密钥登录正常, 可安全执行:")
    print("  - PermitRootLogin prohibit-password")
    print("  - PasswordAuthentication no")
    return True

if __name__ == '__main__':
    main()
