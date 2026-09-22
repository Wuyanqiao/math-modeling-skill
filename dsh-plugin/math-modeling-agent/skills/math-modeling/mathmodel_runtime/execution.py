"""Isolated declared-file execution with serialized, rollback-safe publication."""
import json
import os
from pathlib import Path
import shlex
import signal
import shutil
import subprocess
import time

from .storage import WorkflowError, atomic_json, digest, inside, now
from .validation import inspect_file

KINDS = {".py": "code", ".m": "code", ".csv": "table", ".tsv": "table", ".xlsx": "table", ".png": "figure", ".svg": "figure", ".jpg": "figure", ".docx": "document", ".pdf": "pdf"}


def reproduce_command(argv, *, platform=None):
    """Quote the canonical argument vector for the host's documented shell."""
    if (platform or os.name) == "nt":
        return "powershell", "& " + " ".join("'" + part.replace("'", "''") + "'" for part in argv)
    return "posix", shlex.join(argv)


def probe_environment(executable, cwd, *, timeout=10):
    """Inspect the executed interpreter/tool without collecting environment values."""
    is_python = Path(executable).stem.lower().startswith(("python", "pypy"))
    probe = (
        "import importlib.metadata, json, sys; "
        "print(json.dumps({'version': sys.version.split()[0], 'version_detail': sys.version, "
        "'observed_executable': sys.executable, 'dependencies': "
        "dict(sorted((d.metadata['Name'], d.version) for d in importlib.metadata.distributions() if d.metadata['Name']))}))"
    )
    argv = [executable, "-c", probe] if is_python else [executable, "--version"]
    result = {"name": "python" if is_python else Path(executable).stem, "version": "unknown", "dependencies": {},
              "executable": executable, "probe_argv": argv, "probe_status": "failed",
              "dependency_scope": "installed-distributions" if is_python else "not-applicable"}
    try:
        response = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=timeout, check=True, shell=False)
        if is_python:
            observed = json.loads(response.stdout)
            if not isinstance(observed, dict) or not isinstance(observed.get("version"), str) or not observed["version"].strip():
                raise ValueError("Python probe returned no version")
            dependencies = observed.get("dependencies")
            if not isinstance(dependencies, dict) or any(not isinstance(k, str) or not k or not isinstance(v, str) or not v for k, v in dependencies.items()):
                raise ValueError("Python probe returned invalid dependency versions")
            result.update(observed)
        else:
            lines = (response.stdout or response.stderr).strip().splitlines()
            if not lines:
                raise ValueError("Tool version probe returned no version")
            result["version"] = lines[0][:500]
        result["probe_status"] = "ok"
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        # Never publish stderr: tools may include environment values or credentials.
        result["probe_error"] = type(exc).__name__
    return result


def capture(root, paths, *, required=True):
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
        raise WorkflowError("inputs, code and outputs must be arrays of project paths")
    result = []
    seen = set()
    for raw in paths:
        path = inside(root, raw)
        relative = path.relative_to(root).as_posix()
        if relative in seen:
            raise WorkflowError("Duplicate declared path: " + relative)
        seen.add(relative)
        if not path.is_file():
            if required:
                raise WorkflowError("Required file is missing: " + relative)
            continue
        result.append({"path": relative, "sha256": digest(path), "bytes": path.stat().st_size})
    return result


def hashes(records):
    return {item["path"]: item["sha256"] for item in records}


def publish(store, workspace, output_records, backup_root):
    backups = {}
    touched = []
    try:
        for item in output_records:
            relative = item["path"]
            target = inside(store.root, relative)
            if target.exists():
                if not target.is_file():
                    raise WorkflowError("Output destination is not a file: " + relative)
                backup = backup_root / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
                backups[relative] = backup
            else:
                backups[relative] = None
        for item in output_records:
            relative = item["path"]
            source = inside(workspace, relative)
            target = inside(store.root, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".publish.tmp")
            try:
                shutil.copy2(source, temporary)
                if digest(temporary) != item["sha256"]:
                    raise WorkflowError("Output changed during publication: " + relative, "output_race")
                touched.append(relative)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        if hashes(capture(store.root, [item["path"] for item in output_records])) != hashes(output_records):
            raise WorkflowError("Published output changed concurrently", "output_race")
    except (OSError, WorkflowError) as original:
        failures = []
        for relative in reversed(touched):
            target = inside(store.root, relative)
            try:
                if backups[relative] is None:
                    target.unlink(missing_ok=True)
                else:
                    shutil.copy2(backups[relative], target)
            except OSError as exc:
                failures.append(f"{relative}: {exc}")
        if failures:
            raise WorkflowError("Output publication and rollback failed; recovery copies at " + str(backup_root) + ": " + "; ".join(failures), "output_rollback_failed") from original
        raise


def run_action(store, args):
    from .engine import artifact_add, event, identifier, invalidate, migrate, projection
    argv = args.get("argv")
    if not isinstance(argv, list) or not argv or any(not isinstance(argument, str) or "\0" in argument for argument in argv):
        raise WorkflowError("argv must be a nonempty string array; shell command strings are not accepted")
    timeout = args.get("timeout", 120)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 86400:
        raise WorkflowError("timeout must be between 0 and 86400 seconds")
    seed, parameters = args.get("seed", 0), args.get("parameters", {})
    if isinstance(seed, bool) or not isinstance(seed, int) or not isinstance(parameters, dict):
        raise WorkflowError("seed must be an integer and parameters an object")
    inputs, code = capture(store.root, args.get("inputs", [])), capture(store.root, args.get("code", []))
    if not code:
        raise WorkflowError("Record at least one solver/build source file in code")
    outputs_arg = args.get("outputs", [])
    if not isinstance(outputs_arg, list) or not outputs_arg or any(not isinstance(path, str) for path in outputs_arg):
        raise WorkflowError("Declare outputs as a nonempty array of project paths")
    output_paths = [inside(store.root, path).relative_to(store.root).as_posix() for path in outputs_arg]
    if len(set(output_paths)) != len(output_paths):
        raise WorkflowError("Output paths must be distinct")
    if set(hashes(inputs + code)) & set(output_paths):
        raise WorkflowError("Inputs and source files cannot also be outputs")
    sources = list({item["path"]: item for item in inputs + code}.values())
    with store.locked():
        state = store.load()
        if state is None:
            raise WorkflowError("Initialize the project before execution")
        state = migrate(store, state)
        if any(run.get("status") == "running" for run in state["runs"].values()):
            raise WorkflowError("Another run is active in this project; wait for it to finish", "run_active")
        phase = args.get("phase", "programming")
        if phase not in {"programming", "paper"} or state["project"]["scope"] not in {"full", phase}:
            raise WorkflowError("Execution phase must be programming or paper within the project scope")
        previous_outputs = capture(store.root, output_paths, required=False)
        run_id = identifier("run")
        run = {"run_id": run_id, "phase": phase, "argv": argv, "cwd": str(store.root), "seed": seed, "parameters": parameters,
               "inputs": inputs, "code": code, "outputs": [], "declared_outputs": output_paths, "started_at": now(),
               "finished_at": None, "exit_code": None, "status": "running", "timeout": timeout, "owner_pid": os.getpid()}
        state["runs"][run_id] = run
        state["completed"], state["completedAt"] = False, None
        event(state, "run_started", {"run_id": run_id, "argv": argv})
        projection(state)
        store.save(state)
    run_dir = store.meta / "runs" / run_id
    workspace = run_dir / "workspace"
    started = time.monotonic()
    staged_outputs = []
    process = None
    try:
        run_dir = inside(store.root, ".math-modeling/runs/" + run_id, metadata=True)
        workspace.mkdir(parents=True)
        for item in sources:
            copied = workspace / item["path"]
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(inside(store.root, item["path"]), copied)
            if digest(copied) != item["sha256"]:
                raise WorkflowError("Source changed before execution: " + item["path"], "source_changed")
        actual_argv = list(argv)
        declared = {item["path"] for item in sources} | set(output_paths)
        for index, argument in enumerate(actual_argv[1:], 1):
            if Path(argument).is_absolute():
                for relative in declared:
                    if Path(argument).resolve() == inside(store.root, relative):
                        actual_argv[index] = str(workspace / relative)
                        break
        command = actual_argv[0]
        executable = str(workspace / command) if not Path(command).is_absolute() and ("/" in command or "\\" in command) else shutil.which(command)
        if not executable:
            raise WorkflowError("Executable was not found: " + command, "executable_missing")
        actual_argv[0] = os.path.abspath(executable)
        run.update(actual_argv=actual_argv, executable=actual_argv[0], resolved_executable=str(Path(actual_argv[0]).resolve()), execution_cwd=str(workspace))
        run["environment"] = probe_environment(actual_argv[0], run_dir)
        stdout_path, stderr_path = run_dir / "stdout.log", run_dir / "stderr.log"
        run.update(stdout=str(stdout_path.relative_to(store.root)), stderr=str(stderr_path.relative_to(store.root)))
        with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
            environment = dict(os.environ, PYTHONUTF8="1", MATHMODELING_RUN_ID=run_id, MATHMODELING_SEED=str(seed))
            flags = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
            process = subprocess.Popen(actual_argv, cwd=workspace, stdout=out, stderr=err, env=environment, shell=False, **flags)
            try:
                exit_code = process.wait(timeout=timeout)
                run.update(exit_code=exit_code, status="succeeded" if exit_code == 0 else "failed")
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
                run.update(exit_code=124, status="timeout")
        if run["status"] == "succeeded":
            current_sources = capture(store.root, [item["path"] for item in sources], required=False)
            copied_sources = capture(workspace, [item["path"] for item in sources], required=False)
            run["source_drift"] = hashes(sources) != hashes(current_sources) or hashes(sources) != hashes(copied_sources)
            if run["source_drift"]:
                run["status"] = "source_changed"
            else:
                staged_outputs = capture(workspace, output_paths, required=False)
                if len(staged_outputs) != len(output_paths):
                    run["status"] = "invalid_outputs"
                for output in staged_outputs:
                    inspected = inspect_file(workspace, output["path"], KINDS.get(Path(output["path"]).suffix.lower(), "other"))
                    if not inspected["ok"]:
                        run.setdefault("artifact_errors", []).append({"path": output["path"], "error": "; ".join(inspected["errors"])})
                        run["status"] = "invalid_outputs"
    except (OSError, WorkflowError, subprocess.SubprocessError) as exc:
        run.update(status="source_changed" if getattr(exc, "code", "") == "source_changed" else "failed", exit_code=run["exit_code"] if run["exit_code"] is not None else 127, error=str(exc))
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
    run.update(finished_at=now(), elapsed_seconds=round(time.monotonic() - started, 6))
    with store.locked():
        state = migrate(store, store.load())
        if run["status"] == "succeeded":
            try:
                if hashes(capture(store.root, [item["path"] for item in sources], required=False)) != hashes(sources):
                    raise WorkflowError("Sources changed before output publication", "source_changed")
                if hashes(capture(store.root, output_paths, required=False)) != hashes(previous_outputs):
                    raise WorkflowError("Outputs changed during execution; newer files were preserved", "output_race")
                publish(store, workspace, staged_outputs, run_dir / "publication-backup")
                run["outputs"] = capture(store.root, output_paths)
            except (OSError, WorkflowError) as exc:
                run.update(status="source_changed" if getattr(exc, "code", "") == "source_changed" else "failed", error=str(exc), outputs=[])
        state["runs"][run_id] = run
        if run["status"] == "succeeded":
            for output in run["outputs"]:
                try:
                    artifact_add(store, state, {"path": output["path"], "kind": KINDS.get(Path(output["path"]).suffix.lower(), "other"), "run_id": run_id})
                except WorkflowError as exc:
                    run.setdefault("artifact_errors", []).append({"path": output["path"], "error": str(exc)})
            replay_argv = [run["executable"], *argv[1:]]
            replay_shell, replay_command = reproduce_command(replay_argv)
            manifest = {"schema_version": 1, "created_at_utc": now(), "random_seed": seed, "input_files": inputs,
                        "runtime": run["environment"], "argv": replay_argv, "shell": replay_shell,
                        "key_parameters": parameters, "reproduce_command": replay_command, "run_id": run_id, "code_files": code, "output_files": run["outputs"]}
            if phase == "programming":
                try:
                    atomic_json(inside(store.root, "results/复现清单.json"), manifest)
                except (OSError, WorkflowError) as exc:
                    run.update(status="failed", error="Could not publish reproduction manifest: " + str(exc))
        event(state, "run_finished", {"run_id": run_id, "status": run["status"], "exit_code": run["exit_code"]})
        invalidate(store, state)
        projection(state)
        store.save(state)
        atomic_json(run_dir / "run.json", run)
    return {"ok": run["status"] == "succeeded" and not run.get("artifact_errors") and run.get("environment", {}).get("probe_status") == "ok", "run": run, "revision": state["revision"],
            "notice": "Declared files ran in an isolated copy; this is not an OS sandbox. Independent review must assess scientific correctness."}
