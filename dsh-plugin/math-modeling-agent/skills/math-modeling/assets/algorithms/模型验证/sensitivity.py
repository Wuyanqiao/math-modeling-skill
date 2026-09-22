"""Local derivatives and optional SALib global checks; no silent substitute method."""
import importlib
import json

import numpy as np


def local_sensitivity(model, point, steps):
    point, steps = np.asarray(point, float), np.asarray(steps, float)
    if point.ndim != 1 or not point.size or steps.shape != point.shape or not np.isfinite([point, steps]).all() or np.any(steps <= 0):
        raise ValueError("Need finite point and positive per-parameter steps")
    value = float(model(point.copy()))
    gradient = np.empty(len(point))
    for index, step in enumerate(steps):
        change = np.zeros(len(point))
        change[index] = step
        gradient[index] = (float(model(point + change)) - float(model(point - change))) / (2 * step)
    if not np.isfinite(value) or not np.isfinite(gradient).all():
        raise ValueError("Model values and derivatives must be finite")
    return {"point": point.tolist(), "steps": steps.tolist(), "value": value, "gradient": gradient.tolist(),
            "elasticities": None if value == 0 else (gradient * point / value).tolist()}


def _problem(names, bounds):
    bounds = np.asarray(bounds, float)
    if not names or len(set(names)) != len(names) or not all(isinstance(name, str) and name for name in names):
        raise ValueError("Need unique nonempty parameter names")
    if bounds.shape != (len(names), 2) or not np.isfinite(bounds).all() or np.any(bounds[:, 1] <= bounds[:, 0]):
        raise ValueError("Need finite increasing bounds for each independent uniform parameter")
    return {"num_vars": len(names), "names": list(names), "bounds": bounds.tolist()}


def _salib(module):
    try:
        return importlib.import_module("SALib." + module)
    except ImportError as error:
        raise RuntimeError("SALib is unavailable; install the optional sensitivity dependency in the project environment") from error


def _evaluate(model, samples):
    values = np.asarray([model(row.copy()) for row in samples], float)
    if values.shape != (len(samples),) or not np.isfinite(values).all():
        raise ValueError("Model must return one finite scalar for every sampled parameter vector")
    if np.var(values) == 0:
        raise ValueError("Constant output has no defined variance-based sensitivity indices")
    return values


def morris_screen(model, names, bounds, *, trajectories=64, levels=4, seed=42):
    problem = _problem(names, bounds)
    if not isinstance(trajectories, int) or trajectories < 2 or not isinstance(levels, int) or levels < 4 or levels % 2:
        raise ValueError("Need at least two trajectories and an even grid level count >= 4")
    samples = _salib("sample.morris").sample(problem, trajectories, num_levels=levels, seed=seed)
    result = _salib("analyze.morris").analyze(problem, samples, _evaluate(model, samples), num_levels=levels, seed=seed)
    return {"method": "Morris", "names": names, "evaluations": len(samples), "seed": seed,
            **{key: result[key].tolist() for key in ("mu", "mu_star", "sigma", "mu_star_conf")}}


def sobol_indices(model, names, bounds, *, base_samples=1024, seed=42):
    problem = _problem(names, bounds)
    if not isinstance(base_samples, int) or base_samples < 2 or base_samples & (base_samples - 1):
        raise ValueError("Use a power-of-two Sobol base sample count")
    samples = _salib("sample.sobol").sample(problem, base_samples, calc_second_order=False, scramble=True, seed=seed)
    result = _salib("analyze.sobol").analyze(problem, _evaluate(model, samples), calc_second_order=False, seed=seed)
    return {"method": "Sobol", "names": names, "evaluations": len(samples), "seed": seed,
            "input_assumption": "independent uniforms on the supplied bounds", "second_order_computed": False,
            **{key: result[key].tolist() for key in ("S1", "ST", "S1_conf", "ST_conf")}}


if __name__ == "__main__":
    def additive(x):
        return x[0] + 2 * x[1]

    print(json.dumps({"local": local_sensitivity(additive, [1., 1.], [1e-4, 1e-4]),
                      "morris": morris_screen(additive, ["x1", "x2"], [[0, 1], [0, 1]]),
                      "sobol": sobol_indices(additive, ["x1", "x2"], [[0, 1], [0, 1]])}, indent=2))
