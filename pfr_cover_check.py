# pfr_cover_check.py : exhaustive pre-verification of PFR covering structure on F2^3
# (1) |A+A| distribution over all 256 subsets
# (2) low-doubling sets |A|>=2, |A+A|<=2|A| : exists subspace H, |H|<=|A|, cover count <= ceil(2K)
# (3) coset partition properties for every subspace
# 0 FAIL required before Lean artifact generation. Also emits pfr_cover_family.lean literals.
import sys
from collections import Counter

F = list(range(8))

def xor3(x, y):
    return ((x + y) % 2) * 1 + (((x // 2) + (y // 2)) % 2) * 2 + (((x // 4) + (y // 4)) % 2) * 4

assert all(xor3(x, y) == (x ^ y) for x in F for y in F), "xor3 closed form != bitwise xor"

def sumset(A):
    return sorted({xor3(x, y) for x in A for y in A})

allsub = []
for mask in range(256):
    allsub.append([i for i in F if (mask >> i) & 1])
assert len(allsub) == 256 and len(set(tuple(a) for a in allsub)) == 256

# ---------------- (1) distribution ----------------
dist = Counter()
rows = []
for A in allsub:
    s = len(sumset(A)); n = len(A)
    dist[s] += 1
    rows.append((A, n, s))
print("=== (1) |A+A| distribution over all 256 subsets ===")
for s in sorted(dist):
    print(f"  |A+A| = {s}: {dist[s]} subsets")
assert sum(dist.values()) == 256

# ---------------- subspaces by definition ----------------
def is_subspace(S):
    S = set(S)
    return 0 in S and all(xor3(x, y) in S for x in S for y in S)

subs = [A for A in allsub if is_subspace(A)]
subs_sorted = sorted(subs, key=lambda s: (len(s), s))
print("\n=== subspaces ===")
print("  count:", len(subs), " by size:", dict(sorted(Counter(len(S) for S in subs).items())))
for S in subs_sorted:
    print("   H =", S)

# ---------------- coset machinery (Lean-mirror + set ground truth) ----------------
def coset_of(a, H):
    return sorted({xor3(a, h) for h in H})

def coset_min(a, H):
    c = set(coset_of(a, H))
    for k in range(8):
        if k in c: return k
    return 7

# mirror: first-k-in-0..7 == true min of coset
for a in F:
    for H in subs:
        assert coset_min(a, H) == min(coset_of(a, H)), (a, H)
print("  coset_min mirrors true min: OK")

def cov_count(A, H):           # number of cosets of H met by A
    return len({coset_min(a, H) for a in A})

def cov_count_len(A, H):       # Lean mirror: dedup of rep list
    return len(sorted({coset_min(a, H) for a in A}))

for A in allsub:
    for H in subs:
        assert cov_count(A, H) == cov_count_len(A, H)

# ---------------- (2) low-doubling covering claim ----------------
print("\n=== (2) low-doubling covering claim ===")
fails_exact, fails4 = [], []
low = []   # (A, n, s)
low_list = []
for A, n, s in rows:
    if n >= 2 and s <= 2 * n:
        low.append((A, n, s)); low_list.append(A)
        ceil2K = (2 * s + n - 1) // n
        assert ceil2K <= 4
        best = None
        for H in subs:
            if len(H) <= n:
                c = cov_count(A, H)
                if best is None or c < best[1]:
                    best = (H, c)
        if best is None or best[1] > ceil2K:
            fails_exact.append((A, n, s, ceil2K, best))
        if best is None or best[1] > 4:
            fails4.append((A, n, s, ceil2K, best))
print("  low-doubling sets with |A|>=2 :", len(low))
print("  |A|=1 singletons (also |A+A|<=2|A|, excluded by |A|>=2 gate):", sum(1 for A, n, s in rows if n == 1 and s <= 2))
print("  FAIL exact-claim (cov<=ceil(2K) & |H|<=|A|):", len(fails_exact))
print("  FAIL simplified (cov<=4 & |H|<=|A|):", len(fails4))
for f in fails_exact[:10]:
    print("   FAIL:", f)
# sanity: witnesses also recorded per class sizes
classcnt = Counter(n for _, n, _ in low)
print("  low-doubling by size n:", dict(sorted(classcnt.items())))

# ---------------- (3) coset partition ----------------
print("\n=== (3) coset partition properties ===")
part_fails = []
for H in subs:
    reps = sorted({coset_min(x, H) for x in F})
    cosets = [coset_of(r, H) for r in reps]
    cs = [set(c) for c in cosets]
    ok = (len(H) == len(set(H))) and all(len(c) == len(H) for c in cosets)
    for i in range(len(cs)):
        for j in range(i + 1, len(cs)):
            if cs[i] & cs[j]: ok = False
    if set().union(*cs) != set(F): ok = False
    if len(reps) * len(H) != 8: ok = False
    if not ok: part_fails.append((H, reps, cosets))
    else:
        print(f"   H={H}: |H|={len(H)}, {len(reps)} cosets reps={reps}, sizes all {len(H)}, disjoint, union=F2^3 : OK")
print("  partition FAILs:", len(part_fails))

# ---------------- anchors ----------------
print("\n=== (3b) anchors ===")
def report(A):
    n = len(A); s = len(sumset(A)); K = s / n
    ceil2K = (2 * s + n - 1) // n
    cands = []
    for H in subs:
        if len(H) <= n:
            cands.append((cov_count(A, H), len(H), H))
    m = min(c[0] for c in cands)
    best = sorted({(c[0], c[1], tuple(c[2])) for c in cands if c[0] == m})
    print(f"  A={A}: |A|={n}, |A+A|={s}, K={s}/{n}={K:.4f}, ceil(2K)={ceil2K}, "
          f"min covCount over |H|<=|A| = {m}; optimal (c,|H|,H): {best[:6]}")

report([0,1,2,4])
report([0,1,2,3,4])
report([0,1,2,3])
# K=2 exact example search
k2 = [A for A, n, s in rows if n >= 2 and s == 2 * n]
print("  sets with K=2 exactly (|A+A|=2|A|):", k2[:8], " count:", len(k2))
# K=1 examples
k1 = [A for A, n, s in rows if n >= 1 and s == n]
print("  sets with K=1 (|A+A|=|A|, cosets of subgroups):", len(k1), "e.g.", k1[:6])
# H={0,1,2,3} decomposition
H = [0,1,2,3]
reps = sorted({coset_min(x, H) for x in F})
print("  H=[0,1,2,3] cosets:", [(r, coset_of(r, H)) for r in reps])
# max size of A+A and min
print("  |A+A| range over 256 subsets:", min(dist), "-", max(dist))

# ---------------- grand verdict ----------------
print("\n=== VERDICT ===")
allok = (len(fails_exact) == 0 and len(fails4) == 0 and len(part_fails) == 0 and len(subs) == 16)
print("subspaces found:", len(subs), "(expect 16 = 1+7+7+1; dim0:1 dim1:7 dim2:7 dim3:1)")
print("RESULT:", "ALL PASS (0 FAIL)" if allok else f"{len(fails_exact)} exact fails, {len(fails4)} c<=4 fails, {len(part_fails)} partition fails")
if not allok:
    sys.exit(1)

# ---------------- emit literals + write Lean file ----------------
def lit(A):
    return "[" + ",".join(str(x) for x in A) + "]"

allsub_lit = ",\n  ".join(lit(A) for A in allsub)
low_lit = ",\n  ".join(lit(A) for A in low_list)
sub_lit = ",\n  ".join(lit(S) for S in subs_sorted)
print("\nlowsets count (|A|>=2):", len(low_list), " allsubsets count:", len(allsub))

TEMPLATE = r'''/- pfr_cover_family.lean : exhaustive PFR covering-structure verification on G = F2^3.
Group elements 0..7 with addition xor3 (closed form via div/mod).  All 256 subsets A of
G are checked: whenever |A| >= 2 and |A+A| <= 2|A| (doubling K <= 2), there exists a
subspace H of G with |H| <= |A| such that A meets at most ceil(2K) ( <= 4 ) cosets of H.
Python pre-verified 0 FAIL (pfr_cover_check.py); numbers embedded here were generated by
that script.  Bare core: no imports, Nat literals, recursive Bool checkers, kernel decide.
-/
set_option maxRecDepth 200000

-- Bool equality / le on Nat (structural, no typeclass instances needed)
def beqN : Nat -> Nat -> Bool
  | 0, 0 => true
  | 0, _ + 1 => false
  | _ + 1, 0 => false
  | a + 1, b + 1 => beqN a b

def bleN (a b : Nat) : Bool :=
  match a with
  | 0 => true
  | a1 + 1 => match b with | 0 => false | b1 + 1 => bleN a1 b1

-- list membership / dedup / xor3 / pairwise sums (as in pfr_anchors.lean)
def memB (x : Nat) : List Nat -> Bool
  | [] => false
  | h :: t => if beqN h x then true else memB x t

def dedupB : List Nat -> List Nat
  | [] => []
  | h :: t => if memB h t then dedupB t else h :: dedupB t

def xor3 (a b : Nat) : Nat :=
  (((a / 1 + b / 1) % 2) * 1) + (((a / 2 + b / 2) % 2) * 2) + (((a / 4 + b / 4) % 2) * 4)

def ss (l1 l2 : List Nat) : List Nat :=
  match l1 with
  | [] => []
  | a :: rest => (List.map (fun b => xor3 a b) l2) ++ ss rest l2

-- coset of H through a = list of a xor h; canonical rep = minimal element (first of 0..7)
def cosetList (a : Nat) (H : List Nat) : List Nat := List.map (fun h => xor3 a h) H

def cosetMin (c : List Nat) : Nat :=
  if memB 0 c then 0 else if memB 1 c then 1 else if memB 2 c then 2 else
  if memB 3 c then 3 else if memB 4 c then 4 else if memB 5 c then 5 else
  if memB 6 c then 6 else 7

def rep (a : Nat) (H : List Nat) : Nat := cosetMin (cosetList a H)

def repsOf (A H : List Nat) : List Nat := dedupB (List.map (fun a => rep a H) A)

-- number of cosets of H met by A
def covCount (A H : List Nat) : Nat := (repsOf A H).length

-- subspace test: contains 0, distinct entries, closed under xor3 (pairwise)
-- allY2 x G: for every y in list arg, xor3 x y in the FIXED original list G
def allY2 (x : Nat) (G : List Nat) : List Nat -> Bool
  | [] => true
  | y :: ys => if memB (xor3 x y) G then allY2 x G ys else false

-- allX2 G L: for every x in L, every y in G satisfies xor3 x y in G  (call with allX2 H H)
def allX2 (G : List Nat) : List Nat -> Bool
  | [] => true
  | x :: xs => if allY2 x G G then allX2 G xs else false

def isSubspace (H : List Nat) : Bool :=
  memB 0 H && beqN (dedupB H).length H.length && allX2 H H

-- the 16 subspaces of F2^3 (dim 0 : 1, dim 1 : 7, dim 2 : 7, dim 3 : 1)
def subSpaces : List (List Nat) := [
@@SUBSPACES@@
]

-- doubling bound: ceil(2K) = (2*|A+A| + |A| - 1) / |A|  (K = |A+A|/|A|); <= 4 when K <= 2
def covBound (A : List Nat) : Nat := (2 * (dedupB (ss A A)).length + A.length - 1) / A.length

-- low-doubling predicate: |A| >= 2 and |A+A| <= 2*|A|
def lowDbl (A : List Nat) : Bool :=
  bleN 2 A.length && bleN (dedupB (ss A A)).length (2 * A.length)

-- good cover: |H| <= |A| and covCount(A,H) <= bnd
def goodH (A H : List Nat) (bnd : Nat) : Bool :=
  bleN H.length A.length && bleN (covCount A H) bnd

def orH (A : List Nat) (bnd : Nat) : List (List Nat) -> Bool
  | [] => false
  | H :: Hs => if goodH A H bnd then true else orH A bnd Hs

-- exists subspace H : |H| <= |A| and A covered by <= bnd cosets (bnd = covBound A = ceil(2K))
def existsGood (A : List Nat) : Bool := orH A (covBound A) subSpaces

-- simplified variant with constant bound 4 (valid since K <= 2 implies ceil(2K) <= 4)
def existsGood4 (A : List Nat) : Bool := orH A 4 subSpaces

-- full check over all 256 subsets: every low-doubling A is covered (exact ceil(2K) bound)
def chkAll : List (List Nat) -> Bool
  | [] => true
  | A :: rest => (if lowDbl A then existsGood A else true) && chkAll rest

def allB (f : List Nat -> Bool) : List (List Nat) -> Bool
  | [] => true
  | A :: rest => f A && allB f rest

def cntSub : List (List Nat) -> Nat
  | [] => 0
  | H :: Hs => if isSubspace H then 1 + cntSub Hs else cntSub Hs

-- coset partition check for one H: distinct cosets; every g in 0..7 lies in exactly one;
-- number-of-cosets * |H| = 8
def cntCos (g : Nat) : List Nat -> List Nat -> Nat
  | [], _ => 0
  | r :: rs, H => if memB g (cosetList r H) then 1 + cntCos g rs H else cntCos g rs H

def gsOk (H : List Nat) : Bool :=
  let reps := repsOf [0,1,2,3,4,5,6,7] H
  beqN (cntCos 0 reps H) 1 && beqN (cntCos 1 reps H) 1 && beqN (cntCos 2 reps H) 1 &&
  beqN (cntCos 3 reps H) 1 && beqN (cntCos 4 reps H) 1 && beqN (cntCos 5 reps H) 1 &&
  beqN (cntCos 6 reps H) 1 && beqN (cntCos 7 reps H) 1

def partChk (H : List Nat) : Bool :=
  gsOk H && beqN ((repsOf [0,1,2,3,4,5,6,7] H).length * H.length) 8

def allPart : List (List Nat) -> Bool
  | [] => true
  | H :: Hs => partChk H && allPart Hs

-- the 256 subsets of F2^3 (sorted ascending; literal list generated by python)
def allSubsets : List (List Nat) := [
@@ALLSUBSETS@@
]

-- the low-doubling subsets with |A| >= 2 (python-generated; sublist of allSubsets)
def lowSets : List (List Nat) := [
@@LOWSETS@@
]

-- ============ theorems (all kernel `by decide`) ============

-- every listed subspace is really a subspace (closure checked in kernel)
theorem t_subspaces_listed_ok : allB isSubspace subSpaces = true := by decide

-- among all 256 subsets exactly 16 are subspaces (so none is missing from subSpaces)
theorem t_all_subspaces_found : cntSub allSubsets = 16 := by decide

-- anchor sumsets: |A+A|
theorem sumset_anchor_A : (dedupB (ss [0,1,2,4] [0,1,2,4])).length = 7 := by decide
theorem sumset_anchor_B : (dedupB (ss [0,1,2,3,4] [0,1,2,3,4])).length = 8 := by decide
theorem sumset_subspace_K1 : (dedupB (ss [0,1,2,3] [0,1,2,3])).length = 4 := by decide

-- anchor covers: A = {0,1,2,4} (K=7/4) covered by H = {0,1,2,3} in 2 cosets, |H|=4 <= |A|=4
theorem cov_anchor_A : covCount [0,1,2,4] [0,1,2,3] = 2 := by decide
-- A = {0,1,2,3,4} (K=8/5) covered by H = {0,1,2,3} in 2 cosets, |H|=4 <= |A|=5
theorem cov_anchor_B : covCount [0,1,2,3,4] [0,1,2,3] = 2 := by decide
-- K = 1 example: A itself a subspace -> covered by 1 coset of A
theorem cov_subspace_K1 : covCount [0,1,2,3] [0,1,2,3] = 1 := by decide

-- coset decomposition of H = {0,1,2,3}: exactly 2 cosets (reps 0 and 4)
theorem coset_decomp_H0123_count : (repsOf [0,1,2,3,4,5,6,7] [0,1,2,3]).length = 2 := by decide

-- exact doubling bounds for the anchors: ceil(2*7/4) = 4, ceil(2*8/5) = 4
theorem bound_anchor_A : covBound [0,1,2,4] = 4 := by decide
theorem bound_anchor_B : covBound [0,1,2,3,4] = 4 := by decide

-- coset partition verified for all 16 subspaces
theorem t_partition_all_subspaces : allPart subSpaces = true := by decide

-- low-doubling list sanity: every listed set is low-doubling
theorem t_lowsets_lowdbl : allB lowDbl lowSets = true := by decide

-- simplified claim: every low-doubling A (|A|>=2) is covered by <= 4 cosets of some H, |H| <= |A|
theorem t_lowsets_covered_4 : allB existsGood4 lowSets = true := by decide

-- exact claim: every low-doubling A (|A|>=2) is covered by <= ceil(2K) cosets of some H, |H| <= |A|
theorem t_lowsets_covered_exact : allB existsGood lowSets = true := by decide

-- grand exhaustive theorem: for ALL 256 subsets, low-doubling implies the exact covering claim
theorem t_all_subsets_cover_exact : chkAll allSubsets = true := by decide
'''

lean = (TEMPLATE
        .replace("@@SUBSPACES@@", sub_lit)
        .replace("@@ALLSUBSETS@@", allsub_lit)
        .replace("@@LOWSETS@@", low_lit))

with open(r"C:\Users\Administrator\pfr_cover_family.lean", "w", encoding="ascii") as f:
    f.write(lean)
print("wrote pfr_cover_family.lean")
