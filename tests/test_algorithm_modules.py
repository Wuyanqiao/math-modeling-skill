"""Independent analytic, exhaustive, and convergence checks for six teaching modules."""
import importlib.util
import itertools
from pathlib import Path
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def load_module(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "assets" / "algorithms" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


numeric = load_module("numerical-foundations")
geometry = load_module("computational-geometry")
mechanics = load_module("mechanistic-dynamics")
inverse = load_module("inverse-inference")
dynamic = load_module("dynamic-control")
uncertain = load_module("uncertain-optimization")


class NumericalModuleTests(unittest.TestCase):
    def test_roots_and_linear_algebra_against_analytic_solutions(self):
        result = numeric.run_demo()
        self.assertAlmostEqual(result["bisect_root"], np.sqrt(2), delta=2e-12)
        self.assertAlmostEqual(result["newton_root"], np.sqrt(2), delta=2e-12)
        self.assertLess(result["scalar_residual"], 1e-11)
        np.testing.assert_allclose(result["system_root"], [1, 2], rtol=0, atol=1e-8)
        self.assertLess(result["system_residual"], 1e-8)
        np.testing.assert_allclose(result["linear_solution"], [2, 3], rtol=0, atol=1e-12)
        self.assertLess(result["linear_residual"], 1e-12)
        np.testing.assert_allclose(result["least_squares"], [2, 3], rtol=0, atol=1e-12)
        self.assertEqual(result["rank"], 2)

    def test_interpolation_domain_and_quadrature_accuracy(self):
        result = numeric.run_demo()
        self.assertLess(result["spline_max_error"], 1e-12)
        self.assertTrue(result["outside_domain_is_nan"])
        self.assertAlmostEqual(result["simpson"], 1 / 3, delta=1e-12)
        self.assertAlmostEqual(result["trapezoid"] - 1 / 3, 1 / 60000, delta=1e-12)


class GeometryModuleTests(unittest.TestCase):
    def test_metric_invariance_and_partition_area(self):
        result = geometry.run_demo()
        self.assertLess(result["distance_invariance_error"], 1e-12)
        np.testing.assert_allclose(result["intersection"], [.5, .5], rtol=0, atol=1e-12)
        self.assertAlmostEqual(result["hull_area"], 1)
        self.assertAlmostEqual(result["triangulated_area"], 1)
        self.assertGreater(result["minimum_triangle_area"], 0)
        self.assertTrue(result["center_voronoi_is_bounded"])
        self.assertEqual(result["nearest_index"], 0)
        self.assertAlmostEqual(result["nearest_distance"], np.sqrt(.02))

    def test_segment_domains_and_degeneracy(self):
        self.assertIsNone(geometry.segment_intersection([0, 0], [1, 0], [0, 1], [1, 1]))
        self.assertIsNone(geometry.segment_intersection([0, 0], [1, 0], [2, -1], [2, 1]))
        self.assertIsNone(geometry.segment_intersection([0, 0], [1, 0], [2, 0], [3, 0]))
        np.testing.assert_allclose(geometry.segment_intersection([0, 0], [1, 0], [1, 0], [2, 0]), [1, 0])
        with self.assertRaisesRegex(ValueError, "overlap"):
            geometry.segment_intersection([0, 0], [2, 0], [1, 0], [3, 0])
        with self.assertRaisesRegex(ValueError, "Degenerate"):
            geometry.segment_intersection([0, 0], [0, 0], [1, 0], [2, 0])


class MechanisticModuleTests(unittest.TestCase):
    def test_ode_integrators_recover_manufactured_solutions(self):
        result = mechanics.run_demo()
        self.assertLess(result["decay_max_error"], 1e-8)
        self.assertLess(result["stiff_max_error"]["Radau"], 1e-6)
        self.assertLess(result["stiff_max_error"]["BDF"], 1e-6)

    def test_heat_boundaries_and_refinement(self):
        _, coarse_u, coarse = mechanics.heat_fd(20)
        _, fine_u, fine = mechanics.heat_fd(40)
        self.assertEqual(float(coarse_u[0]), 0)
        self.assertEqual(float(coarse_u[-1]), 0)
        self.assertGreaterEqual(float(fine_u.min()), 0)
        self.assertLess(float(fine_u.max()), 1)
        self.assertLessEqual(fine["cfl"], .5)
        self.assertLess(fine["max_error"], coarse["max_error"] / 3.5)
        self.assertLess(fine["max_error"], 3e-4)

    def test_heat_rejects_unstable_step_and_invalid_domain(self):
        for kwargs in ({"cfl": .6}, {"alpha": 0}, {"final_time": -1}, {"intervals": 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                mechanics.heat_fd(**kwargs)

    def test_fem_checks_field_between_nodes_not_only_nodal_fit(self):
        x, nodal, coarse_error = mechanics.poisson_fem(10)
        _, _, fine_error = mechanics.poisson_fem(20)
        np.testing.assert_allclose(nodal, x * (1 - x), rtol=0, atol=1e-12)
        self.assertAlmostEqual(coarse_error, .1 ** 2 / 4, delta=1e-12)
        self.assertAlmostEqual(coarse_error / fine_error, 4, delta=1e-8)


class InverseModuleTests(unittest.TestCase):
    def test_bounded_fit_recovers_parameters_and_exposes_unidentifiability(self):
        times = np.linspace(0, 4, 21)
        result = inverse.fit_decay(times, 2 * np.exp(-.7 * times))
        np.testing.assert_allclose(result["parameters"], [2, .7], rtol=0, atol=1e-8)
        self.assertLess(result["residual_norm"], 1e-8)
        self.assertEqual(result["jacobian_rank"], 2)
        self.assertEqual(inverse.fit_decay(np.zeros(4), np.full(4, 2.))["jacobian_rank"], 1)

    def test_regularization_has_analytic_solution_and_rejects_negative_penalty(self):
        np.testing.assert_allclose(inverse.tikhonov(np.eye(2), [2, 4], 1), [1, 2], rtol=0, atol=1e-12)
        np.testing.assert_allclose(inverse.tikhonov(np.eye(2), [2, 4], 1, [2, 2]), [2, 3], rtol=0, atol=1e-12)
        with self.assertRaises(ValueError):
            inverse.tikhonov(np.eye(2), [2, 4], -1)

    def test_posterior_and_predictive_variance_against_conjugate_formula(self):
        result = inverse.normal_posterior([1, 2, 3])
        self.assertEqual(result, {"mean": 1.5, "variance": .25, "predictive_variance": 1.25})
        with self.assertRaises(ValueError):
            inverse.normal_posterior([1, 2], observation_variance=0)

    def test_seeded_chains_match_known_target_without_claiming_general_convergence(self):
        samples, acceptance = inverse.metropolis_normal(1.5, .25)
        duplicate, _ = inverse.metropolis_normal(1.5, .25)
        np.testing.assert_array_equal(samples, duplicate)
        self.assertLess(float(np.max(np.abs(samples.mean(axis=1) - 1.5))), .05)
        self.assertAlmostEqual(float(samples.var()), .25, delta=.03)
        self.assertTrue(np.all((acceptance > .25) & (acceptance < .75)))


class DynamicModuleTests(unittest.TestCase):
    def test_inventory_dp_matches_independent_exhaustive_enumeration(self):
        demands = [1, 2, 1]
        costs = []
        for sequence in itertools.product(range(4), repeat=3):
            stock, cost = 0, 0.
            for order, demand in zip(sequence, demands):
                if stock + order > 3:
                    break
                next_stock = max(stock + order - demand, 0)
                cost += 2 * order + 3 * (order > 0) + .5 * next_stock + 8 * max(demand - stock - order, 0)
                stock = next_stock
            else:
                costs.append(cost)
        result = dynamic.inventory_plan(demands)
        self.assertEqual(result["objective"], min(costs))
        self.assertEqual(result["objective"], 14.5)
        for row in result["trajectory"]:
            self.assertLessEqual(row["stock"] + row["order"], 3)

    def test_value_and_policy_iteration_match_absorbing_mdp_solution(self):
        transitions = [[[1, 0], [0, 1]], [[0, 1], [0, 1]]]
        costs = [[1, .2], [0, 1]]
        for solver in (dynamic.value_iteration, dynamic.policy_iteration):
            with self.subTest(solver=solver.__name__):
                result = solver(transitions, costs)
                np.testing.assert_allclose(result["value"], [.2, 0], rtol=0, atol=1e-9)
                self.assertEqual(result["policy"], [1, 0])
                self.assertLess(result["bellman_residual"], 1e-9)

    def test_mdp_rejects_nonstochastic_rows_and_undiscounted_shortcut(self):
        with self.assertRaises(ValueError):
            dynamic.value_iteration([[[.5]]], [[1]])
        with self.assertRaises(ValueError):
            dynamic.value_iteration([[[1]]], [[1]], discount=1)
        with self.assertRaises(RuntimeError):
            dynamic.value_iteration([[[1]]], [[1]], max_iterations=1)

    def test_mpc_constraints_dynamics_and_unconstrained_riccati_reference(self):
        result = dynamic.mpc_scalar()
        states, controls = np.array(result["states"]), np.array(result["controls"])
        self.assertLessEqual(float(np.max(np.abs(controls))), .6 + 1e-9)
        np.testing.assert_allclose(np.diff(states), controls, rtol=0, atol=1e-12)
        self.assertAlmostEqual(controls[0], -.6, delta=1e-6)
        self.assertLess(abs(states[-1]), .01)
        riccati, gain = 1., None
        for _ in range(3):
            gain = riccati / (.1 + riccati)
            riccati = 1 + riccati - riccati ** 2 / (.1 + riccati)
        loose = dynamic.mpc_scalar(initial=.2, control_bound=10, steps=1)
        self.assertAlmostEqual(loose["controls"][0], -gain * .2, delta=1e-5)


class UncertainModuleTests(unittest.TestCase):
    def test_shared_decision_matches_piecewise_cost_and_information_bounds(self):
        result = uncertain.two_stage_inventory([1, 3], [.5, .5])

        def expected_cost(order):
            return 2 * order + sum(.5 * (max(order - d, 0) + 7 * max(d - order, 0)) for d in (1, 3))

        candidates = [0, 1, 3, 10]
        self.assertAlmostEqual(result["objective"], min(map(expected_cost, candidates)))
        self.assertAlmostEqual(result["order"], 3)
        self.assertAlmostEqual(result["objective"], 7)
        self.assertLess(result["balance_residual"], 1e-10)
        perfect_information = .5 * 2 * 1 + .5 * 2 * 3
        self.assertLess(perfect_information, result["objective"])
        self.assertGreater(expected_cost(2), result["objective"])

    def test_capacity_is_shared_and_recourse_remains_feasible(self):
        result = uncertain.two_stage_inventory([1, 3], [.5, .5], capacity=2)
        self.assertAlmostEqual(result["order"], 2)
        self.assertAlmostEqual(result["objective"], 8)
        np.testing.assert_allclose(result["shortage"], [0, 1], rtol=0, atol=1e-9)

    def test_uncertainty_probabilities_are_not_silently_repaired(self):
        for probabilities in ([.2, .2], [0, 1], [-.1, 1.1]):
            with self.subTest(probabilities=probabilities), self.assertRaises(ValueError):
                uncertain.two_stage_inventory([1, 3], probabilities)

    def test_box_counterpart_satisfies_all_vertices_and_known_optimum(self):
        result = uncertain.box_robust_resource([3, 2], [1, 1], [.5, .2], 3)
        decision = np.array(result["decision"])
        np.testing.assert_allclose(decision, [2, 0], rtol=0, atol=1e-9)
        self.assertAlmostEqual(result["objective"], 6)
        for vertex in itertools.product([.5, 1.5], [.8, 1.2]):
            self.assertLessEqual(float(np.dot(vertex, decision)), 3 + 1e-9)
        with self.assertRaises(ValueError):
            uncertain.box_robust_resource([3], [1], [-.1], 3)


if __name__ == "__main__":
    unittest.main()
