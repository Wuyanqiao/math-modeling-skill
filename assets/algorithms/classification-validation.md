# 分类、交叉验证与独立测试

先依据实体/时间/空间相关性设计划分，再考虑模型。普通独立样本示例使用 StratifiedKFold；相关样本需替换为按组或时间划分。

`classification.py::select_knn` 将 StandardScaler 和 KNN 放入 Pipeline，在每个 CV 训练折内重新拟合缩放；`select_tree` 在训练内部选深度。两个接口只接受训练数据，无法用测试标签调参。

依赖：scikit-learn、NumPy。调用 `evaluate_holdout` 对冻结的选择结果作最终评估，不执行 fit。不要反复观察测试曲线选择 K/深度；如使用过测试集决策，应另留新的最终测试数据。

验证：`tests/test_algorithms.py` 记录每折 scaler 拟合均值，逐一与该折训练样本对应；检查独立评估不调用 fit。小合成测试不能证明真实分类准确率。

失败模式：训练类样本不足、K 超过最小训练折样本量、标签泄漏、不平衡指标不合适。先检验数据划分和简单基线，扩展资料见 `../07-机器学习算法说明.md`。
