"""Fix: restart immediately when PID dead, regardless of age"""
with open("D:/hermes/analysis/gateway_watchdog.py", "r", encoding="utf-8") as f:
    c = f.read()

# Change: "dead" means PID not alive
old = 'if diag["status"] == "dead":\n            # Gateway is dead — restart'
new = 'if diag["status"] in ["dead", "recently_died"]:\n            # Gateway process dead — restart immediately'
c = c.replace(old, new)

# Remove the "recently_died: wait" section since we now restart immediately
old2 = '''elif diag["status"] == "stale_state":
            log(f\"  ⚠ state过期({diag['age_seconds']:.0f}s)，但PID存活，等待状态更新\", name)
        elif diag["status"] == \"recently_died\":
            log(f\"  ⚠ 进程刚停止，等待下次检测\", name)'''

new2 = '''elif diag["status"] == "stale_state":
            log(f\"  ⚠ state过期({diag['age_seconds']:.0f}s)，但PID存活，等待状态更新\", name)
        elif diag["status"] == "recently_died":
            log(f\"  ⚠ 进程死亡，立即重启\", name)'''

c = c.replace(old2, new2)

with open("D:/hermes/analysis/gateway_watchdog.py", "w", encoding="utf-8") as f:
    f.write(c)

print("✅ Fixed: restart immediately on process death")
