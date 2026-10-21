#!/usr/bin/env python3
"""
browser-act CLI entry for Hermes.
Auto-manages Python 3.12 env.
Usage: browser-act <args...>
"""
import sys, subprocess
from pathlib import Path

WRAPPER = Path(__file__).parent / "browser_act_wrapper.py"

def main():
    if not WRAPPER.exists():
        print(f"ERROR: wrapper not found at {WRAPPER}", file=sys.stderr)
        sys.exit(1)
    result = subprocess.run(
        [sys.executable, str(WRAPPER)] + sys.argv[1:],
        capture_output=False
    )
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
