# DSH 工作台与适配器回归

2.1.3 本机完整回归 **33/33 通过，0 失败、0 跳过，35.7011 秒**，包括新增的初始化失败重试与真实 Windows 沙箱工作区准备检查；记录为 `project-review/logs/fix-2.1.3-dsh.log`。Windows 权限工具另有 12 项专项全部通过，记录为 `project-review/logs/fix-2.1.3-workspace-permissions.log`。

2.1.2 的历史回归在本机 Windows / Python 3.13.13 / Node 24.11.1 完整运行 **31/31 通过，0 失败、0 跳过，37.3497 秒**，包含真实预设挂载与环境检测沙箱专项。记录为 `project-review/logs/fix-2.1.2-dsh.log`；此计数不包含 2.1.3 新增的权限错误与工作区初始化用例。

以下命令从完整源码仓库执行。功能安装包保留本说明作为验收依据，运行测试还需检出该版本源码及测试文件。

普通适配器回归不安装 Node 依赖，真实 CLI 用 PATH 中的 Python：

```powershell
node --test tests/dsh/adapter.test.mjs
```

可选宿主集成与浏览器测试使用独立临时 npm 项目。安装 `@deepseek-ai/dsh@0.1.7-alpha.1`、`@deepseek-ai/cordis@4.0.3`、`@deepseek-ai/schemastery@3.18.3`、`react@18.2.0`、`react-dom@18.2.0`、`playwright`，把 `DSH_TEST_NODE_MODULES` 设置为该项目的绝对 `node_modules` 路径：

```powershell
$env:DSH_TEST_NODE_MODULES = 'C:\path\to\isolated\node_modules'
node --test tests/dsh/*.test.mjs
```

Windows 浏览器测试使用本机 Edge；其他平台需为隔离 Playwright 准备 Chromium。`DSH_UI_SCREENSHOT` 与 `DSH_CHECKPOINT_SCREENSHOT` 可分别指定概览及恢复预览截图绝对路径。2.1.1 的历史测试基线为 30 项，其中 6 项需要隔离宿主依赖；2.1.2 新增 Windows 受限沙箱检查。缺少 `DSH_TEST_NODE_MODULES` 或指定平台时，对应集成测试明确跳过，不被计为通过；实际通过和跳过数量以当前运行报告为准。

`environment-sandbox.test.mjs` 仅在 Windows 使用真实官方 `dsh-sandbox-local` 受限令牌与 `workspace-write` 授权执行。需要 PATH 中的 Python 3.13（或用 `PYTHON` 指定解释器）以及该解释器中的 NumPy、Matplotlib；使用上面的隔离 DSH 依赖目录，无需浏览器依赖：

```powershell
python -m pip install "numpy>=1.26,<3" "matplotlib>=3.8,<4"
node --test tests/dsh/environment-sandbox.test.mjs
```

`workspace-init-sandbox.test.mjs` 使用同一隔离宿主依赖与 PATH 中的 Python，在自有临时目录中设置权限夹具，调用实际工作区准备工具，再通过真实官方受限 PowerShell、文件系统和会话策略执行 `RuntimeBridge.ensureProject`。它覆盖准备前授权失败、准备后重试、两个全新一级兄弟目录和二次进入的项目身份稳定，且检查深层目录/文件 ACL 不被准备操作改写。该用例不执行模型调用或求解：

```powershell
node --test tests/dsh/workspace-init-sandbox.test.mjs
```

CI 的 `preset-host` 作业在 Ubuntu 和 Windows 执行真实预设注册回归，Windows 另准备 Python 3.13，分别执行环境检测与工作区初始化两个沙箱检查。每个步骤都验证实际执行数与零跳过；Linux 不调度 Windows 沙箱用例，避免把平台跳过计为通过。

`sidebar-host.test.mjs` 还会把官方注册器、插槽渲染器、GuideBody 和浏览器组件实际打包到隔离页面。官方发布包未携带全部构建依赖，需要在同一个临时 npm 项目补齐下列测试依赖；不需要把它们安装到用户 DSH profile：

```powershell
npm install --ignore-scripts @deepseek-ai/dsh-client-ui-dockkit@0.1.7-alpha.1 esbuild@0.28.2 zustand@5.0.15 immer@11.1.18 clsx@2.1.1 anser@2.3.5 diff@9.0.0 katex@0.18.7 shiki@4.3.1 @shikijs/langs@4.3.1 simple-icons@16.31.0 mdast-util-from-markdown@2.0.3 mdast-util-gfm@3.1.0 mdast-util-math@3.0.0 micromark-core-commonmark@2.0.3 micromark-extension-gfm@3.0.0 micromark-extension-math@3.1.0 micromark-factory-space@2.0.1 micromark-util-character@2.1.1 micromark-util-classify-character@2.0.1 micromark-util-sanitize-uri@2.0.1 micromark-util-symbol@2.0.1
```

`browser.test.mjs` 将开始页、浅色、深色、窄侧栏、配置和材料页截图保存为 `project-review/logs/sidebar-*.png`。

当前产品行为是：选择具备 workbench 能力的预设后，“开始”页显示入口；点击进入时 `mm.ensureProject` 才在当前会话工作区自动初始化，重复进入读取已有项目。开始页检测本身只读。已初始化项目也可显示入口；只有不符合预设且尚未初始化的会话才隐藏入口，不能把旧测试说明中的“未初始化隐藏”推广到所有会话。

看板提供“项目、材料、配置、证据、运行、快照”六页。材料支持原题、附件、论文模板和论文要求，单文件上限 20 MiB，按 1 MiB 分块走宿主文件授权；正文要求最多 30,000 字符，保留来源声明。配置提供五项绘图偏好（每项常驻用途小字及悬停说明）和七项默认关闭的额外协作。材料预览保留提取说明和截断提示，独立门禁质检始终保留。

| 层次 | 实际覆盖 | 不覆盖 |
|---|---|---|
| adapter.test.mjs | 编码与注入边界、长配置 stdin、拒绝/取消/截断、宿主 standing policy、多会话与自定义根、实时预设投影、幂等初始化、授权失败保留预设与重试、旧项目要求迁移与拒权、分块顺序/取消清理、设置、环境报告路由与超时、完整 Skill、真实 Python 运行→证据→P1 审查→失效、运行日志、文件恢复与预览版本冲突 | 宿主服务由模拟提供；科学结论仍由独立审核判断 |
| headless-host.test.mjs：服务挂载 | 官方 Cordis/fs/pwsh/subprocess/tools/session/AgentRegistry/skills 真实挂载、真实 Python、多会话与插件重挂载 | 无模型调用；此最小 host 无 settings，跨重挂载自定义根按提示显式提供 |
| headless-host.test.mjs：设置持久化 | 官方 boot/Loader/Config/config-editor/SettingsForms、实际 profile patch 写入、销毁整 Context 后恢复自定义绑定与开关、UI/工具同源 | RPC 传输为进程内 fixture；无桌面窗口 |
| headless-host.test.mjs：预设、配置与材料 | 官方 SessionProjection 响应预设选择事件、并发幂等初始化与旧项目迁移、真实 shell stdin 往返 30,000 中文字符、实际 system-prompt assembly 的用户上下文、20 MiB 原件逐字节/SHA 核对、成功与取消后暂存清理 | 预设 inventory、settings 和 RPC 传输为进程内 fixture；未调用真实模型或修改个人 profile |
| preset-host.test.mjs | 从源 YAML 读取 workbench 节点，通过真实 Loader/PresetRegistry/AgentLoop 复现无 isolate 时的 `agent-preset/invalid`；修复后创建同数学预设两会话、改名数学预设一会话、普通预设一会话，验证 session 发布、scoped tools、`serviceFor`、根服务不泄漏及 `mm.context` 入口识别 | 聚焦实际 workbench 节点，不挂载所有预设工具；settings/RPC 传输为 fixture，无模型请求或个人 profile 修改 |
| environment-sandbox.test.mjs | Windows 上通过官方受限令牌沙箱，在自有临时工作区与宿主私有 TEMP 中复现旧 `0700` 目录拒绝访问，验证修复后的真实 NumPy/Matplotlib 导入、Python 版本探测与临时文件清理 | 需要 Python 3.13 与实际依赖；官方 Windows 后端报告 `partial` 执行强度，仅临时文件失败分支使用故障注入；不替换沙箱实现、不放宽权限、不修改个人 profile；不覆盖桌面 GUI、Linux 沙箱或所有依赖的可用性 |
| workspace-init-sandbox.test.mjs | 在当前用户拥有但缺少 `WRITE_OWNER` 的临时目录中，复现真实宿主初始化拒绝；实际准备工具只读检查/显式备份应用、一级目录权限、旧项目重试、两个新建兄弟项目初始化及身份幂等；真实 fs-sandbox/pwsh-sandbox/sandboxPolicy/SessionProjection 与共享 CLI | 权限变更仅在测试创建的目录；预设 inventory/settings 为 fixture，执行观察委托真实沙箱；后端报告 `partial`，无模型提供者、求解、个人 profile 修改或完整桌面 GUI 验证 |
| browser.test.mjs | 真 Edge/React，会话所属侧栏入口/正文、预设选择后自动初始化、六页/键盘、悬停提示、绘图开关保存、框架图/机制图用途小字可见、材料选择与要求编辑、证据与日志、快照创建/预览/取消/确认、冲突和迟到响应、设置、主题、窄屏、实际滚动条显隐 | 侧栏注册和 RPC 为模拟；不是整个 DSH 桌面的 E2E |
| sidebar-host.test.mjs | 官方 SidebarRightTabRegistry、SlotRegistry/SlotCore、GuideBody 与真实 renderer，入口顺序 10/20/30、key=id、session props、点击替换标签、不符合预设且未初始化时隐藏而不回退默认按钮、卸载清理 | 外围 frame/session/navigation/RPC 与文件/终端定义为 fixture；没有整个桌面或模型调用 |

历史执行环境：Windows、Node 24.11.1、Python 3.13.13；官方 DSH 0.1.7-alpha.1。2.1.1 本机已配置隔离宿主依赖的最终回归结果为 **30/30 通过，0 失败，0 跳过**，耗时 31.6804 秒。完整源码仓库中的记录为 `project-review/logs/fix-2.1.1-dsh.log`，该审计日志不随功能安装包分发。这项结果包括上述 fixture 边界，不包含 2.1.2 新增沙箱用例，不表示完成整个桌面 GUI 或真实模型对话测试，也不证明所有平台均已通过。

安装测试另在全新临时 `DSH_HOME` 使用真实 `dsh plugin --profile web add <tgz> -w --ignore-scripts`，成功后 `--dump-config` 可见 UI、preset 和 workbench 三个入口。Windows 跨盘目录 `link:` 安装失败，因此安装文档采用 tgz。

精确官方源码基准：[`c36a83ff6bb95e3f82cf79f9be7c724270a8aa61`](https://github.com/deepseek-ai/deepseek-harness/tree/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61)。关键接口依据：

- [Shell 类型与执行约定](https://github.com/deepseek-ai/deepseek-harness/blob/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61/packages/shell/shell/src/types.ts)：`workdir`、`execute(spec).result()`、`stdout.text` 与截断标记。
- [官方 PowerShell 工具](https://github.com/deepseek-ai/deepseek-harness/blob/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61/packages/shell/tool-pwsh/src/index.ts)：保留会话 `sandboxPolicy.resolve` 与执行取消边界。
- [Settings 服务](https://github.com/deepseek-ai/deepseek-harness/blob/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61/packages/settings/settings/src/index.ts)：Config volatile 字段、`describe()` 和带 revision 的 `update()`。
- [预设注册规范](https://github.com/deepseek-ai/deepseek-harness/blob/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61/packages/preset/agent-preset-registry/README.md)：宿主 bundle 注册，旧 `.agent-presets` 扫描方式不适用。
- [预设服务隔离与读取](https://github.com/deepseek-ai/deepseek-harness/blob/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61/packages/preset/agent-preset-registry/src/mount.ts)：`mountPreset` 拒绝根域服务泄漏；`serviceForAgent` 按 agent 所属预设读取隔离服务。
- [官方标准预设](https://github.com/deepseek-ai/deepseek-harness/blob/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61/packages/bundle/web-app/presets/standard.patch.yml)：当前插件名称、spawn 子代理与 workflow-ptc。
- [官方侧栏服务与插槽](https://github.com/deepseek-ai/deepseek-harness/blob/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61/packages/client/ui-sidebar-right/src/client/index.ts)：`sidebarRightTabs` 和 keyed/session 插槽；key 是实现 id。
- [侧栏标签动作与属性](https://github.com/deepseek-ai/deepseek-harness/blob/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61/packages/client/ui-sidebar-right/src/client/contract/slots.ts)：`useTabInfo().tab.actions` 与 `replaceTab`，所有打开操作绑定标签所属会话。

测试的临时目录清理均先检查固定前缀与父目录。生产适配器只通过宿主 fs/shell 操作项目；测试中的 Node 文件与子进程 API 仅用于隔离 fixture。
