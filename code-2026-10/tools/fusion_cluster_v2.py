"""三库融合聚类对比分析 v2
- 清洗文本（去 markdown/LaTeX/URL/符号）
- 领域口径：英文词 + 中文 2-gram 关键词匹配 → 分布对比（share + JS 散度），而不是只看「有没有」
- 无监督融合聚类：TF-IDF(word) → LSA150 → KMeans(k=16)，看簇内三库混合度
- 跨库最近邻对齐：每个条目在**另外两个库**里的最近邻距离 → 量化「研究有没有经验支撑 / 经验有没有研究支撑」
"""
import json, re, sqlite3, collections, datetime, pathlib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import Normalizer
from sklearn.neighbors import NearestNeighbors

ARCH = pathlib.Path('D:/hermes/analysis/PAPER_ARCHIVE_agent_memory_swarm_2026-10.md')
EXP_ROOT = pathlib.Path('D:/hermes/hermes-data/profiles/mybot/knowledge_base')
KB = 'D:/hermes/data/kb/hermes_kb.db'
OUT_MD = pathlib.Path('D:/hermes/analysis/FUSION_CLUSTER_REPORT_2026-10-19.md')
OUT_JSON = pathlib.Path('D:/hermes/analysis/fusion_cluster.json')

CJK = re.compile(r'[\u4e00-\u9fff]+')
WORD = re.compile(r'[a-z][a-z\-]{2,}')
NOISE = re.compile(r'(```.*?```|\$[^$]{0,80}\$|https?://\S+|[\*\|\#>~_`\[\]\(\)\{\}])', re.S)

def clean(s):
    s = NOISE.sub(' ', s)
    low = s.lower()
    words = WORD.findall(low)
    cjk = []
    for run in CJK.findall(low):
        cjk += [run[i:i + 2] for i in range(len(run) - 1)]
    return ' '.join(words + cjk)

# ---- 载入 ----
def load_papers():
    t = ARCH.read_text(encoding='utf-8', errors='replace')
    parts = re.split(r'(?m)^###\s+(\d+)\.\s*', t)
    out = []
    for i in range(1, len(parts) - 1, 2):
        num = int(parts[i]); body = parts[i + 1]
        title = body.split('\n', 1)[0].strip()
        out.append({'store': 'paper', 'id': '#%d' % num, 'title': title, 'raw': title + ' ' + body[:1500]})
    return out

def load_exp():
    out = []
    for p in sorted(EXP_ROOT.rglob('*')):
        if not p.is_file() or p.suffix.lower() not in ('.md', '.json', '.py', '.txt', '.mdx'):
            continue
        if p.name.startswith('memos_vec') or p.stat().st_size > 2_000_000:
            continue
        if re.search(r'(route_cache|daydream_|memos_vec|snap_before|snap_after|\.bak)', p.name):
            continue
        rel = p.relative_to(EXP_ROOT)
        dom = rel.parts[0] if len(rel.parts) > 1 else '(root)'
        try:
            txt = p.read_text(encoding='utf-8', errors='replace')[:1200]
        except Exception:
            continue
        out.append({'store': 'exp', 'id': str(rel), 'dom': dom,
                    'title': '%s/%s' % (dom, p.name), 'raw': dom + ' ' + p.stem + ' ' + txt})
    return out

def load_kb():
    c = sqlite3.connect('file:' + KB + '?mode=ro', uri=True)
    out = []
    for eid, etype, name, desc in c.execute('select id,entity_type,name,coalesce(description,"") from entities'):
        out.append({'store': 'kb', 'id': str(eid), 'etype': etype,
                    'title': '%s [%s]' % (name, etype), 'raw': '%s %s %s' % (name, etype, desc[:800])})
    return out

papers, exp, kb = load_papers(), load_exp(), load_kb()
items = papers + exp + kb
for it in items:
    it['clean'] = clean(it['raw'])
print('载入：论文 %d | 经验 %d | KB 实体 %d' % (len(papers), len(exp), len(kb)))

# ---- 领域口径（分布对比）----
DOMAINS = {
 '智能体/编排': ['agent', 'orchestrat', 'workflow', 'multi-agent', 'harness', 'tool use', '智能体', '编排', '工作流'],
 '记忆/上下文': ['memory', 'context window', 'embedding', 'episodic', 'forget', '记忆', '上下文', '遗忘'],
 'RAG/检索': ['rag', 'retriev', 'rerank', 'vector store', 'bm25', '检索', '召回', '重排'],
 '强化学习/后训练': ['reinforcement', 'rlhf', 'ppo', 'dpo', 'grpo', 'reward model', 'post-train', 'fine-tun', '强化', '奖励', '微调'],
 '评测/基准': ['benchmark', 'evaluation', 'ablation', 'leaderboard', 'metric', '评测', '基准', '消融'],
 '安全/攻击': ['attack', 'poison', 'jailbreak', 'injection', 'adversarial', 'exploit', 'vulnerab', 'cve', '攻击', '投毒', '越狱', '注入', '对抗', '漏洞'],
 '密码/脱敏': ['crypto', 'aes', 'rsa', 'sha256', 'desensitiz', 'redact', 'anonym', 'privacy', '加密', '脱敏', '隐私', '匿名'],
 '数学/证明': ['math', 'proof', 'lean', 'coq', 'theorem', 'formal verification', 'smt', '数学', '证明', '定理', '形式化'],
 '优化/运筹': ['optimiz', 'combinatorial', 'scheduling', 'integer program', 'heuristic', 'tsp', 'vrp', '优化', '组合', '调度', '启发式'],
 '时序/预测': ['time series', 'forecast', 'anomaly detection', 'wmpe', '时序', '预测', '趋势'],
 '视觉/图像': ['vision', 'image', 'detection', 'segmentation', 'visual', '视觉', '图像', '检测', '分割'],
 '生成模型/扩散': ['diffusion', 'gan', 'vae', 'flow matching', 'text-to-image', 'distill', '扩散', '生成模型', '蒸馏'],
 '多模态': ['multimodal', 'vlm', 'vision-language', '多模态', '图文'],
 '语音/声纹': ['speech', 'voice', 'asr', 'tts', 'audio', 'mfcc', 'speaker', '语音', '声纹', '说话人'],
 'OCR/图纸': ['ocr', 'drawing', 'cad', 'gdt', 'tolerance', 'engineering drawing', '图纸', '公差', '尺寸'],
 '工业/材料/锂电': ['lithium', 'battery', 'electrode', 'coating', 'oven', 'roller', 'material', 'sem', 'xrd', '锂电', '电池', '极片', '涂布', '烘箱', '辊', '材料'],
 '仿真/CAE': ['ansys', 'abaqus', 'comsol', 'simulation', 'cfd', 'fea', 'finite element', '仿真', '有限元', '热'],
 '科学ML/气候': ['climate', 'neutrino', 'protein', 'physics-informed', 'scientific machine', 'weather', '气候', '中微子', '科学计算'],
 '医疗/流行病': ['epidemi', 'virus', 'covid', 'influenza', 'clinical', 'medical', '流行病', '病毒', '流感', '临床', '医学'],
 '心理/情感': ['psycholog', 'emotion', 'empathy', 'wellbeing', '心理', '情感', '情绪', '共情'],
 '运维/网关': ['gateway', 'watchdog', 'cron', 'deploy', 'systemd', 'restart', '网关', '看门狗', '定时', '部署', '重启', '运维'],
 '知识库/聚类': ['knowledge base', 'cluster', 'taxonomy', 'librarian', 'archive', '知识库', '聚类', '分类', '归档'],
 '模型部署/推理': ['inference', 'quantiz', 'gguf', 'llama.cpp', 'vllm', 'ollama', 'serving', 'latency', 'vram', '推理', '量化', '显存', '部署'],
 'Token/成本': ['token', 'cost', 'pricing', 'compress', 'budget', '成本', '压缩', '预算'],
 '数据/爬虫': ['crawler', 'scrap', 'dataset', 'collect', 'rss', 'api', '爬虫', '抓取', '数据集', '采集'],
}

for it in items:
    low = ' ' + it['clean'] + ' '
    it['domains'] = [d for d, kws in DOMAINS.items() if any(k in low for k in kws)]

def dist(store):
    cnt = collections.Counter()
    for it in items:
        if it['store'] == store:
            for d in it['domains']:
                cnt[d] += 1
    tot = sum(cnt.values()) or 1
    return {d: cnt[d] / tot for d in DOMAINS}

D = {s: dist(s) for s in ('paper', 'exp', 'kb')}

def js(p, q):
    ks = list(DOMAINS)
    p = np.array([p[k] + 1e-9 for k in ks]); q = np.array([q[k] + 1e-9 for k in ks])
    p /= p.sum(); q /= q.sum(); m = (p + q) / 2
    return float(0.5 * (np.sum(p * np.log(p / m)) + np.sum(q * np.log(q / m))))

dom_rows = []
for d in DOMAINS:
    dom_rows.append({'domain': d, 'paper': round(D['paper'][d] * 100, 1),
                     'exp': round(D['exp'][d] * 100, 1), 'kb': round(D['kb'][d] * 100, 1)})
dom_rows.sort(key=lambda r: -(r['paper'] + r['exp'] + r['kb']))

# ---- 融合聚类 ----
vec = TfidfVectorizer(analyzer='word', token_pattern=r'\S+', min_df=4, max_df=0.55,
                      sublinear_tf=True, max_features=80000)
X = vec.fit_transform([it['clean'] for it in items])
svd = TruncatedSVD(n_components=150, random_state=0)
Z = Normalizer(copy=False).fit_transform(svd.fit_transform(X))
print('特征 %s → LSA %s' % (X.shape, Z.shape))

K = 16
km = KMeans(n_clusters=K, n_init=20, random_state=0).fit(Z)
lab = km.labels_
sil = float(silhouette_score(Z, lab, sample_size=min(2000, len(Z)), random_state=0))
print('K=%d silhouette=%.3f' % (K, sil))
terms = np.array(vec.get_feature_names_out())
scores = km.cluster_centers_.dot(svd.components_)

clusters = []
for k in range(K):
    idx = np.where(lab == k)[0]
    mix = collections.Counter(items[i]['store'] for i in idx)
    share = {s: round(mix[s] / max(1, len(idx)), 3) for s in ('paper', 'exp', 'kb')}
    top = [t for t in terms[np.argsort(scores[k])[::-1][:40]] if len(t) > 1][:10]
    clusters.append({'k': k, 'n': len(idx), 'mix': dict(mix), 'share': share, 'terms': top,
                     'samples': [items[i]['title'][:60] for i in idx[:3]]})
clusters.sort(key=lambda c: -c['n'])
cross = [c for c in clusters if sum(1 for s in c['share'] if c['share'][s] >= 0.12) >= 2]

# ---- 跨库最近邻对齐（全矩阵 cosine，避免 kNN 截断偏差）----
Zf = np.asarray(Z, dtype=np.float32)
Zf = Zf / np.maximum(np.linalg.norm(Zf, axis=1, keepdims=True), 1e-9)
IDX = {s: np.array([i for i, it in enumerate(items) if it['store'] == s]) for s in ('paper', 'exp', 'kb')}

def cross_stats(a, b):
    A, B = IDX[a], IDX[b]
    S = Zf[A] @ Zf[B].T                      # cosine 相似度
    Dm = 1.0 - S
    best = Dm.min(axis=1)
    j = Dm.argmin(axis=1)
    pairs = [(items[A[i]]['id'], items[B[jj]]['id'], float(best[i])) for i, jj in enumerate(j)]
    return pairs, best

pairs_pe, v_pe = cross_stats('paper', 'exp')
pairs_pk, v_pk = cross_stats('paper', 'kb')
pairs_ep, v_ep = cross_stats('exp', 'paper')
pairs_kp, v_kp = cross_stats('kb', 'paper')

def stat(v):
    a = np.asarray(v, dtype=float)
    if a.size == 0:
        return {}
    return {'n': int(a.size), 'median': round(float(np.median(a)), 3),
            'p10': round(float(np.percentile(a, 10)), 3),
            'p25': round(float(np.percentile(a, 25)), 3), 'p75': round(float(np.percentile(a, 75)), 3),
            'frac_lt_0.60': round(float((a < 0.60).mean()), 3),
            'frac_lt_0.75': round(float((a < 0.75).mean()), 3),
            'frac_gt_0.90': round(float((a > 0.90).mean()), 3)}

# 最孤立的样本（距离最大的前 5）
def worst(pairs, n=5):
    return [{'a': a, 'b': b, 'dist': round(d, 3)} for a, b, d in sorted(pairs, key=lambda x: -x[2])[:n]]

# ---- KB 滞后与连通性 ----
c = sqlite3.connect('file:' + KB + '?mode=ro', uri=True)
kb_paper = c.execute("select count(*) from entities where entity_type='Paper'").fetchone()[0]
kb_iron = c.execute("select count(*) from entities where entity_type='IronRule'").fetchone()[0]
# 概念连通：无向边（论文--DEFINES-->概念 也要算）
q = """with edges as (
  select source_id a, target_id b from relationships
  union all
  select target_id a, source_id b from relationships)
select sum(case when hp>0 and hr>0 then 1 else 0 end), sum(case when hp>0 and hr=0 then 1 else 0 end),
 sum(case when hp=0 and hr>0 then 1 else 0 end), sum(case when hp=0 and hr=0 then 1 else 0 end)
from (select e.id,
  sum(case when oe.entity_type='Paper' then 1 else 0 end) hp,
  sum(case when oe.entity_type in ('Tool','Skill','Command','Feature','Capability') then 1 else 0 end) hr
 from entities e left join edges x on x.a=e.id left join entities oe on oe.id=x.b
 where e.entity_type='Concept' group by e.id)"""
both, ponly, ronly, none_ = c.execute(q).fetchone()
# 归档条目是否已进 KB（按标题归一化前缀匹配）
def norm_title(s):
    s = re.sub(r'[^0-9a-z\u4e00-\u9fff]+', '', s.lower())
    return s[:42]
kb_names = collections.Counter()
kb_list = []
for (nm,) in c.execute("select name from entities where entity_type='Paper'"):
    kb_names[norm_title(nm)] += 1
    kb_list.append(norm_title(nm))
# 模糊标题匹配（前缀精确 0 命中 ⇒ 改 difflib，避免度量失效假报「0% 覆盖」）
from difflib import SequenceMatcher
def best_ratio(t):
    key = norm_title(t)
    best = 0.0
    for nm in kb_list:
        r = SequenceMatcher(None, key, nm).ratio()
        if r > best:
            best = r
            if best >= 0.95:
                break
    return best
ratios = [best_ratio(it['title']) for it in papers]
matched = sum(1 for r in ratios if r >= 0.80)
matched60 = sum(1 for r in ratios if r >= 0.60)
# KB 边类型三元组（看研究与实践在图里到底怎么连的）
edge_pairs = [(a, b, cc, n) for a, b, cc, n in c.execute("""
 select s.entity_type, r.rel_type, t.entity_type, count(*) n
 from relationships r join entities s on s.id=r.source_id join entities t on t.id=r.target_id
 group by 1,2,3 order by n desc limit 12""")]

rep = {'generated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
       'sizes': {'papers': len(papers), 'exp': len(exp), 'kb': len(kb)},
       'domain_dist_pct': dom_rows,
       'js_divergence': {'paper_exp': round(js(D['paper'], D['exp']), 4),
                         'paper_kb': round(js(D['paper'], D['kb']), 4),
                         'exp_kb': round(js(D['exp'], D['kb']), 4)},
       'clustering': {'k': K, 'silhouette': round(sil, 3), 'cross_clusters': len(cross), 'clusters': clusters},
       'alignment': {'paper_to_exp': stat(v_pe), 'paper_to_kb': stat(v_pk),
                     'exp_to_paper': stat(v_ep), 'kb_to_paper': stat(v_kp),
                     'worst_paper_exp': worst(pairs_pe), 'worst_exp_paper': worst(pairs_ep)},
       'kb_gap': {'archive': len(papers), 'kb_paper': kb_paper, 'kb_iron': kb_iron,
                  'matched_titles': matched, 'coverage_pct': round(100.0 * matched / max(1, len(papers)), 1),
                  'matched60': matched60, 'ratio_median': round(float(sorted(ratios)[len(ratios)//2]), 3),
                  'edge_pairs': [list(x) for x in edge_pairs],
                  'concept_both': both, 'concept_paper_only': ponly,
                  'concept_prac_only': ronly, 'concept_isolated': none_}}
OUT_JSON.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')

# ---- 报告 ----
L = ['# 论文库 / 经验库 / 知识库 —— 融合聚类对比分析', '',
     '生成：%s' % rep['generated_at'], '',
     '## 0. 规模', '',
     '| 库 | 条目 | 说明 |', '|:--|--:|:--|',
     '| 论文库 | %d | 主归档 PAPER_ARCHIVE（含铁律 145 条） |' % len(papers),
     '| 经验库 | %d | profiles/mybot/knowledge_base，44 个域目录（md/json/py） |' % len(exp),
     '| 知识库 | %d | hermes_kb.db 实体（关系 5655 条） |' % len(kb), '',
     '## 1. 领域分布（按库内占比 %，可多标）', '',
     '| 领域 | 论文% | 经验% | 知识库% |', '|:--|--:|--:|--:|']
for r in dom_rows:
    L.append('| %s | %.1f | %.1f | %.1f |' % (r['domain'], r['paper'], r['exp'], r['kb']))
L += ['', '### 分布差异（Jensen–Shannon 散度，越小越像；上界 ln2≈0.693）', '',
      '| 对比 | JS |', '|:--|--:|',
      '| 论文 × 经验 | %.4f |' % rep['js_divergence']['paper_exp'],
      '| 论文 × 知识库 | %.4f |' % rep['js_divergence']['paper_kb'],
      '| 经验 × 知识库 | %.4f |' % rep['js_divergence']['exp_kb'], '',
      '## 2. 融合聚类（K=%d，silhouette=%.3f；跨库簇 %d / %d）' % (K, sil, len(cross), K), '',
      '| 簇 | n | 论文% | 经验% | 知识库% | 主导词 | 判定 |', '|--:|--:|--:|--:|--:|:--|:--|']
for cl in clusters:
    sh = cl['share']
    kind = '跨库' if sum(1 for s in sh if sh[s] >= 0.12) >= 2 else '单库·' + max(sh, key=sh.get)
    L.append('| %d | %d | %.0f | %.0f | %.0f | %s | %s |' % (
        cl['k'], cl['n'], sh['paper'] * 100, sh['exp'] * 100, sh['kb'] * 100, ' '.join(cl['terms'][:7]), kind))
L += ['', '## 3. 跨库最近邻对齐（cosine 距离；越小=存在强对应物）', '',
      '| 方向 | 样本 | 中位数 | P10 | P25 | P75 | <0.60 | <0.75 | >0.90 |', '|:--|--:|--:|--:|--:|--:|--:|--:|--:|']
for key, label in [('paper_to_exp', '论文 → 经验'), ('paper_to_kb', '论文 → 知识库'),
                   ('exp_to_paper', '经验 → 论文'), ('kb_to_paper', '知识库 → 论文')]:
    s = rep['alignment'][key]
    L.append('| %s | %d | %s | %s | %s | %s | %s | %s | %s |' % (
        label, s['n'], s['median'], s['p10'], s['p25'], s['p75'],
        s['frac_lt_0.60'], s['frac_lt_0.75'], s['frac_gt_0.90']))
L += ['', '### 最孤立样本（距离最大，说明该条目在对应库里找不到对话者）', '']
for tag, label in [('worst_paper_exp', '论文在经验库里的最远者'), ('worst_exp_paper', '经验在论文库里的最远者')]:
    L.append('**%s**' % label)
    L.append('')
    L.append('| 条目 | 最近对应物 | 距离 |')
    L.append('|:--|:--|--:|')
    for w in rep['alignment'][tag]:
        L.append('| %s | %s | %.3f |' % (w['a'][:46], w['b'][:46], w['dist']))
    L.append('')
L += ['## 4. 知识库内部：Concept 的「研究—实践」连通（无向边口径）', '',
      '| 象限 | 数量 | 占比 |', '|:--|--:|--:|']
tot_c = max(1, kb.count if False else (both + ponly + ronly + none_))
for lbl, v in [('既连 Paper 又连实践件', both), ('只连 Paper（研究态）', ponly),
               ('只连实践件（经验态）', ronly), ('两不连（孤岛）', none_)]:
    L.append('| %s | %s | %.1f%% |' % (lbl, v, 100.0 * (v or 0) / tot_c))
L += ['', '## 5. 库间滞后（ingest 覆盖）', '',
      '- 论文库 %d 条 vs KB Paper 实体 %d 条' % (len(papers), kb_paper),
      '- 归档标题在 KB Paper 里**模糊匹配 ≥0.80**：**%d / %d = %.1f%%**；≥0.60 有 %d 条；相似度中位数 %.3f' % (
          matched, len(papers), rep['kb_gap']['coverage_pct'], matched60, rep['kb_gap']['ratio_median']),
      '- 论文库铁律 145 vs KB IronRule %d ⇒ 差 %d' % (kb_iron, 145 - kb_iron), '',
      '### 知识库关系结构（前 12 类三元组）', '',
      '| 源类型 | 关系 | 目标类型 | 条数 |', '|:--|:--|:--|--:|']
for a,b,cc,n in edge_pairs:
    L.append('| %s | %s | %s | %d |' % (a,b,cc,n))
L.append('')
OUT_MD.write_text('\n'.join(L), encoding='utf-8')

print('\n=== 领域占比（前 14，%）===')
for r in dom_rows[:14]:
    print('  %-14s 论文%5.1f 经验%5.1f KB%5.1f' % (r['domain'], r['paper'], r['exp'], r['kb']))
print('\nJS:', rep['js_divergence'])
print('\n=== 簇 ===')
for cl in clusters:
    sh = cl['share']
    print('  k%-2d n=%-4d P%3.0f E%3.0f K%3.0f | %s' % (cl['k'], cl['n'], sh['paper'] * 100,
          sh['exp'] * 100, sh['kb'] * 100, ' '.join(cl['terms'][:6])))
print('\n=== 对齐 ===')
for k2, v in rep['alignment'].items():
    print('  %-12s %s' % (k2, v))
print('\nKB gap:', rep['kb_gap'])
print('\n报告：', OUT_MD)
