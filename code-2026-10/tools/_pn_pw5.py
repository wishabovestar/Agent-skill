import io, os, time
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
OUT = "D:/hermes/analysis/_pn/"
TARGETS = [
    ("d_enp", "https://pure.amsterdamumc.nl/files/205589672/Social-dysfunction-and-default-mode-network-functional-integrity-in-neuropsychiatric-disorders.pdf", "d_enp.pdf"),
    ("d_sd122044", "https://www.sciencedirect.com/science/article/pii/S1053811926003599", "d_sd122044.pdf"),
]

def log(*a):
    print(*a, flush=True)

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        "D:/hermes/analysis/_pn/chprof", channel="chrome", headless=False,
        user_agent=UA, locale="en-US", viewport={"width": 1400, "height": 950}, accept_downloads=True)
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    for name, url, out in TARGETS:
        ok = False
        for a in range(3):
            try:
                r = page.goto(url, wait_until="domcontentloaded", timeout=90000)
                time.sleep(16)
                ct = (r.headers.get("content-type") if r else "") or ""
                if "pdf" in ct.lower():
                    b = r.body()
                    io.open(OUT + out, "wb").write(b)
                    log("%s a%d PDF status=%s size=%d head=%s" % (name, a, r.status, len(b), b[:5]))
                    ok = True
                    break
                t = (page.title() or "")[:60]
                log("%s a%d status=%s title=%s chars=%d" % (name, a, r.status if r else -1, t, len(page.content())))
                if "moment" not in t.lower():
                    io.open(OUT + "bw_%s.html" % name, "w", encoding="utf-8").write(page.content())
                    cand = page.eval_on_selector_all("a[href]", "els=>els.map(e=>e.href).filter(h=>/pdfft|\\.pdf/i.test(h))")
                    log("   hrefs=%d %s" % (len(cand), (cand[:1] or [""])[0][:140]))
                    if cand:
                        r2 = page.goto(cand[0], wait_until="domcontentloaded", timeout=90000)
                        time.sleep(12)
                        ct2 = (r2.headers.get("content-type") if r2 else "") or ""
                        log("   pdf2 status=%s ct=%s" % (r2.status if r2 else -1, ct2[:30]))
                        if "pdf" in ct2.lower():
                            b = r2.body()
                            io.open(OUT + out, "wb").write(b)
                            log("   PDF2 size=%d head=%s" % (len(b), b[:5]))
                            ok = True
                    break
            except Exception as e:
                log("%s a%d EXC %s" % (name, a, str(e)[:140]))
                time.sleep(2)
        log("%s RESULT ok=%s" % (name, ok))
    ctx.close()
