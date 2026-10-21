import asyncio, os, aiohttp

URL = "https://novac2c.cdn.weixin.qq.com/"


async def probe(tag, trust_env, no_proxy=None):
    old = os.environ.get("NO_PROXY")
    if no_proxy is not None:
        os.environ["NO_PROXY"] = no_proxy
        os.environ["no_proxy"] = no_proxy
    try:
        async with aiohttp.ClientSession(trust_env=trust_env) as s:
            try:
                async with s.post(URL, data=b"x" * 32,
                                  headers={"Content-Type": "application/octet-stream"}) as r:
                    body = (await r.text())[:60].replace("\n", " ")
                    print("%-28s http=%s body=%s" % (tag, r.status, body))
            except Exception as e:
                print("%-28s EXC %s: %s" % (tag, type(e).__name__, str(e)[:80]))
    finally:
        if no_proxy is not None and old is not None:
            os.environ["NO_PROXY"] = old
            os.environ["no_proxy"] = old


async def main():
    print("ENV NO_PROXY =", os.environ.get("NO_PROXY"))
    print("ENV HTTPS_PROXY =", os.environ.get("HTTPS_PROXY"))
    await probe("trust_env=True  (as-is)", True)
    await probe("trust_env=False (direct)", False)
    await probe("trust_env=True  .weixin.qq.com", True, ".weixin.qq.com")
    await probe("trust_env=True  no_proxy=*", True, "*")
    await probe("trust_env=False (direct2)", False)


asyncio.run(main())
