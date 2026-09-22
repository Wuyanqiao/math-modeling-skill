#!/usr/bin/env python3
"""Run the bundled workflow without relying on the caller's working directory."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mathmodel_runtime.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
