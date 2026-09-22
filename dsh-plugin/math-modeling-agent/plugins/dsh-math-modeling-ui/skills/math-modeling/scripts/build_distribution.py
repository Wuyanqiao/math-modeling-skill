#!/usr/bin/env python3
"""Build inspectable Skill/DSH archives from one source tree, with fail-closed licensing."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "distribution-manifest.json"
LOCAL_NOTICE = "LOCAL_DEVELOPMENT_ONLY.txt"
DSH_BUNDLE = Path("plugins/dsh-math-modeling-ui")


class DistributionError(ValueError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_policy(root: Path) -> dict:
    policy = json.loads((root / "distribution-policy.json").read_text(encoding="utf-8"))
    if policy.get("schema_version") != 1 or policy.get("default_decision") != "block":
        raise DistributionError("Distribution policy must use schema 1 and default_decision=block")
    return policy


def excluded(relative: Path, policy: dict) -> bool:
    return (
        any(part in policy["excluded_names"] or part.endswith(".egg-info") for part in relative.parts)
        or relative.suffix.lower() in policy["excluded_suffixes"]
    )


def source_files(root: Path, policy: dict, *, dsh: bool = False) -> dict[str, Path]:
    """Enumerate declared roots only; reject links instead of copying outside the checkout."""
    paths = ["dsh-plugin/math-modeling-agent"] if dsh else policy["skill_paths"]
    files: dict[str, Path] = {}
    for entry in paths:
        base = root / entry
        if not base.exists():
            continue
        candidates = [base] if base.is_file() else base.rglob("*")
        for path in candidates:
            relative = path.relative_to(root)
            if excluded(relative, policy):
                continue
            if dsh:
                generated = [Path("dsh-plugin/math-modeling-agent/skills/math-modeling"), Path("dsh-plugin/math-modeling-agent") / DSH_BUNDLE / "skills/math-modeling"]
                if any(relative.is_relative_to(directory) for directory in generated):
                    continue
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise DistributionError(f"Symlink or out-of-tree resource is not distributable: {relative}")
            if path.is_file():
                files[relative.as_posix()] = path
    return dict(sorted(files.items()))


def component_for(relative: str, policy: dict) -> dict | None:
    matches = [
        (len(prefix), component)
        for component in policy["components"]
        for prefix in component["prefixes"]
        if relative == prefix or relative.startswith(prefix + "/")
    ]
    return max(matches, key=lambda item: item[0])[1] if matches else None


def authorize(files: dict[str, Path], policy: dict, mode: str) -> tuple[dict[str, Path], list[dict]]:
    accepted: dict[str, Path] = {}
    omissions: list[dict] = []
    blocked: dict[str, list[str]] = {}
    for relative, path in files.items():
        component = component_for(relative, policy)
        decision = component.get("release", "block") if component else "block"
        if mode == "local-development":
            accepted[relative] = path
        elif decision == "exclude":
            omissions.append({"path": relative, "component": component["id"], "reason": "restricted component excluded by policy"})
        elif decision == "allow" and component.get("license") and component.get("evidence"):
            source_root = path.parents[len(Path(relative).parts) - 1].resolve()
            evidence = (source_root / component["evidence"]).resolve()
            if not evidence.is_relative_to(source_root) or not evidence.is_file():
                blocked.setdefault(component["id"], []).append(relative)
            else:
                accepted[relative] = path
        else:
            blocked.setdefault(component["id"] if component else "unclassified", []).append(relative)
    if blocked:
        summary = "; ".join(f"{name}: {len(paths)} file(s), e.g. {paths[0]}" for name, paths in sorted(blocked.items()))
        raise DistributionError(
            "Release blocked: redistribution authorization is unverified. " + summary
            + ". Restricted components are excluded automatically. "
            "Use --mode local-development only for local verification; it does not grant redistribution rights."
        )
    return accepted, omissions


def audit_resources(root: Path, staged: Path, policy: dict, mode: str) -> dict:
    """Check executable/resource completeness and distinguish pre-existing documentation gaps."""
    required = list(policy["required_resources"])
    if mode == "local-development":
        required += policy.get("local_only_required_resources", [])
    missing = [entry for entry in required if not (staged / entry).is_file()]
    errors: list[dict] = []
    existing_gaps: list[dict] = []
    checked_links = 0
    for document in sorted(staged.rglob("*.md")):
        relative = document.relative_to(staged)
        source_document = root / relative
        for match in re.finditer(r"\[[^\]\n]*\]\(([^)\n]+)\)", document.read_text(encoding="utf-8")):
            target = match.group(1).strip().split(' "', 1)[0].strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path or any(char in target for char in "{}*$<>"):
                continue
            target = unquote(parsed.path)
            if target.startswith("/"):
                continue
            source_target = (source_document.parent / target).resolve()
            staged_target = (document.parent / target).resolve()
            if not source_target.is_relative_to(root.resolve()):
                continue
            if not source_target.exists() and not Path(target).suffix and "/" not in target:
                continue
            checked_links += 1
            finding = {"document": relative.as_posix(), "target": target}
            if source_target.exists() and not staged_target.exists():
                errors.append(finding)
            elif not source_target.exists():
                existing_gaps.append(finding)
    syntax_errors = []
    for script in sorted(staged.rglob("*.py")):
        try:
            ast.parse(script.read_text(encoding="utf-8-sig"), filename=str(script))
        except (SyntaxError, UnicodeError) as exc:
            syntax_errors.append({"path": script.relative_to(staged).as_posix(), "error": str(exc)})
    if missing or errors or syntax_errors:
        raise DistributionError(json.dumps({"missing_required_resources": missing, "omitted_link_targets": errors, "python_syntax_errors": syntax_errors}, ensure_ascii=False))
    return {"required_resources": required, "checked_links": checked_links, "preexisting_documentation_gaps": existing_gaps, "python_syntax": "passed"}


def source_identity(root: Path) -> dict:
    def git(*args: str) -> str | None:
        try:
            result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result.stdout.strip() if result.returncode == 0 else None
    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain", "--untracked-files=normal"))}


def smoke(staged: Path) -> list[dict]:
    checks = []
    with tempfile.TemporaryDirectory(prefix="数学建模 smoke project ") as temporary:
        project = Path(temporary).resolve() / "项目 with spaces"
        project.mkdir()
        for action in ["init", "state", "complete"]:
            options = {"title": "Distribution smoke", "scope": "modeling", "profile": "short", "author_id": "distribution-smoke"} if action == "init" else {}
            command = [sys.executable, str(staged / "scripts" / "mathmodel.py"), action, "--project-root", str(project), "--options", json.dumps(options)]
            result = subprocess.run(command, cwd=staged, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"})
            try:
                report = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise DistributionError(f"Clean-directory {action} returned invalid JSON: {result.stdout} {result.stderr}") from exc
            if result.returncode or not report.get("ok") or (action == "complete" and report.get("done")):
                raise DistributionError(f"Clean-directory {action} smoke failed ({result.returncode}): {report} {result.stderr}")
            checks.append({"action": action, "returncode": result.returncode, "working_directory": "temporary Chinese and space path", "scope": "stdlib initialization/state/incomplete-project check; external converters and DSH mounting are separate checks"})
    return checks


def write_manifest(staged: Path, metadata: dict) -> dict:
    files = {
        path.relative_to(staged).as_posix(): {"sha256": sha256(path), "bytes": path.stat().st_size}
        for path in sorted(staged.rglob("*"))
        if path.is_file() and path.relative_to(staged).as_posix() != MANIFEST and "__pycache__" not in path.parts
    }
    manifest = {**metadata, "files": files}
    (staged / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_manifest(staged: Path) -> None:
    manifest = json.loads((staged / MANIFEST).read_text(encoding="utf-8"))
    actual = {path.relative_to(staged).as_posix() for path in staged.rglob("*") if path.is_file() and path.relative_to(staged).as_posix() != MANIFEST and "__pycache__" not in path.parts}
    if actual != set(manifest["files"]):
        raise DistributionError("Distribution manifest file inventory mismatch")
    for name, expected in manifest["files"].items():
        path = staged / name
        if not path.resolve().is_relative_to(staged.resolve()) or sha256(path) != expected["sha256"]:
            raise DistributionError(f"Distribution manifest hash mismatch: {name}")


def make_archive(staged: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(staged.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            info = zipfile.ZipInfo(path.relative_to(staged.parent).as_posix(), date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def build(root: Path, output: Path, mode: str = "release") -> dict:
    root = root.resolve()
    output = output.resolve()
    if mode not in {"release", "local-development"}:
        raise DistributionError(f"Unknown mode: {mode}")
    policy = read_policy(root)
    skill_sources, skill_omissions = authorize(source_files(root, policy), policy, mode)
    dsh_sources, dsh_omissions = authorize(source_files(root, policy, dsh=True), policy, mode)
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+.][A-Za-z0-9.]+)?", version):
        raise DistributionError("VERSION must contain a safe semantic version")
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    source = source_identity(root)
    source["content_sha256"] = hashlib.sha256("\n".join(f"{name}:{sha256(path)}" for name, path in sorted({**skill_sources, **dsh_sources}.items())).encode("utf-8")).hexdigest()
    metadata = {
        "schema_version": 1, "mode": mode, "redistribution_approved": mode == "release",
        "version": version, "source": source, "upstream": policy["upstream"],
        "compatibility": policy["compatibility"],
        "dependencies": {"requires_python": project["requires-python"], "core": project.get("dependencies", []), "optional": project.get("optional-dependencies", {})},
        "excluded_components": skill_omissions + dsh_omissions,
    }
    with tempfile.TemporaryDirectory(prefix="mathmodel 构建验证 ") as temporary:
        staging = Path(temporary).resolve()
        skill = staging / "math-modeling-skill"
        for relative, source_path in skill_sources.items():
            target = skill / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, target)
        if mode == "local-development":
            (skill / LOCAL_NOTICE).write_text("LOCAL DEVELOPMENT ONLY — NOT APPROVED FOR REDISTRIBUTION\nThis archive retains upstream/restricted materials for existing local development verification.\nNo license or redistribution permission is granted. See THIRD_PARTY_NOTICES.md and distribution-policy.json.\n", encoding="utf-8")
        audit = audit_resources(root, skill, policy, mode)
        checks = smoke(skill)
        skill_manifest = write_manifest(skill, {**metadata, "component": "skill", "resource_audit": audit, "smoke_tests": checks})
        verify_manifest(skill)
        dsh = staging / "math-modeling-agent"
        for relative, source_path in dsh_sources.items():
            target = dsh / Path(relative).relative_to("dsh-plugin/math-modeling-agent")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, target)
        if not dsh_sources:
            raise DistributionError("DSH adapter source is missing")
        bundled_skill = dsh / "skills" / "math-modeling"
        shutil.copytree(skill, bundled_skill, ignore=shutil.ignore_patterns("__pycache__"))
        package_skill = dsh / DSH_BUNDLE / "skills" / "math-modeling"
        shutil.copytree(skill, package_skill, ignore=shutil.ignore_patterns("__pycache__"))
        if mode == "local-development":
            shutil.copyfile(skill / LOCAL_NOTICE, dsh / LOCAL_NOTICE)
            shutil.copyfile(skill / LOCAL_NOTICE, dsh / DSH_BUNDLE / LOCAL_NOTICE)
        ui_package = dsh / "plugins" / "dsh-math-modeling-ui" / "package.json"
        ui_version = json.loads(ui_package.read_text(encoding="utf-8")).get("version") if ui_package.exists() else None
        package_checks = smoke(package_skill)
        write_manifest(dsh / DSH_BUNDLE, {**metadata, "component": "dsh-host-bundle", "resource_audit": audit, "smoke_tests": package_checks})
        dsh_manifest = write_manifest(dsh, {**metadata, "component": "dsh", "components": {"skill": version, "adapter": version, "ui": ui_version}, "resource_audit": audit, "smoke_tests": smoke(bundled_skill) + package_checks})
        verify_manifest(dsh)
        suffix = "-LOCAL-DEVELOPMENT" if mode == "local-development" else ""
        products = []
        for component, tree, manifest in [("skill", skill, skill_manifest), ("dsh", dsh, dsh_manifest)]:
            name = f"mathmodel-{component}-{version}{suffix}.zip"
            archive = staging / name
            make_archive(tree, archive)
            products.append({"name": name, "sha256": sha256(archive), "bytes": archive.stat().st_size, "file_count": len(manifest["files"]), "staged_archive": archive})
        output.mkdir(parents=True, exist_ok=True)
        for product in products:
            shutil.copyfile(product.pop("staged_archive"), output / product["name"])
        report = {**metadata, "artifacts": products, "resource_audit": audit, "smoke_tests": checks}
        report_path = output / f"mathmodel-{version}{suffix}-manifest.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["release", "local-development"], default="release")
    parser.add_argument("--source-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "dist")
    args = parser.parse_args(argv)
    try:
        report = build(args.source_root, args.output, args.mode)
    except (DistributionError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
