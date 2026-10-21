#!/usr/bin/env python3
"""Query GitHub API for repo metadata (primary source, no auth needed for public)."""
import json, subprocess, sys

REPOS = [
    "gpaw/gpaw",
    "pierre-24/gpaw",                     # fallback
    "shankar-siva/JDFTx",
    "JDFTx/JDFTx",
    "rescu-dev/RESCU",
    "Advanced-Nanoscale-Design/RESCU",
    "BigDFT-group/bigdft-suite",
    "ACEsuit/mace",
    "ACEsuit/mace-torch",                 # may 404
    "mir-group/nequip",
    "mir-group/allegro",
    "CederGroupHub/chgnet",
    "materialsvirtuallab/m3gnet",
    "materialsvirtuallab/matgl",
    "microsoft/mattersim",
    "max-centre/components/devicexlib",
    "amd/devicexlib",
]

def gh(path):
    r = subprocess.run(
        ["curl", "-s", "-m", "25", "-H", "Accept: application/vnd.github+json",
         "https://api.github.com/" + path], capture_output=True)
    try:
        return json.loads(r.stdout.decode("utf-8", "replace"))
    except Exception:
        return None

for full in REPOS:
    d = gh("repos/" + full)
    if not d or d.get("message"):
        print("%-45s  -> NOT FOUND / %s" % (full, (d or {}).get("message", "?")))
        continue
    print("%-45s  stars=%-6s pushed=%s  lang=%s" % (
        d["full_name"], d["stargazers_count"], (d.get("pushed_at") or "")[:10],
        d.get("language")))
    print("      desc: %s" % (d.get("description") or "")[:160])
