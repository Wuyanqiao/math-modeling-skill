"""Small validated baselines; examples, not automatic model selection."""

import numpy as np
from scipy.optimize import linprog


def linear_resource_allocation(values, constraints, capacities):
    """Maximize values @ x subject to constraints @ x <= capacities, x >= 0."""
    result = linprog(-np.asarray(values, dtype=float), A_ub=constraints,
                     b_ub=capacities, bounds=(0, None), method="highs")
    if not result.success:
        raise ValueError(f"Resource model is not solved: {result.message}")
    return {"allocation": result.x.tolist(), "objective": float(-result.fun),
            "slack": result.slack.tolist()}


def linear_trend_predict(train_time, train_values, future_time):
    """Fit only observed training times; callers keep future values out of fit."""
    time = np.asarray(train_time, dtype=float)
    values = np.asarray(train_values, dtype=float)
    future = np.asarray(future_time, dtype=float)
    if time.ndim != 1 or values.shape != time.shape or len(time) < 2:
        raise ValueError("Training time/value arrays must align and contain at least two points")
    if not np.all(np.diff(time) > 0) or np.any(future <= time[-1]):
        raise ValueError("Use increasing training times and strictly future prediction times")
    design = np.column_stack([np.ones(len(time)), time])
    coefficients, _, rank, _ = np.linalg.lstsq(design, values, rcond=None)
    if rank != 2:
        raise ValueError("Trend is not identifiable")
    predictions = coefficients[0] + coefficients[1] * future
    return {"intercept": float(coefficients[0]), "slope": float(coefficients[1]),
            "predictions": predictions.tolist()}


def topsis(matrix, weights, benefit):
    """Vector-normalized TOPSIS; return closeness and stable zero-based ranking."""
    data = np.asarray(matrix, dtype=float)
    weights = np.asarray(weights, dtype=float)
    benefit = np.asarray(benefit, dtype=bool)
    if data.ndim != 2 or weights.shape != (data.shape[1],) or benefit.shape != weights.shape:
        raise ValueError("One weight and direction are required per criterion")
    if not np.all(np.isfinite(data)) or not np.all(np.isfinite(weights)):
        raise ValueError("TOPSIS requires finite observations and weights")
    if np.any(weights < 0) or weights.sum() <= 0:
        raise ValueError("Weights must be nonnegative with a positive total")
    norms = np.linalg.norm(data, axis=0)
    if np.any(norms == 0):
        raise ValueError("Remove zero-norm criteria and document adjusted weights")
    scaled = data / norms * (weights / weights.sum())
    ideal = np.where(benefit, scaled.max(axis=0), scaled.min(axis=0))
    worst = np.where(benefit, scaled.min(axis=0), scaled.max(axis=0))
    to_ideal = np.linalg.norm(scaled - ideal, axis=1)
    to_worst = np.linalg.norm(scaled - worst, axis=1)
    total = to_ideal + to_worst
    if np.any(total == 0):
        raise ValueError("Identical weighted alternatives have no defined TOPSIS separation")
    closeness = to_worst / total
    return {"scores": closeness.tolist(),
            "ranking": np.argsort(-closeness, kind="stable").tolist()}
