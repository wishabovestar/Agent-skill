# -*- coding: utf-8 -*-
"""R903 挑刺审计补充: 对抗性验证 (V1 第二轮) — 找茬直到零问题"""
import math, random

print("=== 审计 R1: c4 符号约定交叉核对 (文献 Δ=16(abc)^{2p} 对照) ===")
# 三个根排布变体 (x→-x / 换根) 下 c4/Δ 是否稳定
def inv(a2, a4):
    b2 = 4*a2; b4 = 2*a4; b6 = 0; b8 = -a4*a4
    c4 = b2*b2 - 24*b4
    d = -b2*b2*b8 - 8*b4*b4*b4
    return c4, d
A, B = 8, 27  # a=2,b=3,p=3
for name, a2, a4 in [('根0,A,-B (本层约定)', B-A, -A*B),
                     ('根0,-A,B', A-B, -A*B)]:
    c4, d = inv(a2, a4)
    print(f'  {name}: c4={c4} (期望 16(A^2+AB+B^2)={16*(A*A+A*B+B*B)}), 一致={c4==16*(A*A+A*B+B*B)}')
    print(f'    Δ={d}, (A+B)^2 形式={16*A*A*B*B*(A+B)*(A+B)}, 一致={d==16*A*A*B*B*(A+B)*(A+B)}')

print()
print("=== 审计 R2: T4 gcd=1 反例猎杀 (扩域随机 + 非互素对照组) ===")
random.seed(999)
bad = 0
for _ in range(30000):
    A = random.randint(1, 10**7); B = random.randint(1, 10**7)
    if math.gcd(A, B) != 1: continue
    if math.gcd(A*A+A*B+B*B, A*B*(A+B)) != 1:
        bad += 1; print('反例!', A, B)
print(f'  30k 随机互素 (A,B) 直扫: gcd=1 保持, 反例 {bad}')
# 对照组: 非互素时 gcd 可以 >1 (证明前提必要性)
g = math.gcd(6*6+6*12+12*12, 6*12*18)
print(f'  对照组 (A=6,B=12 非互素): gcd={g} (≠1 预期 — 证明需 gcd(A,B)=1)')

print()
print("=== 审计 R3: 3|abc 情形 (Frey 3-adic 例外检查) ===")
# a=3,b=5,p=3: A=27,B=125 (3|a): core 与 AB(A+B) 互素?
A, B = 27, 125
core = A*A+A*B+B*B
print(f'  a=3,b=5,p=3: gcd(core,AB(A+B))={math.gcd(core, A*B*(A+B))} | core={core}')
print(f'  core % 3 = {core % 3} (A≡0 ⟹ core≡B^2 非 0 — 3 例外无公共因子)')
# 3 | (A+B) 情形: a=1,b=2,p=3: A+B=9
A, B = 1, 8
core = A*A+A*B+B*B
print(f'  a=1,b=2,p=3 (3|A+B): gcd={math.gcd(core, A*B*(A+B))} | core={core} (mod 3={core%3})')

print()
print("=== 审计 R4: 万有恒等式在扩展网格 (V4 复跑更大范围) ===")
bad4 = 0; n4 = 0
for a in range(1, 80):
    for b in range(1, 80):
        if math.gcd(a, b) != 1: continue
        for p in (3, 5, 7):
            A, B = a**p, b**p
            b2 = 4*(B-A); b4 = -2*A*B; b8 = -A*A*B*B
            c4 = b2*b2 - 24*b4
            c6 = -b2**3 + 36*b2*b4
            d = -b2*b2*b8 - 8*b4**3
            if c4**3 - c6*c6 != 1728*d: bad4 += 1
            n4 += 1
print(f'  扩展网格 {n4} 曲线: c4^3-c6^2=1728Δ 恒等式 FAIL {bad4}')
print()
print(f'审计补充完成: 反例 {bad+bad4}, 全部通过' if bad+bad4 == 0 else f'!!! 发现反例 {bad+bad4}')
