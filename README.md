# 数学建模 Workbench

由 [Wuyanqiao](https://github.com/Wuyanqiao) 维护的数学建模 Skill 与 DeepSeek Harness 插件，当前版本 **2.1.4**。

支持题目分析、模型设计、代码求解、科研绘图与论文交付，也可以只完成一个阶段或阶段中的一项任务。通用 Skill 通过对话询问配置；DSH 插件通过侧栏看板设置配置、导入材料和启动任务。两者使用相同的项目状态、算法资料和验证规则。

## 下载

| 安装包 | 使用方式 |
|---|---|
| [通用 Skill 2.1.4 ZIP](https://github.com/Wuyanqiao/math-modeling-skill/releases/download/v2.1.4/math-modeling-skill-2.1.4.zip) | 在支持 Skill 的 Agent 中加载，通过对话选择工作范围和偏好 |
| [DSH 插件 2.1.4 TGZ](https://github.com/Wuyanqiao/math-modeling-skill/releases/download/v2.1.4/dsh-math-modeling-ui-2.1.4.tgz) | 安装到 DeepSeek Harness，使用数学建模预设和可视化看板 |

[查看 2.1.4 Release 与校验值](https://github.com/Wuyanqiao/math-modeling-skill/releases/tag/v2.1.4)。`main` 保存通用 Skill 源码和使用资料，DSH 插件通过安装包交付。

## 功能特性

- **按范围执行**：完整流程、建模、编程与验证、论文，以及阶段内单项任务；续接项目时保留进度和已保存选择。
- **题目与材料**：登记原题、附件、论文模板及要求，支持 PDF、Word、Markdown、TXT、LaTeX 等格式；保留原件、哈希和提取状态。
- **模型与算法**：先读算法索引，再按问题加载优化、预测、评价、数值计算、几何、微分方程、反问题、动态决策等资料。每道子问题最多两个独立模型体系；同一物理机理的基础近似与高精度展开计为一个模型族。
- **可复现计算**：记录真实命令、参数、退出码、日志与产物哈希，覆盖无泄漏 Pipeline、敏感性分析和模型验证。
- **科研绘图**：基础路线使用 scientific-visualization 与 matplotlib；按需选择 SciencePlots 科研样式、drawio 可编辑论文框架图、scientific-schematics 概念或机制图、SciVisAgentSkills 三维/显微/分子可视化、seaborn 统计图。
- **可选协作**：规则核验、附件盘点、文献与模型调研、算法原型、独立实验、双语言对照、术语核验；额外协作按用户选择启用，阶段独立质检保留。
- **论文交付**：支持 Word、LaTeX/PDF 或两者，遵循用户模板与要求，正文结论对应真实结果与证据。
- **环境与恢复**：区分必需、当前配置需要和可选依赖，提供安装命令或 Agent 安装提示；支持运行日志、证据检查、快照和恢复预览。

## 安装通用 Skill

1. 下载并解压通用 Skill ZIP，得到 `math-modeling` 文件夹。
2. 将完整文件夹放入所用 Agent 的 Skill 目录，或按该宿主支持的方式加载其中的 `SKILL.md`。资料和工具通过相对路径读取，不要只复制入口文件。
3. 准备 **Python 3.11–3.13**。执行内核只使用标准库，科学计算和文档依赖按实际任务检查与安装。
4. 将题目放在独立的项目目录中，再向 Agent 提出任务。

也可直接获取 `main` 上的通用 Skill：

```bash
git clone --branch main --single-branch https://github.com/Wuyanqiao/math-modeling-skill.git math-modeling
```

首次使用：

> 使用 math-modeling Skill 处理这个项目。先询问执行范围、原题与附件、论文格式与要求、绘图工具和可选协作，再检查环境；沿用我已经明确的选择。

只执行一项：

> 继续当前项目，只做编程阶段的“运行最小求解并验收”。保留现有配置和项目范围，缺少前置结果时先告诉我。

Agent 会分组询问尚未确定的选项，说明每项用途并保存选择。未启用的可选工具和协作不会自行开启；宿主没有问答按钮时，用普通对话选择。详见 [交互配置](references/交互配置.md) 和 [使用指南](使用指南.md)。

需要预先安装常用依赖时，在解压后的 `math-modeling` 目录执行：

```bash
python -m venv .venv
# 激活虚拟环境后，按实际任务选择依赖组
python -m pip install ".[science,figure,docx,pdf,xlsx,validation]"
```

用 `python scripts/mathmodel.py --help` 检查入口。Skill 安装目录与题目目录应互不包含。环境与命令行说明见 [安装说明](docs/installation.md)。

## 安装 DSH 插件

已验证宿主为 **DeepSeek Harness 0.1.7-alpha.1**；本机验证使用 Windows、Node 24 与 Python 3.13。

下载 `.tgz` 后，在已安装 DSH 的终端中执行，替换实际下载路径与 profile 名称：

```powershell
dsh plugin --profile web add "C:\Downloads\dsh-math-modeling-ui-2.1.4.tgz" -w --ignore-scripts
```

升级前备份 profile，待运行中的 Agent 结束后重启 DSH 后端并刷新界面。

1. 选择工作区和 **数学建模 Workbench** Agent 预设。
2. 打开右侧栏，在“工作区文件”“新建终端”下方进入 **数学建模 Workbench**，首次进入自动初始化当前项目。
3. 在“材料”页添加题目、附件、模板和要求，在“配置”页选择绘图、协作选项并检测环境。
4. 点击右上角 **开始**，选择完整流程、单个阶段或阶段中的一项，再点击 **确认开始**。
5. 在看板所属会话查看执行过程，在“项目、证据、运行、快照”页查看状态和结果。

启动沿用所属会话的模型与权限。“已提交”表示宿主接收任务，完成状态依据实际结果与审核。详细安装、旧预设迁移和 Windows 排错见 [DSH 安装说明](docs/DSH安装.md)。

## 项目文件与来源

项目状态保存在题目目录的 `.math-modeling/`。切换 Agent 时，可在同一项目目录续接已有状态。论文结论需要真实计算、推导或来源支撑；竞赛规则以当届官方要求为准。见 [共享运行时](references/共享运行时.md) 和 [运行时 API](RUNTIME_API.md)。

本项目基于 [XiaoMaColtAI/math-modeling-skill](https://github.com/XiaoMaColtAI/math-modeling-skill) 扩展，由 Wuyanqiao 维护。第三方资料和工具保留原来源与许可，不因项目名称或发布版本改变条款；参见 [第三方说明](THIRD_PARTY_NOTICES.md)。
