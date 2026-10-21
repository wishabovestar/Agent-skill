import io, os, re, time
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
PROXY = "socks5://127.0.0.1:10810"
OUT = "D:/hermes/analysis/_pn/"

TARGETS = [
    ("enp", "https://pure.amsterdamumc.nl/files/205589672/Social-dysfunction-and-default-mode-network-functional-integrity-in-neuropsychiatric-disorders.pdf", "bw_enp.pdf"),
    ("sd122044", "https://www.sciencedirect.com/science/article/pii/S1053811926003599", "bw_sd122044.pdf"),
    ("sd122100", "https://www.sciencedirect.com/science/article/pii/S1053811926004155", "bw_sd122100.pdf"),
]

def log(*a):
    print(*a, flush=True)

with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=False, proxy={"server": PROXY},
                           args=["--disable-blink-features=AutomationControlled", "--no-first-run"])
    ctx = br.new_context(user_agent=UA, locale="en-US", viewport={"width": 1400, "height": 950},
                         accept_downloads=True, extra_http_headers={"Accept-Language": "en-US,en;q=0.9"})
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
    page = ctx.new_page()

    for name, url, out in TARGETS:
        ok = False
        for attempt in range(4):
            try:
                r = page.goto(url, wait_until="domcontentloaded", timeout=90000)
                time.sleep(14)
                ct = (r.headers.get("content-type") if r else "") or ""
                if "pdf" in ct.lower():
                    b = r.body()
                    io.open(OUT + out, "wb").write(b)
                    log("%s attempt%d PDF status=%s size=%d head=%s" % (name, attempt, r.status, len(b), b[:5]))
                    ok = True
                    break
                title = (page.title() or "")[:60]
                log("%s attempt%d status=%s title=%s" % (name, attempt, r.status if r else -1, title))
                if "moment" not in title.lower() and attempt > 0:
                    html = page.content()
                    io.open(OUT + "bw_%s.html" % name, "w", encoding="utf-8").write(html)
                    log("   cleared chars=%d" % len(html))
                    cand = page.eval_on_selector_all("a[href]", "els=>els.map(e=>e.href).filter(h=>/pdfft|\.pdf/i.test(h))")
                    log("   pdf_hrefs=%d %s" % (len(cand), (cand[:1] or [""])[0][:140]))
                    if cand:
                        r2 = page.goto(cand[0], wait_until="domcontentloaded", timeout=90000)
                        time.sleep(10)
                        ct2 = (r2.headers.get("content-type") if r2 else "") or ""
                        if "pdf" in ct2.lower():
                            b = r2.body()
                            io.open(OUT + out, "wb").write(b)
                            log("   PDF2 status=%s size=%d head=%s" % (r2.status, len(b), b[:5]))
                            ok = True
                    break
            except Exception as e:
                log("%s attempt%d EXC %s" % (name, attempt, str(e)[:140]))
                time.sleep(3)
        log("%s RESULT ok=%s" % (name, ok))
    br.close()
