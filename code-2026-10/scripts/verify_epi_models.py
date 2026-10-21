# -*- coding: utf-8 -*-
"""验证传染病演化数学模型的数值行为 (完整版)"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import numpy as np

print("="*60); print("验证1: SIR 模型 R0 阈值行为"); print("="*60)
def sir(beta, gamma, S0, I0, R0_prev, steps):
    S, I, R = S0, I0, R0_prev; N = S0+I0+R0_prev; hist=[]
    for _ in range(steps):
        dS=-beta*S*I/N; dI=beta*S*I/N-gamma*I; dR=gamma*I
        S+=dS; I+=dI; R+=dR; hist.append((S,I,R))
    return np.array(hist)
N=1000
for R0 in [0.8, 1.5, 3.0]:
    gamma=0.2; beta=R0*gamma
    h=sir(beta,gamma,N-1,1,0,200)
    peak=h[:,1].max(); finalI=h[-1,2]
    print(f"  R0={R0:>4}: 感染峰值={peak:6.1f} ({(100*peak/N):.1f}%), 累计感染={finalI:.0f} ({(100*finalI/N):.1f}%)")
print("  → R0<1 消退; R0>1 爆发, 峰值随R0↑")

print(); print("="*60); print("验证2: 多毒株竞争 (优势=最大R)"); print("="*60)
R_A, R_B = 3.0, 3.5; share_A=0.5; gens=20
for g in range(gens):
    denom = share_A*R_A + (1-share_A)*R_B
    share_A = share_A*R_A/denom
print(f"  第{gens}代: 逃逸株A占比={share_A:.4f} (B高R胜出)")
print("  → 高R(逃逸/传播强)株被选择dominant")

print(); print("="*60); print("验证3: 毒力-传播权衡 (最优复制α)"); print("="*60)
alphas=np.linspace(0.1,3,100)
def fitness(a):
    trans=a; death=1-np.exp(-0.5*a*a); return trans*(1-death)
fit=np.array([fitness(a) for a in alphas]); opt=alphas[np.argmax(fit)]
print(f"  最优复制速率 α*={opt:.2f}")
print(f"  此时传播={opt:.2f}, 死亡概率={1-np.exp(-0.5*opt**2):.2f}")
print("  → 存在传播/毒力平衡点, 极高毒力反降传播")
print("  → 演化优选温和高传播(流感化), 淘汰速杀高毒株")

print(); print("="*60); print("验证4: 抗原漂移时间 (分子钟)"); print("="*60)
mut_rate=1.1e-3; antigen_sites=100; to_escape=10
years=to_escape/(mut_rate*antigen_sites)
print(f"  10逃逸位点自然累积 ≈ {years:.1f}年 (分子钟)")
print("  → 但感染量大平行选择加速, 实际Omicron<2年")
print("  → 结论: 人群规模可超分子钟预测, 凸显大流行期逃逸演化风险")
