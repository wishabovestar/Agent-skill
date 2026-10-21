"""
Generate WeChat QR code for qqbot3 to re-authenticate
"""
import asyncio, json, sys, os

sys.path.insert(0, "C:/Users/Administrator/AppData/Local/hermes/hermes-agent")
sys.path.insert(0, "D:/hermes/hermes-data/hermes/hermes-agent")

from gateway.platforms.weixin import qr_login

HERMES_HOME = "D:/hermes/hermes-data/profiles/qqbot3"

async def main():
    print("生成qqbot3微信QR码...")
    print("扫码后，程序会等待认证结果...")
    print()
    
    result = await qr_login(
        hermes_home=HERMES_HOME,
        bot_type="3",
        timeout_seconds=480,
    )
    
    if result:
        token = result.get("token", "")
        account_id = result.get("account_id", "")
        print(f"\n✅ 认证成功!")
        print(f"   Token: {token[:30]}...")
        print(f"   AccountID: {account_id}")
        
        # Update .env
        env_path = os.path.join(HERMES_HOME, ".env")
        with open(env_path, "r") as f:
            env = f.read()
        
        # Replace old token
        import re
        env = re.sub(r"^WEIXIN_TOKEN=.*", f"WEIXIN_TOKEN={token}", env, flags=re.MULTILINE)
        env = re.sub(r"^WEIXIN_ACCOUNT_ID=.*", f"WEIXIN_ACCOUNT_ID={account_id}", env, flags=re.MULTILINE)
        
        with open(env_path, "w") as f:
            f.write(env)
        
        print(f"   ✅ .env已更新")
        print(f"\n下一步: 重启gateway: hermes --profile qqbot3 gateway run --replace")
    else:
        print("❌ 认证失败或超时")

if __name__ == "__main__":
    asyncio.run(main())
