import ast, os, sys, importlib.util

SCRIPTS = r"D:/hermes/hermes-data/profiles/mybot/scripts"
names = ["daily_report.py","rss_cache.py","user_profiler.py","push_paper_links_wrapper.py",
         "push_papers_wrapper.py","run_watchdog_v3.py","sleep_consolidation.py",
         "ehentai_v3_weekly.py","hindsight_memory_optimizer.py","vps_poll.py","daydream_engine_v3.py"]

STDLIB = set(sys.stdlib_module_names)

def top_imports(path):
    try:
        tree = ast.parse(open(path, encoding='utf-8', errors='ignore').read())
    except Exception as e:
        return [f"<parse error {e}>"]
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names: mods.add(a.name.split('.')[0])
        elif isinstance(n, ast.ImportFrom):
            if n.module and n.level == 0: mods.add(n.module.split('.')[0])
    return sorted(mods)

print("python:", sys.executable)
for f in names:
    p = os.path.join(SCRIPTS, f)
    mods = top_imports(p)
    missing = []
    local = set()
    for m in mods:
        if m in STDLIB: continue
        # local module next to script?
        if os.path.exists(os.path.join(SCRIPTS, m + ".py")):
            local.add(m); continue
        if importlib.util.find_spec(m) is None:
            missing.append(m)
    flag = "  <-- MISSING" if missing else ""
    print(f"{f:35s} third-party={[m for m in mods if m not in STDLIB]}")
    if missing: print(f"    MISSING: {missing}{flag}")
