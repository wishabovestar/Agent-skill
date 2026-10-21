import json, os, re, sys

BASE = r"D:/hermes/hermes-data/profiles/mybot/skills"
AGENTS = r"C:/Users/Administrator/.agents/skills"

def read_frontmatter(path):
    """Read SKILL.md frontmatter: return dict with name/description/tags."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            txt = f.read(4000)
    except Exception:
        return None
    m = re.match(r"^---\s*\n(.*?)\n---", txt, re.S)
    if not m:
        return None
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip().lower()] = v.strip().strip('"').strip("'")
    return fm

def collect_skills():
    """Return {name: {desc, tags, path, source}} for all skill dirs."""
    skills = {}
    # walk profile skills dir (skip dot dirs)
    for root, dirs, files in os.walk(BASE):
        parts = [p for p in root.split(os.sep) if p not in ("", ".")]
        if any(p.startswith(".") for p in parts):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            continue
        for d in list(dirs):
            if d.startswith("."):
                continue
            full = os.path.join(root, d)
            if os.path.islink(full):
                # resolve symlink target
                target = os.path.realpath(full)
                md = os.path.join(target, "SKILL.md")
                src = "matt-pocock" if target.startswith(AGENTS) else "symlink"
            else:
                md = os.path.join(full, "SKILL.md")
                src = "native"
            if not os.path.exists(md):
                continue
            fm = read_frontmatter(md)
            if not fm:
                continue
            name = fm.get("name") or d
            desc = fm.get("description") or ""
            tags = fm.get("tags") or ""
            # normalize tags list
            tagset = set()
            for t in re.split(r"[,\[\]]", tags):
                t = t.strip().strip('"').strip("'")
                if t and len(t) < 40:
                    tagset.add(t.lower())
            skills[name] = {"desc": desc, "tags": tagset, "path": full, "source": src}
    return skills

def tokenize(s):
    """Tokenize description into meaningful keywords."""
    toks = set()
    s = s.lower()
    # english words
    for w in re.findall(r"[a-z][a-z0-9\-]{2,}", s):
        if w not in ("the", "and", "for", "with", "hermes", "agent", "agents",
                     "skill", "skills", "that", "this", "from", "into", "using",
                     "use", "used", "can", "are", "was", "you", "your", "via",
                     "based", "including", "such", "their", "them", "these", "those"):
            toks.add(w)
    # chinese 2-4 char n-grams
    cn = re.findall(r"[\u4e00-\u9fff]{2,}", s)
    for seg in cn:
        if len(seg) == 2:
            toks.add(seg)
        else:
            for i in range(len(seg) - 1):
                toks.add(seg[i:i + 2])
            if len(seg) >= 3:
                toks.add(seg[:3])
    return toks

def main():
    skills = collect_skills()
    print(f"collected {len(skills)} skills with frontmatter")
    # sources
    from collections import Counter
    srcs = Counter(v["source"] for v in skills.values())
    print("sources:", dict(srcs))

    tokmap = {n: tokenize(v["desc"]) | set(v["tags"]) for n, v in skills.items()}
    names = list(skills.keys())
    # pairwise overlap (Jaccard) — report groups >= 0.6
    edges = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            ta, tb = tokmap[a], tokmap[b]
            if not ta or not tb:
                continue
            inter = ta & tb
            if not inter:
                continue
            jac = len(inter) / len(ta | tb)
            if jac >= 0.4:
                edges.append((jac, a, b, sorted(inter)[:8]))
    edges.sort(reverse=True)
    print(f"\npairs with Jaccard>=0.4: {len(edges)}")
    print("\n=== TOP OVERLAP PAIRS (>=0.5) ===")
    for jac, a, b, shared in edges:
        if jac >= 0.5:
            print(f"  {jac:.2f}  {a} <-> {b}  shared={shared}")

    # dump json for further analysis
    with open(r"D:/hermes/analysis/audit_overlap_edges.json", "w", encoding="utf-8") as f:
        json.dump([{"jaccard": j, "a": a, "b": b, "shared": s} for j, a, b, s in edges], f, ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
