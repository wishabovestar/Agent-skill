# -*- coding: utf-8 -*-
"""
PFR 数值工具层精确核验 (F2^n 编码: 元素 0..2^n-1, 加法 = xor, 集合作整数集合)
① 陪集平移不变性  ② 集合版 Ruzsa 三角 |A+C|*|B| <= |A+B|*|B+C|  ③ 子空间 Ruzsa 距离性质
④ 代表性数字锚(供 Lean 闭式 theorem, 纯整数, 2^a 形式避免 log)
全扫描 + 随机, 目标 0 FAIL。纯 stdlib, 确定性种子。
"""
import sys, math, random
sys.stdout.reconfigure(encoding='utf-8')
random.seed(20260908)

FAIL = []            # (check, detail)
STATS = {}           # check -> count of verified instances

def bump(k, n=1):
    STATS[k] = STATS.get(k, 0) + n

def fail(k, detail):
    FAIL.append((k, detail))
    if len(FAIL) <= 3:
        print("  [FAIL]", k, detail)

# ---------- 基础工具 ----------
def elements(mask, N):
    return [e for e in range(N) if (mask >> e) & 1]

def sumset(S, T):
    return {a ^ b for a in S for b in T}

def is_subspace(S):
    return all(a ^ b in S for a in S for b in S)

def subspaces(n):
    """F2^n 的全部子空间, 每个返回 frozenset 且含 0。"""
    N = 1 << n
    out = []
    for mask in range(1 << N):
        if not (mask & 1):
            continue
        S = set(elements(mask, N))
        if is_subspace(S):
            out.append(frozenset(S))
    return out

def affine_family(n, subsp):
    """全部仿射子空间(子空间 + 全部陪集)去重, 加空集。"""
    N = 1 << n
    fam = set()
    for U in subsp:
        for x in range(N):
            fam.add(frozenset(x ^ u for u in U))
    fam.add(frozenset())
    return [set(s) for s in fam]

def log2i(k):
    """k 为 2 幂时返回指数, 否则 None。"""
    if k <= 0 or (k & (k - 1)):
        return None
    return k.bit_length() - 1

def fmt(S):
    return "{" + ",".join(str(x) for x in sorted(S)) + "}"

# ================= ① 陪集平移不变性 =================
print("== ① 陪集平移不变性 ==")
for n in (3, 4):
    N = 1 << n
    subs = subspaces(n)
    dims = {}
    for U in subs:
        dims[len(U)] = dims.get(len(U), 0) + 1
    print(f"F2^{n}: 子空间总数 {len(subs)}  按大小: "
          + " ".join(f"|U|={k}:{c}" for k, c in sorted(dims.items())))
    for U in subs:
        Uset = set(U)
        # (a) U+U = U (和集 = 自身)
        if sumset(Uset, Uset) != Uset:
            fail("T1_U+U!=U", f"n={n} U={fmt(Uset)}")
        bump("T1_和集=子空间自身")
        # (b) 每个陪集 x+U: (x+U)+(x+U) = U
        for x in range(N):
            cx = {x ^ u for u in Uset}
            if len(cx) != len(Uset):
                fail("T2_陪集大小", f"n={n} U={fmt(Uset)} x={x}")
            if sumset(cx, cx) != Uset:
                fail("T2_陪集自和!=U", f"n={n} U={fmt(Uset)} x={x}")
            bump("T2_(x+U)+(x+U)=U")
        # (c) 任意两陪集 x+U, y+U: |(x+U)+(y+U)| = |U+U| = |U|
        reps = sorted({x for x in range(N)})  # 用全空间元素做平移代表(含重复陪集, 更严格)
        for a in range(len(reps)):
            ca = {reps[a] ^ u for u in Uset}
            for b in range(a, len(reps)):
                cb = {reps[b] ^ u for u in Uset}
                if len(sumset(ca, cb)) != len(Uset):
                    fail("T3_陪集对和集大小", f"n={n} |U|={len(Uset)} x={reps[a]} y={reps[b]}")
                bump("T3_|(x+U)+(y+U)|=|U|")
print(f"  → 子空间和集自封闭: {STATS['T1_和集=子空间自身']} 例; 陪集自和: {STATS['T2_(x+U)+(x+U)=U']} 例; "
      f"陪集对和集大小不变: {STATS['T3_|(x+U)+(y+U)|=|U|']} 例")

# (d) 附加: 一般集合平移不变性 |(a+S)+(b+T)| = |S+T| (随机)
ran = 0
for n in (3, 4):
    N = 1 << n
    for _ in range(1000):
        S = set(random.sample(range(N), random.randint(0, N)))
        T = set(random.sample(range(N), random.randint(0, N)))
        a, b = random.randrange(N), random.randrange(N)
        s0 = len(sumset(S, T))
        s1 = len(sumset({a ^ s for s in S}, {b ^ t for t in T}))
        if s0 != s1:
            fail("T4_平移不变", f"n={n} |S|={len(S)} |T|={len(T)} {s0}!={s1}")
        bump("T4_一般平移不变", 1); ran += 1
print(f"  → 一般集合随机平移不变性: {ran} 例")

# ================= ② 集合版 Ruzsa 三角 =================
def ruzsa_tri(A, B, C, tag):
    """|A+C|*|B| <= |A+B|*|B+C|; 返回 (ok, lhs, rhs, sizes)"""
    lhs = len(sumset(A, C)) * len(B)
    rhs = len(sumset(A, B)) * len(sumset(B, C))
    ok = lhs <= rhs
    return ok, lhs, rhs, (len(A), len(B), len(C))

print("== ② 集合版 Ruzsa 三角 |A+C|*|B| <= |A+B|*|B+C| ==")
# (a) F2^3 全穷举(利用 (A,C) 对称性: A<=C 覆盖全部有序(A,C), B 全 256)
n = 3; N = 1 << n; SZ = 1 << N          # 群大小 N=8, 子集数 SZ=256
M = [[0]*SZ for _ in range(SZ)]
elists = [elements(m, N) for m in range(SZ)]
pc = [len(e) for e in elists]           # |S_mask|
for i in range(SZ):
    Ei = elists[i]
    row = M[i]
    for j in range(i, SZ):
        s = len({a ^ b for a in Ei for b in elists[j]})
        row[j] = s; M[j][i] = s
tot3 = eq3 = fail3 = 0
min_ratio = None
for i in range(SZ):
    row_i = M[i]
    for k in range(i, SZ):
        mik = row_i[k]
        for j in range(SZ):
            lhs = mik * pc[j]           # |B| = popcount
            rhs = row_i[j] * M[j][k]
            tot3 += 1
            if lhs == rhs:
                eq3 += 1
            elif lhs > rhs:
                fail3 += 1
                if fail3 <= 3:
                    fail("T5_穷举三角反例", f"n=3 A={fmt(set(elists[i]))} B={fmt(set(elists[j]))} C={fmt(set(elists[k]))} LHS={lhs} RHS={rhs}")
            else:
                if min_ratio is None or rhs < min_ratio[0]:
                    min_ratio = (rhs, lhs, i, j, k)
print(f"  → F2^3 全穷举(含空集/单点/子空间/全空间; (A,C) 无序即覆盖全部): {tot3} 组, "
      f"FAIL={fail3}, 相等(等号) {eq3} 组")
if min_ratio:
    _, lhs, i, j, k = min_ratio
    print(f"    最紧非等号实例: A={fmt(set(elists[i]))} |A|={len(elists[i])}, B={fmt(set(elists[j]))} |B|={len(elists[j])}, "
          f"C={fmt(set(elists[k]))} |C|={len(elists[k])}: LHS={lhs} RHS={min_ratio[0]}")

def rnd_subsets(n, k, lo=1, hi=None):
    N = 1 << n
    hi = hi or N
    for _ in range(k):
        s = random.randint(lo, hi)
        yield set(random.sample(range(N), s))

# (b) 随机 (两个空间各 5000, 规模 1..16)
for n in (3, 4):
    N = 1 << n
    cnt = 0
    for A, B, C in zip(rnd_subsets(n, 5000), rnd_subsets(n, 5000), rnd_subsets(n, 5000)):
        ok, l, r, _ = ruzsa_tri(A, B, C, f"n={n}")
        if not ok:
            fail("T6_随机三角", f"n={n} A={fmt(A)} B={fmt(B)} C={fmt(C)} LHS={l} RHS={r}")
        bump("T6_随机三角", 1); cnt += 1
    # 小规模退化偏置 (单点/2点/3点 密集)
    small = 0
    for A, B, C in zip(rnd_subsets(n, 1000, 1, 4), rnd_subsets(n, 1000, 1, 4), rnd_subsets(n, 1000, 1, 4)):
        ok, l, r, _ = ruzsa_tri(A, B, C, f"n={n} small")
        if not ok:
            fail("T6s_小规模三角", f"n={n} A={fmt(A)} B={fmt(B)} C={fmt(C)} LHS={l} RHS={r}")
        bump("T6s_小规模三角", 1); small += 1
    print(f"  → F2^{n} 随机(规模1..{N}): 5000 组 + 小规模偏置 1000 组 全过")
    # 空集混合退化
    mix = 0
    for _ in range(1000):
        A = set(random.sample(range(N), random.randint(0, N)))
        B = set(random.sample(range(N), random.randint(0, N)))
        C = set(random.sample(range(N), random.randint(0, N)))
        ok, l, r, _ = ruzsa_tri(A, B, C, f"n={n} mix")
        if not ok:
            fail("T6m_含空退化", f"n={n} A={fmt(A)} B={fmt(B)} C={fmt(C)} LHS={l} RHS={r}")
        bump("T6m_含空退化", 1); mix += 1
    print(f"  → F2^{n} 含空集退化混合: {mix} 组 全过")

# (c) F2^4 仿射子空间族(子空间/陪集/单点/全空间/空集)三重穷举
n = 4
subs4 = subspaces(n)
fam4 = affine_family(n, subs4)
print(f"  → F2^4 仿射子空间族: {len(fam4)} 个集合(含空集), 三重穷举中 ...")
Mf = [[0]*len(fam4) for _ in range(len(fam4))]
fl = [sorted(S) for S in fam4]
for i in range(len(fam4)):
    for j in range(i, len(fam4)):
        s = len({a ^ b for a in fl[i] for b in fl[j]})
        Mf[i][j] = s; Mf[j][i] = s
totf = eqf = failf = 0
for i in range(len(fam4)):
    row_i = Mf[i]
    for k in range(i, len(fam4)):
        mik = row_i[k]
        for j in range(len(fam4)):
            lhs = mik * len(fl[j])
            rhs = row_i[j] * Mf[j][k]
            totf += 1
            if lhs == rhs:
                eqf += 1
            elif lhs > rhs:
                failf += 1
                if failf <= 3:
                    fail("T7_仿射族三角", f"n=4 A={fmt(fam4[i])} B={fmt(fam4[j])} C={fmt(fam4[k])} LHS={lhs} RHS={rhs}")
print(f"  → F2^4 仿射族穷举: {totf} 组 (307 仿射+空集=308 集合, (A,C) 无序), FAIL={failf}, 等号 {eqf} 组")

# 子空间链等号定向退化: A<=B<=C 子空间链应等号
chain_eq = 0
for n in (3, 4):
    for U in subspaces(n):
        for V in subspaces(n):
            if not U <= V: continue
            for W in subspaces(n):
                if not V <= W: continue
                ok, l, r, _ = ruzsa_tri(set(U), set(V), set(W), "chain")
                if not (ok and l == r):
                    fail("T8_子空间链应等号", f"n={n} {fmt(U)}<={fmt(V)}<={fmt(W)} {l}!={r}")
                bump("T8_子空间链等号", 1); chain_eq += 1
print(f"  → 子空间链 A⊆B⊆C 定向退化(应精确等号): {chain_eq} 组 全等号")

# ================= ③ 子空间 Ruzsa 距离 =================
print("== ③ 子空间 Ruzsa 距离 (熵版 d=2H(X+Y)-H(X)-H(Y), 均匀时=2log|U+V|-log|U|-log|V|) ==")
# 整数指数形式: |U|=2^u, |V|=2^v, |U+V|=2^w, a := 2w-u-v (bits), 2^a = |U+V|^2/(|U||V|)
# 均匀性(卷积均匀 => H=log|S| 精确)也一并核验
for n in (3, 4):
    subs = subspaces(n)
    np_ = nz_ = zi_ = inv_ = uni_ = 0
    for U in subs:
        for V in subs:
            W = sumset(set(U), set(V))
            u, v, w = log2i(len(U)), log2i(len(V)), log2i(len(W))
            if u is None or v is None or w is None:
                fail("T9_非2幂大小", f"n={n} U={fmt(U)} V={fmt(V)}"); continue
            a = 2*w - u - v
            # 非负
            if a < 0:
                fail("T9_距离为负", f"n={n} U={fmt(U)} V={fmt(V)} a={a}")
            bump("T9_距离非负", 1); np_ += 1
            # a==0 <=> U==V
            if (a == 0) != (U == V):
                fail("T9_零距离当且仅当U=V", f"n={n} U={fmt(U)} V={fmt(V)} a={a} U==V:{U==V}")
            bump("T9_零距iff同", 1); nz_ += 1
            # 交叉验证浮点 log 公式
            df = 2*math.log2(len(W)) - math.log2(len(U)) - math.log2(len(V))
            if abs(df - a) > 1e-9:
                fail("T9_log不一致", f"n={n} {fmt(U)} {fmt(V)} {a} vs {df}")
            # 陪集平移不变: d(x+U; y+V) = d(U;V), 用三尺寸等式核验
            N = 1 << n
            if n == 3:
                xy = [(x, y) for x in range(N) for y in range(N)]
            else:
                xy = [(0, 0)] + [(random.randrange(N), random.randrange(N)) for _ in range(255)]
            for (x, y) in xy:
                Cx = {x ^ s for s in U}; Cy = {y ^ s for s in V}
                sCx, sCy = len(Cx), len(Cy)
                sW = len(sumset(Cx, Cy))
                if (sCx, sCy, sW) != (len(U), len(V), len(W)):
                    fail("T9_陪集平移不变", f"n={n} U={fmt(U)} V={fmt(V)} x={x} y={y}: {(sCx,sCy,sW)}!={ (len(U),len(V),len(W))}")
                bump("T9_陪集平移不变", 1); inv_ += 1
            # 卷积均匀性: (x+U)+(y+V) 每个元素表示数 = |U∩V|
            if n == 3 or random.random() < 0.1:
                x, y = random.randrange(N), random.randrange(N)
                Cx = {x ^ s for s in U}; Cy = {y ^ s for s in V}
                cnt = {}
                for a1 in Cx:
                    for b1 in Cy:
                        z = a1 ^ b1
                        cnt[z] = cnt.get(z, 0) + 1
                cap = len(U & V)
                if not cnt or len(set(cnt.values())) != 1 or next(iter(cnt.values())) != cap:
                    fail("T9_卷积非均匀", f"n={n} U={fmt(U)} V={fmt(V)} x={x} y={y} cnt={sorted(set(cnt.values()))} |U∩V|={cap}")
                bump("T9_卷积均匀", 1); uni_ += 1
    print(f"  → F2^{n}: 子空间对 {len(subs)}^2={len(subs)**2}: 距离非负 {np_} / 零距iff同 {nz_} / "
          f"陪集平移不变 {inv_} (n=4 每对抽 256 平移) / 卷积均匀(每对抽1平移) {uni_} 全过")

# ================= ④ 代表性数字锚 (n=3 为主, 供 Lean 闭式) =================
print("== ④ 代表性数字锚 (全部经本脚本实测) ==")
def anchor(tag, s):
    print("  [锚]", tag, s)

n3 = 3; N3 = 8
U = frozenset({0, 1, 2, 3})          # <{1,2}> = 4 元子空间 (1^2=3 闭合)
V = frozenset({0, 4})                # <{4}> = 2 元子空间
assert U in subspaces(n3) and V in subspaces(n3)
U4 = frozenset({0, 1, 2, 3, 4, 5, 6, 7})  # F2^4 中 <{1,2,4}> 8 元
V4 = frozenset({0, 8})                    # F2^4 中 <{8}> 2 元
assert U4 in subspaces(4) and V4 in subspaces(4)

# A1: U+U = U
anchor("A1_U+U=U", f"U=<1,2>={fmt(U)}, |U+U|=|U|={len(sumset(U, U))}; "
      f"陪集 x=4: |(4+U)+(4+U)|={len(sumset({4^s for s in U}, {4^s for s in U}))}=|U|, "
      f"(4+U)+U={fmt(sumset({4^s for s in U}, U))} 大小 {len(sumset({4^s for s in U}, U))}")
# A2: U+V = F2^3
UV = sumset(U, V)
anchor("A2_和集", f"V=<4>={fmt(V)}, U+V={fmt(UV)} = F2^3, |U+V|={len(UV)}=2^3")
# A3: Ruzsa 距离整数指数
anchor("A3_d(U;V)", f"|U|=4=2^2, |V|=2=2^1, |U+V|=8=2^3 => 整数指数 a=2*3-2-1=3 (bits), "
      f"2^a=|U+V|^2/(|U||V|)=64/8=8; d(U;U)=2*2-2-2=0, d(V;V)=2*1-1-1=0; "
      f"陪集 x=4,y=3: d(4+U;3+V): |4+U|=4, |3+V|=2, |(4+U)+(3+V)|={len(sumset({4^s for s in U},{3^s for s in V}))}=8 => 同 a=3")
# A4: 三角实例 (子空间, 2^a 形式)
ok, l, r, _ = ruzsa_tri(set(U), set(V), set(U), "A4")
anchor("A4_三角_子空间", f"A=C=U, B=V: |A+C|*|B|={l} (=2^3) <= |A+B|*|B+C|={r} (=2^6): {l} <= {r} 严格")
# A5: 子空间链等号
A5a, A5b, A5c = {0}, {0, 1}, set(U)
ok5, l5, r5, _ = ruzsa_tri(A5a, A5b, A5c, "A5")
anchor("A5_三角_链等号", f"A={{0}}, B=<1>={{0,1}}, C=<1,2>=U: |A+C|={len(sumset(A5a,A5c))}, |B|={len(A5b)} => LHS={l5}; "
      f"|A+B|={len(sumset(A5a,A5b))}, |B+C|={len(sumset(A5b,A5c))} => RHS={r5}: 等号 {l5} = {r5}")
# A6: 陪集三角
A6a, A6b, A6c = {0}, {1, 5}, set(U)
ok6, l6, r6, _ = ruzsa_tri(A6a, A6b, A6c, "A6")
anchor("A6_三角_陪集严格", f"A={{0}}, B=1+<4>={{1,5}}, C=U: LHS |A+C|*|B| = {len(sumset(A6a,A6c))}*2 = {l6}; "
      f"RHS |A+B|*|B+C| = {len(sumset(A6a,A6b))}*{len(sumset(A6b,A6c))} = {r6}: {l6} <= {r6} 严格")
# A7: F2^4 锚
W4 = sumset(U4, V4)
a7 = 2*log2i(len(W4)) - log2i(len(U4)) - log2i(len(V4))
ok7, l7, r7, _ = ruzsa_tri(set(U4), set(V4), set(U4), "A7")
anchor("A7_F2^4", f"W=<1,2,4>={fmt(U4)} (|W|=8), Z=<8>={fmt(V4)} (|Z|=2), W+Z={fmt(W4)} 全空间 |W+Z|={len(W4)}=2^4; "
      f"a=2*4-3-1={a7} (2^a={2**a7}); 三角 A=C=W,B=Z: LHS 8*2={l7} <= RHS 16*16={r7}")
# A8: 非 2 幂一般集三角 (整数式, 无 log)
A8a, A8b, A8c = {0,1,2}, {3,4}, {0,5,6,7}
ok8, l8, r8, sz8 = ruzsa_tri(A8a, A8b, A8c, "A8")
anchor("A8_一般集非2幂", f"A={fmt(A8a)} (|A|={sz8[0]}), B={fmt(A8b)} (|B|={sz8[1]}), C={fmt(A8c)} (|C|={sz8[2]}): "
      f"|A+C|={len(sumset(A8a,A8c))}, LHS={l8}; |A+B|={len(sumset(A8a,A8b))}, |B+C|={len(sumset(A8b,A8c))}, RHS={r8}: {l8} <= {r8}")
# A9: F2^4 一般集 (稍大, 非结构化)
A9a = {0,1,2,3,4}; A9b = {1,3,5,7,9,11}; A9c = {0,2,4,6,8,10,12,14}
ok9, l9, r9, sz9 = ruzsa_tri(A9a, A9b, A9c, "A9")
anchor("A9_F2^4一般集", f"|A|={sz9[0]} (A={fmt(A9a)}), |B|={sz9[1]}, |C|={sz9[2]} (偶元集): "
      f"|A+C|={len(sumset(A9a,A9c))}, LHS={l9}; |A+B|={len(sumset(A9a,A9b))}, |B+C|={len(sumset(A9b,A9c))}, RHS={r9}: {l9} <= {r9}")
# A10: 穷举中非等号的最紧实例已由扫描给出; 再给一个 F2^4 陪集距离不变锚
x, y = 5, 9
sx = len(sumset({x ^ s for s in U4}, {y ^ s for s in V4}))
ax10 = 2*log2i(sx) - 3 - 1
anchor("A10_F2^4陪集距离", f"W=<1,2,4>, Z=<8>: d(5+W; 9+Z): |5+W|={len({5^s for s in U4})}, |9+Z|={len({9^s for s in V4})}, "
      f"|(5+W)+(9+Z)|={sx}=2^{log2i(sx)} => a={ax10} = d(W;Z) (平移不变)")

# ================= 汇总 =================
print()
print("== 汇总 ==")
total_checks = sum(STATS.values()) + tot3 + totf
print(f"总核验实例数: {total_checks}")
for k, v in sorted(STATS.items()):
    print(f"  {k}: {v}")
print(f"  T5_F2^3穷举三角: {tot3} (等号 {eq3})")
print(f"  T7_F2^4仿射族穷举三角: {totf} (等号 {eqf})")
print()
if FAIL:
    print(f"!!! FAIL 总数 = {len(FAIL)} (首个见上)")
    sys.exit(1)
else:
    print("0 FAIL — 全部通过")
