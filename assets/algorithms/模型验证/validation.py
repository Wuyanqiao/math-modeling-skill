"""Model checks with explicit scope; passing these checks is not independent review."""
import importlib.util
import inspect
import json
from pathlib import Path

import numpy as np
from scipy.stats import bootstrap, norm
from sklearn.base import clone
from sklearn.model_selection import GroupKFold, KFold, TimeSeriesSplit


def _group_labels(groups, n_samples):
    labels = np.asarray(groups)
    if labels.shape != (n_samples,):
        raise ValueError("Need one group ID per sample")
    if any(value is None or (isinstance(value, (float, np.floating)) and not np.isfinite(value)) for value in labels):
        raise ValueError("Group IDs cannot be missing or nonfinite")
    if labels.dtype.kind in "Mm" and np.isnat(labels).any():
        raise ValueError("Group IDs cannot contain NaT")
    return labels


def three_way_split(n_samples, *, strategy="random", groups=None, seed=42):
    """60/20/20 train/validation/test example; grouped fractions apply to groups."""
    if not isinstance(n_samples, int) or n_samples < 5:
        raise ValueError("Need at least five samples")
    indices = np.arange(n_samples)
    if strategy == "group":
        groups = _group_labels(groups, n_samples)
        units = np.unique(groups)
        if units.size < 5:
            raise ValueError("Need at least five independent groups for this example split")
        units = np.random.default_rng(seed).permutation(units)
        first, second = int(.6 * units.size), int(.8 * units.size)
        parts = [indices[np.isin(groups, subset)] for subset in (units[:first], units[first:second], units[second:])]
    elif strategy in {"random", "time"}:
        if strategy == "random":
            indices = np.random.default_rng(seed).permutation(indices)
        first, second = int(.6 * n_samples), int(.8 * n_samples)
        parts = [indices[:first], indices[first:second], indices[second:]]
    else:
        raise ValueError("strategy must be random, group, or time")
    return dict(zip(("train", "validation", "test"), parts))


def cv_splits(n_samples, *, strategy="kfold", n_splits=3, groups=None, times=None, gap=0, seed=42):
    """Create folds only on the development pool; keep the final test set outside."""
    indices = np.arange(n_samples)
    if strategy == "kfold":
        if groups is not None or times is not None:
            raise ValueError("Choose group/time validation for dependent observations")
        iterator = KFold(n_splits, shuffle=True, random_state=seed).split(indices)
    elif strategy == "group":
        groups = _group_labels(groups, n_samples)
        iterator = GroupKFold(n_splits).split(indices, groups=groups)
    elif strategy == "time":
        times = np.asarray(times, float)
        if times.shape != (n_samples,) or not np.isfinite(times).all() or np.any(np.diff(times) < 0):
            raise ValueError("Provide finite chronological timestamps")
        iterator = TimeSeriesSplit(n_splits=n_splits, gap=gap).split(indices)
    else:
        raise ValueError("strategy must be kfold, group, or time")
    folds = []
    for train, validation in iterator:
        if strategy == "time" and times[train].max() >= times[validation].min():
            raise ValueError("Time boundary splits a shared timestamp; aggregate/group by time first")
        folds.append((train, validation))
    return folds


def evaluate_regression_folds(estimator, features, target, folds):
    """Clone/fold-fit the entire estimator Pipeline; report actual validation errors."""
    features, target = np.asarray(features), np.asarray(target, float)
    if features.ndim != 2 or target.shape != (len(features),) or not np.isfinite(target).all():
        raise ValueError("Need a feature matrix and finite target vector")
    results = []
    for train, validation in folds:
        train, validation = np.asarray(train), np.asarray(validation)
        for part in (train, validation):
            if part.ndim != 1 or not part.size or not np.issubdtype(part.dtype, np.integer):
                raise ValueError("Split indices must be nonempty integer vectors")
            if part.min() < 0 or part.max() >= len(target) or len(np.unique(part)) != len(part):
                raise ValueError("Invalid split indices")
        if np.intersect1d(train, validation).size:
            raise ValueError("Training and validation indices overlap")
        fitted = clone(estimator).fit(features[train], target[train])
        predicted = np.asarray(fitted.predict(features[validation]), float)
        if predicted.shape != target[validation].shape or not np.isfinite(predicted).all():
            raise ValueError("Invalid model predictions")
        error = predicted - target[validation]
        results.append({"train_indices": train.tolist(), "validation_indices": validation.tolist(),
                        "rmse": float(np.sqrt(np.mean(error ** 2))), "mae": float(np.mean(np.abs(error)))})
    if not results:
        raise ValueError("Need at least one validation fold")
    return results


def bootstrap_mean_interval(observations, *, confidence=.95, resamples=4000, seed=42, sampling_unit="iid"):
    """Percentile bootstrap for an IID population mean, not a future observation."""
    values = np.asarray(observations, float)
    if values.ndim != 1 or values.size < 2 or not np.isfinite(values).all():
        raise ValueError("Need at least two finite observations")
    if sampling_unit != "iid":
        raise ValueError("This routine resamples IID units; use cluster/block bootstrap for dependent data")
    if not 0 < confidence < 1 or not isinstance(resamples, int) or resamples < 2:
        raise ValueError("Invalid confidence level or bootstrap budget")
    rng_option = "rng" if "rng" in inspect.signature(bootstrap).parameters else "random_state"
    result = bootstrap((values,), np.mean, vectorized=True, method="percentile", confidence_level=confidence,
                       n_resamples=resamples, **{rng_option: np.random.default_rng(seed)})
    low, high = float(result.confidence_interval.low), float(result.confidence_interval.high)
    if not np.isfinite([low, high]).all():
        raise RuntimeError("Bootstrap interval is undefined")
    return {"target": "population_mean", "interval_kind": "bootstrap_confidence_interval", "sampling_unit": sampling_unit,
            "method": "percentile", "estimate": float(values.mean()), "interval": [low, high],
            "confidence": confidence, "seed": seed, "resamples": resamples}


def _existing_module(filename):
    path = Path(__file__).resolve().parents[1] / filename
    spec = importlib.util.spec_from_file_location("validation_" + path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normal_uncertainty(observations, *, confidence=.95, observation_variance=1., prior_mean=0., prior_variance=1.):
    """Wrap the existing conjugate model, separating parameter and predictive targets."""
    if not 0 < confidence < 1:
        raise ValueError("Confidence must lie in (0, 1)")
    posterior = _existing_module("inverse-inference.py").normal_posterior(
        observations, observation_variance, prior_mean, prior_variance)
    z = norm.ppf((1 + confidence) / 2)
    mean = posterior["mean"]
    return {"model": "normal likelihood with known variance and normal prior", "probability": confidence,
            "parameter": {"target": "unknown_mean_parameter", "interval_kind": "posterior_credible_interval",
                          "interval": [float(mean - z * np.sqrt(posterior["variance"])), float(mean + z * np.sqrt(posterior["variance"]))]},
            "future_observation": {"target": "one_new_observation", "interval_kind": "posterior_predictive_interval",
                                   "interval": [float(mean - z * np.sqrt(posterior["predictive_variance"])), float(mean + z * np.sqrt(posterior["predictive_variance"]))]}}


def check_residuals(residuals, tolerances):
    """Each residual is a nonnegative violation, in its stated units/scaling."""
    if not residuals or residuals.keys() != tolerances.keys():
        raise ValueError("Every named constraint needs its own tolerance")
    checks = []
    for name, residual in residuals.items():
        tolerance = tolerances[name]
        if not np.isfinite([residual, tolerance]).all() or min(residual, tolerance) < 0:
            raise ValueError("Residuals and tolerances must be finite and nonnegative")
        checks.append({"name": name, "residual": float(residual), "tolerance": float(tolerance), "ok": residual <= tolerance})
    return {"ok": all(row["ok"] for row in checks), "constraints": checks}


def solver_certificate_check(certificate):
    """Check declared certificate consistency, not authenticity or the source equations.

    OPTIMAL may mean within solver gap tolerances. The independent reviewer must
    still match this certificate to a real run, objective and complete constraints.
    """
    required = {"solver", "solver_version", "raw_status", "status", "termination_reason", "sense",
                "objective", "best_bound", "optimality_scope", "gap_tolerance", "residuals", "tolerances"}
    missing = sorted(required - certificate.keys())
    if missing:
        return {"ok": False, "feasible_supported": False, "optimal_supported": False, "issues": ["Missing: " + ", ".join(missing)]}
    status = certificate["status"]
    issues = []
    if not all(isinstance(certificate[key], str) and certificate[key].strip()
               and certificate[key].strip().lower() not in {"unknown", "none"}
               for key in ("solver", "solver_version", "termination_reason")):
        issues.append("Solver identity/version and termination reason must be recorded")
    if certificate["raw_status"] is None or not str(certificate["raw_status"]).strip():
        issues.append("Raw solver status must be recorded")
    if status not in {"OPTIMAL", "FEASIBLE", "LOCAL_OPTIMUM", "INFEASIBLE", "UNKNOWN", "MODEL_INVALID", "UNBOUNDED"}:
        issues.append("Unrecognized normalized solver status")
    if certificate["sense"] not in {"min", "max"}:
        issues.append("Objective sense must be min or max")
    try:
        gap_tolerance = float(certificate["gap_tolerance"])
        if not np.isfinite(gap_tolerance) or gap_tolerance < 0:
            raise ValueError("Gap tolerance must be finite and nonnegative")
        for key in ("objective", "best_bound"):
            value = certificate[key]
            if value is not None and not np.isfinite(float(value)):
                raise ValueError(f"{key} must be finite when present")
    except (TypeError, ValueError) as error:
        return {"ok": False, "feasible_supported": False, "optimal_supported": False, "issues": issues + [str(error)]}
    if status not in {"OPTIMAL", "FEASIBLE", "LOCAL_OPTIMUM"}:
        if certificate["objective"] is not None:
            issues.append("Status without a feasible incumbent must keep objective null")
        return {"ok": not issues, "feasible_supported": False, "optimal_supported": False,
                "status": status, "issues": issues, "conclusion": "No feasible objective claim supported"}
    try:
        constraints = check_residuals(certificate["residuals"], certificate["tolerances"])
        if not constraints["ok"]:
            issues.append("Constraint residual exceeds its declared tolerance")
        objective = float(certificate["objective"])
        if not np.isfinite(objective):
            raise ValueError("Invalid objective")
        bound = certificate["best_bound"]
        gap = None if bound is None else (objective - float(bound) if certificate["sense"] == "min" else float(bound) - objective)
        if gap is not None and (not np.isfinite(gap) or gap < 0):
            issues.append("Objective bound has the wrong direction or is nonfinite")
    except (TypeError, ValueError) as error:
        return {"ok": False, "feasible_supported": False, "optimal_supported": False, "issues": issues + [str(error)]}
    feasible = not issues
    optimal = feasible and status == "OPTIMAL" and certificate["optimality_scope"] == "global" and gap is not None and abs(gap) <= gap_tolerance
    conclusion = ("Global optimum within the declared absolute gap tolerance" if optimal
                  else "Feasible candidate only; global optimality not supported" if feasible
                  else "Candidate fails certificate checks")
    return {"ok": not issues, "status": status, "feasible_supported": feasible, "optimal_supported": optimal,
            "absolute_gap": gap, "gap_tolerance": gap_tolerance, "conclusion": conclusion, "issues": issues}


def check_dimensions(left, right_terms):
    """Compare declared base-dimension exponents for every additive term."""
    def normalize(dimension):
        if not isinstance(dimension, dict) or not all(np.isfinite(value) for value in dimension.values()):
            raise ValueError("Dimension exponents must be finite mappings")
        return {key: float(value) for key, value in dimension.items() if value != 0}

    expected = normalize(left)
    if not right_terms:
        raise ValueError("Need at least one right-hand term")
    matches = [normalize(term) == expected for term in right_terms]
    return {"ok": all(matches), "term_matches": matches,
            "scope": "declared exponents only; actual unit conversions and physical equations need review"}


def refinement_report(steps, errors):
    """Observed orders from errors against an independent exact/reference solution."""
    steps, errors = np.asarray(steps, float), np.asarray(errors, float)
    if steps.ndim != 1 or len(steps) < 3 or steps.shape != errors.shape:
        raise ValueError("Need at least three matched refinement levels")
    if not np.isfinite([steps, errors]).all() or np.any(steps <= 0) or np.any(errors <= 0) or np.any(np.diff(steps) >= 0):
        raise ValueError("Require decreasing positive steps and positive finite reference errors")
    orders = np.log(errors[:-1] / errors[1:]) / np.log(steps[:-1] / steps[1:])
    return {"errors_decrease": bool(np.all(np.diff(errors) < 0)), "observed_orders": orders.tolist(),
            "steps": steps.tolist(), "errors": errors.tolist()}


def mechanistic_demo_checks():
    """Reuse the existing manufactured heat/FEM cases, without duplicating solvers."""
    mechanism = _existing_module("mechanistic-dynamics.py")
    heat_errors, fem_errors, boundary_residuals = [], [], {}
    for intervals in (10, 20, 40):
        _, u, report = mechanism.heat_fd(intervals)
        heat_errors.append(report["max_error"])
        _, _, fem_error = mechanism.poisson_fem(intervals)
        fem_errors.append(fem_error)
        boundary_residuals[f"heat_zero_boundary_n{intervals}"] = float(np.max(np.abs(u[[0, -1]])))
    return {"boundary": check_residuals(boundary_residuals, dict.fromkeys(boundary_residuals, 1e-12)),
            "heat": refinement_report([.1, .05, .025], heat_errors),
            "fem": refinement_report([.1, .05, .025], fem_errors),
            "dimension": check_dimensions({"temperature": 1, "time": -1}, [{"temperature": 1, "time": -1}])}


def linear_solver_demo():
    """A real bounded LP and its solver certificate; the analytic optimum is 10."""
    from scipy.optimize import linprog
    import scipy

    profit = np.array([3., 2.])
    constraints = np.array([[1., 1.], [1., 0.], [0., 1.]])
    capacity = np.array([4., 2., 3.])
    solved = linprog(-profit, A_ub=constraints, b_ub=capacity, bounds=(0, None), method="highs")
    if not solved.success or solved.status != 0:
        raise RuntimeError(solved.message)
    residuals = {"resource": float(np.maximum(constraints @ solved.x - capacity, 0).max()),
                 "nonnegative": float(np.maximum(-solved.x, 0).max()),
                 "dual_inequality_sign": float(np.maximum(solved.ineqlin.marginals, 0).max()),
                 "dual_lower_sign": float(np.maximum(-solved.lower.marginals, 0).max()),
                 "dual_stationarity": float(np.abs(-profit - constraints.T @ solved.ineqlin.marginals - solved.lower.marginals).max())}
    objective = float(profit @ solved.x)
    return {"solver": "scipy.optimize.linprog(method=highs)", "solver_version": scipy.__version__,
            "raw_status": int(solved.status), "status": "OPTIMAL", "termination_reason": solved.message,
            "sense": "max", "objective": objective, "best_bound": float(-capacity @ solved.ineqlin.marginals),
            "bound_source": "Dual objective from actual HiGHS marginals; zero lower bounds add no dual constant",
            "optimality_scope": "global", "gap_tolerance": 1e-9,
            "residuals": residuals, "tolerances": dict.fromkeys(residuals, 1e-9), "decision": solved.x.tolist()}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--certificate-output", type=Path, help="Write the actual LP solver certificate to this explicit path")
    args = parser.parse_args()
    certificate = linear_solver_demo()
    if args.certificate_output:
        args.certificate_output.parent.mkdir(parents=True, exist_ok=True)
        args.certificate_output.write_text(json.dumps(certificate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"bootstrap": bootstrap_mean_interval([1, 2, 3, 4, 5]),
                      "bayesian": normal_uncertainty([1, 2, 3]), "mechanistic": mechanistic_demo_checks(),
                      "solver_certificate": certificate, "solver_check": solver_certificate_check(certificate)}, indent=2))
