"""Run a real demo request and persist its result for independent inspection."""
import base64
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mathmodel_runtime.engine import dispatch

request = json.loads(base64.b64decode(sys.argv[1]))
request.setdefault("project_root", str(ROOT.parent / "mathmodel-upgrade-demo"))
request.setdefault("skill_root", str(ROOT))
if "receipt_file" in request:
    request["receipt"] = json.loads((ROOT / request.pop("receipt_file")).read_text(encoding="utf-8-sig"))
result = dispatch(request)
destination = ROOT / "project-review/logs" / sys.argv[2]
destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
summary = {k: result[k] for k in ("ok", "error", "done", "overall", "blockers", "task_id", "snapshot_hash", "claim", "changes", "expected_revision") if k in result}
for kind, keys in {"run": ("run_id", "status", "exit_code", "error", "artifact_errors", "elapsed_seconds"),
                   "artifact": ("artifact_id", "path", "kind"), "checkpoint": ("checkpoint_id", "name")}.items():
    if kind in result:
        summary[kind] = {key: result[kind][key] for key in keys if key in result[kind]}
print(json.dumps(summary, ensure_ascii=False))
