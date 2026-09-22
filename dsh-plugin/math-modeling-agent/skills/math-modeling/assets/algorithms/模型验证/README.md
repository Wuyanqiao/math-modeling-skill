# 模型验证

在模型选择时确定验证合同，在实际求解后执行相应检查，写作时让每个主张对应检查证据。此目录是与优化、预测等类别并列的按需模块；它提供检查方法和可执行小例，不产生通用“质量分数”，也不替代 M1/P2/W1 的独立科学审查。

每道子问题最多两个独立模型体系。同一模型族的重采样、不同参数、近似精度或求解器验证不另计体系；如果另建独立机制的对照模型，应计入两个体系名额。

| 要回答的问题 | 先加载 | 输出证据 |
|---|---|---|
| 能推广到新数据吗 | 泛化检查 + `validation.py` 的划分/折内评价 | 划分索引、样本单位、真正未见数据误差 |
| 参数变化会推翻结论吗 | 敏感性检查 + `sensitivity.py` | 参数范围、采样设计、局部导数/Morris/Sobol 及稳定性 |
| 结果区间代表什么 | 不确定性检查 | 估计目标、区间类型、概率水平、重采样/后验假设 |
| 程序支持论文中的表述吗 | 求解证据与机理检查 | 求解器证书、真实约束残差、单位/初边值/收敛检查 |

## 1. 泛化：划分必须对应将来的使用方式

先定义独立观察单位与预测场景：新样本、新被试、新地区、未来时间，还是已知对象的新观测。训练集用于拟合，验证集或内层 CV 用于选择模型/阈值，最终测试集仅用于完成选择后的评价。测试集看过再改模型后不再是未见测试证据。

- 独立同分布样本可采用随机划分/K-fold；分类任务按目标分布需要选择分层划分，不能机械保证每折都含罕见类别。
- 同一病人、设备、城市或实验批次重复观测，用 GroupKFold/组划分以避免对象泄漏；“留对象外”评价与“同对象内预测”回答不同问题。
- 时间序列按时间滚动/扩展窗口回测，训练早于验证；预测跨度、标签窗口或滞后特征会跨界时设置 gap/purge。gap 的行数不等于时长，时间间隔不规则时应按实际时间定义切分。
- 同时有组和时间依赖时设计符合两者的专用切分，不能仅选其中一个声称都已消除。
- 预处理、特征筛选、插补与调参均放入每折训练内部的 Pipeline。最终测试集禁止参与 `fit`，包括不使用标签的全体标准化。

这些切分的用途与 Pipeline 的折内处理见 [scikit-learn 交叉验证文档](https://scikit-learn.org/stable/modules/cross_validation.html)；常见的数据泄漏和预处理误用见[官方陷阱说明](https://scikit-learn.org/stable/common_pitfalls.html)。

[validation.py](validation.py) 的 `three_way_split` 提供 60/20/20 随机、分组、顺序示例；比例是演示值，不是任务硬规则。分组比例按组数，必须另报实际样本数。`cv_splits` 仅传入开发集的局部索引范围；`evaluate_regression_folds` 克隆完整 Pipeline 后逐折拟合，输出实际 MAE/RMSE 与索引。它不自动做嵌套调参，也不把跨折标准差称为置信区间。分类/生存等任务需替换相应损失与评价设计。

## 2. 敏感性：先定义输出与参数分布

选择与结论有关的输出：成本、排序、阈值越界、预测误差等；说明参数基准、范围、单位、相关性和失败区域。参数变化引起的排名翻转或约束失效，比只画平滑曲线更能说明结论边界。

| 方法 | 计算与解读 | 主要限制 |
|---|---|---|
| 局部中心差分 | $\partial f/\partial x_i\approx[f(x+h_ie_i)-f(x-h_ie_i)]/(2h_i)$；可报告弹性 $(x_i/f)\partial f/\partial x_i$ | 仅反映当前点附近；需缩小/放大步长比较，避免舍入和截断误差；不能越过合法参数边界。$f=0$ 时弹性未定义 |
| Morris 筛选 | 多条网格轨迹的 elementary effects；$\mu^*$ 排影响强弱，$\sigma$ 反映非线性或交互 | 不能仅凭大 $\sigma$ 区分非线性与交互；范围和网格会改变尺度，筛选结果不是方差百分比 |
| Sobol 全局分析 | 一阶 $S_i=\mathrm{Var}(\mathbb E[Y\mid X_i])/\mathrm{Var}(Y)$；总效应 $S_{Ti}$ 含该变量交互 | 标准分解假定独立输入；相关参数不能独立乱采样。零输出方差时指数未定义，有限样本可能出现小负估计或超过 1 |

[sensitivity.py](sensitivity.py) 对 SALib 进行薄封装，未安装时明确报依赖缺失；不会用局部差分冒充 Morris/Sobol。当前全局示例只支持给定区间内相互独立的均匀输入。Morris 保留采样轨迹顺序；Sobol 用 scrambled Sobol 设计、二次幂基数，`calc_second_order=False`，只计算一阶与总效应。实际模型失败的采样点不能删掉后照旧分析，需先解决定义域或重新设计采样。[SALib 基础流程](https://salib.readthedocs.io/en/latest/user_guide/basics.html)、[官方采样 API](https://salib.readthedocs.io/en/latest/api/SALib.sample.html)

示例 $Y=X_1+2X_2$、独立 $U(0,1)$ 的局部梯度为 $(1,2)$，Morris 的 $\mu^*=(1,2),\sigma=0$，Sobol 一阶和总效应为 $(0.2,0.8)$。另测 $Y=X_1X_2$、独立 $U(-1,1)$：一阶效应为 0，总效应均为 1，用于验证纯交互不会被误判为“两个参数都无影响”。置信区间和不同采样预算/种子的稳定性另作数值证据，不能把单次估计当精确真值。

## 3. 不确定性：参数、统计量、未来观测必须分开

| 区间对象 | 含义 | 示例与限制 |
|---|---|---|
| 统计量的 Bootstrap CI | 对样本重抽并重新计算统计量，近似抽样不确定性 | `bootstrap_mean_interval` 只实现 IID 单位的均值百分位区间；不是未来单次观测区间 |
| 参数后验可信区间 | 给定似然、先验与数据后的参数概率范围 | 依赖先验与模型；不能称为重复抽样频率保证 |
| 后验预测区间 | 对参数后验积分并包括新观测噪声 | 通常比参数区间宽；预测一个新对象与多个未来值的同时覆盖不同 |

Bootstrap 的重抽单位必须匹配数据依赖：按个体整组重抽或时间块重抽，而不是随机打散重复观测。配对差异要按配对单位重抽；数据预处理/模型拟合如果属于目标估计流程，应在重抽中重新执行，不能只重抽已经过拟合的残差。极少样本、强偏倚、非平滑统计量或边界参数需额外论证，BCa 也可能退化。具体区间方法、配对/向量化与退化警告见 [SciPy bootstrap 文档](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html)。

`normal_uncertainty` 复用 [反问题模块](../inverse-inference.md) 的解析正态后验，分别返回参数与单个未来观测区间。观测 $(1,2,3)$，先验 $N(0,1)$、已知观测方差 1 时，后验均值 1.5、方差 0.25，而新观测预测方差 1.25。正式 MCMC 仍需多链、rank-Rhat、ESS、Monte Carlo 误差和后验预测检查；这套解析包装不证明任意复杂后验收敛。[Stan 后验预测检查](https://mc-stan.org/docs/stan-users-guide/posterior-predictive-checks.html)

## 4. 求解状态、残差与论文表述

`run.status` / `exit_code` 是进程运行状态，不能当作求解器状态。脚本正常结束仍可能只找到可行解、达到时间限制、遇到不可行或产生非有限数值；`parameters` 只记录输入参数，不构成状态证明。

CP-SAT 的 `FEASIBLE` 表示找到可行候选，不能写成已证明最优；`OPTIMAL` 也需核对实际 gap 设置与模型语义。`UNKNOWN` 不可凭空填目标值 0。时间限制若保留了 incumbent，应同时记录“有可行候选”及 termination_reason；没有 incumbent 时目标值保持 null。不可行与无界也是不同结论。[OR-Tools 官方 CP-SAT 状态说明](https://developers.google.com/optimization/cp/cp_solver)

| 当前证据 | 可以支持的表述 |
|---|---|
| FEASIBLE + 全部约束通过 | 找到一个可行方案，报告其真实目标值；最小化时是可行上界，最大化时是可行下界 |
| OPTIMAL + 全局适用求解方法 + 有效界/gap | 在所声明的求解容差内证明最优；仍需检查数学模型是否对应题目 |
| 局部优化成功/驻点 | 报告局部候选或局部最优依据；不能从 `success=True` 推出全局最优 |
| UNKNOWN / 无 incumbent / 非有限输出 | 报告未获得相应结论与终止原因，不能替换成零值结果 |

最小化的有效界满足 $L\le z_{\mathrm{inc}}$，绝对 gap 为 $z_{\mathrm{inc}}-L$；最大化满足 $U\ge z_{\mathrm{inc}}$，绝对 gap 为 $U-z_{\mathrm{inc}}$。相对 gap 的分母和近零目标处理依求解器定义，不能混用。此模块证书校验只使用带单位的绝对 gap 容差；若求解器使用相对容差，作者须记录原设置与换算依据。gap 容差不能用来放过方向错误的界；当前检查严格拒绝负 gap，若原始输出存在舍入冲突需回到求解精度和界的来源核验。FEASIBLE 即使碰巧数值 gap 为零也不自动改写 raw_status。

### 真实证书与共享运行时

实际求解脚本输出 `results/solver-certificate.json`，至少保存：

```json
{
  "solver": "实际求解器或接口名",
  "solver_version": "实际版本",
  "raw_status": "求解器原始状态",
  "status": "FEASIBLE",
  "termination_reason": "实际终止原因，例如达到时间限制且保留 incumbent",
  "sense": "min",
  "objective": 123.0,
  "best_bound": 120.0,
  "optimality_scope": "global",
  "gap_tolerance": 0.01,
  "residuals": {"容量超限": 0.0},
  "tolerances": {"容量超限": 0.000001}
}
```

上面只是字段模板，数值是占位说明，不能直接用于项目证据。残差定义：$g(x)\le0$ 用 $\max(g(x),0)$，等式用绝对残差，整数约束还需检查与最近整数的距离。逐项说明量纲/缩放与对应容差，不能把米和万元的残差共用一个无依据阈值。列表必须覆盖模型全部约束，不能只挑通过项。证书还宜附原始日志定位、完整求解参数、最大 gap 与目标/界的来源。

共享运行时连接方式：将证书路径列入实际 `run.outputs` → `artifact-add` 使用 `kind=other` 并绑定真实 `run_id` → 主张通过 `claim.artifact_ids` 引用证书及结果表。`other` JSON 只通过文件/JSON 层检查，不自动证明其科学语义；运行时不会猜中文“最优”关键词。M1 预定义状态映射，P2 独立核对原始日志、代码目标/完整约束与证书，W1/W2 核对论文的结论强度。

`solver_certificate_check` 只检查作者声明字段的一致性和数值边界，不认证数据真实性。`linear_solver_demo` 真实运行 SciPy/HiGHS 的小 LP，取实际对偶边际得到最优界并检查对偶符号/驻点条件；解析最优利润 10 可独立对照。记录的是 SciPy 接口版本，不声称已探测内部 HiGHS 构建版本。CP-SAT 状态回归使用明确测试 fixture；未把 fixture 说成实际 CP-SAT 求解。

## 5. 机理模型固定检查表

- [ ] 单位与量纲：每项控制方程同量纲；摄氏/开尔文、小时/秒等实际换算也正确。`check_dimensions` 只比对作者声明的指数，不自动解析方程或校验仿射单位换算。
- [ ] 初值：在初始时刻代回，检查与观测、物理边界及代数约束一致；未知初值作为识别参数时注明。
- [ ] 边界：每段 Dirichlet/Neumann/Robin 条件、外法向符号、通量单位、界面连续条件按合同检查。
- [ ] 数值误差：先用解析解/制造解或可信参考解对照；至少三个步长/网格层级估计收敛阶，空间和时间误差应分别控制。
- [ ] 物理约束：检查守恒、能量、非负状态、极限行为及参数扰动；不能依靠求解器局部容差代表物理全局误差。
- [ ] 结论稳健性：加密后目标量的变化是否足以改变论文排序/决策？超过合同容差时继续细化或降低结论强度。

`mechanistic_demo_checks` 复用 [机理微分方程模块](../mechanistic-dynamics.md) 的热方程/有限元例程，报告边界残差及三层网格误差；`refinement_report` 需要独立参考误差。没有精确解时应在共同坐标比较多层结果并论证渐近区间，不能把“两个结果很接近”直接转换为真实误差上界。

## 运行与验收

从仓库根目录运行（或替换成实际 Skill 绝对路径）：

```powershell
python assets/algorithms/模型验证/validation.py --certificate-output <PROJECT_ROOT>/results/solver-certificate.json
python assets/algorithms/模型验证/sensitivity.py
python -m unittest discover -s tests -p test_model_validation_module.py -v
```

基础例程需要 NumPy/SciPy/scikit-learn；Morris/Sobol 另需项目环境中的 SALib 可选依赖。例子全为确定的合成函数/数据；随机切分、Bootstrap、SALib 默认 seed=42，实际种子/范围/采样数写入结果。依赖缺失应报告未执行，不得给出通过结论。具体科学任务仍需项目自己的真实证据、代码/输入哈希和独立审查。
