"""compaction 尾部下界两档对照（走生产代码路径，不重写选择逻辑）。

臂 A：默认 lean（tail = 10,000）
臂 B：HERMES_TAIL_FLOOR_TOKENS=24000（窗口 16k + 回溯 8k 的示意几何下界）

测三件事：
  1) 尾部实际 token / 覆盖多少条消息
  2) 10 条埋入事实中，有几条落在 verbatim 尾部（其余只能靠摘要）
  3) 裸尾部的模型召回（不接摘要，仅作覆盖上限的上界参考）
"""
from __future__ import annotations

import io
import json
import os
import random
import sys

HERMES = r"C:/Users/Administrator/AppData/Local/hermes/hermes-agent"
sys.path.insert(0, HERMES)
import ruamel.yaml  # noqa: F401  预载，避免上游链中途裁剪 sys.path 后找不到
print("T22_OK")
