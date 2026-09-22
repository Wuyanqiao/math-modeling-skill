"""Known answers and rejected evidence for the on-demand validation module."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import make_pipeline


MODULES = Path(__file__).resolve().parents[1] / "assets" / "algorithms" / "模型验证"


def load(name):
    spec = importlib.util.spec_from_file_location("model_checks_" + name, MODULES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validation = load("validation")
sensitivity = load("sensitivity")


class FittedRows(BaseEstimator, TransformerMixin):
    rows = []

    def fit(self, features, target=None):
        type(self).rows.append(features[:, 0].copy())
        self.center_ = np.mean(features, axis=0)
        return self

    def transform(self, features):
        return features - self.center_


class GeneralizationTests(unittest.TestCase):
    def test_missing_group_ids_cannot_silently_drop_observations(self):
        for groups in ([0, 1, 2, 3, np.nan], [0, 1, 2, 3, None]):
            with self.subTest(groups=groups), self.assertRaises(ValueError):
                validation.three_way_split(5, strategy="group", groups=groups)

    def test_three_way_random_group_and_chronological_splits(self):
        for strategy in ("random", "time", "group"):
            groups = np.repeat(np.arange(10), 3)
            split = validation.three_way_split(30, strategy=strategy, groups=groups if strategy == "group" else None)
            combined = np.concatenate(list(split.values()))
            np.testing.assert_array_equal(np.sort(combined), np.arange(30))
            self.assertEqual(len(np.unique(combined)), 30)
            if strategy == "time":
                self.assertLess(split["train"].max(), split["validation"].min())
                self.assertLess(split["validation"].max(), split["test"].min())
            elif strategy == "group":
                for left, right in (("train", "validation"), ("train", "test"), ("validation", "test")):
                    self.assertFalse(set(groups[split[left]]) & set(groups[split[right]]))

    def test_group_and_time_cv_preserve_dependency_boundaries(self):
        groups = np.repeat(np.arange(6), 4)
        for train, held in validation.cv_splits(24, strategy="group", groups=groups):
            self.assertFalse(set(groups[train]) & set(groups[held]))
        for train, held in validation.cv_splits(24, strategy="time", times=np.arange(24), gap=2):
            self.assertGreater(held.min() - train.max(), 2)
        with self.assertRaises(ValueError):
            validation.cv_splits(24, strategy="kfold", groups=groups)
        with self.assertRaises(ValueError):
            validation.cv_splits(24, strategy="time", times=np.arange(24)[::-1])
        with self.assertRaises(ValueError):
            validation.cv_splits(24, strategy="time", times=np.zeros(24))

    def test_pipeline_fits_only_fold_training_rows_and_does_not_touch_final_test(self):
        features = np.arange(30.).reshape(-1, 1)
        target = 2 + 3 * features[:, 0]
        partition = validation.three_way_split(30, strategy="time")
        development = np.concatenate([partition["train"], partition["validation"]])
        folds = validation.cv_splits(len(development), strategy="time", times=features[development, 0])
        FittedRows.rows = []
        estimator = make_pipeline(FittedRows(), LinearRegression())
        scores = validation.evaluate_regression_folds(estimator, features[development], target[development], folds)
        for seen, (train, held), result in zip(FittedRows.rows, folds, scores):
            np.testing.assert_array_equal(seen, features[development[train], 0])
            self.assertFalse(set(seen) & set(features[partition["test"], 0]))
            self.assertLess(result["rmse"], 1e-10)
        self.assertFalse(hasattr(estimator[0], "center_"))
        with self.assertRaisesRegex(ValueError, "overlap"):
            validation.evaluate_regression_folds(estimator, features, target, [(np.array([0, 1]), np.array([1, 2]))])


class SensitivityTests(unittest.TestCase):
    def test_local_derivative_and_undefined_zero_output_elasticity(self):
        result = sensitivity.local_sensitivity(lambda x: x[0] ** 2 + 3 * x[1], [2., 1.], [1e-4, 1e-4])
        np.testing.assert_allclose(result["gradient"], [4, 3], rtol=0, atol=1e-8)
        zero = sensitivity.local_sensitivity(lambda x: x[0], [0.], [1e-5])
        self.assertIsNone(zero["elasticities"])

    def test_actual_morris_linear_effects_and_zero_interaction(self):
        result = sensitivity.morris_screen(lambda x: x[0] + 2 * x[1], ["a", "b"], [[0, 1], [0, 1]])
        np.testing.assert_allclose(result["mu_star"], [1, 2], rtol=0, atol=1e-10)
        np.testing.assert_allclose(result["sigma"], [0, 0], rtol=0, atol=1e-10)
        self.assertEqual(result["evaluations"], 64 * 3)

    def test_actual_sobol_additive_variance_decomposition(self):
        result = sensitivity.sobol_indices(lambda x: x[0] + 2 * x[1], ["a", "b"], [[0, 1], [0, 1]])
        np.testing.assert_allclose(result["S1"], [.2, .8], rtol=0, atol=.025)
        np.testing.assert_allclose(result["ST"], [.2, .8], rtol=0, atol=.025)
        self.assertEqual(result["evaluations"], 1024 * 4)

    def test_actual_sobol_detects_pure_interaction_missed_by_first_order(self):
        result = sensitivity.sobol_indices(lambda x: x[0] * x[1], ["a", "b"], [[-1, 1], [-1, 1]], base_samples=2048)
        np.testing.assert_allclose(result["S1"], [0, 0], rtol=0, atol=.04)
        np.testing.assert_allclose(result["ST"], [1, 1], rtol=0, atol=.04)

    def test_unavailable_dependency_and_invalid_design_are_explicit(self):
        with patch.object(sensitivity.importlib, "import_module", side_effect=ImportError), self.assertRaisesRegex(RuntimeError, "SALib is unavailable"):
            sensitivity.sobol_indices(lambda x: x[0], ["a"], [[0, 1]])
        with self.assertRaises(ValueError):
            sensitivity.sobol_indices(lambda x: x[0], ["a"], [[0, 1]], base_samples=1000)
        with self.assertRaises(ValueError):
            sensitivity.sobol_indices(lambda x: 1, ["a"], [[0, 1]])


class UncertaintyTests(unittest.TestCase):
    def test_bootstrap_is_seeded_and_targets_mean_not_future_observation(self):
        first = validation.bootstrap_mean_interval([1, 2, 3, 4, 5])
        second = validation.bootstrap_mean_interval([1, 2, 3, 4, 5])
        self.assertEqual(first, second)
        self.assertEqual(first["target"], "population_mean")
        self.assertLess(first["interval"][0], 3)
        self.assertGreater(first["interval"][1], 3)
        constant = validation.bootstrap_mean_interval([3, 3, 3])
        self.assertEqual(constant["interval"], [3, 3])
        with self.assertRaises(ValueError):
            validation.bootstrap_mean_interval([1, 2, 3], sampling_unit="group")

    def test_posterior_predictive_interval_is_wider_for_the_known_model(self):
        result = validation.normal_uncertainty([1, 2, 3])
        parameter = result["parameter"]["interval"]
        future = result["future_observation"]["interval"]
        self.assertAlmostEqual(sum(parameter) / 2, 1.5)
        self.assertAlmostEqual(sum(future) / 2, 1.5)
        self.assertAlmostEqual((future[1] - future[0]) / (parameter[1] - parameter[0]), np.sqrt(5))
        self.assertNotEqual(result["parameter"]["interval_kind"], result["future_observation"]["interval_kind"])


class SolverAndMechanismTests(unittest.TestCase):
    def test_gap_tolerance_cannot_reverse_a_bound_and_unknown_numbers_are_checked(self):
        certificate = validation.linear_solver_demo()
        for changes in ({"best_bound": 5., "gap_tolerance": 10.},
                        {"sense": "min", "objective": -10., "best_bound": -5., "gap_tolerance": 10.},
                        {"status": "UNKNOWN", "objective": float("nan"), "best_bound": float("inf"), "gap_tolerance": -1.},
                        {"status": "UNKNOWN", "objective": 0., "best_bound": None}):
            with self.subTest(changes=changes):
                result = validation.solver_certificate_check({**certificate, **changes})
                self.assertFalse(result["ok"])
                self.assertFalse(result["optimal_supported"])

    def test_real_highs_certificate_has_primal_dual_optimum_and_feasibility(self):
        certificate = validation.linear_solver_demo()
        result = validation.solver_certificate_check(certificate)
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["optimal_supported"])
        self.assertAlmostEqual(certificate["objective"], 10)
        self.assertAlmostEqual(certificate["best_bound"], 10)
        np.testing.assert_allclose(certificate["decision"], [2, 2], rtol=0, atol=1e-8)

    def test_feasible_fixture_never_becomes_optimal_even_at_zero_gap(self):
        # Explicit CP-SAT status fixture, not an assertion that CP-SAT ran here.
        certificate = validation.linear_solver_demo()
        certificate.update(solver="CP-SAT", solver_version="test fixture", raw_status="FEASIBLE", status="FEASIBLE",
                           termination_reason="test fixture: time limit with incumbent")
        result = validation.solver_certificate_check(certificate)
        self.assertTrue(result["feasible_supported"])
        self.assertFalse(result["optimal_supported"])
        certificate.update(status="UNKNOWN", raw_status="UNKNOWN", objective=None, best_bound=None)
        result = validation.solver_certificate_check(certificate)
        self.assertFalse(result["feasible_supported"])
        self.assertFalse(result["optimal_supported"])

    def test_local_no_bound_and_nonzero_gap_do_not_prove_global_optimum(self):
        certificate = validation.linear_solver_demo()
        for changes in ({"status": "LOCAL_OPTIMUM", "optimality_scope": "local"}, {"best_bound": None},
                        {"best_bound": 12.}, {"optimality_scope": "unknown"}):
            with self.subTest(changes=changes):
                result = validation.solver_certificate_check({**certificate, **changes})
                self.assertFalse(result["optimal_supported"])

    def test_wrong_bound_direction_nonfinite_or_bad_constraints_are_rejected(self):
        certificate = validation.linear_solver_demo()
        for changes in ({"best_bound": 9.}, {"objective": float("nan")}, {"solver_version": None},
                        {"residuals": {"capacity": .1}, "tolerances": {"capacity": .01}},
                        {"residuals": {"capacity": -1.}, "tolerances": {"capacity": .01}}):
            with self.subTest(changes=changes):
                result = validation.solver_certificate_check({**certificate, **changes})
                self.assertFalse(result["ok"])
                self.assertFalse(result["feasible_supported"])
        minimum = {**certificate, "sense": "min", "objective": -10, "best_bound": -10}
        self.assertTrue(validation.solver_certificate_check(minimum)["optimal_supported"])
        self.assertFalse(validation.solver_certificate_check({**minimum, "best_bound": -9})["ok"])

    def test_declared_dimensions_and_manufactured_boundary_refinement_checks(self):
        self.assertFalse(validation.check_dimensions({"length": 1}, [{"time": 1}])["ok"])
        result = validation.mechanistic_demo_checks()
        self.assertTrue(result["boundary"]["ok"])
        self.assertTrue(result["dimension"]["ok"])
        self.assertTrue(result["heat"]["errors_decrease"])
        np.testing.assert_allclose(result["heat"]["observed_orders"], [2, 2], rtol=0, atol=.15)
        np.testing.assert_allclose(result["fem"]["observed_orders"], [2, 2], rtol=0, atol=1e-8)
        with self.assertRaises(ValueError):
            validation.refinement_report([.1, .05], [.01, .001])


if __name__ == "__main__":
    unittest.main()
