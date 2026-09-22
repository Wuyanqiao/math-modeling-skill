import base64
import io
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mathmodel_runtime.engine import dispatch
from mathmodel_runtime.storage import WorkflowError, digest, snapshot
from mathmodel_runtime.schema import validate_state
from mathmodel_runtime import inputs as material_runtime


class ProjectInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="材料 导入 ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.call("init", profile="short", scope="full")

    def call(self, action, **args):
        return dispatch({"action": action, "project_root": str(self.root), "skill_root": str(ROOT), **args})

    def imported(self, raw=b"Original problem text", **args):
        return self.call("input-import", filename="原题.txt", kind="problem", content_base64=base64.b64encode(raw).decode(), **args)["input"]

    def staged(self, raw, upload_id="a" * 32):
        directory = self.root / ".math-modeling/incoming" / upload_id
        directory.mkdir(parents=True, exist_ok=True)
        parts = []
        for index, offset in enumerate(range(0, len(raw), material_runtime.MAX_CHUNK_BYTES)):
            path = directory / f"{index}.base64"
            path.write_text(base64.b64encode(raw[offset:offset + material_runtime.MAX_CHUNK_BYTES]).decode(), encoding="ascii")
            parts.append(path.relative_to(self.root).as_posix())
        return parts

    def hashes(self):
        state = self.call("state")
        return {gate: snapshot(self.root, state, phase, gate=gate)["hash"] for gate, phase in {"M1": "modeling", "P1": "programming", "P2": "programming", "W1": "paper", "W2": "paper"}.items()}

    def test_configuration_persists_false_and_shared_agent_context(self):
        before = self.call("state")
        self.assertFalse(any(before["project"]["optionalCollab"].values()))
        self.assertEqual([name for name, enabled in before["project"]["graphicsTools"].items() if enabled], ["scientific-visualization", "matplotlib"])
        self.call("configure", settings={"graphics_tools": {"scienceplots": True, "seaborn": True}, "optional_collab": {"literature": True, "prototype": True}})
        configured = self.call("configure", settings={"graphics_tools": {"scienceplots": False}, "optional_collab": {"literature": False}, "paper_requirements": {"text": "正文不超过20页", "source": "用户要求"}})
        project = configured["project"]
        self.assertFalse(project["graphicsTools"]["scienceplots"])
        self.assertTrue(project["graphicsTools"]["seaborn"])
        self.assertFalse(project["optionalCollab"]["literature"])
        self.assertTrue(project["optionalCollab"]["prototype"])
        self.assertEqual(project["project_id"], before["project"]["project_id"])
        context = self.call("context")["agent_context"]
        self.assertIn("正文不超过20页", context["content"])
        self.assertIn('"scienceplots": false', context["content"])
        self.assertIn("独立门禁质检始终适用", context["content"])
        self.assertEqual((self.root / context["path"]).read_text(encoding="utf-8"), context["content"])
        self.assertEqual(self.call("state")["required_gates"], ["M1", "P1", "P2", "W1", "W2"])

    def test_configuration_rejects_identity_changes_and_invalid_flags_atomically(self):
        original = self.call("state")["project"]
        for settings in ({"projectRoot": str(self.root.parent)}, {"project_id": "other"}, {"graphics_tools": {"matplotlib": False}}, {"optional_collab": {"literature": "false"}}, {"paper_requirements": {"text": "rules", "source": ""}}, {"title": "new", "scope": "nothing"}):
            with self.subTest(settings=settings), self.assertRaises(WorkflowError):
                self.call("configure", settings=settings)
            self.assertEqual(self.call("state")["project"], original)

    def test_old_v2_state_migrates_without_changing_project_identity(self):
        path = self.root / ".math-modeling/state.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        project_id = state["project"]["project_id"]
        for key in ("graphicsTools", "paperRequirements", "competition", "edition"):
            state["project"].pop(key, None)
        state.pop("inputs", None)
        state.pop("agent_context", None)
        path.write_text(json.dumps(state), encoding="utf-8")
        migrated = self.call("state")
        self.assertEqual(migrated["schema_version"], 2)
        self.assertEqual(migrated["project"]["project_id"], project_id)
        self.assertEqual(migrated["inputs"], {})
        self.assertTrue(self.call("configure", settings={"title": "Migrated project"})["ok"])

    def test_import_preserves_exact_original_and_never_overwrites_same_name(self):
        raw = "\ufeff原题：求最小成本。\r\n".encode("utf-8")
        first, second = self.imported(raw), self.imported(raw + b"second")
        self.assertNotEqual(first["path"], second["path"])
        self.assertEqual((self.root / first["path"]).read_bytes(), raw)
        self.assertEqual(digest(self.root / first["path"]), first["sha256"])
        self.assertEqual(first["extraction"]["status"], "extracted")
        self.assertIn("求最小成本", self.call("input-read", input_id=first["input_id"])["content"])
        self.assertIn(first["path"], self.call("context")["agent_context"]["content"])
        self.assertEqual(len(self.call("input-list")["inputs"]), 2)

    def test_project_relative_source_is_copied_and_absolute_or_traversal_paths_rejected(self):
        source = self.root / "existing.txt"
        source.write_bytes(b"preserve source")
        item = self.call("input-import", kind="problem", filename="original.txt", source_path="existing.txt")["input"]
        self.assertEqual(source.read_bytes(), (self.root / item["path"]).read_bytes())
        for bad in (str(source), "../outside.txt", ".math-modeling/state.json", "C:/outside.txt", "..\\outside.txt"):
            with self.subTest(path=bad), self.assertRaises(WorkflowError):
                self.call("input-import", kind="problem", filename="original.txt", source_path=bad)
        for name in ("../bad.txt", "C:bad.txt", "NUL.txt", "dir/bad.txt", "bad.txt "):
            with self.subTest(filename=name), self.assertRaises(WorkflowError):
                self.call("input-import", kind="problem", filename=name, content_base64="eA==")

    def test_chunked_upload_decodes_multiple_parts_and_removes_owned_staging(self):
        raw = b"a" * (material_runtime.MAX_CHUNK_BYTES + 57)
        parts = self.staged(raw)
        item = self.call("input-import", kind="attachment", filename="data.bin", source_base64_parts=parts, expected_size=len(raw))["input"]
        self.assertEqual((self.root / item["path"]).read_bytes(), raw)
        self.assertTrue(all(not (self.root / path).exists() for path in parts))
        self.assertFalse((self.root / ".math-modeling/incoming" / ("a" * 32)).exists())
        self.assertEqual(item["extraction"]["status"], "not-extracted")

    def test_failed_chunk_import_cleans_verified_parts_without_losing_other_files(self):
        parts = self.staged(b"text")
        directory = (self.root / parts[0]).parent
        keep = directory / "keep.txt"
        keep.write_text("keep", encoding="utf-8")
        (self.root / parts[0]).write_text("not valid base64", encoding="ascii")
        with self.assertRaises(WorkflowError):
            self.call("input-import", kind="problem", filename="original.txt", source_base64_parts=parts, expected_size=4)
        self.assertFalse((self.root / parts[0]).exists())
        self.assertTrue(keep.exists())
        self.assertEqual(self.call("input-list")["inputs"], {})
        parts = self.staged(b"text")
        (self.root / parts[0]).write_text("非ASCII数据", encoding="utf-8")
        with self.assertRaisesRegex(WorkflowError, "ASCII"):
            self.call("input-import", kind="problem", filename="original.txt", source_base64_parts=parts, expected_size=4)
        self.assertFalse((self.root / parts[0]).exists())
        self.assertTrue(keep.exists())

    def test_upload_order_size_and_cleanup_cannot_target_arbitrary_metadata(self):
        parts = self.staged(b"text")
        with self.assertRaises(WorkflowError):
            self.call("input-import", kind="problem", filename="original.txt", source_base64_parts=[".math-modeling/state.json"], expected_size=4)
        self.assertTrue((self.root / ".math-modeling/state.json").is_file())
        with self.assertRaises(WorkflowError):
            self.call("input-import", kind="problem", filename="original.txt", source_base64_parts=parts, expected_size=5)
        self.assertFalse((self.root / parts[0]).exists())
        parts = self.staged(b"new")
        self.assertEqual(self.call("input-staging-cleanup", upload_id="a" * 32)["removed"], 1)
        with self.assertRaises(WorkflowError):
            self.call("input-staging-cleanup", upload_id="../")

    def test_size_and_count_limits_are_enforced_before_original_publication(self):
        with patch.object(material_runtime, "MAX_FILE_BYTES", 3), self.assertRaises(WorkflowError):
            self.imported(b"1234")
        self.assertEqual(self.call("input-list")["inputs"], {})
        self.imported(b"123")
        with patch.object(material_runtime, "MAX_PROJECT_BYTES", 5), self.assertRaises(WorkflowError):
            self.imported(b"456")
        with patch.object(material_runtime, "MAX_INPUTS", 1), self.assertRaises(WorkflowError):
            self.imported(b"1")
        self.assertEqual(len(self.call("input-list")["inputs"]), 1)

    def test_docx_text_is_extracted_with_limitations_and_malformed_original_is_preserved(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>真实原题文本</w:t></w:r></w:p></w:body></w:document>')
        item = self.call("input-import", kind="problem", filename="original.docx", content_base64=base64.b64encode(stream.getvalue()).decode())["input"]
        self.assertEqual(self.call("input-read", input_id=item["input_id"])["content"], "真实原题文本")
        self.assertIn("equations", item["extraction"]["notice"])
        invalid = self.call("input-import", kind="problem", filename="broken.docx", content_base64=base64.b64encode(b"not a docx").decode())["input"]
        self.assertEqual(invalid["extraction"]["status"], "failed")
        self.assertEqual((self.root / invalid["path"]).read_bytes(), b"not a docx")
        self.assertIsNone(self.call("input-read", input_id=invalid["input_id"])["content"])

    def test_pdf_without_extractor_is_explicitly_blocked_and_original_retained(self):
        raw = b"%PDF-1.4\nminimal input placeholder"
        with patch.dict(sys.modules, {"pypdf": None}):
            item = self.call("input-import", kind="problem", filename="original.pdf", content_base64=base64.b64encode(raw).decode())["input"]
        self.assertEqual(item["extraction"]["status"], "blocked")
        self.assertIsNone(self.call("input-read", input_id=item["input_id"])["content"])
        self.assertEqual((self.root / item["path"]).read_bytes(), raw)

    def test_binary_or_non_utf8_text_is_never_reported_as_extracted(self):
        item = self.imported(b"\xff\xfe\x00\x00")
        self.assertEqual(item["extraction"]["status"], "failed")
        self.assertIsNone(self.call("input-read", input_id=item["input_id"])["content"])

    def test_material_drift_is_visible_and_prevents_reading_stale_extraction(self):
        item = self.imported()
        (self.root / item["path"]).write_bytes(b"tampered original")
        current = self.call("state")
        self.assertTrue(current["inputs"][item["input_id"]]["stale"])
        self.assertIn("已漂移", current["agent_context"]["content"])
        with self.assertRaisesRegex(WorkflowError, "changed"):
            self.call("input-read", input_id=item["input_id"])

    def test_material_and_configuration_freshness_is_scoped_to_the_relevant_gates(self):
        original = self.hashes()
        self.call("input-import", kind="paper-template", filename="template.tex", content_base64=base64.b64encode(b"\\documentclass{article}").decode())
        paper = self.hashes()
        for gate in ("M1", "P1", "P2"):
            self.assertEqual(original[gate], paper[gate])
        for gate in ("W1", "W2"):
            self.assertNotEqual(original[gate], paper[gate])
        self.call("configure", settings={"paper_requirements": {"text": "20 pages", "source": "User"}})
        requirements = self.hashes()
        self.assertEqual(paper["P2"], requirements["P2"])
        self.assertNotEqual(paper["W1"], requirements["W1"])
        self.call("configure", settings={"graphics_tools": {"drawio": True}})
        graphics = self.hashes()
        self.assertEqual(graphics["M1"], requirements["M1"])
        self.assertNotEqual(graphics["P1"], requirements["P1"])
        self.imported()
        self.assertNotEqual(self.hashes()["M1"], graphics["M1"])

    def test_problem_import_invalidates_an_existing_model_review(self):
        (self.root / "题目分析报告.md").write_text("模型：最小化成本，目标x，约束x>=1。", encoding="utf-8")
        (self.root / "术语表格.md").write_text("|x|决策量|", encoding="utf-8")
        task = self.call("gate-prepare", gate="M1")
        receipt = {"task_id": task["task_id"], "snapshot_hash": task["snapshot_hash"], "reviewer_id": "independent-fixture", "review_source": "external", "status": "PASS", "scope": "Test fixture", "evidence": [{"path": path, "sha256": sha} for path, sha in task["request"]["snapshot"]["files"].items()], "findings": [], "rework": ""}
        self.call("gate-record", gate="M1", receipt=receipt)
        self.imported()
        self.assertEqual(self.call("state")["gates"]["M1"]["status"], "invalidated")

    def test_read_only_input_and_context_reads_preserve_restore_preview_revision(self):
        item = self.imported()
        checkpoint = self.call("checkpoint-create")["checkpoint"]["checkpoint_id"]
        preview = self.call("checkpoint-restore", checkpoint_id=checkpoint)
        for action, options in (("context", {}), ("input-list", {}), ("input-read", {"input_id": item["input_id"]}), ("state", {})):
            self.assertEqual(self.call(action, **options)["revision"], preview["expected_revision"])
        self.assertTrue(self.call("checkpoint-restore", checkpoint_id=checkpoint, apply=True, expected_revision=preview["expected_revision"])["ok"])

    def test_large_unicode_configuration_roundtrips_through_bounded_cli_stdin(self):
        requirement = "真实论文要求" * 5000
        request = {"action": "configure", "project_root": str(self.root), "skill_root": str(ROOT), "settings": {"paper_requirements": {"text": requirement, "source": "用户面板填写"}}}
        encoded = base64.b64encode(json.dumps(request, ensure_ascii=False).encode("utf-8")).decode()
        command = [sys.executable, str(ROOT / "scripts/mathmodel.py"), "--request-base64", "-"]
        run = subprocess.run(command, input=encoded, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(run.returncode, 0, run.stderr or run.stdout)
        result = json.loads(run.stdout)
        self.assertEqual(result["project"]["paperRequirements"]["text"], requirement)
        self.assertIn(requirement, result["agent_context"]["content"])
        oversized = subprocess.run(command, input="A" * (2 * 1024 * 1024 + 1), capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(oversized.returncode, 1)
        self.assertIn("2 MiB", json.loads(oversized.stdout)["error"])

    def test_damaged_import_cannot_be_reapproved_and_repair_restores_eligibility(self):
        (self.root / "题目分析报告.md").write_text("模型：最小化成本，目标x，约束x>=1。", encoding="utf-8")
        (self.root / "术语表格.md").write_text("|x|决策量|", encoding="utf-8")
        item = self.imported(b"original")
        self.call("gate-prepare", gate="M1")
        (self.root / item["path"]).write_bytes(b"changed")
        with self.assertRaisesRegex(WorkflowError, "Imported original"):
            self.call("gate-prepare", gate="M1")
        self.assertEqual(self.call("validate", phase="modeling")["overall"], "missing")
        (self.root / item["path"]).write_bytes(b"original")
        self.assertTrue(self.call("gate-prepare", gate="M1")["ok"])

    def test_imported_tmp_attachment_is_hashed_and_restored_by_checkpoints(self):
        item = self.call("input-import", kind="attachment", filename="measurements.tmp", content_base64=base64.b64encode(b"original data").decode())["input"]
        before = self.hashes()
        state = self.call("state")
        self.assertIn(item["path"], snapshot(self.root, state, "modeling", gate="M1")["files"])
        checkpoint = self.call("checkpoint-create")["checkpoint"]["checkpoint_id"]
        (self.root / item["path"]).write_bytes(b"damaged data")
        self.assertNotEqual(before["M1"], self.hashes()["M1"])
        preview = self.call("checkpoint-restore", checkpoint_id=checkpoint)
        self.call("checkpoint-restore", checkpoint_id=checkpoint, apply=True, expected_revision=preview["expected_revision"])
        self.assertEqual((self.root / item["path"]).read_bytes(), b"original data")
        current = self.call("context")
        self.assertFalse(current["inputs"][item["input_id"]]["stale"])
        self.assertEqual(current["agent_context"]["content"], (self.root / ".math-modeling/project-context.md").read_text(encoding="utf-8"))

    def test_legacy_requirement_text_is_migrated_without_losing_content_or_inventing_a_source(self):
        path = self.root / ".math-modeling/state.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        state["project"]["paperRequirements"] = "旧要求：保留全部推导，中文摘要。"
        path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        result = self.call("state")
        migrated = result["project"]["paperRequirements"]
        self.assertEqual(migrated["text"], state["project"]["paperRequirements"])
        self.assertEqual(migrated["source"], "旧版项目字段（来源未核实）")
        self.assertIn(migrated["text"], result["agent_context"]["content"])
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["project"]["paperRequirements"], migrated)
        with self.assertRaises(WorkflowError):
            self.call("configure", settings={"paper_requirements": "New requests must use an object"})
        with self.assertRaises(WorkflowError):
            validate_state(state)

    def test_context_routes_agents_to_the_actual_algorithm_and_figure_entry_points(self):
        context = self.call("context")["agent_context"]
        self.assertIn("每道子问题最多两个独立模型体系", context["content"])
        self.assertIn("先读 references/算法索引.md", context["content"])
        self.assertIn("tools/figure/INTEGRATIONS.zh-CN.md", context["content"])
        for reference in context["references"].values():
            self.assertTrue(reference["available"])
            self.assertTrue((Path(context["skill_root"]) / reference["path"]).is_file())
        core_only = self.root.parent / (self.root.name + "-runtime-only")
        core_only.mkdir()
        self.addCleanup(core_only.rmdir)
        reduced = dispatch({"action": "context", "project_root": str(self.root), "skill_root": str(core_only)})["agent_context"]
        self.assertFalse(any(reference["available"] for reference in reduced["references"].values()))
        self.assertIn("不宣称已加载", reduced["content"])

    def test_old_checkpoint_restore_preserves_new_inputs_in_the_recovery_checkpoint(self):
        baseline = self.call("checkpoint-create")["checkpoint"]["checkpoint_id"]
        # Represent a pre-upgrade checkpoint whose state legitimately used a free-text extension.
        base = self.root / ".math-modeling/checkpoints" / baseline
        saved = json.loads((base / "state.json").read_text(encoding="utf-8"))
        saved.pop("inputs", None)
        saved["project"].pop("graphicsTools", None)
        saved["project"]["paperRequirements"] = "旧快照中的论文要求"
        (base / "state.json").write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
        manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        manifest["state_sha256"] = digest(base / "state.json")
        (base / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        item = self.imported(b"new material after baseline")
        self.call("configure", settings={"paper_requirements": {"text": "新要求", "source": "用户面板填写"}, "graphics_tools": {"drawio": True}})
        preview = self.call("checkpoint-restore", checkpoint_id=baseline)
        self.assertIn({"path": item["path"], "operation": "remove"}, preview["changes"])
        restored = self.call("checkpoint-restore", checkpoint_id=baseline, apply=True, expected_revision=preview["expected_revision"])
        old = self.call("context")
        self.assertEqual(old["inputs"], {})
        self.assertEqual(old["project"]["paperRequirements"]["text"], "旧快照中的论文要求")
        self.assertFalse(old["project"]["graphicsTools"]["drawio"])
        recovery = restored["recovery_checkpoint"]
        recover_preview = self.call("checkpoint-restore", checkpoint_id=recovery)
        self.call("checkpoint-restore", checkpoint_id=recovery, apply=True, expected_revision=recover_preview["expected_revision"])
        recovered = self.call("context")
        self.assertEqual(recovered["inputs"][item["input_id"]]["sha256"], item["sha256"])
        self.assertEqual((self.root / item["path"]).read_bytes(), b"new material after baseline")
        self.assertEqual(recovered["project"]["paperRequirements"]["text"], "新要求")
        self.assertTrue(recovered["project"]["graphicsTools"]["drawio"])
        self.assertIn(item["path"], recovered["agent_context"]["content"])


if __name__ == "__main__":
    unittest.main()
