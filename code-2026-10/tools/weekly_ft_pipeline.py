#!/usr/bin/env python3
"""
用户画像周微调管道 — weekly_ft_pipeline.py
每周日凌晨2点由 cron 触发

流程:
  1. 收集本周所有用户会话数据
  2. 构建 LoRA 微调数据集 (Alpaca 格式)
  3. 如果数据量 ≥ 100 条, 启动 LoRA 微调
  4. 评估微调效果
  5. 优于基线则导出为 Ollama 适配器并更新 Modelfile
  6. 发送报告

依赖: torch, unsloth, peft, transformers, datasets, sentence-transformers
"""

import sys, os, json, time, sqlite3, shutil, subprocess
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from typing import Optional

# ── 配置 ──
PROFILES_DIR = Path("D:/hermes/profiles/user_profiles")
ANALYSIS_DIR = Path("D:/hermes/analysis")
MODEL_CACHE = Path.home() / ".ollama/models"
LORA_OUTPUT_DIR = ANALYSIS_DIR / "lora_adapters"
FT_DATASET_DIR = ANALYSIS_DIR / "ft_datasets"
EVAL_DIR = ANALYSIS_DIR / "ft_eval"

LORA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
FT_DATASET_DIR.mkdir(parents=True, exist_ok=True)
EVAL_DIR.mkdir(parents=True, exist_ok=True)

MIN_SAMPLES = 100  # 最少样本数才启动微调
BASE_MODEL = "Qwen/Qwen2.5-7B"  # HF model ID
OLLAMA_BASE = "qwen2.5:7b"

# ── Step 1: 数据收集 ──

def collect_weekly_sessions(days: int = 7) -> list[dict]:
    """从 state.db 收集本周用户会话"""
    from user_profiler import SESSION_DB, scan_recent_sessions
    sessions = scan_recent_sessions(days)
    
    records = []
    for user_key, messages in sessions.items():
        platform, user_id = user_key.split(":", 1)
        # 从消息中提取 user-assistant pairs
        for i in range(len(messages) - 1):
            if messages[i]["role"] == "user" and messages[i+1]["role"] == "assistant":
                records.append({
                    "instruction": messages[i]["content"][:2048],
                    "output": messages[i+1]["content"][:2048],
                    "user_id": user_id,
                    "platform": platform,
                    "timestamp": messages[i].get("timestamp", 0),
                    # 后续从画像补充 style_label
                })
    return records

# ── Step 2: 构建数据集 ──

def build_dataset(records: list[dict]) -> list[dict]:
    """构建 Alpaca 格式微调数据集"""
    print(f"📦 原始记录数: {len(records)}")
    
    # 去重 + 过滤短消息
    seen = set()
    clean = []
    for r in records:
        key = (r["instruction"][:100], r["output"][:100])
        if key in seen:
            continue
        seen.add(key)
        if len(r["instruction"]) < 5 or len(r["output"]) < 5:
            continue
        if r["instruction"] == r["output"]:
            continue
        clean.append(r)
    
    print(f"   ✅ 去重后: {len(clean)} 条有效样本")
    return clean

def save_dataset(dataset: list[dict]) -> Path:
    """保存数据集为 JSONL"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    path = FT_DATASET_DIR / f"weekly_ft_{timestamp}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for item in dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"   💾 数据集保存: {path} ({len(dataset)} 条)")
    return path

# ── Step 3: LoRA 微调 ──

def run_lora_training(dataset_path: Path) -> Optional[Path]:
    """使用 unsloth 执行 QLoRA 微调"""
    from datasets import load_dataset
    from unsloth import FastLanguageModel, is_bfloat16_supported
    import torch
    from transformers import TrainingArguments
    from trl import SFTTrainer
    
    print(f"\n🚀 开始 LoRA 微调...")
    print(f"   数据集: {dataset_path}")
    
    # 加载模型 (4bit QLoRA)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=True,
    )
    
    # 添加 LoRA 适配器
    model = FastLanguageModel.get_peft_model(
        model,
        r=8,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=16,
        lora_dropout=0.05,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
        use_rslora=False,
        loftq_config=None,
    )
    
    # 加载数据集
    dataset = load_dataset("json", data_files=str(dataset_path), split="train")
    
    # Alpaca 格式 prompt template
    alpaca_prompt = """Below is an instruction that describes a task. Write a response that appropriately completes the request.

### Instruction:
{}

### Response:
{}"""
    
    EOS_TOKEN = tokenizer.eos_token
    
    def formatting_prompts_func(examples):
        instructions = examples["instruction"]
        outputs = examples["output"]
        texts = []
        for inst, out in zip(instructions, outputs):
            text = alpaca_prompt.format(inst, out) + EOS_TOKEN
            texts.append(text)
        return {"text": texts}
    
    dataset = dataset.map(formatting_prompts_func, batched=True)
    
    # 训练参数
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=2048,
        dataset_num_proc=2,
        packing=False,
        args=TrainingArguments(
            per_device_train_batch_size=1,
            gradient_accumulation_steps=4,
            warmup_steps=5,
            max_steps=min(60, len(dataset) * 3),  # 最多60步
            learning_rate=2e-4,
            fp16=not is_bfloat16_supported(),
            bf16=is_bfloat16_supported(),
            logging_steps=10,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=42,
            output_dir=str(LORA_OUTPUT_DIR / f"run_{datetime.now().strftime('%Y%m%d_%H%M')}"),
            save_strategy="steps",
            save_steps=30,
            report_to="none",
        ),
    )
    
    print(f"\n🏋️ 开始训练...")
    start_vram = torch.cuda.memory_allocated() / 1024**3
    print(f"   VRAM 初始: {start_vram:.1f} GB")
    
    trainer_stats = trainer.train()
    
    peak_vram = torch.cuda.max_memory_allocated() / 1024**3
    print(f"   ✅ 训练完成! VRAM 峰值: {peak_vram:.1f} GB")
    print(f"   Loss: {trainer_stats.training_loss:.4f}")
    
    # 保存 LoRA 权重
    run_dir = trainer.args.output_dir
    lora_path = Path(run_dir) / "lora_adapter"
    model.save_pretrained(str(lora_path))
    tokenizer.save_pretrained(str(lora_path))
    print(f"   💾 LoRA 权重保存: {lora_path}")
    
    return lora_path

# ── Step 4: 评估 ──

def evaluate_lora(lora_path: Path, dataset_path: Path) -> dict:
    """评估微调效果"""
    from unsloth import FastLanguageModel
    import torch
    
    print(f"\n📊 评估 LoRA 适配器: {lora_path}")
    
    # 加载 + LoRA
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model, r=8,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )
    
    # 加载训练好的 LoRA 权重
    from peft import PeftModel
    model = PeftModel.from_pretrained(model, str(lora_path))
    
    # 测试推理
    test_prompts = [
        "锂电池补锂工艺中压延补锂的优缺点是什么？",
        "请解释一下 transformer 的注意力机制",
        "帮我写一个 Python 装饰器",
    ]
    
    results = []
    FastLanguageModel.for_inference(model)
    for prompt in test_prompts:
        inputs = tokenizer([prompt], return_tensors="pt").to("cuda")
        outputs = model.generate(
            **inputs, max_new_tokens=256,
            temperature=0.7, top_p=0.95,
        )
        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        results.append({
            "prompt": prompt,
            "response_length": len(response),
        })
        print(f"   Prompt: {prompt[:40]}...")
        print(f"   Response length: {len(response)} chars")
    
    vram_used = torch.cuda.memory_allocated() / 1024**3
    torch.cuda.empty_cache()
    
    return {
        "eval_samples": len(test_prompts),
        "vram_at_eval": round(vram_used, 1),
        "responses": results,
    }

# ── Step 5: 导出为 Ollama 适配器 ──

def export_to_ollama(lora_path: Path) -> Optional[str]:
    """导出 LoRA 适配器为 Ollama Modelfile 格式"""
    from unsloth import FastLanguageModel
    import torch
    
    print(f"\n📤 导出 LoRA 到 Ollama 格式...")
    
    # 合并权重
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=True,
    )
    from peft import PeftModel
    model = PeftModel.from_pretrained(model, str(lora_path))
    merged = model.merge_and_unload()
    
    # 保存为 safetensors
    export_dir = lora_path.parent / "ollama_export"
    merged.save_pretrained(str(export_dir))
    tokenizer.save_pretrained(str(export_dir))
    print(f"   ✅ 合并模型保存: {export_dir}")
    
    # 创建 Ollama Modelfile
    modelfile = f"""FROM {OLLAMA_BASE}
ADAPTER {export_dir}
SYSTEM "You are a personalized assistant fine-tuned for user interaction patterns."
"""
    modelfile_path = lora_path.parent / "Modelfile"
    modelfile_path.write_text(modelfile, encoding="utf-8")
    print(f"   📄 Modelfile: {modelfile_path}")
    
    return str(modelfile_path)

# ── Step 6: 主入口 ──

def main():
    start_time = time.time()
    print(f"🔄 每周微调管道 — {datetime.now().isoformat()}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    # Step 1-2: 收集并构建数据集
    records = collect_weekly_sessions(days=7)
    dataset = build_dataset(records)
    
    if len(dataset) < MIN_SAMPLES:
        print(f"\n⚠️ 数据不足 ({len(dataset)} < {MIN_SAMPLES}), 跳过本轮微调")
        print(f"   预计需要: 7天 × {MIN_SAMPLES // 7} 条/天")
        print(f"   ⏱️ 总耗时: {time.time() - start_time:.1f}s")
        return
    
    dataset_path = save_dataset(dataset)
    
    # Step 3: 微调
    lora_path = run_lora_training(dataset_path)
    if not lora_path:
        print("❌ 微调失败")
        return
    
    # Step 4: 评估
    eval_result = evaluate_lora(lora_path, dataset_path)
    
    # 保存评估报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "dataset_size": len(dataset),
        "training_loss": eval_result.get("loss", "N/A"),
        "vram_peak_gb": eval_result.get("vram_at_eval", "N/A"),
        "eval_responses": eval_result.get("responses", []),
    }
    report_path = EVAL_DIR / f"eval_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n   📊 评估报告: {report_path}")
    
    # Step 5: 导出 (可选)
    # modelfile = export_to_ollama(lora_path)
    
    elapsed = time.time() - start_time
    print(f"\n✅ 周微调管道完成! ⏱️ {elapsed:.0f}s")
    print(f"   数据集: {len(dataset)} 条")
    print(f"   LoRA适配器: {lora_path}")
    print(f"   Ollama模型: ollama create qwen2.5-ft-weekly -f {lora_path.parent}/Modelfile")


if __name__ == "__main__":
    main()
