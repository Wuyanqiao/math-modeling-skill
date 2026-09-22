---
name: mathmodel-drawio
description: 在数学建模项目选择 drawio 后创建可编辑论文框架、模型关系或方法流程图，并核对节点与真实模型和代码的一致性。
---

# 可编辑论文框架图

先读取项目 context；仅当 `graphicsTools.drawio` 为 true 时选择此路线。
读取已确认的建模报告、程序与论文证据大纲，列出有依据的节点、关系和分区。
不同子问题的节点可以分列，同一物理机理不同近似置于同一模型族分区。
不补造尚未实现的实验和结果，不为每个子问题机械添加独立模型。

使用 diagrams.net 原生 `mxfile/diagram/mxGraphModel/root/mxCell` XML，保留 `.drawio`。
节点具稳定 ID，边以 source/target 连接节点，标签用 XML 转义；避免把整幅图嵌成单个图片节点。
`scripts/editable_diagram.py` 接收显式节点/边 JSON，可以在无桌面端的环境生成可编辑源文件。
相对本文件的脚本位于 `../../scripts/editable_diagram.py`；脚本路径相对 Skill 根为 `tools/figure/scripts/editable_diagram.py`。

```json
{
  "title": "子问题一方法框架",
  "nodes": [
    {"id": "input", "label": "输入数据", "x": 40, "y": 40},
    {"id": "model", "label": "已确认模型", "x": 280, "y": 40}
  ],
  "edges": [{"source": "input", "target": "model", "label": "清洗后变量"}]
}
```

```bash
python "<SKILL_ROOT>/tools/figure/scripts/editable_diagram.py" framework.json --output figures/framework.drawio
```

打开 `.drawio` 后可移动节点、修改文字与连线。已安装 draw.io 桌面 CLI 时，使用它导出 SVG/PDF并核对字体；未安装时保留源文件并说明预览尚未生成，不能声称已经检查渲染。
图注放在论文正文，说明图中模块与子问题；按最终印刷宽度检查文字、箭头、分区与灰度辨识。
参考：[diagrams.net XML 文档](https://www.drawio.com/doc/faq/diagram-source-edit)。
