#!/usr/bin/env python3
"""Check importable DOCX dependencies and executable converters without installing anything."""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import shutil
import subprocess
import sys

REQUIRED_MODULES = {"docx": "python-docx", "lxml.etree": "lxml", "defusedxml.minidom": "defusedxml"}
OPTIONAL_BINARIES = {"pandoc": ["--version"]}


def check_environment(*, need_pandoc: bool = False) -> dict:
    modules = []
    for module, package in REQUIRED_MODULES.items():
        try:
            importlib.import_module(module)
            try:
                version = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                version = "unknown"
            modules.append({"module": module, "package": package, "ok": True, "version": version})
        except Exception as exc:
            modules.append({"module": module, "package": package, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    binaries = []
    for name, arguments in OPTIONAL_BINARIES.items():
        path = shutil.which(name)
        item = {"binary": name, "path": path, "required": need_pandoc, "ok": False}
        if path:
            try:
                run = subprocess.run([path, *arguments], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
                item.update(ok=run.returncode == 0, returncode=run.returncode, version=run.stdout.splitlines()[0] if run.stdout else "")
            except (OSError, subprocess.TimeoutExpired) as exc:
                item["error"] = str(exc)
        binaries.append(item)
    return {"ok": all(item["ok"] for item in modules) and all(item["ok"] for item in binaries if item["required"]), "python": sys.version.split()[0], "modules": modules, "binaries": binaries}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Machine-readable dependency results")
    parser.add_argument("--need-pandoc", action="store_true", help="Require working Pandoc for document conversion")
    args = parser.parse_args(argv)
    report = check_environment(need_pandoc=args.need_pandoc)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for item in report["modules"]:
            print(f"{'OK' if item['ok'] else 'MISSING/BROKEN'}: {item['package']} {item.get('version', item.get('error', ''))}")
        for item in report["binaries"]:
            print(f"{'OK' if item['ok'] else 'MISSING/BROKEN'}: {item['binary']} ({'required' if item['required'] else 'optional'})")
        if not all(item["ok"] for item in report["modules"]):
            print('安装: python -m pip install "python-docx>=1.1,<2" "lxml>=5,<7" "defusedxml>=0.7.1,<1"')
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
