"""Load one pinned SciVisAgentSkills package into an explicit local cache."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

REGISTRY = Path(__file__).resolve().parents[1] / "integrations/scivis-agent-skills/registry.json"


def load_skill(tool: str, cache_dir: Path, offline: bool = False) -> Path:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    package = registry["tools"][tool]
    base = cache_dir.expanduser().absolute()
    if any(path.is_symlink() for path in (base, *base.parents)):
        raise ValueError("Skill cache must not be a symlink")
    root = base / registry["commit"]
    for record in package["files"]:
        target = root / record["path"]
        if any(path.is_symlink() for path in (target, *target.parents)):
            raise ValueError("Skill cache contains a symlink")
        target.resolve().relative_to(root.resolve())
        if target.exists():
            if target.stat().st_size == record["bytes"] and hashlib.sha256(target.read_bytes()).hexdigest() == record["sha256"]:
                continue
            raise ValueError(f"Cached skill changed: {target}; use a new cache directory")
        if offline:
            raise FileNotFoundError(f"Skill is not cached: {target}")
        url = f'https://raw.githubusercontent.com/{registry["repository"]}/{registry["commit"]}/{record["path"]}'
        request = urllib.request.Request(url, headers={"User-Agent": "MathModel-Workbench"})
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read(record["bytes"] + 1)
        if len(content) != record["bytes"] or hashlib.sha256(content).hexdigest() != record["sha256"]:
            raise ValueError(f"Upstream content does not match pinned hash: {record['path']}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write(content)
    return root / package["entry"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool", required=True, choices=("paraview", "napari", "vmd", "ttk"))
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    try:
        entry = load_skill(args.tool, args.cache_dir, args.offline)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps({"tool": args.tool, "skill": str(entry), "verified": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
