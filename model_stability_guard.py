# -*- coding: utf-8 -*-
"""本地大模型稳定性守护 (2026-08-16, GX2)
基于前期损坏经验 (OOM/段错误/量化不兼容/依赖漂移)
防护: 冒烟测试 + 状态基线 + 回滚检测

损坏动力学五阶段:
  ① 累积期: 上下文/依赖缓慢增长 (无感)
  ② 临界期: 显存/兼容性逼近极限 (警告)
  ③ 崩溃期: OOM/段错误/量化错误 (故障)
  ④ 恢复期: 重启/重装 (成本高)
  ⑤ 复发期: 未根治 → 周期重复

守护: 检测①② → 避免③
"""
import io
import json
import os
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(os.path.dirname(BASE), "data", "model_stability.json")


def smoke_ollama():
    """冒烟测试: Ollama 可用性 + 模型加载"""
    try:
        r = subprocess.run(["curl", "-s", "http://localhost:11434/api/tags"],
                           capture_output=True, text=True, timeout=10)
        tags = json.loads(r.stdout) if r.stdout else {}
        models = [m["name"] for m in tags.get("models", [])]
        return {"ok": len(models) > 0, "models": models}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def smoke_infer(model="qwen2.5:7b-clean"):
    """推理冒烟: 最小生成测试"""
    import urllib.request
    body = json.dumps({"model": model, "prompt": "1+1=",
                       "stream": False, "max_tokens": 8}).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate",
                                 body, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            ans = json.loads(r.read())["response"].strip()
            return {"ok": len(ans) > 0, "answer": ans}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def load_state():
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def main():
    print("=== 本地大模型稳定性守护 ===\n")

    print("[损坏动力学五阶段]")
    phases = [
        ("① 累积期", "上下文/依赖缓慢增长 — 无感"),
        ("② 临界期", "显存/兼容性逼近极限 — 警告窗口"),
        ("③ 崩溃期", "OOM/段错误/量化错误 — 故障"),
        ("④ 恢复期", "重启/重装 — 高成本"),
        ("⑤ 复发期", "未根治 → 周期重复"),
    ]
    for p, d in phases:
        print(f"  {p}: {d}")
    print("  → 守护目标: 检测①②, 避免③")

    print("\n[冒烟测试]")
    o = smoke_ollama()
    print(f"  Ollama: {'✅ 正常' if o['ok'] else '❌ 异常'} "
          f"({len(o.get('models', []))} 模型)")
    s = smoke_infer()
    print(f"  推理: {'✅ 正常' if s['ok'] else '❌ 异常'} "
          f"{'答案: ' + s['answer'] if s['ok'] else s.get('error', '')}")

    # 状态基线对比
    st = load_state()
    now = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
           "ollama": o["ok"], "infer": s["ok"],
           "models": o.get("models", [])}
    prev = st.get("last")
    if prev:
        drift = []
        if prev.get("infer") and not now["infer"]:
            drift.append("推理能力退化!")
        if set(prev.get("models", [])) != set(now["models"]):
            drift.append("模型清单变化")
        print(f"\n[状态对比 vs 上次]")
        print(f"  {'⚠️ 检测到漂移: ' + '; '.join(drift) if drift else '✅ 无漂移 (稳定)'}")
        print(f"  上次: {prev.get('ts')} | 本次: {now['ts']}")
    else:
        print(f"\n[状态对比] 首次运行 (建立基线)")

    # 保存状态
    st["last"] = now
    st["history"] = st.get("history", [])[-9:] + [now]
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"  基线已保存: {STATE}")

    print("\n[稳定性建议]")
    print("  ① 迭代前: 冒烟测试 (本脚本) + 快照")
    print("  ② 迭代中: 小步验证 + 回滚点 (git/.bak)")
    print("  ③ 迭代后: 状态对比 (漂移检测)")
    print("  ④ 降级链: 主模型→备份→网络兜底 (GT 已验证)")


if __name__ == "__main__":
    main()
