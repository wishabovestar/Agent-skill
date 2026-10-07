#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
matseek_pipeline.py -- MatSeek-style structured processing of the Hermes 知识库.

Method (adapted from MatSeek, ICLR 2026: "unifies structured data extraction with
literature-derived relational knowledge mining"):

  [1] STRUCTURED EXTRACTION  -> one normalized record per document
  [2] RELATIONAL KNOWLEDGE   -> (head, relation, tail) triples with evidence spans

This build uses OFFLINE HEURISTICS ONLY (PyMuPDF + regex + lexicons). Zero LLM calls.
Every extracted knowledge field carries its provenance section + a confidence value.
Fields the document does not state are recorded as "not_stated" -- never invented.

Corpora (all three, per user):
  A. full-text PDFs           D:\\hermes\\data\\papers
  B. abstract-level JSON      hermes-data\\shared\\knowledge_base, data\\{math,physics,book}_knowledge
  C. GitHub scout JSON        data\\agent_knowledge            (typed as repo, not paper)

Outputs (D:\\hermes\\data\\matseek):
  matseek_knowledge.db        SQLite (documents, sections, figures, entities, triples)
  records/<id>.json           one JSON per document
  triples.jsonl               append-only triple stream
  kg_export.json              entity/relation graph export
  MATSEEK_REPORT.md           human-readable run report
  manifest.json               counts + config

Idempotent and resumable: rerunning re-extracts and overwrites by content hash.
"""

import os, re, sys, json, sqlite3, hashlib, glob, time
from datetime import datetime, timezone
from collections import Counter, defaultdict

# ---------------------------------------------------------------- config
OUT = r"D:\hermes\data\matseek"
REC_DIR = os.path.join(OUT, "records")
DB = os.path.join(OUT, "matseek_knowledge.db")
TRIPLES = os.path.join(OUT, "triples.jsonl")
KG = os.path.join(OUT, "kg_export.json")
REPORT = os.path.join(OUT, "MATSEEK_REPORT.md")
MANIFEST = os.path.join(OUT, "manifest.json")

PDF_DIR = r"D:\hermes\data\papers"
ABS_ROOTS = [
    r"D:\hermes\hermes-data\shared\knowledge_base",
    r"D:\hermes\data\math_knowledge",
    r"D:\hermes\data\physics_knowledge",
    r"D:\hermes\data\book_knowledge\literature",
]
GH_ROOT = r"D:\hermes\data\agent_knowledge"

NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")

# ---------------------------------------------------------------- lexicons
METHODS = [
    "transformer", "diffusion model", "reinforcement learning", "deep learning",
    "machine learning", "neural network", "convolutional neural network", "gcn",
    "graph neural network", "monte carlo", "mcmc", "variational inference",
    "finite element", "finite element method", "gaussian process", "kernel method",
    "support vector machine", "random forest", "gradient boosting", "bayesian inference",
    "stochastic gradient descent", "adam", "policy gradient", "q-learning",
    "actor-critic", "diffusion", "kronecker", "domain decomposition", "multigrid",
    "quasi-monte carlo", "latin hypercube", "smoothed particle hydrodynamics",
    "lattice boltzmann", "density functional theory", "molecular dynamics",
    "path integral", "shooting method", "spectral method", "galerkin",
    "model predictive control", "kalman filter", "particle filter", "markov chain",
    "contrastive learning", "self-supervised learning", "transfer learning",
    "federated learning", "attention mechanism", "lstm", "recurrent neural network",
    "encoder-decoder", "autoencoder", "normalizing flow", "score matching",
    "schrodinger bridge", "optimal transport", "operator splitting", "ensemble kalman",
    "principal component analysis", "t-sne", "umap", "k-means", "dbscan",
    "tokenization", "chain-of-thought", "in-context learning", "rag",
]
DATASETS = [
    "imagenet", "cifar-10", "cifar-100", "mnist", "fashion-mnist", "coco",
    "glue", "superglue", "squad", "squad 2.0", "mmlu", "hellaswag", "gsm8k",
    "humaneval", "wikitext", "the pile", "openwebtext", "common crawl",
    "criteo", "movielens", "amazon reviews", "pascal voc", "ade20k", "cityscapes",
    "kitti", "nuscenes", "librispeech", "common voice", "vqa", "gqa", "sroie",
    "pubmedqa", "msmarco", "beir", "mt-bench", "alpaca", "openwebmath",
]
METRICS = [
    "accuracy", "precision", "recall", "f1", "f1 score", "auc", "auroc", "auprc",
    "rmse", "mae", "mape", "mse", "r2", "iou", "dice", "bleu", "rouge", "meteor",
    "perplexity", "top-1 accuracy", "top-5 accuracy", "ndcg", "mrr",
    "macro-f1", "micro-f1", "pass@1", "hit rate", "calibration error", "ece",
]
TOOLS = [
    "pytorch", "tensorflow", "jax", "keras", "scikit-learn", "sklearn", "xgboost",
    "lightgbm", "catboost", "huggingface", "transformers", "deepspeed", "megatron",
    "vllm", "faiss", "milvus", "lammps", "vasp", "quantum espresso", "openfoam",
    "ansys", "abaqus", "comsol", "gurobi", "cplex", "cvxpy", "matlab",
    "numpy", "scipy", "pandas", "statsmodels", "pymc", "stan", "geant4", "root",
    "sumo", "openmm", "gromacs", "namd", "lammps", "ovito",
]
MATERIALS = [
    "lithium", "li-ion", "silicon", "graphite", "nmc", "lfp", "nca", "lmno",
    "solid electrolyte", "llzo", "sulfide electrolyte", "separator", "binder",
    "pvdf", "copper foil", "aluminum foil", "nickel", "cobalt", "manganese",
    "perovskite", "gan", "sic", "graphene", "carbon nanotube", "mxene",
    "high-entropy alloy", "steel", "titanium alloy", "aluminum alloy",
]
CONCEPTS = [
    "generalization", "robustness", "interpretability", "scalability", "efficiency",
    "sample complexity", "convergence rate", "regret bound", "identifiability",
    "causal inference", "fairness", "privacy", "hallucination", "alignment",
    "uncertainty quantification", "calibration", "sparsity", "quantization",
    "distillation", "long context", "context window", "sparse attention",
    "thermal management", "capacity fade", "coulombic efficiency", "overpotential",
]
LEX = {"Method": METHODS, "Dataset": DATASETS, "Metric": METRICS,
       "Tool": TOOLS, "Material": MATERIALS, "Concept": CONCEPTS}

SECTION_ALIASES = {
    "problem":      ["introduction", "background", "motivation", "problem statement"],
    "method":       ["method", "methods", "methodology", "approach", "model",
                     "proposed", "framework", "algorithm", "formulation", "theory"],
    "results":      ["experiment", "experiments", "result", "results", "evaluation",
                     "empirical", "analysis", "ablation"],
    "conclusion":   ["conclusion", "conclusions", "summary", "discussion"],
    "limitations":  ["limitation", "limitations", "future work", "threats to validity",
                     "discussion"],
    "related":      ["related work", "prior work", "literature review"],
    "references":   ["reference", "references", "bibliography"],
}

STOP = set("""a an the and or but if then else of for to in on at by with from as is are was were be been being
this that these those it its we our you your they their he she his her not no nor can could may might must should
will would do does did done have has had than so such more most other some any each both few many much own same
also however therefore thus hence which who whom whose what when where why how all into over under between within
using used use uses based show shows shown propose proposed present presents result results method methods paper
study approach data model models new two three one first second also can may upon per via et al fig figure table
""".split())

# ---------------------------------------------------------------- helpers
def sstr(v):
    """Coerce whatever the JSON gave us into a string (some KB entries store a
    dict/list where a string is expected -> was a TypeError on ~1 file in 500)."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return " ".join(sstr(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return " ".join(sstr(x) for x in v)
    return str(v)

def norm(s):
    return re.sub(r"\s+", " ", sstr(s)).strip()

def sentences(txt, n=2, minlen=40):
    """first n sentences worth of text, bounded."""
    txt = norm(txt)
    if not txt:
        return ""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", txt)
    out, tot = [], 0
    for p in parts:
        if len(p) < 10:
            continue
        out.append(p)
        tot += len(p)
        if len(out) >= n or tot > 420:
            break
    return norm(" ".join(out))[:600]

def first_sentence_with(txt, words, window=None, maxlen=500):
    """find a sentence containing any of `words`; return (sentence, matched_word)."""
    body = norm(txt if window is None else txt[:window])
    for p in re.split(r"(?<=[.!?])\s+", body):
        low = p.lower()
        for w in words:
            if w in low:
                return norm(p)[:maxlen], w
    return "", ""

def sha(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8", "ignore"))
    return h.hexdigest()[:20]

def rec_id(kind, *parts):
    return kind[:2] + "-" + sha(*parts)

def _term_re(t):
    """word-boundary matcher; spaces in the term match any whitespace."""
    body = re.escape(t).replace(r"\ ", r"\s+")
    return re.compile(r"(?<![A-Za-z0-9])" + body + r"(?![A-Za-z0-9])", re.I)

def find_terms(text, vocab):
    """Count lexicon hits with word boundaries, longest term first, no overlap.

    CRITICAL: plain substring counting produced garbage ('iou' inside 'previous',
    'ece' inside 'science', 'stan' inside 'constant', 'sic' inside 'physics'),
    which poisoned the entity + triple layers.  Boundaries + longest-first +
    span masking kills that class of false positive.
    """
    low = text or ""
    taken = bytearray(len(low))
    hits = Counter()
    for t in sorted(vocab, key=len, reverse=True):
        for m in _term_re(t).finditer(low):
            a, b = m.start(), m.end()
            if any(taken[a:b]):
                continue
            for i in range(a, b):
                taken[i] = 1
            hits[t] += 1
    return hits

# ---------------------------------------------------------------- extractors: PDF
def pdf_pages_text(path, limit=None):
    import fitz
    doc = fitz.open(path)
    pages = []
    n = len(doc) if limit is None else min(limit, len(doc))
    for i in range(n):
        pages.append(doc[i].get_text("text") or "")
    doc.close()
    return pages

def pdf_title_authors(pages):
    """largest-font span on page 1 = title; following lines = authors."""
    import fitz
    return None, None, None  # replaced below (kept for API symmetry)

def extract_pdf(path):
    import fitz
    doc = fitz.open(path)
    npages = len(doc)

    # ---- title: pick the largest-font BLOCK on page 1, but never the rotated
    # arXiv sidebar stamp (it is the largest thing on many arXiv PDFs and used to
    # be chosen as the title, then bled into the "problem" field).
    title, title_size = "", 0.0
    meta_title = ""
    try:
        meta_title = norm((doc.metadata or {}).get("title", "") or "")
    except Exception:
        meta_title = ""
    try:
        d = doc[0].get_text("dict")
        W = doc[0].rect.width
        best = None
        for blk in d.get("blocks", []):
            parts, mx, xs = [], 0.0, []
            for ln in blk.get("lines", []):
                for sp in ln.get("spans", []):
                    t = norm(sp.get("text", ""))
                    if not t:
                        continue
                    parts.append(t)
                    mx = max(mx, float(sp.get("size", 0)))
                    xs.append(sp.get("bbox", [0, 0, 0, 0])[0])
            if not parts:
                continue
            txt = norm(" ".join(parts))
            if len(txt) < 12:
                continue
            if re.search(r"(?i)arxiv:\s*\d{4}\.\d{4,5}|^\[[a-z]{2}\.[A-Z]{2}\]", txt):
                continue
            if xs and min(xs) < W * 0.12:      # sidebar / margin stamp column
                continue
            if best is None or mx > best[0] + 1e-6:
                best = (mx, txt)
        if best:
            title_size, title = best
    except Exception:
        pass
    title = re.sub(r"\s+", " ", title).strip()
    if len(title) < 12 and meta_title:
        title = meta_title

    page1 = ""
    try:
        page1 = doc[0].get_text("text") or ""
    except Exception:
        pass

    # ---- authors: the line band on page 1 between title and "Abstract" ----
    authors = []
    p1 = [norm(l) for l in page1.splitlines()]
    p1 = [l for l in p1 if l and not re.match(r"(?i)^arxiv:\s*\d", l)]
    ai = next((i for i, l in enumerate(p1) if re.match(r"(?i)^a\s*b\s*s\s*t\s*r\s*a\s*c\s*t", l)), -1)
    band = p1[1:ai] if ai > 1 else p1[1:10]
    for l in band[:14]:
        if re.search(r"(?i)abstract|keywords|index terms", l):
            continue
        if re.search(r"(?i)@[a-z0-9]", l):
            continue
        if re.search(r"(?i)university|institute|department|laborator", l) and "," not in l:
            continue
        for piece in re.split(r",|;|·|\band\b", l):
            piece = norm(re.sub(r"[\d*\u2020\u2021\u00a7]+", " ", piece))
            if not (3 <= len(piece) <= 60) or not re.search(r"[A-Za-z]", piece):
                continue
            if re.search(r"(?i)abstract|keywords|www\.|http", piece):
                continue
            # affiliation / address noise that comma-splitting lets through
            if re.search(r"(?i)universit|faculty|institut|department|school|laborator|college|"
                         r"academy|research cent|via\b|street|avenue|road|boulevard|"
                         r"\bUSA\b|\bUK\b|\bChina\b|\bItaly\b|\bGermany\b|\bFrance\b|"
                         r"\bJapan\b|\bKorea\b|new york|california|bolzano|bozen|zip|"
                         r"graduate school|@", piece):
                continue
            # the title itself is often repeated as the first "line" of the band
            if title and (piece.lower() in title.lower() or title.lower().startswith(piece.lower())):
                continue
            # a lone capitalised word with no other token is usually a city/country
            if len(piece.split()) == 1 and piece[:1].isupper() and len(piece) < 14:
                continue
            authors.append(piece)
    seen, dedup = set(), []
    for a in authors:
        k = a.lower()
        if k not in seen:
            seen.add(k); dedup.append(a)
    authors = dedup[:15]

    pages = [(doc[i].get_text("text") or "") for i in range(npages)]
    doc.close()
    full = "\n".join(pages)

    # ---- sections ----
    secs = []
    num_re = re.compile(r"^\s*(\d+(?:\.\d+){0,3})[\.\s]\s*([A-Z][A-Za-z0-9 \-/:,()]{2,70})\s*$")
    name_re = re.compile(
        r"^\s*(Abstract|Introduction|Related Work|Background|Motivation|Preliminaries|"
        r"Methods?|Methodology|Approach|Model|Framework|Algorithm|Experiments?|Results?|"
        r"Evaluation|Analysis|Ablation(?: Study)?|Discussion|Limitations?|Future Work|"
        r"Conclusions?|Conclusions and Future Work|References|Bibliography|Appendix)"
        r"\s*:?\s*$", re.I)
    for pno, txt in enumerate(pages):
        for line in txt.splitlines():
            l = norm(line)
            if not (3 <= len(l) <= 80):
                continue
            m = num_re.match(l) or name_re.match(l)
            if m:
                h = norm(m.group(2) if num_re.match(l) else m.group(1))
                if h and not h.isdigit():
                    secs.append({"heading": h, "page": pno + 1})
    # dedupe consecutive
    ded = []
    for s in secs:
        if not ded or ded[-1]["heading"].lower() != s["heading"].lower():
            ded.append(s)

    def sec_text(names, maxlen=3000):
        """text following the first heading whose name matches, until next heading."""
        for i, s in enumerate(ded):
            hl = s["heading"].lower()
            if any(nm in hl for nm in names):
                start_pg = s["page"] - 1
                end_pg = ded[i + 1]["page"] - 1 if i + 1 < len(ded) else min(start_pg + 4, npages - 1)
                body = "\n".join(pages[start_pg:end_pg + 1])
                j = body.lower().find(s["heading"].lower())
                if j >= 0:
                    body = body[j + len(s["heading"]):]
                for nm in [d["heading"] for d in ded[i + 1:i + 2]]:
                    k = body.lower().find(nm.lower())
                    if k > 0:
                        body = body[:k]
                return norm(body)[:maxlen]
        return ""

    # abstract
    abstract = ""
    m = re.search(r"(?is)abstract[\s:—-]*(.{80,2600}?)(?:\n\s*(?:\d+\.?\s*)?"
                  r"(?:introduction|keywords|index terms|1\s+introduction)\b)", full)
    if m:
        abstract = norm(m.group(1))
    if not abstract:
        # try pure-text abstract: paragraph after the word Abstract
        i = full.lower().find("abstract")
        if i >= 0:
            abstract = norm(full[i + 8:i + 2000])
    abstract = abstract[:2600]

    # keywords
    kw = []
    m = re.search(r"(?is)keywords?[\s:—-]*(.{5,300}?)(?:\n\s*\n|\n\s*(?:\d+\.?\s*)?(?:introduction|1\s+introduction))", full)
    if m:
        kw = [norm(k) for k in re.split(r"[,;·]", m.group(1)) if 2 <= len(norm(k)) <= 45][:15]

    # figures & tables captions
    figs, tabs = [], []
    for pno, txt in enumerate(pages):
        for mt in re.finditer(r"(?im)^\s*(figure|fig\.?|table)\s*(\d+[a-zA-Z]?)\s*[:.]?\s*([^\n]{5,300})", txt):
            kind, num, cap = mt.group(1).lower(), mt.group(2), norm(mt.group(3))
            item = {"label": f"{'Fig' if kind.startswith('fig') else 'Table'} {num}",
                    "caption": cap, "page": pno + 1}
            (figs if kind.startswith("fig") else tabs).append(item)
    figs, tabs = figs[:60], tabs[:60]

    # references
    refs = 0
    for rname in ("references", "bibliography"):
        for i, s in enumerate(ded):
            if rname in s["heading"].lower():
                rb = "\n".join(pages[s["page"] - 1:])
                refs = max(refs, len(re.findall(r"(?m)^\s*\[\d{1,4}\]", rb)))
                refs = max(refs, len(re.findall(r"(?m)^\s*\d{1,4}\.\s+[A-Z]", rb)))
    arxiv = ""
    m = re.search(r"arxiv[:\s]*(\d{4}\.\d{4,5})", full, re.I)
    if m:
        arxiv = m.group(1)

    # ---- knowledge pack (heuristic, provenance-tracked) ----
    intro = sec_text(SECTION_ALIASES["problem"])
    meth = sec_text(SECTION_ALIASES["method"])
    res = sec_text(SECTION_ALIASES["results"])
    con = sec_text(SECTION_ALIASES["conclusion"])
    lim = sec_text(SECTION_ALIASES["limitations"])

    def pack(text, fallback_src):
        if norm(text):
            return sentences(text, 2), 0.6
        return "", 0.0

    def looks_like_frontmatter(txt):
        return bool(re.search(r"(?i)@[a-z0-9][\w.\-]*\.[a-z]{2,}|department of|"
                              r"university|institute of|arxiv:\s*\d", txt or ""))

    def looks_like_toc(txt):
        return len(re.findall(r"(?i)\bpage\b", txt or "")) >= 4

    kp = {}
    t, c = pack(intro, "introduction")
    if t and looks_like_frontmatter(t):
        t, c = "", 0.0
    if not t:
        t = sentences(abstract, 2); c = 0.45 if t else 0.0
        src = "abstract" if t else "not_stated"
    else:
        src = "introduction"
    kp["problem"] = {"text": t or "not_stated", "evidence": src, "confidence": round(c, 2)}

    t, c = pack(meth, "method")
    if not t:
        hits = find_terms(abstract, METHODS)
        t = ("提及方法: " + ", ".join([h for h, _ in hits.most_common(6)])) if hits else ""
        c = 0.3 if t else 0.0
        src = "abstract(lexicon)" if t else "not_stated"
    else:
        src = "method section"
    kp["method"] = {"text": t or "not_stated", "evidence": src, "confidence": round(c, 2)}

    t, c = pack(res, "results")
    if t and looks_like_toc(t):          # a table-of-contents page is not results
        t, c = "", 0.0
    if not t:
        t, c = pack(con, "conclusion")
    kp["data_and_conclusions"] = {"text": t or "not_stated",
                                  "evidence": ("results/experiments" if res else ("conclusion" if con else "not_stated")),
                                  "confidence": round(c, 2)}

    t, c = pack(lim, "limitations")
    if not t:
        t, c = "", 0.0
    kp["limitations"] = {"text": t or "not_stated",
                         "evidence": ("limitations/discussion/future work" if t else "not_stated"),
                         "confidence": round(c, 2)}

    # entities
    corpus_for_lex = norm(abstract + " " + intro + " " + meth + " " + res + " " + con)
    entities = []
    for etype, vocab in LEX.items():
        for term, cnt in find_terms(corpus_for_lex, vocab).most_common(12):
            entities.append({"name": term, "type": etype, "count": cnt})
    for ln in ded[:40]:
        entities.append({"name": ln["heading"], "type": "Section", "count": 1})

    fname = os.path.basename(path)
    m = re.match(r"^(\d{4}\.\d{4,5})[_\- ](.*)$", fname)
    fid, ftitle = (m.group(1), m.group(2)) if m else ("", "")
    title = title or ftitle or fname.replace(".pdf", "")

    return {
        "id": rec_id("paper", (arxiv or fid or fname)),
        "kind": "paper_pdf",
        "source_path": path,
        "source_url": (f"https://arxiv.org/abs/{arxiv or fid}" if (arxiv or fid) else ""),
        "arxiv_id": arxiv or fid,
        "title": norm(title),
        "authors": authors,
        "year": (("20" + (arxiv or fid)[:2]) if (arxiv or fid)[:2].isdigit() else ""),
        "venue": "",
        "categories": [],
        "abstract": abstract,
        "keywords": kw,
        "pages": npages,
        "knowledge": kp,
        "sections": ded,
        "figures": figs,
        "tables": tabs,
        "references_count": refs,
        "entities": entities,
        "extraction_method": "heuristic:pymupdf+regex",
    }

# ---------------------------------------------------------------- extractors: abstract JSON
def extract_abs_json(path, entry):
    title = norm(entry.get("title", ""))
    summ = norm(entry.get("summary", "") or entry.get("abstract", ""))
    aid = entry.get("arxiv_id", "") or ""
    topic = os.path.splitext(os.path.basename(path))[0]
    kp = {
        "problem": {"text": sentences(summ, 1) or "not_stated",
                    "evidence": "abstract(summary field)" if summ else "not_stated",
                    "confidence": 0.4 if summ else 0.0},
        "method": {"text": "", "evidence": "not_stated", "confidence": 0.0},
        "data_and_conclusions": {"text": sentences(summ, 2, minlen=0) or "not_stated",
                                 "evidence": "abstract(summary field)" if summ else "not_stated",
                                 "confidence": 0.4 if summ else 0.0},
        "limitations": {"text": "not_stated", "evidence": "not_stated", "confidence": 0.0},
    }
    hits = find_terms(summ, METHODS)
    if hits:
        kp["method"]["text"] = "提及方法: " + ", ".join([h for h, _ in hits.most_common(6)])
        kp["method"]["evidence"] = "abstract(lexicon)"
        kp["method"]["confidence"] = 0.3
    entities = []
    for etype, vocab in LEX.items():
        for term, cnt in find_terms(summ, vocab).most_common(8):
            entities.append({"name": term, "type": etype, "count": cnt})
    return {
        "id": rec_id("abs", aid or title),
        "kind": "paper_abstract",
        "source_path": path,
        "source_url": entry.get("url", "") or (f"https://arxiv.org/abs/{aid}" if aid else ""),
        "arxiv_id": aid,
        "title": title,
        "authors": [norm(a) for a in (entry.get("authors") or [])][:20],
        "year": (entry.get("published", "") or "")[:4],
        "venue": entry.get("venue", ""),
        "categories": entry.get("categories", []) or [],
        "abstract": summ,
        "keywords": [],
        "pages": 0,
        "knowledge": kp,
        "sections": [],
        "figures": [],
        "tables": [],
        "references_count": 0,
        "entities": entities,
        "topic": topic, "topics": [topic],
        "extraction_method": "heuristic:json-fields+lexicon",
    }

# ---------------------------------------------------------------- extractors: github scout
def _iter_dicts(node):
    """Recursively yield every dict that looks like a repo record."""
    if isinstance(node, dict):
        if node.get("full_name"):
            yield node
        for v in node.values():
            yield from _iter_dicts(v)
    elif isinstance(node, list):
        for v in node:
            yield from _iter_dicts(v)

def extract_gh_json(path, entry):
    if not isinstance(entry, dict) or not entry.get("full_name"):
        return None
    lang = entry.get("language", "") or ""
    topics = entry.get("topics", []) or []
    owner = entry["full_name"].split("/")[0]
    ents = [{"name": lang, "type": "Language", "count": 1}] if lang else []
    ents += [{"name": t, "type": "Topic", "count": 1} for t in topics[:12]]
    return {
        "id": rec_id("repo", entry["full_name"]),
        "kind": "repo",
        "source_path": path,
        "source_url": entry.get("url", ""),
        "arxiv_id": "",
        "title": entry["full_name"],
        "authors": [owner],
        "year": (entry.get("created_at", "") or "")[:4],
        "venue": "",
        "categories": topics,
        "abstract": norm(entry.get("description", "")),
        "keywords": topics,
        "pages": 0,
        "knowledge": {
            "problem": {"text": norm(entry.get("description", ""))[:400] or "not_stated",
                        "evidence": "repo description" if entry.get("description") else "not_stated",
                        "confidence": 0.5 if entry.get("description") else 0.0},
            "method": {"text": "not_stated", "evidence": "not_stated", "confidence": 0.0},
            "data_and_conclusions": {"text": f"stars={entry.get('stars')} forks={entry.get('forks')}",
                                     "evidence": "repo metrics", "confidence": 0.9},
            "limitations": {"text": "not_stated", "evidence": "not_stated", "confidence": 0.0},
        },
        "sections": [], "figures": [], "tables": [], "references_count": 0,
        "entities": ents,
        "repo": {"stars": entry.get("stars"), "forks": entry.get("forks"),
                 "language": lang, "license": entry.get("license", ""),
                 "pushed_at": entry.get("pushed_at", "")},
        "extraction_method": "heuristic:json-fields",
    }

# ---------------------------------------------------------------- triples
def build_triples(rec):
    tr, sid = [], rec["id"]
    def add(h, r, t, ev):
        if h and r and t and len(str(t)) < 90:
            tr.append({"head": h, "relation": r, "tail": str(t), "evidence": norm(ev)[:160], "document": sid})
    if rec["kind"] == "repo":
        for a in rec["authors"][:1]:
            add(rec["title"], "OWNED_BY_ORG", a, "full_name owner")
        if rec.get("repo", {}).get("language"):
            add(rec["title"], "WRITTEN_IN", rec["repo"]["language"], "language field")
        for t in rec["keywords"][:10]:
            add(rec["title"], "HAS_TOPIC", t, "topics field")
        return tr
    # papers
    for a in rec["authors"][:12]:
        add(rec["title"] or rec["id"], "AUTHORED_BY", a, "page1 authors")
    for c in (rec["categories"] or [])[:6]:
        add(rec["title"] or rec["id"], "HAS_CATEGORY", c, "categories field")
    if rec.get("topic"):
        add(rec["title"] or rec["id"], "IN_TOPIC", rec["topic"], "knowledge_base topic dir")
    for e in rec["entities"]:
        et, nm = e["type"], e["name"]
        if et == "Method":
            add(rec["title"] or rec["id"], "USES_METHOD", nm, "lexicon hit in abstract/sections")
        elif et == "Dataset":
            add(rec["title"] or rec["id"], "EVALUATES_ON", nm, "lexicon hit in abstract/sections")
        elif et == "Metric":
            add(rec["title"] or rec["id"], "REPORTS_METRIC", nm, "lexicon hit in abstract/sections")
        elif et == "Tool":
            add(rec["title"] or rec["id"], "USES_TOOL", nm, "lexicon hit in abstract/sections")
        elif et == "Material":
            add(rec["title"] or rec["id"], "MENTIONS_MATERIAL", nm, "lexicon hit in abstract/sections")
        elif et == "Concept":
            add(rec["title"] or rec["id"], "ADDRESSES_CONCEPT", nm, "lexicon hit in abstract/sections")
    kp = rec["knowledge"]
    if kp["method"]["evidence"] != "not_stated":
        add(rec["title"] or rec["id"], "HAS_METHOD_TEXT", kp["method"]["text"][:80], kp["method"]["evidence"])
    return tr

def _merge(a, b):
    """Fold duplicate record b into a (a wins on scalars; unions on the rest).

    Identity is the logical document (arxiv id / repo full_name), so the same
    paper listed in several topic dirs -- or the same repo seen by many scout
    runs -- collapses to ONE document with merged provenance. Without this the
    same repo appeared in 743 files and inflated the graph ~20x.
    """
    for k in ("title", "abstract", "year", "venue", "source_url", "arxiv_id"):
        if not a.get(k) and b.get(k):
            a[k] = b[k]
    for k in ("authors", "categories", "keywords"):
        av, bv = a.get(k) or [], b.get(k) or []
        a[k] = list(dict.fromkeys([norm(x) for x in av] + [norm(x) for x in bv]))[:25]
    paths = a.setdefault("source_paths", [a.get("source_path", "")])
    if b.get("source_path") and b["source_path"] not in paths:
        paths.append(b["source_path"])
    tv = set(a.get("topics") or [])
    if b.get("topic"):
        tv.add(b["topic"])
    tv |= set(b.get("topics") or [])
    a["topics"] = sorted(tv)[:12]
    em = {}
    for e in (a.get("entities") or []) + (b.get("entities") or []):
        kk = (e["type"], e["name"])
        em[kk] = max(em.get(kk, 0), e.get("count", 1))
    a["entities"] = [{"name": n, "type": t, "count": c} for (t, n), c in em.items()]
    if a.get("repo") and b.get("repo"):
        a["repo"]["stars"] = max(a["repo"].get("stars") or 0, b["repo"].get("stars") or 0)
        a["repo"]["forks"] = max(a["repo"].get("forks") or 0, b["repo"].get("forks") or 0)
    # a duplicate with better knowledge wins on empty fields
    for f, v in (b.get("knowledge") or {}).items():
        if v.get("text") and v["text"] != "not_stated" and a["knowledge"].get(f, {}).get("confidence", 0) < v.get("confidence", 0):
            a["knowledge"][f] = v
    return a

# ---------------------------------------------------------------- sqlite
SCHEMA = """
CREATE TABLE IF NOT EXISTS documents(
  id TEXT PRIMARY KEY, kind TEXT, title TEXT, authors TEXT, year TEXT, venue TEXT,
  arxiv_id TEXT, categories TEXT, abstract TEXT, keywords TEXT, pages INT,
  references_count INT, source_path TEXT, source_url TEXT,
  problem TEXT, problem_conf REAL, method TEXT, method_conf REAL,
  data_and_conclusions TEXT, dac_conf REAL, limitations TEXT, lim_conf REAL,
  problem_ev TEXT, method_ev TEXT, dac_ev TEXT, lim_ev TEXT,
  extraction_method TEXT, content_hash TEXT, extracted_at TEXT, extra TEXT
);
CREATE TABLE IF NOT EXISTS sections(
  doc_id TEXT, heading TEXT, page INT, ord INT
);
CREATE TABLE IF NOT EXISTS figures(
  doc_id TEXT, label TEXT, caption TEXT, page INT, kind TEXT
);
CREATE TABLE IF NOT EXISTS entities(
  doc_id TEXT, name TEXT, type TEXT, count INT
);
CREATE TABLE IF NOT EXISTS triples(
  doc_id TEXT, head TEXT, relation TEXT, tail TEXT, evidence TEXT
);
CREATE INDEX IF NOT EXISTS ix_doc_kind ON documents(kind);
CREATE INDEX IF NOT EXISTS ix_triple_rel ON triples(relation);
CREATE INDEX IF NOT EXISTS ix_triple_head ON triples(head);
CREATE INDEX IF NOT EXISTS ix_ent_name ON entities(name);
CREATE INDEX IF NOT EXISTS ix_ent_type ON entities(type);
CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(title, abstract, keywords, content='');
"""

def init_db():
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    c.commit()
    return c

def upsert(conn, rec, triples):
    kp = rec["knowledge"]
    DOC_COLS = ["id", "kind", "title", "authors", "year", "venue", "arxiv_id",
                "categories", "abstract", "keywords", "pages", "references_count",
                "source_path", "source_url", "problem", "problem_conf", "method",
                "method_conf", "data_and_conclusions", "dac_conf", "limitations",
                "lim_conf", "problem_ev", "method_ev", "dac_ev", "lim_ev",
                "extraction_method", "content_hash", "extracted_at", "extra"]
    conn.execute("INSERT OR REPLACE INTO documents (" + ",".join(DOC_COLS) + ") VALUES ("
                 + ",".join("?" * len(DOC_COLS)) + ")", (
        rec["id"], rec["kind"], rec["title"], json.dumps(rec["authors"], ensure_ascii=False),
        rec["year"], rec["venue"], rec["arxiv_id"],
        json.dumps(rec["categories"], ensure_ascii=False), rec["abstract"],
        json.dumps(rec["keywords"], ensure_ascii=False), rec["pages"], rec["references_count"],
        rec["source_path"], rec["source_url"],
        kp["problem"]["text"], kp["problem"]["confidence"],
        kp["method"]["text"], kp["method"]["confidence"],
        kp["data_and_conclusions"]["text"], kp["data_and_conclusions"]["confidence"],
        kp["limitations"]["text"], kp["limitations"]["confidence"],
        kp["problem"]["evidence"], kp["method"]["evidence"],
        kp["data_and_conclusions"]["evidence"], kp["limitations"]["evidence"],
        rec["extraction_method"], sha(rec["title"], rec["abstract"], rec["source_path"]),
        NOW, json.dumps({k: v for k, v in rec.items()
                         if k in ("topic", "repo")}, ensure_ascii=False)))
    conn.execute("DELETE FROM sections WHERE doc_id=?", (rec["id"],))
    for i, s in enumerate(rec["sections"]):
        conn.execute("INSERT INTO sections VALUES(?,?,?,?)", (rec["id"], s["heading"], s.get("page", 0), i))
    conn.execute("DELETE FROM figures WHERE doc_id=?", (rec["id"],))
    for f in rec["figures"]:
        conn.execute("INSERT INTO figures VALUES(?,?,?,?,?)", (rec["id"], f["label"], f["caption"], f["page"], "figure"))
    for t in rec["tables"]:
        conn.execute("INSERT INTO figures VALUES(?,?,?,?,?)", (rec["id"], t["label"], t["caption"], t["page"], "table"))
    conn.execute("DELETE FROM entities WHERE doc_id=?", (rec["id"],))
    for e in rec["entities"]:
        conn.execute("INSERT INTO entities VALUES(?,?,?,?)", (rec["id"], e["name"], e["type"], e["count"]))
    conn.execute("DELETE FROM triples WHERE doc_id=?", (rec["id"],))
    for t in triples:
        conn.execute("INSERT INTO triples VALUES(?,?,?,?,?)",
                     (t["document"], t["head"], t["relation"], t["tail"], t["evidence"]))
    conn.execute("INSERT INTO docs_fts(rowid,title,abstract,keywords) VALUES("
                 "(SELECT rowid FROM documents WHERE id=?),?,?,?)",
                 (rec["id"], rec["title"], rec["abstract"], " ".join(rec["keywords"])))

# ---------------------------------------------------------------- main
def main():
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(REC_DIR, exist_ok=True)
    conn = init_db()
    stats = defaultdict(int)
    errors = []
    all_triples = []
    seen_ids = set()

    # A. PDFs
    pdfs = sorted(glob.glob(os.path.join(PDF_DIR, "*.pdf")))
    print(f"[A] full-text PDFs: {len(pdfs)}")
    for i, p in enumerate(pdfs, 1):
        try:
            rec = extract_pdf(p)
            rec["extracted_at"] = NOW
            tr = build_triples(rec)
            with open(os.path.join(REC_DIR, rec["id"] + ".json"), "w", encoding="utf-8") as fh:
                json.dump(rec, fh, ensure_ascii=False, indent=1)
            upsert(conn, rec, tr); all_triples += tr
            stats["pdf"] += 1; stats["triples"] += len(tr); seen_ids.add(rec["id"])
            print(f"    {i:2}/{len(pdfs)} {os.path.basename(p)[:60]:62} pages={rec['pages']:3} sec={len(rec['sections']):3} fig={len(rec['figures']):2} tri={len(tr)}")
        except Exception as e:
            errors.append({"source": p, "error": f"{type(e).__name__}: {e}"}); stats["pdf_err"] += 1
            print(f"    {i:2}/{len(pdfs)} ERROR {os.path.basename(p)[:50]} -> {e}")
        if i % 10 == 0:
            conn.commit()
    conn.commit()

    # B. abstract-level JSON
    n = 0
    for root in ABS_ROOTS:
        if not os.path.isdir(root):
            continue
        for dp, dn, fn in os.walk(root):
            for f in fn:
                if not f.lower().endswith(".json"):
                    continue
                n += 1
    print(f"[B] abstract-level JSON files: {n}")
    c = 0
    for root in ABS_ROOTS:
        if not os.path.isdir(root):
            continue
        for dp, dn, fn in os.walk(root):
            for f in sorted(fn):
                if not f.lower().endswith(".json"):
                    continue
                p = os.path.join(dp, f)
                try:
                    with open(p, encoding="utf-8") as fh:
                        data = json.load(fh)
                    entries = data if isinstance(data, list) else [data]
                    for e in entries:
                        if not isinstance(e, dict):
                            continue
                        if not e.get("title"):
                            continue
                        rec = extract_abs_json(p, e)
                        rec["extracted_at"] = NOW
                        if rec["id"] in seen_ids:
                            continue
                        seen_ids.add(rec["id"])
                        tr = build_triples(rec)
                        upsert(conn, rec, tr); all_triples += tr
                        stats["abstract"] += 1; stats["triples"] += len(tr); c += 1
                except Exception as e:
                    errors.append({"source": p, "error": f"{type(e).__name__}: {e}"}); stats["abs_err"] += 1
        conn.commit()
        print(f"    scanned {root} -> total abstracts={stats['abstract']}")

    # C. github scout
    gh = []
    if os.path.isdir(GH_ROOT):
        for dp, dn, fn in os.walk(GH_ROOT):
            for f in fn:
                if f.lower().endswith(".json"):
                    gh.append(os.path.join(dp, f))
    print(f"[C] github scout JSON files: {len(gh)}")
    for p in sorted(gh):
        try:
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
            for e in _iter_dicts(data):
                rec = extract_gh_json(p, e)
                if not rec or rec["id"] in seen_ids:
                    continue
                seen_ids.add(rec["id"])
                rec["extracted_at"] = NOW
                tr = build_triples(rec)
                upsert(conn, rec, tr); all_triples += tr
                stats["repo"] += 1; stats["triples"] += len(tr)
        except Exception as e:
            errors.append({"source": p, "error": f"{type(e).__name__}: {e}"}); stats["gh_err"] += 1
    conn.commit()

    # triples stream
    with open(TRIPLES, "w", encoding="utf-8") as fh:
        for t in all_triples:
            fh.write(json.dumps(t, ensure_ascii=False) + "\n")

    # KG export
    nodes = defaultdict(lambda: {"type": "unknown", "count": 0, "docs": set()})
    edges = defaultdict(int)
    for t in all_triples:
        nodes[t["head"]]["docs"].add(t["document"]); nodes[t["head"]]["count"] += 1
        nodes[t["tail"]]["docs"].add(t["document"]); nodes[t["tail"]]["count"] += 1
        edges[(t["head"], t["relation"], t["tail"])] += 1
    kg = {
        "generated_at": NOW,
        "method": "MatSeek-style (offline heuristic extraction + relational mining)",
        "nodes": [{"id": k, "count": v["count"], "documents": len(v["docs"])}
                  for k, v in sorted(nodes.items(), key=lambda x: -x[1]["count"])],
        "edges": [{"source": a, "relation": r, "target": b, "weight": w}
                  for (a, r, b), w in sorted(edges.items(), key=lambda x: -x[1])],
    }
    with open(KG, "w", encoding="utf-8") as fh:
        json.dump(kg, fh, ensure_ascii=False, indent=1)

    # report
    cur = conn.cursor()
    kinds = dict(cur.execute("SELECT kind, COUNT(*) FROM documents GROUP BY kind").fetchall())
    rels = cur.execute("SELECT relation, COUNT(*) FROM triples GROUP BY relation ORDER BY 2 DESC").fetchall()
    tp = cur.execute("SELECT type, COUNT(*) FROM entities GROUP BY type ORDER BY 2 DESC").fetchall()
    have = {}
    for f in ("problem", "method", "data_and_conclusions", "limitations"):
        have[f] = cur.execute(f"SELECT COUNT(*) FROM documents WHERE {f} != 'not_stated' AND {f} != ''").fetchone()[0]
    tot = cur.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    topsec = cur.execute("SELECT heading, COUNT(*) FROM sections GROUP BY lower(heading) ORDER BY 2 DESC LIMIT 15").fetchall()
    topnodes = kg["nodes"][:25]
    with open(REPORT, "w", encoding="utf-8") as fh:
        W = fh.write
        W("# MatSeek 结构化处理报告\n\n")
        W(f"- 生成时间: {NOW}\n- 方法: MatSeek 式「结构化抽取 + 关系知识挖掘」\n- 抽取引擎: **离线启发式**(PyMuPDF + 正则 + 词典), 零 LLM 调用\n- 目录: `{OUT}`\n\n")
        W("## 1. 规模\n\n| 项 | 数量 |\n|---|---|\n")
        for k, v in sorted(kinds.items()):
            W(f"| documents.{k} | {v} |\n")
        W(f"| **documents 合计** | **{tot}** |\n")
        W(f"| triples | {len(all_triples)} |\n| 唯一节点 | {len(kg['nodes'])} |\n| 唯一边(去重) | {len(kg['edges'])} |\n")
        W(f"| 章节 sections | {cur.execute('SELECT COUNT(*) FROM sections').fetchone()[0]} |\n")
        W(f"| 图表 figures+tables | {cur.execute('SELECT COUNT(*) FROM figures').fetchone()[0]} |\n")
        W(f"| 实体 entities | {cur.execute('SELECT COUNT(*) FROM entities').fetchone()[0]} |\n")
        W(f"| 错误 errors | {len(errors)} |\n")
        W("\n## 2. 知识包字段覆盖率（启发式, 诚实标注）\n\n> 文档未声明的一律记 `not_stated`，**不臆造**。\n\n| 字段 | 已抽取 | 覆盖率 |\n|---|---|---|\n")
        for k, v in have.items():
            W(f"| {k} | {v} | {100.0*v/max(1,tot):.1f}% |\n")
        W("\n## 3. 关系分布\n\n| 关系 | 次数 |\n|---|---|\n")
        for r, v in rels:
            W(f"| {r} | {v} |\n")
        W("\n## 4. 实体类型分布\n\n| 类型 | 次数 |\n|---|---|\n")
        for t, v in tp:
            W(f"| {t} | {v} |\n")
        W("\n## 5. 高频章节标题\n\n| 标题 | 次数 |\n|---|---|\n")
        for h, v in topsec:
            W(f"| {h} | {v} |\n")
        W("\n## 6. 图谱中心节点 Top25\n\n| 节点 | 度数 | 覆盖文档数 |\n|---|---|---|\n")
        for nd in topnodes:
            W(f"| {nd['id']} | {nd['count']} | {nd['documents']} |\n")
        if errors:
            W(f"\n## 7. 错误 ({len(errors)})\n\n")
            for e in errors[:60]:
                W(f"- `{os.path.basename(e['source'])}` — {e['error']}\n")
        W("\n## 8. 产物\n\n")
        for f in (DB, REC_DIR, TRIPLES, KG, MANIFEST):
            W(f"- `{f}`\n")
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump({"generated_at": NOW, "stats": dict(stats), "documents_total": tot,
                   "triples_total": len(all_triples), "nodes": len(kg["nodes"]),
                   "edges": len(kg["edges"]), "errors": errors[:200],
                   "elapsed_sec": round(time.time() - t0, 1)},
                  fh, ensure_ascii=False, indent=1)
    conn.commit(); conn.close()
    print("\n=== DONE ===")
    print(json.dumps(dict(stats), ensure_ascii=False, indent=1))
    print(f"documents={tot} triples={len(all_triples)} nodes={len(kg['nodes'])} edges={len(kg['edges'])} errors={len(errors)}")
    print(f"elapsed={time.time()-t0:.1f}s")

if __name__ == "__main__":
    main()
