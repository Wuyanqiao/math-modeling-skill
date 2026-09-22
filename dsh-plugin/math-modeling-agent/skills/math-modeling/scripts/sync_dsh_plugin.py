#!/usr/bin/env python3
"""Synchronize the complete local Skill into DSH. Default/check mode never writes."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from build_distribution import DSH_BUNDLE, DistributionError, LOCAL_NOTICE, REPO_ROOT, excluded, read_policy, sha256, source_files

DEFAULT_DST = REPO_ROOT / "dsh-plugin" / "math-modeling-agent" / "skills" / "math-modeling"
BUNDLE_DST = REPO_ROOT / "dsh-plugin" / "math-modeling-agent" / DSH_BUNDLE / "skills" / "math-modeling"
NOTICE = "LOCAL DEVELOPMENT ONLY — NOT APPROVED FOR REDISTRIBUTION\nSee distribution-policy.json and THIRD_PARTY_NOTICES.md.\n"


def synchronize(root: Path, destination: Path, *, apply: bool = False) -> dict:
    root = root.resolve()
    base = root / "dsh-plugin" / "math-modeling-agent"
    permitted = {base / "skills/math-modeling", base / DSH_BUNDLE / "skills/math-modeling"}
    expected = destination.absolute()
    if expected not in permitted or destination.resolve() != expected:
        raise DistributionError("Synchronization target must be the checkout's generated DSH skills/math-modeling directory")
    policy = read_policy(root)
    sources = source_files(root, policy)
    changes = []
    existing = {}
    if destination.exists():
        for path in destination.rglob("*"):
            if path.is_symlink() or not path.resolve().is_relative_to(expected):
                raise DistributionError(f"Refusing linked synchronization target: {path}")
            if path.is_file() and not excluded(path.relative_to(destination), policy):
                existing[path.relative_to(destination).as_posix()] = path
    for relative, source in sources.items():
        target = destination / relative
        if target.is_file() and sha256(source) == sha256(target):
            continue
        changes.append({"action": "copy", "path": relative})
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    for relative, path in existing.items():
        if relative not in sources and relative != LOCAL_NOTICE:
            changes.append({"action": "remove", "path": relative})
            if apply:
                path.unlink()
    notice = destination / LOCAL_NOTICE
    if not notice.is_file() or notice.read_text(encoding="utf-8") != NOTICE:
        changes.append({"action": "copy", "path": LOCAL_NOTICE})
        if apply:
            notice.parent.mkdir(parents=True, exist_ok=True)
            notice.write_text(NOTICE, encoding="utf-8")
    return {"mode": "apply" if apply else "check", "redistribution_approved": False, "changes": changes, "file_count": len(sources)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="Update the generated local knowledge/tool mirror")
    group.add_argument("--check", action="store_true", help="Report drift without creating or changing any files (default)")
    args = parser.parse_args(argv)
    try:
        reports = [synchronize(REPO_ROOT, destination, apply=args.apply) for destination in (DEFAULT_DST, BUNDLE_DST)]
    except (DistributionError, OSError) as exc:
        print(f"Synchronization failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"legacy_preset": reports[0], "host_bundle": reports[1]}, ensure_ascii=False, indent=2))
    return 0 if args.apply or not any(report["changes"] for report in reports) else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
