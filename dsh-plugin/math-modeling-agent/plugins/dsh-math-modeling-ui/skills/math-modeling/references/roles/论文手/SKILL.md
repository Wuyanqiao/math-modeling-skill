---
name: 论文手
description: 基于模型和真实运行证据撰写所选格式的论文，检查主张、引用、图表与实际渲染。
---

# 论文手

`SKILL_ROOT = ROLE_ROOT/../../..` 只读，论文写 `PROJECT_ROOT`。读 `../../../references/共享运行时.md`，恢复范围、paper_format、profile 和规则来源。

## 开始

核对题目、模型合同、真实代码与结果、必要图表和引用。官方规则未知时明确标记；通用/课程任务不强求竞赛名称。缺关键证据回对应阶段，禁止编造数值与引用。

默认 Word；可选仅 Word、仅 LaTeX/PDF 或两者。无通用八图、15000 字或最低页数要求；官方与用户硬约束写入项目配置，其余只是建议。

## 顺序

1. `claim-add` 将核心主张关联公式、结果行列、图、运行输出或已核验原文位置，保存到项目内部元数据。
2. `gate-prepare` 执行 `W1` 准备，由独立 Subagent、外部 Agent 或人工审查证据大纲。严格模式通过后才按官方结构写完整正文，审查等级和限制如实记录。
3. 先确定共同正文、数据、公式和参考文献，再生成所选格式；同时生成两种格式时再检查 Word/LaTeX 一致性。
4. 用共享 `validate` 检查真实产物、运行关联、主张与硬约束。实际打开文档检查公式、图表、字体、分页、编号引用、参考文献和 Markdown 格式残留。
5. 高级 Word/LaTeX 工具见 `../../../tools/docx/SKILL.md` / `../../../tools/latex/SKILL.md`，先确认依赖与组件授权。旧工具的默认数量不覆盖项目 profile；显式传递当前规则，不按配额扩写。
6. 格式冻结后准备 `W2`，独立审查结论、数值、单位、原文支持、图表、附录、支撑材料完整性和实际渲染，`gate-record` 保存原回执；修改后重验。
7. `complete` 汇总质量和审查状态；未独立验收可受限交付，不能报告完整独立通过。

## 格式与范围

- Word：`完整论文.docx`，公式用可编辑 OMML。旧转换工具生成的清单与警告记录保留供审核。
- LaTeX：`完整论文-LaTeX/` 源码和实际编译的 `完整论文.pdf`。模板复制到项目，检查资源/编译哈希、引用、页数与字体；缺引擎明确阻塞 PDF。
- 共享运行时的 LaTeX 验证要求 `.tex` 入口已登记为 code/document，真实 paper run.code 包含该入口和必要依赖，直接执行 xelatex/pdflatex/lualatex/latexmk 并记录 PDF 输出。Python/shell 转发或复制脚本不自动视为真实 TeX 构建；旧高级工具可准备模板和检查，最终需保留直接编译记录。
- Word 有硬页数上限时，页数取自读取当前 DOCX 的真实渲染运行及其已登记 PDF 输出；不能用无关 PDF 或 LaTeX 版本页数替代 Word 页数。
- 正文只包含题目答案、模型、结果和学术证据；回执、内部 ID、日志、哈希和 checkpoint 放 `.math-modeling/`。

按需读 `references/工作流程.md`、`references/章节模板.md`、`references/写作规范.md`、`references/自审框架.md`；高级格式读 `references/论文格式规范.md` / `references/LaTeX格式规范.md`；英文读 `references/英文化工作流.md`；审查读 `../../../references/Subagent调度.md`。

真实竞赛读 `../../../references/交付与截止时间协议.md`，尽早走通导出链，用 `checkpoint-create` 保存版本。支撑包必须实际解压验证；未经用户或平台证据确认，不声称已经提交。
