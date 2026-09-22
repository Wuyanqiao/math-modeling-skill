# 通用 Skill 安装与环境

从 [2.1.4 Release](https://github.com/Wuyanqiao/math-modeling-skill/releases/tag/v2.1.4) 下载通用 ZIP，解压得到 `math-modeling/`。保留结构，按 Agent 的 Skill 安装方式加载 `SKILL.md`。仓库 `main` 也可直接作为通用 Skill；DSH 插件见 [DSH 安装](DSH安装.md)。

## Python 与依赖

使用 Python 3.11–3.13。状态、配置、清单和证据内核只使用标准库，执行 `python scripts/mathmodel.py --help` 可检查入口。

| 依赖组 | 用途 |
|---|---|
| `science` | NumPy、SciPy、pandas、NetworkX、scikit-learn |
| `figure` | matplotlib 与数据图 |
| `figure-styles` | SciencePlots、seaborn |
| `sensitivity` | SALib 全局敏感性分析 |
| `docx` | Word、公式及 XML 处理 |
| `pdf` | PDF 读取与渲染 |
| `xlsx` | Excel 读写 |
| `validation` | JSON Schema 校验 |

在 Skill 目录建立虚拟环境，Windows PowerShell 示例：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install ".[science,figure,docx,pdf,validation]"
```

Linux 或 macOS 使用 `source .venv/bin/activate` 激活环境。跨平台功能以本机检测为准，已执行的整体回归覆盖 Windows 与 Linux。

LaTeX、Pandoc、LibreOffice、drawio 导出程序和三维软件按任务单独准备。安装 Python 依赖不会自动安装这些程序；环境检测会报告实际解释器和缺失项，不会自动安装。

## 独立项目目录

安装目录与题目目录必须互不包含。以下 PowerShell 示例在 Skill 同级创建题目目录：

```powershell
$skillRoot = (Get-Location).Path
$projectRoot = Join-Path (Split-Path $skillRoot -Parent) 'my-modeling-project'
New-Item -ItemType Directory -Path $projectRoot -Force | Out-Null
$request = @{ action = 'init'; project_root = $projectRoot; scope = 'full'; profile = 'balanced'; paper_format = 'word' } | ConvertTo-Json -Compress
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($request))
python "$skillRoot/scripts/mathmodel.py" --request-base64 $encoded
python "$skillRoot/scripts/mathmodel.py" environment --project-root $projectRoot
```

上例是手动初始化方式。通过 Agent 使用时，先按 [交互配置](../references/交互配置.md) 沿用已有选择、询问未决项，再初始化或恢复；不要用示例默认值覆盖用户偏好。

环境检测区分基础必需、当前配置需要和可选依赖。用户可手动执行安装命令，或授权 Agent 在确认的环境中安装；安装后重新检测。完整接口见 [运行时 API](../RUNTIME_API.md)。只安装 Python 模块不能替代包含角色资料、算法、模板和工具的完整 Skill。
