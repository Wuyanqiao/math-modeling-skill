# 项目审查、升级与验证证据

本目录保留升级前的原始审查及问题复现。用户采纳建议后，已在 `codex/universal-upgrade` 实施 2.0.0；当前实现与验证状态见 [升级验收记录](../docs/upgrade-verification.md)，开发入口见 [项目 README](../README.md)。旧报告中的“尚未实现”和初次失败日志描述审查时的基线，不代表当前分支状态。

审查日期：2026-09-22。目标：**通用 Skill 优先，兼容多种 Agent，对 DeepSeek Harness 桌面工作台做专门增强。**

- [实现与运行分析](PROJECT_ASSESSMENT.zh-CN.md)：架构、实际运行方式、检查结果和改进依据。
- [升级路线图](UPGRADE_ROADMAP.zh-CN.md)：目标架构、实施顺序和每一阶段的验收标准。
- [DSH 专项审查](DSH_AUDIT.md)：适配层缺陷、源码位置和隔离复现结果。
- [基线记录](baseline.json)：仓库同步、提交、环境和验证边界。
- [运行日志](logs/) 与 [DSH 复现脚本](probes/dsh-probes.mjs)：可复核证据。

你的 GitHub fork `Wuyanqiao/math-modeling-skill` 的 `main` 已按要求快进上游 16 个提交。同步后 GitHub 比较结果为 `identical`，领先/落后均为 0；本地 `main` 也已同步。审查提交：`3c4bd1927663327812665941a445281b9c008a78`。

初次审查分支为 `codex/project-assessment`，当时源代码保持上游原样；实施分支为 `codex/universal-upgrade`。隔离 Python 环境位于 `.venv/`，通过本目录 `.gitignore` 排除。当前通过证据使用 `upgrade-final-*`、`upgraded-*` 与最终 `demo-*` 日志；DSH 旧探针只是历史缺陷复现，不是新版测试套件。

## 复核本次检查

以下 PowerShell 命令从仓库根目录运行。`.venv` 使用 `--system-site-packages` 继承了本机已有依赖，只额外安装 `defusedxml==0.7.1`；这是本机复测环境，不能作为全新机器安装验证。

```powershell
$env:PYTHONUTF8 = '1'
$reviewPython = (Resolve-Path 'project-review/.venv/Scripts/python.exe').Path

# 测试临时目录须位于 Skill 仓库外，并规范成长路径，避免 Windows 8.3 路径比较失败。
$reviewTempRoot = & $reviewPython -c 'from pathlib import Path; import tempfile; print(Path(tempfile.gettempdir()).resolve())'
$env:TEMP = $reviewTempRoot
$env:TMP = $reviewTempRoot

& $reviewPython -m unittest discover -s tests -v
& $reviewPython tools/docx/scripts/self_check.py
& $reviewPython -m compileall -q tools 'references/roles/编程手/scripts'
& $reviewPython scripts/sync_dsh_plugin.py
& $reviewPython 'references/roles/编程手/scripts/check_env.py' --features data visualization optimization
& $reviewPython tools/latex/scripts/latex_paper.py doctor --engine xelatex --need-pandoc

node --check dsh-plugin/math-modeling-agent/plugins/math-modeling.js
node --check dsh-plugin/math-modeling-agent/plugins/dsh-math-modeling-ui/lib/index.js
node --check dsh-plugin/math-modeling-agent/plugins/dsh-math-modeling-ui/client/client.js
node project-review/probes/dsh-probes.mjs
```

复现脚本使用临时项目和模拟宿主，输出 `logs/dsh-probes.json`；`observedDefect: true` 表示观察到了现有问题，**不是通过了质量测试**。本次没有实际挂载 DSH 桌面预设，也没有求解完整赛题或生成完整论文。

`logs/unittest-temp-inside-skill.log` 保留了一次审查过程中的错误配置：临时目录被放入 Skill 根目录内，触发了源码的写入保护。它不属于上游缺陷，最终结果以 `logs/unittest-isolated.log` 为准。
