import re, html as H

raw = open(r"D:/hermes/data/intel/logs/_cl_docket_20260918.html", encoding="utf-8").read()
for n in [155, 156, 157, 158, 159]:
    m = re.search(r'id="entry-%d"' % n, raw)
    if not m:
        print(f"#{n}: NOT FOUND"); continue
    seg = raw[m.start():m.start() + 2600]
    seg = re.sub(r"<script.*?</script>", " ", seg, flags=re.S)
    txt = H.unescape(re.sub(r"<[^>]+>", " ", seg))
    txt = re.sub(r"\s+", " ", txt).strip()
    print(f"#{n}: {txt[:300]}")
    print("-" * 60)
