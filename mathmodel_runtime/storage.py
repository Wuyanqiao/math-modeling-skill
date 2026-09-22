"""Project boundaries, content snapshots and atomic, serialized state updates."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time


META = ".math-modeling"
EXCLUDED = {META, ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}
PHASES = ("modeling", "programming", "paper")
GATES = {"M1": "modeling", "P1": "programming", "P2": "programming", "W1": "paper", "W2": "paper"}


class WorkflowError(ValueError):
    def __init__(self, message, code="invalid_request"):
        super().__init__(message)
        self.code = code


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def object_hash(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def inside(root, value, *, metadata=False):
    root = Path(root).resolve()
    raw = Path(value)
    target = (root / raw).resolve()
    if not target.is_relative_to(root) or target == root:
        raise WorkflowError("Path must be a file or directory within the authorized project", "path_boundary")
    if not metadata and META in target.relative_to(root).parts:
        raise WorkflowError("Project metadata cannot be used as an output artifact", "path_boundary")
    # Reject symlink traversal even if its resolved destination is still in project.
    lexical = root / raw if not raw.is_absolute() else raw
    for item in (lexical, *lexical.parents):
        if item == root:
            break
        if item.is_symlink():
            raise WorkflowError("Symlink paths are not supported for project artifacts", "path_boundary")
    return target


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".write-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def project_files(root):
    root = Path(root)
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not Path(directory, d).is_symlink())
        for name in sorted(files):
            path = Path(directory, name)
            if path.is_symlink() or name.endswith((".pyc", ".tmp")):
                continue
            yield path


def paper_only_path(state, relative, artifact=None):
    """Paper-only additions do not change already-reviewed scientific evidence."""
    artifact = artifact or {}
    program_paths = {item["path"] for run in state.get("runs", {}).values() if run.get("phase") == "programming" for group in ("code", "inputs", "outputs") for item in run.get(group, [])}
    if relative in program_paths:
        return False
    paper_paths = {item["path"] for run in state.get("runs", {}).values() if run.get("phase") == "paper" for group in ("code", "outputs") for item in run.get(group, [])}
    return (relative in paper_paths or artifact.get("role") == "render" or artifact.get("kind") in {"document", "pdf", "outline"}
            or Path(relative).suffix.lower() in {".tex", ".bib", ".cls", ".sty", ".docx", ".pdf"})


def snapshot(root, state, phase, gate=None, minimal_run_id=None):
    """Bind each gate to its evidence contract, preserving forward stage progress."""
    index = PHASES.index(phase)
    hashes = {}
    registered = {artifact["path"]: artifact for artifact in state.get("artifacts", {}).values()}
    config = {key: state["project"].get(key) for key in ("scope", "profile", "paperFormat", "subproblems", "rules")}
    minimal_paths = set()
    if gate == "P1":
        if minimal_run_id is None:
            minimal_run_id = state["gates"]["P1"].get("snapshot", {}).get("config", {}).get("minimal_run_id")
        run = state.get("runs", {}).get(minimal_run_id, {})
        minimal_paths = {item["path"] for group in ("inputs", "code", "outputs") for item in run.get(group, [])}
        config["minimal_run_id"] = minimal_run_id
        config["minimal_run"] = {key: run.get(key) for key in ("phase", "argv", "actual_argv", "executable", "environment", "seed", "parameters", "inputs", "code", "outputs", "status", "exit_code")}
    claim_paths = set()
    if gate == "W1":
        for claim in state.get("claims", {}).values():
            for aid in claim["artifact_ids"]:
                artifact = state["artifacts"].get(aid, {})
                if artifact.get("path"):
                    claim_paths.add(artifact["path"])
                run = state.get("runs", {}).get(artifact.get("run_id"), {})
                claim_paths.update(item["path"] for group in ("inputs", "code") for item in run.get(group, []))
    selected = set()
    for path in project_files(root):
        relative = path.relative_to(root).as_posix()
        suffix = path.suffix.lower()
        artifact = registered.get(relative, {})
        kind = artifact.get("kind")
        modeling = (relative.startswith(("data/", "inputs/")) or path.name in {"题目分析报告.md", "术语表格.md"} or kind in {"model", "terms"})
        source = suffix in {".py", ".m", ".ipynb", ".r", ".jl"} and not paper_only_path(state, relative, artifact)
        programming = modeling or (not paper_only_path(state, relative, artifact) and (source or relative.startswith(("results/", "figures/")) or kind in {"code", "table", "figure", "manifest"}))
        if gate == "P1":
            include = modeling or source or relative in minimal_paths
        elif gate == "W1":
            include = modeling or relative in claim_paths or kind == "outline" or path.name in {"论文大纲.md", "证据大纲.md"}
        else:
            include = modeling or (index >= 1 and programming) or index == 2
        if include:
            hashes[relative] = digest(path)
            selected.add(relative)
    if index >= 1 and gate != "P1":
        config["artifact_bindings"] = {artifact["artifact_id"]: {key: artifact.get(key) for key in ("path", "kind", "sha256", "question", "run_id", "role", "logical_id", "source_artifact_id")} for artifact in registered.values() if artifact["path"] in selected}
        referenced_runs = {artifact.get("run_id") for artifact in registered.values() if artifact["path"] in selected and artifact.get("run_id")}
        if gate == "P2":
            programming_runs = [run for run in state.get("runs", {}).values() if run.get("phase") == "programming"]
            if programming_runs:
                referenced_runs.add(programming_runs[-1]["run_id"])
        config["run_bindings"] = {run_id: {key: state["runs"][run_id].get(key) for key in ("phase", "argv", "actual_argv", "executable", "environment", "seed", "parameters", "inputs", "code", "outputs", "status", "exit_code")} for run_id in sorted(referenced_runs) if run_id in state.get("runs", {})}
    if index == 2:
        config["claims"] = state.get("claims", {})
    return {"files": hashes, "config": config, "hash": object_hash({"files": hashes, "config": config})}


class Store:
    def __init__(self, project_root, skill_root):
        self.root = Path(project_root).resolve()
        self.skill = Path(skill_root).resolve()
        if self.root == self.skill or self.root.is_relative_to(self.skill) or self.skill.is_relative_to(self.root):
            raise WorkflowError("PROJECT_ROOT and SKILL_ROOT must be separate, non-overlapping directories", "path_boundary")
        if not self.root.is_dir():
            raise WorkflowError("PROJECT_ROOT must be an existing directory", "project_missing")
        self.meta = inside(self.root, META, metadata=True)
        self.path = self.meta / "state.json"

    @contextmanager
    def locked(self):
        self.meta.mkdir(exist_ok=True)
        lock = self.meta / "state.lock"
        started = time.monotonic()
        while True:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump({"pid": os.getpid(), "created_at": now()}, stream)
                break
            except FileExistsError:
                if time.monotonic() - started > 5:
                    raise WorkflowError("Project is locked; inspect state.lock and its owning process before recovery", "project_locked")
                time.sleep(0.05)
        try:
            yield
        finally:
            lock.unlink(missing_ok=True)

    def load(self):
        if not self.path.exists():
            return None
        if self.path.is_symlink():
            raise WorkflowError("State file cannot be a symlink", "path_boundary")
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise WorkflowError("State is unreadable; restore a checkpoint or backup: " + str(exc), "state_corrupt") from exc
        if not isinstance(state, dict) or not isinstance(state.get("project"), dict):
            raise WorkflowError("State must contain a project object", "state_corrupt")
        stored = state["project"].get("projectRoot")
        if not stored or Path(stored).resolve() != self.root:
            raise WorkflowError("Stored project root differs from the authorized invocation", "path_boundary")
        if state.get("schema_version") == 2:
            from .schema import validate_state
            validate_state(state)
        return state

    def save(self, state):
        from .schema import validate_state
        validate_state(state)
        state["revision"] = state.get("revision", 0) + 1
        state["updated_at"] = now()
        atomic_json(self.path, state)
