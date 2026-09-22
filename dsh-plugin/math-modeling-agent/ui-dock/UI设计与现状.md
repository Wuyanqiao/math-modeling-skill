# 数学建模看板现状

看板使用 React 18 与宿主 `shell.overlay`、`settings.section` 插槽，按主视图当前会话及已初始化项目显示，不依赖预设名称。

- 项目页展示运行时阻塞、阶段进度、审核回执和能力。
- 证据页展示产物哈希、子问题、主张与来源，并通过宿主授权预览文本或二进制元数据。
- 运行页展示真实运行记录、stdout/stderr 受限预览和活动记录。
- 后台只读状态快照；主动“重新验证”调用共享 CLI。过期快照不能被解释为当前任务已完成。
- 看板和 `mm_ui_toggle` 共用宿主 Config/settings；支持窄屏、键盘标签切换、深色与减少动态效果偏好。

浏览器回归运行于真实 Edge 与 React，RPC 使用测试数据；这不等于整个桌面 GUI 与真实模型工作流已通过端到端测试。安装参见 [组合包 README](../plugins/dsh-math-modeling-ui/README.md)。
