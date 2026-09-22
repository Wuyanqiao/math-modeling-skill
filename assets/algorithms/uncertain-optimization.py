"""Small deterministic equivalents with explicit information timing and uncertainty."""
import json

import numpy as np
from scipy.optimize import linprog


def two_stage_inventory(demands, probabilities, *, purchase_cost=2., holding_cost=1., shortage_cost=7., capacity=10.):
    """One shared order x before demand; scenario-specific leftovers and lost sales."""
    demands, probabilities = np.asarray(demands, float), np.asarray(probabilities, float)
    if demands.ndim != 1 or not demands.size or demands.shape != probabilities.shape:
        raise ValueError("Need paired demand and probability vectors")
    if not np.isfinite([demands, probabilities]).all() or np.any(demands < 0) or np.any(probabilities <= 0):
        raise ValueError("Use finite nonnegative demand and strictly positive scenario probabilities")
    if not np.isclose(probabilities.sum(), 1, rtol=0, atol=1e-12):
        raise ValueError("Probabilities must sum to one; do not silently normalize")
    parameters = [purchase_cost, holding_cost, shortage_cost, capacity]
    if not np.isfinite(parameters).all() or min(parameters) < 0 or holding_cost + shortage_cost <= 0:
        raise ValueError("Invalid costs or capacity")
    n = demands.size
    cost = np.concatenate([[purchase_cost], holding_cost * probabilities, shortage_cost * probabilities])
    # x - leftover_s + shortage_s = demand_s: x appears only once, hence nonanticipativity.
    balance = np.column_stack([np.ones(n), -np.eye(n), np.eye(n)])
    result = linprog(cost, A_eq=balance, b_eq=demands, bounds=[(0, capacity)] + [(0, None)] * (2 * n), method="highs")
    if not result.success:
        raise RuntimeError(result.message)
    return {"order": float(result.x[0]), "objective": float(result.fun),
            "leftover": result.x[1:1 + n].tolist(), "shortage": result.x[1 + n:].tolist(),
            "balance_residual": float(np.max(np.abs(balance @ result.x - demands))),
            "probabilities": probabilities.tolist(), "demands": demands.tolist()}


def box_robust_resource(profit, nominal, radius, capacity):
    """Max profit for nonnegative decisions, independent box-uncertain resource coefficients."""
    profit, nominal, radius = (np.asarray(value, float) for value in (profit, nominal, radius))
    if profit.ndim != 1 or not profit.size or nominal.shape != profit.shape or radius.shape != profit.shape:
        raise ValueError("Expected three matching vectors")
    if not np.isfinite([profit, nominal, radius]).all() or np.any(radius < 0) or np.any(nominal < radius):
        raise ValueError("Require finite coefficients, nonnegative radii, and nonnegative box lower bounds")
    if not np.isfinite(capacity) or capacity < 0:
        raise ValueError("Capacity must be finite and nonnegative")
    worst = nominal + radius
    result = linprog(-profit, A_ub=[worst], b_ub=[capacity], bounds=(0, None), method="highs")
    if not result.success:
        raise RuntimeError(result.message)
    return {"decision": result.x.tolist(), "objective": float(-result.fun),
            "worst_case_consumption": float(worst @ result.x), "capacity": float(capacity)}


def run_demo():
    return {"two_stage": two_stage_inventory([1., 3.], [.5, .5]),
            "robust": box_robust_resource([3., 2.], [1., 1.], [.5, .2], 3.)}


if __name__ == "__main__":
    print(json.dumps(run_demo(), indent=2, allow_nan=False))
