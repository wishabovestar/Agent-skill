#!/usr/bin/env python3
"""
生成测试数据集：模拟锂电池实验数据
包含各种冗余类型用于测试紧凑格式
"""
import csv
import random
import math
from datetime import datetime, timedelta

random.seed(42)

# ── 参数 ──
BATCHES = [
    "批次-2026-Q1-高镍811-A",
    "批次-2026-Q1-高镍811-B", 
    "批次-2026-Q1-高镍811-C",
    "批次-2026-Q1-磷酸铁锂-A",
    "批次-2026-Q1-磷酸铁锂-B",
]
STATUSES = ["合格", "不合格", "待检", "返修"]
MATERIALS = ["NCM811", "NCM622", "LFP", "LCO", "NCA"]
TEST_ITEMS = ["循环保持率%", "内阻增长率%", "厚度膨胀率%", "容量保持率%"]

headers = [
    "实验编号",         # 顺序ID
    "批次号",           # 字典编码（5个唯一值）
    "材料类型",         # 字典编码（5个唯一值）
    "测试项目",         # 字典编码（4个唯一值）
    "测试值",           # 浮点数
    "状态",             # 字典编码（4个唯一值）
    "温度(°C)",         # 整数，范围有限
    "湿度(%RH)",        # 整数百分比
    "压力(kPa)",        # 浮点数
    "测试日期",         # 日期
    "操作员",           # 字典编码
    "循环次数",         # 整数，递增
    "备注",             # 长文本（少量）
]

# 操作员
OPERATORS = ["张三", "李四", "王五", "赵六", "钱七"]

rows = []
base_date = datetime(2026, 1, 15)

for i in range(1, 1001):  # 1000行
    batch = random.choice(BATCHES)
    material = random.choice(MATERIALS)
    test_item = random.choice(TEST_ITEMS)
    status = random.choice(STATUSES)
    op = random.choice(OPERATORS)
    
    # 测试值 - 不同类型的数据
    if test_item == "循环保持率%":
        test_val = round(random.uniform(75.0, 99.9), 2)
    elif test_item == "内阻增长率%":
        test_val = round(random.uniform(5.0, 45.0), 2)
    elif test_item == "厚度膨胀率%":
        test_val = round(random.uniform(1.0, 15.0), 2)
    else:
        test_val = round(random.uniform(85.0, 100.0), 2)
    
    temp = random.randint(20, 45)
    humidity = random.randint(30, 80)
    pressure = round(random.uniform(95.0, 105.0), 2)
    days_offset = random.randint(0, 180)
    test_date = (base_date + timedelta(days=days_offset)).strftime("%Y-%m-%d")
    cycle = i + 1000  # 递增
    
    remark = ""
    if status == "不合格":
        remark = random.choice(["极片开裂", "电解液泄漏", "容量骤降", "内阻过大"])
    
    rows.append([
        str(i),           # 实验编号
        batch,            # 批次号（字典）
        material,         # 材料类型（字典）
        test_item,        # 测试项目（字典）
        str(test_val),    # 测试值（浮点）
        status,           # 状态（字典）
        str(temp),        # 温度（整数）
        str(humidity),    # 湿度（整数）
        str(pressure),    # 压力（浮点）
        test_date,        # 日期
        op,               # 操作员（字典）
        str(cycle),       # 循环次数（递增）
        remark,           # 备注（稀疏）
    ])

# 写入CSV
with open("D:/hermes/analysis/test_data_1000.csv", "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    writer.writerow(headers)
    writer.writerows(rows)

# 同时写一个更大的版本（5000行）
rows_big = []
for i in range(1, 5001):
    batch = random.choice(BATCHES)
    material = random.choice(MATERIALS)
    test_item = random.choice(TEST_ITEMS)
    status = random.choice(STATUSES)
    op = random.choice(OPERATORS)
    
    if test_item == "循环保持率%":
        test_val = round(random.uniform(75.0, 99.9), 2)
    elif test_item == "内阻增长率%":
        test_val = round(random.uniform(5.0, 45.0), 2)
    elif test_item == "厚度膨胀率%":
        test_val = round(random.uniform(1.0, 15.0), 2)
    else:
        test_val = round(random.uniform(85.0, 100.0), 2)
    
    temp = random.randint(20, 45)
    humidity = random.randint(30, 80)
    pressure = round(random.uniform(95.0, 105.0), 2)
    days_offset = random.randint(0, 180)
    test_date = (base_date + timedelta(days=days_offset)).strftime("%Y-%m-%d")
    cycle = i + 10000
    
    remark = ""
    if status == "不合格":
        remark = random.choice(["极片开裂", "电解液泄漏", "容量骤降", "内阻过大"])
    
    rows_big.append([
        str(i),
        batch,
        material,
        test_item,
        str(test_val),
        status,
        str(temp),
        str(humidity),
        str(pressure),
        test_date,
        op,
        str(cycle),
        remark,
    ])

with open("D:/hermes/analysis/test_data_5000.csv", "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    writer.writerow(headers)
    writer.writerows(rows_big)

print("✅ 测试数据生成完成:")
print(f"   test_data_1000.csv: {len(rows)} 行")
print(f"   test_data_5000.csv: {len(rows_big)} 行")
