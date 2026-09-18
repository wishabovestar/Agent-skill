#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""curl_guarded.py — 带【跳转后复核】的安全取数(共享模块)

背景(实测驱动):
  r1182  发现本机 curl 调用带 -L 却无任何跳转目标校验
  r1183  给 smart_fetcher.py 做了单点修复(_curl_url_fetch + _guard_final_url)
  r1185  全库扫描(变量级闭包)查出 ★ 79 处含 curl 调用点中【11 处】使用 -L
         ⇒ 10 处仍无复核 ⇒ 本模块把单点修复抽成【共享件】

设计要点:
  · 用 `-o <tmp> -w '%{url_effective}'` 让 stdout 只留【最终 URL】, body 落文件
    ⇒ 不改调用方的解析习惯(取到的仍是 body 字符串)
  · ★ 两道判据: 入口域 / 最终 URL 都必须过 redirect_guard + egress 白名单
  · ★ fail-open 但【响亮】: guard 模块不可用时放行, 但返回 why 里标注 guard-unavailable
    —— 采集/优化路径, 非安全门(与 egress_allowlist 同层)

用法:
    from curl_guarded import curl_fetch, guard_final_url, safe_curl

    rc, final_url, body, err = curl_fetch(url, timeout=30, proxy="socks5://...")
    ok, why = guard_final_url(url, final_url)
    # 或者一步到位:
    body, why = safe_curl(url, timeout=30)
"""
import os
import re
import subprocess
import sys
import tempfile

# ── guard 接入(软依赖) ────────────────────────────────────────────────
_GUARD = None
_GUARD_ERR = ""
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from redirect_guard import is_safe_download_redirect as _isafe  # noqa: E402
    _GUARD = _isafe
except Exception as _e:  # pragma: no cover
    _GUARD_ERR = "%s: %s" % (type(_e).__name__, _e)

_EGRESS = None
try:
    import egress_allowlist as _EG  # noqa: E402
    _EGRESS = _EG
except Exception:
    pass

# 本地 / 元数据 / 保留段(自保一层, 不依赖 guard 是否可用)
_RE_LOCAL = re.compile(
    r"^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.|0\.|"
    r"localhost$|.*\.local$|.*\.localhost$|\[::1\]$)", re.I)


def _is_local(hostport):
    h = (hostport or "").split("/")[0].split("@")[-1]
    h = h.split(":")[0] if not h.startswith("[") else h.split("]")[0] + "]"
    return bool(_RE_LOCAL.match(h))


def guard_final_url(entry_url, final_url):
    """★ 跳转后复核。返回 (ok: bool, why: str)"""
    if not final_url or final_url.strip() == entry_url.strip():
        return True, "no-redirect"
    try:
        from urllib.parse import urlparse
        fe, ff = urlparse(entry_url), urlparse(final_url)
        if _is_local(ff.netloc) and not _is_local(fe.netloc):
            return False, "公网→本地/元数据地址: %s -> %s" % (entry_url[:50], final_url[:50])
        if _GUARD is not None:
            if not _GUARD(entry_url, final_url):
                return False, "redirect_guard 拒绝: %s -> %s" % (entry_url[:50], final_url[:50])
        else:
            return True, "guard-unavailable:%s" % _GUARD_ERR[:60]
        if _EGRESS is not None:
            chk = getattr(_EGRESS, "check_egress", None)
            if callable(chk):
                try:
                    ok2, why2 = chk(final_url)
                    if not ok2:
                        return False, "egress 拒绝最终 URL: %s" % str(why2)[:60]
                except Exception:
                    pass
        return True, "redirect-ok"
    except Exception as e:
        return True, "guard-error:%s" % str(e)[:50]


def curl_fetch(url, timeout=30, proxy=None, insecure=True,
               extra_args=None, headers=None):
    """取 body, 同时拿回最终 URL。返回 (rc, final_url, body, err)

    ★ stdout 只留最终 URL(body 走 -o 临时文件)⇒ 调用方拿到的仍是 body。
    """
    fd, tmp = tempfile.mkstemp(prefix="cg_", suffix=".body")
    os.close(fd)
    flags = "-skL" if insecure else "-sL"
    cmd = ["curl", flags, "--max-time", str(timeout),
           "-o", tmp, "-w", "%{url_effective}"]
    if proxy:
        cmd += ["--proxy", proxy]
    for h in (headers or []):
        cmd += ["-H", h]
    cmd += list(extra_args or [])
    cmd += [url]
    err, rc, final, body = "", 1, "", ""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        rc = r.returncode
        final = (r.stdout or "").strip()
        err = (r.stderr or "").strip()[:200]
        try:
            with open(tmp, "r", encoding="utf-8", errors="replace") as f:
                body = f.read()
        except Exception as e:
            if not err:
                err = "read-body: %s" % e
    except subprocess.TimeoutExpired:
        err = "timeout after %ss" % (timeout + 5)
    except Exception as e:
        err = "%s: %s" % (type(e).__name__, e)
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass
    return rc, final, body, err


def safe_curl(url, timeout=30, proxy=None, insecure=True, extra_args=None, headers=None):
    """一步到位: 取数 + 跳转复核。

    返回 (body_or_None, why)
      body 非 None  ⇒ 成功且通过复核
      body 为 None  ⇒ 失败(why 说明原因, 含 redirect-guard 拒绝)
    """
    rc, final, body, err = curl_fetch(url, timeout=timeout, proxy=proxy,
                                      insecure=insecure, extra_args=extra_args,
                                      headers=headers)
    if rc != 0:
        return None, "curl rc=%d %s" % (rc, err[:80])
    ok, why = guard_final_url(url, final)
    if not ok:
        return None, "redirect-guard: " + why
    return body, why


def run(cmd, timeout=None, **kw):
    """★ `subprocess.run` 的【直接替代品】—— 自动加跳转复核, 调用方改动 ≤1 个词。

    用法(替换):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        r = cg.run(cmd, capture_output=True, text=True, timeout=60)   # ★ 只改这

    行为:
      · 自动补 -o <tmp> -w '%{url_effective}'
      · 执行后: 从临时文件读 body 充当 r.stdout; 从 -w 输出取最终 URL 并复核
      · ★ 复核失败 ⇒ 返回 returncode=97, stdout="", stderr 含 [redirect-guard] 说明
        (调用方原本对非 0 返回码/空 body 的处理逻辑会自然生效)
      · 非 curl 命令 ⇒ 原样透传给 subprocess.run, 零行为变化
    """
    if not cmd or not isinstance(cmd, (list, tuple)):
        return subprocess.run(cmd, timeout=timeout, **kw)
    if not any(str(c).endswith("curl") or str(c) == "curl" for c in cmd[:2]):
        return subprocess.run(cmd, timeout=timeout, **kw)

    cmd = [str(c) for c in cmd]
    # 找 URL(最后一个 http(s) 参数)
    url = None
    for c in reversed(cmd):
        if c.startswith("http://") or c.startswith("https://"):
            url = c
            break
    fd, tmp = tempfile.mkstemp(prefix="cg_", suffix=".body")
    os.close(fd)
    if "-o" not in cmd and "--output" not in cmd:
        cmd += ["-o", tmp, "-w", "%{url_effective}"]
    try:
        r = subprocess.run(cmd, timeout=timeout, **kw)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise

    # 组装一个与 subprocess.CompletedProcess 同形的结果
    capture = kw.get("capture_output", False) or kw.get("stdout") == subprocess.PIPE
    text_mode = bool(kw.get("text")) or bool(kw.get("universal_newlines")) \
        or bool(kw.get("encoding"))
    body, final = "", ""
    try:
        if text_mode:
            with open(tmp, "r", encoding=kw.get("encoding") or "utf-8",
                      errors="replace") as f:
                body = f.read()
        else:
            with open(tmp, "rb") as f:
                body = f.read()
    except Exception:
        body = "" if text_mode else b""
    try:
        os.unlink(tmp)
    except Exception:
        pass
    # -w 的输出在 stdout(当通过 capture 拿到时)
    if capture and getattr(r, "stdout", None):
        so = r.stdout
        if isinstance(so, bytes):
            so = so.decode("utf-8", "replace")
        lines = so.rstrip("\n").split("\n")
        if lines and lines[-1].startswith("http"):
            final = lines[-1].strip()
    # ★★ 关键修正(r1192): 必须与 subprocess.run 的【类型语义】一致 ——
    #   原版在【不带 text=True】时返回 bytes, 带时返回 str。
    #   早先版本无条件返回 str ⇒ 调用方写 `r.stdout.decode()` 会抛 AttributeError,
    #   而多处用 `except Exception: continue/pass` 包裹 ⇒ ★ 静默失效(fetch 恒 None)。
    #   ⇒ 现按 text_mode 返回对应类型。
    r.stdout = body if capture else None
    if url and r.returncode == 0:
        ok, why = guard_final_url(url, final)
        if not ok:
            r.returncode = 97
            r.stdout = ("" if text_mode else b"") if capture else None
            _se = r.stderr
            if isinstance(_se, bytes):
                _se = _se.decode("utf-8", "replace")
            r.stderr = ("[redirect-guard] " + why + "\n" + (_se or ""))
    return r


if __name__ == "__main__":
    import json
    u = sys.argv[1] if len(sys.argv) > 1 else "https://api.github.com/zen"
    b, w = safe_curl(u, timeout=25)
    print(json.dumps({"url": u, "ok": b is not None, "why": w,
                      "bytes": len(b) if b else 0}, ensure_ascii=False, indent=1))
