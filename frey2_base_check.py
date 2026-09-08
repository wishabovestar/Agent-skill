# -*- coding: utf-8 -*-
"""L4 前置基准: Frey 曲线不变量系统 + 互素族 (2026-09-08)
角色: flt_frey2_lean.lean 的 Python 锚定层 (R792 基准先自验纪律)
声明 (V1 自审后的精确形式):
  T1 x(x-A)(x+B) = x^3 + (B-A)x^2 - ABx        [多项式展开]
  T2 c4(E) = 16(A^2+AB+B^2),  Delta = 16 A^2 B^2 (A+B)^2
  T3 c4^3 - c6^2 = 1728 Delta  (c6 定义核算 — 万有恒等式)
  T4 gcd(A^2+AB+B^2, AB(A+B)) = 1  (gcd(A,B)=1)  [R896 P2 精确化: 除3外->恰1]
  T5 q|abc (q奇素): v_q(Delta) = 2p·v_q(abc) >= 2p, 且 q ∤ c4  (乘性+级降输入)
  T6 若 a^p+b^p=c^p: Delta = 16(abc)^{2p}   [纯代数代入; p=2 真三元 3,4,5 实例]
独立核算 (V4): 从原始 Weierstrass 系数 a1..a6 按 Silverman 定义
  计算 b2,b4,b6,b8 -> c4,c6,Delta — 与闭式比较 (两套独立实现)
独立路线 (V5): gcd 用素因子分解法 (非 Euclid); mod-q 分类表; p=2 真三元
"""
import math, random

def core(A, B): return A*A + A*B + B*B
def c4_closed(A, B): return 16 * core(A, B)
def delta_closed(A, B): return 16 * A*A * B*B * (A+B)*(A+B)
def c6_closed(A, B):
    s = B - A
    return -32 * s * (2*s*s + 9*A*B)

def def_invariants(A, B):
    """V4 独立核算: 原始定义 (a1=a3=a6=0, a2=B-A, a4=-AB)"""
    a2, a4 = B - A, -A*B
    b2 = 4*a2
    b4 = 2*a4
    b6 = 0
    b8 = -a4*a4
    c4 = b2*b2 - 24*b4
    c6 = -b2*b2*b2 + 36*b2*b4 - 216*b6
    d  = -b2*b2*b8 - 8*b4*b4*b4 - 27*b6*b6 + 9*b2*b4*b6
    return c4, c6, d

def gcd_factors(x, y):
    """V5 独立路线: gcd 经素因子分解 (试除至 sqrt)"""
    fx = set()
    n = x
    d = 2
    while d*d <= n:
        while n % d == 0:
            fx.add(d); n //= d
        d += 1
    if n > 1: fx.add(n)
    g = 1
    for q in fx:
        if y % q == 0: g *= q
    return g

def vp(n, q):
    v = 0
    while n % q == 0:
        v += 1; n //= q
    return v

# ── V2 穷举 (a,b 互素, 1..40) ─────────────────────────────
print("=== V2 穷举: 互素 (a,b) 1..40, p in {3,5} ===")
bad = 0; n_t2 = 0; n_t4 = 0
for a in range(1, 41):
    for b in range(1, 41):
        if math.gcd(a, b) != 1: continue
        for p in (3, 5):
            A, B = a**p, b**p
            n_t2 += 1
            c4d, c6d, dd = def_invariants(A, B)
            # T2 闭式 vs 定义
            if c4d != c4_closed(A, B) or dd != delta_closed(A, B):
                bad += 1; print(f'T2 FAIL a={a} b={b} p={p}')
            # T3 万有恒等式
            if c4d**3 - c6d*c6d != 1728 * dd:
                bad += 1; print(f'T3 FAIL a={a} b={b} p={p}')
            # T4 gcd=1 (Euclid) + V5 (素因子法)
            g1 = math.gcd(core(A, B), A*B*(A+B))
            g2 = gcd_factors(core(A, B), A*B*(A+B))
            if g1 != 1 or g2 != 1:
                bad += 1; print(f'T4 FAIL a={a} b={b} p={p} gcd={g1}/{g2}')
            # T5 指数: 对 q | a 或 b (奇): v_q(Delta) 与 2p·v_q(abc) 一致, q∤c4
            for q in set([3,5,7,11,13]):
                if q % 2 == 0: continue
                va = vp(A*B*(A+B), q)  # = v_q(abc 积结构) 侧 (A=a^p...)
                vd = vp(delta_closed(A, B), q)
                if va == 0: continue
                if vd != 2*va or (vd != 0 and delta_closed(A,B) % q == 0 and core(A,B) % q == 0):
                    bad += 1; print(f'T5 FAIL a={a} b={b} p={p} q={q}')
                n_t2 += 1
print(f'V2: {n_t2} 检查, FAIL {bad}')
print()

# ── V3 随机大样本 ──────────────────────────────────────────
print("=== V3 随机大样本: 200k (a,b<=10^6 互素), p in {3,5,7} ===")
random.seed(20260908)
bad3 = 0; n3 = 0
for _ in range(200000):
    a = random.randint(1, 10**6); b = random.randint(1, 10**6)
    if math.gcd(a, b) != 1: continue
    p = random.choice((3, 5, 7))
    A, B = a**p, b**p
    n3 += 1
    if math.gcd(core(A, B), A*B*(A+B)) != 1:
        bad3 += 1; print(f'T4 FAIL big a={a} b={b} p={p}')
    c4d, c6d, dd = def_invariants(A, B)
    if dd != delta_closed(A, B):
        bad3 += 1; print(f'T2 FAIL big a={a} b={b} p={p}')
    if c4d**3 - c6d*c6d != 1728*dd:
        bad3 += 1; print(f'T3 FAIL big a={a} b={b} p={p}')
    if n3 >= 100000: break
print(f'V3: {n3} 样本, FAIL {bad3}')
print()

# ── V4 独立核算对比统计 (覆盖 V2 网格) ────────────────────
print("=== V4 独立核算: 定义路径 vs 闭式 (穷举网格全量) ===")
mismatch = 0; nn = 0
for a in range(1, 60):
    for b in range(1, 60):
        if math.gcd(a, b) != 1: continue
        for p in (3, 5):
            A, B = a**p, b**p
            c4d, c6d, dd = def_invariants(A, B)
            nn += 1
            if (c4d, c6d, dd) != (c4_closed(A,B), c6_closed(A,B), delta_closed(A,B)):
                mismatch += 1
                print(f'V4 MISMATCH a={a} b={b} p={p}')
print(f'V4: {nn} 曲线 (定义 vs 闭式: c4,c6,Delta 三元组), 不一致 {mismatch}')
print()

# ── V5 独立路线 ───────────────────────────────────────────
print("=== V5 独立路线 ===")
# ① mod-q 分类表: core(A,B) 何时被 q 整除 (gcd=1 证明的模骨架)
print("① core mod-q 分类 (q=3,5,7; A,B mod q 全扫):")
for q in (3, 5, 7):
    hit = [(x, y) for x in range(q) for y in range(q)
           if (x*x + x*y + y*y) % q == 0 and (x, y) != (0, 0)]
    print(f'   q={q}: core≡0 的非零类 {hit if len(hit) <= 6 else len(hit)} 个')
# ② p=2 真三元 3,4,5: Delta = 16(abc)^{2p} 实例
A, B, c = 9, 16, 5  # 3^2+4^2=5^2
lhs = delta_closed(A, B)
rhs = 16 * (3*4*5)**(4)   # (abc)^{2p} = 60^4
print(f"② p=2 真三元 3-4-5: Delta={lhs}, 16(abc)^4={rhs}, 一致={lhs == rhs}")
# ③ j 不变量有限性 (非退化): c4 != 0 且 Delta != 0 (A,B>0)
a, b = 2, 3
A, B = a**3, b**3
c4v = c4_closed(A, B); dv = delta_closed(A, B)
print(f"③ 非退化 (A=8,B=27): c4={c4v} !=0, Delta={dv} !=0 -> j 有限 = {c4v != 0 and dv != 0}")
print()
print("V2/V3/V4/V5 全部完成 (bad 计数全 0 = 通过)")
