#!/usr/bin/env python3
"""Minimal HTTP CONNECT proxy that tunnels through an upstream SOCKS5 proxy.

Why this exists
---------------
``hermes update`` downloads its release ZIP with ``urllib.request.urlretrieve``.
urllib honours ``HTTP_PROXY`` / ``HTTPS_PROXY`` but understands *only HTTP
proxies* -- not SOCKS5. On hosts where the only egress is a SOCKS5 listener
(e.g. xray-core on 127.0.0.1:10808 behind the GFW), the update therefore dies
with ``WinError 10060`` / "Remote end closed connection" while ``git`` and
``curl --socks5`` work fine.

Point ``HTTPS_PROXY`` at this bridge and urllib regains access:

    python socks_http_bridge.py --listen 127.0.0.1:8899 --socks 127.0.0.1:10808
    HTTPS_PROXY=http://127.0.0.1:8899 HTTP_PROXY=http://127.0.0.1:8899 hermes update

Pure stdlib -- no PySocks dependency. Only the CONNECT method is implemented
(that is all urllib needs for https:// URLs).
"""

import argparse
import select
import socket
import struct
import sys
import threading
import time

BUFSIZE = 65536
IDLE_TIMEOUT = 120


def socks5_connect(socks_host, socks_port, dst_host, dst_port, timeout=30):
    """Open a tunnel to (dst_host, dst_port) through a SOCKS5 proxy."""
    s = socket.create_connection((socks_host, socks_port), timeout=timeout)
    s.settimeout(timeout)
    # Greeting: version 5, one method, no-auth.
    s.sendall(b"\x05\x01\x00")
    resp = s.recv(2)
    if len(resp) < 2 or resp[0] != 0x05 or resp[1] != 0x00:
        s.close()
        raise OSError(f"SOCKS5 negotiation failed: {resp!r}")
    # Request: CONNECT, address.
    try:
        addr = b"\x01" + socket.inet_aton(dst_host)
    except OSError:
        host_b = dst_host.encode("idna") if dst_host else b""
        if len(host_b) > 255:
            s.close()
            raise OSError("hostname too long")
        addr = b"\x03" + bytes([len(host_b)]) + host_b
    s.sendall(b"\x05\x01\x00" + addr + struct.pack("!H", dst_port))
    rep = s.recv(4)
    if len(rep) < 4 or rep[0] != 0x05 or rep[1] != 0x00:
        s.close()
        raise OSError(f"SOCKS5 connect failed (rep={rep[1:2]!r})")
    # Consume the bound address.
    atyp = rep[3]
    if atyp == 0x01:
        s.recv(4)
    elif atyp == 0x03:
        n = s.recv(1)
        if n:
            s.recv(n[0])
    elif atyp == 0x04:
        s.recv(16)
    s.recv(2)
    s.settimeout(None)
    return s


def read_head(conn):
    """Read bytes up to and including the blank line ending the header block."""
    buf = b""
    while b"\r\n\r\n" not in buf and b"\n\n" not in buf:
        try:
            chunk = conn.recv(4096)
        except OSError:
            return None
        if not chunk:
            return None
        buf += chunk
        if len(buf) > 65536:
            return None
    return buf


def pump(a, b):
    """Bidirectional copy until either side closes."""
    try:
        while True:
            try:
                r, _, _ = select.select([a, b], [], [], IDLE_TIMEOUT)
            except (OSError, ValueError):
                return
            if not r:
                return
            for src in r:
                dst = b if src is a else a
                try:
                    data = src.recv(BUFSIZE)
                except OSError:
                    return
                if not data:
                    return
                try:
                    dst.sendall(data)
                except OSError:
                    return
    finally:
        for s in (a, b):
            try:
                s.close()
            except OSError:
                pass


def handle(conn, socks_addr, stats):
    try:
        head = read_head(conn)
        if not head:
            return
        line = head.split(b"\r\n", 1)[0].decode("latin-1", "replace")
        parts = line.split()
        if len(parts) < 2:
            return
        method, target = parts[0].upper(), parts[1]
        if method != "CONNECT":
            conn.sendall(b"HTTP/1.1 501 Not Implemented\r\n\r\n")
            stats["rejected"] += 1
            return
        host, _, port_s = target.rpartition(":")
        port = int(port_s) if port_s.isdigit() else 443
        if not host:
            conn.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            return
        try:
            upstream = socks5_connect(socks_addr[0], socks_addr[1], host, port)
        except Exception as exc:  # noqa: BLE001 - report and close
            stats["failed"] += 1
            try:
                conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            except OSError:
                pass
            print(f"  ! {host}:{port} -> {exc}", flush=True)
            return
        conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        stats["tunnels"] += 1
        print(f"  -> CONNECT {host}:{port} OK", flush=True)
        pump(conn, upstream)
    except Exception as exc:  # noqa: BLE001
        print(f"  ! handler error: {exc}", flush=True)
    finally:
        try:
            conn.close()
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--listen", default="127.0.0.1:8899")
    ap.add_argument("--socks", default="127.0.0.1:10808")
    args = ap.parse_args()

    lhost, _, lport = args.listen.rpartition(":")
    shost, _, sport = args.socks.rpartition(":")
    listen_addr = (lhost or "127.0.0.1", int(lport or 8899))
    socks_addr = (shost or "127.0.0.1", int(sport or 10808))

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(listen_addr)
    srv.listen(64)
    stats = {"tunnels": 0, "failed": 0, "rejected": 0}
    print(
        f"socks_http_bridge: HTTP CONNECT {listen_addr[0]}:{listen_addr[1]}"
        f" -> SOCKS5 {socks_addr[0]}:{socks_addr[1]}",
        flush=True,
    )
    try:
        while True:
            try:
                conn, _peer = srv.accept()
            except OSError:
                time.sleep(0.2)
                continue
            threading.Thread(
                target=handle, args=(conn, socks_addr, stats), daemon=True
            ).start()
    except KeyboardInterrupt:
        print(f"\nshutting down: {stats}", flush=True)
    finally:
        srv.close()


if __name__ == "__main__":
    sys.exit(main())
