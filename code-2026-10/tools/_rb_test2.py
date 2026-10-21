import hashlib

dates = {
 "2026-08-05":6, "2026-08-08":7, "2026-08-15":6, "2026-08-22":0,
 "2026-08-29":4, "2026-09-05":4, "2026-09-12":7, "2026-09-19":None,
}
f8 = fh = 0
for d, rec in dates.items():
    h = hashlib.md5(d.encode()).hexdigest()
    a = int(h[:8],16) % 8
    b = int(h,16) % 8
    hit_a = "OK" if a == rec else "  "
    hit_b = "OK" if b == rec else "  "
    if rec is not None:
        f8 += (a == rec); fh += (b == rec)
    print("%s rec=%s  first8=%d[%s]  full=%d[%s]" % (d, rec, a, hit_a, b, hit_b))
print("matches: first8=%d full=%d" % (f8, fh))
