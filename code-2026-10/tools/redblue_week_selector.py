import hashlib, datetime, sys

d = datetime.date.today().strftime('%Y-%m-%d')
h = int(hashlib.md5(d.encode()).hexdigest(), 16)
print("date:", d)
print("md5:", hashlib.md5(d.encode()).hexdigest())
print("mod8:", h % 8)

# 主题池 (0-based 索引)
pool = [
    "Web应用攻击面 (SQL注入/XSS/SSRF)",
    "Agent安全 (恶意指令防御/工具滥用)",
    "API认证与授权绕过",
    "供应链与依赖漏洞 (SBOM/已知CVE)",
    "凭据管理与本地提权",
    "社交工程与钓鱼仿真",
    "服务发现与端口扫描 (防御视角)",
    "加密实现审计 (弱算法/错误使用)",
]
idx = h % 8
print("topic_index:", idx)
print("topic:", pool[idx])

# 周数估算: 2026-01-01 起算
start = datetime.date(2026, 1, 1)
week = (datetime.date.today() - start).days // 7 + 1
print("week:", week)
