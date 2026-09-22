#!/usr/bin/env python3
"""Run reproducible numeric fixtures. A pass is not a real-contest quality claim."""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "assets" / "algorithms"))
from baselines import linear_resource_allocation, linear_trend_predict, topsis


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(fixtures_path=None, budget_seconds=30):
    if budget_seconds <= 0:
        raise ValueError("budget_seconds must be positive")
    started = time.perf_counter()
    fixtures_path = Path(fixtures_path or Path(__file__).with_name("synthetic-v1.json"))
    fixtures = json.loads(fixtures_path.read_text(encoding="utf-8"))
    cases = []
    timings = {}
    functions = {"optimization": linear_resource_allocation,
                 "prediction": linear_trend_predict, "evaluation": topsis}
    for name, function in functions.items():
        fixture = fixtures[name]
        arguments = {key: value for key, value in fixture.items()
                     if key not in {"expected", "absolute_tolerance"}}
        case_started = time.perf_counter()
        actual = function(**arguments)
        timings[name] = round(time.perf_counter() - case_started, 6)
        checks = {key: bool(np.allclose(actual[key], expected, rtol=0,
                                        atol=fixture["absolute_tolerance"]))
                  for key, expected in fixture["expected"].items()}
        if name == "optimization":
            checks["feasible"] = bool(np.all(np.asarray(actual["slack"]) >= -fixture["absolute_tolerance"]))
        cases.append({"name": name, "actual": actual, "expected": fixture["expected"],
                      "absolute_tolerance": fixture["absolute_tolerance"],
                      "checks": checks, "passed": all(checks.values())})
    sources = [Path(__file__).resolve(), ROOT / "assets/algorithms/baselines.py"]
    report = {"schema_version": 1, "seed": fixtures["seed"],
              "stochastic": fixtures["stochastic"], "provenance": fixtures["provenance"],
              "input": {"path": str(fixtures_path.resolve()), "sha256": sha256(fixtures_path)},
              "code": [{"path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path)} for path in sources],
              "runtime": {"python": platform.python_version(), "platform": platform.platform(),
                          "dependencies": {name: importlib.metadata.version(name) for name in ("numpy", "scipy")}},
              "command": [sys.executable, str(Path(__file__).resolve()), "--fixtures", str(fixtures_path.resolve())],
              "cases": cases, "passed": all(case["passed"] for case in cases)}
    canonical = json.dumps(cases, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    report["results_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    elapsed = time.perf_counter() - started
    report["timing"] = {"elapsed_seconds": round(elapsed, 6), "cases_seconds": timings,
                        "budget_seconds": budget_seconds, "within_budget": elapsed <= budget_seconds,
                        "note": "Measured wall time; the budget is reported, not a process-kill deadline."}
    report["metrics"] = {"numeric_cases_passed": sum(case["passed"] for case in cases),
                         "numeric_cases_total": len(cases),
                         "numeric_success_rate": sum(case["passed"] for case in cases) / len(cases)}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path)
    parser.add_argument("--output", type=Path, help="Optional report path in your project")
    parser.add_argument("--budget-seconds", type=float, default=30, help="Reported wall-time target, not a hard timeout")
    args = parser.parse_args()
    report = run(args.fixtures, args.budget_seconds)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
