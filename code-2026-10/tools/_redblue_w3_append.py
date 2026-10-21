# -*- coding: utf-8 -*-
"""第3周红蓝对抗报告追加脚本 (2026-08-15) — 服务发现与端口扫描 (防御视角) 专题深化轮"""
from pathlib import Path

report = """

---

# 周红蓝对抗: 服务发现与端口扫描 (防御视角) (第3周)

> 日期: 2026-08-15 | 模型: deepseek-v4-flash | 主题选择: md5("2026-08-15")%8=6
> 注: 与第1周(2026-08-05)主题碰撞, 本轮为**专题深化轮** — 聚焦2026下半年新增攻击链 (WSUS大范围利用/AI服务暴露面/Agent化扫描/扫描工具反噬), 基础扫描技术分类见第1周, 不重复。
> 范围声明: 全部分析基于公开文献/工具资料 + 本机防御自查 (netstat/redis-cli, 仅本地), 未对任何真实公网系统发起扫描。

## 红队攻击路径 (8条)

### 路径A: 高危端口批量测绘→0day/1day利用链 (2025-2026实战: WSUS 8530/8531)
```
① Shodan/Censys/自建ZMap测绘全网 8530/8531 (WSUS默认HTTP/HTTPS)
② SANS传感器实测: CVE-2025-59287公开后一周内8530/8531扫描流量显著激增
③ 对暴露WSUS发送反序列化payload (AuthorizationCookie, CVSS 9.8, 未认证)
④ 无补丁服务器被控 → 投递infostealer (2025-10-23起 Huntress/Unit42观测到实际利用)
```
- 攻击技术: 互联网测绘+未认证反序列化 (CVE-2025-59287, 补丁未装即暴露=漏洞)
- 可能后果: 全内网补丁分发服务器沦陷 → 批量横向+供应链式投毒
- 检测难度: ★★☆☆☆ (补丁缺口+端口暴露的确定性组合, 但响应窗口仅数天)

### 路径B: AI/LLM服务暴露面扫描 (2026最大新兴攻击面)
```
① 全网扫描 11434 (Ollama) / 3000,8080 (Open WebUI) / 7860 (Flowise) / 80,443 (Langflow)
② 2026实测: ~30万Ollama实例暴露, 31%未认证 (Intruder扫200万主机)
③ 未认证 /api/generate、/api/chat → 免费算力盗用、模型投毒、提示词/对话数据泄露
④ Sysdig 2026-06实案: 攻击者以暴露Ollama为"认知核心"自动完成侦察→指纹→exploit合成
```
- 攻击技术: 默认无认证端口扫描+API滥用; 高级: LLM被当作自动化攻击编排大脑
- 可能后果: 数据泄露/算力盗用/供应链污染; Agent工作流与明文API key暴露 (CSA: 12,000+ Open WebUI暴露)
- 检测难度: ★★★☆☆ (流量看似正常API调用, 需基线+行为分析)

### 路径C: 云原生/容器服务发现 (Docker/K8s/Redis 高危默认端口)
```
① 扫描 2375/2376 (Docker API) / 6443 (K8s API) / 6379 (Redis) / 9100 (node_exporter)
② 未认证Docker API → 容器逃逸+主机控制; 未绑定Redis → 写crontab/SSH key
③ 云元数据服务 (169.254.169.254) SSRF联动: 从Web漏洞跳板到云凭据
```
- 攻击技术: 默认端口盲扫 + SSRF打云元数据; 容器化环境资产边界模糊
- 可能后果: 容器逃逸→宿主机沦陷; 云AK/SK泄露; 集群级横向
- 检测难度: ★★☆☆☆ (端口特征明确, 但公网/内网边界在容器时代模糊)

### 路径D: Agent化扫描 (MCP/AI编排扫描 — 传统沙盒检测失效)
```
① 攻击者向已控Agent/MCP server下发"资产盘点"类任务
② 通过 nmap-mcp / MCP-集成扫描器 (GitHub: Vorota-ai/nmap-mcp 等) 触发端口扫描
③ 扫描动作封装为MCP工具调用, 不经过shell → 绕过shell命令检测 (bash历史/沙盒正则)
④ Agent自主迭代: 扫描→指纹→搜索CVE→生成exploit (Sysdig Ollama案例同型)
```
- 攻击技术: 工具调用链注入/滥用; 命令检测面从shell扩展到MCP层
- 可能后果: 检测规则盲区内的自动侦察; 恶意Agent被当作合法工具使用
- 检测难度: ★★★★☆ (需在MCP/工具调用层审计, 传统EDR/SIEM看不到)

### 路径E: 扫描工具反噬 (防御方工具自身成漏洞入口)
```
① 诱导/等待管理员在受控环境运行 Advanced IP Scanner / Advanced Port Scanner
② CVE-2025-1868: 扫描发起时向目标(或伪造服务器)发送NTLM hash → 抓取/中继
③ 复用hash做Pass-the-Hash / NTLM中继到SMB/AD → 管理员凭据沦陷
```
- 攻击技术: 凭据哈希泄露 via 扫描工具协议; 被动等待+主动诱捕
- 可能后果: 防御方自持工具反向泄密; 安全团队成为高价值钓鱼目标
- 检测难度: ★★★☆☆ (NTLMv2流量在LAN内常态存在, 需关注非预期目标方向)

### 路径F: 无状态高速扫描进化 (覆盖率与隐身兼得)
```
① ZeroMap类新一代: 无状态SYN (Masscan速度) + 随机源端口/包间抖动 (隐身)
② RustScan: 65k端口~3秒完成, 可无缝联动nmap -sV 深度指纹
③ 分布式资产扫描器 (GitHub: tangxiaofeng7/cscan 420⭐): 多节点分片覆盖+漏洞关联
```
- 攻击技术: 无状态发包+异步重组, 速率可达10Mpps但抖动随机化
- 可能后果: 短时间窗口内完成全端口+指纹, 传统阈值规则追不上
- 检测难度: ★★★☆☆ (仍可被流式检测发现, 但窗口缩短)

### 路径G: 被动/指纹侧信道测绘 (几乎不可检测)
```
① 不主动发包, 利用证书透明度日志 (CT log) / 被动流量 (JA3/JA4 TLS指纹) 收集资产
② 分析TLS证书SAN/颁发者 → 发现内部域名与相关IP段
③ 对已识别的服务做版本banner比对 (banner grabbing only 已知开放端口)
```
- 攻击技术: 被动测绘+第三方数据 (Censys每日ZMap/ZGrab公开索引)
- 可能后果: 攻击面无需接触目标即可完整还原; 检测完全失效
- 检测难度: ★★★★★ (无主动流量, 只能靠资产收敛+最小暴露)

### 路径H: 隐蔽隧道化内网横向扫描 (立足后第二阶段)
```
① 已获立足点 (钓鱼/0day) → C2经HTTPS/DNS/合法云服务隧道
② 隧道内对内网做慢速垂直扫描 (仅高价值端口: 22/445/3389/3306/5985/6443)
③ 利用Windows管理通道 (WinRM 5985/5986, SMB 445) 横向移动
```
- 攻击技术: 加密隧道封装扫描流量; 跳板链; 内网服务隐写
- 可能后果: 内网全图+域控/数据库沦陷; 隧道流量与正常HTTPS不可区分
- 检测难度: ★★★★☆ (需东西向流量镜像+行为基线; MITRE T1046/T1049)

## 蓝队防御矩阵

| 攻击路径 | 检测层 (WAF/SIEM/IDS) | 缓解层 (配置/代码/流程) | 落地参考 |
|:---------|:----------------------|:------------------------|:---------|
| A WSUS高危端口链 | Suricata告警 8530/8531 外部访问; SIEM关联WSUS补丁状态 | **端口最小化**: 8530/8531仅允许内部客户端; WSUS补丁SLA≤72h; 外网禁止暴露 | Unit42/Huntress/Picus WSUS加固指引 |
| B AI/LLM暴露面 | 11434/7860/3000 非本机源访问告警; API调用基线 (调用频次/模型列表) | Ollama强制回环绑定+API key/代理认证; Open WebUI前置SSO; 禁止公网直连 | CSA研究笔记2026-05; Intruder 200万主机扫描报告 |
| C 云原生端口 | Docker/K8s/Redis 默认端口外部访问告警; 元数据服务SSRF规则 | Docker API TLS+认证; Redis bind 127.0.0.1+requirepass; 云元数据IMDSv2 | 本机自查: Redis[::]:6379 wildcard绑定即此类风险 |
| D Agent化扫描 | MCP/工具调用日志审计 (扫描类工具调用白名单); Agent动作异常检测 | 工具调用审批制; MCP server最小权限; Agent沙盒无外发扫描能力 | nmap-mcp等MCP扫描工具清单; Sysdig Ollama案例 |
| E 扫描工具反噬 | NTLMv2出站到非预期目标告警; 扫描工具运行环境审计 | 扫描工具运行于隔离VM+专用账号(非域管); 禁用NBNS/LLMNR; SMB签名 | CVE-2025-1868 (Advanced IP Scanner) |
| F 高速扫描进化 | 流式检测 (UPSD); 边界SYN代理+限速; 异常源端口抖动识别 | 防火墙SYN cookie; 未使用端口默认关闭; 云WAF统一入口 | ZeroMap/RustScan特征; 第1周UPSD方案延续 |
| G 被动测绘 | 证书监控 (新证书/异常SAN); CT log订阅; 外部攻击面管理(EASM) | 证书最小信息; 内部域名拆分; 公开服务收敛到网关 | Censys CT监控; Shodan自我镜像监控 |
| H 隧道横向扫描 | 东西向流量镜像; 跳板登录审计; EDR横向移动告警; 隧道特征(长连接/固定间隔) | 微分段零信任; PAM; 服务器防火墙白名单; 管理通道源IP限制 | MITRE ATT&CK T1046/T1049; Zeek conn.log跨天关联 |

**检测规则落地示例 (基于本周检索):**
```suricata
# WSUS端口外部访问 (CVE-2025-59287 高危通道)
alert tcp $EXTERNAL_NET any -> $HOME_NET 8530,8531
(msg:"WSUS port exposed from internet - possible CVE-2025-59287 recon";
 flow:to_server,established; detection_filter:track by_src, count 5, seconds 60;
 sid:41000001; rev:1;)

# Ollama API 非本机源访问
alert tcp any any -> $HOME_NET 11434
(msg:"Ollama API accessed from non-loopback - check AI exposure";
 flow:to_server,established; sid:41000002; rev:1;)

# Docker API 外部访问
alert tcp $EXTERNAL_NET any -> $HOME_NET 2375,2376
(msg:"Docker API exposed - container takeover risk";
 flow:to_server,established; sid:41000003; rev:1;)
```
```zeek
# 慢速扫描跨天关联 (Zeek scan.zeek 参数调优)
# 降低 scan.zeek 的 threshold 并加长 interval: SumBytes/attempts 跨天聚合
# 例: redef Scan::interesting_ports += {8530/tcp, 8531/tcp, 11434/tcp, 2375/tcp};
```
> 已知局限: 端口规则可被被动测绘(路径G)完全绕过 → 必须叠加EASM+证书监控; Agent化扫描(路径D)需在工具调用层检测, 网络层看不到。

## 借鉴清单 (攻击侧/防御侧)

### 攻击侧 (巡天情报采集 2026-08-15)
| 来源 | 内容 | 价值 |
|:-----|:-----|:-----|
| CVE-2025-59287 (WSUS RCE, CVSS 9.8) | 未认证反序列化, 8530/8531端口大范围扫描利用, 投递infostealer | 高危端口测绘→利用的2025-2026实战范式 |
| CVE-2025-1868 (Advanced IP Scanner) | 扫描工具发起扫描时泄露NTLM hash, 可中继到SMB/AD | 防御方工具反噬攻击面 |
| 30万暴露Ollama / 1.2万Open WebUI (Intruder/CSA 2026) | 未认证AI推理API大规模暴露; Sysdig实案: Ollama做攻击编排大脑 | AI服务暴露面测绘与利用链 |
| tangxiaofeng7/cscan (420⭐) | 企业级分布式资产/漏洞扫描器 | 分布式扫描工程实现 |
| Vorota-ai/nmap-mcp | MCP server实现AI驱动网络扫描 | Agent化扫描/工具滥用向量 |
| alexhraber/flowhawk (78⭐) | eBPF实时网络监控+AI威胁检测 | 轻量检测替代方案参考 |
| ExploitCraft/ReconNinja / RECON-GHOST | 38阶段自动化侦察框架 (bug bounty向) | 攻击侦察全流程工具链 |
| ZeroMap / RustScan / masscan / zmap | 高速无状态扫描器族 (第1周延续, 新增ZeroMap隐身演进) | 扫描流量特征库 |

### 防御侧 (巡天情报采集 2026-08-15)
| 来源 | 内容 | 价值 |
|:-----|:-----|:-----|
| ivre/masscanned | Rust低交互honeypot, 专捕扫描器与bot, 与IVRE集成=自建GreyNoise | 扫描源识别+内部情报源 |
| Zeek scan.zeek (v6.0.9文档) | 失败连接尝试跨时间窗统计检测慢速扫描 (interval/threshold可调) | 慢速扫描检测基线 |
| yave/Zeek-Suricata-detection-rules (2025-10) | 实战化Zeek/Suricata规则 (大ICMP载荷/base64/速率异常) | 可直接部署规则集 |
| GreyNoise Global Observation Grid (2026-01-14) | 全球telnet流量骤降阶跃变化 → 扫描器景观突变观测 | 互联网扫描基线动态监测 |
| Unit42 / Huntress / Picus WSUS加固指引 | 8530/8531仅内网客户端可访问; 补丁SLA; 检测规则 | 高危端口事件响应模板 |
| threatclaw Nuclei AI暴露模板 | 用Nuclei模板扫描Ollama/Langflow/ComfyUI暴露 | 防御方主动测绘工具 |
| Suricata detection_filter (stateless+阈值) | by_src计数限流语义 (10次/15秒) | 高速/低速扫描通用规则范式 |
| eBPF网络监控 (flowhawk等) | 内核态实时流量分析+AI异常检测 | 新型检测架构参考 |

## Hermes增强建议

### 1. 落实第1周未落地的 NETWORK_SCAN 规则扩展 (优先级高)
现状核实: `security_sandbox.py` 第58-64行仍仅覆盖 `nmap/masscan/nikto/sqlmap/metasploit` — 第1周建议的 `zmap/zgrab/rustscan/unicornscan/hping3/zeromap` 未添加。
本周新增缺口: `nuclei/naabu/httpx/amass/subfinder/dnsx` (AI暴露面测绘+子域枚举工具族) 亦未覆盖。
建议直接补齐 (当前文件实测为第1周建议的2倍缺口):
```python
"NETWORK_SCAN": [
    r'\bnmap\s+', r'\bmasscan\s+', r'\bnikto\s+', r'\bsqlmap\s+',
    r'\bmetasploit\b', r'\bzmap\s+', r'\bzgrab\s+', r'\brustscan\s+',
    r'\bunicornscan\s+', r'\bhping3\s+', r'\bzeromap\s+',
    r'\bnuclei\s+', r'\bnaabu\s+', r'\bhttpx\s+',
    r'\bamass\s+', r'\bsubfinder\s+', r'\bdnsx\s+',
]
```

### 2. MCP/工具调用层扫描管控 (优先级高, 本周新增洞察)
风险: nmap-mcp 等MCP server可将扫描封装为工具调用, 完全绕过shell命令检测面。
建议:
- 在 Hermes 工具调度层增加"扫描类工具"清单 (scan_ports/probe_service/nmap-mcp/nuclei等), 调用需审批 (approvals.mode 对扫描类强制)
- MCP server最小权限: 禁止向Agent暴露公网扫描类MCP (仅允许白名单沙盒目标)
- network_executor.scan_ports() 增加目标范围校验: 拒绝非RFC1918/非沙盒网段

### 3. network_executor 增加 ScanDetector 模块 (优先级中, 第1周建议延续)
建议在 `network_executor.py` 增加被扫描检测: 本地监听接口统计单位时间SYN/异常端口次数 (复刻 Suricata detection_filter 语义 10次/15秒), 新增 8530/8531/11434/2375/6379 高危端口外部访问告警 (对应本周规则sid:41000001-41000003), 输出与DiscoveryEngine合并。

### 4. 本机暴露面自查结果 (2026-08-15, 防御侧实测)
| 端口 | 绑定 | 判定 | 建议 |
|:-----|:-----|:-----|:-----|
| 6379 Redis | **[::]:6379 wildcard (IPv6) + 127.0.0.1** | ⚠️ IPv6侧全接口暴露 (已有requirepass, 但属SSRF高危目标) | `CONFIG SET bind 127.0.0.1` / 防火墙阻断IPv6 6379 |
| 445/139 SMB/NetBIOS | 0.0.0.0 + 192.0.2.2/198.51.100.1 网卡 | ⚠️ 全网卡暴露 (Windows默认) | 确认内网可信度; 关闭139; 启用SMB签名 |
| 11434 Ollama | 127.0.0.1 仅回环 | ✅ 良好 (对照30万暴露实例) | 保持; 增加代理认证防本机恶意进程 |
| 10808 xray代理 | 127.0.0.1 仅回环 | ✅ 良好 | 保持 |
| 135/49664-49683 RPC | 0.0.0.0 | ⚠️ Windows默认 | 常规补丁管理 |

### 5. AI暴露面定期自扫 + Honeypot演练 (优先级中)
- 每月用Nuclei AI暴露模板对本地AI服务做自测 (Ollama/Open WebUI/gateway端口), 确认无公网可达
- 在沙盒部署 masscanned (ivre) 低交互honeypot, 捕获真实扫描行为建立本地扫描源指纹库
- 订阅 GreyNoise 类公开扫描源IP段 → 本地防火墙黑名单联动

---

*安全边界: 本文档全部内容基于公开资料推演与本机防御自查, 未对任何真实公网系统发起扫描/攻击; 实操建议仅限本地沙盒。*
"""

path = Path("D:/hermes/data/intel/redblue_借鉴.md")
with open(path, "a", encoding="utf-8") as f:
    f.write(report)
print("appended OK, new size:", path.stat().st_size)
print("total lines:", sum(1 for _ in open(path, encoding="utf-8")))
