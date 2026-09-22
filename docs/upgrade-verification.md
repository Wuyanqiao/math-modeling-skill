# 2.0.0 升级与验收记录

基于上游 `3c4bd1927663327812665941a445281b9c008a78`，在 `codex/universal-upgrade` 实施。原 fork 落后的 16 个提交已先完成快进同步。本文件记录本地开发版的实际验证；CI 配置、模拟测试、真实宿主挂载和桌面端到端测试分别计量。

## 实施对应关系

| 原路线图 | 当前实现 |
|---|---|
| A1 依赖与自动验证 | Python 分组依赖、3.11–3.13 范围、真实导入/执行器 doctor、Windows/Linux 与 Node 22/24 CI |
| A2 复现合同 | 实际执行器、环境探测、输入/代码/输出 SHA-256、参数和种子声明、真实退出码与日志；兼容原复现清单结构 |
| A3 门禁和交付 | 可执行 schema、各关卡证据快照、前置审查、独立身份声明、P0/P1 阻断、来源与格式校验、变化撤销完成状态 |
| A4 状态与并发 | 会话绑定、明确项目根、原子状态、同项目运行串行、失败持久化、输出发布回滚、旧状态备份迁移 |
| A5 完整分发 | 同源构建通用 Skill、旧预设布局、现代 DSH bundle；清单哈希、资源引用审计、中文空格路径脱离源码烟雾测试 |
| B 共享内核 | 标准库 Python CLI、五个 schema、三个 profile；单阶段/完整流程、Word/LaTeX/双格式；DSH 委托同一 CLI |
| C DSH 增强 | 现代 preset 注册、共享设置、双会话绑定；右侧栏原生入口、项目识别与四页看板、运行日志与证据、产物预览、快照与恢复 |
| D 科学质量 | 四张算法卡片和渐进索引、CV 内预处理与训练内调参、三个确定性数值基准、文献服务状态与支持等级拆分 |

恢复预览同时绑定修订号和文件清单；预览后外部改动也须重新预览。快照不可覆盖，恢复前创建回退副本。论文生成使用自己的执行阶段，不会因新增论文源文件或渲染页而误撤销已经完成的编程审查。

## 本机验收环境和证据

Windows 11、CPython 3.13.13、Node 24.11.1；外部 XeLaTeX 和 Poppler 可用。测试依赖安装在审查用虚拟环境，开发包没有安装进用户现有 Agent skills 目录。

数值基准实际通过 3/3：优化结果 `(2,2)`、目标值10；预测为23/25/27/29；TOPSIS 为0/0.5/1。报告同时记录数值容差、固定输入、结果/代码哈希、环境、各案例耗时与观测预算。本轮总测量约0.12秒，属于小型合成基线，不能推断复杂赛题表现。原始记录：`project-review/logs/upgraded-baselines.json`。

完整合成案例位于仓库相邻的 `mathmodel-upgrade-demo`，从 [示例脚本](../examples/README.md) 创建。模型具有独立解析证明：`3x+2y=2(x+y)+x≤10`，仅 `(2,2)` 达界。每个审查关卡由实际独立 Subagent 阅读文件并复核，回执保存于 `project-review/logs/demo-*-receipt.json`；单元测试中的合成回执与该案例审查分开。

阶段验收会检查真实求解、两张逻辑图、数值主张、直接 TeX 构建、渲染页和最终完成状态。旧探针与初次失败日志作为历史问题证据保留，不作为当前通过证明。

最终本机结果：

| 检查 | 实际结果 | 证据记录 |
|---|---|---|
| Python 全集 | 206/206 通过，38.16秒；含22个边界用例与真实 XeLaTeX | `upgrade-final-regression.log` |
| DOCX 工具自检 | 通过，原生文档与公式验证成功 | `upgraded-docx-self-check.log` |
| DSH Node 全集 | 22/22 通过，无跳过，14.69秒；含本轮侧栏新增检查 | `upgrade-sidebar-dsh.log` |
| 官方宿主集成 | 真正 fs/shell/tools/session/skills 挂载、双会话隔离、Config/SettingsForms 持久化、完整 Context 重启续接通过 | Node 全集的2项官方宿主测试 |
| 浏览器交互 | Edge/React 侧栏入口、四页、预览、快照取消/确认/冲突重试、键盘、设置、同会话项目变化与迟到响应、原生主题、窄屏和滚动条显隐通过；RPC 为模拟 | `browser.test.mjs`，`sidebar-{guide,panel-light,light,dark,narrow}.png` |
| 官方侧栏契约 | 实际 SidebarRightTabRegistry、SlotCore/SlotRegistry、GuideBody 和 renderer，入口顺序10/20/30、key/session、点击打开、未初始化隐藏和卸载通过 | `sidebar-host.test.mjs`，外围 frame/session/navigation/RPC 是 fixture |
| 官方 CLI 安装 | `.tgz` 在独立临时 profile 安装成功，预设/UI/workbench 注入 | `dsh-installed-profile.yml`，`dsh-install-validation.json` |
| wheel 独立安装 | 2.0.0，标准库环境，3种 profile 各 init/state/complete；8个资源全加载，非法状态拒绝 | `upgrade-final-wheel-summary.json` |
| 完整合成案例 | 5个真实独立审核均 PASS；`done=true`、三个阶段均ok、无阻塞 | `demo-final-completion.json` |
| 独立复现 | 求解CSV与图PNG字节一致；外部重编译与渲染的两页PNG字节一致 | `demo-P2-independent-check.json`、`demo-W2-independent-check.json` |
| 完成失效与恢复 | 把目标值10改成11后，P1/P2/W1/W2及完成状态失效；预览准确列出改动，恢复后哈希一致且重新完成 | `demo-recovery.json` |
| 语法与入口 | Python compileall、根Skill frontmatter校验通过 | 可按检查命令重放 |
| 最终分发 | 通用Skill和DSH组合包构建成功；两个源码镜像零漂移，48处受审计资源链接全部有效；三个独立副本均通过中文空格路径 smoke | `upgrade-final-sync.log`、`upgrade-final-distribution.log` |
| GitHub 跨平台 CI | 提交 `64fd4c9` 的 Windows/Linux × Python3.11/3.13 四个作业和 Node24 作业全部通过；矩阵主作业使用 Node22 | [实际工作流运行](https://github.com/Wuyanqiao/math-modeling-skill/actions/runs/35700674713) |

以上日志均位于源码审查目录 `project-review/logs/`，不打入功能安装包。案例为一次完整交付、一次修改拒绝、一次恢复成功；这是可核验的小样本结果，不是整体成功率承诺。新实现不依靠自动填入 PASS，独立审查者实际重新求解、编译并查看了全部页面。

## 可重放检查

```powershell
python -m unittest discover -s tests -v
python tools/docx/scripts/self_check.py
python -m compileall -q mathmodel_runtime scripts tools references/roles/编程手/scripts
python benchmarks/run_baselines.py --output baseline-report.json
node --test tests/dsh/*.test.mjs
python scripts/sync_dsh_plugin.py --check
python scripts/build_distribution.py --mode local-development --output dist
python -m build --wheel --outdir dist/runtime
```

真实 DSH 组件测试通过 `DSH_TEST_NODE_MODULES` 指向隔离安装的官方宿主依赖后执行，具体命令见 [DSH 说明](../dsh-plugin/README.md)。默认测试环境缺宿主依赖时应显式跳过，不能算作真实宿主测试通过。

## 适用范围和外部条件

- 本机验证与远程矩阵分别保留证据；未列出的系统、Python/Node 版本不在本轮实测范围。远端默认显式跳过4个需要隔离官方宿主/浏览器依赖的Node用例；本机22项Node验收包含这些用例且无跳过。无TeX引擎的环境明确跳过真实TeX烟雾测试，本机已实际执行。
- 声明审核身份是可审计字段；只有宿主提供独立认证时才具备宿主认证身份等级。运行时不会仅凭填写一个 reviewer 字符串保证现实独立性。
- 声明文件的隔离执行目录不是操作系统沙箱，DSH 适配器继承宿主文件和执行权限。
- 上游根源码授权仍待明确，部分继承工具包含限制条款。已实现组件来源清单和 release 阻断，本地包标为 LOCAL-DEVELOPMENT。技术验证完成不意味着已获得重新分发许可。
- Word 的 ZIP/XML 检查不能证明分页；有硬页数要求时必须绑定真实 DOCX 渲染产物。LaTeX 必须登记入口并保留直接 TeX 执行来源。
- 文献元数据匹配不等于原文支持结论。服务异常、成功零结果和部分成功均有不同状态。
