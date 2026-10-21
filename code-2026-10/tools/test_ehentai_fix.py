#!/usr/bin/env python3
"""测试ehentai_v3 VPS抓取修复"""
import sys, importlib.util
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

spec = importlib.util.spec_from_file_location('eh', 'D:/hermes/hermes-data/profiles/mybot/scripts/ehentai_v3_weekly.py')
eh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eh)

print("测试1: get() 首页")
html = eh.get(eh.BASE)
print(f"  返回: {len(html)} 字节, gallery={'gallery' in html.lower()}")

print("测试2: vps_fetch 直接调用")
out = eh.vps_fetch(eh.BASE)
print(f"  返回: {len(out)} 字节, gallery={'gallery' in out.lower()}")
print("✅ 修复验证完成")
