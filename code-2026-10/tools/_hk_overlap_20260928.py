# -*- coding: utf-8 -*-
import os, re, json
from collections import Counter, defaultdict
SKILLS = r"D:\hermes\hermes-data\profiles\mybot\skills"
def rd(p):
    try: return open(p, encoding="utf-8").read()
    except Exception: return ""
def fm(text):
    name=desc=None
    mm=re.search(r"^---\s*\n(.*?)\n---", text, re.S)
    if mm:
        b=mm.group(1)
        n=re.search(r"^name:\s*(.+)$",b,re.M); dd=re.search(r"^description:\s*(.+)$",b,re.M)
        if n: name=n.group(1).strip().strip('"\'')
        if dd: desc=dd.group(1).strip().strip('"\'')
    return name,desc
files=[]
for root,dirs,fs in os.walk(SKILLS):
    if ".archive" in root.split(os.sep): continue
    if "SKILL.md" in fs: files.append(os.path.join(root,"SKILL.md"))
recs=[]
for f in files:
    n,dd=fm(rd(f))
    if n: recs.append((n, dd or "", f))
print("skills with name:", len(recs))
def toks(s):
    s=s.lower()
    return set(re.findall(r"[a-z0-9]{3,}|[\u4e00-\u9fff]{2,}", s))
# pairwise overlap >0.4 on name+desc tokens
pairs=[]
for i in range(len(recs)):
    for j in range(i+1,len(recs)):
        a=toks(recs[i][0]+" "+recs[i][1]); b=toks(recs[j][0]+" "+recs[j][1])
        if not a or not b: continue
        jc=len(a&b)/len(a|b)
        if jc>=0.35:
            pairs.append((jc, recs[i][0], recs[j][0]))
pairs.sort(reverse=True)
print("name+desc token-overlap pairs (Jaccard>=0.35):", len(pairs))
for jc,n1,n2 in pairs[:40]:
    print("  %.2f  %-32s <-> %s" % (jc, n1, n2))
# family clustering by leading word
fam=defaultdict(list)
for n,_,_ in recs:
    fam[n.split("-")[0]].append(n)
print()
print("families (>=3 share prefix):")
for k,v in sorted(fam.items(), key=lambda x:-len(x[1])):
    if len(v)>=3: print("  %-16s x%d  %s" % (k,len(v),v[:12]))
