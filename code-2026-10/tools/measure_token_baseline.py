#!/usr/bin/env python3
"""Measure current token consumption baseline for Hermes profile mybot."""
import sys
sys.path.insert(0, r'D:\hermes\hermes-data\hermes-agent')

from tools.registry import registry, discover_builtin_tools
from toolsets import resolve_toolset
import json

discover_builtin_tools()
tools = registry._tools

print(f"Total registered tools: {len(tools)}")
print()

# Group by toolset
by_ts = {}
for name, entry in tools.items():
    ts = entry.toolset or 'unknown'
    by_ts.setdefault(ts, []).append(name)

total_est = 0
for ts in sorted(by_ts):
    names = by_ts[ts]
    est = len(names) * 250
    total_est += est
    print(f"  {ts:20s}: {len(names):3d} tools, ~{est:>6,} tokens")
print(f"  {'TOTAL':20s}: {len(tools):3d} tools, ~{total_est:>6,} tokens")

# CLI platform toolsets
cli_ts = ['web','vision','video','image_gen','video_gen','terminal','skills','browser',
          'cronjob','file','code_execution','memory','session_search','clarify',
          'delegation','todo','tts','kanban','computer_use','search','x_search']
all_cli_tools = set()
for t in cli_ts:
    all_cli_tools.update(resolve_toolset(t))

print(f"\nCLI platform ({len(cli_ts)} toolsets): {len(all_cli_tools)} unique tools")
print(f"CLI tool names: {sorted(all_cli_tools)}")

# weixin
wx_ts = ['terminal','file','web','delegation','cronjob','memory','session_search',
         'clarify','todo','tts']
all_wx_tools = set()
for t in wx_ts:
    all_wx_tools.update(resolve_toolset(t))
print(f"\nWeixin platform ({len(wx_ts)} toolsets): {len(all_wx_tools)} unique tools")
print(f"Weixin tool names: {sorted(all_wx_tools)}")

# Token waste
cli_tool_token = len(all_cli_tools) * 250
wx_tool_token = len(all_wx_tools) * 250
print(f"\n--- Utilization ---")
print(f"CLI:     {len(all_cli_tools)} tools × ~250 = ~{cli_tool_token:,} tokens")
print(f"         ~5 tools used = ~1,250 tokens useful out of {cli_tool_token:,}")
print(f"         Waste: ~{cli_tool_token - 1250:,} tokens/request ({((cli_tool_token-1250)/cli_tool_token)*100:.0f}%)")
print(f"Weixin:  {len(all_wx_tools)} tools × ~250 = ~{wx_tool_token:,} tokens")
print(f"         ~5 tools used = ~1,250 tokens useful out of {wx_tool_token:,}")
print(f"         Waste: ~{wx_tool_token - 1250:,} tokens/request ({((wx_tool_token-1250)/wx_tool_token)*100:.0f}%)")

# Now scan skills directory
from pathlib import Path
skills_dir = Path(r'D:\hermes\hermes-data\profiles\mybot\skills')

total_skill_chars = 0
total_skill_desc_chars = 0
skill_count = 0
by_category = {}

for skill_file in sorted(skills_dir.rglob('SKILL.md')):
    skill_count += 1
    content = skill_file.read_text(encoding='utf-8', errors='replace')
    total_skill_chars += len(content)
    # Extract description from frontmatter
    if content.startswith('---'):
        end = content.find('---', 3)
        if end > 0:
            fm = content[3:end]
            for line in fm.strip().split('\n'):
                if line.strip().startswith('description:'):
                    desc = line.split(':', 1)[1].strip().strip("'\"")
                    total_skill_desc_chars += len(desc)
                    break
    
    # Category = parent dir name relative to skills_dir
    rel = skill_file.relative_to(skills_dir)
    cat = rel.parent.name if rel.parent.name != '.' else 'general'
    by_category.setdefault(cat, 0)
    by_category[cat] += 1

total_desc_tokens = total_skill_desc_chars // 4
print(f"\n--- Skills Analysis ---")
print(f"Total SKILL.md files: {skill_count}")
print(f"Total descriptions chars: {total_skill_desc_chars:,} (~{total_desc_tokens:,} tokens)")
print(f"Total SKILL.md chars: {total_skill_chars:,} (~{total_skill_chars//4:,} tokens)")
print(f"\nBy category:")
for cat in sorted(by_category):
    print(f"  {cat:20s}: {by_category[cat]:2d} skills")

# Calculate skills block size in system prompt
# Current format: each skill line = "    - name: description" (~name_len + desc_len + 10 chars)
# Names-only format: "  category [names only]: name1, name2, name3"
desc_format_chars = 0
name_only_chars = 0
cat_lines = {}
for skill_file in sorted(skills_dir.rglob('SKILL.md')):
    content = skill_file.read_text(encoding='utf-8', errors='replace')
    rel = skill_file.relative_to(skills_dir)
    cat = rel.parent.name if rel.parent.name != '.' else 'general'
    # Get name and desc
    name = skill_file.stem  # fallback
    
    if content.startswith('---'):
        end = content.find('---', 3)
        if end > 0:
            fm = content[3:end]
            for line in fm.strip().split('\n'):
                s = line.strip()
                if s.startswith('name:'):
                    name = s.split(':', 1)[1].strip().strip("'\"")
    
    cat_lines.setdefault(cat, [])
    cat_lines[cat].append(name)

print(f"\n--- Skills Block Size Estimation ---")
for cat in sorted(cat_lines):
    names = cat_lines[cat]
    # Current format with descriptions
    # We don't have desc lengths for all, approximate
    current_chars = sum(20 + len(n) + 40 for n in names)  # "    - name: desc..."
    names_only_chars = len(f"  {cat} [names only]: {', '.join(names)}")
    print(f"  {cat:20s}: {len(names):2d} skills | full: ~{current_chars:>5} chars (~{current_chars//4:>4} tok) | names-only: ~{names_only_chars:>4} chars (~{names_only_chars//4:>3} tok)")
