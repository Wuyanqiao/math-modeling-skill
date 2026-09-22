---
name: mathmodel-scivis-agent-skills
description: 在数学建模项目选择 SciVisAgentSkills 后，按三维仿真、显微图像、分子或拓扑数据加载对应的固定版本 Skill，保留尺度和可复现可视化状态。
---

# SciVisAgentSkills 按任务适配

先读项目 context；仅在 `graphicsTools.scivis-agent-skills=true` 且数据类型相符时使用。
来源：[KuangshiAi/SciVisAgentSkills](https://github.com/KuangshiAi/SciVisAgentSkills)，固定提交 `5c9ce7d28905af949dc4192b8984a44a7a5d9402`。

| 数据/任务 | 加载器 tool | 运行依赖与检查 |
|---|---|---|
| 网格、体场、流场、等值面 | paraview | ParaView 的 pvpython，网格尺度、变量关联、传递函数、相机与色标 |
| 显微多通道/时序图像 | napari | napari 及格式读取器，体素间距、通道、强度范围；输出视口而非整个桌面 |
| 分子结构与轨迹 | vmd | VMD/MDAnalysis，拓扑、单位、帧区间、周期边界及原子选择 |
| 标量场拓扑 | ttk | ParaView + TTK，标量字段、持久性阈值及保留结构 |

在项目工作目录调用：

```bash
python "<SKILL_ROOT>/tools/figure/scripts/load_scivis_skill.py" --tool paraview --cache-dir .math-modeling/skill-cache
```

脚本从原作者仓库下载固定版本的对应 SKILL.md 和它引用的同目录资料；校验预置 SHA-256后返回本地入口。
首次使用需要网络；已有校验一致的缓存可以离线读取。仅读取匹配任务的一份 Skill 和所需参考，不批量加载四套文档。
读取返回的 SKILL.md 后，按当前宿主修正其中过时的安装说明和路径假设；它不替代项目的权限、模型上限和证据契约。

不要因为选择本选项就在核心 Python 环境安装所有 GUI/分子软件。检查目标工具可执行文件与版本，保留独立环境。
无目标工具时报告缺失能力；已有求解结果可另画二维切片，但应如实标记实际后端。
保留真实输入、渲染脚本、版本、相机、色标范围、抽样规则与输出图；图像增强必须记录且不能创造原数据不存在的结构。
这些图不替代数值守恒、收敛或误差检验。
