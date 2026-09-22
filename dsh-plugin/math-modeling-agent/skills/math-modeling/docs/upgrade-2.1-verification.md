# 2.1.0 能力升级与验收记录

基于已同步上游的 `WuYanqiao/universal-upgrade`，延续 [2.0.0 的运行时与证据合同](upgrade-verification.md)。这一版新增项目输入与配置、按需算法资料、科研绘图集成，以及数据预处理和模型验证独立模块。原始审查、历史缺陷和旧版本成绩保留其原有日期与版本。

## 使用变化

- 在 DeepSeek Harness 中选择数学建模 Workbench 预设，打开右侧栏，在“工作区文件”“新建终端”之后点击数学建模入口，即在该会话工作区幂等初始化；已有项目直接打开并迁移兼容字段。
- 六页分别为项目、材料、配置、证据、运行、快照。材料页保存原题、附件、论文模板与要求；支持 PDF、DOCX、Markdown、TXT、LaTeX 等原文件。旧 DOC 等无法直接抽取的材料仍保存并显示具体限制，不假装已读取。
- 配置保存五项绘图偏好和七项可选 Subagent 协作，关闭状态同样持久化。绘图开关名称下方常驻显示用途小字；额外说明保留在悬停提示。基础 scientific-visualization 与 matplotlib 按绘图任务加载。
- 配置页的“环境与依赖”按已保存项目配置检查实际解释器与软件，区分基础必需、当前配置需要和可选项，提供逐项及当前缺失项的复制命令/安装 Prompt。不会自动安装，也不会把所有三维后端列为必装；检测失败、过期结果和未在线核验的服务明确标记。
- 延续 DSH 原生主题、字体、圆角和蓝色交互色，无 slogan；滚动条默认隐藏，悬停或滚动时显示。输入与配置变化产生新的项目上下文，并使关联科学审核过期。
- 每道子问题至多两个独立模型体系。同一物理机理的基础近似与高精度展开算一个模型族；这一语义限制由前置合同与独立审查核验，运行时不凭模型名称自动判定科学独立性。

## 能力与实际验证

| 项目 | 本次证据与边界 |
|---|---|
| 六类算法模块 | 数值计算、计算几何、机理微分方程、反问题、动态控制、不确定性优化；解析解、独立穷举、网格收敛与信息时序检查。先读算法索引，按问题加载 |
| 数据预处理 | Simple/KNN/Iterative、编码、尺度、比例/周期特征、random/group/time/group_time；真实 sklearn 检查测试数据变化不影响训练拟合，每个 CV 折独立拟合 |
| 模型验证 | 三段划分、交叉/分组/滚动验证；局部/Morris/Sobol；Bootstrap、参数后验与预测区间；求解状态、目标界、约束残差、单位量纲、初边值与网格细化 |
| 全局敏感性 | 真实 SALib 1.6.0：加性模型 Morris μ*=[1,2]，Sobol 一阶与总效应约 [0.2,0.8]；另测试纯交互模型。使用合成函数验证算法，不作为赛题实证 |
| 求解状态 | 真实 HiGHS 线性规划目标与界均为 10，残差通过；FEASIBLE 不支持已证明最优，UNKNOWN/非有限输出及错误界方向不会获得最优支持 |
| 绘图 | 同一组合成数据比较默认与增强样式；中文/英文、PNG/PDF/SVG/灰度，300 dpi、实际画布尺寸、字体及样式恢复检查；SciencePlots 2.2.2 实际运行 |
| 材料与配置 | 核心行为测试覆盖原文哈希、提取限制、路径边界、旧字段迁移、配置失效、恢复与输入完整性。实际官方 DSH 宿主测试包含 20 MiB 文件和 30,000 中文字符要求 |
| DSH 界面 | 真 Edge/React，六页、常驻用途说明、开关保存、材料导入、项目切换、迟到响应、深浅主题、窄屏、滚动条。RPC/外围会话框架仍为 fixture |
| 环境面板 | 查看实际解释器与分类状态、复制命令/Prompt、配置及输入变化后过期、检测失败和跨会话迟到响应；检查过程不更新项目状态或执行安装 |
| Skill 兼容 | 根入口、两个自有集成入口及四个内置科研 Skill frontmatter 校验；保留上游原始哈希、适配后哈希和许可证 |
| 独立 wheel | 2.1.0 在不继承系统包、无可选依赖的独立环境安装；八个资源、三个 profile 的 init/state/complete，以及中文材料导入、配置保存、控制台版本均通过 |
| 分发预检 | 两份内嵌 Skill 各 297 个源文件、零漂移；完整 Skill/DSH 包资源审计与中文空格路径烟雾测试通过。最终安装包在提交后重新构建并记录干净源码身份 |

本机完整回归 **Python 314/314（60.238 秒）、DSH 29/29（33.7574 秒）通过，无失败、无跳过**。Python 和 DSH 回归分别保存在源码 `project-review/logs/upgrade-2.1-python.log`、`upgrade-2.1-dsh.log`。数值验证见同目录 `model-validation-verification.json`，图形验证见 `figure-style-comparison/verification.json`，界面截图见 `sidebar-config.png`、`sidebar-materials.png`、`sidebar-environment.png`。审查日志不进入功能分发包。

## 重放

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python tools/docx/scripts/self_check.py
python -m compileall -q mathmodel_runtime scripts tools assets/algorithms references/roles/编程手/scripts
node --test tests/dsh/*.test.mjs
python scripts/sync_dsh_plugin.py --check
python scripts/build_distribution.py --mode local-development --output dist
python -m build --wheel --outdir dist/runtime
```

真实宿主及浏览器用例需配置 `DSH_TEST_NODE_MODULES`，见 [DSH 回归说明](../tests/dsh/README.md)。未安装依赖时明确跳过；模拟测试、官方服务挂载、浏览器交互和完整桌面端到端验收分别表述。

## 安装与外部工具

同名 DSH bundle 更新需重启后端；备份选中 profile 的包、锁和补丁配置后，用官方 CLI 安装 2.1.0 tarball，再重启该 DSH 进程。保留其他 bundle、会话、项目和用户自定义外部 Skill 路径。具体安装源提交与逐文件哈希记录在分发清单，本机安装收据单独保存在 DSH 备份目录。

面板选项代表项目偏好，不能作为外部服务已执行的证据。drawio 输出可编辑 XML；scientific-schematics 的外部生成器需要相应服务配置；SciVisAgentSkills 通过固定提交和 SHA 的加载器按选定任务读取资料，实际 3D/显微/分子后端仍需可用。此轮没有声称调用了这些外部生成服务或完成真实三维仿真。来源与调用条件见 [绘图集成](../tools/figure/INTEGRATIONS.zh-CN.md)。
