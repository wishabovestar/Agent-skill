"""
E-hentai 智能收藏 v3
特征: 马尔可夫链预测 + 多因子评分 + 每周一次
"""
import re, urllib.request, urllib.parse, json, time, sys
from pathlib import Path
from collections import Counter

PROXY = "socks5://127.0.0.1:10808"

# VPS中转抓取 — e-hentai被GFW阻断时, 经海外VPS绕过 (2026-08-06修复)
VPS_SSH = r"D:/hermes/analysis/vps_ssh.py"
def vps_fetch(url, timeout=30, post_data=None):
    import subprocess
    method = "--data " + repr(post_data.decode()) if post_data else ""
    cmd = [sys.executable, VPS_SSH, "exec",
           "curl -s --max-time %d %s -H 'User-Agent: Mozilla/5.0' -H 'Cookie: %s' '%s'" % (timeout, method, COOKIE, url)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 15)
        return r.stdout
    except Exception:
        return ""
with open("D:/hermes/data/credentials/ehentai_credentials.json") as f:
    EH = json.load(f)
COOKIE = f"ipb_member_id={EH['ipb_member_id']}; ipb_pass_hash={EH['ipb_pass_hash']}; igneous={EH['igneous']}"
BASE = "https://e-hentai.org"

EXCLUDE = {"non-h","yaoi","futanari","trap","reverse+rape","ai+generate","no+insertion","misc","western","shemale","crossdressing"}
BONUS = {"slave","toy","ahegao","bdsm","corruption","mind+control","mind+break","public+use","humiliation","degradation","bondage","training","pet+play","exhibitionism"}

def get(url):
    p = urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY})
    o = urllib.request.build_opener(p)
    r = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Cookie': COOKIE})
    try:
        with o.open(r, timeout=20) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception:
        return vps_fetch(url)

def add_fav(gid, token):
    url = f"{BASE}/gallerypopups.php?gid={gid}&t={token}&act=addfav"
    p = urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY})
    o = urllib.request.build_opener(p)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Cookie': COOKIE})
    try:
        o.open(req, timeout=15)
    except Exception:
        vps_fetch(url)
    data = urllib.parse.urlencode({'favcat':'0','apply':'Apply Changes','update':'1'}).encode()
    req2 = urllib.request.Request(url, data=data, headers={'User-Agent':'Mozilla/5.0','Cookie':COOKIE,'Content-Type':'application/x-www-form-urlencoded'})
    try:
        resp = o.open(req2, timeout=15)
        body = resp.read().decode('utf-8', errors='replace').lower()
        return "already" in body or "added" in body
    except Exception:
        body = vps_fetch(url, post_data=data).lower()
        return "already" in body or "added" in body

# ── 马尔可夫链预测 ──
class MarkovPredictor:
    def __init__(self):
        self.transitions = {}  # tagA -> {tagB: count}
        self.total = 0
    
    def learn(self, tags):
        """从标签序列学习转移概率"""
        for i in range(len(tags)-1):
            a, b = tags[i], tags[i+1]
            if a not in self.transitions:
                self.transitions[a] = Counter()
            self.transitions[a][b] += 1
            self.total += 1
    
    def predict_score(self, tags):
        """基于马尔可夫链评估标签一致性和自然度"""
        if self.total == 0: return 5  # 默认分
        score = 0
        for i in range(len(tags)-1):
            a, b = tags[i], tags[i+1]
            if a in self.transitions and b in self.transitions[a]:
                prob = self.transitions[a][b] / sum(self.transitions[a].values())
                score += prob * 10  # 高转移概率=高匹配
            else:
                score -= 2  # 未见过的转移=扣分
        return max(0, min(10, score))

markov = MarkovPredictor()

# ── Step 1: 分析已收藏 + 训练马尔可夫链 ──
print("=== Step 1: 分析收藏 + 训练马尔可夫链 ===")
fav_gids = set()
fav_data = []  # {gid, token, tags, rating, artist, popularity}

for p in range(3):
    html = get(f"{BASE}/favorites.php?page={p}")
    gts = re.findall(rf'{BASE}/g/(\d+)/([a-f0-9]+)/', html)
    for gid, tok in gts:
        fav_gids.add(gid)

# Sample first 20 to train Markov chain
sampled = 0
for gid, tok in list(gts)[:20]:
    try:
        gh = get(f"{BASE}/g/{gid}/{tok}/")
        tags = [urllib.parse.unquote(t).lower() for t in re.findall(r'href="https://e-hentai\.org/tag/([^"]+)"', gh)]
        rm = re.search(r'avg_rating[^>]*>\s*([\d.]+)', gh)
        rating = float(rm.group(1)) if rm else 0
        title = re.search(r'id="gn"[^>]*>(.*?)</h1>', gh)
        artists = [t.split(':')[1] if ':' in t else t for t in tags if t.startswith('artist:')]
        fav_data.append({'gid': gid, 'rating': rating, 'artists': artists, 'tags': tags, 'title': title.group(1).strip()[:50] if title else '?'})
        markov.learn(tags)
        sampled += 1
    except: pass
    time.sleep(1.5)

print(f"已收藏: {len(fav_gids)}, 训练样本: {sampled}, 转移矩阵: {sum(len(v) for v in markov.transitions.values())} 条")

# ── Step 2: 规律总结 ──
print("\n=== Step 2: 收藏规律总结 ===")
all_tags = Counter()
all_artists = set()
all_ratings = []
for d in fav_data:
    all_tags.update(d['tags'])
    all_artists.update(d['artists'])
    all_ratings.append(d['rating'])

print(f"  平均评分: ⭐{sum(all_ratings)/len(all_ratings):.2f}" if all_ratings else "评分不足")
print(f"  高频标签: {[t for t,_ in all_tags.most_common(20) if ':' in t][:10]}")
print(f"  艺术家: {list(all_artists)[:8]}")
print(f"  正向标签出现在收藏中的频次:")
bonus_in_fav = sum(1 for t in all_tags if any(b in t for b in BONUS))
print(f"   {bonus_in_fav}/{len(list(all_tags))} 标签包含正向词")

# ── Step 3: 搜索候选 ──
print("\n=== Step 3: 搜索候选 ===")
candidates = []

# 3a: 关注作者新作
for artist in list(all_artists)[:4]:
    try:
        html = get(f"{BASE}/?{urllib.parse.urlencode({'q': f'artist:{artist}', 'f_cats': '1023'})}")
        gts = re.findall(rf'{BASE}/g/(\d+)/([a-f0-9]+)/', html)
        titles = re.findall(r'<div class="glink">(.*?)</div>', html)
        for i in range(min(10, len(gts), len(titles))):
            gid, tok = gts[i]
            if gid not in fav_gids:
                candidates.append({'gid':gid,'tok':tok,'title':titles[i].strip()[:50],'src':f'author:{artist}','priority':1})
    except: pass
    time.sleep(1.5)

# 3b: 中文+正向标签搜索
for bt in ['language:chinese']:
    try:
        html = get(f"{BASE}/?{urllib.parse.urlencode({'q': bt, 'f_cats': '1023'})}")
        gts = re.findall(rf'{BASE}/g/(\d+)/([a-f0-9]+)/', html)
        titles = re.findall(r'<div class="glink">(.*?)</div>', html)
        for i in range(min(30, len(gts), len(titles))):
            gid, tok = gts[i]
            if gid not in fav_gids:
                candidates.append({'gid':gid,'tok':tok,'title':titles[i].strip()[:50],'src':'chinese','priority':2})
    except: pass
    time.sleep(1.5)

# 3c: 正向标签搜索
for bt in list(BONUS)[:6]:
    try:
        html = get(f"{BASE}/?{urllib.parse.urlencode({'q': bt, 'f_cats': '1023'})}")
        gts = re.findall(rf'{BASE}/g/(\d+)/([a-f0-9]+)/', html)
        titles = re.findall(r'<div class="glink">(.*?)</div>', html)
        for i in range(min(10, len(gts), len(titles))):
            gid, tok = gts[i]
            if gid not in fav_gids:
                candidates.append({'gid':gid,'tok':tok,'title':titles[i].strip()[:50],'src':bt,'priority':3})
    except: pass
    time.sleep(1.5)

# 去重
seen = set(); uniq = []
for c in candidates:
    if c['gid'] not in seen:
        seen.add(c['gid']); uniq.append(c)
print(f"候选: {len(uniq)}")

# ── Step 4: 多因子评分 ──
print("\n=== Step 4: 评分 + 马尔可夫预测 ===")
scored = []
for c in uniq[:25]:
    try:
        gh = get(f"{BASE}/g/{c['gid']}/{c['tok']}/")
        tags = [urllib.parse.unquote(t).lower() for t in re.findall(r'href="https://e-hentai\.org/tag/([^"]+)"', gh)]
        if not tags: continue
        
        # Rating
        rm = re.search(r'avg_rating[^>]*>\s*([\d.]+)', gh)
        rating = float(rm.group(1)) if rm else 0
        
        # 必须条件：中文 + 无负面
        if not any('chinese' in t for t in tags): continue
        if any(ex in ' '.join(tags) for ex in EXCLUDE): continue
        
        # 多因子评分
        rating_score = max(0, (rating - 3.0) * 5)      # ⭐: 3→0, 4→5, 5→10
        bonus_cnt = sum(1 for t in tags if any(b in t for b in BONUS))
        bonus_score = bonus_cnt * 3                     # 正向标签: 每个+3
        chinese_score = 5                                # 中文: +5
        markov_score = markov.predict_score(tags)        # 马尔可夫: 0-10
        popularity = 0
        # 热度: 搜索页面排名靠前加分
        if len(candidates) > 0 and c in candidates[:10]:
            popularity = 8 - candidates.index(c) if c in candidates else 0
        
        total = rating_score + bonus_score + chinese_score + markov_score + popularity
        scored.append({'gid':c['gid'],'tok':c['tok'],'title':c['title'],'total':total,
                       'rating':rating, 'bonus':bonus_cnt, 'markov':markov_score, 'src':c['src']})
    except: pass
    time.sleep(1.5)

scored.sort(key=lambda x:-x['total'])
print(f"通过筛选: {len(scored)}")
for s in scored[:5]:
    print(f"  ⭐{s['rating']}马尔可夫:{s['markov']:.1f}分 | 总分{s['total']:.1f} | {s['title'][:45]}")

# ── Step 5: 收藏 ──
print("\n=== Step 5: 收藏 ===")
added = 0
for s in scored[:8]:
    if add_fav(s['gid'], s['tok']):
        print(f"  ✅ 总分{s['total']:.1f}: {s['title'][:40]}")
        added += 1
    time.sleep(3)

print(f"\n━━━ 周度收藏完成 ━━━")
print(f"新增: {added}")
print(f"下次执行: 7天后 (2026-07-25)")
print(f"规律: 马尔可夫链已更新 ({sampled}条训练记录 → {sum(len(v) for v in markov.transitions.values())}条转移)")
