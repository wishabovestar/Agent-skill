import hashlib

def first8_mod8(d):
    h = hashlib.md5(d.encode()).hexdigest()
    return int(h[:8], 16) % 8

def full_mod8(d):
    h = hashlib.md5(d.encode()).hexdigest()
    return int(h, 16) % 8

# Note says 2026-08-05 and 2026-08-15 both mod8=6 (服务发现, index6)
for d in ["2026-08-05", "2026-08-15", "2026-08-29", "2026-09-12", "2026-09-19"]:
    print(d, "first8=%d" % first8_mod8(d), "full=%d" % full_mod8(d))
