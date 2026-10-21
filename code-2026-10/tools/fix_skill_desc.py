#!/usr/bin/env python3
"""批量修复skill description — superpowers规范: 加'用于'触发前缀"""
import os, re, json

SKILLS = r'D:\hermes\hermes-data\profiles\mybot\skills'
FIX_MAP = {
    'computer-use': '用于驱动桌面操作：点击、输入、浏览屏幕。当需要操作本地桌面或模拟用户交互时。',
    'comfyui': '用于通过diffusion工作流生成图片、视频、音频。当需要AI生成视觉/音频内容时。',
    'agent-coordination-infra': '用于部署和管理多Agent协调消息基础设施（MCP Agent Mail等）。当需要Agent间消息/身份/文件租约系统时。',
    'vps-remote-management': '用于VPS/远程服务器管理。当需要SSH连接、密钥认证、Sentinel监控或CentOS运维时。',
    'loop-me': '用于严格审视你的计划/设计/工作流方案。当需要被追问、挑战或打磨spec时。',
    'state-false-alive-recovery': '用于Hermes Gateway State假活诊断与恢复。当PID死亡但state显示running时。',
    'adhd-friendly-output': '用于ADHD友好输出风格：动作先行、步骤编号、状态重申、抑制离题。当需要简洁行动导向的回复时。',
    'open-source-reconnaissance': '用于开源项目系统调查。当需要评估开源生态/项目选型时。',
    'awesome-llm-apps-reference': '用于awesome-llm-apps知识参考。当需要AI应用/Agent/RAG方案检索时。',
    'dev-workflow-engineer': '用于软件工程工作流路由。当需要Matt Pocock技能或全平台工程流程时。',
    'difficulty-triage': '用于指令难易度分流。当需要决定direct/light_tool/dispatch/project工作流时。',
    'browser-act': '用于浏览器自动化CLI。当需要隐形提取网页或浏览器操作时。',
}

def fix_skill(skill_name, new_desc):
    """更新SKILL.md的description行"""
    for root, dirs, files in os.walk(SKILLS):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        if 'SKILL.md' in files:
            p = os.path.join(root, 'SKILL.md')
            if os.path.basename(root) == skill_name:
                with open(p, encoding='utf-8') as f:
                    content = f.read()
                # 替换description行 (支持单双引号)
                new_content = re.sub(
                    r'^description:\s*.*$',
                    f"description: '{new_desc}'",
                    content, count=1, flags=re.M)
                if new_content != content:
                    with open(p, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    print(f'  ✅ {skill_name}: description已修复')
                    return True
                else:
                    print(f'  ⚠️ {skill_name}: 替换失败(检查格式)')
                    return False
    print(f'  ❌ {skill_name}: 未找到')
    return False

if __name__ == '__main__':
    print('=== 批量修复skill description (superpowers规范) ===\n')
    ok, fail = 0, 0
    for name, desc in FIX_MAP.items():
        if fix_skill(name, desc):
            ok += 1
        else:
            fail += 1
    print(f'\n完成: 成功{ok} 失败{fail}')
