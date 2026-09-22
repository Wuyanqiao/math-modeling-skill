# 线性资源分配基线

适用：连续非负决策，线性目标与约束，系数已明确。整数变量、非线性费用不能套此示例。

合同：max cᵀx，Ax≤b，x≥0；记录单位、可行域、求解状态、残差和容差。若不可行/无界，不把失败状态当数值解。

实现：`baselines.py::linear_resource_allocation`，依赖 NumPy/SciPy，使用 HiGHS。基准 `../../benchmarks/synthetic-v1.json` 的 optimization 有已知最优解，可用 `../../benchmarks/run_baselines.py` 验证。

复杂度与风险：实际规模依赖稀疏结构、病态程度与求解器；先跑小实例、保留求解状态，不承诺通用秒级。约束放宽、整数松弛、抽样均需显式记录。

扩展按需读 `../01-优化算法说明.md`；先保留精确基线，再验证启发式质量、运行预算与最优性差距。
