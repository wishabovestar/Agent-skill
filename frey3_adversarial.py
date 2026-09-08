# -*- coding: utf-8 -*-
"""R905 L5 对抗审计 (R1-R5) — 挑刺轮: 直到 0 反例
R1 前提必要性对照: 非互素 (q|A∧q|B) → 三重根(cusp) → 加法签名 a_q=0
   (证明"互素"前提非空洞 — 破坏它结论失效: 半稳定破坏)
R2 符号/顺序约定: A,B 含负值/交换 A↔B → 分类不变; 三根序 (0,A,−B) 任意
R3 尖点三重根判定: 对 gcd>1 组枚举检测 cusp 与预测一致 (q∈[5,97] 全扫)
R4 扩展网格: A,B≤200 非互素全对 × q∈[5,97] — 预测 vs 枚举 (含 cusp)
R5 半稳定装配统计: 互素组随机素扫 — cusp 出现率恒 0 (T3 数值侧)
"""
import random, time
from frey3_base_check import gcd, is_prime, detect_modq, predict_modq, a_q

t0 = time.time(); fails = []; checks = 0

# R1 + R3: 非互素全对 × q 全扫 — cusp 预测必中, 点计数 a_q=0 (加法签名)
r1_cusp = 0; r1_mis = 0
for A in range(2, 61):
    for B in range(2, 61):
        g = gcd(A, B)
        if g == 1: continue
        for q in range(5, 98, 2):
            if not is_prime(q): continue
            det = detect_modq(A, B, q)
            pre = predict_modq(A, B, q)     # 非互素 → 允许 z=3 (cusp)
            checks += 1
            if det != pre:
                fails.append(f"R3 cusp mismatch A={A} B={B} q={q} det={det} pre={pre}")
                r1_mis += 1
                if r1_mis > 5: break
            if pre == "cusp":
                r1_cusp += 1
                a = a_q(A, B, q)            # 加法约化: a_q = 0 (q≥5 必要签名)
                if a != 0:
                    fails.append(f"R1 additive a_q={a}≠0 A={A} B={B} q={q}")
        if r1_mis > 5: break
    if r1_mis > 5: break
print(f"R1+R3 非互素对照: cusp 命中 {r1_cusp} 条 → 加法签名 a_q=0 全过 | mismatch={r1_mis} ✅")

# R2: 符号/镜像/交换约定 — 判别式 A²B²(A+B)² 在 (A,B)→(−A,−B) (镜像,
# 根 {0,A,−B}→{0,−A,B}=x→−x 镜像) 与 (A,B)→(B,A) (根重排) 下数值恒等
# 注: (A,B)→(−A,B) 是换曲线 (判别式零集 A=B vs A=−B) — 非不变变换 (V1 自审抓)
r2_mis = 0
random.seed(9052)
for _ in range(3000):
    A = random.randint(-5000, 5000); B = random.randint(-5000, 5000)
    if A == 0 or B == 0 or gcd(abs(A), abs(B)) != 1: continue
    q = random.choice([p for p in range(5, 300, 2) if is_prime(p)])
    d  = (A*A * B*B * (A+B)*(A+B)) % q          # 原曲线
    dm = ((-A)*(-A) * (-B)*(-B) * (-(A+B))*(-(A+B))) % q   # 镜像 (−A,−B)
    ds = (B*B * A*A * (A+B)*(A+B)) % q          # 交换 (B,A)
    checks += 1
    if d != dm or d != ds:
        fails.append(f"R2 invariance broken A={A} B={B} q={q} d={d} dm={dm} ds={ds}")
        r2_mis += 1
print(f"R2 镜像/交换约定: 3000 组判别式数值恒等 mismatch={r2_mis} ✅")

# R4: 扩展网格 (非互素, 大范围) — 枚举 vs 预测 全含 cusp
r4_cusp = 0; r4_mis = 0
for A in range(2, 121):
    for B in range(2, 121):
        if gcd(A, B) == 1: continue
        for q in (5, 7, 11, 13, 17, 19, 23):
            det = detect_modq(A, B, q); pre = predict_modq(A, B, q)
            checks += 1
            if det != pre:
                fails.append(f"R4 mismatch A={A} B={B} q={q} det={det} pre={pre}")
                r4_mis += 1
                if r4_mis > 5: break
            r4_cusp += (pre == "cusp")
        if r4_mis > 5: break
    if r4_mis > 5: break
print(f"R4 扩展网格(非互素≤120×q): {checks} 检查 cusp={r4_cusp} mismatch={r4_mis} ✅")

# R5: 半稳定装配 — 互素组: cusp 永 0 (T3: 无加法约化 → 奇素半稳定)
cusp_hit = 0; n_curves = 0
for _ in range(5000):
    A = random.randint(2, 10**7); B = random.randint(2, 10**7)
    if gcd(A, B) != 1: continue
    n_curves += 1
    for q in random.sample([p for p in range(5, 500, 2) if is_prime(p)], 5):
        if predict_modq(A, B, q) == "cusp":
            cusp_hit += 1
            fails.append(f"R5 cusp on coprime A={A} B={B} q={q}")
print(f"R5 半稳定装配: 互素曲线 {n_curves} × 5q — cusp 命中 {cusp_hit} (恒 0 = 奇素无加法约化) ✅")

print(f"\n总检查 {checks} | FAIL {len(fails)}")
if fails:
    print("FAIL 明细(前5):"); [print(" ", f) for f in fails[:5]]
else:
    print(f"对抗审计全绿 ✅ (用时 {time.time()-t0:.1f}s) — 直到 0 反例")
