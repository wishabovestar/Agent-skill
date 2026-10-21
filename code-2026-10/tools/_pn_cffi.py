import io, os
from curl_cffi import requests as cr

PX = "socks5h://127.0.0.1:10810"
OUT = "D:/hermes/analysis/_pn/"
T = [
    ("cf_enp.pdf", "https://pure.amsterdamumc.nl/files/205589672/Social-dysfunction-and-default-mode-network-functional-integrity-in-neuropsychiatric-disorders.pdf"),
    ("cf_sd122044.html", "https://www.sciencedirect.com/science/article/pii/S1053811926003599"),
    ("cf_sd122100.html", "https://www.sciencedirect.com/science/article/pii/S1053811926004155"),
    ("cf_radboud.pdf", "https://repository.ubn.ru.nl/bitstream/handle/2066/332280/332280.pdf?sequence=1&isAllowed=y"),
    ("cf_rug.pdf", "https://research.rug.nl/files/1520373816/1-s2.0-S0924977X2600088X-main.pdf"),
]
for name, url in T:
    for imp in ["chrome124", "chrome120"]:
        try:
            r = cr.get(url, impersonate=imp, proxy=PX, timeout=90, allow_redirects=True,
                       headers={"Accept-Language": "en-US,en;q=0.9",
                                "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8"})
            b = r.content
            io.open(OUT + name, "wb").write(b)
            print("%s [%s] status=%s size=%d ct=%s head=%s" % (
                name, imp, r.status_code, len(b), r.headers.get("content-type", "")[:35], b[:6]), flush=True)
            if r.status_code == 200 and len(b) > 20000:
                break
        except Exception as e:
            print("%s [%s] EXC %s" % (name, imp, str(e)[:130]), flush=True)
