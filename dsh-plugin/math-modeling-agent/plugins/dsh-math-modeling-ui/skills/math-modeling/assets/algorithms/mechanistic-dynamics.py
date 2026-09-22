"""Known-solution ODE, stable finite difference heat flow, and 1-D P1 FEM."""
import json

import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import solve_banded


def heat_fd(intervals=40, final_time=.05, alpha=1.0, cfl=.4):
    """u_t=alpha*u_xx, u(0,t)=u(1,t)=0, u(x,0)=sin(pi*x)."""
    if not isinstance(intervals, int) or intervals < 2:
        raise ValueError("intervals must be an integer >= 2")
    if not np.isfinite([final_time, alpha, cfl]).all() or final_time <= 0 or alpha <= 0 or not 0 < cfl <= .5:
        raise ValueError("Require positive time/diffusivity and 0 < CFL <= 0.5")
    x = np.linspace(0, 1, intervals + 1)
    dx = 1 / intervals
    steps = int(np.ceil(final_time * alpha / (cfl * dx ** 2)))
    dt = final_time / steps
    ratio = alpha * dt / dx ** 2
    u = np.sin(np.pi * x)
    u[[0, -1]] = 0
    for _ in range(steps):
        u[1:-1] = u[1:-1] + ratio * (u[2:] - 2 * u[1:-1] + u[:-2])
    exact = np.exp(-alpha * np.pi ** 2 * final_time) * np.sin(np.pi * x)
    return x, u, {"steps": steps, "dt": dt, "cfl": ratio, "max_error": float(np.max(np.abs(u - exact)))}


def poisson_fem(intervals=20):
    """P1 elements for -u''=2 on (0,1), zero Dirichlet; exact u=x*(1-x)."""
    if not isinstance(intervals, int) or intervals < 2:
        raise ValueError("intervals must be an integer >= 2")
    h = 1 / intervals
    bands = np.zeros((3, intervals - 1))
    bands[0, 1:] = -1 / h
    bands[1, :] = 2 / h
    bands[2, :-1] = -1 / h
    u = np.zeros(intervals + 1)
    u[1:-1] = solve_banded((1, 1), bands, np.full(intervals - 1, 2 * h))
    x = np.linspace(0, 1, intervals + 1)
    midpoints = (x[:-1] + x[1:]) / 2
    midpoint_error = np.max(np.abs((u[:-1] + u[1:]) / 2 - midpoints * (1 - midpoints)))
    return x, u, float(midpoint_error)


def run_demo():
    times = np.linspace(0, 1, 21)
    decay = solve_ivp(lambda t, y: -2 * y, (0, 1), [1.0], t_eval=times, rtol=1e-9, atol=1e-11)
    stiff_errors = {}
    for method in ("Radau", "BDF"):
        result = solve_ivp(lambda t, y: -1000 * (y - np.cos(t)) - np.sin(t), (0, 1), [1.0],
                           method=method, t_eval=times, rtol=1e-8, atol=1e-10)
        if not result.success or result.t[-1] != 1:
            raise RuntimeError(f"{method} failed to reach final time")
        stiff_errors[method] = float(np.max(np.abs(result.y[0] - np.cos(times))))
    if not decay.success or decay.t[-1] != 1:
        raise RuntimeError("ODE integration failed")
    _, _, coarse = heat_fd(20)
    _, _, fine = heat_fd(40)
    _, _, fem_coarse = poisson_fem(10)
    _, _, fem_fine = poisson_fem(20)
    return {"decay_max_error": float(np.max(np.abs(decay.y[0] - np.exp(-2 * times)))),
            "stiff_max_error": stiff_errors, "heat_coarse": coarse, "heat_fine": fine,
            "fem_midpoint_errors": [fem_coarse, fem_fine]}


if __name__ == "__main__":
    print(json.dumps(run_demo(), indent=2, allow_nan=False))
