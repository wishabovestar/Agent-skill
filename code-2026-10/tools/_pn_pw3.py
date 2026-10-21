import io, os, time
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
PROXY = "socks5://127.0.0.1:10810"
PUB = "https://pure.amsterdamumc.nl/en/publications/social-dysfunction-and-default-mode-network-functional-integrity-/"
PDF = "https://pure.amsterdamumc.nl/files/205589672/Social-dysfunction-and-default-mode-network-functional-integrity-in-neuropsychiatric-disorders.pdf"
OUT = "D:/hermes/analysis/_pn/"

def log(*a):
    print(*a, flush=True)

with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=True, proxy={"server": PROXY},
                           args=["--disable-blink-features=AutomationControlled"])
    ctx = br.new_context(user_agent=UA, locale="en-US", accept_downloads=True)
    page = ctx.new_page()
    page.goto(PUB, wait_until="domcontentloaded", timeout=80000)
    time.sleep(5)
    log("pub ok title=%s" % (page.title() or "")[:60])
    try:
        with page.expect_response(lambda r: "pdf" in (r.headers.get("content-type") or "").lower(), timeout=90000) as ri:
            page.evaluate("u=>{window.location.href=u}", PDF)
        resp = ri.value
        body = resp.body()
        io.open(OUT + "bw_enp.pdf", "wb").write(body)
        log("NAV_PDF status=%s size=%d head=%s" % (resp.status, len(body), body[:5]))
    except Exception as e:
        log("NAV_PDF FAIL %s" % str(e)[:160])
        try:
            r = page.goto(PDF, referer=PUB, timeout=90000)
            log("GOTO status=%s ct=%s" % (r.status if r else -1, (r.headers.get("content-type") if r else "")[:40]))
            if r:
                b = r.body()
                io.open(OUT + "bw_enp.pdf", "wb").write(b)
                log("GOTO size=%d head=%s" % (len(b), b[:5]))
        except Exception as e2:
            log("GOTO FAIL %s" % str(e2)[:160])
    br.close()
