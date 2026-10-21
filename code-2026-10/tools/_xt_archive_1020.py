# -*- coding: utf-8 -*-
"""把本轮巡天采集归档到知识库目录（带口径与缺陷声明）"""
from pathlib import Path
from datetime import datetime

src = Path("D:/hermes/analysis/_xt_report_1020.md").read_text(encoding="utf-8")
hdr = f"""# 巡天知识采集更新 · {datetime.now().strftime('%Y-%m-%d %H:%M')}

- 执行：mybot 会话手动触发（cron 3416eaa83100 / 8947bbe85b0f 今日 06:21 / 05:20 已跑）
- 去重基线：近 45 天归档 JSON 中 seen=4745 个 full_name（838 个文件）
- 代理：强制直连（ProxyHandler({{}})；注册表代理 socks5h://127.0.0.1:10810 会让 urllib 全源 SSL EOF）
- 原始数据：`_xt_update_20261020_0914.json`

## 口径声明（必须先读）
1. `new=3 / dup=57` 只对**本轮 60 条实抓**而言，不等于当日在库总量。
2. GitHub 搜索未认证，search 限额 10 次/分、60 次/时；本轮 8 组查询、间隔 7 s。
3. arXiv 的 `solid-state-battery` / `battery-manufacturing` 两查询返回的最新命中为 **8 月/7 月**，
   与 `sortBy=submittedDate` 预期不符 ⇒ **排序疑似未生效，未验证**，不得据此断言「近期无新文」。
4. 本轮未跑 `kb_sync.py` 索引，只落文件；索引重建属周任务（周一 04:00）。

---

"""
ftr = """

---

## 本轮观察（判断，非原文）
- `HexaFuture/HexaShell` (★32, created 2026-10-09) 与今日交付的卡片 514 为同一工作（薄 harness + RGB 三角化 + 写自工具，42 个 RoboDojo 任务）⇒ 论文-代码已对上号。
- `robot-agent-exploration/rax`（RAX harness：让 coding agent 通过在线探索学机器人任务）与 514 同一范式，说明「coding agent 当机器人程序员」已成小分支。
- `ctoldigital/axuse` 走 CDP/可访问性树而非截屏做 computer-use，是 514「纯 RGB」路线的对立面，值得对照。
- 锂电侧真正相关的是 `2608.07958 LIBAD`（极片制造多模态异常检测基准）与 `2607.11521`（辊压 U 形曲线 → 极片热导），与你的涂布/辊压工艺直接对口。
"""
out = Path("D:/hermes/data/agent_knowledge/xuntian_update_20261020_0915.md")
out.write_text(hdr + src + ftr, encoding="utf-8")
print("WROTE", out, out.stat().st_size, "bytes")
