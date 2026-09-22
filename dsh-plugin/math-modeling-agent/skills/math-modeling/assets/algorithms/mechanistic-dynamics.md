# 机理建模与微分方程数值解

**何时加载**：传热、扩散、运动、反应、传播等具有状态演化规律的问题。统计外推不能代替所需的守恒和边界机制。每道子问题最多两个独立模型体系；同一控制方程的基础近似、高精度展开、不同网格或求解器算一个模型族。

## 先建立完整问题

- ODE：$\dot y=f(t,y,\theta),\ y(t_0)=y_0$。列出状态、单位、参数来源、初值、时间区间与外力。
- PDE：例如 $u_t=\nabla\cdot(\alpha\nabla u)+q$。同时定义空间区域、材料/介质、初值、每段边界类型及参数。
- Dirichlet 指定状态；Neumann 指定通量/法向导数；Robin 描述混合交换。符号方向、单位与界面连续条件必须一致。
- 代数约束、质量矩阵、事件切换和延迟不能直接忽略后硬塞普通 ODE；明确是否需要 DAE、事件或延迟求解器。

## 求解方法

| 结构 | 起点 | 验证与升级依据 |
|---|---|---|
| 非刚性初值问题 | RK45；高精度需求可考虑 DOP853 | 容差收紧、守恒/解析解、事件时间稳定性 |
| 刚性 ODE | Radau 或 BDF，提供 Jacobian/稀疏结构 | 检查初值一致性、负浓度、极端时间尺度，比较成本与残差 |
| 规则网格 PDE | 有限差分；显式或隐式时间积分 | 明确离散模板、稳定性条件、边界实现、网格与时间步收敛 |
| 复杂区域/材料 | 有限元弱形式 + 网格 + 基函数 + 边界装配 | 网格质量、弱残差、积分阶次、网格收敛；求解线性系统只是其中一步 |

[`solve_ivp` 官方文档](https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html) 区分非刚性和刚性方法，并说明误差控制参数。求解器内部的 `atol + rtol*abs(y)` 是局部误差控制，不能直接宣称所有物理量的全局误差已小于同一数值。不同单位状态应分别设置绝对误差。

一维热方程的显式中心差分为

$$u_i^{n+1}=u_i^n+r(u_{i+1}^n-2u_i^n+u_{i-1}^n),\qquad r=\alpha\Delta t/(\Delta x)^2.$$

对本卡的常系数均匀一维网格，稳定条件是 $0<r\le1/2$；不能推广成所有 PDE 的通用阈值。隐式方法放宽这一稳定性限制仍需控制截断误差。

Poisson 方程 $-\nabla\cdot(k\nabla u)=f$ 的弱式是在符合齐次 Dirichlet 约束的试验函数上满足 $\int k\nabla u\cdot\nabla v=\int fv$（含通量边界时还须相应边界项）。非齐次 Dirichlet 用提升或约束处理；纯 Neumann 需检查相容性与常数零空间。复杂几何可按 [DOLFINx 官方 Poisson 示例](https://docs.fenicsproject.org/dolfinx/main/python/demos/demo_poisson.html) 扩展，依赖另行检查。

## 最小例与验证

[mechanistic-dynamics.py](mechanistic-dynamics.py) 全部为无量纲制造解，未使用外部实验数据：

1. $y'=-2y, y(0)=1$，RK45 对照 $e^{-2t}$；核对完整到达终点及误差。
2. $y'=-1000(y-\cos t)-\sin t, y(0)=1$，Radau/BDF 对照 $\cos t$。系数 1000 是这个刚性示例的尺度，不是识别刚性的通用门槛。
3. 热方程 $\alpha=1$，$x\in[0,1]$，初值 $\sin(\pi x)$、两端零值，真解 $e^{-\pi^2t}\sin(\pi x)$；在 $t=0.05$ 比较 20/40 区间网格且 $\Delta t\propto\Delta x^2$，检验二阶空间收敛趋势和稳定性。
4. 线性有限元求 $-u''=2$、两端零值；真解 $x(1-x)$。节点恰好吻合不足以验证整体场，测试单元中点误差，并检查网格加倍误差约为四分之一。

```powershell
python assets/algorithms/mechanistic-dynamics.py
python -m unittest discover -s tests -p test_algorithm_modules.py -v
```

只需 NumPy/SciPy，示例有限元是已实现的一维常系数线性单元，未实现通用二维/三维 FEM。实际题目还应验证量纲、初边值、守恒/能量、可行状态、空间和时间误差分别收敛、参数扰动及实验数据对照。`success=True`、曲线平滑或更密网格都不能独自证明机理正确。
