"""Independent format and provenance validators; optional engines report blocked."""

import ast
import csv
import importlib.metadata
import importlib.util
import importlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

from .storage import WorkflowError, digest, inside, paper_only_path, project_files


FEATURES = {
    "data": {"numpy": "numpy", "pandas": "pandas"},
    "optimization": {"scipy": "scipy"},
    "machine-learning": {"sklearn": "scikit-learn"},
    "figure": {"PIL": "Pillow", "matplotlib": "matplotlib"},
    "docx": {"docx": "python-docx", "lxml": "lxml", "defusedxml": "defusedxml"},
    "pdf": {"pypdf": "pypdf"},
    "xlsx": {"openpyxl": "openpyxl"},
    "validation": {"jsonschema": "jsonschema"},
}


def doctor(features=None):
    selected = list(features or FEATURES)
    unknown = set(selected) - FEATURES.keys() - {"latex", "render"}
    if unknown:
        raise WorkflowError("Unknown capabilities: " + ", ".join(sorted(unknown)))
    capabilities = {}
    for feature in selected:
        if feature not in FEATURES:
            continue
        modules = {}
        for module, package in FEATURES[feature].items():
            try:
                importlib.import_module(module)
                available = True
            except (ImportError, OSError):
                available = False
            try:
                version = importlib.metadata.version(package) if available else None
            except importlib.metadata.PackageNotFoundError:
                version = "unknown"
            modules[package] = {"available": available, "version": version}
        capabilities[feature] = {"available": all(m["available"] for m in modules.values()), "dependencies": modules}
    for feature, names in {"latex": ["xelatex", "latexmk"], "render": ["pdftoppm"]}.items():
        if features and feature not in selected:
            continue
        entries = {}
        for name in names:
            executable = shutil.which(name)
            available, version = False, None
            if executable:
                try:
                    result = subprocess.run([executable, "--version" if name != "pdftoppm" else "-v"],
                                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
                    available = result.returncode == 0
                    version = (result.stdout or result.stderr).strip().splitlines()[0] if (result.stdout or result.stderr).strip() else None
                except (OSError, subprocess.TimeoutExpired):
                    pass
            entries[name] = {"available": available, "path": executable, "version": version}
        capabilities[feature] = {"available": all(e["available"] for e in entries.values()), "dependencies": entries}
    missing = [name for name, value in capabilities.items() if not value["available"]]
    return {"ok": True, "python": sys.version.split()[0], "executable": sys.executable,
            "capabilities": capabilities, "missing": missing,
            "ready": not missing, "notice": "Availability is not proof of a completed solve, build or visual review."}


def xml_document(raw, *, allow_svg_doctype=False):
    if b"<!ENTITY" in raw.replace(b"\x00", b"").upper():
        raise WorkflowError("XML entities and external doctypes are not supported")
    if allow_svg_doctype:
        external = rb'<!DOCTYPE\s+svg\s+(?:PUBLIC\s+(?:"[^"]*"|\x27[^\x27]*\x27)\s+|SYSTEM\s+)(?:"[^"]*"|\x27[^\x27]*\x27)\s*>'
        raw = re.sub(external, b"", raw, count=1, flags=re.I)
    if b"<!DOCTYPE" in raw.replace(b"\x00", b"").upper():
        raise WorkflowError("Internal XML subsets and non-SVG doctypes are not supported")
    return ET.fromstring(raw)


def read_zip_xml(archive, name):
    info = archive.getinfo(name)
    if info.file_size > 32 * 1024 * 1024:
        raise WorkflowError("XML package part exceeds the 32 MiB inspection limit")
    return xml_document(archive.read(name))


def environment_errors(runtime):
    if not isinstance(runtime, dict):
        return ["Runtime environment must be an object"]
    errors = []
    if runtime.get("probe_status") != "ok":
        errors.append("Runtime environment probe is missing or failed; execute again with a working version probe")
    version = runtime.get("version")
    if not isinstance(runtime.get("name"), str) or not runtime["name"].strip() or not isinstance(version, str) or not version.strip() or version.strip().lower() in {"unknown", "recorded in argv"}:
        errors.append("runtime.name and runtime.version must identify the observed execution environment")
    dependencies = runtime.get("dependencies")
    if not isinstance(dependencies, dict) or any(not isinstance(name, str) or not name.strip() or not isinstance(value, str) or not value.strip() for name, value in dependencies.items()):
        errors.append("runtime.dependencies must record observed dependency versions")
    executable, argv = runtime.get("executable"), runtime.get("probe_argv")
    if not isinstance(executable, str) or not Path(executable).is_absolute() or not isinstance(argv, list) or not argv or argv[0] != executable:
        errors.append("Environment probe must identify the actual absolute executable")
    return errors


def validate_manifest(path, root):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = []
    if not isinstance(data, dict):
        return ["Manifest must be an object"]
    seed = data.get("random_seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        errors.append("random_seed must be an integer")
    if not isinstance(data.get("key_parameters"), dict):
        errors.append("key_parameters must be an object")
    command = data.get("reproduce_command")
    if not isinstance(command, str) or not command.strip():
        errors.append("reproduce_command must be nonempty")
    runtime = data.get("runtime", {})
    errors.extend(environment_errors(runtime))
    inputs = data.get("input_files")
    if not isinstance(inputs, list):
        errors.append("input_files must be an array containing path and sha256")
    else:
        for item in inputs:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))):
                errors.append("Each input requires a valid path and SHA-256")
                continue
            try:
                file = inside(root, item["path"])
                if not file.is_file() or digest(file) != item["sha256"]:
                    errors.append("Input absent or changed: " + item["path"])
            except WorkflowError as exc:
                errors.append(str(exc))
    return errors


def inspect_file(root, relative, kind=None):
    item = {"path": str(relative), "ok": False, "blocked": False, "errors": [], "details": {}}
    try:
        path = inside(root, relative)
        if not path.is_file() or path.stat().st_size == 0:
            raise WorkflowError("File is missing or empty")
        suffix = path.suffix.lower()
        allowed = {"model": {".md", ".txt"}, "terms": {".md", ".csv", ".txt"},
                   "document": {".docx", ".tex"}, "pdf": {".pdf"},
                   "figure": {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".svg", ".pdf"},
                   "table": {".csv", ".tsv", ".xlsx"}, "manifest": {".json"},
                   "code": {".py", ".m", ".r", ".jl", ".tex", ".ipynb"}, "outline": {".md", ".txt"}}
        if kind in allowed and suffix not in allowed[kind]:
            raise WorkflowError("File format does not match declared artifact kind")
        item["bytes"] = path.stat().st_size
        item["sha256"] = digest(path)
        if kind == "manifest":
            item["errors"] = validate_manifest(path, root)
        elif suffix == ".docx":
            with zipfile.ZipFile(path) as archive:
                read_zip_xml(archive, "[Content_Types].xml")
                document = read_zip_xml(archive, "word/document.xml")
                text = "".join(n.text or "" for n in document.iter() if n.tag.endswith("}t"))
                if not text.strip():
                    raise WorkflowError("DOCX has no readable document text")
                item["details"] = {"content_units": len(text), "structural_only": True}
        elif suffix == ".xlsx":
            import openpyxl
            book = openpyxl.load_workbook(path, read_only=True, data_only=False)
            try:
                found = any(any(value is not None for value in row) for sheet in book for row in sheet.iter_rows(values_only=True))
                if not found:
                    raise WorkflowError("Workbook has no data")
            finally:
                book.close()
        elif suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}:
            from PIL import Image
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                image.load()
                item["details"] = {"width": image.width, "height": image.height}
        elif suffix == ".svg":
            document = xml_document(path.read_bytes(), allow_svg_doctype=True)
            if document.tag.split("}")[-1] != "svg":
                raise WorkflowError("Expected an SVG root")
            visible = {"path", "rect", "circle", "ellipse", "line", "polygon", "polyline", "text", "image"}
            if not any(n.tag.split("}")[-1] in visible for n in document.iter()):
                raise WorkflowError("SVG has no drawable content")
            if any(n.tag.split("}")[-1] in {"script", "foreignObject"} for n in document.iter()):
                raise WorkflowError("Executable SVG content is not supported for previews")
        elif suffix == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(path)
            if reader.is_encrypted or not reader.pages:
                raise WorkflowError("PDF must have readable, unencrypted pages")
            content = [(page.extract_text() or "").strip() or bool(page.get("/Resources")) for page in reader.pages]
            if not all(content):
                raise WorkflowError("PDF contains a page without detectable content")
            item["details"] = {"pages": len(reader.pages), "structural_only": True}
        elif suffix in {".csv", ".tsv"}:
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = csv.reader(stream, delimiter="\t" if suffix == ".tsv" else ",")
                header = next(rows, [])
                count = 0
                for row in rows:
                    if len(row) != len(header):
                        raise WorkflowError("Table has inconsistent column counts")
                    count += bool(any(cell.strip() for cell in row))
                if not header or count == 0:
                    raise WorkflowError("Table needs a header and at least one data row")
                item["details"] = {"rows": count, "columns": len(header)}
        elif suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        elif suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
        elif suffix in {".md", ".txt", ".tex", ".m", ".bib", ".r", ".jl"}:
            content = path.read_text(encoding="utf-8-sig")
            if not content.strip() or re.fullmatch(r"\s*(TODO|TBD|待补充|占位符)[.!。\s]*", content, re.I):
                raise WorkflowError("Text contains only a placeholder")
            item["details"] = {"content_units": len(content.strip())}
        elif kind in {"document", "figure", "table", "code", "pdf"}:
            raise WorkflowError("Unsupported format for declared artifact kind")
        item["ok"] = not item["errors"]
    except ImportError as exc:
        item["blocked"] = True
        item["errors"].append("Missing inspection dependency: " + str(exc))
    except (OSError, ValueError, SyntaxError, ET.ParseError, zipfile.BadZipFile, KeyError) as exc:
        item["errors"].append(str(exc))
    return item


def fresh_run(root, run):
    if run.get("exit_code") != 0 or run.get("status") != "succeeded" or run.get("source_drift") or run.get("artifact_errors") or not run.get("code"):
        return False
    if environment_errors(run.get("environment")):
        return False
    for group in ("inputs", "code", "outputs"):
        for item in run.get(group, []):
            try:
                path = inside(root, item["path"])
                if not path.is_file() or digest(path) != item["sha256"]:
                    return False
            except (OSError, WorkflowError, KeyError):
                return False
    return True


def direct_tex_build(root, run, sources, pdf):
    """Require a directly invoked TeX tool and its registered, current entry source."""
    tools = {"xelatex": {"xelatex", "xetex"}, "pdflatex": {"pdflatex", "pdftex"},
             "lualatex": {"lualatex", "luatex", "luahbtex"}, "latexmk": {"latexmk"}}
    argv, actual = run.get("argv", []), run.get("actual_argv", [])
    executable = run.get("executable")
    if not argv or not actual or not isinstance(executable, str) or not Path(executable).is_absolute():
        return False
    if not Path(actual[0]).is_absolute() or Path(actual[0]) != Path(executable):
        return False
    requested = Path(argv[0]).stem.lower()
    if requested not in tools:
        return False
    # TeX distributions may resolve the command alias to an engine binary on Unix.
    for command in (actual[0], executable):
        path = Path(command)
        if path.suffix.lower() not in {"", ".exe"} or path.stem.lower() not in tools[requested]:
            return False
    code = {item["path"]: item["sha256"] for item in run.get("code", [])}
    entry_sources = set()
    for argument in argv[1:]:
        if argument.startswith("-") or Path(argument).suffix.lower() != ".tex":
            continue
        try:
            entry_sources.add(inside(root, argument).relative_to(Path(root)).as_posix())
        except WorkflowError:
            continue
    actual_entries = set()
    execution_root = Path(run.get("execution_cwd") or run.get("cwd") or root).resolve()
    for argument in actual[1:]:
        if argument.startswith("-") or Path(argument).suffix.lower() != ".tex":
            continue
        path = (execution_root / argument).resolve()
        if path.is_relative_to(execution_root):
            actual_entries.add(path.relative_to(execution_root).as_posix())
    registered_entry = any(path in sources and path in actual_entries and code.get(path) == sources[path]
                           for path in entry_sources)
    output_bound = any(item["path"] == "完整论文.pdf" and item["sha256"] == pdf.get("sha256")
                       for item in run.get("outputs", []))
    return registered_entry and output_bound


def word_render_outputs(root, runs, artifacts, document):
    """Find current PDF artifacts generated by a run that consumed this DOCX version."""
    candidates = []
    for artifact in artifacts:
        if Path(artifact["path"]).suffix.lower() != ".pdf":
            continue
        run = runs.get(artifact.get("run_id"))
        if not run or run.get("phase") != "paper" or not fresh_run(root, run):
            continue
        input_bound = any(item["path"] == "完整论文.docx" and item["sha256"] == document.get("sha256")
                          for item in run.get("inputs", []))
        output_bound = any(item["path"] == artifact["path"] and item["sha256"] == artifact["sha256"]
                           for item in run.get("outputs", []))
        if input_bound and output_bound:
            inspected = inspect_file(root, artifact["path"], "pdf")
            if inspected["ok"] and inspected.get("sha256") == artifact["sha256"]:
                candidates.append(inspected)
    return candidates


def phase_validation(root, state, phase, profile):
    items, warnings = [], []
    def check(name, ok, note="", blocked=False):
        items.append({"name": name, "ok": bool(ok), "note": note, "blocked": blocked})
    from .inputs import input_integrity_errors
    for index, error in enumerate(input_integrity_errors(root, state, phase)):
        check("imported_input_integrity:" + str(index), False, error)
    artifacts = [artifact for artifact in state["artifacts"].values() if phase != "programming" or not paper_only_path(state, artifact["path"], artifact)]
    kinds = {}
    for artifact in artifacts:
        kinds.setdefault(artifact["kind"], []).append(artifact)
    def inspect(relative, kind=None):
        result = inspect_file(root, relative, kind)
        check(relative, result["ok"], "; ".join(result["errors"]), result["blocked"])
        return result
    if phase == "modeling":
        inspect("题目分析报告.md", "model")
        inspect("术语表格.md", "terms")
    elif phase == "programming":
        runs = [r for r in state["runs"].values() if r.get("phase") == "programming"]
        check("successful_current_run", bool(runs) and fresh_run(root, runs[-1]), "Register a real execution with current input/code/output hashes")
        check("result_tables", bool(kinds.get("table")), "Register a nonempty result table")
        for artifact in kinds.get("code", []) + kinds.get("table", []) + kinds.get("figure", []):
            inspect(artifact["path"], artifact["kind"])
        inspect("results/复现清单.json", "manifest")
        for artifact in kinds.get("table", []) + kinds.get("figure", []):
            run = state["runs"].get(artifact.get("run_id"))
            produced = bool(run and fresh_run(root, run) and any(o["path"] == artifact["path"] and o["sha256"] == artifact["sha256"] for o in run.get("outputs", [])))
            check("provenance:" + artifact["path"], produced, "Results must be bound to a successful run that produced this version")
        for question in state["project"]["subproblems"]:
            evidence = [a for a in artifacts if a.get("question") == question and a["kind"] in {"table", "figure"}]
            check("evidence:" + question, bool(evidence), "A result table or figure must answer this subproblem")
    elif phase == "paper":
        formats = state["project"]["paperFormat"]
        document = None
        pdf = None
        if formats in {"word", "word+latex"}:
            document = inspect("完整论文.docx", "document")
        if formats in {"latex", "word+latex"}:
            pdf = inspect("完整论文.pdf", "pdf")
            sources = {}
            for artifact in artifacts:
                if artifact["kind"] not in {"code", "document"} or Path(artifact["path"]).suffix.lower() != ".tex":
                    continue
                source = inspect(artifact["path"], artifact["kind"])
                current = source["ok"] and source.get("sha256") == artifact["sha256"]
                check("tex_source:" + artifact["path"], current, "Registered TeX source must match its current file")
                if current:
                    sources[artifact["path"]] = source["sha256"]
            check("registered_tex_source", bool(sources), "Register the TeX entry source as code or document")
            builds = [r for r in state["runs"].values() if r.get("phase") == "paper" and fresh_run(root, r)]
            bound = any(direct_tex_build(root, run, sources, pdf) for run in builds)
            check("pdf_build_provenance", bound,
                  "PDF requires a direct xelatex/pdflatex/lualatex/latexmk run with actual executor, registered TeX entry in code, and current output hash; unverified wrappers require a direct rebuild")
        rules = state["project"].get("rules", {})
        if "min_content_units" in rules:
            if document:
                units = document.get("details", {}).get("content_units", 0)
            else:
                sources = [a for a in artifacts if a["path"].endswith(".tex")]
                units = sum(len(inside(root, a["path"]).read_text(encoding="utf-8")) for a in sources)
            check("required_content_units", units >= rules["min_content_units"], "Explicit content length rule: " + rules["source"])
        if "max_pages" in rules:
            page_counts = []
            missing_render = False
            if formats in {"latex", "word+latex"}:
                pages = (pdf or {}).get("details", {}).get("pages")
                missing_render = pages is None
                if pages is not None:
                    page_counts.append(pages)
            if document is not None:
                rendered = word_render_outputs(root, state["runs"], artifacts, document)
                check("word_page_render_provenance", bool(rendered),
                      "Word page counts require a registered PDF output of a successful run consuming this exact DOCX", not rendered)
                missing_render = missing_render or not rendered
                page_counts.extend(item["details"]["pages"] for item in rendered)
            check("required_page_limit", not missing_render and bool(page_counts) and max(page_counts) <= rules["max_pages"],
                  "All selected formats require current, source-bound page counts: " + rules["source"], missing_render)
        claims = list(state["claims"].values())
        for question in state["project"]["subproblems"]:
            valid = [c for c in claims if c.get("question") == question and c.get("artifact_ids")]
            check("claims:" + question, bool(valid), "Register the conclusion and its evidence before W1/W2")
        for claim in claims:
            for identifier in claim["artifact_ids"]:
                artifact = state["artifacts"].get(identifier)
                check("claim:" + claim["claim_id"] + ":" + identifier, artifact is not None, "Referenced artifact must exist")
                if artifact:
                    result = inspect(artifact["path"], artifact["kind"])
                    check("claim_hash:" + identifier, result.get("sha256") == artifact["sha256"], "Claim evidence version must be current")
        # Visual review is a distinct reviewer responsibility; never infer it from ZIP/XML validity.
        warnings.append("Structural checks do not prove visual layout or scientific correctness; W2 reviewer must inspect rendered pages and conclusions.")
    else:
        raise WorkflowError("Unknown phase")
    figures = {a.get("logical_id", a["path"]) for a in kinds.get("figure", []) if a.get("role") != "render"}
    recommended = profile.get("recommendations", {}).get("figures", 0)
    if len(figures) < recommended and phase != "modeling":
        warnings.append(f"Profile recommends {recommended} logical figures; found {len(figures)}. This is advisory.")
    rules = state["project"].get("rules", {})
    if phase in {"programming", "paper"} and "min_figures" in rules:
        check("required_figure_count", len(figures) >= rules["min_figures"], "Explicit rule: " + rules["source"])
    if phase == "paper" and rules.get("require_render"):
        rendered = [a for a in kinds.get("figure", []) if a.get("role") == "render" and a.get("source_artifact_id") in state["artifacts"]]
        check("rendered_pages", bool(rendered), "Register render output bound to its source document")
        for artifact in rendered:
            inspect(artifact["path"], "figure")
            source = state["artifacts"][artifact["source_artifact_id"]]
            run = state["runs"].get(artifact.get("run_id"))
            bound = bool(run and fresh_run(root, run) and any(x["path"] == source["path"] and x["sha256"] == source["sha256"] for x in run.get("inputs", [])))
            check("render_provenance:" + artifact["artifact_id"], bound and not source.get("stale"), "Render must be generated from the current source document")
    overall = "blocked" if any(i["blocked"] for i in items) else ("ok" if all(i["ok"] for i in items) else "missing")
    return {"ok": True, "phase": phase, "overall": overall, "items": items, "warnings": warnings}
