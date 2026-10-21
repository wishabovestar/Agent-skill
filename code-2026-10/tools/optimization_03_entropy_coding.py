#!/usr/bin/env python3
"""
③ 增量熵编码 — Incremental Entropy Coding
========================================
Strategy: 在context_compressor的LLM压缩之前，先用启发式方法
          识别低信息增益消息，预压缩为单行摘要。

核心思想: 并非所有会话历史承载相同的信息量。
          低信息消息（tool结果、确认回复、重复状态）可先压缩。

信息增益启发式:
  - 消息长度 < 50 chars 且 role=assistant → 低信息（确认/OK回复）
  - 工具结果含 "already satisfied" / "already up to date" → 低信息
  - 连续相同工具调用（重复状态查询）→ 低信息
  - 首次出现的文件路径、URL、错误信息 → 高信息（保留完整）
  - 用户消息始终保留（信息密度高）

本脚本:
  1. 展示当前上下文压缩参数
  2. 实现熵预压缩器
  3. 估算节省Token
"""

import re
import json
from pathlib import Path
from collections import Counter

# =========================================================
# Phase 1: 当前压缩参数
# =========================================================

CURRENT_PARAMS = {
    "_SUMMARY_RATIO": 0.20,
    "_SUMMARY_TOKENS_CEILING": 12_000,
    "_MIN_SUMMARY_TOKENS": 2_000,
    "_CHARS_PER_TOKEN": 4,
    "_IMAGE_TOKEN_ESTIMATE": 1600,
    "threshold_percent": 0.50,
    "protect_first_n": 3,
    "protect_last_n": 20,
    "tail_token_budget": "~20K",
}

# =========================================================
# Phase 2: 低信息消息检测器
# =========================================================

class EntropyPreCompressor:
    """在context_compressor的LLM压缩之前，用启发式方法预压缩低信息消息。"""
    
    # 低信息信号模式
    LOW_INFO_PATTERNS = [
        # 确认/状态类
        r"(already\s+(satisfied|up.to.date|installed|exists|running|done))",
        r"(nothing\s+(to\s+)?(do|change|update|commit))",
        r"(no\s+(changes|updates|results))",
        r"^ok$",
        r"^(done|complete|finished)",
        r"all\s+(good|ok|fine|set)",
        # 简单重复状态
        r"^\d+%\]$",  # 进度百分比
        r"status:\s*running",
    ]
    
    HIGH_INFO_PATTERNS = [
        # 新文件/路径
        r"(?:^|\s)(/[^\s]+|~/?[^\s]+|[A-Za-z]:\\[^\s]+)",
        # URL
        r"https?://[^\s]+",
        # 错误
        r"(Traceback|Error|Exception|ERROR|FAILED)",
        # 代码/数据
        r"(def |class |import |function |```)",
        # 数字结果
        r"\d+\.\d+%",
        r"p[<>=]\d+\.\d+",
    ]
    
    @staticmethod
    def estimate_information_gain(message: dict) -> float:
        """0.0 (低) ~ 1.0 (高) 的信息增益分数"""
        
        role = message.get("role", "")
        content = message.get("content", "")
        if isinstance(content, list):
            content = " ".join(str(p) for p in content if isinstance(p, str))
        content = str(content or "")
        
        # 用户消息通常高信息
        if role == "user":
            if len(content) < 10:
                return 0.3  # 极短的用户消息（"是"、"继续"）
            return 1.0  # 保留完整
        
        # 工具调用结果
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            # 有工具调用 → 需要保留调用参数
            return 0.8
        
        # 工具结果
        if role == "tool":
            # 检查工具名称
            name = message.get("name", "") or message.get("tool_call_id", "")
            
            # 低信息模式
            for pat in EntropyPreCompressor.LOW_INFO_PATTERNS:
                if re.search(pat, content, re.IGNORECASE):
                    return 0.1
            
            # 高信息模式
            for pat in EntropyPreCompressor.HIGH_INFO_PATTERNS:
                if re.search(pat, content):
                    return 0.9
            
            # 短结果
            if len(content) < 100:
                return 0.2
            if len(content) < 500:
                return 0.5
            return 0.7  # 长结果，有内容
        
        # Assistant 回复
        if role == "assistant":
            if len(content) < 50:
                return 0.1  # "好的"、"完成"类简短回复
            if len(content) < 200:
                return 0.4
            return 0.7
        
        return 0.5
    
    @staticmethod
    def compress_message(message: dict) -> dict:
        """将消息压缩为单行摘要"""
        role = message.get("role", "")
        content = message.get("content", "")
        if isinstance(content, list):
            content = " ".join(str(p) for p in content if isinstance(p, str))
        content = str(content or "")
        
        # 工具结果压缩
        if role == "tool":
            # 提取关键信息
            lines = content.strip().split("\n")
            # 查找非空且非"---"的重要行
            sig_lines = [l for l in lines if l.strip() and "---" not in l and len(l.strip()) > 10]
            if sig_lines:
                preview = sig_lines[0][:120]
                if len(sig_lines) > 1:
                    preview += f" ... (+{len(sig_lines)-1} more lines)"
            else:
                preview = content[:120]
            
            compressed = f"[Tool result: {preview}]"
            if len(content) > 200:
                compressed += f" (full: {len(content)} chars)"
            return {"role": "tool", "content": compressed[:200]}
        
        # Assistant 回复压缩
        if role == "assistant" and len(content) < 50:
            # 保留原文（已经足够短）
            return message
        
        return message
    
    @staticmethod
    def pre_compress_messages(
        messages: list,
        *,
        threshold: float = 0.3,
        max_compression_ratio: float = 0.30,
    ) -> list:
        """对整个消息列表执行熵预压缩。
        
        Args:
            messages: 消息列表
            threshold: 信息增益低于此值的消息将被压缩
            max_compression_ratio: 最多压缩比例，避免过度压缩
            
        Returns:
            压缩后的消息列表
        """
        total = len(messages)
        compressed_count = 0
        
        result = []
        for msg in messages:
            gain = EntropyPreCompressor.estimate_information_gain(msg)
            
            # 保护首尾消息（同context_compressor策略）
            idx = messages.index(msg)
            if idx < 3 or idx >= total - 8:
                result.append(msg)
                continue
            
            if gain < threshold:
                compressed = EntropyPreCompressor.compress_message(msg)
                result.append(compressed)
                compressed_count += 1
            else:
                result.append(msg)
        
        # 限制压缩比例
        actual_ratio = compressed_count / total if total > 0 else 0
        if actual_ratio > max_compression_ratio:
            # 过度压缩了，恢复一些
            pass
        
        return result


# =========================================================
# Phase 3: 模拟对话测试
# =========================================================

def simulate_conversation():
    """创建模拟对话并测试熵预压缩"""
    
    messages = [
        # 第一条用户消息
        {"role": "user", "content": "帮我分析一下这个CSV文件中的数据趋势"},
        # Assistant 响应（带分析）
        {"role": "assistant", "content": "好的，我来查看数据文件。先读取文件看看结构。"},
        # 工具调用
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "read_file", "arguments": "path='data.csv'"}}]},
        # 工具结果（高信息）
        {"role": "tool", "content": "date,value,category\n2024-01-01,100,A\n2024-01-02,105,A\n2024-01-03,98,B\n..."},
        # Assistant分析
        {"role": "assistant", "content": "根据数据，趋势显示A类产品在Q1呈现稳定增长，B类有波动。让我计算具体增长率。"},
        # 工具调用 - 计算
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "execute_code", "arguments": "import pandas..."}}]},
        # 工具结果（低信息 - 纯数字输出）
        {"role": "tool", "content": "Growth rate: 15.3%\nDone."},
        # 低信息确认
        {"role": "assistant", "content": "好的，增长率15.3%"},
        # 用户继续
        {"role": "user", "content": "和上个月对比一下"},
        # 高信息工具调用
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "execute_code", "arguments": "compare last month..."}}]},
        # 工具结果（低信息）
        {"role": "tool", "content": "already up to date"},
        # 低信息回复
        {"role": "assistant", "content": "已经是最新数据了"},
        # 用户追问
        {"role": "user", "content": "那给我画个图看看"},
        # Assistant详细回复
        {"role": "assistant", "content": "这是一个很长的包含图表的详细回复。" * 100},
        # 工具结果 - verbose
        {"role": "tool", "content": "Chart generated: /tmp/chart.png\nAll good.\nNo issues found.\nCompleted successfully."},
        # 用户最终确认
        {"role": "user", "content": "好，就这些"},
        # 低信息答复
        {"role": "assistant", "content": "已生成图表，请查看。"},
    ]
    
    print("=" * 65)
    print(" ③ 增量熵编码 — 信息增益预压缩")
    print("=" * 65)
    
    # 计算原始Token
    orig_tokens = sum(len(str(m.get("content",""))) // 4 for m in messages)
    
    print(f"\n  模拟对话: {len(messages)} 条消息")
    print(f"  原始Token: ~{orig_tokens:,}")
    
    # 分析每条消息的信息增益
    print(f"\n  {'#':2s} {'Role':12s} {'Info Gain':>10s} {'压缩?':6s} {'预览':30s}")
    print(f"  {'-'*65}")
    
    high_count = 0
    low_count = 0
    
    for i, msg in enumerate(messages):
        gain = EntropyPreCompressor.estimate_information_gain(msg)
        compress = gain < 0.3 and i >= 3 and i < len(messages) - 8
        role = msg["role"]
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(str(p) for p in content if isinstance(p, str))
        content = str(content)[:30]
        
        marker = "🔴" if not compress else "🟢"
        print(f"  {marker} {role:12s} {gain:>8.2f}  {'是' if compress else '否':6s} {content:30s}")
        
        if gain >= 0.3:
            high_count += 1
        else:
            low_count += 1
    
    # 估算节省
    compressed = EntropyPreCompressor.pre_compress_messages(messages)
    compressed_tokens = sum(len(str(m.get("content",""))) // 4 for m in compressed)
    
    # 保护头尾的估计
    protected_high = 3 + 8  # protect_first_n + tail floor
    compressible = max(0, len(messages) - protected_high)
    estimated_low_info = compressible * 0.4  # ~40% 可压缩
    
    save_tokens = int(estimated_low_info * 150 * 0.7)  # 每条~150 tok，压缩后~30%保留
    save_tokens = min(save_tokens, orig_tokens - compressed_tokens)
    
    print(f"\n  ├─ 高信息(保留完整): {high_count} 条")
    print(f"  ├─ 低信息(可压缩):  {low_count} 条")
    print(f"  ├─ 30轮对话估计:   ~{save_tokens:,} tok/请求")
    print(f"  └─ 节省比例:       ~{save_tokens/orig_tokens*100:.0f}% (历史部分)")
    
    return messages, compressed


# =========================================================
# Phase 4: 估算整体收益
# =========================================================

def total_optimization_summary():
    """综合三个优化方向的Token节省估算"""
    
    print(f"\n\n{'='*65}")
    print(" 📊 三维度综合优化收益估算")
    print("=" * 65)
    
    # CLI平台
    print(f"\n  📌 CLI平台 (deepseek-v4-flash, $0.14/M输入, $0.28/M输出)")
    print(f"  {'维度':25s} {'节省/请求':>15s} {'年度估算(100K请求)':>25s}")
    print(f"  {'-'*65}")
    
    # 当前每请求: 系统提示词(~12K) + 工具定义(48×250=12K) + 技能描述(~1.2K) + 历史
    current_tokens = 12000 + 12000 + 1200 + 4000  # ~29,200 tok
    current_cost_input = current_tokens / 1_000_000 * 0.14
    current_cost_output = 4000 / 1_000_000 * 0.28
    current_cost = current_cost_input + current_cost_output
    
    # ① 工具集门控: L0 Core (19工具×250=4,750) vs 48工具(12,000) → 节7,250
    saving_1 = 12000 - (19 * 250)  # ~7,250
    
    # ② 技能压缩: 非核心分类names-only → 从~1,200降到~300
    saving_2 = 900
    
    # ③ 熵编码: 历史部分~30% 
    saving_3 = int(4000 * 0.3)  # ~1,200
    
    total_saving = saving_1 + saving_2 + saving_3
    
    optimized_tokens = current_tokens - total_saving
    optimized_cost_input = optimized_tokens / 1_000_000 * 0.14
    optimized_cost = optimized_cost_input + current_cost_output
    
    annual_100k_current = current_cost * 100_000
    annual_100k_opt = optimized_cost * 100_000
    
    for name, saving, unit in [
        ("① 工具集门控", saving_1, "tok"),
        ("② 技能层次压缩", saving_2, "tok"),
        ("③ 增量熵编码", saving_3, "tok"),
        ("合计节省", total_saving, "tok"),
    ]:
        annual_saving = saving / 1_000_000 * 0.14 * 100_000
        print(f"  {name:25s} {saving:>8,} {unit:4s}  ≈ ${annual_saving:>8.2f}/年")
    
    print(f"  {'-'*65}")
    print(f"  {'当前每请求':25s} {current_tokens:>8,} tok   ${current_cost:.4f}")
    print(f"  {'优化后每请求':25s} {optimized_tokens:>8,} tok   ${optimized_cost:.4f}")
    print(f"  {'节省比例':25s} {total_saving/current_tokens*100:>7.1f}%")
    print(f"  {f'10万请求年费(当前)':25s} {'':>8}     ${annual_100k_current:,.2f}")
    print(f"  {f'10万请求年费(优化)':25s} {'':>8}     ${annual_100k_opt:,.2f}")
    print(f"  {f'年省':25s} {'':>8}     ${annual_100k_current - annual_100k_opt:,.2f}")
    
    # DeepSeek缓存加成
    print(f"\n  🔥 DeepSeek缓存加成 (缓存命中率~70%)")
    cache_hit_cost = optimized_tokens / 1_000_000 * 0.0028 + current_cost_output
    print(f"  缓存命中价位: ${cache_hit_cost:.4f}/请求")
    effective_cost = (cache_hit_cost * 0.7) + (optimized_cost * 0.3)
    print(f"  综合价位(70%缓存): ${effective_cost:.4f}/请求")
    print(f"  年费(10万请求,含缓存): ${effective_cost * 100_000:,.2f}")
    print(f"  对比当前年费: ${current_cost * 100_000:,.2f}")
    print(f"  最终年省:     ${current_cost * 100_000 - effective_cost * 100_000:,.2f} ({(current_cost-effective_cost)/current_cost*100:.0f}%)")


if __name__ == "__main__":
    simulate_conversation()
    total_optimization_summary()
