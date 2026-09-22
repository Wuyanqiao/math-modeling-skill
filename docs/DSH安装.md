# DSH 插件安装与升级

下载 [2.1.4 DSH 插件](https://github.com/Wuyanqiao/math-modeling-skill/releases/download/v2.1.4/dsh-math-modeling-ui-2.1.4.tgz)。包内包含匹配的通用 Skill、运行时和侧栏界面，不需要额外整合 ZIP。

已验证宿主为 DeepSeek Harness 0.1.7-alpha.1；本机使用 Node 24.11.1、Python 3.13 与 Windows。确认对应环境能运行 `dsh`、`node`、`python`，再执行：

```powershell
dsh plugin --profile web add "C:\Downloads\dsh-math-modeling-ui-2.1.4.tgz" -w --ignore-scripts
```

路径和 profile 按实际情况替换。本地文件安装后应保留 `.tgz`：profile 可能继续引用该路径，移走文件会影响后续重装。

升级前备份 profile 中的 `package.json`、lockfile、`cordis.yml` 和 `cordis.patch.yml`。待 Agent 任务结束后重启 DSH 后端并刷新界面，保留其他插件、模型与权限配置。

## 使用

选择工作区和数学建模 Workbench 预设，在右侧栏文件与终端下方进入看板；首次点击时初始化，之后复用已有状态。保存材料与配置后，点击右上角“开始”选择执行范围。

看板和主聊天区可能属于不同会话。任务使用看板所属会话；弹层可展开查看会话与目录，执行过程和停止操作在该会话中进行。

## 早期预设迁移

2.1.1 起，workbench 服务须声明隔离域。若旧 profile 的 `cordis.patch.yml` 保存了自定义预设 `config.plugins` 覆盖列表，检查对应节点：

```yaml
- id: math-modeling
  name: dsh-math-modeling-ui/workbench
  isolate:
    mathModelWorkbench: true
```

节点 ID 以实际配置为准，保留其他节点。缺少声明会报 `Preset services require isolate realms: mathModelWorkbench`；全新安装包自带正确声明。

## Windows 初始化权限

若正确选择预设后仍出现 `SetNamedSecurityInfoW`、`grantWrite`、`Win32 5`，检查工作区父目录的沙箱授权条件。普通文件写入权限不等于能够设置沙箱所需的安全描述符。

安装包保留准备工具：

```text
<实际 profile>/node_modules/dsh-math-modeling-ui/skills/math-modeling/scripts/prepare_dsh_windows_workspace.py
```

执行 `python <工具路径> --help`，按帮助对实际父目录做只读检查。显式应用须同时指定 `--apply` 和新的 `--backup` 文件。工具只准备一级项目目录所需权限，不递归修改深层文件，不改变所有者；保留备份后重试看板，无需切换完全访问。

## 验证范围

2.1.4 本机 DSH 回归 45/45 通过，覆盖预设隔离、Windows 沙箱初始化、环境检测、任务选择、防重与官方会话提交。提交测试使用隔离模型，不代表替用户完成了数学建模。第三方来源及原许可见 [第三方说明](../THIRD_PARTY_NOTICES.md)。
