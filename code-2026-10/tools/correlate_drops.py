# -*- coding: utf-8 -*-
"""Correlate monitor/DP-audio link drops (Kernel-PnP 1010) with AweSun remote sessions
   and with machine restarts. Reports POSITIVE and NEGATIVE results honestly."""
import re, datetime, sys

LOG = r"C:\Users\Administrator\AppData\Roaming\Oray\AweSun\log\history.log"

# ---- Source A: monitor link drops ----
drops = """2026-07-19 12:08:07
2026-07-19 16:08:04
2026-07-19 16:49:02
2026-07-19 23:13:39
2026-07-20 07:58:16
2026-07-23 00:51:45
2026-07-23 07:38:21
2026-07-24 01:18:36
2026-07-24 09:26:15
2026-07-25 00:48:37
2026-07-25 13:08:18
2026-07-26 16:29:07
2026-07-27 08:31:20
2026-08-26 23:00:22
2026-09-04 08:44:48
2026-09-12 10:30:32
2026-09-13 12:22:20
2026-09-17 00:30:34""".strip().split("\n")
drops = [datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S") for s in drops]

# ---- Source B: AweSun remote-control session starts ----
raw = open(LOG, "rb").read().decode("gbk", errors="replace")
starts = []
for line in raw.splitlines():
    m = re.match(r"\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(.*)", line)
    if m and "开始桌面控制" in m.group(2):
        starts.append(datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))

# ---- Source C: machine restart initiation times (1074/6006) ----
restarts = """2026-07-23 09:08:55
2026-07-25 12:43:55
2026-07-26 15:29:28
2026-08-03 10:59:47
2026-08-04 11:10:20
2026-08-11 07:30:08
2026-08-16 23:18:08
2026-08-23 08:12:44
2026-08-23 12:25:26
2026-08-26 08:26:33
2026-08-29 11:16:26
2026-08-29 14:10:50
2026-09-09 15:09:07
2026-09-12 10:20:51
2026-09-12 11:56:07
2026-09-12 17:50:13
2026-09-13 09:43:29
2026-09-13 13:44:40
2026-09-13 16:13:09
2026-09-15 08:33:15
2026-09-15 09:19:20
2026-09-16 08:07:07
2026-09-16 15:53:29""".split("\n")
restarts = [datetime.datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S") for s in restarts]

print("=" * 78)
print("A. drops=%d   B. AweSun session starts=%d (%s .. %s)" % (
    len(drops), len(starts), starts[0], starts[-1]))
print("   C. restarts=%d" % len(restarts))
print("=" * 78)

def match(src_name, times, window):
    print("\n--- correlation: drop vs %s (window +-%ds) ---" % (src_name, window))
    hit = 0
    for d in drops:
        near = [t for t in times if abs((d - t).total_seconds()) <= window]
        if near:
            hit += 1
            best = min(near, key=lambda t: abs((d - t).total_seconds()))
            print("  HIT  drop %s   <- %s %s  (delta %+ds)" % (
                d, src_name, best, int((d - best).total_seconds())))
        else:
            print("  MISS drop %s   (no %s within +-%ds)" % (d, src_name, window))
    print("  ==> %s: %d/%d drops have a nearby %s (%.1f%%)" % (
        src_name, hit, len(drops), src_name, 100.0 * hit / len(drops)))
    return hit

match("AweSun session", starts, 180)
match("restart", restarts, 600)

print("\n" + "=" * 78)
print("B. Are the drops clustered or spread? gap analysis")
prevs = None
for d in drops:
    if prevs is not None:
        gap = (d - prevs).total_seconds() / 86400.0
        print("  %s  (+%.2f days)" % (d, gap))
    else:
        print("  %s  (start)" % d)
    prevs = d

print("\n" + "=" * 78)
print("C. AweSun session DURATION distribution (how long the remote screen works)")
durs = []
cur = None
for line in raw.splitlines():
    m = re.match(r"\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(.*)", line)
    if not m:
        continue
    t = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    if "开始桌面控制" in m.group(2):
        cur = t
    elif "结束桌面控制" in m.group(2) and cur is not None:
        durs.append((cur, (t - cur).total_seconds()))
        cur = None
if durs:
    secs = sorted(x[1] for x in durs)
    print("  n=%d  min=%.0fs  median=%.0fs  max=%.0fs" % (
        len(secs), secs[0], secs[len(secs)//2], secs[-1]))
    print("  sessions shorter than 60s: %d (%.1f%%)" % (
        sum(1 for s in secs if s < 60), 100.0*sum(1 for s in secs if s < 60)/len(secs)))
    print("  sessions longer than 300s: %d (%.1f%%)" % (
        sum(1 for s in secs if s > 300), 100.0*sum(1 for s in secs if s > 300)/len(secs)))
    print("  last 10 sessions (start, duration):")
    for s, d in durs[-10:]:
        print("     %s  %.0fs" % (s, d))
