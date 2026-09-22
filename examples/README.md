# 可运行的小型演示

这是确定性合成资源分配例子，最优值可通过顶点枚举独立确认。用于演练工作流，不代表真实赛题表现。

在仓库外创建空目录，运行：

```powershell
python examples/prepare_demo.py "<PROJECT_ROOT>"
python scripts/mathmodel.py gate-prepare --project-root "<PROJECT_ROOT>" --options '{"gate":"M1"}'
```

由真实独立审查者审核模型后记录回执。M1 通过后，用 `run` 执行最小求解：

```json
{
  "action": "run",
  "project_root": "<PROJECT_ROOT>",
  "argv": ["python", "solver.py"],
  "code": ["solver.py"],
  "inputs": ["data/case.json"],
  "outputs": ["results/solution.csv"],
  "seed": 42,
  "parameters": {"case": "synthetic-resource-v1", "random_sampling": false}
}
```

通过 `--options` 或 `--request-base64` 向 CLI 传入请求。输出应为 x=2、y=2、目标值10、约束违反量0。完成真实 P1 审核后，再带 `--figures` 执行，输出声明增加 `figures/result_q1_region.svg/.png` 和 `figures/result_q1_usage.svg/.png`；SVG与PNG是同一逻辑图。

登记产物的 question=q1、run_id，建立 claim-add，然后执行 P2、W1、论文生成和 W2。示例不自动填入任何 PASS，缺少真实审查时 complete 应保持未完成。

论文示例为两个页面的合成案例说明，选择 `paper_format=latex`。将 `build_demo_paper.py` 复制到项目，W1 审查通过后以 paper run 执行它，声明 `results/solution.csv` 为输入、`paper.tex` 为输出。登记生成的 TeX 入口后直接执行：

```json
{
  "action": "run",
  "project_root": "<PROJECT_ROOT>",
  "phase": "paper",
  "argv": ["xelatex", "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", "-jobname=完整论文", "paper.tex"],
  "code": ["paper.tex"],
  "inputs": ["figures/result_q1_region.png", "figures/result_q1_usage.png"],
  "outputs": ["完整论文.pdf"],
  "seed": 42
}
```

使用真实渲染器将 PDF 转成页面图，再进行 W2 独立视觉和数值审查。TeX/PDF 引擎是外部能力，需要通过 doctor 确认；无法运行时应保留阻塞状态，不能用无关 PDF 代替。

可把 `render_demo.py` 复制到项目，以 paper run 执行；`code=["render_demo.py"]`、`inputs=["完整论文.pdf"]`、`outputs=["render/page-1.png","render/page-2.png"]`。登记这两张页面图时设置 `role="render"`、`source_artifact_id` 为当前 PDF 的登记 ID。页面图服务于视觉审查，不计作论文逻辑图。
