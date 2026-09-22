"""Create editable draw.io XML from explicitly supplied nodes and edges."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def diagram_xml(spec: dict) -> bytes:
    nodes, edges = spec.get("nodes", []), spec.get("edges", [])
    if not 1 <= len(nodes) <= 200 or len(edges) > 500:
        raise ValueError("Provide 1–200 nodes and at most 500 edges")
    ids = set()
    document = ET.Element("mxfile", host="app.diagrams.net")
    diagram = ET.SubElement(document, "diagram", id="framework", name=str(spec.get("title", "论文框架")))
    graph = ET.SubElement(diagram, "mxGraphModel", grid="1", gridSize="10", page="1", pageWidth="1169", pageHeight="827")
    root = ET.SubElement(graph, "root")
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", parent="0")
    for node in nodes:
        identifier = node.get("id", "")
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,63}", identifier) or identifier in ids:
            raise ValueError(f"Invalid or duplicate node ID: {identifier!r}")
        ids.add(identifier)
        label = str(node.get("label", ""))
        if not label or len(label) > 500:
            raise ValueError("Each node requires a label of at most 500 characters")
        cell = ET.SubElement(root, "mxCell", id="node-" + identifier, value=label, vertex="1", parent="1",
                             style="rounded=1;whiteSpace=wrap;html=0;fillColor=#f4f7fc;strokeColor=#63758e;fontColor=#202b3c;fontSize=14;spacing=12;")
        geometry = {}
        for key, default in (("x", 40), ("y", 40), ("width", 180), ("height", 70)):
            value = node.get(key, default)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 10000 or (key in ("width", "height") and value == 0):
                raise ValueError(f"Invalid node geometry: {key}")
            geometry[key] = str(value)
        ET.SubElement(cell, "mxGeometry", geometry | {"as": "geometry"})
    for index, edge in enumerate(edges):
        if edge.get("source") not in ids or edge.get("target") not in ids:
            raise ValueError("Every edge must connect supplied node IDs")
        cell = ET.SubElement(root, "mxCell", id=f"edge-{index}", value=str(edge.get("label", "")),
                             source="node-" + edge["source"], target="node-" + edge["target"], edge="1", parent="1",
                             style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=0;endArrow=block;fontSize=12;strokeColor=#63758e;")
        ET.SubElement(cell, "mxGeometry", relative="1", attrib={"as": "geometry"})
    ET.indent(document)
    return ET.tostring(document, encoding="utf-8", xml_declaration=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.spec.stat().st_size > 1024 * 1024:
            raise ValueError("Diagram specification exceeds 1 MiB")
        content = diagram_xml(json.loads(args.spec.read_text(encoding="utf-8")))
        if args.output.suffix.lower() != ".drawio":
            raise ValueError("Output must use .drawio extension")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as output:
            output.write(content)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
