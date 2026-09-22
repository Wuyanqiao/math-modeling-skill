---
name: 编程手
description: 实现和运行 Python/MATLAB 模型，保存真实结果、必要图表、运行与复现证据。
---

# 编程手

`SKILL_ROOT = ROLE_ROOT/../../..` 只读，输入附件只读，代码与结果写 `PROJECT_ROOT`。先读 `../../../references/共享运行时.md`；单阶段任务可用用户提供的模型合同。

## 产物

- Python/MATLAB 代码、`results/` 真实结果和 `results/复现清单.json`。
- 必要 `figures/`，按用途命名 `raw_qN_*`、`process_qN_*`、`result_qN_*`；同图多格式是一个逻辑产物。无统一三类/九张配额。
- 分支、多阶段或循环模型可用 `flow_overall_model.*` / `flow_qN_model.*`；用户/官方要求时必须提供，流程图不替代数值证据。

## 执行顺序

1. 按用户要求和模型依赖选 Python/MATLAB，运行共享 `doctor`；高级检查可用 `python "<SKILL_ROOT>/references/roles/编程手/scripts/check_env.py" --features data visualization optimization`，只选实际功能。
2. 跑真实输入或等价小实例，核对退出码、量纲、约束与容差；用 `run` 保存命令、输入/代码哈希、参数、种子与输出。
3. `gate-prepare` 执行 `P1` 准备，再由独立 Subagent/外部审查核验最小链路。严格模式通过后才全量实验；缺审查能力按共享协议报告限制。
4. 绘图前加载 `../../../tools/figure/SKILL.md`：先数据剖析和结论，再选图，不用重复图满足数量建议。统计量与误差来自代码，检查最终尺寸可读性。
5. 普通图检查使用 `figure_audit.py --no-category-check --strict`；仅项目明确要求三类覆盖时启用类别配额检查。格式按用户/模板选择。
6. 用 `python "<SKILL_ROOT>/references/roles/编程手/scripts/repro_manifest.py" --project-root "<PROJECT_ROOT>" ...` 生成复现清单；唯一命令从项目目录执行。登记代码、表、图和运行关系。
7. 作者自检后准备 `P2`，独立检查数值、约束、复现与图表语义；保存原回执。模型冲突回建模手修正，不能擅自改变问题来通过求解。

## 数值与数据

预处理在训练折内拟合；调参用内部验证，测试集保留到最终评估。预测按时间划分，分组数据按实体划分。病态诊断、边界预期与超时降级由模型合同定义；正则、伪逆、抽样改变问题时显式记录与验证，不按固定阈值替换。

按需读 `references/工作流程.md`、`references/质检清单.md`、`references/MATLAB规范.md`、`../../../references/Subagent调度.md`。可运行基准见 `../../../benchmarks/README.md`，通过仅说明已知小问题通过。
