import io, os, re, time
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
PROXY = "socks5://127.0.0.1:10810"
OUT = "D:/hermes/analysis/_pn/"

def log(*a):
    print(*a, flush=True)

def save_dl(dl, name):
    path = OUT + name
    dl.save_as(path)
    sz = os.path.getsize(path)
    with io.open(path, "rb") as f:
        head = f.read(5)
    log("   SAVED %s size=%d head=%s" % (name, sz, head))
    return sz

with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=False, proxy={"server": PROXY},
                           args=["--disable-blink-features=AutomationControlled", "--no-first-run",
                                 "--no-default-browser-check"])
    ctx = br.new_context(user_agent=UA, locale="en-US", viewport={"width": 1400, "height": 950},
                         accept_downloads=True,
                         extra_http_headers={"Accept-Language": "en-US,en;q=0.9"})
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
    page = ctx.new_page()

    # 1) ENP via user-gesture click on the publication page
    try:
        page.goto("https://pure.amsterdamumc.nl/en/publications/social-dysfunction-and-default-mode-network-functional-integrity-/",
                  wait_until="domcontentloaded", timeout=80000)
        time.sleep(6)
        link = page.query_selector("a[href$='.pdf']")
        log("enp_click link=%s" % (link.get_attribute("href")[:90] if link else "NONE"))
        if link:
            with page.expect_download(timeout=90000) as di:
                link.click()
            save_dl(di.value, "bw_enp.pdf")
    except Exception as e:
        log("enp FAIL %s" % str(e)[:200])

    # 2) ScienceDirect gold OA x2
    for tag, pii in [("122044", "S1053811926003599"), ("122100", "S1053811926004155")]:
        try:
            page.goto("https://www.sciencedirect.com/science/article/pii/%s" % pii,
                      wait_until="domcontentloaded", timeout=90000)
            for i in range(10):
                time.sleep(4)
                t = page.title() or ""
                if "Just a moment" not in t:
                    break
            t = page.title() or ""
            html = page.content()
            io.open(OUT + "bw_sd_%s.html" % tag, "w", encoding="utf-8").write(html)
            log("sd_%s title=%s chars=%d" % (tag, t[:70], len(html)))
            cand = page.eval_on_selector_all(
                "a[href]", "els=>els.map(e=>e.href).filter(h=>/pdfft|pdf/i.test(h))")
            log("   pdf_hrefs=%d %s" % (len(cand), (cand[:1] or [""])[0][:150]))
            if cand:
                with page.expect_download(timeout=120000) as di:
                    page.goto(cand[0])
                save_dl(di.value, "bw_sd_%s.pdf" % tag)
        except Exception as e:
            log("sd_%s FAIL %s" % (tag, str(e)[:200]))

    br.close()
