# 数学建模 Workbench 宿主组合包

此包当前版本为 **2.1.2**，同时注册 DeepSeek Harness 0.1.7-alpha.1 的 Agent 预设、`mm_*` 工具与 React 看板。`skills/math-modeling` 必须含共享 Python 运行时；只复制 JS 源文件不能得到完整安装包。

完整源码构建与验证说明：[升级分支安装指南](https://github.com/Wuyanqiao/math-modeling-skill/blob/WuYanqiao/universal-upgrade/dsh-plugin/README.md)。运行时 API 在包内 `skills/math-modeling/RUNTIME_API.md`。若分支尚未推送，以本地 checkout 的文档为准。

从本目录执行 `npm pack --ignore-scripts --pack-destination <临时目录>`，随后在选定的 `DSH_HOME` 下运行 `dsh plugin --profile web add <生成的tgz路径> -w --ignore-scripts`。先使用独立临时 profile 验证；Windows 跨盘目录参数可能被 pnpm 转成无效 link，因此优先安装 tgz。用 `dsh --profile web --dump-config` 检查 UI、预设和 workbench 入口均存在。

从 2.1.0 升级时，若实际 profile 的 `cordis.patch.yml` 保存了旧的预设 `config.plugins` 覆盖列表，须在其中的 workbench 节点同步补齐 `isolate: { mathModelWorkbench: true }`，并保留其他自定义项；然后在任务结束后重启宿主。旧覆盖仍生效时，只替换 npm 包无法修复 `agent-preset/invalid`。预设可用性须通过实际创建会话确认，不能仅依据配置输出。

当前包为 `private: true`、`UNLICENSED` 的本地开发包。`LOCAL_DEVELOPMENT_ONLY.txt` 与 `distribution-manifest.json` 保留资料授权边界和文件哈希，不授权公开发布。

初始化后，UI 只展示共享运行时返回的状态与已保存快照；完成判定以 `mm_complete` 的 `done` 为准。运行、刷新、产物和日志预览都经过宿主 shell；不改写宿主沙箱策略。审核身份字段是声明信息，不代表宿主认证。

“配置”页的“环境与依赖”调用 `mm.environment`；Agent 可使用 `mm_environment`。检测读取当前会话绑定项目的已保存配置，将依赖列为必需、已选或可选，显示实际 Python 解释器、检查时间，以及已就绪、缺失、检测错误或需人工配置的状态。未保存的配置草稿不参与检测；`ok:true` 表示请求完成，环境是否齐备需查看 `ready` 和逐项结果。

可复制安装命令或 Agent 安装提示，再通过宿主正常授权流程执行；检测本身不安装、不联网、不修改项目状态。密钥仅检查是否配置，不返回或展示密钥内容，不验证外部服务可用性。缺少或损坏的库、超时和宿主拒权不会被当作成功；单次宿主调用上限 90 秒，安装后应重新检测。开始页和状态轮询不会自动运行环境检查。
