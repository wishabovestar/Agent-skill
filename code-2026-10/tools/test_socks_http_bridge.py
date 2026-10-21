#!/usr/bin/env python3
"""Smoke test for socks_http_bridge.py.

Spawns the bridge on a scratch port against the local SOCKS5 egress and
asserts the behaviours the Hermes updater depends on:

  1. a real HTTPS GET tunnels end-to-end through CONNECT
  2. a non-CONNECT method is rejected with 501 (not a hang / crash)
  3. an unreachable target either fails fast at CONNECT (502) or is
     optimistically acked by the upstream proxy (200) with the tunnel then
     closing -- i.e. never a hang -- and the listener survives the error
     path to serve the next request

Note on 3: some SOCKS upstreams (xray/freedom outbounds) reply success to
CONNECT before DNS/connect has actually resolved, so a 200 here is not a
bridge bug; what matters is that the client gets a prompt close rather than
a stuck socket, and that the listener stays up.

Exit code 0 = all passed. Run:  python test_socks_http_bridge.py
"""

import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRIDGE = HERE / "socks_http_bridge.py"
LISTEN_PORT = 8901
SOCKS = "127.0.0.1:10808"


def wait_for_port(port, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            s.settimeout(0.4)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False


def fetch_via_bridge(url, timeout=45):
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"https": f"http://127.0.0.1:{LISTEN_PORT}"})
    )
    with opener.open(url, timeout=timeout) as r:
        return r.status, r.read(4)


def probe(target, method=b"CONNECT", timeout=20):
    """Send a hand-rolled request.

    Returns (status_line, tunnel_closed). `tunnel_closed` is True when the
    peer closed the socket instead of holding it open, and None when we hit
    the timeout (which would itself be a failure).
    """
    with socket.create_connection(("127.0.0.1", LISTEN_PORT), timeout=10) as s:
        s.sendall(method + b" " + target + b" HTTP/1.1\r\nHost: x\r\n\r\n")
        s.settimeout(timeout)
        head = b""
        while b"\r\n" not in head:
            chunk = s.recv(256)
            if not chunk:
                return head, True
            head += chunk
        if b"200" not in head:
            return head, True  # error responses come with a closed connection
        s.settimeout(15)
        try:
            return head, s.recv(64) == b""
        except TimeoutError:
            return head, None


def code_of(head):
    parts = head.split()
    return int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None


def main():
    proc = subprocess.Popen(
        [sys.executable, str(BRIDGE), "--listen", f"127.0.0.1:{LISTEN_PORT}", "--socks", SOCKS],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    failures = []
    try:
        if not wait_for_port(LISTEN_PORT):
            print("FAIL: bridge never opened port")
            return 1

        # 1. real HTTPS through CONNECT
        try:
            status, _ = fetch_via_bridge("https://github.com/NousResearch/hermes-agent")
            if status == 200:
                print("PASS 1: HTTPS via CONNECT -> 200")
            else:
                failures.append(f"1: unexpected status {status}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"1: {exc}")

        # 2. non-CONNECT method rejected
        head, _ = probe(b"example.com:443", method=b"GET")
        if code_of(head) == 501:
            print("PASS 2: non-CONNECT -> 501 Not Implemented")
        else:
            failures.append(f"2: expected 501, got {head[:60]!r}")

        # 3a. unreachable target: fast 502, or optimistic 200 + prompt close
        head, closed = probe(b"nonexistent.invalid:443")
        code = code_of(head)
        if closed is None:
            failures.append("3a: bridge hung on unreachable target")
        elif code == 502:
            print("PASS 3a: unreachable -> 502 Bad Gateway")
        elif code == 200 and closed:
            print("PASS 3a: unreachable -> upstream acked 200, tunnel closed (no hang)")
        else:
            failures.append(f"3a: code={code} closed={closed}")

        # 3b. listener survived the error path
        try:
            status, _ = fetch_via_bridge("https://github.com/NousResearch/hermes-agent")
            if status == 200:
                print("PASS 3b: listener survived the error path")
            else:
                failures.append(f"3b: post-error status {status}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"3b: listener died after error: {exc}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        return 1
    print("\nALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
