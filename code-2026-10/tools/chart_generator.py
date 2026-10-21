"""
qqbot2 微信: 图片+数据 → 生成基于数据的图表/图片
v1.0 — 分析图片格式结构,用新数据重新生成

工作流:
  1. 用户发送参考图片 + 数据(CSV/表格/描述)
  2. 分析图片结构(图表类型/布局/配色)
  3. 用新数据生成相同结构的新图片
  
支持的图表类型: 柱状图/折线图/散点图/饼图/雷达图/热力图
"""
import os, sys, json, re, hashlib
from pathlib import Path
from datetime import datetime
import subprocess

# ===== 配置 =====
OUTPUT_DIR = Path("D:/hermes/data/generated_charts")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = OUTPUT_DIR / "_generation_log.json"

# ===== 支持的图表模板 =====
CHART_TEMPLATES = {
    "bar": {
        "name": "柱状图",
        "desc": "比较不同类别的数值",
        "matplotlib": "plt.bar(x, y)",
    },
    "barh": {
        "name": "水平柱状图",
        "desc": "适合类别名称较长的情况",
        "matplotlib": "plt.barh(y, x)",
    },
    "line": {
        "name": "折线图",
        "desc": "展示数据随时间或顺序变化的趋势",
        "matplotlib": "plt.plot(x, y)",
    },
    "scatter": {
        "name": "散点图",
        "desc": "展示两个变量之间的关系",
        "matplotlib": "plt.scatter(x, y)",
    },
    "pie": {
        "name": "饼图",
        "desc": "展示各部分占总体的比例",
        "matplotlib": "plt.pie(sizes, labels)",
    },
    "radar": {
        "name": "雷达图",
        "desc": "多维度对比",
        "matplotlib": "雷达图 (polar projection)",
    },
    "heatmap": {
        "name": "热力图",
        "desc": "矩阵数据的颜色编码展示",
        "matplotlib": "plt.imshow(data, cmap='viridis')",
    },
    "stacked_bar": {
        "name": "堆叠柱状图",
        "desc": "展示总量及各部分构成",
        "matplotlib": "plt.bar(x, y1, bottom=y2)",
    },
    "grouped_bar": {
        "name": "分组柱状图",
        "desc": "多组数据并列比较",
        "matplotlib": "多组并列 bar",
    },
    "histogram": {
        "name": "直方图",
        "desc": "数据分布展示",
        "matplotlib": "plt.hist(data)",
    },
    "box": {
        "name": "箱线图",
        "desc": "数据分布和异常值",
        "matplotlib": "plt.boxplot(data)",
    },
}

# ===== 生成Python绘图脚本 =====
def generate_plot_script(chart_type, data_json, title="", xlabel="", ylabel="",
                          color_scheme="default", width=10, height=6, dpi=150):
    """Generate a Python script that creates the chart image"""
    
    # Escape the data for embedding
    data_str = json.dumps(data_json, ensure_ascii=False)
    
    # Color schemes
    schemes = {
        "default": ["#2196F3", "#FF5722", "#4CAF50", "#FFC107", "#9C27B0",
                    "#00BCD4", "#E91E63", "#3F51B5", "#8BC34A", "#FF9800"],
        "professional": ["#2E86AB", "#A23B72", "#F18F01", "#C73E1D", "#3B1F2B",
                        "#3A7D44", "#7B2D8E", "#D62828", "#1D3557", "#457B9D"],
        "vibrant": ["#FF006E", "#8338EC", "#3A86FF", "#FB5607", "#06D6A0",
                   "#FFBE0B", "#FF006E", "#9C89B8", "#EF476F", "#118AB2"],
        "pastel": ["#FFB3BA", "#BAFFC9", "#BAE1FF", "#FFFFBA", "#E8BAFF",
                   "#FFD9BA", "#BAFFE8", "#FFBAE1", "#D9BAFF", "#BAFFD9"],
        "ceramics": ["#8B4513", "#CD853F", "#D2691E", "#A0522D", "#DEB887",
                    "#F4A460", "#8B7355", "#C4A882", "#B8860B", "#D2B48C"],
    }
    colors = schemes.get(color_scheme, schemes["default"])
    colors_str = json.dumps(colors)
    
    script = f'''"""
Auto-generated chart: {chart_type}
Generated at: {datetime.now().isoformat()}
"""
import json, sys, os, datetime
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
# CJK font fallback
import os as _os
for _fp in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simsun.ttc",
            "C:/Windows/Fonts/msyhbd.ttc", "/usr/share/fonts",
            "/System/Library/Fonts"]:
    if _os.path.exists(_fp):
        try:
            plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimSun", "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            break
        except:
            pass

# Data
data = json.loads({data_str!r})

# Colors
colors = {colors_str}

# Create figure
fig, ax = plt.subplots(figsize=({width}, {height}), dpi={dpi})
fig.patch.set_facecolor("white")

# Title and labels
if {title!r}:
    ax.set_title({title!r}, fontsize=14, fontweight="bold", pad=15)
if {xlabel!r}:
    ax.set_xlabel({xlabel!r}, fontsize=11)
if {ylabel!r}:
    ax.set_ylabel({ylabel!r}, fontsize=11)
'''

    # Chart-type specific code
    if chart_type == "bar":
        script += '''
# Bar chart
categories = data.get("categories", [])
values = data.get("values", [])
x = range(len(categories))
bars = ax.bar(x, values, color=colors[:len(categories)], width=0.6, edgecolor="white")
ax.set_xticks(x)
ax.set_xticklabels(categories, rotation=45, ha="right")
for bar, val in zip(bars, values):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(values)*0.01,
            f"{val}", ha="center", va="bottom", fontsize=9)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
'''

    elif chart_type == "barh":
        script += '''
# Horizontal bar chart
categories = data.get("categories", [])
values = data.get("values", [])
y_pos = range(len(categories))
bars = ax.barh(y_pos, values, color=colors[:len(categories)], edgecolor="white")
ax.set_yticks(y_pos)
ax.set_yticklabels(categories)
ax.invert_yaxis()
for bar, val in zip(bars, values):
    ax.text(bar.get_width() + max(values)*0.01, bar.get_y() + bar.get_height()/2,
            f"{val}", ha="left", va="center", fontsize=9)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
'''

    elif chart_type == "line":
        script += '''
# Line chart
categories = data.get("categories", [])
datasets = data.get("datasets", [{"label": "Data", "values": []}])
x = range(len(categories))
for i, ds in enumerate(datasets):
    color = colors[i % len(colors)]
    ax.plot(x, ds.get("values", []), "-o", color=color, linewidth=2,
            markersize=6, label=ds.get("label", f"Series {i+1}"))
ax.set_xticks(x)
ax.set_xticklabels(categories, rotation=45, ha="right")
ax.legend(frameon=True, fancybox=True, shadow=True)
ax.grid(True, alpha=0.3)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
'''

    elif chart_type == "scatter":
        script += '''
# Scatter plot
x_vals = data.get("x", [])
y_vals = data.get("y", [])
sizes = data.get("sizes", [50]*len(x_vals))
groups = data.get("groups", [])
if groups:
    unique = list(set(groups))
    for i, g in enumerate(unique):
        idx = [j for j, v in enumerate(groups) if v == g]
        ax.scatter([x_vals[j] for j in idx], [y_vals[j] for j in idx],
                  c=colors[i % len(colors)], label=g, s=60, alpha=0.7, edgecolors="white")
    ax.legend()
else:
    ax.scatter(x_vals, y_vals, c=colors[0], s=sizes, alpha=0.7, edgecolors="white")
ax.grid(True, alpha=0.3)
'''

    elif chart_type == "pie":
        script += '''
# Pie chart
labels = data.get("labels", [])
sizes = data.get("sizes", [])
explode = data.get("explode", None)
if explode is None:
    explode = [0.05] * len(labels)
wedges, texts, autotexts = ax.pie(sizes, labels=labels, autopct="%1.1f%%",
    startangle=90, colors=colors[:len(labels)], explode=explode,
    textprops={"fontsize": 10})
for t in autotexts:
    t.set_color("white")
    t.set_fontweight("bold")
ax.axis("equal")
'''

    elif chart_type == "radar":
        script += '''
# Radar chart
categories = data.get("categories", [])
datasets = data.get("datasets", [])
n = len(categories)
angles = np.linspace(0, 2*np.pi, n, endpoint=False).tolist()
angles += angles[:1]
for i, ds in enumerate(datasets):
    values = ds.get("values", []) + ds.get("values", [])[:1]
    ax.plot(angles, values, "-o", color=colors[i % len(colors)],
            linewidth=2, label=ds.get("label", f"Series {i+1}"))
    ax.fill(angles, values, alpha=0.1, color=colors[i % len(colors)])
ax.set_xticks(angles[:-1])
ax.set_xticklabels(categories, fontsize=9)
ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.0))
ax.set_theta_offset(np.pi/2)
'''

    elif chart_type == "heatmap":
        script += '''
# Heatmap
matrix = data.get("matrix", [])
row_labels = data.get("row_labels", [])
col_labels = data.get("col_labels", [])
im = ax.imshow(matrix, cmap="viridis", aspect="auto")
plt.colorbar(im, ax=ax, shrink=0.8)
if row_labels:
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels(row_labels)
if col_labels:
    ax.set_xticks(range(len(col_labels)))
    ax.set_xticklabels(col_labels, rotation=45, ha="right")
for i in range(len(matrix)):
    for j in range(len(matrix[0])):
        val = matrix[i][j]
        if isinstance(val, (int, float)):
            text = f"{val:.1f}"
            ax.text(j, i, text, ha="center", va="center",
                   color="white" if np.max(matrix) != np.min(matrix) and val > (np.max(matrix)+np.min(matrix))/2 else "black",
                   fontsize=8)
'''

    elif chart_type == "stacked_bar":
        script += '''
# Stacked bar chart
categories = data.get("categories", [])
datasets = data.get("datasets", [])
x = range(len(categories))
bottoms = np.zeros(len(categories))
for i, ds in enumerate(datasets):
    vals = ds.get("values", [])
    bars = ax.bar(x, vals, bottom=bottoms, color=colors[i % len(colors)],
                  label=ds.get("label", f"Part {i+1}"), width=0.6)
    bottoms += vals
ax.set_xticks(x)
ax.set_xticklabels(categories, rotation=45, ha="right")
ax.legend()
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
'''

    elif chart_type == "histogram":
        script += '''
# Histogram
values = data.get("values", [])
bins = data.get("bins", 10)
n, bins, patches = ax.hist(values, bins=bins, color=colors[0], edgecolor="white", alpha=0.7)
for i, patch in enumerate(patches):
    patch.set_facecolor(colors[i % len(colors)])
ax.set_xlabel(data.get("xlabel", "Value"))
ax.set_ylabel(data.get("ylabel", "Frequency"))
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
'''

    elif chart_type == "box":
        script += '''
# Box plot
datasets = data.get("datasets", [])
labels = [ds.get("label", f"Set {i+1}") for i, ds in enumerate(datasets)]
values = [ds.get("values", []) for ds in datasets]
bp = ax.boxplot(values, patch_artist=True, labels=labels)
for i, patch in enumerate(bp["boxes"]):
    patch.set_facecolor(colors[i % len(colors)])
    patch.set_alpha(0.6)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.grid(True, alpha=0.3, axis="y")
'''

    else:
        return None

    script += f'''
# Save
plt.tight_layout()
output = r"{OUTPUT_DIR!s}"
os.makedirs(output, exist_ok=True)
filepath = os.path.join(output, "chart_{chart_type}_{{}}.png".format(datetime.datetime.now().strftime("%Y%m%d_%H%M%S")))
plt.savefig(filepath, bbox_inches="tight", facecolor="white")
plt.close()
print(f"✅ Saved: {{filepath}}")
'''

    return script


# ===== 生成图表 =====
def generate_chart(chart_type, data, title="", xlabel="", ylabel="",
                   color_scheme="default", width=10, height=6, dpi=150):
    """Generate a chart image from data"""
    script = generate_plot_script(chart_type, data, title, xlabel, ylabel,
                                  color_scheme, width, height, dpi)
    if not script:
        return None, f"不支持的图表类型: {chart_type}"
    
    # Write script to temp file
    script_path = OUTPUT_DIR / f"_gen_{chart_type}_{datetime.now().strftime('%H%M%S')}.py"
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)
    
    # Execute
    try:
        r = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "PYTHONUTF8": "1"}
        )
        if r.returncode == 0:
            # Find output file
            outputs = list(OUTPUT_DIR.glob(f"chart_{chart_type}_*.png"))
            if outputs:
                latest = max(outputs, key=os.path.getmtime)
                log_generation(chart_type, data, str(latest))
                return str(latest), r.stdout
            return None, "输出文件未找到"
        else:
            return None, f"生成失败: {r.stderr[:500]}"
    except Exception as e:
        return None, f"执行错误: {e}"
    finally:
        if script_path.exists():
            script_path.unlink()


# ===== 记录生成日志 =====
def log_generation(chart_type, data, output_path):
    log = {"generations": []}
    if LOG_FILE.exists():
        with open(LOG_FILE) as f:
            log = json.load(f)
    log["generations"].append({
        "chart_type": chart_type,
        "data_keys": list(data.keys()) if isinstance(data, dict) else [],
        "output": output_path,
        "generated_at": datetime.now().isoformat(),
    })
    log["last_run"] = datetime.now().isoformat()
    if len(log["generations"]) > 500:
        log["generations"] = log["generations"][-250:]
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


# ===== 分析图片结构（模板匹配）=====
def analyze_image_structure(image_path):
    """
    Analyze image to determine chart type and structure
    Uses filename/context hints since full CV isn't available
    """
    name = Path(image_path).stem.lower()
    # Try to infer chart type from description
    chart_types = {
        "bar": ["bar", "柱状", "bars", "column"],
        "line": ["line", "折线", "trend", "curve", "plot"],
        "pie": ["pie", "饼", "circle", "环形"],
        "scatter": ["scatter", "散点", "point", "correlation"],
        "radar": ["radar", "雷达", "spider"],
        "heatmap": ["heat", "热力", "matrix"],
        "histogram": ["hist", "直方", "分布"],
        "stacked_bar": ["stacked", "堆叠"],
        "box": ["box", "箱线"],
    }
    for ct, keywords in chart_types.items():
        if any(kw in name for kw in keywords):
            return ct
    return "bar"  # default


# ===== 数据解析 =====
def parse_user_data(text):
    """Parse user-provided data into structured format"""
    text = text.strip()
    result = {"categories": [], "values": []}
    
    # Try JSON
    try:
        return json.loads(text)
    except:
        pass
    
    # Try CSV format: label,value or label value
    lines = text.split("\n")
    if len(lines) >= 2:
        # Check if it's a table
        for line in lines:
            parts = re.split(r"[, \t]+", line.strip(), maxsplit=1)
            if len(parts) == 2:
                try:
                    val = float(parts[1])
                    result["categories"].append(parts[0].strip())
                    result["values"].append(val)
                except:
                    pass
    
    if result["categories"]:
        return result
    
    # Try just numbers
    nums = re.findall(r"-?\d+\.?\d*", text)
    if nums:
        result["values"] = [float(n) for n in nums]
        result["categories"] = [f"#{i+1}" for i in range(len(nums))]
    
    return result


# ===== 主入口 =====
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    
    if cmd == "generate":
        # python chart_generator.py generate <chart_type> <data_json>
        if len(sys.argv) < 4:
            print("用法: python chart_generator.py generate <chart_type> '<data_json>' [title]")
            sys.exit(1)
        chart_type = sys.argv[2]
        data = json.loads(sys.argv[3])
        title = sys.argv[4] if len(sys.argv) > 4 else ""
        
        path, msg = generate_chart(chart_type, data, title=title)
        if path:
            print(f"✅ 图表已生成: {path}")
            print(f"📊 类型: {CHART_TEMPLATES.get(chart_type, {}).get('name', chart_type)}")
        else:
            print(f"❌ {msg}")
    
    elif cmd == "fromdata":
        # python chart_generator.py fromdata <chart_type>
        # Read data from stdin
        chart_type = sys.argv[2] if len(sys.argv) > 2 else "bar"
        data = parse_user_data(sys.stdin.read())
        path, msg = generate_chart(chart_type, data)
        if path:
            print(f"✅ {path}")
        else:
            print(f"❌ {msg}")
    
    elif cmd == "templates":
        print("📊 支持的图表类型:\n")
        for key, t in CHART_TEMPLATES.items():
            print(f"  {key:15s} {t['name']:10s} - {t['desc']}")
    
    elif cmd == "help":
        print("""
用法:
  python chart_generator.py generate <chart_type> '<json_data>' [title]
  python chart_generator.py fromdata <chart_type>  (从stdin读取数据)
  python chart_generator.py templates              (列出支持的图表类型)

数据格式 (JSON):
  bar:      {"categories":["A","B"], "values":[10,20]}
  line:     {"categories":["A","B"], "datasets":[{"label":"X","values":[1,2]}]}
  pie:      {"labels":["A","B","C"], "sizes":[30,50,20]}
  scatter:  {"x":[1,2,3], "y":[4,5,6], "groups":["g1","g1","g2"]}
  heatmap:  {"matrix":[[1,2],[3,4]], "row_labels":["R1","R2"], "col_labels":["C1","C2"]}

示例:
  python chart_generator.py generate bar '{"categories":["陶瓷A","陶瓷B","陶瓷C"],"values":[85,92,78]}' "陶瓷性能对比"
""")
