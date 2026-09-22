# 数学建模 Workbench 宿主组合包

此包同时注册 DeepSeek Harness 0.1.7-alpha.1 的 Agent 预设、`mm_*` 工具与 React 看板。`skills/math-modeling` 必须含共享 Python 运行时；只复制 JS 源文件不能得到完整安装包。

完整源码构建与验证说明：[升级分支安装指南](https://github.com/Wuyanqiao/math-modeling-skill/blob/WuYanqiao/universal-upgrade/dsh-plugin/README.md)。运行时 API 在包内 `skills/math-modeling/RUNTIME_API.md`。若分支尚未推送，以本地 checkout 的文档为准。

从本目录执行 `npm pack --ignore-scripts --pack-destination <临时目录>`，随后在选定的 `DSH_HOME` 下运行 `dsh plugin --profile web add <生成的tgz路径> -w --ignore-scripts`。先使用独立临时 profile 验证；Windows 跨盘目录参数可能被 pnpm 转成无效 link，因此优先安装 tgz。用 `dsh --profile web --dump-config` 检查 UI、预设和 workbench 入口均存在。

当前包为 `private: true`、`UNLICENSED` 的本地开发包。`LOCAL_DEVELOPMENT_ONLY.txt` 与 `distribution-manifest.json` 保留资料授权边界和文件哈希，不授权公开发布。

初始化后，UI 只展示共享运行时返回的状态与已保存快照；完成判定以 `mm_complete` 的 `done` 为准。运行、刷新、产物和日志预览都经过宿主 shell；不改写宿主沙箱策略。审核身份字段是声明信息，不代表宿主认证。
