"""Immutable snapshots, content-bound previews and transactional checkpoint restoration."""
import json
import os
from pathlib import Path
import re
import shutil
import uuid

from .storage import WorkflowError, atomic_json, digest, inside, now, object_hash, project_files


def file_index(root):
    return {path.relative_to(root).as_posix(): digest(path) for path in project_files(root)}


def create(store, state, name):
    if any(run.get("status") == "running" for run in state["runs"].values()):
        raise WorkflowError("Cannot checkpoint while a recorded run is active", "run_active")
    identifier = "checkpoint_" + uuid.uuid4().hex[:16]
    base = inside(store.root, ".math-modeling/checkpoints/" + identifier, metadata=True)
    base.mkdir(parents=True, exist_ok=False)
    files = file_index(store.root)
    for relative, expected in files.items():
        source = inside(store.root, relative)
        target = base / "files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if digest(target) != expected:
            raise WorkflowError("File changed while checkpointing: " + relative, "snapshot_race")
    if file_index(store.root) != files:
        raise WorkflowError("Project file set changed while checkpointing", "snapshot_race")
    atomic_json(base / "state.json", state)
    record = {"checkpoint_id": identifier, "name": name or identifier, "created_at": now(),
              "source_revision": state["revision"], "completed_when_created": state["completed"],
              "files": files, "state_sha256": digest(base / "state.json")}
    atomic_json(base / "manifest.json", record)
    state["checkpoints"].append({key: value for key, value in record.items() if key != "files"})
    return record


def restore_files(root, base, saved):
    """Replace a checked file inventory, pruning only empty in-project directories."""
    for relative in set(file_index(root)) - set(saved):
        target = inside(root, relative)
        target.unlink()
        parent = target.parent
        while parent != root and parent.is_relative_to(root):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    for relative, expected in saved.items():
        target = inside(root, relative)
        source = inside(base / "files", relative)
        if not source.is_file() or digest(source) != expected:
            raise WorkflowError("Checkpoint source changed: " + relative, "checkpoint_corrupt")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".restore-" + uuid.uuid4().hex[:8] + ".tmp")
        try:
            shutil.copy2(source, temporary)
            if digest(temporary) != expected:
                raise WorkflowError("Checkpoint copy changed: " + relative, "checkpoint_corrupt")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    if file_index(root) != saved:
        raise WorkflowError("Restored files do not match checkpoint", "restore_race")


def checkpoint_action(store, state, action, args):
    from .engine import event, invalidate, migrate
    from .schema import validate_state
    if action == "checkpoint-create":
        record = create(store, state, args.get("name"))
        event(state, "checkpoint_created", {"checkpoint_id": record["checkpoint_id"]})
        return {"ok": True, "checkpoint": record}
    if action == "checkpoint-list":
        return {"ok": True, "checkpoints": state["checkpoints"]}
    if action != "checkpoint-restore":
        raise WorkflowError("Unknown checkpoint action")
    checkpoint_id = args.get("checkpoint_id", "")
    if not isinstance(checkpoint_id, str) or not re.fullmatch(r"checkpoint_[a-f0-9]{16}", checkpoint_id):
        raise WorkflowError("Invalid checkpoint identifier")
    if any(run.get("status") == "running" for run in state["runs"].values()):
        raise WorkflowError("Cannot restore while a recorded run is active", "run_active")
    base = inside(store.root, ".math-modeling/checkpoints/" + checkpoint_id, metadata=True)
    manifest_path = inside(base, "manifest.json", metadata=True)
    state_path = inside(base, "state.json", metadata=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("state_sha256") != digest(state_path):
        raise WorkflowError("Checkpoint state hash is missing or corrupt", "checkpoint_corrupt")
    restored = json.loads(state_path.read_text(encoding="utf-8"))
    validate_state(restored, allow_legacy_project=True)
    restored = migrate(store, restored)
    if manifest.get("checkpoint_id") != checkpoint_id or Path(restored["project"]["projectRoot"]).resolve() != store.root:
        raise WorkflowError("Checkpoint does not belong to this project")
    current = file_index(store.root)
    saved = manifest.get("files")
    if not isinstance(saved, dict):
        raise WorkflowError("Checkpoint inventory is invalid", "checkpoint_corrupt")
    for relative, expected in saved.items():
        inside(store.root, relative)
        source = inside(base / "files", relative)
        if not re.fullmatch(r"[a-f0-9]{64}", str(expected)) or not source.is_file() or digest(source) != expected:
            raise WorkflowError("Checkpoint content is missing or corrupt: " + relative, "checkpoint_corrupt")
    changes = [{"path": path, "operation": "add" if path not in current else "replace"} for path in saved if current.get(path) != saved[path]]
    changes += [{"path": path, "operation": "remove"} for path in current if path not in saved]
    preview = {"current_files": object_hash(current), "checkpoint_manifest": digest(manifest_path)}
    if not args.get("apply", False):
        state.setdefault("restore_previews", {})[checkpoint_id] = preview
        return {"ok": True, "preview": True, "checkpoint_id": checkpoint_id, "changes": changes,
                "expected_revision": state["revision"] + 1, "notice": "Apply requires the current preview, unchanged files and expected_revision. A recovery checkpoint is created first."}
    if args.get("expected_revision") != state["revision"] or state.get("restore_previews", {}).get(checkpoint_id) != preview:
        raise WorkflowError("Project or checkpoint changed since restore preview; preview again", "revision_conflict")
    recovery = create(store, state, "before-restore-" + checkpoint_id)
    try:
        restore_files(store.root, base, saved)
    except (OSError, WorkflowError) as exc:
        recovery_base = inside(store.root, ".math-modeling/checkpoints/" + recovery["checkpoint_id"], metadata=True)
        rollback_error = None
        try:
            restore_files(store.root, recovery_base, recovery["files"])
        except (OSError, WorkflowError) as rollback:
            rollback_error = str(rollback)
        state["completed"], state["completedAt"] = False, None
        event(state, "restore_failed", {"recovery_checkpoint": recovery["checkpoint_id"], "error": str(exc), "rollback_succeeded": rollback_error is None, "rollback_error": rollback_error})
        raise WorkflowError("Restore interrupted; " + ("original files restored" if rollback_error is None else "automatic rollback failed: " + rollback_error) + "; recovery checkpoint: " + recovery["checkpoint_id"], "restore_failed") from exc
    revision, checkpoints = state["revision"], state["checkpoints"]
    state.clear()
    state.update(restored)
    state["revision"], state["checkpoints"] = revision, checkpoints
    state.pop("restore_previews", None)
    state["completed"], state["completedAt"] = False, None
    invalidate(store, state)
    event(state, "checkpoint_restored", {"checkpoint_id": checkpoint_id, "recovery_checkpoint": recovery["checkpoint_id"]})
    return {"ok": True, "restored": checkpoint_id, "changes": changes, "recovery_checkpoint": recovery["checkpoint_id"],
            "notice": "Files restored; run complete to revalidate the deliverable."}
