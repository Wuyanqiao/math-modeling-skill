"""Configuration-derived checks, honest probes and read-only project boundaries."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
from unittest.mock import patch

from mathmodel_runtime import environment
from mathmodel_runtime.engine import dispatch
from mathmodel_runtime.storage import Store, WorkflowError


ROOT = Path(__file__).resolve().parents[1]


class EnvironmentReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mathmodel-environment-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "项目 空格"
        self.root.mkdir()
        self.store = Store(self.root, ROOT)
        self.call("init", scope="modeling")

    def call(self, action, **args):
        return dispatch({"action": action, "project_root": str(self.root), "skill_root": str(ROOT), **args})

    def state(self, *, scope="modeling", paper_format="word", graphics=None, inputs=None, rules=None):
        state = self.store.load()
        state["project"].update(scope=scope, paperFormat=paper_format, graphicsTools=graphics or {}, rules=rules or {})
        state["inputs"] = {str(index): {"filename": filename, "kind": kind} for index, (filename, kind) in enumerate(inputs or [])}
        return state

    @contextmanager
    def probes(self, failures=None):
        failures = failures or {}

        def package(identifier, deadline):
            return {"status": failures.get(identifier, "ready"), "version": "1.2.3", "detail": "probe fixture"}

        with patch.object(environment, "probe_package", side_effect=package), patch.object(environment, "probe_command", return_value={"status": "missing", "detail": "not on PATH"}), patch.object(environment, "_find_command", return_value=None):
            yield

    def report(self, state=None, failures=None):
        with self.probes(failures):
            result = environment.environment_report(self.store, state or self.state())
        return result, {item["id"]: item for item in result["items"]}

    def test_only_python_is_core_and_modeling_does_not_require_every_optional_package(self):
        result, items = self.report(failures=dict.fromkeys(environment.DEPENDENCIES, "missing"))
        self.assertTrue(result["ready"])
        self.assertEqual([item["id"] for item in result["items"] if item["requirement"] == "required"], ["python"])
        self.assertEqual(items["matplotlib"]["requirement"], "optional")
        self.assertEqual(items["python-docx"]["requirement"], "optional")
        self.assertIsNone(result["install_command"])
        self.assertNotIn("pip install", result["agent_prompt"])

    def test_scope_format_and_input_materials_select_only_relevant_features(self):
        _, program = self.report(self.state(scope="programming", inputs=[("题目.pdf", "problem"), ("数据.xlsx", "attachment")]))
        for key in ("numpy", "pandas", "matplotlib", "pypdf", "openpyxl"):
            self.assertEqual(program[key]["requirement"], "selected", key)
        self.assertEqual(program["python-docx"]["requirement"], "optional")
        _, word = self.report(self.state(scope="paper", paper_format="word"))
        for key in ("python-docx", "lxml", "defusedxml", "pillow"):
            self.assertEqual(word[key]["requirement"], "selected", key)
        self.assertEqual(word["latex-engine"]["requirement"], "optional")
        self.assertEqual(word["pandoc"]["requirement"], "optional")
        _, latex = self.report(self.state(scope="paper", paper_format="latex"))
        self.assertEqual(latex["latex-engine"]["requirement"], "selected")
        self.assertEqual(latex["pypdf"]["requirement"], "selected")
        self.assertEqual(latex["python-docx"]["requirement"], "optional")

    def test_aggregate_repairs_exclude_optional_packages_and_preserve_explicit_false(self):
        state = self.state(scope="programming", graphics={"scienceplots": True, "seaborn": False})
        result, items = self.report(state, {"numpy": "missing", "scienceplots": "error", "salib": "missing", "seaborn": "missing"})
        self.assertFalse(result["ready"])
        self.assertIn("numpy>=1.26,<3", result["install_command"])
        self.assertIn("SciencePlots>=2.1,<3", result["install_command"])
        for optional in ("SALib", "seaborn"):
            self.assertNotIn(optional, result["install_command"])
            self.assertNotIn(optional, result["agent_prompt"])
        self.assertIn("SALib>=1.5,<2", items["salib"]["install_command"])
        self.assertEqual(items["seaborn"]["requirement"], "optional")

    def test_drawio_does_not_require_desktop_and_scivis_does_not_select_all_gui_tools(self):
        result, items = self.report(self.state(graphics={"drawio": True, "scivis-agent-skills": True}))
        self.assertEqual(items["drawio"]["status"], "ready")
        self.assertIsNone(items["drawio"]["install_command"])
        self.assertEqual(items["scivis-agent-skills"]["status"], "manual")
        self.assertEqual(items["scivis-agent-skills"]["requirement"], "selected")
        for key in ("paraview", "napari", "vmd"):
            self.assertEqual(items[key]["requirement"], "optional")
            self.assertIsNone(items[key]["install_command"])
        self.assertFalse(result["ready"])
        self.assertIsNone(result["install_command"])

    def test_service_checks_never_return_credentials_or_read_dotenv(self):
        secret = "ENVIRONMENT_TEST_SECRET_MUST_NOT_APPEAR"
        (self.root / ".env").write_text("OPENROUTER_API_KEY=" + secret, encoding="utf-8")
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}):
            _, items = self.report(self.state(graphics={"scientific-schematics": True}))
        self.assertIn("未配置", items["scientific-schematics"]["detail"])
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": secret}):
            result, items = self.report(self.state(graphics={"scientific-schematics": True}))
        self.assertEqual(items["scientific-schematics"]["status"], "manual")
        self.assertIn("已配置", items["scientific-schematics"]["detail"])
        self.assertNotIn(secret, json.dumps(result, ensure_ascii=False))
        self.assertFalse(result["ready"])

    def test_legacy_material_and_explicit_word_page_requirements_need_real_routes(self):
        _, items = self.report(self.state(scope="paper", rules={"max_pages": 10}, inputs=[("原题.doc", "problem")]))
        for key in ("word-renderer", "legacy-office-input"):
            self.assertEqual(items[key]["requirement"], "selected")
            self.assertEqual(items[key]["status"], "manual")
            self.assertIsNone(items[key]["install_command"])
        self.assertEqual(items["pypdf"]["requirement"], "selected")

    def test_dispatch_leaves_all_project_bytes_revision_and_legacy_state_unchanged(self):
        state = self.store.load()
        state["project"]["paperRequirements"] = "旧版原文必须保持"
        self.store.path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        (self.root / "untracked.txt").write_text("drift must not trigger environment invalidation", encoding="utf-8")
        before = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        with self.probes(), patch("mathmodel_runtime.engine.invalidate", side_effect=AssertionError("environment must not invalidate")), patch.object(Store, "save", side_effect=AssertionError("environment must not save")):
            result = self.call("environment")
        after = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertTrue(result["ok"])
        self.assertTrue(Path(result["executable"]).is_absolute())
        self.assertFalse((self.store.meta / "state.lock").exists())

    def test_uninitialized_project_is_not_created_by_environment(self):
        empty = Path(self.temporary.name) / "not initialized"
        empty.mkdir()
        with self.assertRaises(WorkflowError) as error:
            dispatch({"action": "environment", "project_root": str(empty), "skill_root": str(ROOT)})
        self.assertEqual(error.exception.code, "not_initialized")
        self.assertEqual(list(empty.iterdir()), [])

    def test_copy_commands_quote_paths_and_constraints_for_each_shell(self):
        executable = "/opt/Python's env/python & $value"
        specifications = ["numpy>=1.26,<3", "python-docx>=1.1,<2"]
        command = environment.install_command(specifications, executable=executable, platform="linux")
        self.assertEqual(shlex.split(command), [executable, "-m", "pip", "install", *specifications])
        windows = environment.install_command(specifications, executable="C:\\用户's env\\python.exe", platform="win32")
        self.assertEqual(windows, "& 'C:\\用户''s env\\python.exe' '-m' 'pip' 'install' 'numpy>=1.26,<3' 'python-docx>=1.1,<2'")

    def test_feature_install_ranges_match_the_declared_project_extras(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        declared = {spec for extra, requirements in project["optional-dependencies"].items() if extra != "dev" for spec in requirements}
        self.assertEqual(declared, {entry[1] for entry in environment.DEPENDENCIES.values()})
        for version in ("0.9.0", "3.0.0", "2.0.0rc1", "unknown"):
            self.assertFalse(environment._in_range(version, "numpy>=1.26,<3"))
        self.assertTrue(environment._in_range("2.2.1", "numpy>=1.26,<3"))

    def test_latexmk_alone_cannot_satisfy_an_actual_tex_engine(self):
        with patch.object(environment, "_find_command", side_effect=lambda name, project_root: sys.executable if name == "latexmk" else None), patch.object(environment, "_run_probe", side_effect=AssertionError("latexmk is not an engine")):
            result = environment.probe_command(("xelatex", "lualatex", "pdflatex"), project_root=self.root)
        self.assertEqual(result["status"], "missing")

    def test_command_lookup_never_executes_project_or_relative_path_programs(self):
        filename = "xelatex.exe" if sys.platform == "win32" else "xelatex"
        candidate = self.root / filename
        candidate.write_text("must not execute", encoding="utf-8")
        candidate.chmod(0o755)
        with patch.dict(os.environ, {"PATH": os.pathsep.join([str(self.root), "."])}):
            self.assertIsNone(environment._find_command("xelatex", self.root))


class ActualProbeTests(unittest.TestCase):
    def test_real_isolated_import_ignores_project_shadow_and_pythonpath(self):
        with tempfile.TemporaryDirectory(prefix="mathmodel-shadow-") as directory:
            root = Path(directory)
            marker = root / "executed"
            (root / "json.py").write_text("from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\nraise RuntimeError('shadow')\n", encoding="utf-8")
            with patch.dict(os.environ, {"PYTHONPATH": str(root)}):
                result = environment.probe_python("json", "")
            self.assertEqual(result["status"], "ready", result)
            self.assertFalse(marker.exists())
        self.assertEqual(environment.probe_python("_mathmodel_absent_dependency_39859", "")["status"], "missing")

    def test_real_user_site_is_visible_and_broken_imports_do_not_expose_exception_secrets(self):
        with tempfile.TemporaryDirectory(prefix="mathmodel-user-site-") as directory:
            base_executable = getattr(sys, "_base_executable", sys.executable)
            configured = {**os.environ, "PYTHONUSERBASE": directory}
            configured.pop("PYTHONNOUSERSITE", None)
            configured.pop("PYTHONPATH", None)
            discovered = subprocess.run([base_executable, "-P", "-c", "import json,site; print(json.dumps([site.getusersitepackages(),site.ENABLE_USER_SITE]))"], env=configured, capture_output=True, text=True, timeout=15, check=True)
            path, enabled = json.loads(discovered.stdout)
            self.assertTrue(enabled, "Base interpreter must permit the standard user site for this regression")
            user_site = Path(path)
            package = user_site / "mathmodel_probe_fixture"
            package.mkdir(parents=True)
            module = package / "__init__.py"
            module.write_text("ANSWER=42\n", encoding="utf-8")
            metadata = user_site / "mathmodel_probe_fixture-1.2.3.dist-info"
            metadata.mkdir()
            (metadata / "METADATA").write_text("Metadata-Version: 2.1\nName: mathmodel-probe-fixture\nVersion: 1.2.3\n", encoding="utf-8")
            with patch.dict(os.environ, configured, clear=True), patch.object(environment.sys, "executable", base_executable):
                found = environment.probe_python("mathmodel_probe_fixture", "mathmodel-probe-fixture")
                self.assertEqual(found["status"], "ready", found)
                self.assertEqual(found["version"], "1.2.3")
                module.write_text("raise RuntimeError('SECRET_FROM_IMPORT_MUST_NOT_APPEAR')\n", encoding="utf-8")
                broken = environment.probe_python("mathmodel_probe_fixture", "mathmodel-probe-fixture")
                self.assertEqual(broken["status"], "error", broken)
                self.assertNotIn("SECRET_FROM_IMPORT", json.dumps(broken))
                module.write_text("import _absent_transitive_dependency_948\n", encoding="utf-8")
                transitive = environment.probe_python("mathmodel_probe_fixture", "mathmodel-probe-fixture")
                self.assertEqual(transitive["status"], "error", transitive)
                self.assertIn("内部依赖", transitive["detail"])

    def test_real_timeout_is_an_error_and_never_returns_child_output(self):
        start = time.monotonic()
        with patch.object(environment, "_IMPORT_SCRIPT", "import time; print('SECRET_TIMEOUT_OUTPUT', flush=True); time.sleep(10)"):
            result = environment.probe_python("unused", "", deadline=start + .2)
        self.assertEqual(result["status"], "error")
        self.assertIn("超时", result["detail"])
        self.assertNotIn("SECRET_TIMEOUT_OUTPUT", json.dumps(result))
        self.assertLess(time.monotonic() - start, 4)

    def test_version_probe_returns_only_version_and_discarded_failure_output(self):
        with patch.object(environment, "_find_command", return_value=sys.executable):
            result = environment.probe_command(("python",))
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["version"], sys.version.split()[0])
        output = {"returncode": 1, "stdout": b"SECRET_FAILED_VERSION", "stderr": b"SECRET_KEY"}
        with patch.object(environment, "_find_command", return_value=sys.executable), patch.object(environment, "_run_probe", return_value=output):
            failure = environment.probe_command(("python",))
        self.assertEqual(failure["status"], "error")
        self.assertNotIn("SECRET", json.dumps(failure))


if __name__ == "__main__":
    unittest.main()
