import re
card = open('_cards/forget_pair.md', encoding='utf-8').read()
i1 = card.index('## 篇一'); i2 = card.index('## 篇二'); i3 = card.index('## 两篇的判据')
a = card[i1:i2]; b = card[i2:i3]
ta = open('_p1_2610.21405.txt', encoding='utf-8').read()
tb = open('_p1_2610.18052.txt', encoding='utf-8').read()
def norm(s):
    return s.replace('\u00a0',' ')
def check(sec, txt, name):
    toks = re.findall(r'\d[\d,]*\.?\d*%?', sec)
    miss = []
    for t in toks:
        raw = t.rstrip('%')
        cands = {raw, raw.replace(',', ''), raw.replace(',', ',')}
        if not any(c in txt for c in cands):
            miss.append(t)
    print(name, 'tokens', len(toks), 'missing', sorted(set(miss)))
check(a, ta, 'MemCut')
check(b, tb, 'Bemula')
