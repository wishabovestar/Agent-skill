#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
补投:把 cron 投递失败项的输出,节流重投到指定通道。

背景(2026-09-19 实测):
  微信通道 iLink 限流(ret=-2 errmsg=prepare failed)导致 25 个 cron job 的
  `last_delivery_error` 非空;看门狗已重试 3 次到上限(watchdog_retry_state.json n=3)。
  直接批量补投会【加重限流】—— 必须节流 + 只投有真实内容且有价值的项。

设计约束(每条都有理由):
  * 只投 no_agent=False(agent job)⇒ 脚本直出 job 的正常路径本就是"没事",补投=发噪声。
    例外:脚本 job 若输出不含常规 OK 标志,另行判断(本脚本默认跳过)。
  * 跳过名称/产物含"静默"的 ⇒ 正常路径应 0 字节,补投是错的。
  * 跳过超过 MAX_AGE_H 小时的 ⇒ 过期内容补投无意义(如 17 天前的用户画像更新)。
  * 从产物中只取 `## Response` 之后的正文 ⇒ 前面是 Prompt/步骤,属内部记录。
  * 每条间隔 THROTTLE_S 秒 ⇒ 微信退避窗口是 48s,必须大于它。
  * 连续 THROTTLE_S 次超时/失败即【整体中止】⇒ 不要在限流中死磕,失败也是信号。

用法:
  python redeliver_failed.py --dry-run          # 只列计划,不发送
  python redeliver_failed.py --target qqbot     # 投到 qqbot(top-level 名)
  python redeliver_failed.py --target weixin:{chat_id}
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROFILE = r"<PROFILE_ROOT>"
HERMES = r"C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.exe"
JOBS = os.path.join(PROFILE, "cron", "jobs.json")
OUTDIR = os.path.join(PROFILE, "cron", "output")

MAX_AGE_H = 72.0        # 超过 3 天的直接跳过
THROTTLE_S = 75.0       # 每条间隔(> 微信 48s 退避窗口)
SEND_TIMEOUT = 60       # 单条投递超时
MAX_CONSEC_FAIL = 2     # 连续失败到此数即整体中止
SILENT_MARKERS = ("静默",)


def is_silent(name, prompt):
    blob = (name or "") + (prompt or "")
    return any(m in blob for m in SILENT_MARKERS)


def latest_output(job_id):
    d = os.path.join(OUTDIR, job_id)
    if not os.path.isdir(d):
        return None
    fs = [os.path.join(d, f) for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))]
    if not fs:
        return None
    return max(fs, key=os.path.getmtime)


def extract_body(path):
    """只取 ## Response 之后的正文;找不到就返回 None(宁可跳过也不投内部记录)。"""
    with open(path, encoding="utf-8", errors="replace") as fh:
        t = fh.read()
    for marker in ("## Response", "## 输出", "## Final"):
        i = t.find(marker)
        if i >= 0:
            body = t[i + len(marker):].strip()
            if body:
                return body
    return None


def build_plan():
    with open(JOBS, encoding="utf-8") as fh:
        jobs = json.load(fh)["jobs"]
    now = time.time()
    plan, skipped = [], []
    for j in jobs:
        if not j.get("last_delivery_error"):
            continue
        name = j.get("name") or ""
        jid = (j.get("id") or "")[:12]
        p = latest_output(jid)
        age_h = (now - os.path.getmtime(p)) / 3600.0 if p else 1e9
        reason = None
        if is_silent(name, j.get("prompt")):
            reason = "静默 job(正常路径应无输出)"
        elif j.get("no_agent") is True:
            reason = "脚本直出 job(内容多为常规 OK)"
        elif age_h > MAX_AGE_H:
            reason = "过期 %.0fh(> %.0fh)" % (age_h, MAX_AGE_H)
        elif not p:
            reason = "无产物文件"
        body = extract_body(p) if p and not reason else None
        if not reason and not body:
            reason = "产物中无 ## Response 正文段"
        if reason:
            skipped.append((name, jid, reason))
        else:
            plan.append({
                "name": name, "id": jid, "path": p,
                "body": body, "age_h": age_h, "bytes": len(body.encode("utf-8")),
            })
    plan.sort(key=lambda x: x["age_h"])
    return plan, skipped


def redeliver(plan, target, dry_run):
    ok = fail = 0
    consec = 0
    sent_log = []
    for n, item in enumerate(plan, 1):
        hdr = "📮 【补投】%s · 原投递失败(限流)已重试3次 · 产出 %.1fh 前\n\n" % (item["name"], item["age_h"])
        msg = hdr + item["body"]
        if dry_run:
            print("  [DRY %2d] %-30s %6d B" % (n, item["name"][:30], len(msg.encode("utf-8"))))
            continue
        tmp = os.path.join(PROFILE, "data", "_redeliver_cur.txt")
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(msg)
        try:
            r = subprocess.run([HERMES, "send", "-t", target, "-f", tmp, "--json"],
                               capture_output=True, text=True, timeout=SEND_TIMEOUT)
            rc = r.returncode
            out = (r.stdout or "") + (r.stderr or "")
        except subprocess.TimeoutExpired:
            rc, out = 124, "TIMEOUT"
        # ★ 成功判据 = 平台返回的 `success: true` 或 `message_id`,而不是退出码。
        #   实测教训(2026-09-19,三个坑连踩):
        #     1) `-t qqbot:<chat_id> -f f`  rc=1 "Could not resolve <chat_id> on qqbot"
        #        ⇒ `hermes send --list` 展示的 "platform:chat_id" 不能直接用作 -t,要用裸名。
        #     2) `-t qqbot:<chat_id> "text"` rc=0 "sent" ⇒ 假成功,内容并未送达。
        #     3) 解析时若 `stdout + stderr` 拼接,stderr 有字就破坏 JSON ⇒ 必须【只解析 stdout】,
        #        再回退整体。否则真成功(rc=0/success=true)会被判成 FAIL,误触中止。
        def _parse_mid(s):
            """★ 2026-09-19 加固: 不再要求整段 stdout 是纯 JSON。
            实测(_redeliver_log2.txt 09:44): 裸 `-t qqbot` 确实投递成功(rc=0/`"success": true`)
            却被判 FAIL ⇒ 连续失败计数误触中止, 且成功项不写标记 ⇒ 下一轮**重复投递**(用户收到重复消息)。
            原因: stdout 里 JSON 之外还有前后缀文本 ⇒ `json.loads(s[k:])` 抛 "Extra data"。
            改为 raw_decode 容忍前后缀, 并在解析失败时落盘原始输出以便取证。
            """
            if not s:
                return None, None
            dec = json.JSONDecoder()
            for i, ch in enumerate(s):
                if ch != "{":
                    continue
                try:
                    d, _ = dec.raw_decode(s[i:])
                except Exception:
                    continue
                if isinstance(d, dict) and ("message_id" in d or "success" in d):
                    return d.get("message_id"), d.get("success")
            return None, None

        mid, succ = _parse_mid(r.stdout or "")
        if mid is None and succ is None:
            mid, succ = _parse_mid(out)
        good = bool(mid) or succ is True
        if not good:
            # 取证: 解析失败时落盘原始 stdout/stderr (供事后判"真失败"还是"假失败")
            try:
                with open(os.path.join(PROFILE, "data", "_redeliver_raw.log"), "a", encoding="utf-8") as fh:
                    fh.write("=== %s | %s rc=%s ===\n[stdout]\n%s\n[stderr]\n%s\n\n" % (
                        time.strftime("%Y-%m-%d %H:%M:%S"), item["name"], rc,
                        (r.stdout or "")[:2000], (r.stderr or "")[:800]))
            except Exception:
                pass
        if good:
            ok += 1
            consec = 0
            print("  [%2d/%d] OK   %-30s %6d B  mid=%s…" % (
                n, len(plan), item["name"][:30], len(msg.encode("utf-8")), str(mid or "success")[:22]))
        else:
            fail += 1
            consec += 1
            conf_err = "Could not resolve" in out
            print("  [%2d/%d] FAIL %-30s rc=%s %s" % (
                n, len(plan), item["name"][:30], rc, out.strip()[:120].replace(chr(10), " ")))
            if conf_err:
                print("  ⛔ target 配置错误(Could not resolve)⇒ 立即中止,这是参数问题不是限流")
                break
            if consec >= MAX_CONSEC_FAIL:
                print("  ⛔ 连续 %d 次失败 ⇒ 通道仍在限流,中止(避免加重限流)" % consec)
                break
        sent_log.append({"id": item["id"], "name": item["name"], "rc": rc, "mid": mid})
        if n < len(plan):
            time.sleep(THROTTLE_S)
    return ok, fail, sent_log


def load_marker():
    """已成功补投过的 job_id 集合,避免重跑时重复轰炸。"""
    p = os.path.join(PROFILE, "data", "redelivered_ids.json")
    try:
        with open(p, encoding="utf-8") as fh:
            return set(json.load(fh).get("done", []))
    except Exception:
        return set()


def save_marker(done):
    p = os.path.join(PROFILE, "data", "redelivered_ids.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"done": sorted(done), "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")},
                  fh, ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=None, help="投递目标,用【裸平台名】如 qqbot(带 :chat_id 会 Could not resolve)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all", action="store_true", help="忽略已投标记,重投全部")
    a = ap.parse_args()

    plan, skipped = build_plan()
    done_ids = set() if a.all else load_marker()
    if done_ids:
        before = len(plan)
        plan = [p for p in plan if p["id"] not in done_ids]
        if before != len(plan):
            print("  (已投标记跳过 %d 项)" % (before - len(plan)))
    print("══ 补投计划:%d 项可投 / %d 项跳过 ══" % (len(plan), len(skipped)))
    for name, jid, why in skipped:
        print("  SKIP %-32s %s" % (name[:32], why))
    print()
    if not plan:
        print("  无可补投项(可能都已投过;加 --all 重投)。")
        return 0
    if a.dry_run or not a.target:
        redeliver(plan, a.target or "", True)
        if not a.target:
            print("\n  (未指定 --target,仅演练。加 --target qqbot 才会真投)")
        return 0
    print("══ 开始补投 → %s(间隔 %.0fs)══" % (a.target, THROTTLE_S))
    ok, fail, sent = redeliver(plan, a.target, False)
    for s in sent:
        if s.get("mid"):
            done_ids.add(s["id"])
    save_marker(done_ids)
    print("\n══ 结果:成功 %d / 失败 %d(已投标记累计 %d)══" % (ok, fail, len(done_ids)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
