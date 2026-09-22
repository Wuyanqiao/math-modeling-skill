# DeepSeek Harness 数学建模工作台

本适配器把通用 Skill 接入 DeepSeek Harness，当前本地开发版本为 **2.1.2**。流程规则、产物验证、证据、审查回执和完成判定全部由共享 Python 运行时负责；DSH 插件提供宿主授权的 shell/文件调用、会话绑定、工具与状态看板。

本次升级在 `WuYanqiao/universal-upgrade` 分支，尚不能把仓库 `main` 当作已包含这些改动的版本。完整发行包由根目录构建器生成。当前只允许本地开发验证包；上游资料的再分发授权尚未齐备，npm 包设置 `private: true`、`license: UNLICENSED`，不表示本项目获得了这些资料的许可证。

## 已核验宿主

目标为官方 **DeepSeek Harness 0.1.7-alpha.1**，源码基准 [`c36a83ff6bb95e3f82cf79f9be7c724270a8aa61`](https://github.com/deepseek-ai/deepseek-harness/tree/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61)。实测为 Windows、Node 24.11.1、PowerShell、Python 3.13.13。安装依赖 Commander 15 要求 Node ≥22.12.0；本项目没有对该最低版本作实际回归。

该版本通过 profile 的 bundle 注册预设，不再扫描 `.agent-presets` 目录。`agent.cordis.yml` 和 `preset.yml` 保留为可读 composition 与兼容资源；实际入口是 `plugins/dsh-math-modeling-ui/cordis.patch.yml`，同时加入 UI 和 `@deepseek-ai/dsh-agent-preset`。安装后可改预设显示名；入口以当前会话预设的实际 workbench 能力或已初始化项目判断是否显示。

## 从当前源码构建

在此升级分支的仓库根目录执行：

```powershell
python scripts/build_distribution.py --mode local-development --output dist
```

解压生成的 `mathmodel-dsh-*-LOCAL-DEVELOPMENT.zip`，在解压目录找到：

```text
math-modeling-agent/
  agent.cordis.yml
  preset.yml
  skills/math-modeling/                       # 通用 Skill 兼容副本
  plugins/dsh-math-modeling-ui/
    package.json
    cordis.patch.yml                          # 实际宿主安装入口
    lib/                                     # 宿主适配器
    client/                                  # React 看板
    skills/math-modeling/                     # npm 包内完整运行时
    LOCAL_DEVELOPMENT_ONLY.txt
    distribution-manifest.json
```

不要直接对未生成 `skills/math-modeling/scripts/mathmodel.py` 的源插件目录打包并当作完整发行包。构建器校验资源、复制工具脚本与模板，执行运行时冒烟检查，并生成 SHA-256 清单。

## 安装到选定的 profile

先使用独立 `DSH_HOME` 验证；下列变量只影响当前 PowerShell。将 `$bundlePath` 改为解压得到的 npm 包目录。

```powershell
$bundlePath = 'D:\your-build\math-modeling-agent\plugins\dsh-math-modeling-ui'
$packageOutput = Join-Path $env:TEMP 'mathmodel-local-pack'
New-Item -ItemType Directory -Force -Path $packageOutput | Out-Null
Push-Location $bundlePath
npm pack --ignore-scripts --pack-destination $packageOutput
Pop-Location

$env:DSH_HOME = Join-Path $env:TEMP 'mathmodel-dsh-validation'
$archivePath = Join-Path $packageOutput 'dsh-math-modeling-ui-2.1.2.tgz'
dsh plugin --profile web add $archivePath -w --ignore-scripts
dsh --profile web --dump-config
dsh --profile web
```

`.tgz` 安装已在官方 CLI 和全新临时 profile 上实际成功，配置输出包含 `dsh-math-modeling-ui`、`preset-math-modeling` 和 `dsh-math-modeling-ui/workbench`。本机 pnpm 10 对 Windows 跨盘目录参数生成了错误的 `link:` 路径，因此这里使用 tarball。默认 profile 禁止自动安装 peer 时会提示缺失 peer；宿主从其安装位置提供这些组件，仍应通过真实挂载检查确认可用。

确认验证结果后，再按你的桌面工作台配置选择实际 `DSH_HOME` 与 profile。不要猜测个人 AppData 路径，也不要复制或覆盖整个宿主配置。此实现保留宿主当前授权与沙箱策略；安装或运行失败时查看实际错误，不自动扩大权限。`dsh plugin --profile web --help` 会透传给 pnpm 并产生 profile 操作日志，查询启动器用法应使用 `dsh --help`。

## 从 2.1.0 升级

2.1.2 同时修复 Windows DSH 受限沙箱下 Python 3.13 探测临时目录的权限兼容问题。从 2.1.1 更新时按上面的 tgz 安装步骤替换插件，重启宿主后在配置页重新检测环境；检测继续遵守现有沙箱授权。

2.1.1 在预设的 workbench 插件节点增加 `isolate.mathModelWorkbench: true`。缺少此声明时，官方注册器会报 `agent-preset/invalid`，原因是 `Preset services require isolate realms: mathModelWorkbench`，新会话无法创建。

安装新包前备份实际 profile 配置；安装后检查该 profile 的 `cordis.patch.yml` 是否另存了数学建模预设的 `config.plugins` 覆盖列表。如果存在，须在其中 `name: dsh-math-modeling-ui/workbench` 的节点同步增加下列声明，并保留其他节点和用户自定义配置。旧覆盖仍生效时，仅替换包内声明不足以修复问题。

```yaml
isolate:
  mathModelWorkbench: true
```

在当前任务结束后重启宿主，使已导入的插件和预设重新加载。通过真实预设创建新会话确认可用；`--dump-config` 只能确认合成配置，不能替代实际挂载与会话创建验证。

## 会话内使用

在独立于 Skill 的项目目录创建会话，选择“数学建模 Workbench”预设，然后从右侧栏“开始”页进入 Workbench。首次打开看板由 `mm.ensureProject` 自动初始化当前会话工作区，已有项目则幂等读取；进入“配置”页后可保存任务范围、论文格式和工具偏好。仅展开开始页不会写入项目。

需要自定义项目根、质量配置或子问题时，调用 `mm_project_init`，选择 `scope=full|modeling|programming|paper`、`profile=balanced|short|competition`、论文格式及子问题，并可显式指定 `projectRoot`。绑定由宿主 settings 持久化，每次操作重新定位当前会话。项目状态在 `<project>/.math-modeling/state.json`。

常用流程：

1. 首次打开看板自动初始化，或显式 `mm_project_init`；导入题面与附件、保存要求及配置，然后执行 `mm_context` → `mm_doctor` → `mm_phase_enter`。
2. `mm_run` 执行真实命令，登记 inputs/code/outputs 与退出状态。
3. `mm_artifact_add`、`mm_claim_add` 连接产物、子问题与论证证据。
4. `mm_gate` 的 `prepare` 生成审核任务与快照；独立审核者读取证据后提交 `record` 回执。
5. `mm_check_deliverables` 排查阻塞，最后用 `mm_complete` 重新验证；判断完成必须查看 `done`，不能只看请求的 `ok`。

`reviewer_id`、`review_source` 是审计声明，不是宿主认证凭据。不能用一个不同的字符串证明独立审查。快照或产物变更会使相关审查失效。

材料与配置工具为 `mm_configure`、`mm_context`、`mm_input_list`、`mm_input_read` 和 `mm_input_import`；后者导入当前项目内已有文件，面板上传使用分块接口。`mm_environment` 按项目已保存配置检测环境与依赖，返回实际 Python 解释器、分类状态和安装建议，不执行安装。其他工具包括 `mm_state`、`mm_skill_read`、`mm_todo`、`mm_log`、`mm_checkpoint`、`mm_artifact_read`、`mm_run_log_read`、`mm_ui_toggle`。恢复检查点先查看默认预览，再以预览返回的 revision 应用恢复。精确请求格式见 [运行时 API](../RUNTIME_API.md)。

## 看板与验证边界

选择数学建模 Workbench 预设后打开右侧栏“开始”页，在“工作区文件”“新建终端”下方点击 Workbench。进入看板时自动初始化当前会话工作区，已有项目则幂等读取。仅展开开始页不会写项目。识别基于当前会话投影的预设 composition 能力，修改显示名称不影响识别；无匹配预设且无项目时不显示入口。

看板有“项目、材料、配置、证据、运行、快照”六页，沿用 DeepSeek Harness 原生字体、主题、圆角与克制的蓝色交互色。图标按钮使用悬停提示，键盘标签导航可用，不含 slogan，所有内容滚动条在悬停或滚动时显示。

“材料”支持多文件选择/拖放，分类为原题、原题附件、论文模板或论文要求；单文件上限 20 MiB，以 1 MiB 分块通过宿主授权文件接口暂存，再由运行时校验和登记。原件不覆盖，并记录大小和 SHA-256。TXT/Markdown/LaTeX 按实际编码提取文本，DOCX/PDF 按解析能力报告已提取、部分、待解析或失败；“已提取文本”不保证公式、图片和排版完整。Word 旧 .doc 和其他二进制保留原件。预览显示提取说明与截断提示。论文要求可直接输入，最多 30,000 字符，保存来源“用户面板填写”；它不自动成为经核实的竞赛官方规则。

“配置”持久保存项目名称、范围、论文格式、五项绘图偏好和七项额外协作开关。基础 scientific-visualization/matplotlib 始终启用，相关绘图规范与脚本随 Skill 提供，Python 库和外部软件仍须通过环境检查。五项可选绘图开关默认关闭，每项都有常驻用途小字和悬停说明：

| 选项 | 常驻用途说明 | 使用提示 |
|---|---|---|
| SciencePlots | 参考科研绘图样式库 | 没有 LaTeX 时使用 `no-latex` |
| drawio | 画可编辑的论文框架图 | 保留 `.drawio` 源文件 |
| scientific-schematics | 画概念或机制示意图 | 生成服务需要单独配置 |
| SciVisAgentSkills | 画三维仿真、显微图像和分子可视化图 | 按任务检查所需软件 |
| seaborn | 画统计比较、分布图和热图 | 基于真实数据选择统计表达 |

七项可选协作为规则核验、附件盘点、文献与模型调研、算法原型、独立实验、双语言对照和术语核验，全部默认关闭。保存开关只改变项目工作偏好，不表示相关软件或 API 已可用；明确关闭也会持久保存。独立门禁质检始终保留。

“配置”页的“环境与依赖”通过 `mm.environment` 检测当前会话绑定项目的**已保存配置**，不会使用尚未保存的开关草稿。结果显示检查时间、实际 Python 解释器路径与版本，并将依赖分为必需、已选和可选；状态分别表示已就绪、缺失、检测错误或需人工配置。`ready` 只评价必需与已选项，不能把请求 `ok:true` 理解为环境已经齐备。点击检测不安装软件、不修改配置、不写入项目状态；密钥只检查是否配置，不返回或展示密钥内容，也不联网验证服务可用性。

可以复制报告提供的安装命令，或把安装提示交给当前 Agent，经过正常的宿主授权流程执行。命令面向报告中的实际解释器，避免把库装进另一个 Python 环境；手工安装的软件或外部服务可能只提供说明，没有可直接运行的命令。安装后再次检测确认结果。Host 授权失败、探测超时、损坏的库和缺失依赖会明确显示，不假装检测通过。单次宿主调用上限为 90 秒；环境检测只在用户发起时执行，开始页和看板状态轮询不会反复探测依赖。

配置和材料索引持久化到项目，`.math-modeling/project-context.md` 提供通用 Agent 可读的上下文；DSH 在会话上下文中加入保存的配置和材料索引，Agent 通过 `mm_context` 获取最新核验内容、`mm_input_read` 读取具体材料。附件文本和自定义要求作为用户资料，不提升为系统指令；算法先查索引、每子问题最多两个独立模型体系、绘图按集成路由的约定也写入上下文。

开始页每 2 秒、看板每 5 秒只读检测状态；标签不可见时暂停，重新显示或窗口重新获得焦点时读取。开始页只读检测不运行 shell；首次打开看板会调用自动初始化，“重新验证”和产物/日志/恢复操作经宿主授权调用共享 CLI。每次操作使用该侧栏标签的 `sessionId`，同会话项目变化或关闭设置时清除旧预览。状态栏显示保存或核验时间，UI 不自行推断完成。二进制产物返回元数据，可使用宿主文件预览器查看。

“快照”页支持创建项目快照，并按名称、时间和创建时验收状态列出快照。选择“预览恢复”后，先查看新增、替换和删除的文件清单，再点击“确认恢复”，或选择“取消恢复”。预览后的文件变化会触发冲突并要求重新预览；切换会话会清除旧预览。恢复成功后仍须运行 `mm_complete` 重新验收。

UI 设置与 `mm_ui_toggle` 使用同一 Config/settings 入口。没有持久化 settings 的最小宿主会明确提示绑定仅当前进程有效，重启后需重新初始化或指定根目录。

2.1.1 的历史测试集共 **30 项**，包含 24 项适配器回归和 6 项需要隔离宿主依赖的集成/浏览器检查，最终全套 **30/30 通过、0 失败、0 跳过，31.6804 秒**。三项原有官方宿主检查覆盖服务挂载与 Python CLI、真实环境报告及检测不改写状态、Loader/Config/SettingsForms 持久化与重启恢复，以及实时预设投影、幂等初始化与旧项目迁移、30,000 中文字符要求、用户上下文注入和 20 MiB 原件逐字节/SHA 核对。预设回归使用真实 Loader、PresetRegistry 和 AgentLoop，复现缺少隔离声明的失败，再验证数学预设、多会话、改名与普通预设的能力隔离。

2.1.2 增加实际 Windows 受限令牌沙箱检查：使用 Python 3.13 复现旧临时目录拒绝访问，验证真实 NumPy/Matplotlib 导入、版本探测和清理。Windows CI 强制执行且拒绝跳过；上述 2.1.1 历史计数不包含这项新检查。具体平台与依赖条件见 [宿主兼容测试](../tests/dsh/README.md)。

Edge/React 测试覆盖六页交互、材料和配置，以及会话/恢复竞态；官方侧栏注册表、GuideBody 与真实插槽渲染器另验证入口顺序、session/key 契约、点击打开、不符合预设且未初始化时隐藏及插件卸载。浏览器 RPC 和外围会话/导航仍为 fixture，材料宿主测试的预设 inventory/settings/RPC 也为进程内 fixture；新增预设用例的 registry、AgentLoop 和 session 为真实实现，settings/RPC 传输为 fixture。**这些结果不表示整个桌面 GUI、真实模型对话和所有平台的端到端验收已完成**。完整源码仓库中的结果记录为 `project-review/logs/fix-2.1.1-dsh.log`，该审计日志不随功能安装包分发；测试命令和精确来源见 [宿主兼容测试](../tests/dsh/README.md)。
