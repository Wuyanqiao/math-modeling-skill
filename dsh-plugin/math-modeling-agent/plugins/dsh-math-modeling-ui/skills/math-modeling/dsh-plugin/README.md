# DeepSeek Harness 数学建模工作台

本适配器把通用 Skill 接入 DeepSeek Harness。流程规则、产物验证、证据、审查回执和完成判定全部由共享 Python 运行时负责；DSH 插件提供宿主授权的 shell/文件调用、会话绑定、工具与状态看板。

本次升级在 `WuYanqiao/universal-upgrade` 分支，尚不能把仓库 `main` 当作已包含这些改动的版本。完整发行包由根目录构建器生成。当前只允许本地开发验证包；上游资料的再分发授权尚未齐备，npm 包设置 `private: true`、`license: UNLICENSED`，不表示本项目获得了这些资料的许可证。

## 已核验宿主

目标为官方 **DeepSeek Harness 0.1.7-alpha.1**，源码基准 [`c36a83ff6bb95e3f82cf79f9be7c724270a8aa61`](https://github.com/deepseek-ai/deepseek-harness/tree/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61)。实测为 Windows、Node 24.11.1、PowerShell、Python 3.13.13。安装依赖 Commander 15 要求 Node ≥22.12.0；本项目没有对该最低版本作实际回归。

该版本通过 profile 的 bundle 注册预设，不再扫描 `.agent-presets` 目录。`agent.cordis.yml` 和 `preset.yml` 保留为可读 composition 与兼容资源；实际入口是 `plugins/dsh-math-modeling-ui/cordis.patch.yml`，同时加入 UI 和 `@deepseek-ai/dsh-agent-preset`。安装后可改预设显示名，看板按当前项目判断是否显示。

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
$archivePath = Join-Path $packageOutput 'dsh-math-modeling-ui-2.0.0.tgz'
dsh plugin --profile web add $archivePath -w --ignore-scripts
dsh --profile web --dump-config
dsh --profile web
```

`.tgz` 安装已在官方 CLI 和全新临时 profile 上实际成功，配置输出包含 `dsh-math-modeling-ui`、`preset-math-modeling` 和 `dsh-math-modeling-ui/workbench`。本机 pnpm 10 对 Windows 跨盘目录参数生成了错误的 `link:` 路径，因此这里使用 tarball。默认 profile 禁止自动安装 peer 时会提示缺失 peer；宿主从其安装位置提供这些组件，仍应通过真实挂载检查确认可用。

确认验证结果后，再按你的桌面工作台配置选择实际 `DSH_HOME` 与 profile。不要猜测个人 AppData 路径，也不要复制或覆盖整个宿主配置。此实现保留宿主当前授权与沙箱策略；安装或运行失败时查看实际错误，不自动扩大权限。`dsh plugin --profile web --help` 会透传给 pnpm 并产生 profile 操作日志，查询启动器用法应使用 `dsh --help`。

## 会话内使用

选择“数学建模 Workbench”预设，在独立于 Skill 的项目目录创建会话。调用 `mm_project_init` 时选择 `scope=full|modeling|programming|paper`、`profile=balanced|short|competition`、论文格式及子问题；可显式指定 `projectRoot`。绑定由宿主 settings 持久化，每次操作重新定位当前会话。项目状态在 `<project>/.math-modeling/state.json`。

常用流程：

1. `mm_project_init` → `mm_doctor` → `mm_phase_enter`。
2. `mm_run` 执行真实命令，登记 inputs/code/outputs 与退出状态。
3. `mm_artifact_add`、`mm_claim_add` 连接产物、子问题与论证证据。
4. `mm_gate` 的 `prepare` 生成审核任务与快照；独立审核者读取证据后提交 `record` 回执。
5. `mm_check_deliverables` 排查阻塞，最后用 `mm_complete` 重新验证；判断完成必须查看 `done`，不能只看请求的 `ok`。

`reviewer_id`、`review_source` 是审计声明，不是宿主认证凭据。不能用一个不同的字符串证明独立审查。快照或产物变更会使相关审查失效。

其他工具包括 `mm_state`、`mm_skill_read`、`mm_todo`、`mm_log`、`mm_checkpoint`、`mm_artifact_read`、`mm_run_log_read`、`mm_ui_toggle`。恢复检查点先查看默认预览，再以预览返回的 revision 应用恢复。精确请求格式见 [运行时 API](../RUNTIME_API.md)。

## 看板与验证边界

打开 DSH 右侧栏的“开始”页。当前会话工作目录或显式绑定目录存在已初始化数学建模项目时，“工作区文件”“新建终端”下方会出现“数学建模 Workbench”。点击后在同一侧边栏标签内打开看板。刚初始化的项目会在下一次只读检测时出现；没有项目的会话不显示入口。入口使用官方 `sidebarRightTabs` 和 `sidebar.right.tab.guide.entry`，正文使用 `sidebar.right.pane.tab`，不再使用浮动 overlay。

看板分为“项目、证据、运行、快照”四页，使用 DeepSeek Harness 原生主题变量、字体、圆角按钮与分段标签，配合可折叠分区。图标按钮的名称与说明位于悬停提示，键盘焦点可见，标签支持方向键和 Home/End。界面不含 slogan；主内容与日志预览的滚动条默认透明，悬停或滚动时显示，滚动结束后自动隐藏。

开始页每 2 秒、看板每 5 秒只读检测状态；标签不可见时暂停，重新显示或窗口重新获得焦点时读取。后台检测不运行 shell；“重新验证”和产物/日志/恢复操作经宿主授权调用共享 CLI。每次操作使用该侧栏标签的 `sessionId`，同会话项目变化或关闭设置时清除旧预览。状态栏显示保存或核验时间，UI 不自行推断完成。二进制产物返回元数据，可使用宿主文件预览器查看。

“快照”页支持创建项目快照，并按名称、时间和创建时验收状态列出快照。选择“预览恢复”后，先查看新增、替换和删除的文件清单，再点击“确认恢复”，或选择“取消恢复”。预览后的文件变化会触发冲突并要求重新预览；切换会话会清除旧预览。恢复成功后仍须运行 `mm_complete` 重新验收。

UI 设置与 `mm_ui_toggle` 使用同一 Config/settings 入口。没有持久化 settings 的最小宿主会明确提示绑定仅当前进程有效，重启后需重新初始化或指定根目录。

本次已测试真实官方 Cordis/fs/pwsh/tools/session/skills 服务挂载与 Python CLI，真实 Loader/Config/SettingsForms 持久化和重启恢复，以及 Edge 中的 React 交互。另用官方侧栏注册表、GuideBody 与真实插槽渲染器验证了入口顺序、session/key 契约、点击打开、未初始化隐藏及插件卸载。浏览器 RPC 和外围会话/导航仍为 fixture；**未完成整个桌面 GUI、真实模型对话和所有平台的端到端测试**。测试命令和精确来源见 [宿主兼容测试](../tests/dsh/README.md)。
