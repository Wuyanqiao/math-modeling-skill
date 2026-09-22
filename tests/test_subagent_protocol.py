import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mathmodel_runtime.engine import dispatch
from mathmodel_runtime.storage import WorkflowError


class SubagentProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name).resolve()
        self.call("init", scope="modeling", author_id="author", profile="short")
        self.model = self.project / "题目分析报告.md"
        self.model.write_text("# Model\nMinimize x squared; verify x=0 and nonnegative objective.", encoding="utf-8")
        (self.project / "术语表格.md").write_text("|符号|含义|单位|\n|x|决策变量|无量纲|", encoding="utf-8")

    def call(self, action, **options):
        return dispatch({"action": action, "project_root": str(self.project), **options})

    def receipt(self, prepared, **changes):
        receipt = {"task_id": prepared["task_id"], "snapshot_hash": prepared["snapshot_hash"],
                   "reviewer_id": "independent-reviewer", "review_source": "external",
                   "status": "PASS", "scope": "M1 model assumptions, units and known optimum",
                   "evidence": [{"path": self.model.name,
                                 "sha256": hashlib.sha256(self.model.read_bytes()).hexdigest()}],
                   "findings": [], "rework": ""}
        return {**receipt, **changes}

    def test_single_phase_does_not_require_other_phase_reviews(self):
        prepared = self.call("gate-prepare", gate="M1")
        self.call("gate-record", gate="M1", receipt=self.receipt(prepared))
        result = self.call("complete")
        self.assertTrue(result["done"])
        self.assertEqual(result["required_gates"], ["M1"])
        self.assertEqual(result["gates"]["M1"]["receipt"]["review_source"], "external")
        self.assertEqual(result["gates"]["M1"]["identity_assurance"], "declared")

    def test_author_self_review_is_rejected(self):
        prepared = self.call("gate-prepare", gate="M1")
        with self.assertRaises(WorkflowError) as error:
            self.call("gate-record", gate="M1", receipt=self.receipt(prepared, reviewer_id="author"))
        self.assertEqual(error.exception.code, "review_identity")
        self.assertEqual(self.call("state")["gates"]["M1"]["status"], "pending")

    def test_unresolved_major_finding_cannot_pass(self):
        prepared = self.call("gate-prepare", gate="M1")
        with self.assertRaises(WorkflowError) as error:
            self.call("gate-record", gate="M1", receipt=self.receipt(
                prepared, findings=[{"level": "P0", "text": "Objective does not answer question"}]))
        self.assertEqual(error.exception.code, "review_findings")

    def test_changed_model_rejects_stale_receipt(self):
        prepared = self.call("gate-prepare", gate="M1")
        receipt = self.receipt(prepared)
        self.model.write_text("A different model and optimum", encoding="utf-8")
        with self.assertRaises(WorkflowError) as error:
            self.call("gate-record", gate="M1", receipt=receipt)
        self.assertEqual(error.exception.code, "review_snapshot")

    def test_deleted_evidence_revokes_completion(self):
        prepared = self.call("gate-prepare", gate="M1")
        self.call("gate-record", gate="M1", receipt=self.receipt(prepared))
        self.assertTrue(self.call("complete")["done"])
        self.model.unlink()
        refreshed = self.call("state")
        self.assertEqual(refreshed["gates"]["M1"]["status"], "invalidated")
        self.assertFalse(refreshed["completed"])
        self.assertFalse(self.call("complete")["done"])

    def test_new_input_invalidates_current_review(self):
        prepared = self.call("gate-prepare", gate="M1")
        self.call("gate-record", gate="M1", receipt=self.receipt(prepared))
        (self.project / "data").mkdir()
        (self.project / "data/new.csv").write_text("value\n2\n", encoding="utf-8")
        self.assertEqual(self.call("state")["gates"]["M1"]["status"], "invalidated")

    def test_missing_review_cannot_be_reported_as_independent_completion(self):
        result = self.call("complete")
        self.assertFalse(result["done"])
        self.assertIn("Gate M1: pending", result["blockers"])
        self.assertEqual(result["deliverableChecks"]["modeling"], "ok")

    def test_full_workflow_cannot_skip_to_final_review(self):
        other = self.project / "other-task"
        other.mkdir()
        dispatch({"action": "init", "project_root": str(other), "scope": "full"})
        with self.assertRaises(WorkflowError) as error:
            dispatch({"action": "gate-prepare", "project_root": str(other), "gate": "W2"})
        self.assertEqual(error.exception.code, "gate_prerequisite")

    def test_cli_new_process_restores_shared_state(self):
        prepared = self.call("gate-prepare", gate="M1")
        self.call("gate-record", gate="M1", receipt=self.receipt(prepared, review_source="human"))
        process = subprocess.run([sys.executable, str(ROOT / "scripts/mathmodel.py"), "state",
                                  "--project-root", str(self.project)],
                                 capture_output=True, text=True, encoding="utf-8", check=True)
        state = json.loads(process.stdout)
        self.assertEqual(state["gates"]["M1"]["status"], "pass")
        self.assertEqual(state["gates"]["M1"]["receipt"]["review_source"], "human")
        self.assertEqual(state["project"]["profile"], "short")


if __name__ == "__main__":
    unittest.main()
