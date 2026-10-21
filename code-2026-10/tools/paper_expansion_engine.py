"""
论文研究扩展引擎 v1.0
发现高价值论文 → 扩展到同作者+引用论文链
"""
import json, re, urllib.request, urllib.parse, time
from pathlib import Path

TRACKING_DB = Path("D:/hermes/data/paper_tracking")
TRACKING_DB.mkdir(parents=True, exist_ok=True)

ARCHIVE = "D:/hermes/data/math_knowledge/papers"
AI_DL_DIR = Path("D:/hermes/data/agent_knowledge/AI_DL_research")
AI_DL_DIR.mkdir(parents=True, exist_ok=True)

def search_arxiv_authors(first_author, max_results=10):
    """搜索同第一作者的其他论文"""
    url = f"http://export.arxiv.org/api/query?search_query=au:{urllib.parse.quote(first_author)}&sortBy=submittedDate&max_results={max_results}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Hermes/1.0'})
        with urllib.request.urlopen(req, timeout=20) as resp:
            xml = resp.read().decode('utf-8')
            titles = re.findall(r'<title>(.*?)</title>', xml, re.DOTALL)
            ids = re.findall(r'<id>(.*?)</id>', xml)
            authors = re.findall(r'<author>.*?<name>(.*?)</name>.*?</author>', xml, re.DOTALL)
            papers = []
            for i in range(1, min(len(titles), len(ids))):
                papers.append({"title": titles[i].strip()[:100], "url": ids[i].strip()})
            return papers
    except:
        return []

def expand_paper(arxiv_id):
    """展开一篇论文：同作者+引用链"""
    result = {"paper_id": arxiv_id, "same_authors": [], "citations": []}
    url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Hermes/1.0'})
        with urllib.request.urlopen(req, timeout=20) as resp:
            xml = resp.read().decode('utf-8')
            # Extract first author
            authors = re.findall(r'<author>.*?<name>(.*?)</name>.*?</author>', xml, re.DOTALL)
            if authors:
                first_au = authors[0].strip()
                result["same_authors"] = search_arxiv_authors(first_au)
                # Extract cited papers from abstract
                abstract = re.search(r'<abstract>(.*?)</abstract>', xml, re.DOTALL)
                if abstract:
                    refs = re.findall(r'\[(\d+)\]', abstract.group(1))
                    result["citations"] = [f"Reference [{r}]" for r in refs[:5]]
    except: pass
    return result

if __name__ == "__main__":
    import sys
    aid = sys.argv[1] if len(sys.argv) > 1 else "2606.03979"
    result = expand_paper(aid)
    print(json.dumps(result, ensure_ascii=False, indent=2))
