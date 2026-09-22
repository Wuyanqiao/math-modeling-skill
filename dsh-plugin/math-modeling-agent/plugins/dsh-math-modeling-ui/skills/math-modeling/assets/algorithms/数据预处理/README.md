# 数据预处理

此目录是可独立使用的数据预处理模块，作为优化、预测、评价等模型之前的公共步骤。入口是 [preprocessing.py](preprocessing.py)，包含可直接执行的合成数据示例，以及可放入 scikit-learn 交叉验证的 `Pipeline`。

先依据数据产生过程划分训练与测试，再在训练集内分析缺失、学习填补器和编码器、拟合尺度参数。测试集只调用 `transform`；填补方案和超参数也在训练集的内部验证中选择。这一边界同样适用于特征筛选、PCA、异常值阈值和重采样。[scikit-learn 防泄漏指南](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage)

## 运行与依赖

在仓库根目录安装已有的科学计算可选依赖，然后运行：

```bash
python -m pip install -e ".[science]"
python "assets/algorithms/数据预处理/preprocessing.py"
python -m unittest discover -s tests -p test_preprocessing_module.py -v
```

脚本不下载数据、不覆盖材料、不写文件；stdout 输出 JSON，包含训练、测试、排除行的**位置索引**、训练缺失比例、整列缺失名单、最终特征名、合成样本预测和 RMSE。它展示接口运行，并不代表竞赛数据上的模型效果。运行前保留真实输入的 SHA-256、字段单位和版本；项目已有运行登记工具可登记此脚本及 stdout。

本次核验环境为 Python 3.13.13、NumPy 2.5.3、pandas 3.0.5、scikit-learn 1.9.1。源码使用 `keep_empty_features`、`sparse_output` 等现代接口，依赖范围沿用项目 `science`，不另外固定一套版本。复现实验时保存实际版本和随机种子。

## 按数据特点选择方案

先在训练部分确认观测单位、ID/重复实体、字段类型、单位、取值范围、缺失编码、时序频率和目标可获得时间。根据这些信息确定候选方案，再比较训练内部的验证结果；缺失比例本身不能证明缺失机制。

| 训练数据特点 | 可运行选项 | 使用条件与检查 |
| --- | --- | --- |
| 缺失较少，先建立稳健基线 | `imputation="simple", simple_strategy="median"` | 偏态和异常值情况下优先比较中位数；近对称连续变量可比较 `mean`；计数/离散值可比较 `most_frequent` |
| 相近观测的特征相似，样本规模适中 | `imputation="knn", n_neighbors=5` | 本实现先用训练集观测值拟合 `StandardScaler`，再计算 KNN 距离；无关特征、高维、离群点会削弱邻居意义，k 只能在训练内部选 |
| 多变量相关结构能支持预测缺失项 | `imputation="iterative", seed=42` | 显式启用实验性 `IterativeImputer`；固定随机种子、关闭后验采样。观察收敛警告和结果合理性，不保证胜过简单填补 |
| 某数值列在训练部分全部缺失 | `empty_policy="constant"` 或 `"error"` | 默认保留维度、固定为 `empty_fill_value=0`，且对测试后来出现的该列值也使用常数；报表保留该列名单。关键物理变量可选 `error`，要求补资料 |
| 类别变量无自然顺序 | `encoding="onehot"` | 仅从训练集学习词表；新类别编码为该字段的全零向量，不增加维度；类别缺失保留独立标记 |
| 类别有外部定义的自然顺序 | `encoding="ordinal", ordinal_categories={...}` | 必须显式提供每列的顺序，不能根据字母排序猜测；未知类别/缺失记为 -1，模型解释中需单独说明 |

Simple、KNN、Iterative 的统计假设、资源需求不同，应保留简单基线；Iterative 目前仍是实验性接口。该模板执行单次确定性填补，不把它当作传播缺失不确定性的多重插补。[缺失值处理官方指南](https://scikit-learn.org/stable/modules/impute.html)，[IterativeImputer 接口](https://scikit-learn.org/stable/modules/generated/sklearn.impute.IterativeImputer.html)

`OneHotEncoder(handle_unknown="ignore")` 的未知类别语义是全零，不能把它解释为某个已经学习的类别；类别频率合并等扩展也应只在训练折拟合。[OneHotEncoder 官方接口](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.OneHotEncoder.html)

### 尺度与特征构造

| 设置 | 适用检查 |
| --- | --- |
| `scale="standard"` | 线性正则、SVM、距离方法的常见起点；训练均值/标准差用于后续数据 |
| `scale="robust"` | 用训练中位数和四分位距减少极值对尺度的影响；不等于删除异常点 |
| `scale="minmax"` | 希望训练样本落在固定范围；测试值可以越出 `[0,1]`，此实现不静默截断 |
| `scale="none"` | 保留填补后尺度；使用 KNN 填补时，其前置的距离标准化仍然生效 |
| `ratios={"density": ("mass", "volume")}` | 仅使用同一行预先声明的数值列；分母 0 记缺失，再由训练填补器处理，不把无定义的比值写成真实 0 |
| `cyclical={"hour": 24}` | 生成周期正弦/余弦特征；周期由领域约定提供，不从测试表现倒推 |

所有数值列（含生成列）都附带缺失指示器，因此测试阶段首次缺失也有稳定维度。训练整列缺失标志和指示器保留，常数 0 只是管道占位，不是“测量值等于 0”。`RowFeatures` 把显式声明的数值字段中的 ±∞ 视作缺失，无法解析的非数值字符串则报错；请在原始质量报告记录这些处理。

强偏态变量还可在训练折内考虑 `PowerTransformer(method="yeo-johnson")`，或对严格正值考虑 Box-Cox；不能对未满足取值条件的数据硬套变换。此文件没有自动选择幂变换，以免在缺少领域依据时改变变量含义。[PowerTransformer 官方接口](https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.PowerTransformer.html)

## 划分契约

`split_indices(frame, ...)` 返回 `(train_positions, test_positions, excluded_positions)`，使用位置索引，所以原 DataFrame 索引可不连续。`prepare_split(...)` 会调用它，再执行唯一的训练拟合。

| mode | 参数 | 保证与边界 |
| --- | --- | --- |
| `random` | `test_size, seed, stratify` | 独立同分布样本的固定随机划分；分类可传目标数组作分层；有组/时间约束时拒绝仍用 random |
| `group` | `group_col` | 整组进入同一侧，避免同一患者、站点、设备的重复记录两边出现；test_size 是组的比例，行数比例未必相同 |
| `time` | `time_col, gap` | 先排序，最后若干**唯一时间点**作为测试，同一时间点不会跨边界；训练/测试间排除 gap 个时间点 |
| `group_time` | `group_col, time_col, gap` | 先按时间划分，再从训练中移除出现在未来测试中的组；同时要求时间前后和组不相交。可能无法留下训练样本，此时明确报错 |

`gap` 是离散时间点数量，**不是小时或天数**；不规则时间间隔需要自行按实际时间定义 embargo。`group_time` 的目标是“未来的新组”，并不适合直接评价“同一设备未来的观测”；后者用时间划分，并说明允许同一实体跨期。分组和时间的验证设计应跟真实部署问题一致。[GroupShuffleSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupShuffleSplit.html)，[TimeSeriesSplit 与 gap](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)

此模块不生成滞后/滚动统计，也不对完整数据做向后填充。若扩展时间特征，必须按实体排序、`shift(1)` 或遵守可获得时间，并在每个回测时点只使用已公开的历史；目标泄漏不会仅靠 `Pipeline` 自动消除。

## 使用自己的数据

可把 `preprocessing.py` 复制到项目代码目录后导入：

```python
import pandas as pd
from preprocessing import prepare_split

raw = pd.read_csv("data.csv")
prepared = prepare_split(
    raw,
    target="target",
    numeric_columns=["mass", "volume", "hour"],
    categorical_columns=["site_type"],
    split={"mode": "time", "time_col": "timestamp", "test_size": 0.2, "gap": 1},
    imputation="simple",
    scale="robust",
    ratios={"density": ("mass", "volume")},
    cyclical={"hour": 24},
)
print(prepared["audit"])
# 只能用 y_train 拟合；y_test 留作最终评估。
```

字段必须显式声明。`prepare_split` 拒绝把 target、group_col、time_col 直接放入预测列；若确需日历协变量，先根据预测时已知的日历规则声明 hour 等独立字段。目标缺失时报错，不自动填补标签。类别值规范化为字符串，缺失保留为 NaN；原数据不能使用内部保留值 `__MATHMODEL_MISSING__`。

内部交叉验证时，应把**未拟合**的预处理器与模型放进同一个外层 Pipeline，而不是把 `prepared["X_train"]` 当作所有折已经预处理好的输入：

```python
from sklearn.linear_model import Ridge
from sklearn.model_selection import TimeSeriesSplit, cross_validate
from sklearn.pipeline import Pipeline
from preprocessing import make_preprocessor, split_indices

train, test, excluded = split_indices(raw, mode="time", time_col="timestamp", test_size=0.2, gap=1)
pipeline = Pipeline([
    ("prepare", make_preprocessor(["mass", "volume"], ["site_type"])),
    ("model", Ridge(alpha=1.0)),
])
training = raw.iloc[train]  # split_indices 的时间模式已按时间排序
scores = cross_validate(
    pipeline, training[["mass", "volume", "site_type"]], training["target"],
    cv=TimeSeriesSplit(n_splits=3, gap=1), scoring="neg_mean_squared_error", error_score="raise",
)
pipeline.fit(training[["mass", "volume", "site_type"]], training["target"])
predictions = pipeline.predict(raw.iloc[test][["mass", "volume", "site_type"]])
```

此 `TimeSeriesSplit` 示例适用于等间隔且每时点一行的数据；重复时间点或面板数据须提供保持时间点/分组边界的折索引，不能照抄按行划分。`GroupKFold` 可处理组分离，组与时间同时存在时需验证两个约束。参数搜索和特征筛选也应留在外层 Pipeline/训练内部验证中。

当前实现输出 dense 数组，面向中小规模表格；高基数类别、海量 KNN 和高维 Iterative 应先评估内存/时间，改用稀疏编码、频率合并或更简单的填补，且保持同一训练拟合边界。

## 已执行的行为测试

测试用真实 scikit-learn 计算验证：改变测试数值、类别及标签不影响训练转换结果与拟合统计；未知类别不扩词表；三种填补器对训练整列缺失遵守相同策略；首次测试缺失有指示器；显式顺序编码有确定映射；比值和周期特征只依赖当前行；随机划分可重复；组不跨边界；时间点相同不会跨边界；gap/跨期组排除可核查；交叉验证的每一折使用该折训练中位数。另对完整示例和克隆的三个填补 Pipeline 检查确定性输出。
