# DSH 适配器回归

以下命令从完整源码仓库执行。功能安装包保留本说明作为验收依据，运行测试还需检出该版本源码及测试文件。

普通回归不安装 Node 依赖，真实 CLI 用 PATH 中的 Python：

```powershell
node --test tests/dsh/adapter.test.mjs
```

可选宿主集成与浏览器测试使用独立临时 npm 项目。安装 `@deepseek-ai/dsh@0.1.7-alpha.1`、`@deepseek-ai/cordis@4.0.3`、`@deepseek-ai/schemastery`、`react@18.2.0`、`react-dom@18.2.0`、`playwright`，把 `DSH_TEST_NODE_MODULES` 设置为该项目的绝对 `node_modules` 路径：

```powershell
$env:DSH_TEST_NODE_MODULES = 'C:\path\to\isolated\node_modules'
node --test tests/dsh/*.test.mjs
```

Windows 浏览器测试使用本机 Edge；其他平台需为隔离 Playwright 准备 Chromium。`DSH_UI_SCREENSHOT` 与 `DSH_CHECKPOINT_SCREENSHOT` 可分别指定概览及恢复预览截图绝对路径。没有 `DSH_TEST_NODE_MODULES` 时，宿主和浏览器测试明确跳过，不被计为通过。

`sidebar-host.test.mjs` 还会把官方注册器、插槽渲染器、GuideBody 和浏览器组件实际打包到隔离页面。官方发布包未携带全部构建依赖，需要在同一个临时 npm 项目补齐下列测试依赖；不需要把它们安装到用户 DSH profile：

```powershell
npm install --ignore-scripts @deepseek-ai/dsh-client-ui-dockkit@0.1.7-alpha.1 esbuild@0.28.2 zustand@5.0.15 immer@11.1.18 clsx@2.1.1 anser@2.3.5 diff@9.0.0 katex@0.18.7 shiki@4.3.1 @shikijs/langs@4.3.1 simple-icons@16.31.0 mdast-util-from-markdown@2.0.3 mdast-util-gfm@3.1.0 mdast-util-math@3.0.0 micromark-core-commonmark@2.0.3 micromark-extension-gfm@3.0.0 micromark-extension-math@3.1.0 micromark-factory-space@2.0.1 micromark-util-character@2.1.1 micromark-util-classify-character@2.0.1 micromark-util-sanitize-uri@2.0.1 micromark-util-symbol@2.0.1
```

`browser.test.mjs` 将开始页、浅色、深色和窄侧栏截图保存为 `project-review/logs/sidebar-*.png`。

| 层次 | 实际覆盖 | 不覆盖 |
|---|---|---|
| adapter.test.mjs | 编码与注入边界、拒绝/取消/截断、宿主 standing policy、两个会话、自定义根、预设改名、设置、完整 Skill、真实 Python 运行→证据→P1 审查→失效、实际运行日志、UI 快照路由、真实文件恢复与预览版本冲突 | 宿主服务由模拟提供 |
| headless-host.test.mjs 第一项 | 官方 Cordis/fs/pwsh/subprocess/tools/session/AgentRegistry/skills 真实挂载、真实 Python、多会话与插件重挂载 | 无模型调用；此最小 host 无 settings，跨重挂载自定义根按提示显式提供 |
| headless-host.test.mjs 第二项 | 官方 boot/Loader/Config/config-editor/SettingsForms、实际 profile patch 写入、销毁整 Context 后恢复自定义绑定与开关、UI/工具同源 | RPC 传输为进程内 fixture；无桌面窗口 |
| browser.test.mjs | 真 Edge/React，会话所属侧栏入口/正文、初始化识别、四页/键盘、悬停提示、证据与日志、快照创建/预览/取消/确认、冲突和迟到响应、设置、主题、窄屏、实际滚动条显隐 | 侧栏注册和 RPC 为模拟；不是整个 DSH 桌面的 E2E |
| sidebar-host.test.mjs | 官方 SidebarRightTabRegistry、SlotRegistry/SlotCore、GuideBody 与真实 renderer，入口顺序10/20/30、key=id、session props、点击替换标签、未初始化隐藏而不回退默认按钮、卸载清理 | 外围 frame/session/navigation/RPC 与文件/终端定义为 fixture；没有整个桌面或模型调用 |

本次执行环境：Windows、Node 24.11.1、Python 3.13.13；官方 DSH 0.1.7-alpha.1。安装测试另在全新临时 `DSH_HOME` 使用真实 `dsh plugin --profile web add <tgz> -w --ignore-scripts`，成功后 `--dump-config` 可见 UI、preset 和 workbench 三个入口。Windows 跨盘目录 `link:` 安装失败，因此安装文档采用 tgz。

精确官方源码基准：[`c36a83ff6bb95e3f82cf79f9be7c724270a8aa61`](https://github.com/deepseek-ai/deepseek-harness/tree/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61)。关键接口依据：

- [Shell 类型与执行约定](https://github.com/deepseek-ai/deepseek-harness/blob/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61/packages/shell/shell/src/types.ts)：`workdir`、`execute(spec).result()`、`stdout.text` 与截断标记。
- [官方 PowerShell 工具](https://github.com/deepseek-ai/deepseek-harness/blob/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61/packages/shell/tool-pwsh/src/index.ts)：保留会话 `sandboxPolicy.resolve` 与执行取消边界。
- [Settings 服务](https://github.com/deepseek-ai/deepseek-harness/blob/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61/packages/settings/settings/src/index.ts)：Config volatile 字段、`describe()` 和带 revision 的 `update()`。
- [预设注册规范](https://github.com/deepseek-ai/deepseek-harness/blob/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61/packages/preset/agent-preset-registry/README.md)：宿主 bundle 注册，旧 `.agent-presets` 扫描方式不适用。
- [官方标准预设](https://github.com/deepseek-ai/deepseek-harness/blob/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61/packages/bundle/web-app/presets/standard.patch.yml)：当前插件名称、spawn 子代理与 workflow-ptc。
- [官方侧栏服务与插槽](https://github.com/deepseek-ai/deepseek-harness/blob/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61/packages/client/ui-sidebar-right/src/client/index.ts)：`sidebarRightTabs` 和 keyed/session 插槽；key 是实现 id。
- [侧栏标签动作与属性](https://github.com/deepseek-ai/deepseek-harness/blob/c36a83ff6bb95e3f82cf79f9be7c724270a8aa61/packages/client/ui-sidebar-right/src/client/contract/slots.ts)：`useTabInfo().tab.actions` 与 `replaceTab`，所有打开操作绑定标签所属会话。

测试的临时目录清理均先检查固定前缀与父目录。生产适配器只通过宿主 fs/shell 操作项目；测试中的 Node 文件与子进程 API 仅用于隔离 fixture。
