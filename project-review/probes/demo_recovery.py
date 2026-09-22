"""Exercise invalidation and recovery on the already independently reviewed demo."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mathmodel_runtime.engine import dispatch
from mathmodel_runtime.storage import digest

project = ROOT.parent / "mathmodel-upgrade-demo"
def call(action, **args):
    return dispatch({"action": action, "project_root": str(project), "skill_root": str(ROOT), **args})

before = call("complete")
assert before["done"], before["blockers"]
target = project / "results/solution.csv"
original = target.read_bytes()
original_hash = digest(target)
saved = call("checkpoint-create", name="independently-reviewed-two-page-demo")["checkpoint"]
try:
    target.write_text("x,y,objective\n2,2,11\n", encoding="utf-8")
    drift = call("state")
    assert not drift["completed"]
    rejected = call("complete")
    assert not rejected["done"] and rejected["blockers"]
    preview = call("checkpoint-restore", checkpoint_id=saved["checkpoint_id"])
    assert {"path": "results/solution.csv", "operation": "replace"} in preview["changes"]
    polled = call("state")
    assert polled["revision"] == preview["expected_revision"]
    restored = call("checkpoint-restore", checkpoint_id=saved["checkpoint_id"], apply=True,
                    expected_revision=preview["expected_revision"])
    assert target.read_bytes() == original and digest(target) == original_hash
    complete = call("complete")
    assert complete["done"] and not complete["blockers"]
    report = {"passed": True, "checkpoint_id": saved["checkpoint_id"], "preview": preview,
              "modified_result_rejected": not rejected["done"], "blockers_after_drift": rejected["blockers"],
              "readonly_poll_kept_revision": polled["revision"] == preview["expected_revision"],
              "recovery_checkpoint": restored["recovery_checkpoint"], "original_csv_sha256": original_hash,
              "restored_csv_sha256": digest(target), "restored_completed": complete["done"],
              "deliverableChecks": complete["deliverableChecks"],
              "gate_statuses": {key: value["status"] for key, value in complete["gates"].items()}}
    (ROOT / "project-review/logs/demo-recovery.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "project-review/logs/demo-restored-completion.json").write_text(json.dumps(complete, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
except Exception:
    target.write_bytes(original)
    call("state")
    raise
