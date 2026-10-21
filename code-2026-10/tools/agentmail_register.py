#!/usr/bin/env python3
"""注册agent mail身份 - Amazon + 淘宝联盟 (修正参数)"""
import json, urllib.request

BASE = 'http://127.0.0.1:8765/mcp'
SESSION = '7a92a214495548d49e9b0cce5f7c025a'

def mcp_call(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 10, "method": method, "params": params}).encode()
    req = urllib.request.Request(BASE, data=body, headers={
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
        'Mcp-Session-Id': SESSION
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except Exception as e:
        return {'error': str(e)}

def extract_text(r):
    try:
        return r['result']['content'][0]['text'][:400]
    except:
        return str(r)[:400]

# 1. ensure_project
print("=== 创建项目 ===")
r = mcp_call('tools/call', {'name': 'ensure_project', 'arguments': {'human_key': r'D:\hermes\projects\cloudlink-affiliate'}})
print(extract_text(r))

# 2. register_agent (Amazon)
print("\n=== 注册Amazon agent ===")
r = mcp_call('tools/call', {'name': 'register_agent', 'arguments': {
    'project_key': 'd-hermes-projects-cloudlink-affiliate',
    'program': 'Amazon Associates联盟推广',
    'model': 'deepseek-v4-flash',
    'name': 'amazon-associates',
    'task_description': '管理Amazon Associates联盟推广，生成推荐设备链接'
}})
print(extract_text(r))

# 3. register_agent (淘宝)
print("\n=== 注册淘宝联盟agent ===")
r = mcp_call('tools/call', {'name': 'register_agent', 'arguments': {
    'project_key': 'd-hermes-projects-cloudlink-affiliate',
    'program': '阿里妈妈/淘宝联盟推广',
    'model': 'deepseek-v4-flash',
    'name': 'taobao-union',
    'task_description': '管理阿里妈妈淘宝联盟推广，对接账号 user@example.com'
}})
print(extract_text(r))
