import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "assets/algorithms"))
from baselines import linear_resource_allocation, linear_trend_predict, topsis
from classification import evaluate_holdout, select_knn, select_tree

spec = importlib.util.spec_from_file_location("numeric_benchmarks", ROOT / "benchmarks/run_baselines.py")
benchmarks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmarks)


class NumericBaselineTests(unittest.TestCase):
    def test_known_numeric_answers_and_reproducible_result_identity(self):
        first, second = benchmarks.run(), benchmarks.run()
        self.assertTrue(first["passed"])
        self.assertEqual({case["name"] for case in first["cases"]},
                         {"optimization", "prediction", "evaluation"})
        self.assertEqual(first["results_sha256"], second["results_sha256"])
        self.assertEqual(len(first["input"]["sha256"]), 64)
        self.assertEqual(len(first["code"]), 2)

    def test_changed_expected_answer_fails_and_changes_input_hash(self):
        baseline = benchmarks.run()
        fixture = json.loads((ROOT / "benchmarks/synthetic-v1.json").read_text(encoding="utf-8"))
        fixture["optimization"]["expected"]["objective"] = 11
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "changed.json"
            path.write_text(json.dumps(fixture), encoding="utf-8")
            changed = benchmarks.run(path)
        self.assertFalse(changed["passed"])
        self.assertNotEqual(baseline["input"]["sha256"], changed["input"]["sha256"])

    def test_infeasible_optimization_is_not_reported_as_solution(self):
        with self.assertRaisesRegex(ValueError, "not solved"):
            linear_resource_allocation([1], [[1]], [-1])

    def test_forecast_requires_future_times_and_retains_nonzero_intercept(self):
        result = linear_trend_predict([0, 1, 2], [3, 5, 7], [3])
        self.assertAlmostEqual(result["intercept"], 3)
        self.assertAlmostEqual(result["predictions"][0], 9)
        with self.assertRaisesRegex(ValueError, "strictly future"):
            linear_trend_predict([0, 1, 2], [3, 5, 7], [1])

    def test_evaluation_rejects_undefined_scores(self):
        with self.assertRaisesRegex(ValueError, "no defined"):
            topsis([[1, 1], [1, 1]], [1, 1], [True, True])
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            topsis([[1, 2], [2, 1]], [-1, 1], [True, False])


class ClassificationIsolationTests(unittest.TestCase):
    def setUp(self):
        self.X = np.array([[i, i * i] for i in range(12)], dtype=float)
        self.y = np.array([0, 1] * 6)

    def test_scaler_is_fitted_on_each_training_fold_then_refitted_once(self):
        observed_means = []
        original_fit = StandardScaler.fit

        def record_fit(scaler, X, y=None, sample_weight=None):
            observed_means.append(np.mean(X, axis=0))
            return original_fit(scaler, X, y, sample_weight=sample_weight)

        with mock.patch.object(StandardScaler, "fit", record_fit):
            search = select_knn(self.X, self.y, neighbors=(1,), folds=3, seed=42)
        splits = StratifiedKFold(3, shuffle=True, random_state=42).split(self.X, self.y)
        expected_means = [self.X[train].mean(axis=0) for train, _ in splits]
        self.assertEqual(len(observed_means), 4)
        np.testing.assert_allclose(observed_means[:3], expected_means)
        np.testing.assert_allclose(observed_means[-1], self.X.mean(axis=0))
        self.assertIn("scale", search.best_estimator_.named_steps)

    def test_holdout_evaluation_never_refits_or_tunes(self):
        search = select_tree(self.X, self.y, depths=(1, 2), folds=3)
        parameters = search.best_params_.copy()
        with mock.patch.object(search, "fit", side_effect=AssertionError("test set reached fit")):
            report = evaluate_holdout(search, np.array([[12, 144], [13, 169]]), np.array([0, 1]))
        self.assertEqual(search.best_params_, parameters)
        self.assertEqual(len(report["predictions"]), 2)


if __name__ == "__main__":
    unittest.main()
