# -*- coding: utf-8 -*-
"""追加第2周红蓝对抗报告到 redblue_借鉴.md"""
import io

ADD = u"""

---

# 周红蓝对抗: 加密实现审计 (弱算法/错误使用) (第2周)

> 日期: 2026-08-08 | 模型: deepseek-v4-flash | 主题选择: md5("2026-08-08")%8=7
> 范围声明: 全部分析基于公开文献/工具资料，仅本地沙盒推演，未对任何真实系统发起攻击。

## 红队攻击路径 (8条)

### 路径A: 弱哈希滥用 (MD5/SHA-1)
```
① 侦察目标认证/签名逻辑 (密码哈希、JWT签名、证书指纹、文件校验)
② 识别MD5/SHA-1使用点 (响应头、前端JS、源码、配置)
③ 离线破解: 彩虹表+字典 (MD5 14.7T/s@GPU, 秒破弱密码)
④ 碰撞攻击: SHAttered类构造 (SHA-1碰撞对, 用于恶意证书/文件签名)
⑤ 替换合法对象 (恶意jar/更新包/证书) 维持信任链
```
- 攻击技术: 彩虹表、字典攻击、选择前缀碰撞 (Chosen-Prefix)
- 可能后果: 密码库批量还原、签名伪造、供应链投毒(更新包)
- 检测难度: ★★☆☆☆ (破解侧离线不可检测; 签名伪造需证书透明度监控)

### 路径B: 过时对称加密 (DES/3DES/RC4/ECB)
```
① 抓取流量/密文 (中间人或数据库泄漏)
② 识别弱套件: 3DES(64位块)/RC4(流密码偏差)/DES(56位密钥)
③ Sweet32: 2^32.5块后撞生日 → 恢复明文块 (3DES CBC需~785GB流量)
④ ECB模式: 相同明文块→相同密文块 → 企鹅图/模式泄露 (头像/会话cookie可辨识)
⑤ RC4: Bar Mitzvah/偏差攻击恢复cookie (TLS会话劫持)
```
- 攻击技术: 生日攻击、已知明文模式分析、统计偏差
- 可能后果: 会话cookie解密、机密明文还原、数据完整性破坏
- 检测难度: ★★★☆☆ (需要大量密文采样, 被动侧可检测弱套件协商)

### 路径C: JWT算法混淆 (alg:none / RS256→HS256 / kid注入)
```
① 拿到JWT (Authorization头/cookie/本地存储)
② 改alg为none并删签名 → 服务端若信任alg头则直接绕过
③ RS256→HS256: 将公钥(jwks/证书)作为HMAC密钥重签 → 服务端用公钥验签则通过
④ kid字段注入: kid="../../etc/passwd" / SQL注入 → 服务端按kid路径取密钥
⑤ 弱HMAC密钥爆破 (jwt-attack-suite: wordlist秒级爆破)
```
- 攻击技术: 算法混淆、参数注入、密钥爆破
- 可能后果: 任意用户冒充 (越权/提权)、完整账号接管
- 检测难度: ★★★☆☆ (需校验alg白名单与服务端验签逻辑; 流量侧可检测异常alg头)

### 路径D: Padding Oracle攻击 (CBC模式)
```
① 找到使用CBC+PKCS7且区分填充错误的端点 (登录/解密/加解密API)
② 逐字节修改密文块, 观察填充错误/成功响应差异 (oracle)
③ 恢复明文/构造任意密文 (padding-oracle-attacker/pax自动化工具有216+142⭐)
④ 变体: Bleichenbacher (RSA PKCS#1 v1.5) → 恢复RSA密钥/解密TLS会话
```
- 攻击技术: 选择密文攻击、侧信道(oracle)
- 可能后果: 密文解密、会话固定/重放、TLS会话密钥恢复(1998经典, 至今影响)
- 检测难度: ★★★★☆ (请求模式异常密集, 但合法业务错误响应会掩盖oracle信号)

### 路径E: 弱随机数与nonce重用 (PRNG/ECDSA)
```
① 收集签名样本 (ECDSA签名在区块链/固件更新/授权中公开)
② 检测nonce(k)重用/可预测 (两个同k签名 → 私钥d=(s1-s2)/(r1-r2) mod n)
③ 弱PRNG: rand()/mt19937种子可预测 → 预测IV/nonce/密钥
④ 经典: PS3 ECDSA同k签名 → 主私钥恢复(2010); WEP FMS攻击(2001)
⑤ 应用: 恢复JWT签名私钥/固件签名密钥 → 伪造任意签名
```
- 攻击技术: 格攻击(Lattice)、代数求解、统计预测
- 可能后果: 私钥恢复、任意签名伪造、区块链资产盗取
- 检测难度: ★★★★☆ (需大量签名样本+离线分析, 在线流量基本无特征)

### 路径F: TLS错误配置 (旧协议/弱套件/证书校验缺失)
```
① 资产侦察: TLS指纹/协议探测 (zgrab2/testssl.sh)
② 发现SSLv3/TLS1.0/1.1、RC4/3DES/CBC套件、空加密(EXPORT级)
③ 主动攻击: POODLE(SSLv3,2014)/BEAST(TLS1.0 CBC,2011)/降级攻击
④ 证书链弱点: 自签名/过期/CN不匹配/弱公钥(512/1024位RSA)
⑤ 中间人: 客户端证书校验缺失 → 明文窃听
```
- 攻击技术: 协议降级、padding攻击、中间人
- 可能后果: 会话劫持、敏感数据窃听、凭证泄露
- 检测难度: ★★★☆☆ (testssl.sh/zgrab2可全自动发现; 被动流量检测弱套件协商)

### 路径G: 硬编码密钥与默认凭据
```
① 源码/配置文件/镜像/固件扫描 (gitleaks/trufflehog模式: AES密钥/API key/私钥块)
② 前端JS/移动端APK提取硬编码密钥 (strings/反编译)
③ 默认密钥/出厂密钥 (路由器/设备/数据库弱口令)
④ 密钥轮换缺失 → 泄漏密钥长期有效
```
- 攻击技术: 静态扫描、逆向、字典
- 可能后果: 加密数据直接解密、系统认证绕过、供应链投毒
- 检测难度: ★☆☆☆☆ (扫描器全自动; 但历史遗留/第三方组件内硬编码难覆盖)

### 路径H: 加密错误使用模式 (Crypto Misuse)
```
① 认证加密缺失: 仅加密不认证 (CBC+独立MAC顺序错误 → CBC-MAC攻击)
② 盐重用/固定IV → 相同明文产生相同密文 (模式分析/彩虹表)
③ KDF迭代次数过低 (PBKDF2<10万次/BCrypt<10轮) → GPU爆破成本低
④ 自己造轮子: 自定义XOR/ROT/混淆替代真加密 (商业软件常见)
⑤ 密钥直接当IV用/IV=nonce固定 → 首块明文可恢复
```
- 攻击技术: 密码分析组合 (模式/重用/弱参数)
- 可能后果: 加密形同虚设、密码库批量还原
- 检测难度: ★★★★☆ (需静态分析+上下文判断; 自动化工具LAMMA/semgrep可覆盖)

## 蓝队防御矩阵

| 攻击路径 | 检测层 (WAF/SIEM/工具) | 缓解层 (配置/代码/流程) | 落地参考 |
|:---------|:----------------------|:------------------------|:---------|
| A 弱哈希 | 代码扫描: bandit/semgrep标记MD5/SHA1用于安全上下文; SIEM告警旧摘要算法证书 | 密码存储强制argon2id/bcrypt/scrypt; 签名证书迁移SHA-256+; 禁止MD5/SHA1用于安全目的 | PyCQA/bandit 8200⭐; trailofbits/semgrep-rules 515⭐ |
| B 过时对称 | 被动流量检测TLS套件协商 (3DES/RC4/ECB); Zeek TLS日志规则 | TLS1.2+仅启用AEAD (AES-GCM/ChaCha20); 禁用CBC/RC4/3DES; 应用层强制GCM模式 | testssl.sh评级; Mozilla SSL配置生成器 |
| C JWT混淆 | WAF规则: 拒绝alg!=白名单的JWT; SIEM关联异常alg字段; 服务端严格校验签名 | 服务端硬编码alg白名单(RS256); 禁止alg:none; kid参数化查询+路径校验; 密钥≥256bit | jwt-attack-suite(攻击侧反推); NullAILab/nullai-token-playground攻防实验 |
| D Padding Oracle | 请求异常密集检测 (同端点高频解密请求); 统一错误响应(不区分填充错误) | 使用AEAD替代CBC+padding; 错误响应归一化; 加解密端点速率限制 | padding-oracle-attacker 216⭐(验证用); liamg/pax 142⭐ |
| E 弱随机/nonce | 离线审计: 收集签名样本做格分析(红队演练); 代码扫描禁止rand()/time种子 | 使用CSPRNG (secrets/os.urandom); ECDSA强制RFC6979确定性nonce; 定期密钥轮换 | RFC6979; PS3/WEP历史案例库 |
| F TLS错误配置 | 定期testssl.sh/zgrab2资产扫描; 证书有效期/CT日志监控 | TLS1.2+最小配置; 证书自动轮换(ACME); 客户端强制证书校验 | testssl/testssl.sh 9156⭐(2026-08-04活跃); zmap/zgrab2 2152⭐ |
| G 硬编码密钥 | 仓库扫描(gitleaks/trufflehog)接入CI; 镜像/固件扫描 | 密钥托管到KMS/HSM; 密钥轮换策略; 默认凭据强制修改 | 凭据管理交叉主题(第5周预案) |
| H Crypto误用 | 静态分析: bandit/gosec/semgrep crypto规则; 依赖SBOM检查弱库 | 使用高抽象库(libsodium/Google Tink); 安全编码规范; 代码评审加密点 | tls-attacker 876⭐(库级fuzz); LAMMA-beta(实现审计) |

**检测规则落地示例 (Zeek/SNORT风格):**
```text
# TLS弱套件协商检测 (TLS1.0/1.1, RC4/3DES)
alert tls $HOME_NET any -> $EXTERNAL_NET any
(msg:"TLS weak protocol/version negotiation"; flow:established;
tls.version; content:"|03 01|"; sid:40000010;)  # TLS 1.0

# JWT异常alg (无签名token特征: 三段中第二段为空或alg=none)
alert http $EXTERNAL_NET any -> $HOME_NET any
(msg:"JWT alg none/weak header"; flow:to_server,established;
content:"alg"; nocase; content:"none"; nocase; sid:40000011;)
```
> 已知局限: 加密误用类攻击多在应用层且无网络特征 → 必须叠加静态分析(CI门禁)与服务端逻辑加固, 不能只靠流量检测。

## 借鉴清单 (攻击侧/防御侧)

### 攻击侧 (巡天情报采集 2026-08-08)
| 来源 | 内容 | 价值 |
|:-----|:-----|:-----|
| Zeeshanafridai/jwt-attack-suite | JWT攻击全类CLI: alg:none绕过/RS256→HS256混淆/HMAC密钥爆破/kid注入 | 算法混淆攻击自动化模板 |
| KishanBagaria/padding-oracle-attacker (216⭐) | PKCS7 padding oracle攻击CLI+库, 并发请求 | CBC oracle攻击落地 |
| liamg/pax (142⭐) | Go PKCS7 padding oracle CLI | 轻量快速oracle工具 |
| Vozec/RSA-Padding-Oracle | Bleichenbacher RSA PKCS#1 v1.5实现 | TLS/密钥恢复攻击参考 |
| demining/Phantom-Signature-Attack | CVE-2025-29774 Bitcoin SIGHASH_SINGLE漏洞分析 (GitHub检索) | 2025加密实现缺陷案例 |
| smxlabs/LAMMA-beta | Crypto实现漏洞评估与审计框架 | 攻击+审计双用 |
| NullAILab/nullai-token-playground | JWT攻防实验室 (alg:none/弱密钥/篡改/混淆) | 训练/验证环境 |

### 防御侧 (巡天情报采集 2026-08-08)
| 来源 | 内容 | 价值 |
|:-----|:-----|:-----|
| testssl/testssl.sh (9156⭐, 2026-08-04更新) | TLS/SSL全项审计: 协议/套件/证书/漏洞检查 | 主动TLS审计首选 |
| tls-attacker/TLS-Attacker (876⭐, 2026-08-02更新) | Java TLS库分析框架, 手动+自动化测试 | 库级fuzz/回归测试 |
| trailofbits/semgrep-rules (515⭐) | 含Crypto误用规则集 (弱哈希/ECB/固定IV) | 静态检测规则库 |
| PyCQA/bandit (8200⭐) / securego/gosec (8918⭐) | Python/Go安全静态扫描 (含弱加密告警) | CI门禁集成 |
| projectdiscovery/nuclei (30371⭐, 2026-08-05更新) | 模板化漏洞扫描, 社区含TLS/crypto检测模板 | 攻击面持续检测 |
| zmap/zgrab2 (2152⭐) | 快速应用层扫描+TLS指纹 | 资产TLS配置基线 |
| cerberauth/vulnapi (276⭐) | API安全漏洞扫描器 | API加密/认证检测 |
| Cy-S3c/BurpMCP-Ultra (178⭐) | Burp MCP服务器: JWT/IDOR攻击模块 | Agent化渗透集成 |

## Hermes增强建议

### 1. security_sandbox.py 增加 CRYPTO_WEAK 检测类别 (优先级高)
现状: 危险命令6类 (DESTRUCTIVE/NETWORK_SCAN/PRIVILEGE/DATA_EXFIL/CRYPTO_MINER) + AI攻击链21条 + 风险评分30条
缺口: 无弱加密算法使用检测 (openssl md5/des/rc4/3des, 生成弱密钥等)
建议: 新增 `CRYPTO_WEAK` 类 (权重0.6-0.7, WARN级):
```python
"CRYPTO_WEAK": [
    r'openssl\\s+.*\\b(md5|sha1|des|des3|3des|rc4|rc2)\\b',
    r'\\b(md5sum|sha1sum)\\s+.*(-c|--check)',
    r'openssl\\s+genrsa\\s+-out\\s+\\S+\\s+(512|768|1024)\\b',
]
```

### 2. 集成 testssl.sh 到 network_executor (优先级中)
- network_executor 已有端口扫描/banner识别; 增加 `TLSAuditor` 模块调用 testssl.sh 对本地沙盒HTTPS服务做协议/套件审计
- 输出评级 (A-F) + 弱套件清单, 与现有 DiscoveryEngine 结果合并

### 3. skill_security_scanner 增加加密误用规则 (优先级中)
- 14风险模式 (P/E/PE/SC/R) 基础上, 增加 `CAT-C` Crypto误用类:
  - C1: 硬编码密钥/IV (源码中`key=`+base64/hex字面量)
  - C2: 弱哈希用于安全上下文 (hashlib.md5/sha1 + password/signature)
  - C3: 自定义加密实现 (XOR/ROT/混淆函数)
  - C4: 弱参数 (PBKDF2低迭代/固定盐/固定IV)

### 4. 内部知识库加密基线核查 (优先级低)
- 核查 `knowledge_store.py`/`search_fallback.py` 的SQLite FTS5 (明文存储, 无需哈希) — 确认无弱哈希/硬编码密钥残留
- 巡天数据落盘加密: 凭据文件已存 `D:/hermes/data/credentials/` (AES-256-GCM) — 确认轮换机制存在

### 5. JWT/Token安全专项 (优先级中, 若Hermes gateway涉及token)
- 若gateway/bot服务使用JWT: 检查alg白名单、密钥强度、轮换; 用 `nullai-token-playground` 做本地攻防验证
- 新增检测规则: 入站请求JWT alg头白名单校验 (网关层)

---

*安全边界: 本文档全部内容基于公开资料推演, 未对任何真实系统发起攻击; 实操建议仅限本地沙盒。*
"""

path = r"D:/hermes/data/intel/redblue_借鉴.md"
with io.open(path, "a", encoding="utf-8") as f:
    f.write(ADD)
print("APPENDED OK, chars:", len(ADD))
