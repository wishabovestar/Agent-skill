import hashlib

d = '2026-08-08'
h = int(hashlib.md5(d.encode()).hexdigest(), 16)
print('md5 hash % 8 =', h % 8)
print('simple mod =', int('20260808') % 8)
