# DeepSeek Harness 集成审查

审查基线：`upstream/main`，提交 `3c4bd192`。审查日期：2026-09-22。仅新增审查材料，没有修改生产代码或安装插件。

结论：现有 DSH 集成已经包含工作流工具、状态落盘和进度 UI，但完成判定与根 Skill 的证据规则并未形成一致的可执行合同。作为自有项目升级基础，优先修复状态隔离、产物合同和真实校验接入，再扩展桌面交互。

## 运行结构与验证边界

- `dsh-plugin/math-modeling-agent/agent.cordis.yml` 挂载宿主工具及本地 `plugins/math-modeling.js`；后者注册十个 `mm_*` 工具、提示段、内置 Skill。
- 工作流采用三阶段、五门禁，写入项目 `.math-modeling/state.json`。UI 组合包由 `lib/index.js` 提供 RPC，`client/client.js` 每 10 秒读取并渲染状态。
- `scripts/sync_dsh_plugin.py` 镜像根 Skill、references、assets，但 tools 仅同步 SKILL.md，不同步工具执行脚本。
- 复现入口：`node project-review/probes/dsh-probes.mjs`。实际结果：`project-review/logs/dsh-probes.json`。Node `v24.11.1`；导入未修改的生产 JS，模拟 DSH 的 fs/shell/agents/settings，数据写入系统临时目录。复现清单使用仓库真实 Python CLI 生成。
- 未安装或启动真实 DSH Desktop，未验证其插件生命周期、沙箱授权及 RPC/UI 端到端行为。跨会话测试是“同一插件实例切换 currentInitiator.cwd”；`agent.cordis.yml` 开头说明预设按进程挂载一次，与该风险吻合，但实际版本仍需 E2E 确认。

## 优先修复的已复现问题

下表行号均对应审查基线。`engine` 指 `dsh-plugin/math-modeling-agent/plugins/math-modeling.js`。

| 优先级 | 问题与实际证据 | 源码位置 | 修复方向 |
|---|---|---|---|
| P1 | 官方复现清单被 DSH 误判：运行真实 `repro_manifest.py`，生成 `input_files[0].sha256`；DSH 返回“缺少字段: 输入 SHA-256”。反而把顶层 `hash` 设为 null 能通过。 | `references/roles/编程手/scripts/repro_manifest.py:51`；engine:517、520 | 统一 JSON Schema，读取真实嵌套字段并验证输入哈希、版本、命令和值；用生成器输出做集成测试。 |
| P1 | W2 可直接记录 PASS：前四门禁仍 pending，回执含未解决 P0，`mode=record` 仍返回 pass。只检查字段存在/数组和 evidence 非空，没有检查 reviewer 身份或派发记录。 | engine:365、409、420、432 | prepare 持久化审核任务，record 校验依赖、审核身份/只读来源、快照一致性与 P0/P1；不能把任意文本当独立验收证据。 |
| P1 | 可错误宣布完成：空 DOCX、空 PNG、空代码、空结果表，以及全 null 的形式清单，记录五个自填 PASS 后，`mm_complete.done=true`。检查未运行求解、OOXML、渲染、图片或真实环境校验。 | engine:495、502、514、528、547、555 | 产物检查调用统一验证器，记录命令/退出码/日志/输入输出哈希；完成状态由验证结果计算。 |
| P1 | 状态与当前项目脱节：显式设置自定义 projectRoot 初始化成功，下一次 `mm_state` 却显示未初始化；同实例从会话 A 切换到 B，仍返回 A 项目。 | engine:90、93、240、710、716 | 每次从调用上下文解析 sessionId→projectId，禁止全局缓存首个 cwd；显式 projectRoot 需要绑定到会话并贯穿所有工具。 |
| P1 | 门禁通过后修改模型，仍允许进入 programming；删除旧代码并新增代码后，完成判定 `drift=[]`、done=true。快照只比较旧快照中仍存在的文件，不覆盖新增、删除及递归目录。 | engine:306、348、568、574 | 递归内容哈希，比较完整文件集合；建模变更使相关及下游门禁失效，在阶段进入和门禁操作时即检查。 |
| P1 | 已完成后 Python 探测失败：本次 `mm_complete.done=false`，programming=blocked，但落盘 `completed=true` 未清除。 | engine:525、547、583 | 完成状态每次重新赋值；失败或变更时清除 completedAt，并提供失效原因。 |
| P1 | 独立复制 DSH 包后工具链不全：figure/export、docx/paper_format、latex/latex_paper、paper_search/hybrid_scholar 均在主仓库存在、在内置 SKILL_ROOT 缺失，而包内说明直接引用这些路径。 | `scripts/sync_dsh_plugin.py:13`、`:110`；`dsh-plugin/README.md:3`、`:123` | 提供真正包含运行时的发行包或版本绑定的依赖安装器，构建时审计所有引用。README 已承认“仅说明文档”，应明确知识库自包含不等于可运行工具链自包含。 |
| P2 | `mm_check_deliverables phase=paper` 在 currentPhase=modeling 时省略正式图基线，切换到 paper 后同一批文件变为 missing。 | engine:479、486、530 | 检查函数显式接收目标阶段；用论文实际引用的逻辑图计数。 |
| P2 | `optionalCollab='literature,prototype'` 两项仍为 false。缺花括号使 else 绑定到内层 if，公开 schema 定义的字符串输入不执行预期分支。 | engine:285、708 | 用明确分支统一解析字符串、数组/对象；将实际存储值回显并验证。 |
| P2 | UI 点击关闭后，再用 `mm_ui_toggle on` 返回 enabled=true，但 UI RPC 仍返回 enabled=false。两个入口分别依赖 DSH settings 和优先级更高的本地文件。 | engine:794；`plugins/dsh-math-modeling-ui/lib/index.js:85`、`:160` | 一个设置服务作为唯一真相，GUI 和模型工具调用同一接口。 |
| P2 | `mm_todo reset` 返回旧任务完成数 1，随后 list 才返回 0。 | engine:617、625、629 | reset 后从新数组计算并返回状态。 |

## 完成判定与 UI 的确切关系

`mm_complete` 不读取 Python `check_env.py` 报告，也不执行 figure/docx/latex 的确定性门禁。其唯一环境命令是 `python --version`：该命令非零会导致 programming=blocked、done=false；能打印版本不代表依赖或编译可用。

UI 没有另一个完成算法：host 在 `plugins/dsh-math-modeling-ui/lib/index.js:155` 直接投影 `data.completed`；client 在 `client/client.js:184` 根据该布尔值显示“项目已完成 / 所有门禁通过，交付物齐全”。所以 engine 没有撤销 completed 时，UI 会继续显示旧的成功结论。

## 仅静态确认或需宿主验证的事项

- **根 Skill 与插件的单阶段合同不同**：`SKILL.md:45` 允许仅执行对应阶段；engine:43 固定全门禁依赖链，engine:558、564 无条件检查五门禁与三阶段。建议增加任务 scope、requiredGates 和已有证据导入。
- **图合同不同**：`SKILL.md:82` 要求 SVG/PNG/灰度预览算同一逻辑图，engine:459 仅去扩展名，没有去灰度后缀；`SKILL.md:95` 要求至少八幅正式图，engine:480 却只数 result 文件；总体建模流程图也未纳入 engine 的检查。
- **UI 预设 id 不兼容安装示例**：README:42、82 建议安装为 `math-modeling` 且声称可改名；client:42 的 TARGET 固定为 `math-modeling-agent`，client:92 对其他 id 返回 null。应根据能力或配置识别预设，而非固定名称。
- **路径边界需加强**：初始化与 skillRead 有 contains 检查；但 engine:150 信任落盘的 `state.project.projectRoot`，engine:116、163 又以它决定写入目录和 workspace-write 参数。临时模拟中修改该字段可以使 mm_log 请求写入另一个目录。真实宿主能否阻止该请求未验证，不能据此宣称已突破 DSH 沙箱。应把解析出的授权项目根当权威值，并校验 realpath/符号链接边界。
- **持久化健壮性**：state 是 apply 闭包共享可变对象（engine:129），落盘是整份 writeText（engine:175），无修订号、串行写队列或原子替换。并发更新和异常中断的风险有代码依据，尚未模拟真实多会话并发。解析失败静默返回 freshState（engine:150）也可能掩盖损坏，需要 schema、迁移、备份与明确错误。

## 对自有项目的结构建议

保留根 Skill 作为多 Agent 的通用行为协议，把项目状态、任务范围、复现清单、门禁回执、产物元数据提取为同一套版本化 Schema 和宿主无关验证核心。DSH 只适配会话上下文、独立审核派发、运行命令、文件授权与 UI 数据；其他 Agent 可经 CLI 或 MCP 适配，避免在各适配层重复实现合同。

先建立核心合同与上述回归用例，再制作完整发行包、依赖诊断和版本矩阵；随后在 DSH UI 中显示真实阻塞项、回执详情、变更失效、运行日志和文件预览。真实 DSH E2E 验收应覆盖双会话、项目切换、重启续接、取消任务、失败重试、安装改名及受限权限。
