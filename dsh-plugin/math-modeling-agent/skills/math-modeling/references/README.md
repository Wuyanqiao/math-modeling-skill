# 参考资料导航

本目录采用渐进式加载。先确定当前阶段，只读取对应角色入口；遇到具体任务再读取一份或少量参考文件。

## 根目录

- `SKILL_ROOT`：本仓库根目录，只读。
- `PROJECT_ROOT`：用户项目目录，所有产物写入这里。

相对链接以当前文档目录为基准；标注 SKILL_ROOT 的资源路径以仓库根目录为基准。执行命令使用绝对脚本路径，不依赖当前工作目录。共享运行时入口见 `共享运行时.md`。

## 三角色

| 阶段 | 入口 | 固定交付物 |
|---|---|---|
| 建模分析 | `roles/建模手/SKILL.md` | `题目分析报告.md`、`术语表格.md` |
| 代码实现 | `roles/编程手/SKILL.md` | Python/MATLAB 代码、结果表格、覆盖必要主张的候选图、按需总体建模流程图、复现清单 |
| 论文撰写 | `roles/论文手/SKILL.md` | 默认 Word；按用户选择交付 Word、LaTeX/PDF 或两者 |

## 按任务加载

| 任务 | 读取 |
|---|---|
| 选模型 | `roles/建模手/references/建模设计理论.md` |
| 查具体算法 | `算法索引.md`，先读匹配算法卡片，再按需读长文 |
| Python/MATLAB 实现 | `roles/编程手/references/工作流程.md` |
| MATLAB 工具箱与出图 | `roles/编程手/references/MATLAB规范.md` |
| 可视化 | `../tools/figure/SKILL.md` |
| 图型选择与科研绘图避坑 | `../tools/figure/references/chart-types/chart_selection.md` |
| Subagent 调度与阶段质检 | `Subagent调度.md` |
| 真实竞赛、截止时间与最终提交 | `交付与截止时间协议.md` |
| 论文结构 | `roles/论文手/references/章节模板.md` |
| Word 格式 | `roles/论文手/references/论文格式规范.md` |
| LaTeX 格式 | `roles/论文手/references/LaTeX格式规范.md` |

## 工具

| 工具 | 入口 |
|---|---|
| 科研可视化 | `../tools/figure/SKILL.md` |
| 双引擎论文搜索 | `../tools/paper_search/SKILL.md` |
| PDF | `../tools/pdf/SKILL.md` |
| Excel | `../tools/xlsx/SKILL.md` |
| DOCX | `../tools/docx/SKILL.md` |
| LaTeX | `../tools/latex/SKILL.md` |

外部论文只在确有需要时搜索和读取，并保留来源。
