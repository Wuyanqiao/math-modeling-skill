import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mathmodel_runtime.engine import dispatch
from mathmodel_runtime.storage import WorkflowError


class DeliveryProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name).resolve()
        self.call("init", scope="modeling")
        self.paper = self.project / "draft.md"
        self.paper.write_text("Verified checkpoint content", encoding="utf-8")
        self.saved = self.call("checkpoint-create", name="Checkpoint V1")["checkpoint"]
        self.saved_file = self.project / ".math-modeling/checkpoints" / self.saved["checkpoint_id"] / "files/draft.md"

    def call(self, action, **options):
        return dispatch({"action": action, "project_root": str(self.project), **options})

    def test_checkpoint_preserves_prior_version_through_later_edits(self):
        self.paper.write_text("Unverified optimization", encoding="utf-8")
        second = self.call("checkpoint-create", name="Checkpoint V2")["checkpoint"]
        self.assertNotEqual(second["checkpoint_id"], self.saved["checkpoint_id"])
        self.assertEqual(self.saved_file.read_text(encoding="utf-8"), "Verified checkpoint content")
        self.assertEqual(len(self.call("checkpoint-list")["checkpoints"]), 2)

    def test_restore_is_previewed_and_keeps_recovery_copy(self):
        self.paper.write_text("Unverified optimization", encoding="utf-8")
        extra = self.project / "new-user-note.md"
        extra.write_text("Keep recoverable", encoding="utf-8")
        preview = self.call("checkpoint-restore", checkpoint_id=self.saved["checkpoint_id"])
        self.assertTrue(preview["preview"])
        self.assertEqual(self.paper.read_text(encoding="utf-8"), "Unverified optimization")
        self.assertTrue(extra.exists())
        restored = self.call("checkpoint-restore", checkpoint_id=self.saved["checkpoint_id"],
                             apply=True, expected_revision=preview["expected_revision"])
        self.assertEqual(self.paper.read_text(encoding="utf-8"), "Verified checkpoint content")
        recovery = self.project / ".math-modeling/checkpoints" / restored["recovery_checkpoint"] / "files"
        self.assertEqual((recovery / "new-user-note.md").read_text(encoding="utf-8"), "Keep recoverable")
        self.assertEqual((recovery / "draft.md").read_text(encoding="utf-8"), "Unverified optimization")
        self.assertFalse(self.call("state")["completed"])

    def test_changed_revision_requires_new_restore_preview(self):
        self.paper.write_text("Changed", encoding="utf-8")
        preview = self.call("checkpoint-restore", checkpoint_id=self.saved["checkpoint_id"])
        self.call("log", event="new user work", detail="Revision changed")
        with self.assertRaises(WorkflowError) as error:
            self.call("checkpoint-restore", checkpoint_id=self.saved["checkpoint_id"],
                      apply=True, expected_revision=preview["expected_revision"])
        self.assertEqual(error.exception.code, "revision_conflict")
        self.assertEqual(self.paper.read_text(encoding="utf-8"), "Changed")

    def test_corrupted_snapshot_is_rejected_before_changing_working_files(self):
        self.saved_file.write_text("Corrupt content", encoding="utf-8")
        with self.assertRaises(WorkflowError) as error:
            self.call("checkpoint-restore", checkpoint_id=self.saved["checkpoint_id"])
        self.assertEqual(error.exception.code, "checkpoint_corrupt")
        self.assertEqual(self.paper.read_text(encoding="utf-8"), "Verified checkpoint content")


if __name__ == "__main__":
    unittest.main()
