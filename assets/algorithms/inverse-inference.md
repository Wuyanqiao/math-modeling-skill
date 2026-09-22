# 参数识别、反问题与贝叶斯推断

**何时加载**：已知机理/观测方程而参数未知，需要从观测反推参数、隐状态、边界或源项，并回答参数是否可信。拟合、正则化、后验估计可以服务于同一个模型族；不把每种估计器各算一个模型。每道子问题最多两个独立模型体系。

## 合同先于优化

定义前向映射 $y_i=h(x_i;\theta)+\epsilon_i$、可观测量、参数单位和允许范围；区分输入误差、观测噪声、机理偏差与数值误差。明确采样设计和训练/验证分工；按时间、实验批次、被试或空间组划分，不能用最终测试集选择正则化强度/先验。

| 目标 | 方法 | 条件与风险 |
|---|---|---|
| 非线性参数拟合 | 有界非线性最小二乘、加权残差 | 权重来自误差尺度/协方差；局部极小、初值、边界活跃、单位缩放需报告 |
| 病态反演 | Tikhonov、平滑/稀疏正则化 | 正则项表达先验偏好，可能引入偏差；强度用训练内验证、噪声依据等选择 |
| 不确定参数 | 似然 + 明确先验 + 后验推断 | 区分可信区间和频率置信区间；先验不能伪装成观测 |
| 无解析后验 | MCMC/HMC 等 | 多链、热身、混合/收敛与有效样本诊断；采样成功不等于模型正确 |
| 模型解释力 | 后验预测检验、留出预测 | 在数据空间检查尾部、方差、相关结构和覆盖率，不能只看参数均值 |

目标可写为 $\min_{\ell\le\theta\le u}\sum_i[r_i(\theta)/\sigma_i]^2$。相关误差应使用协方差白化而不是只除逐点标准差；稳健损失缓解异常值敏感性，但不能掩盖单位错误或系统偏差。SciPy 的 [`least_squares`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html) 提供边界、Jacobian 和损失选项；全局/局部求解与约束选择见[优化教程](https://docs.scipy.org/doc/scipy/tutorial/optimize.html)。

## 可辨识性不能跳过

先检查结构可辨识性：是否不同参数能生成完全相同观测？如 $y=(a+b)x$ 只能识别和，不能凭低拟合误差分别报告 $a,b$。再看实际可辨识性：有限噪声数据是否足够区分参数？

- 在有物理意义的尺度上检查灵敏度/Jacobian 的列相关性、秩与奇异值；数值秩只是一项局部诊断，不证明全局唯一。
- 采用多初值、参数剖面、bootstrap 或后验相关性检查平坦方向；观测时间范围不足时增加观测设计比堆求解器更有效。
- 若不可辨识，报告可识别的参数组合、固定参数的依据或增加实验；不得把求解器返回的一组值写成唯一物理常数。

Tikhonov 示例求解 $\|A\theta-y\|^2+\lambda\|\theta-\theta_0\|^2$，通过增广矩阵 $[A;\sqrt\lambda I]$ 进行 QR/SVD 最小二乘，避免显式逆矩阵。一般正则矩阵 $L$ 需同时说明零空间与边界含义，本示例仅实现 $L=I$。

## 贝叶斯验证路线

后验为 $p(\theta\mid y)\propto p(y\mid\theta)p(\theta)$；后验预测对参数不确定性积分，再加观测噪声，不能把参数标准差直接当预测区间。先做先验预测检查，再从后验生成复制观测，与真实观测的任务相关统计量比较。[Stan 官方预测检验](https://mc-stan.org/docs/stan-users-guide/posterior-predictive-checks.html)

正式 MCMC 结果应记录每链种子、采样/热身长度、接受/发散信息、rank-normalized split-Rhat、bulk/tail ESS 和 Monte Carlo 误差；目标参数与尾部概率分别评估。短链、Rhat 接近 1 或看似平滑的轨迹都不是完整证明；多模态还需探索不同模式。[Stan 官方链诊断](https://mc-stan.org/rstan/reference/Rhat.html)

## 可运行例与边界

[inverse-inference.py](inverse-inference.py) 使用合成数据和解析对照：

- $y=2e^{-0.7t}$，21 个无噪声观测恢复 $(2,0.7)$；只在 $t=0$ 观测时 Jacobian 秩退化为 1，衰减率不可识别。
- $A=I,y=(2,4),\lambda=1,\theta_0=0$ 的正则解为 $(1,2)$。
- $\theta\sim N(0,1)$，$y_i\mid\theta\sim N(\theta,1)$，观测 $(1,2,3)$：后验 $N(1.5,0.25)$，单次新观测预测方差为 1.25。
- 四条随机游走 Metropolis 链以这个已知正态后验为目标，seed=42，热身 2000、每链保留 8000；与解析均值/方差对照。这只是采样机制的数值示例，未实现 rank-Rhat/ESS，也不认证任意题目后验收敛。

```powershell
python assets/algorithms/inverse-inference.py
python -m unittest discover -s tests -p test_algorithm_modules.py -v
```

需要 NumPy/SciPy。例子不需要 Stan 或付费服务；复杂后验使用相应软件前检查独立依赖。真实题目需记录数据与代码哈希、边界、先验来源、验证集、优化停止原因、采样诊断以及预测覆盖，不能把本例无噪声恢复精度推广到真实测量。
