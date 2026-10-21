"""
WeChat QR login for qqbot3 — uses gateway code directly
Generates QR as PNG, saves to file
"""
import asyncio, json, sys, os

sys.path.insert(0, "C:/Users/Administrator/AppData/Local/hermes/hermes-agent")

from gateway.platforms.weixin import qr_login

async def main():
    profile = sys.argv[1] if len(sys.argv) > 1 else "qqbot3"
    print(f"=== {profile} 微信QR认证 ===")
    print("请准备好用微信扫描二维码")
    print()
    
    result = await qr_login(
        hermes_home=f"D:/hermes/hermes-data/profiles/{profile}",
        bot_type="3",
        timeout_seconds=480,
    )
    
    if result:
        token = result.get("token", "")
        account_id = result.get("account_id", "")
        print(f"\n✅ 认证成功!")
        print(f"  Token: {token[:40]}...")
        print(f"  AccountID: {account_id}")
        
        # Update .env
        env_path = f"D:/hermes/hermes-data/profiles/{profile}/.env"
        with open(env_path, "r") as f:
            env = f.read()
        
        import re
        env = re.sub(r"^WEIXIN_TOKEN=.*", f"WEIXIN_TOKEN={token}", env, flags=re.MULTILINE)
        env = re.sub(r"^WEIXIN_ACCOUNT_ID=.*", f"WEIXIN_ACCOUNT_ID={account_id}", env, flags=re.MULTILINE)
        
        with open(env_path, "w") as f:
            f.write(env)
        
        print(f"\n✅ {profile} .env已更新")
        print(f"\n下一步:")
        print(f"  hermes --profile {profile} gateway run --replace")
    else:
        print("❌ 认证失败或超时")

if __name__ == "__main__":
    asyncio.run(main())
