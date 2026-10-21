#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Start the ONE host gateway (multiplex architecture) fully DETACHED.

Hermes >= v0.21.5 with gateway.multiplex_profiles: true forbids per-profile
gateways. The single host gateway (default profile) serves every profile.
Launched DETACHED so an explorer.exe restart cannot take it down.
"""
import os, sys, subprocess, time, json

HERMES_HOME = r"D:\hermes\hermes-data"
HERMES_EXE  = r"C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.exe"

env = os.environ.copy()
env["PYTHONUTF8"] = "1"
env["PYTHONIOENCODING"] = "utf-8"
env["HERMES_HOME"] = HERMES_HOME
env.pop("_HERMES_GATEWAY", None)
env["no_proxy"] = ("ilinkai.weixin.qq.com,novac2c.cdn.weixin.qq.com,*.weixin.qq.com,"
                   "api.sgroup.qq.com,api.imdgrp.com,open.feishu.cn,localhost,127.0.0.1")
env["NO_PROXY"] = env["no_proxy"]

cap = os.path.join(r"D:\hermes\analysis\gw_capture",
                   time.strftime("host_gateway_%Y%m%d_%H%M%S.out.txt"))
os.makedirs(os.path.dirname(cap), exist_ok=True)

out = open(cap, "w", encoding="utf-8", errors="replace")
p = subprocess.Popen(
    [HERMES_EXE, "--profile", "default", "gateway", "run"],
    cwd=HERMES_HOME,
    env=env,
    stdout=out,
    stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
)
print(json.dumps({"spawned_pid": p.pid, "capture": cap}))
