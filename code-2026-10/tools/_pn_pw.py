import io, json, os, re, time
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
PROXY = "socks5://127.0.0.1:10810"

TARGETS = [
    ("enp_pure", "https://pure.amsterdamumc.nl/en/publications/social-dysfunction-and-default-mode-network-functional-integrity-/"),
    ("sd_122044", "https://www.sciencedirect.com/science/article/pii/S1053811926003599"),
    ("sd_122100", "https://www.sciencedirect.com/science/article/pii/S1053811926004155"),
    ("radboud", "https://repository.ubn.ru.nl/handle/2066/332280"),
]

def log(*a):
    print(*a, flush=True)

with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=True, proxy={"server": PROXY},
                           args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
    ctx = br.new_context(user_agent=UA, locale="en-US", viewport={"width": 1366, "height": 900},
                         extra_http_headers={"Accept-Language": "en-US,en;q=0.9"})
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
    page = ctx.new_page()
    for name, url in TARGETS:
        try:
            r = page.goto(url, wait_until="domcontentloaded", timeout=70000)
            time.sleep(9)
            html = page.content()
            io.open("pw_%s.html" % name, "w", encoding="utf-8").write(html)
            title = (page.title() or "")[:90]
            log("%s status=%s chars=%d title=%s" % (name, r.status if r else -1, len(html), title))
            links = page.eval_on_selector_all("a[href]", "els=>els.map(e=>e.href)")
            pdfs = sorted(set([u for u in links if re.search(r"(\.pdf|pdfft|bitstream|/files/)", u, re.I)]))
            log("   pdf_links=%d" % len(pdfs))
            for u in pdfs[:4]:
                log("   L %s" % u[:160])
            for i, u in enumerate(pdfs[:2]):
                try:
                    resp = ctx.request.get(u, timeout=90000)
                    body = resp.body()
                    fn = "pw_%s_%d.bin" % (name, i)
                    io.open(fn, "wb").write(body)
                    log("   DL%d %s size=%d ct=%s head=%s" % (i, resp.status, len(body),
                        (resp.headers.get("content-type") or "")[:30], body[:5]))
                except Exception as e:
                    log("   DL%d FAIL %s" % (i, str(e)[:120]))
        except Exception as e:
            log("%s FAIL %s" % (name, str(e)[:200]))
    br.close()
