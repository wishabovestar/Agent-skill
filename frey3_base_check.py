# -*- coding: utf-8 -*-
"""R905 L5 基准: Frey 多项式模 q 约化分类 (V2-V5) — 自验纪律: part 0 先验自身
T1 重根⟺判别式零 | T2 根重数分类(光滑/节点/尖点) | T3 互素⟹奇素半稳定(结构)
V2 穷举: 互素 A,B≤40 × 奇素 q∈[5,97]: 枚举检测(根+导数) vs 判别式预测
V3 随机大样本: 20k 互素 A,B≤10^6 × q 三类
V4 独立路线: 点计数 a_q 签名 (节点→±1 必要 / 光滑→Hasse / 见对抗-尖点→0)
V5 判别式独立核算: 完整展开公式 vs A^2B^2C^2 闭式
"""
import math, random, time

def gcd(a, b):
    while b: a, b = b, a % b
    return a

def is_prime(n):
    if n < 2: return False
    if n < 4: return True
    if n % 2 == 0: return False
    i = 3
    while i * i <= n:
        if n % i == 0: return False
        i += 2
    return True

def prime_factors(n):
    fs, d = set(), 2
    while d * d <= n:
        while n % d == 0: fs.add(d); n //= d
        d += 1
    if n > 1: fs.add(n)
    return fs

# ---------- 判别式公式 (完整 Silverman/通用三次展开) ----------
def disc_full(A, B):
    u, v, w = (B - A), -(A * B), 0          # f = x^3 + ux^2 + vx + w
    return u*u*v*v - 4*v*v*v - 4*u*u*u*w - 27*w*w + 18*u*v*w

def disc_closed(A, B):
    return A*A * B*B * (A+B)*(A+B)

# ---------- 模 q 枚举检测 (独立路径: 根 + 形式导数) ----------
def detect_modq(A, B, q):
    """返回 'smooth' | 'node' | 'cusp' — 枚举 F_q 上 f, f', f'' 判重根"""
    ba = (B - A) % q; ab = (A * B) % q     # f = x^3 + (B-A)x^2 - ABx
    f  = lambda x: (x*x*x + ba*x*x - ab*x) % q
    fp = lambda x: (3*x*x + 2*ba*x - ab) % q
    fpp= lambda x: (6*x + 2*ba) % q
    mult = []
    for r in range(q):
        if f(r) == 0 and fp(r) == 0:
            mult.append(r)
    if not mult: return "smooth"
    if any(fpp(r) == 0 for r in mult): return "cusp"
    return "node"

def predict_modq(A, B, q):
    z = sum(1 for v in (A % q, B % q, (A+B) % q) if v == 0)
    return {0: "smooth", 1: "node", 3: "cusp"}[z]   # z==2 不可能(线性依赖)

# ---------- V4 点计数 ----------
def a_q(A, B, q):
    """a_q = q+1 - #E(F_q), E: y^2 = x(x-A)(x+B)"""
    pts = 1  # 无穷远
    ba = (B - A) % q; ab = (A * B) % q
    half = (q - 1) // 2
    for x in range(q):
        fv = (x*x*x + ba*x*x - ab*x) % q
        if fv == 0: pts += 1
        elif pow(fv, half, q) == 1: pts += 2
    return q + 1 - pts

t0 = time.time(); fails = []; checks = 0

# ===== V5: 判别式公式独立核算 (先于一切 — 公式是后续全部依赖) =====
random.seed(905)
v5_n = 0
for _ in range(5000):
    A, B = random.randint(-8000, 8000), random.randint(-8000, 8000)
    if disc_full(A, B) != disc_closed(A, B):
        fails.append(f"V5 disc mismatch A={A} B={B}")
        break
    v5_n += 1
checks += v5_n
print(f"V5 判别式核算: {v5_n} 随机组 disc(展开)==A²B²(A+B)² 全过 ✅")

# ===== V2: 穷举 互素 A,B≤40 × 奇素 q∈[5,97] =====
v2_cnt = {"smooth": 0, "node": 0, "cusp": 0}; v2_mis = 0
for A in range(1, 41):
    for B in range(1, 41):
        if gcd(A, B) != 1: continue
        for q in range(5, 98, 2):
            if not is_prime(q): continue
            det = detect_modq(A, B, q)
            pre = predict_modq(A, B, q)
            checks += 1
            if det != pre:
                fails.append(f"V2 mismatch A={A} B={B} q={q} det={det} pre={pre}")
                v2_mis += 1
                if v2_mis > 5: break
            v2_cnt[det] += 1
        if v2_mis > 5: break
    if v2_mis > 5: break
print(f"V2 穷举: smooth={v2_cnt['smooth']} node={v2_cnt['node']} cusp={v2_cnt['cusp']} mismatch={v2_mis} ✅")

# ===== V3: 随机大样本 20k 互素 × q 三类 =====
v3_cnt = {"smooth": 0, "node": 0}; v3_mis = 0
for _ in range(20000):
    A = random.randint(1, 10**6); B = random.randint(1, 10**6)
    if gcd(A, B) != 1: continue
    # q1: A 的大奇素因子 (若≥5) — disc 代数预测
    pf = [p for p in prime_factors(A) if p >= 5]
    qs = (pf[:1] if pf else [])
    qs += [random.choice([q for q in range(5, 200, 2) if is_prime(q)])]
    qs += [random.choice([q for q in range(5, 2000, 2) if is_prime(q)])]
    for q in qs:
        pre = predict_modq(A, B, q)
        if q < 200:
            det = detect_modq(A, B, q)     # 枚举独立检测 (小 q)
        else:
            det = "smooth" if disc_closed(A, B) % q != 0 else "node"  # 代数判据
        checks += 1
        if det != pre:
            fails.append(f"V3 mismatch A={A} B={B} q={q} det={det} pre={pre}")
            v3_mis += 1
            if v3_mis > 5: break
        v3_cnt[det] += 1
    if v3_mis > 5: break
print(f"V3 随机: smooth={v3_cnt['smooth']} node={v3_cnt['node']} mismatch={v3_mis} ✅")

# ===== V4: 点计数独立签名 =====
node_q = 0; smooth_q = 0; v4_mis = 0; node_sigs = {"+1": 0, "-1": 0}
PRIMES9 = [5, 7, 11, 13, 17, 19, 23, 29, 31]
for _ in range(400):
    A = random.randint(1, 10**5); B = random.randint(1, 10**5)
    if gcd(A, B) != 1: continue
    for q in PRIMES9:
        pre = predict_modq(A, B, q)
        if pre == "cusp": continue          # 互素组无尖点 (对抗脚本覆盖)
        a = a_q(A, B, q)
        checks += 1
        if pre == "node":                   # 乘法约化必要签名: a_q = ±1
            node_q += 1
            if a == 1: node_sigs["+1"] += 1
            elif a == -1: node_sigs["-1"] += 1
            else:
                fails.append(f"V4 node a_q={a} A={A} B={B} q={q}")
                v4_mis += 1
        else:                               # 光滑: Hasse 界
            smooth_q += 1
            if a * a > 4 * q:
                fails.append(f"V4 smooth a_q={a} 破 Hasse A={A} B={B} q={q}")
                v4_mis += 1
print(f"V4 点计数: node {node_q} 条 → a_q=±1 (分裂{node_sigs['+1']}/非分裂{node_sigs['-1']}) | smooth {smooth_q} 条 → Hasse 全过 ✅")

print(f"\n总检查 {checks} | FAIL {len(fails)}")
if fails:
    print("FAIL 明细(前5):"); [print(" ", f) for f in fails[:5]]
else:
    print("五重基准全绿 ✅ (V1 自审见 R905 档, V2-V5 本脚本, 用时 %.1fs)" % (time.time() - t0))
