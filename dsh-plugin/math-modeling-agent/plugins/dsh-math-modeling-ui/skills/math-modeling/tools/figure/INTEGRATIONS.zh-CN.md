# 绘图能力与项目配置

先读取共享运行时的 `context` 或 `.math-modeling/project-context.md`，以 `project.graphicsTools` 为准。
`scientific-visualization` 与 `matplotlib` 为基础能力；其他开关只在用户选择后参与路由。
已有 MATLAB 工作流仍可使用原工具，不为风格切换改写已经验证的求解结果。

| 情境 | 按需加载 | 交付与检查 |
|---|---|---|
| 每次绘图前定义数据、误差和版面 | [scientific-visualization](skills/scientific-visualization/SKILL.md) | 变量/单位、重复样本、缺失值、变换、最终尺寸与图注 |
| 绘制坐标轴、布局、标注与导出 | [matplotlib](skills/matplotlib/SKILL.md) | Figure/Axes 接口，局部样式，保留可执行代码与原数据 |
| `scienceplots=true` | [SciencePlots 官方说明](https://github.com/garrettj403/SciencePlots) | 先 import scienceplots，再使用 science + no-latex；中文另检查本机字体 |
| `seaborn=true`，统计比较/分布/热图 | [seaborn](skills/seaborn/SKILL.md) | 明确聚合与误差定义；axes-level API 拼入 Matplotlib 多面板 |
| `drawio=true`，论文框架/方法流程 | [drawio 适配](integrations/drawio/SKILL.md) | 可编辑 .drawio 源文件，按论文需要导出 SVG/PDF，逐节点核对模型依据 |
| `scientific-schematics=true`，概念/机制图 | [scientific-schematics](skills/scientific-schematics/SKILL.md) | 仅示意；先检查生成服务，保留提示词、版本、审阅记录，不把栅格改扩展名当矢量 |
| `scivis-agent-skills=true`，三维/显微/分子数据 | [SciVisAgentSkills 适配](integrations/scivis-agent-skills/SKILL.md) | 按数据加载 ParaView/napari/VMD/TTK 对应资料；记录尺度、相机、传递函数及所用软件 |

## 兼容约定

- 关闭的开关必须保持关闭；安装了库不表示用户选择了它。基础绘图不依赖 OpenRouter、ParaView、napari、VMD 或 draw.io 桌面端。
- 配置项表达用户偏好，不证明软件已安装。检查依赖后运行；缺失时说明具体组件，数据图可以使用已安装 Matplotlib。示意图生成服务或三维工具缺失时不得宣称成功调用。
- `scientific-schematics` 的原始生成器通过 OpenRouter 发送提示词和图像，需要用户配置 `OPENROUTER_API_KEY`；面板勾选不会自动发送项目文件或读取其他应用的密钥。当前宿主有用户已授权的图像生成工具时可采用该工具，并如实记录实际后端。
- 外部示例的版本锁与期刊尺寸是来源快照。沿用本项目 Python 3.11–3.13 和既有依赖环境；只有用户目标刊物或模板的实际要求可以成为硬验收条件。
- 数据图不得使用图像生成补出数据点、实验照片或仿真结果。概念图不能代替结果证据；模型数量按模型族计算，绘图后端不另算模型体系。
- 样式提升必须保留原始数值、缺失间断与统计口径。用标记/线型冗余编码，图注交代误差和样本数；导出后检查真实物理尺寸、字体与裁切，再查看 PNG。

## 代码组织

原有 `tools/figure/scripts` 接口保持可用。新图使用项目设置驱动的样式上下文，避免全局 rcParams 污染其他图。将脚本目录加入 Python 路径后：

```python
from project_style import project_style, series_style
from export_figure import export_figure
import matplotlib.pyplot as plt

with project_style(project_root=PROJECT_ROOT, lang="zh", journal="general") as applied:
    fig, ax = plt.subplots(figsize=(5, 3.5), layout="constrained")
    ax.plot(x, y, **series_style(0, sample_count=len(x)))
    ax.set(xlabel="时间 / s", ylabel="温度 / °C")
    export_figure(fig, "figures/temperature", size_inches=(5, 3.5), formats=["pdf", "svg", "png"])
    plt.close(fig)
```

`x/y` 必须来自项目实际数据。`applied` 记录是否真实启用 SciencePlots；上下文退出后恢复原样式。指定 `size_inches` 的默认导出保留物理尺寸，确需裁剪时显式传 `tight=True`。
`skills/scientific-visualization/scripts` 另外提供图像元数据检查、调色板对比度审计和导出规划工具；调用时使用其绝对路径，避免与旧版同名 `figure_export.py` 混淆。
所有产物仍经 `artifact-add` 关联实际运行与子问题，并为支撑主张的图填写证据定位。

## 来源

四个内置 K-Dense Skill 固定于提交 `49c6e97775eaa18ba791bebe23162a70ae601c18`。
[上游与逐文件哈希](skills/UPSTREAM.json)记录原始内容和本地适配，保留 [MIT 许可证](skills/LICENSE.md)。
适配包含移除自动向用户论文插入作者宣传引用的要求、将兼容性说明保留到通用 frontmatter 的 `metadata`，以及补充项目配置的优先级；实际使用软件的来源在本项目第三方说明中保留。
SciVisAgentSkills 通过固定版本加载器按任务获取资料，不将未标明许可证的全文重新发布到本仓库。
