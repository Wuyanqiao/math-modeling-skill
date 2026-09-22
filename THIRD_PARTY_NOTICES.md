# 来源与第三方说明

本项目由 Wuyanqiao 在 [XiaoMaColtAI/math-modeling-skill](https://github.com/XiaoMaColtAI/math-modeling-skill) 基础上维护。上游基线为 `3c4bd1927663327812665941a445281b9c008a78`；原有 Git 历史、作者信息及组件许可文件保留。2.1.4 的通用交互、共享运行时、验证合同与 DSH 工作台改进见本仓库提交记录。

公开仓库和发布附件不等于为所有内容授予统一开源许可。本项目未添加 MIT、Apache 等整仓许可；下列组件的原有条款分别适用。发布操作本身不代表第三方再分发授权已经核实。

| 组件 | 来源和条款 |
| --- | --- |
| 原始 Skill、算法资料、模板及继承的工具改动 | 上游 Git 历史。所检查基线没有根目录许可证，未据此推定可以重新许可全部内容。 |
| `tools/docx/` | 保留 [Anthropic 原许可](tools/docx/LICENSE.txt)。其中包含复制、衍生作品及向第三方分发限制；这些限制没有因本项目改动而消失。 |
| `tools/xlsx/` | 保留 [Anthropic 原许可](tools/xlsx/LICENSE.txt)，同上。 |
| `tools/pdf/` | 保留 [Anthropic 原许可](tools/pdf/LICENSE.txt)，同上。 |
| DSH 安装包 | 基于上游适配器改进。原 UI 子包曾声明 MIT，但该声明不覆盖其全部内嵌资源；当前包保持 `private: true`、`UNLICENSED`，不在 npm 注册表发布。 |
| 本分支运行时、交互和文档改进 | 本仓库提交记录；维护者尚未为这些改进单独声明统一分发许可。 |
| 图表资料与继承示例 | 保留原说明和引用；尚未建立每个继承文件的完整许可证明。 |
| Python、Node 及桌面应用依赖 | 按各自发布渠道和许可证安装；安装包不内嵌这些第三方程序。 |

`tools/figure/skills/` 中四个 Skill 来自 [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills/tree/49c6e97775eaa18ba791bebe23162a70ae601c18/skills)，固定于该提交，保留其 [MIT 许可证](tools/figure/skills/LICENSE.md) 及 [来源、哈希和适配记录](tools/figure/skills/UPSTREAM.json)。Skill 文档许可与其引用的软件库许可相互独立。

SciencePlots 和 seaborn 是可选、单独安装的 Python 库。drawio 集成生成可编辑 XML，不内嵌 draw.io 应用。[SciVisAgentSkills](https://github.com/KuangshiAi/SciVisAgentSkills/tree/5c9ce7d28905af949dc4192b8984a44a7a5d9402) 通过本项目集成指南及固定提交、校验哈希的加载器按需用于本机，其完整 Skill 文本不随本项目分发；所检查快照没有根目录许可文件。

发行包内的 `distribution-manifest.json` 记录所含文件及 SHA-256，只证明文件组成与完整性，不授予新的第三方权利。
