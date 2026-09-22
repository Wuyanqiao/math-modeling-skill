"""Finite inventory DP, discounted finite MDPs, and constrained scalar MPC."""
import json

import numpy as np
from scipy.optimize import minimize


def inventory_plan(demands, *, capacity=3, initial=0, order_cost=2., setup_cost=3., holding_cost=.5, shortage_cost=8.):
    """Order-before-demand, zero lead time, lost sales, and zero terminal salvage."""
    demands = np.asarray(demands)
    if demands.ndim != 1 or not demands.size or not np.issubdtype(demands.dtype, np.integer) or np.any(demands < 0):
        raise ValueError("Demand must be a nonempty vector of nonnegative integers")
    if not isinstance(capacity, int) or not isinstance(initial, int) or capacity < 0 or not 0 <= initial <= capacity:
        raise ValueError("Invalid integer capacity or initial stock")
    costs = np.array([order_cost, setup_cost, holding_cost, shortage_cost])
    if not np.isfinite(costs).all() or np.any(costs < 0):
        raise ValueError("Costs must be finite and nonnegative")
    values = np.zeros((demands.size + 1, capacity + 1))
    policy = np.zeros((demands.size, capacity + 1), dtype=int)
    for t in range(demands.size - 1, -1, -1):
        for stock in range(capacity + 1):
            orders = np.arange(capacity - stock + 1)
            remaining = np.maximum(stock + orders - demands[t], 0)
            shortage = np.maximum(demands[t] - stock - orders, 0)
            candidate = (order_cost * orders + setup_cost * (orders > 0) + holding_cost * remaining
                         + shortage_cost * shortage + values[t + 1, remaining])
            best = int(np.argmin(candidate))
            policy[t, stock], values[t, stock] = orders[best], candidate[best]
    stock, trajectory = initial, []
    for t, demand in enumerate(demands):
        order = int(policy[t, stock])
        next_stock = max(stock + order - int(demand), 0)
        trajectory.append({"period": t, "stock": stock, "order": order, "demand": int(demand),
                           "next_stock": next_stock, "shortage": max(int(demand) - stock - order, 0)})
        stock = next_stock
    return {"objective": float(values[0, initial]), "trajectory": trajectory, "policy": policy.tolist()}


def _mdp_inputs(transitions, costs, discount):
    transitions, costs = np.asarray(transitions, float), np.asarray(costs, float)
    if transitions.ndim != 3 or transitions.shape[0] != transitions.shape[2] or costs.shape != transitions.shape[:2]:
        raise ValueError("Use P[state, action, next_state] and cost[state, action]")
    if not np.isfinite(transitions).all() or not np.isfinite(costs).all() or np.any(transitions < 0):
        raise ValueError("Invalid probabilities or costs")
    if not np.allclose(transitions.sum(axis=2), 1, rtol=0, atol=1e-12) or not 0 <= discount < 1:
        raise ValueError("Require stochastic rows and 0 <= discount < 1")
    return transitions, costs


def value_iteration(transitions, costs, discount=.9, tolerance=1e-10, max_iterations=10000):
    transitions, costs = _mdp_inputs(transitions, costs, discount)
    if not np.isfinite(tolerance) or tolerance <= 0 or max_iterations < 1:
        raise ValueError("Invalid stopping budget")
    value = np.zeros(costs.shape[0])
    for iteration in range(max_iterations):
        q = costs + discount * np.einsum("sak,k->sa", transitions, value)
        updated = q.min(axis=1)
        difference = np.max(np.abs(updated - value))
        value = updated
        if difference <= tolerance:
            q = costs + discount * np.einsum("sak,k->sa", transitions, value)
            residual = float(np.max(np.abs(q.min(axis=1) - value)))
            return {"value": value.tolist(), "policy": q.argmin(axis=1).tolist(),
                    "bellman_residual": residual, "value_error_bound": residual / (1 - discount),
                    "iterations": iteration + 1}
    raise RuntimeError("Value iteration did not converge within its budget")


def policy_iteration(transitions, costs, discount=.9, max_iterations=1000):
    transitions, costs = _mdp_inputs(transitions, costs, discount)
    rows = np.arange(costs.shape[0])
    policy = np.zeros(costs.shape[0], dtype=int)
    for iteration in range(max_iterations):
        value = np.linalg.solve(np.eye(costs.shape[0]) - discount * transitions[rows, policy], costs[rows, policy])
        q = costs + discount * np.einsum("sak,k->sa", transitions, value)
        improved = q.argmin(axis=1)
        if np.array_equal(improved, policy):
            return {"value": value.tolist(), "policy": policy.tolist(), "iterations": iteration + 1,
                    "bellman_residual": float(np.max(np.abs(q.min(axis=1) - value)))}
        policy = improved
    raise RuntimeError("Policy iteration did not converge within its budget")


def mpc_scalar(initial=2., *, horizon=3, steps=5, control_bound=.6):
    """Re-solve a convex finite-horizon problem for x_next=x+u; apply first action."""
    if not np.isfinite([initial, control_bound]).all() or control_bound <= 0 or horizon < 1 or steps < 1:
        raise ValueError("Invalid initial state, horizon, step count, or control bound")
    state, states, controls = float(initial), [float(initial)], []
    for _ in range(steps):
        def objective(u):
            future = state + np.cumsum(u)
            return state ** 2 + np.dot(future[:-1], future[:-1]) + .1 * np.dot(u, u) + future[-1] ** 2

        result = minimize(objective, np.zeros(horizon), method="SLSQP", bounds=[(-control_bound, control_bound)] * horizon,
                          options={"ftol": 1e-12, "maxiter": 200})
        if not result.success or np.max(np.abs(result.x)) > control_bound + 1e-9:
            raise RuntimeError("MPC subproblem failed or returned an infeasible control")
        control = float(result.x[0])
        state += control
        controls.append(control)
        states.append(state)
    return {"states": states, "controls": controls, "horizon": horizon, "control_bound": control_bound}


def run_demo():
    transitions = [[[1, 0], [0, 1]], [[0, 1], [0, 1]]]
    costs = [[1, .2], [0, 1]]
    return {"inventory": inventory_plan([1, 2, 1]),
            "value_iteration": value_iteration(transitions, costs),
            "policy_iteration": policy_iteration(transitions, costs), "mpc": mpc_scalar()}


if __name__ == "__main__":
    print(json.dumps(run_demo(), indent=2, allow_nan=False))
