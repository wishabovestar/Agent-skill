# hermes-agent-toolchain

个人 Agent 运行环境里长期打磨出来的一套 Python 工具链，覆盖：网络取数、论文检索与核验、记忆与调度的自动化、以及若干自检/审计闸门。

所有脚本都来自真实在跑的 cron / CLI 任务，不是示例代码；因此它们**带有本机路径假设**（`D:/hermes/...`），移植时需要改路径与 profile 名。仓库内**不含任何凭据**：密钥、token、内网地址、VPS 主机在入库前已脱敏（换成了 `203.0.113.x` / `192.0.2.x` 这类文档保留地址）。

## 目录

| 目录 | 内容 |
|---|---|
| `tools/` | 通用工具：网页抓取与反爬绕过、论文全文/元数据取证、知识库结构化、审计与自检闸门 |
| `scripts/` | 在生产 cron 上跑的脚本：早报、夜巡（arXiv 新投稿）、期刊增量、GitHub 月度、记忆整合、白日梦引擎 |
| `skills/` | 技能文档（SKILL.md），按 `devops/`、`integration/`、`productivity/` 分类 |

## 几个比较有用的脚本

- `scripts/night_watch.py` — 抓 arXiv 9 个类别的 `/new` 页，按关键词双线打分，只推「未见的新投稿且分数达阈」，失败类别自曝，全部抓空则非零退出。
- `scripts/a_incremental.py` — OpenAlex 期刊侧滚动窗口增量，带词典加权阈值与独立的 seen 台账。
- `scripts/news_brief_v2.py` — 多源早报（商品行情 / 科技 RSS / HN / arXiv / WHO 疫情通报 / 本地算法产物），空列表计入失败源而不是当成成功。
- `scripts/gh_monthly.py` — GitHub 月度更新，`created:` 与 `topic:` 双口径，带 90 天去重台账与 `--dry-run`。
- `tools/search_fallback.py` — 搜索缓存层 + 多后端 fallback 链（DDG → curl → arXiv API → GitHub → 直接报错）。
- `tools/bypass_engine.py` — 反爬绕过链：本地缓存 → 伪装直连 → 浏览器渲染 → Google Cache → Wayback，并识别阻断类型。

## 设计取向

1. **失败要出声**：抓取失败写进失败源列表并在正文里自曝；空列表不等于成功；全源失败时非零退出，让调度器报警，而不是安静地发一条空报告。
2. **数字必须能回原文**：论文类的数字清单会做归一化子串比对（NFKC、去千分位、统一 Unicode 负号），区分「原文没有」与「上下文改写过」。
3. **入库前脱敏**：见 `tools/security_sandbox.py` 的检测规则与密钥脱敏实现。
4. **限速优先**：GitHub 未认证 search 是 10 次/分，撞 403 就等 25 秒重试；爬虫按 robots.txt 与低频随机间隔设计。

## 免责

部分脚本涉及网页采集。请自行确认目标站点的 robots.txt 与服务条款，不要用于绕过付费墙或高频抓取。仓库代码按现状提供，不保证对任意环境可用。

## License

MIT，见 `LICENSE`。
