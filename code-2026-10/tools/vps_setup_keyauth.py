#!/usr/bin/env python3
"""VPS SSH密钥认证设置 — 安全流程
1. 生成密钥对 (本地)
2. 上传公钥到VPS
3. 验证密钥登录
4. 然后才禁用密码认证 (由后续脚本执行)
"""
import paramiko, json, os, sys

CRED = r'D:/hermes/data/credentials/vps_credentials.json'
KEY_DIR = r'D:/hermes/data/credentials/vps_keys'
PUB_KEY = os.path.join(KEY_DIR, 'vps_ed25519.pub')
PRIV_KEY = os.path.join(KEY_DIR, 'vps_ed25519')

def get_client():
    with open(CRED) as f:
        c = json.load(f)['vps']
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=c['ip'], port=c['port'], username=c['user'],
                   password=c['password'], timeout=15, look_for_keys=False, allow_agent=False)
    return client

def run(client, cmd, timeout=30):
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    return out, err

def main():
    os.makedirs(KEY_DIR, exist_ok=True)
    
    # 1. 生成密钥 (如不存在)
    if not os.path.exists(PRIV_KEY):
        print("生成ED25519密钥对...")
        key = paramiko.Ed25519Key.generate()
        key.write_private_key_file(PRIV_KEY)
        with open(PUB_KEY, 'w') as f:
            f.write(f'ssh-ed25519 {key.get_base64()} hermes-vps-key\n')
        print(f"  ✅ 密钥已生成: {KEY_DIR}")
    else:
        print("使用已有密钥")
    
    with open(PUB_KEY) as f:
        pub = f.read().strip()
    
    # 2. 上传公钥
    print("上传公钥到VPS...")
    client = get_client()
    out, err = run(client, f'''
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "{pub}" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
echo "公钥已添加"''')
    print(out.strip())
    
    # 3. 验证密钥登录
    print("验证密钥登录...")
    try:
        v = paramiko.SSHClient()
        v.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        v.connect(hostname=json.load(open(CRED))['vps']['ip'],
                  port=json.load(open(CRED))['vps']['port'],
                  username=json.load(open(CRED))['vps']['user'],
                  key_filename=PRIV_KEY, timeout=10, look_for_keys=False, allow_agent=False)
        _, out, _ = v.exec_command('echo KEY_AUTH_OK')
        print(f"  ✅ 密钥登录验证: {out.read().decode().strip()}")
        v.close()
    except Exception as e:
        print(f"  ❌ 密钥登录失败: {e}")
        return False
    
    client.close()
    print("\n✅ 密钥认证就绪! 下一步可安全禁用密码认证")
    return True

if __name__ == '__main__':
    main()
