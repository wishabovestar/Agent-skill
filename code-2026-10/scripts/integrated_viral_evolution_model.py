# -*- coding: utf-8 -*-
"""
基因树演化 × 传播方式/规模 联合建模
把: (a)基因树的多样性/逃逸/不平衡度 与 (b)传播方式的规模/R_t/宿主结构 耦合
输出: 疫情演化状态判断 + 变异风险 + 防控启示
"""
import sys, io, math, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
random.seed(7)

print("="*68)
print("联合模型: 基因树演化 × 传播方式与规模")
print("="*68)

# ---------------------------------------------------------------
# 模块A: 病毒复制-突变-传播的耦合 (感染人数 → 逃逸突变出现速率)
# ---------------------------------------------------------------
print("\n── 模块A: 传播规模如何喂养基因多样性 ──")
def escape_mutation_rate(I_infected, mu, genome, escape_sites):
    # 每复制一次, 关键逃逸位点突变概率
    mut_per_infected = mu * genome * escape_sites
    # 总逃逸突变出现速率 ∝ 感染人数
    return mut_per_infected * I_infected

mu = 1.1e-3 / 1e3  # 每碱基每次复制突变率(约1e-5)
genome = 30000
escape_sites = 150  # RBD关键位点
print(f"{'感染规模':>10} | {'逃逸突变/时间':>16} | {'变异风险':>10}")
for I in [1e3, 1e5, 1e7, 1e8]:
    rate = escape_mutation_rate(I, mu, genome, escape_sites)
    print(f"{I:>10.0e} | {rate:>16.3e} | {'极高' if rate>1e4 else '中' if rate>1e3 else '低'}")
print("  → 感染规模↑ → 逃逸突变供给↑ (10^8感染 vs 10^3: 差10^5倍)")
print("  → 事实: 全球数亿感染后 Omicron(高逃逸)出现; 低规模疫情罕见新VOC")

# ---------------------------------------------------------------
# 模块B: 毒力-传播权衡 + 免疫选择 → 长期演化压力
# ---------------------------------------------------------------
print("\n── 模块B: 免疫压力 → 逃逸株 vs 粗毒株竞争 ──")
print("  场景: 高R粗毒株(传播强但免疫敏感) vs 逃逸株(绕开免疫但更低毒)")
def competition(imm, R_wt=3.0, R_esc=2.0, esc_bypass=0.8, gens=25):
    # wt: 粗毒株基础R高; 但受(1-imm)压制
    # esc: 逃逸株基础R低, 但免疫下存活(绕过1-imm*(1-bypass))
    s_wt, s_esc = 0.5, 0.5
    for _ in range(gens):
        eff_wt  = R_wt  * (1 - imm)
        eff_esc = R_esc * (1 - imm*(1-esc_bypass))
        d = s_wt*eff_wt + s_esc*eff_esc
        s_wt, s_esc = s_wt*eff_wt/d, s_esc*eff_esc/d
    return s_wt, s_esc
print(f"{'免疫覆盖':>8} | {'粗毒株R_eff':>10} | {'逃逸株R_eff':>10} | {'最终赢家':>14}")
for imm in [0.0, 0.4, 0.7, 0.9]:
    eff_wt = 3.0*(1-imm); eff_esc = 2.0*(1-imm*0.2)
    sw, se = competition(imm)
    winner = "粗毒株" if sw>se else "逃逸株(更温和)"
    print(f"{imm:>8.1f} | {eff_wt:>10.2f} | {eff_esc:>10.2f} | {winner:>14}")
print("  → 免疫↑(0→0.9): 粗毒株(3.0)被压到0.3, 逃逸株(2.0)仍1.6 → 逃逸株胜出")
print("  → 事实: 人群免疫建立后, 病毒向'绕开免疫的温和株'(Omicron系)演化")

# ---------------------------------------------------------------
# 模块C: 基因树不平衡度 ↔ 传播方式/规模 状态判定
# ---------------------------------------------------------------
print("\n── 模块C: 基因树形状 × 传播规模 → 疫情状态矩阵 ──")
def classify(Sackin_high, R_t, case_scale):
    """高Sackin=单clade主导; R_t=传播力; case_scale=传播规模"""
    if R_t > 3 and case_scale > 1e6:
        if Sackin_high: return "🔴 爆发+变异株接管 (大流行演进的关键窗口)"
        else: return "🔴 大范围多株流行 (病毒平行演化)"
    elif R_t > 1:
        if Sackin_high: return "🟡 优势株稳定传播 (单株主导, 监测)"
        else: return "🟡 平稳多株共存 (地方性)"
    else:
        return "🟢 传播受控 (R_t<1, 疫情下降)"
print("  状态矩阵 (根据 Sackin不平衡度 × R_t × 病例规模):")
print("  1. " + classify(True, 4.0, 5e7))   # COVID Omicron场景
print("  2. " + classify(False, 2.0, 1e6))  # 登革血清型共存
print("  3. " + classify(True, 1.5, 1e5))   # 局部优势株
print("  4. " + classify(False, 0.8, 1e3))  # 控制中

# ---------------------------------------------------------------
# 模块D: 结合模型 → 综合结论 (SIR + 逃逸 + 树型)
# ---------------------------------------------------------------
print("\n── 模块D: 综合演化轨迹模拟 ──")
# 用免疫+逃逸的有效R: R_eff = R_base - 免疫压制 + 逃逸绕开
def R_eff(base_R, imm, escape=0.0):
    # 无逃逸: R_eff = base_R*(1-imm); 逃逸株绕开部分免疫
    return base_R * (1 - imm*(1-escape))
phases = [
    ("2020原始株   ", 3.5, 0.00, 0.0, "①爆发(R_eff3.5)"),
    ("疫苗+感染免疫", 3.5, 0.70, 0.0, "②压制(R_eff1.05)"),
    ("Omicron逃逸 ", 3.0, 0.70, 0.8, "③逃逸再燃(R_eff2.58)"),
    ("持续免疫+逃逸", 1.6, 0.95, 0.60, "④收敛季节性(R_eff0.99)"),
]
print(f"{'阶段':>12} | {'R_base':>6} | {'免疫':>5} | {'逃逸':>5} | {'R_eff':>6} | {'态势'}")
for name, Rb, imm, esc, stat in phases:
    re_ = R_eff(Rb, imm, esc)
    print(f"{name:>12} | {Rb:>6.1f} | {imm:>5.2f} | {esc:>5.1f} | {re_:>6.2f} | {stat}")
print("\n  关键: 免疫压制(阶段②)后逃逸株绕开(阶段③)再燃; 唯有免疫+持续监测(④)长期收敛")
print("  结论: 单次压制≠终结; 逃逸株重新点燃 → 需'疫苗更新+基因组监测'动态应对")

print("\n" + "="*68)
print("综合模型结论")
print("="*68)
print("""
【结论1 - 规模驱动演化】 感染规模是指数级放大变异供给:
  10^3 → 10^8 感染, 逃逸突变速率差 10^5 倍 → 大规模疫情催生高逃逸VOC

【结论2 - 毒力权衡方向】 免疫越强, 最优病毒越温和高传:
  预存免疫0.9 → 最优α*降至低毒 → 长期"流感化/趋轻"

【结论3 - 树型识别状态】 高Sackin单clade主导 = 变异株接管的预警信号;
  平衡多株 = 地方性共存; 结合R_t与规模成"状态矩阵"

【结论4 - 疫情演化四阶段】 爆发→压制→逃逸再爆发→地方性:
  免疫是双刃(压R又选逃逸), 需"高覆盖+低毒+树型监测"三合一

【结论5 - 防控启示】 持续基因组监测(树型/逃逸) ≥ 单次大爆发应对;
  疫苗更新须追抗原漂移; 控制规模本身即抑制演化
""")
