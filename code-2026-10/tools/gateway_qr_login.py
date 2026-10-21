"""Simple wrapper to run gateway's qr_login for a profile"""
import asyncio, sys, os

sys.path.insert(0, "C:/Users/Administrator/AppData/Local/hermes/hermes-agent")

from gateway.platforms.weixin import qr_login

async def main():
    profile = sys.argv[1]
    print(f"[{profile}] Running WeChat QR login...")
    print("Scan the QR code with your phone when it appears.")
    print()
    
    result = await qr_login(
        hermes_home=f"D:/hermes/hermes-data/profiles/{profile}",
        bot_type="3",
        timeout_seconds=480,
    )
    
    if result:
        token = result.get("token", "")
        account_id = result.get("account_id", "")
        print(f"\n{'='*50}")
        print(f"✅ SUCCESS!")
        print(f"  Token: {token[:40]}...")
        print(f"  Account: {account_id}")
        
        # Update .env
        env_path = f"D:/hermes/hermes-data/profiles/{profile}/.env"
        with open(env_path, "r") as f:
            env = f.read()
        
        import re
        env = re.sub(r"^WEIXIN_TOKEN=.*", f"WEIXIN_TOKEN={token}", env, flags=re.MULTILINE)
        env = re.sub(r"^WEIXIN_ACCOUNT_ID=.*", f"WEIXIN_ACCOUNT_ID={account_id}", env, flags=re.MULTILINE)
        
        with open(env_path, "w") as f:
            f.write(env)
        print(f"  ✅ .env updated")
        print(f"  Next: restart gateway with:")
        print(f"    hermes --profile {profile} gateway run --replace")
    else:
        print(f"\n❌ Login failed or timed out")

if __name__ == "__main__":
    asyncio.run(main())
