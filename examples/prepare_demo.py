"""Create an isolated demo project; no synthetic reviewer PASS is recorded."""

import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mathmodel_runtime.engine import dispatch


def prepare(project):
    project = Path(project).resolve()
    if project.exists() and any(project.iterdir()):
        raise ValueError("Choose an empty project directory outside the Skill repository")
    project.mkdir(parents=True, exist_ok=True)
    result = dispatch({"action": "init", "project_root": str(project), "skill_root": str(ROOT),
                       "scope": "full", "profile": "short", "paper_format": "latex", "author_id": "demo-author",
                       "title": "Synthetic resource allocation verification"})
    (project / "data").mkdir()
    case = {"provenance": "Deterministic synthetic test, not contest or business data", "objective": [3, 2], "A": [[1, 1], [1, 0], [0, 1]], "b": [4, 2, 3]}
    (project / "data/case.json").write_text(json.dumps(case, indent=2), encoding="utf-8")
    (project / "题目分析报告.md").write_text("# Resource allocation model\n\nThis is a synthetic verification case. Maximize 3x+2y subject to x+y<=4, x<=2, y<=3 and nonnegative x,y.\n\nVariables are continuous divisible resource amounts; objective coefficients are fixed, deterministic and additive. There is no claim of real-world generalization.\n\nValidation: enumerate vertices (0,0),(2,0),(2,2),(1,3),(0,3); objective values 0,6,10,9,6 give unique optimum (2,2), value 10. Confirm constraint residuals and compare scipy HiGHS output within 1e-9.\n", encoding="utf-8")
    (project / "术语表格.md").write_text("|Symbol|Meaning|Unit|\n|---|---|---|\n|x|First allocation|resource unit|\n|y|Second allocation|resource unit|\n|z=3x+2y|Linear objective|value unit|\n", encoding="utf-8")
    shutil.copy2(ROOT / "examples/resource_solver.py", project / "solver.py")
    return {"project_root": str(project), "project_id": result["project"]["project_id"], "next": "Request gate-prepare M1, then obtain an actual independent review; do not invent a receipt."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root", type=Path)
    print(json.dumps(prepare(parser.parse_args().project_root), ensure_ascii=False))
