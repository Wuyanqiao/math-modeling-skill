from concurrent.futures import ThreadPoolExecutor
import json
import importlib.util
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mathmodel_runtime import checkpoints, execution
from mathmodel_runtime.engine import dispatch
from mathmodel_runtime.storage import WorkflowError
from mathmodel_runtime.validation import inspect_file


class RuntimeEdgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="runtime 边界 ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def call(self, action, **arguments):
        return dispatch({"action": action, "project_root": str(self.root), "skill_root": str(ROOT), **arguments})

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        return path

    def modeling(self):
        self.call("init", scope="modeling", profile="short", author_id="author")
        self.write("题目分析报告.md", "目标最小化成本，明确变量约束与验证方式。")
        self.write("术语表格.md", "x 为决策变量，单位无量纲。")

    def receipt(self):
        task = self.call("gate-prepare", gate="M1")
        return {"task_id": task["task_id"], "reviewer_id": "reviewer", "review_source": "external", "snapshot_hash": task["snapshot_hash"],
                "status": "PASS", "scope": "Regression fixture, not a scientific review", "findings": [], "rework": "",
                "evidence": [{"path": path, "sha256": sha} for path, sha in task["request"]["snapshot"]["files"].items()]}

    def modify_state(self, update):
        path = self.root / ".math-modeling/state.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        update(state)
        path.write_text(json.dumps(state), encoding="utf-8")

    def solver(self, delay=0, outputs=("a.csv",)):
        self.call("init", scope="programming", profile="short")
        source = "from pathlib import Path\nimport time\ntime.sleep(" + str(delay) + ")\n"
        source += "\n".join(f"Path({name!r}).write_text('x,y\\n1,2\\n')" for name in outputs)
        self.write("solver.py", source)
        return {"argv": [sys.executable, "solver.py"], "code": ["solver.py"], "outputs": list(outputs)}

    def wait_running(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if any(run["status"] == "running" for run in self.call("state")["runs"].values()):
                return
            time.sleep(0.01)
        self.fail("Execution did not enter running state")

    def test_unknown_scope_cannot_remove_all_completion_requirements(self):
        self.modeling()
        self.modify_state(lambda state: state["project"].update(scope="nothing"))
        with self.assertRaises(WorkflowError) as caught:
            self.call("complete")
        self.assertEqual(caught.exception.code, "schema_validation")

    def test_project_cannot_contain_its_skill_installation(self):
        installed = self.root / "installed-skill"
        installed.mkdir()
        with self.assertRaisesRegex(WorkflowError, "non-overlapping"):
            dispatch({"action": "init", "project_root": str(self.root), "skill_root": str(installed)})

    def test_boolean_revision_is_not_an_integer_revision(self):
        self.modeling()
        self.modify_state(lambda state: state.update(revision=True))
        with self.assertRaises(WorkflowError):
            self.call("state")

    def test_pending_gates_clear_an_incorrect_completed_flag_on_state_read(self):
        self.modeling()
        self.modify_state(lambda state: state.update(completed=True, completedAt="forged"))
        state = self.call("state")
        self.assertFalse(state["completed"])
        self.assertIsNone(state["completedAt"])

    def test_pass_gate_requires_its_recorded_review_task(self):
        self.modeling()
        self.call("gate-record", gate="M1", receipt=self.receipt())
        self.modify_state(lambda state: state["review_tasks"].clear())
        with self.assertRaisesRegex(WorkflowError, "recorded review"):
            self.call("complete")

    def test_receipt_schema_requires_rework_field(self):
        self.modeling()
        receipt = self.receipt()
        receipt.pop("rework")
        with self.assertRaisesRegex(WorkflowError, "rework"):
            self.call("gate-record", gate="M1", receipt=receipt)

    def test_whitespace_does_not_turn_the_author_into_an_independent_reviewer(self):
        self.modeling()
        receipt = self.receipt()
        receipt["reviewer_id"] = " author "
        with self.assertRaisesRegex(WorkflowError, "different"):
            self.call("gate-record", gate="M1", receipt=receipt)

    def test_restore_preview_is_invalidated_by_external_file_edits(self):
        self.modeling()
        checkpoint = self.call("checkpoint-create")["checkpoint"]["checkpoint_id"]
        preview = self.call("checkpoint-restore", checkpoint_id=checkpoint)
        self.write("new-work.txt", "work created after preview")
        with self.assertRaisesRegex(WorkflowError, "preview"):
            self.call("checkpoint-restore", checkpoint_id=checkpoint, apply=True, expected_revision=preview["expected_revision"])
        self.assertEqual((self.root / "new-work.txt").read_text(), "work created after preview")

    def test_read_only_state_polling_does_not_expire_restore_preview(self):
        self.modeling()
        checkpoint = self.call("checkpoint-create")["checkpoint"]["checkpoint_id"]
        self.write("题目分析报告.md", "new model")
        preview = self.call("checkpoint-restore", checkpoint_id=checkpoint)
        for _ in range(3):
            self.assertEqual(self.call("state")["revision"], preview["expected_revision"])
            self.assertEqual(self.call("checkpoint-list")["revision"], preview["expected_revision"])
        restored = self.call("checkpoint-restore", checkpoint_id=checkpoint, apply=True, expected_revision=preview["expected_revision"])
        self.assertTrue(restored["ok"])

    def test_failed_restore_rolls_back_all_original_files(self):
        self.modeling()
        checkpoint = self.call("checkpoint-create")["checkpoint"]["checkpoint_id"]
        self.write("题目分析报告.md", "new model")
        self.write("术语表格.md", "new notation")
        self.write("extra.txt", "keep me")
        preview = self.call("checkpoint-restore", checkpoint_id=checkpoint)
        original_replace = checkpoints.os.replace
        writes = 0
        def fail_second_restore(source, target):
            nonlocal writes
            if ".restore-" in Path(source).name:
                writes += 1
                if writes == 2:
                    raise OSError("injected restore I/O failure")
            return original_replace(source, target)
        with patch.object(checkpoints.os, "replace", side_effect=fail_second_restore):
            with self.assertRaisesRegex(WorkflowError, "original files restored"):
                self.call("checkpoint-restore", checkpoint_id=checkpoint, apply=True, expected_revision=preview["expected_revision"])
        self.assertEqual((self.root / "题目分析报告.md").read_text(), "new model")
        self.assertEqual((self.root / "术语表格.md").read_text(), "new notation")
        self.assertEqual((self.root / "extra.txt").read_text(), "keep me")
        self.assertTrue(self.call("state")["ledger"][-1]["detail"]["rollback_succeeded"])

    def test_checkpoint_state_tampering_is_detected(self):
        self.modeling()
        checkpoint = self.call("checkpoint-create")["checkpoint"]["checkpoint_id"]
        path = self.root / ".math-modeling/checkpoints" / checkpoint / "state.json"
        path.write_text("{}")
        with self.assertRaisesRegex(WorkflowError, "state hash"):
            self.call("checkpoint-restore", checkpoint_id=checkpoint)

    def test_restore_handles_file_directory_shape_changes(self):
        self.modeling()
        path = self.write("shape", "original file")
        checkpoint = self.call("checkpoint-create")["checkpoint"]["checkpoint_id"]
        path.unlink()
        self.write("shape/child.txt", "new directory")
        preview = self.call("checkpoint-restore", checkpoint_id=checkpoint)
        self.call("checkpoint-restore", checkpoint_id=checkpoint, apply=True, expected_revision=preview["expected_revision"])
        self.assertEqual(path.read_text(), "original file")

    def test_source_copy_failure_is_finalized_and_does_not_leave_running(self):
        arguments = self.solver()
        original_copy = execution.shutil.copy2
        def fail_workspace_copy(source, target, *args, **kwargs):
            if "workspace" in Path(target).parts:
                raise OSError("injected staging failure")
            return original_copy(source, target, *args, **kwargs)
        with patch.object(execution.shutil, "copy2", side_effect=fail_workspace_copy):
            result = self.call("run", **arguments)
        self.assertFalse(result["ok"])
        self.assertEqual(result["run"]["status"], "failed")
        self.assertTrue(self.call("run", **arguments)["ok"])

    def test_invalid_output_does_not_replace_a_valid_existing_table(self):
        arguments = self.solver()
        self.write("a.csv", "old,value\n1,99\n")
        self.write("solver.py", "from pathlib import Path\nPath('a.csv').write_text('header-only')\n")
        result = self.call("run", **arguments)
        self.assertFalse(result["ok"])
        self.assertEqual((self.root / "a.csv").read_text(), "old,value\n1,99\n")

    def test_publication_failure_restores_already_replaced_outputs(self):
        arguments = self.solver(outputs=("a.csv", "b.csv"))
        self.write("a.csv", "old,value\n1,11\n")
        self.write("b.csv", "old,value\n1,22\n")
        original_replace = execution.os.replace
        def fail_second_output(source, target):
            if Path(target).name == "b.csv" and Path(source).name.endswith(".publish.tmp"):
                raise OSError("injected publication failure")
            return original_replace(source, target)
        with patch.object(execution.os, "replace", side_effect=fail_second_output):
            result = self.call("run", **arguments)
        self.assertFalse(result["ok"])
        self.assertEqual((self.root / "a.csv").read_text(), "old,value\n1,11\n")
        self.assertEqual((self.root / "b.csv").read_text(), "old,value\n1,22\n")
        self.assertEqual(result["run"]["outputs"], [])

    def test_concurrent_runs_are_rejected_and_external_output_changes_preserved(self):
        arguments = self.solver(delay=0.5)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.call, "run", **arguments)
            self.wait_running()
            with self.assertRaisesRegex(WorkflowError, "active"):
                self.call("run", **arguments)
            self.assertFalse(self.call("complete")["done"])
            self.write("a.csv", "manual,value\n1,77\n")
            result = future.result(timeout=10)
        self.assertFalse(result["ok"])
        self.assertEqual((self.root / "a.csv").read_text(), "manual,value\n1,77\n")
        self.assertIn("newer files were preserved", result["run"]["error"])

    def test_output_manifest_failure_is_not_left_running(self):
        arguments = self.solver()
        (self.root / "results/复现清单.json").mkdir(parents=True)
        result = self.call("run", **arguments)
        self.assertFalse(result["ok"])
        self.assertEqual(self.call("state")["runs"][result["run"]["run_id"]]["status"], "failed")

    def test_execution_records_actual_executable_and_copied_absolute_script(self):
        arguments = self.solver()
        arguments["argv"][1] = str(self.root / "solver.py")
        result = self.call("run", **arguments)
        self.assertTrue(result["ok"])
        run = result["run"]
        self.assertEqual(run["actual_argv"][0], run["executable"])
        self.assertTrue(Path(run["executable"]).is_absolute())
        self.assertIn("workspace", Path(run["actual_argv"][1]).parts)

    def test_run_log_read_is_bounded_and_ignores_tampered_state_log_paths(self):
        arguments = self.solver()
        self.write("solver.py", "from pathlib import Path\nprint('readable solver output')\nPath('a.csv').write_text('x,y\\n1,2\\n')\n")
        run_id = self.call("run", **arguments)["run"]["run_id"]
        self.write("unrelated.txt", "not a run log")
        self.modify_state(lambda state: state["runs"][run_id].update(stdout="unrelated.txt"))
        log = self.call("run-log-read", run_id=run_id, stream="stdout", max_bytes=8)
        self.assertEqual(log["content"], "readable")
        self.assertTrue(log["truncated"])
        self.assertIn(".math-modeling/runs/", log["path"])
        for bad in ({"run_id": "../unrelated"}, {"run_id": run_id, "stream": "../../unrelated"}, {"run_id": run_id, "max_bytes": 300000}):
            with self.assertRaises(WorkflowError):
                self.call("run-log-read", **bad)

    @unittest.skipUnless(importlib.util.find_spec("matplotlib"), "Matplotlib required for real SVG fixture")
    def test_real_matplotlib_svg_external_doctype_is_supported(self):
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import pyplot as plt
        figure, axes = plt.subplots()
        self.addCleanup(plt.close, figure)
        axes.plot([0, 1], [1, 2])
        path = self.root / "matplotlib.svg"
        figure.savefig(path)
        self.assertIn(b"<!DOCTYPE svg PUBLIC", path.read_bytes())
        self.assertTrue(inspect_file(self.root, path.name, "figure")["ok"])
        self.write("entity.svg", '<!DOCTYPE svg [<!ENTITY secret "expanded">]><svg xmlns="http://www.w3.org/2000/svg"><text>&secret;</text></svg>')
        self.assertFalse(inspect_file(self.root, "entity.svg", "figure")["ok"])
        (self.root / "entity-utf16.svg").write_bytes((self.root / "entity.svg").read_text().encode("utf-16"))
        self.assertFalse(inspect_file(self.root, "entity-utf16.svg", "figure")["ok"])
        self.write("script.svg", '<!DOCTYPE svg SYSTEM "https://example.invalid/svg.dtd"><svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><rect width="1" height="1"/></svg>')
        self.assertFalse(inspect_file(self.root, "script.svg", "figure")["ok"])


class GateProgressionTests(unittest.TestCase):
    """Observable gate progression with deterministic fixture data, not scientific review."""
    setUp = RuntimeEdgeTests.setUp
    call = RuntimeEdgeTests.call
    write = RuntimeEdgeTests.write
    def review_gate(self, gate):
        task = self.call("gate-prepare", gate=gate)
        receipt = {"task_id": task["task_id"], "reviewer_id": "external-fixture", "review_source": "external", "snapshot_hash": task["snapshot_hash"],
                   "status": "PASS", "scope": "Regression fixture; no scientific review claim", "findings": [], "rework": "",
                   "evidence": [{"path": path, "sha256": sha} for path, sha in task["request"]["snapshot"]["files"].items()]}
        self.call("gate-record", gate=gate, receipt=receipt)

    def programming_gates(self):
        self.call("init", scope="full", profile="short")
        self.write("题目分析报告.md", "目标最小化成本，明确变量约束与验证方式。")
        self.write("术语表格.md", "x 为决策变量，无量纲。")
        self.review_gate("M1")
        self.write("solver.py", "from pathlib import Path\nimport sys\nPath('results').mkdir(exist_ok=True)\nPath('results/minimal.csv').write_text('x,value\\n1,3\\n')\nif 'full' in sys.argv:\n Path('results/full.csv').write_text('x,value\\n1,3\\n2,4\\n')\n")
        self.call("run", argv=[sys.executable, "solver.py"], code=["solver.py"], outputs=["results/minimal.csv"])
        self.review_gate("P1")
        self.call("run", argv=[sys.executable, "solver.py", "full"], code=["solver.py"], outputs=["results/minimal.csv", "results/full.csv"])
        artifact = self.call("artifact-add", path="results/full.csv", kind="table", question="q1")["artifact"]
        self.assertEqual(self.call("state")["gates"]["P1"]["status"], "pass")
        self.review_gate("P2")
        return artifact

    def test_full_results_and_new_manifest_preserve_minimal_run_gate(self):
        self.programming_gates()
        state = self.call("state")
        self.assertEqual([state["gates"][gate]["status"] for gate in ("M1", "P1", "P2")], ["pass"] * 3)
        self.write("results/minimal.csv", "x,value\n1,999\n")
        state = self.call("state")
        self.assertEqual(state["gates"]["M1"]["status"], "pass")
        self.assertEqual(state["gates"]["P1"]["status"], "invalidated")
        self.assertEqual(state["gates"]["P2"]["status"], "invalidated")

    def test_natural_five_gate_flow_preserves_w1_during_paper_and_render_creation(self):
        artifact = self.programming_gates()
        self.call("phase", phase="paper")
        self.call("claim-add", claim_id="result", question="q1", text="The minimum fixture value is 3", artifact_ids=[artifact["artifact_id"]])
        self.write("论文大纲.md", "摘要、模型与数值证据、结论。")
        self.call("artifact-add", path="论文大纲.md", kind="outline")
        self.review_gate("W1")
        self.write("main.tex", r"\documentclass{article}\begin{document}Fixture\end{document}")
        self.call("artifact-add", path="main.tex", kind="code")
        self.write("build_paper.py", "from pathlib import Path\nimport zipfile\nwith zipfile.ZipFile('完整论文.docx','w') as z:\n z.writestr('[Content_Types].xml','<Types/>')\n z.writestr('word/document.xml','<w:document xmlns:w=\"urn:fixture\"><w:t>Fixture model and result 3.</w:t></w:document>')\nPath('figures').mkdir(exist_ok=True)\nPath('figures/render.svg').write_text('<svg xmlns=\"http://www.w3.org/2000/svg\"><rect width=\"10\" height=\"10\"/></svg>')\n")
        paper = self.call("run", phase="paper", argv=[sys.executable, "build_paper.py"], code=["build_paper.py"], outputs=["完整论文.docx", "figures/render.svg"])
        self.assertTrue(paper["ok"], paper)
        document = self.call("artifact-add", path="完整论文.docx", kind="document")["artifact"]
        self.call("artifact-add", path="figures/render.svg", kind="figure", role="render", source_artifact_id=document["artifact_id"])
        state = self.call("state")
        self.assertEqual([state["gates"][gate]["status"] for gate in ("M1", "P1", "P2", "W1")], ["pass"] * 4)
        self.review_gate("W2")
        self.assertTrue(self.call("complete")["done"])
        self.call("claim-add", claim_id="result", question="q1", text="Changed claimed value", artifact_ids=[artifact["artifact_id"]])
        state = self.call("state")
        self.assertEqual(state["gates"]["P2"]["status"], "pass")
        self.assertEqual(state["gates"]["W1"]["status"], "invalidated")
        self.assertEqual(state["gates"]["W2"]["status"], "invalidated")


if __name__ == "__main__":
    unittest.main()
