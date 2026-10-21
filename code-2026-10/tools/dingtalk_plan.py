"""
钉钉短中长期改善措施
"""
print("""
============================================================
钉钉连接改善方案
============================================================

## 当前诊断
- 每次重启后 DingTalk 正常连接（Stream Mode）
- 但 Gateway 周期性崩溃（约20-60min），导致无响应
- State 显示 connected 但实际已死（假活）
- 看门狗v3已部署但检测周期2分钟

## 根因
1. Gateway 进程因 GBK 编码异常或竞争条件崩溃
2. State 不随进程死亡更新（假活）
3. 无消息队列缓冲（崩溃期间消息丢失）
4. 看门狗检测到问题但无法自动修复（需--replace导致竞争条件）

============================================================
短/中/长期措施
============================================================

### 🔴 短期 (24h)
""")

print("S1: 稳定Gateway运行")
print("  • 停止使用 --replace 竞争")
print("  • 改为 stop → wait 5s → start")
print("  • 由看门狗v3唯一管理重启，禁止手动入口")
print()

print("S2: 看门狗增加自动修复能力")
print("  • 检测到 mybot PID死亡 → 先 stop (清理锁) → wait 5s → run (不带--replace)")
print("  • 记录每次重启原因和时间")
print("  • 连续重启>3次/30min → 告警但不重启")
print()

print("S3: 清理假活状态")
print("  • 看门狗检测到 PID 死亡 → 立即在 state 标记 dingtalk: disconnected")
print("  • 不再依赖 gateway 自身更新 state")
print()

print("""
### 🟡 中期 (1-2周)
""")

print("M1: 启动稳定性")
print("  • 创建 launcher 脚本：stop → 等5s确认PID死亡 → run")
print("  • launcher 输出日志到固定文件")
print("  • 看门狗调用 launcher 而非直接 hermes gateway run")
print()

print("M2: 消息队列缓冲")
print("  • 钉钉消息无法投递时暂存到本地文件")
print("  • Gateway恢复后重发")
print("  • 缓冲区上限100条/用户")
print()

print("M3: 单独管理dingtalk进程")
print("  • 评估是否可将 DingTalk 作为独立进程运行")
print("  • 与 mybot gateway 解耦")
print()

print("""
### 🔵 长期 (1-2月)
""")

print("L1: 多平台冗余")
print("  • 关键用户在钉钉+飞书同时绑定")
print("  • 一个平台断开时走另一个")
print()

print("L2: Gateway 平滑重启")
print("  • 重启时不中断正在处理的消息")
print("  • 实现 graceful shutdown")
print()

print("L3: 自动修复管线")
print("  • 检测 → 诊断 → 修复 → 验证 → 通知")
print("  • 端到端零人工干预")
print()

print("""
============================================================
立即执行的步骤:
  1. 停止 mybot gateway
  2. 等待5秒
  3. 启动 mybot gateway (不带--replace)
  4. 看门狗v3接手监控
""")
