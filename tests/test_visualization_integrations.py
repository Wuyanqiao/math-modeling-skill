import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools/figure/scripts" / f"{name}.py")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


diagram = module("editable_diagram")
loader = module("load_scivis_skill")


class VisualizationIntegrations(unittest.TestCase):
    def test_drawio_preserves_editable_labels_and_connections(self):
        root = ET.fromstring(diagram.diagram_xml({"nodes": [{"id": "input", "label": "温度 < 阈值 & 保留原数据"},
                                                         {"id": "model", "label": "传热模型", "x": 280}],
                                                "edges": [{"source": "input", "target": "model", "label": "边界条件"}]}))
        nodes = {cell.get("id"): cell for cell in root.findall(".//mxCell")}
        self.assertEqual(nodes["node-input"].get("value"), "温度 < 阈值 & 保留原数据")
        self.assertEqual(nodes["node-model"].get("vertex"), "1")
        self.assertEqual(nodes["edge-0"].get("source"), "node-input")
        self.assertEqual(nodes["edge-0"].get("target"), "node-model")
        self.assertFalse(root.findall(".//image"))

    def test_drawio_rejects_dangling_edges_and_invalid_geometry(self):
        with self.assertRaises(ValueError):
            diagram.diagram_xml({"nodes": [{"id": "a", "label": "输入"}], "edges": [{"source": "a", "target": "missing"}]})
        with self.assertRaises(ValueError):
            diagram.diagram_xml({"nodes": [{"id": "a", "label": "输入", "x": float("nan")}]})

    def test_cache_supports_offline_and_rejects_modified_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = b"# Pinned skill\n"
            registry = root / "registry.json"
            registry.write_text(json.dumps({"repository": "owner/repo", "commit": "abc", "tools": {"napari": {
                "entry": "napari/SKILL.md", "files": [{"path": "napari/SKILL.md", "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}]}}}))
            with patch.object(loader, "REGISTRY", registry):
                with self.assertRaises(FileNotFoundError):
                    loader.load_skill("napari", root / "cache", offline=True)
                target = root / "cache/abc/napari/SKILL.md"
                target.parent.mkdir(parents=True)
                target.write_bytes(content)
                with patch.object(loader.urllib.request, "urlopen", side_effect=AssertionError("Offline mode made a network call")):
                    self.assertEqual(loader.load_skill("napari", root / "cache", offline=True), target)
                    target.write_bytes(b"changed")
                    with self.assertRaises(ValueError):
                        loader.load_skill("napari", root / "cache", offline=True)

    def test_vendored_files_match_reviewed_hashes(self):
        root = ROOT / "tools/figure/skills"
        manifest = json.loads((root / "UPSTREAM.json").read_text(encoding="utf-8"))
        for record in manifest["files"]:
            with self.subTest(path=record["path"]):
                self.assertEqual(hashlib.sha256((root / record["path"]).read_bytes()).hexdigest(), record["vendored_sha256"])


if __name__ == "__main__":
    unittest.main()
