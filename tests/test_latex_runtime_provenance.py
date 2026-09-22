"""Provenance fixtures test validators; optional smoke test actually invokes TeX."""

import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mathmodel_runtime.engine import dispatch
from mathmodel_runtime.validation import phase_validation


class LatexRuntimeProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="paper provenance ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.tex = self.root / "main.tex"
        self.tex.write_text(r"\documentclass{article}\begin{document}Provenance fixture.\end{document}", encoding="utf-8")
        self.pdf("完整论文.pdf")
        self.docx()
        self.state = {"project": {"paperFormat": "latex", "subproblems": [], "rules": {}},
                      "artifacts": {}, "runs": {}, "claims": {}}
        self.register("main.tex", "code")
        self.register("完整论文.pdf", "pdf", "tex-build")
        self.state["runs"]["tex-build"] = self.run_record("xelatex", ["main.tex"], [], ["完整论文.pdf"])

    def entry(self, relative):
        return {"path": relative, "sha256": hashlib.sha256((self.root / relative).read_bytes()).hexdigest()}

    def register(self, relative, kind, run_id=None):
        self.state["artifacts"][relative] = {**self.entry(relative), "artifact_id": relative,
                                              "kind": kind, "run_id": run_id}

    def run_record(self, tool, code, inputs, outputs):
        executable = str(Path(sys.executable).with_name(tool + Path(sys.executable).suffix))
        argv = [executable, code[0]]
        return {"phase": "paper", "status": "succeeded", "exit_code": 0,
                "argv": argv, "actual_argv": list(argv), "executable": executable,
                "environment": {"name": tool, "version": "fixture", "dependencies": {},
                                "probe_status": "ok", "executable": executable, "probe_argv": [executable, "--version"]},
                "cwd": str(self.root), "execution_cwd": str(self.root),
                "code": [self.entry(path) for path in code],
                "inputs": [self.entry(path) for path in inputs],
                "outputs": [self.entry(path) for path in outputs]}

    def pdf(self, name, pages=1):
        writer = PdfWriter()
        for _ in range(pages):
            page = writer.add_blank_page(width=200, height=200)
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                     NameObject("/Subtype"): NameObject("/Type1"),
                                     NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 10 Tf 10 100 Td (Test fixture) Tj ET")
            page[NameObject("/Contents")] = writer._add_object(stream)
        with (self.root / name).open("wb") as output:
            writer.write(output)

    def docx(self):
        with zipfile.ZipFile(self.root / "完整论文.docx", "w") as archive:
            archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
            archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Current Word paper fixture</w:t></w:r></w:p></w:body></w:document>')

    def validate(self):
        return phase_validation(self.root, self.state, "paper", {"recommendations": {}})

    def checks(self):
        return {item["name"]: item for item in self.validate()["items"]}

    def test_direct_registered_tex_build_is_accepted(self):
        self.assertTrue(self.checks()["pdf_build_provenance"]["ok"])
        self.assertEqual(self.validate()["overall"], "ok")

    def test_pdf_copy_wrapper_cannot_impersonate_tex_compilation(self):
        (self.root / "copy.py").write_text("print('fixture')", encoding="utf-8")
        self.state["runs"]["tex-build"] = self.run_record("python", ["copy.py", "main.tex"], [], ["完整论文.pdf"])
        self.assertFalse(self.checks()["pdf_build_provenance"]["ok"])

    def test_tex_build_requires_registered_source_in_executed_code(self):
        self.state["artifacts"].pop("main.tex")
        checks = self.checks()
        self.assertFalse(checks["registered_tex_source"]["ok"])
        self.assertFalse(checks["pdf_build_provenance"]["ok"])

    def test_recorded_requested_tool_cannot_hide_different_actual_executor(self):
        self.state["runs"]["tex-build"]["actual_argv"][0] = sys.executable
        self.assertFalse(self.checks()["pdf_build_provenance"]["ok"])

    def test_actual_tex_entry_must_match_registered_entry(self):
        self.state["runs"]["tex-build"]["actual_argv"] = [self.state["runs"]["tex-build"]["executable"], "other.tex"]
        self.assertFalse(self.checks()["pdf_build_provenance"]["ok"])

    def test_actual_executor_path_must_match_execution_record(self):
        self.state["runs"]["tex-build"]["actual_argv"][0] = str(self.root / Path(self.state["runs"]["tex-build"]["executable"]).name)
        self.assertFalse(self.checks()["pdf_build_provenance"]["ok"])

    def test_changed_tex_source_invalidates_build(self):
        self.tex.write_text("Changed source", encoding="utf-8")
        checks = self.checks()
        self.assertFalse(checks["tex_source:main.tex"]["ok"])
        self.assertFalse(checks["pdf_build_provenance"]["ok"])

    def word_mode(self):
        self.state["project"].update(paperFormat="word", rules={"source": "test fixture", "max_pages": 2})
        (self.root / "render.py").write_text("print('renderer test fixture')", encoding="utf-8")

    def test_unrelated_short_pdf_does_not_satisfy_word_page_limit(self):
        self.word_mode()
        checks = self.checks()
        self.assertFalse(checks["word_page_render_provenance"]["ok"])
        self.assertFalse(checks["required_page_limit"]["ok"])

    def test_word_page_limit_uses_current_docx_render_input(self):
        self.word_mode()
        self.state["runs"]["render"] = self.run_record("python", ["render.py"], ["完整论文.docx"], ["完整论文.pdf"])
        self.register("完整论文.pdf", "pdf", "render")
        self.assertTrue(self.checks()["word_page_render_provenance"]["ok"])
        self.assertTrue(self.checks()["required_page_limit"]["ok"])
        with zipfile.ZipFile(self.root / "完整论文.docx", "a") as archive:
            archive.writestr("changed-version.txt", "new document revision")
        self.assertFalse(self.checks()["word_page_render_provenance"]["ok"])

    def test_dual_format_needs_word_render_in_addition_to_tex_pdf(self):
        self.state["project"].update(paperFormat="word+latex", rules={"source": "test fixture", "max_pages": 2})
        self.assertTrue(self.checks()["pdf_build_provenance"]["ok"])
        self.assertFalse(self.checks()["word_page_render_provenance"]["ok"])

    @unittest.skipUnless(shutil.which("xelatex"), "Optional real TeX engine is not installed")
    def test_actual_xelatex_runtime_build_passes_provenance(self):
        def call(action, **options):
            return dispatch({"action": action, "project_root": str(self.root), **options})
        call("init", scope="paper", paper_format="latex", profile="short")
        artifact = call("artifact-add", path="main.tex", kind="code", question="q1")["artifact"]
        call("claim-add", text="A typesetting fixture, not a scientific conclusion", question="q1",
             artifact_ids=[artifact["artifact_id"]])
        built = call("run", phase="paper", argv=[shutil.which("xelatex"), "-interaction=nonstopmode",
                   "-halt-on-error", "-jobname=完整论文", "main.tex"], code=["main.tex"], outputs=["完整论文.pdf"])
        self.assertTrue(built["ok"], built)
        validated = call("validate", phase="paper")
        self.assertEqual(validated["overall"], "ok", validated)


if __name__ == "__main__":
    unittest.main()
