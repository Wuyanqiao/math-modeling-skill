---
name: 双引擎论文搜索
description: 用可用学术检索源发现候选文献，区分后端失败与零结果、元数据匹配与原文支持。
---

# 学术检索与证据核验

OpenAlex 提供结构化元数据，AnySearch 提供学术搜索。默认并行检索；可按宿主能力选择单源，搜索源数量不等于证据质量。可能需要服务授权/密钥；不在日志和报告中写密钥。

```powershell
python "<SKILL_ROOT>/tools/paper_search/scripts/hybrid_scholar.py" --query "robust optimization vehicle routing" --limit 10 --json
python "<SKILL_ROOT>/tools/paper_search/scripts/hybrid_scholar.py" --query "analytic hierarchy process" --openalex-only --json
```

## 输出语义

- `providers` 记录各后端 `ok`、`empty` 或 `failed`、条数、时间和安全错误类别；空结果是成功搜索后的零记录，服务失败不能解释为没有论文。
- `search_status` 为 ok / partial / failed；全部启用源失败时 CLI 返回非零。partial 保留成功源结果并报告失败来源。
- `metadata_matched` 表示 DOI 或题名/年份匹配；兼容字段 `cross_validated` 保留相同含义，不代表理论正确或原文支持结论。
- 每项 `claim_support` 默认 unverified。打开原始出版页核验作者、题名、年份、期刊等，再阅读与主张相关原文并记录页码/段落；检索器不自动将它改成 verified。
- 引用量不是正确性的证明；不得根据标题或摘要编造结论。同 DOI 优先匹配，无 DOI 需题名高度相似且年份相容；排序考虑查询相关性。

Python 的旧 `search_papers()` 仍返回列表，服务状态可从该 provider 的 `last_result` 读取；新调用优先 `search_result()`，返回 ProviderResult。HybridScholar 保留原分组并新增后端状态。

## 回退与证据登记

某后端缺权限或失败时，可以用可用源发现候选并单独核验出版机构原文，记录能力缺口，不静默标成双源通过。对话或共享 runtime 的 claim 证据应包含原文位置与支持范围；跨源匹配和原文语义审核是两项不同工作。开发测试使用模拟响应，不需要调用付费服务。
