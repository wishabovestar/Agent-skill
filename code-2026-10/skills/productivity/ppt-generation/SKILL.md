---
name: ppt-generation
description: "Use when 撰写/生成/渲染 PPT(.pptx)：中文排版、配色、视觉 QA。"
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [ppt, pptx, slides, chinese, presentation]
    related_skills: [powerpoint, cn-application-diagrams, project-application-materials]
---

# 生成中文 PPT — 本机原生工具链

## When to Use / 何时用

- 用户要「写 PPT / 做汇报稿 / 生成幻灯片 / 申报答辩 PPT」
- 需要把 Markdown 大纲转成 .pptx
- 需要把已有 .pptx 转成图片做视觉检查
- ⚠️ 不适用：单纯读 .pptx 文本（也可用本工具 `read`，比 markitdown 少一个依赖）

## 工具

`D:/hermes/analysis/ppt_tool.py`

```bash
T="D:/hermes/analysis/ppt_tool.py"
python "$T" check                        # 依赖自检（含 PowerPoint COM）
python "$T" build deck.md -o out.pptx -t navy   # MD -> PPTX；主题 navy|gray|dark
python "$T" read out.pptx                # 提取文本 + 备注
python "$T" render out.pptx -o png/ --pdf # -> 逐页 PNG（+可选 PDF），走 PowerPoint COM
python "$T" qa out.pptx                  # 空页/占位符/字号过小/中文缺 a:ea
python "$T" check-fonts out.pptx         # 回读 XML 证明 a:ea 真写入
```

Markdown 约定：`# ` = 新页（首个作封面）｜`## ` = 页内小节｜`- `/`* ` = 要点｜
`1.` = 有序｜`> ` = 演讲者备注｜`---` = 强制分页｜`<br>` = 换行

## ⭐ 三条硬教训（都是实测踩出来的）

### 1. 中文字体：只设 `font.name` 是【无效的】

python-pptx 的 `run.font.name = "微软雅黑"` 只写 `<a:latin>`，**中文不走 latin**，会回退到主题默认字体。
要真生效必须另写 `<a:ea typeface="微软雅黑"/>`（+ `a:cs`），且 `a:ea` 在
`CT_TextCharacterProperties` 里**必须排在 `a:latin` 之后、`a:sym` 之前**。

```python
rPr = run._r.get_or_add_rPr()          # ⚠️ 不可用 run._r.rPr（可能为 None）
_ensure_typeface(rPr, "a:ea", "微软雅黑", ("a:cs","a:sym","a:hlinkClick","a:hlinkMouseOver","a:rtl","a:extLst"))
```

这与 `md2docx_cn.py` 的 `w:eastAsia` 坑是**同一个坑的变体**（Word 侧叫 `w:eastAsia`，PPT 侧叫 `a:ea`）。
✅ 必须用 `ppt_tool.py check-fonts` **回读 XML 自证**，不要相信“我设过了”。

### 2. 本机【没有 LibreOffice】—— 渲染走 PowerPoint COM

`powerpoint` 技能文档的 QA 路径是 `soffice --convert-to pdf` + `pdftoppm`，**本机两者都没装**。
但本机有 **PowerPoint COM（Office 12.0）**，可直出 PNG 与 PDF：

```python
import win32com.client as w
app = w.Dispatch("PowerPoint.Application")
pres = app.Presentations.Open(path, WithWindow=False)
for i, sl in enumerate(pres.Slides, 1):
    sl.Export(f"slide-{i:02d}.png", "PNG", 1600, 900)   # 逐页 PNG
pres.SaveAs(out_pdf, 32)                                  # 32 = ppSaveAsPDF
```

⚠️ 中文环境下 `Export(folder,'PNG')` 会生成 `幻灯片1.PNG`；**逐页 Export 才能控命名**。

### 3. 视觉 QA 必须【真看图】，三轮才收敛

用 `vision_analyze` 看渲染出的 PNG。本工具首版被看出的真缺陷：

| 缺陷 | 根因 | 修法 |
|:--|:--|:--|
| 封面/标题栏四角露白，“卡片悬浮”感 | 全幅底色用了 `ROUNDED_RECTANGLE` | 改 `RECTANGLE`（`bar(..., rounded=False)` 默认） |
| 正文堆在上半部、下半页全空 | 起始 y 写死 1.55"，未随条目数均衡 | 按条目数估块高，用 0.42×余量下移（⚠️ 0.5 会偏下） |
| 封面文字块偏上 | 起始 y 写死 | 按标题行数估高后垂直居中 |
| **正文字号偏小** | 照抄技能文档的 14-16pt —— **那是按 4:3 写的** | 16:9 (13.33") 幅面用 **24-26pt**（n≤3） |

⇒ **照抄技能里的字号表会偏小**：先看幅面是 4:3 还是 16:9 再定字号。

## 主题配色（复用既定标准）

| 主题 | 用途 | 主色 |
|:--|:--|:--|
| `navy` | 深蓝金正式系（汇报/答辩） | `#16365C` / 金 `#C98A1B` / 文字 `#2B3A4A` |
| `gray` | 申报书黑白风格 | `#1A1A1A` / `#444444` / 底 `#F2F2F2` |
| `dark` | 全文深色 | `#21295A` / 青 `#00A896` |

取自 `cn-application-diagrams`，**不另立标准**。

## 交付惯例（用户偏好）

- 中文正式材料用**微软雅黑**；`md2docx_cn.py` 侧正文用仿宋_GB2312（Word 文档，非 PPT）
- 申报类六段式：一、研究背景 / 二、研究目标 / 三、研究内容 / 四、技术路线 / 五、研究基础与团队 / 六、预期成果
- 产物路径直说绝对路径；CLI 无附件通道，不要说“已发送文件”
