"""Parameter recovery, regularization, and analytic Bayesian checks on synthetic data."""
import json

import numpy as np
from scipy.linalg import lstsq
from scipy.optimize import least_squares


def fit_decay(times, observations):
    times, observations = np.asarray(times, float), np.asarray(observations, float)
    if times.ndim != 1 or times.shape != observations.shape or times.size < 2:
        raise ValueError("Need paired time and observation vectors")
    if not np.isfinite([times, observations]).all() or np.any(times < 0):
        raise ValueError("Require finite observations and nonnegative times")
    result = least_squares(lambda p: p[0] * np.exp(-p[1] * times) - observations,
                           [1., .5], bounds=([0., 0.], [10., 5.]), method="trf",
                           ftol=1e-12, xtol=1e-12, gtol=1e-12)
    if not result.success:
        raise RuntimeError(result.message)
    singular_values = np.linalg.svd(result.jac, compute_uv=False)
    return {"parameters": result.x.tolist(), "residual_norm": float(np.linalg.norm(result.fun)),
            "jacobian_rank": int(np.linalg.matrix_rank(result.jac)),
            "singular_values": singular_values.tolist()}


def tikhonov(matrix, observations, strength, reference=None):
    """Solve ||A*x-y||^2 + strength*||x-reference||^2 by augmented least squares."""
    matrix, observations = np.asarray(matrix, float), np.asarray(observations, float)
    if matrix.ndim != 2 or observations.shape != (matrix.shape[0],):
        raise ValueError("Incompatible matrix and observation shapes")
    reference = np.zeros(matrix.shape[1]) if reference is None else np.asarray(reference, float)
    if reference.shape != (matrix.shape[1],) or not np.isfinite(strength) or strength < 0:
        raise ValueError("Require nonnegative strength and a matching reference")
    if not (np.isfinite(matrix).all() and np.isfinite(observations).all() and np.isfinite(reference).all()):
        raise ValueError("Data must be finite")
    augmented = np.vstack([matrix, np.sqrt(strength) * np.eye(matrix.shape[1])])
    target = np.concatenate([observations, np.sqrt(strength) * reference])
    return lstsq(augmented, target)[0]


def normal_posterior(observations, observation_variance=1., prior_mean=0., prior_variance=1.):
    """Known-variance normal likelihood and proper normal prior."""
    observations = np.asarray(observations, float)
    if observations.ndim != 1 or not observations.size or not np.isfinite(observations).all():
        raise ValueError("Need a nonempty finite observation vector")
    if not np.isfinite([observation_variance, prior_mean, prior_variance]).all() or min(observation_variance, prior_variance) <= 0:
        raise ValueError("Variances must be positive and finite")
    variance = 1 / (1 / prior_variance + observations.size / observation_variance)
    mean = variance * (prior_mean / prior_variance + observations.sum() / observation_variance)
    return {"mean": float(mean), "variance": float(variance),
            "predictive_variance": float(variance + observation_variance)}


def metropolis_normal(mean, variance, *, seed=42, draws=8000, warmup=2000):
    """Four educational random-walk chains for a known target; no convergence certification."""
    if not np.isfinite([mean, variance]).all() or variance <= 0 or draws < 2 or warmup < 0:
        raise ValueError("Invalid normal target or sampling budget")
    rng = np.random.default_rng(seed)
    standard_deviation = np.sqrt(variance)
    state = mean + standard_deviation * np.array([-4., -1., 1., 4.])
    samples = np.empty((4, draws))
    accepted = np.zeros(4)
    for step in range(warmup + draws):
        proposed = state + rng.normal(0, 2 * standard_deviation, size=4)
        log_ratio = -((proposed - mean) ** 2 - (state - mean) ** 2) / (2 * variance)
        accept = np.log(rng.uniform(size=4)) < log_ratio
        state[accept] = proposed[accept]
        if step >= warmup:
            samples[:, step - warmup] = state
            accepted += accept
    return samples, accepted / draws


def run_demo():
    times = np.linspace(0, 4, 21)
    fit = fit_decay(times, 2 * np.exp(-.7 * times))
    rank_deficient = fit_decay(np.zeros(4), np.full(4, 2.))
    regularized = tikhonov([[1, 0], [0, 1]], [2, 4], 1.)
    posterior = normal_posterior([1, 2, 3])
    draws, acceptance = metropolis_normal(posterior["mean"], posterior["variance"])
    return {"fit": fit, "unidentifiable_rank": rank_deficient["jacobian_rank"],
            "regularized_solution": regularized.tolist(), "posterior": posterior,
            "mcmc_seed": 42, "mcmc_chain_means": draws.mean(axis=1).tolist(),
            "mcmc_variance": float(draws.var()), "mcmc_acceptance": acceptance.tolist(),
            "mcmc_diagnostics": "analytic-target smoke check only; production rank-Rhat/ESS required"}


if __name__ == "__main__":
    print(json.dumps(run_demo(), indent=2, allow_nan=False))
