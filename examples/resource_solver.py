"""Small synthetic optimization example; exact answer independently known."""

import argparse
import csv
import json
from pathlib import Path

import numpy as np
from scipy.optimize import linprog


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--figures", action="store_true")
    args = parser.parse_args()
    case = json.loads(Path("data/case.json").read_text(encoding="utf-8"))
    solution = linprog(-np.array(case["objective"]), A_ub=case["A"], b_ub=case["b"], bounds=(0, None), method="highs")
    if not solution.success:
        raise RuntimeError(solution.message)
    np.testing.assert_allclose(solution.x, [2, 2], atol=1e-9, rtol=0)
    np.testing.assert_allclose(-solution.fun, 10, atol=1e-9, rtol=0)
    usage = np.array(case["A"]) @ solution.x
    if np.any(usage - case["b"] > 1e-9) or np.any(solution.x < -1e-9):
        raise ValueError("Returned allocation violates the model constraints")
    Path("results").mkdir(exist_ok=True)
    with Path("results/solution.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["x", "y", "objective"])
        writer.writerow([*solution.x, -solution.fun])
    print(json.dumps({"x": solution.x.tolist(), "objective": -solution.fun, "max_constraint_violation": max(0.0, float(np.max(np.array(case["A"]) @ solution.x - case["b"]))) }))
    if args.figures:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon
        plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "svg.fonttype": "none"})
        Path("figures").mkdir(exist_ok=True)
        fig, ax = plt.subplots(figsize=(5.2, 4.2), layout="constrained")
        ax.add_patch(Polygon([[0, 0], [2, 0], [2, 2], [1, 3], [0, 3]], color="#24938a", alpha=.22))
        ax.plot([0, 4], [4, 0], color="#466388", label="x + y = 4")
        ax.axvline(2, color="#98704a", linestyle="--", label="x = 2")
        ax.axhline(3, color="#6d648d", linestyle=":", label="y = 3")
        ax.scatter([solution.x[0]], [solution.x[1]], color="#b84143", zorder=5, s=55)
        ax.annotate(f"Optimum ({solution.x[0]:g}, {solution.x[1]:g}), value {-solution.fun:g}", solution.x, xytext=(.25, 3.65), arrowprops={"arrowstyle": "->"})
        ax.set(xlim=(0, 4), ylim=(0, 4), xlabel="Decision x", ylabel="Decision y", title="Feasible region and optimum")
        ax.legend(loc="upper right", fontsize=8)
        for extension in ("svg", "png"):
            fig.savefig("figures/result_q1_region." + extension, dpi=300)
        plt.close(fig)
        fig, ax = plt.subplots(figsize=(5.2, 3.6), layout="constrained")
        positions = np.arange(3)
        ax.bar(positions - .18, usage, width=.36, color="#24938a", label="Used")
        ax.bar(positions + .18, case["b"], width=.36, color="#abb9c9", label="Capacity")
        ax.set(xticks=positions, xticklabels=["Shared resource", "x capacity", "y capacity"], ylabel="Units", title="Resource use at the optimum")
        ax.legend()
        for extension in ("svg", "png"):
            fig.savefig("figures/result_q1_usage." + extension, dpi=300)
        plt.close(fig)


if __name__ == "__main__":
    main()
