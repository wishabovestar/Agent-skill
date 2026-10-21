"""Full platform diagnosis with iLink test"""
import json, subprocess, os

print("=" * 60)
print("全平台连接诊断")
print("=" * 60)

profiles = ["mybot", "qqbot2", "qqbot3", "qqbot4"]
all_ok = True

for p in profiles:
    print(f"\n--- {p} ---")
    try:
        with open(f"D:/hermes/hermes-data/profiles/{p}/gateway_state.json") as f:
            d = json.load(f)
        pid = d.get("pid", 0)
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, timeout=5)
        alive = str(pid) in r.stdout.decode("gbk", errors="replace")
        print(f"  PID: {pid} | Alive: {alive}")
        
        platforms = d.get("platforms", {})
        for name, info in platforms.items():
            s = info.get("state", "?")
            e = info.get("error_message", "")
            icon = {"connected": "✅", "connecting": "⏳", "disconnected": "❌", 
                    "retrying": "🔄", "stopped": "⏹️"}.get(s, "❓")
            print(f"  {icon} {name}: {s}", f"  err: {e[:60]}" if e else "")
            if s != "connected":
                all_ok = False
        
        # iLink test
        env_path = f"D:/hermes/hermes-data/profiles/{p}/.env"
        if os.path.exists(env_path):
            has_wx = False
            with open(env_path) as f:
                for line in f:
                    if line.startswith("WEIXIN_TOKEN=") and not line.startswith("#WEIXIN_TOKEN="):
                        has_wx = True
                        tok = line.split("=", 1)[1].strip()
                        rr = subprocess.run(["curl", "-s", "--max-time", "6",
                            "-H", f"Authorization: Bearer {token}",
                            "-H", "Content-Type: application/json",
                            "-d", '{"get_updates_buf":""}',
                            "https://ilinkai.weixin.qq.com/ilink/bot/getupdates"],
                            capture_output=True, timeout=8)
                        resp = rr.stdout.decode(errors="replace").strip()
                        if "-14" in resp:
                            print(f"  ⚠ iLink: session expired")
                            all_ok = False
                        elif '"ret":0' in resp:
                            print(f"  ✅ iLink: OK")
                        else:
                            print(f"  ❓ iLink: {resp[:40]}")
                        break
            if not has_wx:
                print(f"  ℹ️ WeChat: disabled (no credentials)")
                
    except FileNotFoundError:
        print(f"  ❌ No gateway_state.json (profile not started)")
        all_ok = False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        all_ok = False

print(f"\n{'='*60}")
if all_ok:
    print("✅ 全部平台连接正常")
else:
    print("⚠️ 存在异常，见上方标记")
print(f"{'='*60}")
