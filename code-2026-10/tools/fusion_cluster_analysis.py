"""论文库 / 经验库 / 知识库 —— 融合聚类 + 对比分析
输出：D:/hermes/analysis/FUSION_CLUSTER_REPORT_2026-10-19.md + fusion_cluster.json
"""
import json, os, re, sqlite3, collections, datetime, pathlib

ARCH = pathlib.Path('D:/hermes/analysis/PAPER_ARCHIVE_agent_memory_swarm_2026-10.md')
EXP_ROOT = pathlib.Path('D:/hermes/hermes-data/profiles/mybot/knowledge_base')
KB = 'D:/hermes/data/kb/hermes_kb.db'
OUT_MD = pathlib.Path('D:/hermes/analysis/FUSION_CLUSTER_REPORT_2026-10-19.md')
OUT_JSON = pathlib.Path('D:/hermes/analysis/fusion_cluster.json')

# ---------------- 1. 载入三库 ----------------
def load_papers():
    t = ARCH.read_text(encoding='utf-8', errors='replace')
    parts = re.split(r'(?m)^###\s+(\d+)\.\s*', t)
    out = []
    for i in range(1, len(parts) - 1, 2):
        num = int(parts[i]); body = parts[i + 1]
        title = body.split('\n', 1)[0].strip()
        out.append({'store': 'paper', 'id': '#%d' % num, 'title': title,
                    'text': (title + ' ' + body[:1200])})
    return out

def load_exp():
    out = []
    for p in EXP_ROOT.rglob('*'):
        if not p.is_file():
            continue
        if p.suffix.lower() not in ('.md', '.json', '.py', '.txt', '.mdx'):
            continue
        if p.name.startswith('memos_vec') or p.stat().st_size > 3_000_000:
            continue
        rel = p.relative_to(EXP_ROOT)
        dom = rel.parts[0] if len(rel.parts) > 1 else '(root)'
        try:
            txt = p.read_text(encoding='utf-8', errors='replace')[:900]
        except Exception:
            continue
        out.append({'store': 'exp', 'id': str(rel), 'title': '%s / %s' % (dom, p.name),
                    'text': '%s %s %s' % (dom.replace('-', ' '), p.stem.replace('-', ' '), txt)})
    return out

def load_kb():
    c = sqlite3.connect('file:' + KB + '?mode=ro', uri=True)
    out = []
    for eid, etype, name, desc in c.execute('select id,entity_type,name,coalesce(description,"") from entities'):
        out.append({'store': 'kb', 'id': str(eid), 'etype': etype, 'title': '%s [%s]' % (name, etype),
                    'text': '%s %s %s' % (name, etype, desc[:600])})
    rel = c.execute('select count(*) from relationships').fetchone()[0]
    return out, rel

papers = load_papers()
exp = load_exp()
kb, kb_rels = load_kb()
allitems = papers + exp + kb
print('载入：论文 %d | 经验 %d | 知识库实体 %d | KB 关系 %d' % (len(papers), len(exp), len(kb), kb_rels))

# ---------------- 2. 领域词典（融合口径） ----------------
DOMAINS = {
 '智能体/编排': ['agent', '智能体', 'multi-agent', 'orchestrat', '编排', 'tool use', '工具调用', 'react', 'workflow', '工作流', 'subagent', 'harness', 'swarm', '群体'],
 '记忆/上下文': ['memory', '记忆', 'context window', '上下文', 'retrieval memory', 'forget', '遗忘', 'embedding', '向量', 'episodic', 'semantic memory'],
 'RAG/检索': ['rag', 'retriev', '检索', 'rerank', '重排', 'vector store', 'bm25', '召回', 'knowledge graph', '知识图谱'],
 '强化学习/后训练': ['reinforcement', '强化学习', 'rlhf', 'ppo', 'dpo', 'grpo', 'reward', '奖励', 'policy gradient', 'post-train', '后训练', 'fine-tun', '微调'],
 '评测/基准': ['benchmark', '基准', 'evaluat', '评测', 'eval', 'ablation', '消融', 'score', 'leaderboard', '协议', 'metric'],
 '安全/攻击': ['attack', '攻击', 'poison', '投毒', 'jailbreak', '越狱', 'injection', '注入', 'adversarial', '对抗', 'exploit', '渗透', '漏洞', 'vulnerab', 'cve', 'security', '安全'],
 '密码/脱敏': ['crypto', '加密', 'aes', 'rsa', 'sha256', '脱敏', 'desensitiz', 'redact', 'privacy', '隐私', '匿名'],
 '数学/证明': ['math', '数学', 'proof', '证明', 'lean', 'coq', 'isabelle', 'theorem', '定理', 'formal', '形式化', 'sat/smt', 'smt'],
 '优化/运筹': ['optimiz', '优化', 'combinatorial', '组合优化', 'scheduling', '调度', 'integer program', 'lp', '启发式', 'heuristic', 'tsp', 'vrp'],
 '时序/预测': ['time series', '时序', 'forecast', '预测', 'lstm', 'transformer forecast', 'anomaly detection', '趋势', 'wmpe', 'mse'],
 '视觉/图像': ['vision', '视觉', 'image', '图像', 'detection', '检测', 'segmentation', '分割', 'diffusion image', 'visual', '像素'],
 '生成模型/扩散': ['diffusion', '扩散', 'gan', 'vae', 'flow matching', '生成模型', 'text-to-image', '蒸馏', 'distill'],
 '多模态': ['multimodal', '多模态', 'vlm', 'vision-language', 'vl model', '图文', 'audio-visual'],
 '语音/声纹': ['speech', '语音', 'voice', '声纹', 'asr', 'tts', 'audio', '音频', 'mfcc', '说话人'],
 'OCR/图纸': ['ocr', '图纸', 'drawing', 'cad', 'gdt', '公差', 'tolerance', '尺寸', '扫描件', 'engineering drawing'],
 '工业/材料/锂电': ['lithium', '锂电', '电池', 'battery', '极片', 'electrode', '涂布', 'coating', '烘箱', 'oven', '辊', 'roller', '材料', 'material', 'sem', 'xrd', 'spectro'],
 '仿真/CAE': ['ansys', 'abaqus', 'comsol', 'simulation', '仿真', 'cfd', 'fea', 'finite element', '有限元', 'maxwell', 'thermal', '热'],
 '科学ML/气候': ['climate', '气候', 'neutrino', '中微子', 'protein', 'physics-informed', 'scientific machine', '科学计算', 'weather', '气象'],
 '医疗/流行病': ['epidemi', '流行病', 'virus', '病毒', 'covid', 'influenza', '流感', 'clinical', '临床', '医学', 'medical'],
 '心理/情感': ['psycholog', '心理', 'emotion', '情感', '情绪', 'empathy', '共情', 'wellbeing'],
 '运维/网关': ['gateway', '网关', 'watchdog', '看门狗', 'cron', '定时', 'deploy', '部署', 'systemd', 'ops', '运维', 'restart', '重启'],
 '知识库/聚类': ['knowledge base', '知识库', 'cluster', '聚类', 'taxonomy', '分类', 'embedding cluster', 'librarian', '归档', 'archive'],
 '模型部署/推理': ['inference', '推理', 'quantiz', '量化', 'gguf', 'llama.cpp', 'vllm', 'ollama', 'serving', 'latency', '显存', 'vram'],
 'Token/成本': ['token', '成本', 'cost', 'price', 'pricing', 'compress', '压缩', 'budget', '预算', 'context compress'],
 '数据/爬虫': ['crawler', '爬虫', 'scrap', '抓取', 'dataset', '数据集', 'collect', '采集', 'rss', 'api'],
}

def dom_of(text):
    low = text.lower()
    hits = []
    for d, kws in DOMAINS.items():
        for k in kws:
            if k in low:
                hits.append(d); break
    return hits

for it in allitems:
    it['domains'] = dom_of(it['text'])

# ---------------- 3. 领域 × 库 覆盖矩阵 ----------------
stores = ['paper', 'exp', 'kb']
cov = collections.defaultdict(lambda: collections.Counter())
for it in allitems:
    for d in it['domains']:
        cov[d][it['store']] += 1

rows = []
for d in DOMAINS:
    c = cov[d]
    rows.append({'domain': d, 'paper': c['paper'], 'exp': c['exp'], 'kb': c['kb'],
                 'stores': sum(1 for s in stores if c[s] > 0)})
rows.sort(key=lambda r: (-r['stores'], -(r['paper'] + r['exp'] + r['kb'])))

def jac(a, b):
    A = {i for i, it in enumerate(allitems) if it['store'] == a}
    B = {i for i, it in enumerate(allitems) if it['store'] == b}
    return None

def domain_set(s):
    return {it['domains'][0] for it in allitems if it['store'] == s and it['domains']}

def jset(a, b):
    A, B = domain_set(a), domain_set(b)
    return len(A & B) / max(1, len(A | B)), len(A & B), len(A), len(B)

jac_pe, ipe, ape, bpe = jset('paper', 'exp')
jac_pk, ipk, apk, bpk = jset('paper', 'kb')
jac_ek, iek, aek, bek = jset('exp', 'kb')

# ---------------- 4. 联合聚类（融合） ----------------
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import Normalizer
import numpy as np

docs = [it['text'] for it in allitems]
vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 3), min_df=3, max_features=120000,
                      sublinear_tf=True)
X = vec.fit_transform(docs)
svd = TruncatedSVD(n_components=120, random_state=0)
Z = Normalizer(copy=False).fit_transform(svd.fit_transform(X))
print('TF-IDF 矩阵 %s → SVD %s' % (X.shape, Z.shape))

K = 14
km = KMeans(n_clusters=K, n_init=10, random_state=0).fit(Z)
lab = km.labels_
sil = silhouette_score(Z, lab, sample_size=min(1500, len(Z)), random_state=0)
print('K=%d silhouette=%.3f' % (K, sil))

terms = np.array(vec.get_feature_names_out())
# 簇中心在 SVD 空间（K×120）；映射回词表空间以取主导词：w @ components_
scores = km.cluster_centers_.dot(svd.components_)
clusters = []
for k in range(K):
    idx = np.where(lab == k)[0]
    mix = collections.Counter(allitems[i]['store'] for i in idx)
    top = terms[np.argsort(scores[k])[::-1][:24]]
    clusters.append({'k': k, 'n': len(idx), 'mix': dict(mix),
                     'terms': [t for t in top if len(t) > 1][:10],
                     'share': {s: round(mix[s] / max(1, len(idx)), 2) for s in stores},
                     'samples': [allitems[i]['title'][:70] for i in idx[:3]]})
clusters.sort(key=lambda c: -c['n'])

cross = [c for c in clusters if sum(1 for s in stores if c['share'][s] >= 0.10) >= 2]
solo = [c for c in clusters if c not in cross]

# ---------------- 5. KB 覆盖缺口：Paper 实体 vs 归档条目 ----------------
c = sqlite3.connect('file:' + KB + '?mode=ro', uri=True)
kb_papers = [r[0] for r in c.execute("select name from entities where entity_type='Paper'")]
kb_irons = c.execute("select count(*) from entities where entity_type='IronRule'").fetchone()[0]
kb_tools = c.execute("select count(*) from entities where entity_type='Tool'").fetchone()[0]
kb_skills = c.execute("select count(*) from entities where entity_type='Skill'").fetchone()[0]
arch_n = len(papers)

# 知识→实践 连通性：Concept 同时连 Paper 与 Tool/Skill
q = """
select
  sum(case when has_paper>0 and has_prac>0 then 1 else 0 end) as both,
  sum(case when has_paper>0 and has_prac=0 then 1 else 0 end) as paper_only,
  sum(case when has_paper=0 and has_prac>0 then 1 else 0 end) as prac_only,
  sum(case when has_paper=0 and has_prac=0 then 1 else 0 end) as none_
from (
 select e.id,
   sum(case when oe.entity_type='Paper' then 1 else 0 end) has_paper,
   sum(case when oe.entity_type in ('Tool','Skill','Command','Feature') then 1 else 0 end) has_prac
 from entities e
 left join relationships r on r.source_id=e.id
 left join entities oe on oe.id=r.target_id
 where e.entity_type='Concept' group by e.id)
"""
both, ponly, pronly, none_ = c.execute(q).fetchone()

rep = {
    'generated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'stores': {'papers': len(papers), 'exp_files': len(exp), 'kb_entities': len(kb), 'kb_rels': kb_rels},
    'kb_types': dict(collections.Counter(it['etype'] for it in kb)),
    'domain_matrix': rows,
    'domain_jaccard': {'paper_exp': [round(jac_pe, 3), ipe, ape, bpe],
                       'paper_kb': [round(jac_pk, 3), ipk, apk, bpk],
                       'exp_kb': [round(jac_ek, 3), iek, aek, bek]},
    'clustering': {'k': K, 'silhouette': round(float(sil), 3), 'cross_store_clusters': len(cross),
                   'solo_clusters': len(solo), 'clusters': clusters},
    'kb_gap': {'archive_entries': arch_n, 'kb_paper_entities': len(kb_papers),
               'kb_ironrule': kb_irons, 'tok_both': both, 'tok_paper_only': ponly,
               'tok_prac_only': pronly, 'tok_none': none_},
}
OUT_JSON.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')

# ---------------- 6. Markdown 报告 ----------------
L = []
L.append('# 论文库 / 经验库 / 知识库 —— 融合聚类对比分析')
L.append('')
L.append('生成时间：%s' % rep['generated_at'])
L.append('')
L.append('## 0. 三库规模')
L.append('')
L.append('| 库 | 实体数 | 说明 |')
L.append('|:--|--:|:--|')
L.append('| 论文库 | %d 条 | PAPER_ARCHIVE（含铁律 %d 条） |' % (len(papers), 145))
L.append('| 经验库 | %d 个文件 / 44 域 | profiles/mybot/knowledge_base（md/json/py） |' % len(exp))
L.append('| 知识库 | %d 实体 / %d 关系 | hermes_kb.db，类型：%s |' % (
    len(kb), kb_rels, ', '.join('%s=%d' % (k, v) for k, v in collections.Counter(it['etype'] for it in kb).most_common(6))))
L.append('')
L.append('## 1. 领域 × 库 覆盖矩阵（按三库齐 → 两库 → 单库排序）')
L.append('')
L.append('| 领域 | 论文 | 经验 | 知识库 | 覆盖库数 |')
L.append('|:--|--:|--:|--:|:--:|')
for r in rows:
    L.append('| %s | %d | %d | %d | %d |' % (r['domain'], r['paper'], r['exp'], r['kb'], r['stores']))
L.append('')
L.append('### 领域集合 Jaccard（只看两库各自出现过的领域集合）')
L.append('')
L.append('| 对比 | Jaccard | 交集数 | A 领域数 | B 领域数 |')
L.append('|:--|--:|--:|--:|--:|')
L.append('| 论文 × 经验 | %.3f | %d | %d | %d |' % (jac_pe, ipe, ape, bpe))
L.append('| 论文 × 知识库 | %.3f | %d | %d | %d |' % (jac_pk, ipk, apk, bpk))
L.append('| 经验 × 知识库 | %.3f | %d | %d | %d |' % (jac_ek, iek, aek, bek))
L.append('')
L.append('## 2. 融合聚类（char 2-3gram TF-IDF → SVD120 → KMeans k=%d，silhouette=%.3f）' % (K, sil))
L.append('')
L.append('跨库簇 %d 个，单库簇 %d 个。' % (len(cross), len(solo)))
L.append('')
L.append('| 簇 | 规模 | 论文 | 经验 | 知识库 | 主导词 | 判定 |')
L.append('|--:|--:|--:|--:|--:|:--|:--|')
for cl in clusters:
    sh = cl['share']
    kind = '跨库' if sum(1 for s in stores if sh[s] >= 0.10) >= 2 else '单库(%s)' % max(sh, key=sh.get)
    L.append('| %d | %d | %.0f%% | %.0f%% | %.0f%% | %s | %s |' % (
        cl['k'], cl['n'], sh['paper'] * 100, sh['exp'] * 100, sh['kb'] * 100,
        ' '.join(cl['terms'][:6]), kind))
L.append('')
L.append('## 3. 知识库内部：知识→实践连通性')
L.append('')
L.append('Concept 实体按「是否连到 Paper」×「是否连到 Tool/Skill/Command/Feature」四象限：')
L.append('')
L.append('| 象限 | 数量 |')
L.append('|:--|--:|')
L.append('| 既连论文又连实践（真正打通） | %s |' % both)
L.append('| 只连论文（研究态） | %s |' % ponly)
L.append('| 只连实践（经验态） | %s |' % pronly)
L.append('| 两不连（孤岛） | %s |' % none_)
L.append('')
L.append('## 4. 库间滞后')
L.append('')
L.append('- 论文库 %d 条 vs 知识库 Paper 实体 %d 条（差 %d）' % (arch_n, len(kb_papers), arch_n - len(kb_papers)))
L.append('- 论文库铁律 145 条 vs 知识库 IronRule %d 条（差 %d）' % (kb_irons, 145 - kb_irons))
L.append('')
OUT_MD.write_text('\n'.join(L), encoding='utf-8')

print('\n=== 领域覆盖（前 12） ===')
for r in rows[:12]:
    print('  %-14s 论文%4d 经验%4d KB%4d 库数%d' % (r['domain'], r['paper'], r['exp'], r['kb'], r['stores']))
print('\n=== Jaccard ===', rep['domain_jaccard'])
print('=== 簇 ===')
for cl in clusters:
    print('  k%-2d n=%-4d paper %.0f%% exp %.0f%% kb %.0f%% | %s' % (
        cl['k'], cl['n'], cl['share']['paper'] * 100, cl['share']['exp'] * 100, cl['share']['kb'] * 100,
        ' '.join(cl['terms'][:6])))
print('\n报告：', OUT_MD)
