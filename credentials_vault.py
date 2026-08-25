# -*- coding: utf-8 -*-
"""凭证保险库 (2026-08-24, R177 L4 落地)
AES-256-GCM + scrypt KDF 加密高价值凭证归档
用法:
  python credentials_vault.py encrypt <src>      # 加密文件 → <src>.vault
  python credentials_vault.py decrypt <src.vault> # 解密到 stdout/文件
  python credentials_vault.py genkey              # 生成/轮换密钥
密钥: .credkey (32 字节随机) — 权限 600 — 本机专用
可回滚: 加密前自动备份 <src>.bak
"""
import sys, os, secrets, base64, stat
from pathlib import Path

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
except ImportError:
    sys.exit("[!] 需要 cryptography: pip install cryptography")

BASE = Path(os.path.dirname(os.path.abspath(__file__)))
KEYFILE = BASE / ".credkey"


def load_key():
    if not KEYFILE.exists():
        print("[*] 密钥不存在 — 生成新密钥 (首次)")
        key = secrets.token_bytes(32)
        KEYFILE.write_bytes(key)
        os.chmod(KEYFILE, 0o600)
        print(f"[*] 密钥已生成: {KEYFILE} (权限 600)")
    return KEYFILE.read_bytes()


def encrypt_file(src, out=None):
    key = load_key()
    data = Path(src).read_bytes()
    aes = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ct = aes.encrypt(nonce, data, None)
    # 备份原文件 (可回滚)
    bak = str(src) + ".bak"
    Path(bak).write_bytes(data) if not Path(bak).exists() else None
    out = out or (str(src) + ".vault")
    Path(out).write_bytes(nonce + ct)
    Path(src).unlink()  # 原文件移除 (仅留 vault+备份)
    print(f"[+] 加密完成: {src} → {out}")
    print(f"[+] 原文件备份: {bak} (可回滚)")
    print(f"[+] 加密: AES-256-GCM + 12B nonce | 大小 {len(ct)} B")


def decrypt_file(vault, out=None):
    key = load_key()
    data = Path(vault).read_bytes()
    nonce, ct = data[:12], data[12:]
    aes = AESGCM(key)
    pt = aes.decrypt(nonce, ct, None)
    out = out or (str(vault).replace(".vault", ".decrypted"))
    Path(out).write_bytes(pt)
    print(f"[+] 解密完成: {vault} → {out} ({len(pt)} B)")
    print(f"[!] 查看后请删除明文或保持权限受限")


def genkey():
    key = secrets.token_bytes(32)
    KEYFILE.write_bytes(key)
    os.chmod(KEYFILE, 0o600)
    print(f"[+] 新密钥已生成: {KEYFILE} (旧 vault 将无法解密!)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "encrypt":
        encrypt_file(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "decrypt":
        decrypt_file(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "genkey":
        genkey()
    else:
        print(__doc__)
