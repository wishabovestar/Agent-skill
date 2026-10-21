#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MEMORY.md 瘦身（v2 结构）+ 修正 header 指针。

策略（见提案 A/B/C）：
  A 迁移 → 新建 skill hermes-harness（11器/钉根/工具栈/文档）与 hermes-kb（KB 用法）
  B 压缩 → L4 路径细节、L13 拆分、L17+L18 合并、L25 表述
  C 修正 → header 指针 analysis/MEMORY_ARCHITECTURE_v2.md → harness/docs/...
"""
import io, os, shutil, sys, datetime

P = r'D:/hermes/hermes-data/profiles/mybot/memories/MEMORY.md'
LIMIT = 2200

NEW = """# 记忆层 v2（结构见 D:/hermes/analysis/harness/docs/MEMORY_ARCHITECTURE_v2.md）
## L0 · 不可变核
用户=锂电研发工程师(极片热工艺 IR烘箱200°C+冷辊5°C)；极简指令+结构化表格；要【端到端真跑通】(脚本+指标+日志)，不接受只给方案；澄清多选常按推荐项。凭据本地脱敏(D:/hermes/data/credentials/)。
profile=mybot；微信仅 qqbot3。本机 Win11 终端=bash(git-bash)，【MSYS 路径转换已禁】⇒ native 只吃 D:/...；传 /d/... 落成 D:\\d\\...。向日葵(AweSun)远程控制本机，勿停用。
⭐ v2 核心：记忆是【传导层】非可信容器；每条须带【来源+翻转条件】；无来源断言不入 L1。
§
## L1 · 事实条（权威件位置见 harness/README.md）
⭐ 工具栈在 harness/{tools,docs,state,sandbox}；体检 = harness/tools/baseline.py --check；11 器清单 / 钉根文件 / 权威文档 ⇒ skill **hermes-harness**。
Gateway：单 host 服务全部 profile；重启=Hermes_Gateway_76bff4d2.vbs。PYTHONUTF8=1。
VPS 203.0.113.10:2222 仅密钥；GFW 旁路=vps_ssh.py；xray socks5 127.0.0.1:10808。
HF 被墙⇒hf-mirror。微信限流⇒错峰 06:15-30 摘要化。图纸隐私 AES-256-GCM，外发前过 analysis/drawing_privacy_enforcer.py。提权 IsInRole(Admin)=True。
本机模型（harness/docs/local_models_report.md）：Ollama 8 个全可用；⚠️ llama-server:8080 未运行。RTX5070 12GB。
§
## L2 · 指针（不存内容，只存去哪找）
⭐ 共享知识库 v3（全 profile 单一真源）= D:/hermes/data/kb/hermes_kb.db；打开/检索/写入/部署/归档入库 ⇒ skill **hermes-kb**（含「写库必走独立进程」铁律）。
事故/运维长文 ⇒ skills：devops/gateway-watchdog-v2 · windows-host-diagnostics · hermes-package-maintenance · wechat-connection-resilience。
研究细目（LSA-HI·注意力A/B ⇒ skill lsa-hi-sparse-attention / attention-ab-validation；图纸 613-39859-02·3D 配色）⇒ skill + user profile。
⭐ 审计铁律（harness/docs/REPRO_AUDIT.md+VERIFY_LAYER.md）：判「不复现」前【先证明检查器能命中一个已知在源的数】——可复现是【流程属性】，不是数据属性。
⭐ 元层自身 MR5=⚠️未抹平；台账人工登记 ⇒ 覆盖需边界。
⭐ 深读负结果+迁移规范: paper_deepread/MIGRATION_agent_patterns.md。
⭐⭐ 多用户隔离: qqbot4=江西富鸿金属(铜-石墨烯导线)申报负责人 ≠ mybot锂电用户 ⇒ **严禁跨 profile 合并 memories/画像**；KB & 论文库是共享件(paper archive 单文件 @analysis)。台账 analysis/KBFUSION_qqbot4_20261014.md。
"""


def main():
    apply = "--apply" in sys.argv
    cur = io.open(P, encoding="utf-8").read()

    print(f"  现状  : {len(cur)} 字符 ({100.0*len(cur)/LIMIT:.1f}%)")
    print(f"  瘦身后: {len(NEW)} 字符 ({100.0*len(NEW)/LIMIT:.1f}%)")
    print(f"  节省  : {len(cur)-len(NEW)} 字符  ({(1-len(NEW)/len(cur))*100:.0f}%)")
    print("  header 指针:", "harness/docs/MEMORY_ARCHITECTURE_v2.md" in NEW and "✓ 已修正" or "✗")
    print("  段清单:", [l[3:].split('（')[0] for l in NEW.splitlines() if l.startswith('## ')])

    if len(NEW) > LIMIT:
        print(f"  ✗ 超出预算 {len(NEW)-LIMIT} 字符，中止")
        return 1

    if not apply:
        print("\n  （试算，未写盘。加 --apply 生效）")
        return 0

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{P}.bak_before_slim_{ts}"
    shutil.copy2(P, bak)
    io.open(P, "w", encoding="utf-8", newline="\n").write(NEW)

    chk = io.open(P, encoding="utf-8").read()
    print(f"\n  ✅ 已写入。备份: {bak}")
    print(f"  验证: {len(chk)} 字符 ({100.0*len(chk)/LIMIT:.1f}%)")
    for k in ('harness/docs/MEMORY_ARCHITECTURE_v2.md', 'hermes-harness', 'hermes-kb',
              'Hermes_Gateway_76bff4d2', '203.0.113.10:2222', 'hf-mirror',
              '多用户隔离', 'MIGRATION_agent_patterns'):
        print(f"    {k:42s} {'✓' if k in chk else '✗'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
