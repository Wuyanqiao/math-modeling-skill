"""One-off final wheel verification; writes evidence outside tracked source."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "project-review/logs/upgrade-final-wheel.log"
SUMMARY = ROOT / "project-review/logs/upgrade-final-wheel-summary.json"
lines = []
summary = {"version": "2.0.0", "status": "running", "checks": []}


def run(argv, cwd):
    result = subprocess.run([str(x) for x in argv], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {argv}\n{result.stdout}\n{result.stderr}")
    return result.stdout


try:
    output = run([sys.executable, "-m", "build", "--wheel", "--outdir", "dist/runtime"], ROOT)
    wheel = ROOT / "dist/runtime/mathmodel_workbench-2.0.0-py3-none-any.whl"
    assert wheel.is_file(), output
    summary.update(wheel=str(wheel), wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(), wheel_bytes=wheel.stat().st_size)
    lines.append("PASS build: " + wheel.name)
    with zipfile.ZipFile(wheel) as archive:
        resources = sorted(name for name in archive.namelist() if name.startswith("mathmodel_runtime/resources/"))
    expected = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / "mathmodel_runtime/resources").rglob("*.json"))
    assert resources == expected, resources
    summary["resources"] = resources
    lines.append(f"PASS wheel resources: {len(resources)} JSON files (5 schemas, 3 profiles)")
    with tempfile.TemporaryDirectory(prefix="mathmodel wheel 独立验证 ") as temporary:
        outside = Path(temporary).resolve()
        assert outside.is_relative_to(Path(tempfile.gettempdir()).resolve()) and not outside.is_relative_to(ROOT)
        environment = outside / "隔离环境"
        venv.EnvBuilder(with_pip=True, system_site_packages=False).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        config = (environment / "pyvenv.cfg").read_text(encoding="utf-8")
        assert "include-system-site-packages = false" in config
        install = run([python, "-I", "-m", "pip", "install", "--no-index", "--no-deps", wheel], outside)
        lines.append("PASS install: --no-index --no-deps into fresh system_site_packages=False venv")
        probe = r'''
import importlib.metadata, importlib.util, json, pathlib, sys
import mathmodel_runtime
from mathmodel_runtime.engine import load_profile
from mathmodel_runtime.schema import ROOT, validate_schema
from mathmodel_runtime.storage import WorkflowError
profiles = {name: load_profile(name) for name in ("short", "balanced", "competition")}
schemas = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in ROOT.glob("*.json")}
assert len(schemas) == 5 and len(profiles) == 3
try:
    validate_schema("state.schema.json", {})
except WorkflowError as exc:
    assert exc.code == "schema_validation"
else:
    raise AssertionError("Installed schema validator accepted missing state fields")
optional = {name: importlib.util.find_spec(name) is not None for name in ("docx", "lxml", "jsonschema", "numpy", "pypdf", "PIL")}
assert not any(optional.values()), optional
print(json.dumps({"python": sys.version, "isolated": sys.flags.isolated, "prefix": sys.prefix, "base_prefix": sys.base_prefix, "module": mathmodel_runtime.__file__, "sys_path": sys.path, "optional_modules_present": optional, "installed": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}, "profiles": sorted(profiles), "schemas": sorted(schemas), "invalid_state_rejected": True}))
'''
        observed = json.loads(run([python, "-I", "-c", probe], outside))
        assert observed["isolated"] == 1 and observed["prefix"] != observed["base_prefix"]
        assert Path(observed["module"]).resolve().is_relative_to(environment.resolve())
        assert not any(Path(entry).resolve() == ROOT for entry in observed["sys_path"] if entry)
        assert observed["installed"]["mathmodel-workbench"] == "2.0.0"
        summary["isolated_environment"] = observed
        lines.append("PASS isolated imports: installed wheel only; optional modules absent; all schemas/profiles load; malformed state rejected")
        for profile in ("short", "balanced", "competition"):
            project = outside / ("项目 with spaces " + profile)
            project.mkdir()
            for action in ("init", "state", "complete"):
                options = {"profile": profile, "scope": "modeling"} if action == "init" else {}
                report = json.loads(run([python, "-I", "-m", "mathmodel_runtime", action, "--project-root", project, "--options", json.dumps(options)], outside))
                assert report["ok"] is True, report
                state_path = project / ".math-modeling/state.json"
                state = json.loads(state_path.read_text(encoding="utf-8"))
                assert state["completed"] is False and state["project"]["profile"] == profile
                if action == "complete":
                    assert report["done"] is False and report["blockers"], report
                summary["checks"].append({"profile": profile, "action": action, "ok": True, "completed": state["completed"], "done": report.get("done"), "blockers": report.get("blockers", [])})
            lines.append(f"PASS {profile}: init/state/complete from outside checkout using python -I; completed=false; completion blockers present")
        command = environment / ("Scripts/mathmodel.exe" if os.name == "nt" else "bin/mathmodel")
        version = run([command, "--version"], outside).strip()
        assert version == "mathmodel 2.0.0", version
        summary["console_entrypoint"] = version
        lines.append("PASS installed console entrypoint: " + version)
    summary["status"] = "passed"
    lines.append("RESULT: all final wheel checks passed")
except Exception as exc:
    summary["status"] = "failed"
    summary["error"] = str(exc)
    lines.append("FAIL: " + str(exc))
    raise
finally:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n".join(lines))
