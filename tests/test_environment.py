import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("docx_environment_check", ROOT / "tools/docx/scripts/check_env.py")
environment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(environment)


class DocxEnvironmentTests(unittest.TestCase):
    def report(self, imports=None, *, binary=None, run=None, required=False):
        with patch.object(environment.importlib, "import_module", side_effect=imports), patch.object(environment.importlib.metadata, "version", return_value="test"), patch.object(environment.shutil, "which", return_value=binary), patch.object(environment.subprocess, "run", return_value=run):
            return environment.check_environment(need_pandoc=required)

    def test_missing_defusedxml_is_a_required_dependency_failure(self):
        def importer(name):
            if name == "defusedxml.minidom":
                raise ModuleNotFoundError("defusedxml")
            return object()
        report = self.report(importer)
        self.assertFalse(report["ok"])
        failed = [item["package"] for item in report["modules"] if not item["ok"]]
        self.assertEqual(failed, ["defusedxml"])

    def test_broken_extension_import_is_not_reported_as_available(self):
        def importer(name):
            if name == "lxml.etree":
                raise OSError("DLL load failed")
            return object()
        report = self.report(importer)
        self.assertFalse(report["ok"])
        self.assertIn("DLL load failed", report["modules"][1]["error"])

    def test_missing_optional_converter_does_not_block_native_docx(self):
        self.assertTrue(self.report()["ok"])
        self.assertFalse(self.report(required=True)["ok"])

    def test_converter_path_must_actually_execute(self):
        failed = subprocess.CompletedProcess(["pandoc", "--version"], 1, "", "broken wrapper")
        report = self.report(binary="pandoc", run=failed, required=True)
        self.assertFalse(report["ok"])
        self.assertEqual(report["binaries"][0]["returncode"], 1)

    def test_working_converter_reports_version(self):
        passed = subprocess.CompletedProcess(["pandoc", "--version"], 0, "pandoc 3.8\n", "")
        report = self.report(binary="pandoc", run=passed, required=True)
        self.assertTrue(report["ok"])
        self.assertEqual(report["binaries"][0]["version"], "pandoc 3.8")


if __name__ == "__main__":
    unittest.main()
