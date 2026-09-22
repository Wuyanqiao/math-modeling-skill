"""Execution metadata must describe the program's interpreter, not this process."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import venv

from mathmodel_runtime.engine import dispatch
from mathmodel_runtime.execution import probe_environment, reproduce_command
from mathmodel_runtime.storage import WorkflowError


class RuntimeEnvironmentTests(unittest.TestCase):
    def test_run_probes_the_executed_python_and_records_replay(self):
        with tempfile.TemporaryDirectory(prefix="runtime environment ") as folder:
            base = Path(folder).resolve()
            environment = base / "separate python"
            venv.EnvBuilder(with_pip=False).create(environment)
            executable = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            project = base / "project"
            project.mkdir()
            dispatch({"action": "init", "project_root": str(project), "scope": "programming", "profile": "short"})
            source = (
                "import importlib.metadata, json, sys\n"
                "from pathlib import Path\n"
                "Path('actual.json').write_text(json.dumps({'executable': sys.executable, "
                "'version': sys.version.split()[0], 'dependencies': "
                "dict(sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions() if d.metadata['Name']))}), encoding='utf-8')\n"
            )
            (project / "solver.py").write_text(source, encoding="utf-8")
            result = dispatch({"action": "run", "project_root": str(project), "argv": [str(executable), "solver.py"],
                               "code": ["solver.py"], "outputs": ["actual.json"]})
            self.assertTrue(result["ok"])
            observed = json.loads((project / "actual.json").read_text(encoding="utf-8"))
            recorded = result["run"]["environment"]
            self.assertEqual(recorded["probe_status"], "ok")
            self.assertEqual(recorded["version"], observed["version"])
            self.assertEqual(recorded["dependencies"], observed["dependencies"])
            self.assertEqual(Path(recorded["observed_executable"]), Path(observed["executable"]))
            self.assertEqual(recorded["executable"], str(executable))
            self.assertNotEqual(Path(recorded["executable"]), Path(sys.executable))
            manifest = json.loads((project / "results/复现清单.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["runtime"], recorded)
            self.assertEqual(manifest["argv"], [str(executable), "solver.py"])
            self.assertEqual((manifest["shell"], manifest["reproduce_command"]), reproduce_command(manifest["argv"]))

    def test_failed_probe_is_explicit_and_does_not_copy_error_output(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = str(Path(folder) / "python-missing")
            result = probe_environment(missing, folder)
            self.assertEqual(result["probe_status"], "failed")
            self.assertEqual(result["version"], "unknown")
            self.assertEqual(result["probe_error"], "FileNotFoundError")
            with patch("mathmodel_runtime.execution.subprocess.run", side_effect=subprocess.TimeoutExpired([sys.executable], 0.01, stderr="secret")):
                result = probe_environment(sys.executable, folder, timeout=0.01)
            self.assertEqual(result["probe_error"], "TimeoutExpired")
            self.assertEqual(result["probe_status"], "failed")
            self.assertNotIn("secret", json.dumps(result))

    def test_replay_quoting_preserves_spaces_apostrophes_and_metacharacters(self):
        argv = ["C:\\Program Files\\Python\\python.exe", "it's $name; harmless.py"]
        shell, command = reproduce_command(argv, platform="nt")
        self.assertEqual(shell, "powershell")
        self.assertEqual(command, "& 'C:\\Program Files\\Python\\python.exe' 'it''s $name; harmless.py'")
        import shlex
        shell, command = reproduce_command(argv, platform="posix")
        self.assertEqual(shell, "posix")
        self.assertEqual(shlex.split(command), argv)

    def test_successful_solver_with_failed_probe_cannot_prepare_p1(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder).resolve()
            dispatch({"action": "init", "project_root": str(project), "scope": "programming", "profile": "short"})
            (project / "solver.py").write_text("from pathlib import Path\nPath('result.txt').write_text('computed')\n", encoding="utf-8")
            failed = {"name": "python", "version": "unknown", "dependencies": {}, "probe_status": "failed",
                      "probe_error": "TimeoutExpired", "executable": sys.executable, "probe_argv": [sys.executable, "-c", "pass"]}
            with patch("mathmodel_runtime.execution.probe_environment", return_value=failed):
                result = dispatch({"action": "run", "project_root": str(project), "argv": [sys.executable, "solver.py"],
                                   "code": ["solver.py"], "outputs": ["result.txt"]})
            self.assertEqual(result["run"]["exit_code"], 0)
            self.assertFalse(result["ok"])
            with self.assertRaises(WorkflowError) as error:
                dispatch({"action": "gate-prepare", "project_root": str(project), "gate": "P1"})
            self.assertEqual(error.exception.code, "gate_validation")


if __name__ == "__main__":
    unittest.main()
