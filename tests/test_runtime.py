import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mathmodel_runtime.engine import dispatch
from mathmodel_runtime.storage import WorkflowError, digest
from mathmodel_runtime.validation import inspect_file, validate_manifest


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="建模 runtime ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def call(self, action, **args):
        return dispatch({"action": action, "project_root": str(self.root), "skill_root": str(ROOT), **args})

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def modeling(self, scope="modeling"):
        self.call("init", scope=scope, profile="short", author_id="author")
        self.write("题目分析报告.md", "模型：对输入进行线性优化，约束 x <= 3，目标最大化 x。验证最优值为3。")
        self.write("术语表格.md", "|符号|含义|单位|\n|x|决策变量|单位量|")

    def review(self, gate):
        prepared = self.call("gate-prepare", gate=gate)
        files = prepared["request"]["snapshot"]["files"]
        receipt = {"task_id": prepared["task_id"], "snapshot_hash": prepared["snapshot_hash"],
                   "reviewer_id": "independent-reviewer", "review_source": "external", "status": "PASS",
                   "scope": "Deterministic test fixture; not a real scientific review", "evidence": [{"path": p, "sha256": h} for p, h in files.items()],
                   "findings": [], "rework": ""}
        return self.call("gate-record", gate=gate, receipt=receipt)

    def solver(self):
        self.write("solver.py", "from pathlib import Path\np=Path('results/table.csv');p.parent.mkdir(exist_ok=True);p.write_text('x,value\\n1,3\\n',encoding='utf-8')\n")
        return self.call("run", argv=[sys.executable, "solver.py"], code=["solver.py"], outputs=["results/table.csv"], seed=42)

    def test_scoped_completion_and_no_figure_quota(self):
        self.modeling()
        self.assertEqual(self.call("state")["required_gates"], ["M1"])
        self.review("M1")
        result = self.call("complete")
        self.assertTrue(result["done"])
        self.assertTrue(result["completed"])

    def test_gate_order_self_review_and_p0_rejected(self):
        self.modeling(scope="full")
        with self.assertRaisesRegex(WorkflowError, "Prerequisite"):
            self.call("gate-prepare", gate="W2")
        task = self.call("gate-prepare", gate="M1")
        evidence = [{"path": p, "sha256": h} for p, h in task["request"]["snapshot"]["files"].items()]
        receipt = {"task_id": task["task_id"], "snapshot_hash": task["snapshot_hash"], "reviewer_id": "author", "review_source": "subagent",
                   "status": "PASS", "scope": "review", "evidence": evidence, "findings": [], "rework": ""}
        with self.assertRaisesRegex(WorkflowError, "different"):
            self.call("gate-record", gate="M1", receipt=receipt)
        receipt["reviewer_id"] = "reviewer"
        receipt["findings"] = [{"level": "P0", "text": "wrong objective"}]
        with self.assertRaisesRegex(WorkflowError, "P0/P1"):
            self.call("gate-record", gate="M1", receipt=receipt)

    def test_empty_artifacts_and_forged_receipts_cannot_complete(self):
        self.call("init")
        for name in ("题目分析报告.md", "术语表格.md", "完整论文.docx", "figures/result_q1.png"):
            self.write(name, "")
        with self.assertRaises(WorkflowError):
            self.call("gate-record", gate="W2", receipt={"status": "PASS"})
        self.assertFalse(self.call("complete")["done"])
        with self.assertRaises(WorkflowError):
            self.call("artifact-add", path="完整论文.docx", kind="document")

    def test_changed_added_deleted_files_invalidate_and_clear_completion(self):
        for operation in ("change", "add", "delete"):
            with self.subTest(operation=operation):
                self.modeling()
                self.write("data/input.csv", "x\n1\n")
                self.review("M1")
                self.assertTrue(self.call("complete")["done"])
                if operation == "change":
                    self.write("data/input.csv", "x\n2\n")
                elif operation == "add":
                    self.write("data/new.csv", "x\n3\n")
                else:
                    (self.root / "data/input.csv").unlink()
                state = self.call("state")
                self.assertFalse(state["completed"])
                self.assertIsNone(state["completedAt"])
                self.assertEqual(state["gates"]["M1"]["status"], "invalidated")

    def test_stale_review_snapshot_is_rejected(self):
        self.modeling()
        task = self.call("gate-prepare", gate="M1")
        self.write("术语表格.md", "修改符号含义")
        with self.assertRaisesRegex(WorkflowError, "snapshot"):
            self.call("gate-record", gate="M1", receipt={"task_id": task["task_id"], "snapshot_hash": task["snapshot_hash"]})

    def test_real_run_manifest_and_claim_provenance(self):
        self.call("init", scope="programming", profile="short")
        result = self.solver()
        self.assertTrue(result["ok"])
        run = result["run"]
        self.assertEqual(run["exit_code"], 0)
        self.assertEqual(validate_manifest(self.root / "results/复现清单.json", self.root), [])
        aid = self.call("artifact-add", path="results/table.csv", kind="table", question="q1", run_id=run["run_id"])["artifact"]["artifact_id"]
        self.call("claim-add", text="The optimal value is 3", question="q1", artifact_ids=[aid])
        self.review("P1")
        self.review("P2")
        self.assertTrue(self.call("complete")["done"])
        self.write("solver.py", "raise RuntimeError('bad solver')\n")
        failed = self.call("run", argv=[sys.executable, "solver.py"], code=["solver.py"], outputs=["results/table.csv"])
        self.assertFalse(failed["ok"])
        self.assertEqual((self.root / "results/table.csv").read_text(), "x,value\n1,3\n")
        self.assertFalse(self.call("complete")["done"])

    def test_run_cannot_overwrite_input_and_isolates_declared_sources(self):
        self.call("init", scope="programming")
        original = self.write("data.txt", "original")
        self.write("solver.py", "from pathlib import Path\nPath('data.txt').write_text('changed');Path('result.txt').write_text('output')\n")
        result = self.call("run", argv=[sys.executable, "solver.py"], code=["solver.py"], inputs=["data.txt"], outputs=["result.txt"])
        self.assertFalse(result["ok"])
        self.assertEqual(original.read_text(), "original")
        self.assertFalse((self.root / "result.txt").exists())

    def test_run_timeout_is_recorded_without_publishing_outputs(self):
        self.call("init", scope="programming")
        self.write("solver.py", "import time\ntime.sleep(5)\n")
        result = self.call("run", argv=[sys.executable, "solver.py"], code=["solver.py"], outputs=["result.csv"], timeout=0.1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["run"]["exit_code"], 124)

    def test_concurrent_writes_keep_every_note(self):
        self.call("init")
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda i: self.call("log", event="concurrent", detail=i), range(12)))
        notes = [x["detail"] for x in self.call("state")["ledger"] if x["event"] == "concurrent"]
        self.assertEqual(sorted(notes), list(range(12)))

    def test_state_root_tampering_and_corruption_fail_closed(self):
        self.call("init")
        file = self.root / ".math-modeling/state.json"
        original = json.loads(file.read_text(encoding="utf-8"))
        original["project"]["projectRoot"] = str(self.root.parent)
        file.write_text(json.dumps(original), encoding="utf-8")
        with self.assertRaisesRegex(WorkflowError, "root"):
            self.call("log", event="bad")
        file.write_text("{corrupt", encoding="utf-8")
        with self.assertRaisesRegex(WorkflowError, "unreadable"):
            self.call("state")

    def test_legacy_state_backup_and_untrusted_pass_invalidated(self):
        self.modeling()
        original = self.call("state")
        original.pop("schema_version")
        original["version"] = 6
        original["completed"] = True
        original["phases"]["modeling"]["gateM1"] = {"status": "pass"}
        (self.root / ".math-modeling/state.json").write_text(json.dumps(original), encoding="utf-8")
        migrated = self.call("state")
        self.assertFalse(migrated["completed"])
        self.assertEqual(migrated["gates"]["M1"]["status"], "pending")
        self.assertTrue((self.root / ".math-modeling" / migrated["migration"]["backup"]).exists())

    def test_checkpoint_preview_revision_and_recovery_snapshot(self):
        self.modeling()
        checkpoint = self.call("checkpoint-create", name="baseline")["checkpoint"]["checkpoint_id"]
        original = (self.root / "题目分析报告.md").read_text(encoding="utf-8")
        self.write("题目分析报告.md", "changed")
        self.write("extra.txt", "remove after explicit restore")
        preview = self.call("checkpoint-restore", checkpoint_id=checkpoint)
        self.assertTrue(preview["preview"])
        self.assertEqual((self.root / "题目分析报告.md").read_text(), "changed")
        result = self.call("checkpoint-restore", checkpoint_id=checkpoint, apply=True, expected_revision=preview["expected_revision"])
        self.assertTrue(result["ok"])
        self.assertTrue(result["recovery_checkpoint"])
        self.assertEqual((self.root / "题目分析报告.md").read_text(encoding="utf-8"), original)
        self.assertFalse((self.root / "extra.txt").exists())
        preview = self.call("checkpoint-restore", checkpoint_id=checkpoint)
        self.call("log", event="concurrent change")
        with self.assertRaisesRegex(WorkflowError, "preview"):
            self.call("checkpoint-restore", checkpoint_id=checkpoint, apply=True, expected_revision=preview["expected_revision"])

    def test_todo_reset_and_string_collaboration(self):
        state = self.call("init", optional_collab="literature,prototype")
        self.assertTrue(state["project"]["optionalCollab"]["literature"])
        self.call("todo", operation="check", index=0)
        self.assertEqual(self.call("todo", operation="reset")["done"], 0)

    def test_registered_artifact_preview_cannot_escape_project(self):
        self.call("init")
        self.write("data.txt", "hello")
        artifact = self.call("artifact-add", path="data.txt", kind="other")["artifact"]
        self.assertEqual(self.call("artifact-read", artifact_id=artifact["artifact_id"])["content"], "hello")
        with self.assertRaises(WorkflowError):
            self.call("artifact-read", path="../outside.txt")
        with self.assertRaises(WorkflowError):
            self.call("artifact-add", path="data.txt", kind="figure")

    def test_cli_base64_json_handles_unicode_and_spaces(self):
        request = {"action": "init", "project_root": str(self.root), "scope": "modeling", "title": "中文 ' quotes $() ` text"}
        encoded = base64.b64encode(json.dumps(request).encode()).decode()
        result = subprocess.run([sys.executable, str(ROOT / "scripts/mathmodel.py"), "--request-base64", encoded], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["project"]["title"], request["title"])


if __name__ == "__main__":
    unittest.main()
