# -*- coding: utf-8 -*-
"""每日 03:30 记忆日报 —— 把 01:00 睡眠巩固 + 02:00 白日梦的产出压成一条微信消息。

存在理由（2026-10-19 体检结论）：
  两个作业每天准时跑完，但 deliver=local ⇒ 结果只躺在 cron/output/ 里，
  连 status=warning 都没人看见（而且它们 exit 0，不触发任何告警）。
  这个脚本不做新分析，只做【投递】：读两个 json，取 Top3，打到 stdout，
  由 cron 直接发到微信（deliver=origin）。

设计约束：
  - 任何异常都 exit 0 并打印原因（cron 非零退出 = 告警轰炸，且这里本来就只是播报）。
  - 不复述全文：微信一条消息，目标 ≤ 1200 字。
  - 数字全部来自 json 原值，不修饰、不补全；缺数据就明说缺。
"""
import glob
import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROFILE = Path(__file__).resolve().parents[1]
OUT = PROFILE / "cron" / "output"
TODAY = datetime.now().strftime("%Y%m%d")


def load_sleep():
    """今日睡眠巩固 json；没有则退回最近一份。"""
    p = OUT / f"sleep_consolidation_{TODAY}.json"
    if not p.exists():
        fs = sorted(OUT.glob("sleep_consolidation_2*.json"))
        p = Path(fs[-1]) if fs else None
    if not p or not p.exists():
        return None, None
    try:
        return json.loads(p.read_text(encoding="utf-8")), p.name
    except Exception:
        return None, p.name


def load_daydream():
    """今日最新的白日梦 json（同日可能有多次运行，取时间戳最大的）。"""
    fs = sorted(glob.glob(str(OUT / f"daydream_v4_{TODAY}_*.json")))
    if not fs:
        fs = sorted(glob.glob(str(OUT / "daydream_v4_2*.json")))
    if not fs:
        return None, None
    p = Path(fs[-1])
    try:
        return json.loads(p.read_text(encoding="utf-8")), p.name
    except Exception:
        return None, p.name


def clip(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def main():
    L = [f"🌙 记忆日报 {datetime.now().strftime('%m-%d')}"]
    sl, sn = load_sleep()
    dd, dn = load_daydream()

    # ── 睡眠巩固 ──
    if not sl:
        L.append(f"\n**睡眠**：未找到 json（{sn or '无文件'}）")
    else:
        st = sl.get("status", "?")
        icon = {"ok": "✅", "ok_with_findings": "✅", "warning": "⚠️", "error": "❌"}.get(st, "•")
        L.append(f"\n**睡眠** {icon} `{st}`")
        integ = (sl.get("stage1_integrity") or {})
        if integ:
            lost = integ.get("lost_sections") or []
            L.append(f"- 完整性 vs {integ.get('backup','?')}：丢段 {len(lost)}"
                     f"{('（' + ', '.join(lost[:3]) + '）') if lost else ''}"
                     f" · 字符 Δ{integ.get('delta', 0):+d}")
        fs_ = sl.get("findings") or []
        if fs_:
            L.append("- 发现：")
            for f in fs_[:3]:
                L.append(f"  · {clip(f, 90)}")
            if len(fs_) > 3:
                L.append(f"  · …另 {len(fs_) - 3} 条")
        sg = sl.get("suggestions") or []
        if sg:
            s0 = sg[0]
            if isinstance(s0, dict):
                txt = f"{s0.get('title','')} {((s0.get('items') or [''])[0])}".strip()
            else:
                txt = str(s0)
            L.append(f"- 首条建议：{clip(txt, 90)}")

    # ── 白日梦 ──
    if not dd:
        L.append(f"\n**白日梦**：未找到 json（{dn or '无文件'}）")
    else:
        cs = dd.get("cross_filter_stats") or {}
        concepts = dd.get("concepts") or []
        ideas = dd.get("cross_domain_ideas") or []
        L.append(f"\n**白日梦** `{dd.get('status','?')}` · 重放 {len(dd.get('replayed') or [])} 条"
                 f" · 抽象 {len(concepts)} 条 · 联想 {len(ideas)}/{cs.get('attempted', dd.get('cross_domain_attempted', 0))}")
        for c in concepts[:3]:
            src = c.get("src", "?")
            L.append(f"  · 🧠[{c.get('domain','?')}] {clip(c.get('principle',''), 70)} `{src}`")
        if ideas:
            for i in ideas[:3]:
                L.append(f"  · 💡[{i.get('strength','?')}] {clip(i.get('idea',''), 90)}")
        else:
            L.append(f"  · 今日无新联想（同题 {cs.get('same_topic',0)} · 跨天重复 {cs.get('dup_prev',0)}"
                     f" · 空谈 {cs.get('ungrounded',0)} · LLM判无 {cs.get('llm_null',0)}）")
        if dd.get("elapsed_s") is not None:
            L.append(f"  · 耗时 {dd['elapsed_s']}s")

    L.append("\n（来源：01:00 睡眠巩固 / 02:00 白日梦；明细见 cron/output/）")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"⚠️ 记忆日报脚本异常: {type(e).__name__}: {e}")
        sys.exit(0)      # 播报器永不把 cron 弄成非零退出
