"""Deterministic numerical primitives; run directly for the documented examples."""
import json

import numpy as np
from scipy.integrate import simpson, trapezoid
from scipy.interpolate import CubicSpline
from scipy.linalg import lstsq, solve
from scipy.optimize import root, root_scalar


def run_demo():
    def f(x):
        return x * x - 2.0

    bisect = root_scalar(f, bracket=(0.0, 2.0), method="bisect", xtol=1e-12)
    newton = root_scalar(f, x0=1.0, fprime=lambda x: 2 * x, method="newton", xtol=1e-12)
    system = root(lambda z: [z[0] + z[1] - 3, z[0] ** 2 + z[1] ** 2 - 5], [0.8, 2.2])
    if not (bisect.converged and newton.converged and system.success):
        raise RuntimeError("Root solver failed")
    knots = np.linspace(0, 1, 5)
    query = np.linspace(0, 1, 41)
    spline = CubicSpline(knots, knots ** 3, bc_type=((1, 0.0), (1, 3.0)), extrapolate=False)
    grid = np.linspace(0, 1, 101)
    matrix = np.array([[3.0, 1.0], [1.0, 2.0]])
    rhs = np.array([9.0, 8.0])
    solution = solve(matrix, rhs, assume_a="pos")
    design = np.column_stack((np.ones(5), np.arange(5)))
    coefficients, _, rank, singular_values = lstsq(design, 2 + 3 * np.arange(5))
    return {
        "bisect_root": float(bisect.root), "newton_root": float(newton.root),
        "scalar_residual": float(max(abs(f(bisect.root)), abs(f(newton.root)))),
        "system_root": system.x.tolist(),
        "system_residual": float(np.linalg.norm(system.fun, ord=np.inf)),
        "spline_max_error": float(np.max(np.abs(spline(query) - query ** 3))),
        "outside_domain_is_nan": bool(np.isnan(spline(1.1))),
        "trapezoid": float(trapezoid(grid ** 2, x=grid)),
        "simpson": float(simpson(grid ** 2, x=grid)),
        "linear_solution": solution.tolist(),
        "linear_residual": float(np.linalg.norm(matrix @ solution - rhs)),
        "least_squares": coefficients.tolist(), "rank": int(rank),
        "singular_values": singular_values.tolist(),
    }


if __name__ == "__main__":
    print(json.dumps(run_demo(), indent=2, allow_nan=False))
