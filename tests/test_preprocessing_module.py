"""Behavioral checks for the standalone preprocessing module, including leakage."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold, cross_validate
from sklearn.pipeline import Pipeline


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("mathmodel_preprocessing", ROOT / "assets/algorithms/数据预处理/preprocessing.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def sample_frame():
    return pd.DataFrame({"x": [1., 2., np.nan, 4., 5., 6., 7., 8., 9., 10., 11., 12.],
                         "z": [3., 5., 7., 9., 11., 13., 15., 17., np.nan, 21., 23., 25.],
                         "kind": ["a", "b"] * 6, "target": np.arange(12, dtype=float),
                         "time": pd.date_range("2025-01-01", periods=12)})


class PreprocessingTests(unittest.TestCase):
    def test_test_values_cannot_change_fitted_statistics_or_training_outputs(self):
        frame = sample_frame()
        altered = frame.copy()
        altered.loc[9:, ["x", "z", "target"]] = 1e9
        altered.loc[9:, "kind"] = "test-only-category"
        for imputation in ("simple", "knn", "iterative"):
            with self.subTest(imputation=imputation):
                options = {"split": {"mode": "time", "time_col": "time"}, "imputation": imputation}
                first = module.prepare_split(frame, "target", ["x", "z"], ["kind"], **options)
                second = module.prepare_split(altered, "target", ["x", "z"], ["kind"], **options)
                np.testing.assert_array_equal(first["train_indices"], np.arange(9))
                np.testing.assert_allclose(first["X_train"], second["X_train"], rtol=0, atol=0)
                first_columns = first["preprocessor"].named_steps["columns"].named_transformers_
                second_columns = second["preprocessor"].named_steps["columns"].named_transformers_
                for left, right in zip(first_columns["categorical"]["encode"].categories_, second_columns["categorical"]["encode"].categories_):
                    np.testing.assert_array_equal(left, right)
                np.testing.assert_array_equal(first_columns["numeric"]["scale"].mean_, second_columns["numeric"]["scale"].mean_)
                imputer1, imputer2 = first_columns["numeric"]["impute"], second_columns["numeric"]["impute"]
                if imputation == "simple":
                    np.testing.assert_array_equal(imputer1.statistics_, [5.5, 10.])
                elif imputation == "knn":
                    np.testing.assert_array_equal(imputer1._fit_X, imputer2._fit_X)
                    expected_mean = frame.iloc[:9][["x", "z"]].mean().to_numpy()
                    np.testing.assert_allclose(first_columns["numeric"]["distance_scale"].mean_, expected_mean)
                else:
                    np.testing.assert_array_equal(imputer1.initial_imputer_.statistics_, imputer2.initial_imputer_.statistics_)
                self.assertTrue(np.isfinite(second["X_test"]).all())
                before = first_columns["numeric"]["scale"].mean_.copy()
                first["preprocessor"].transform(altered.iloc[9:])
                np.testing.assert_array_equal(first_columns["numeric"]["scale"].mean_, before)

    def test_unknown_category_is_legal_without_expanding_the_training_vocabulary(self):
        train = pd.DataFrame({"kind": ["a", "b", None]})
        processor = module.make_preprocessor([], ["kind"])
        matrix = processor.fit_transform(train)
        result = processor.transform(pd.DataFrame({"kind": ["new"]}))
        self.assertEqual(result.shape[1], matrix.shape[1])
        np.testing.assert_array_equal(result, np.zeros((1, 3)))
        self.assertNotIn("new", processor["columns"].named_transformers_["categorical"]["encode"].categories_[0])

    def test_training_empty_columns_follow_the_same_explicit_policy_for_all_imputers(self):
        train = pd.DataFrame({"empty": [np.nan] * 4, "observed": [1., 2., 3., 4.], "empty_kind": [None] * 4})
        test = pd.DataFrame({"empty": [900.], "observed": [2.], "empty_kind": ["unseen"]})
        for imputation in ("simple", "knn", "iterative"):
            with self.subTest(imputation=imputation):
                processor = module.make_preprocessor(["empty", "observed"], ["empty_kind"], imputation=imputation)
                train_matrix = processor.fit_transform(train)
                result = processor.transform(test)
                self.assertEqual(result.shape[1], train_matrix.shape[1])
                self.assertTrue(np.isfinite(result).all())
                np.testing.assert_array_equal(result[:, 0], [0.])
                np.testing.assert_array_equal(train_matrix[:, 0], np.zeros(4))
                empty = processor["columns"].named_transformers_["numeric"]["empty"]
                np.testing.assert_array_equal(empty.empty_features_, [True, False])
        with self.assertRaisesRegex(ValueError, "entirely missing"):
            module.make_preprocessor(["empty"], [], empty_policy="error").fit(train)

    def test_new_numeric_missingness_has_an_indicator_without_refitting(self):
        processor = module.make_preprocessor(["x"], [], scale="none")
        matrix = processor.fit_transform(pd.DataFrame({"x": [2., 4., 6.]}))
        np.testing.assert_array_equal(matrix[:, 1], [0., 0., 0.])
        np.testing.assert_array_equal(processor.transform(pd.DataFrame({"x": [np.nan]})), [[4., 1.]])

    def test_explicit_ordinal_order_and_unknown_code(self):
        processor = module.make_preprocessor([], ["grade"], encoding="ordinal", ordinal_categories={"grade": ["low", "medium", "high"]})
        processor.fit(pd.DataFrame({"grade": ["high", "low", None]}))
        result = processor.transform(pd.DataFrame({"grade": ["medium", "high", "new", None]}))
        np.testing.assert_array_equal(result[:, 0], [1., 2., -1., -1.])
        with self.assertRaisesRegex(ValueError, "explicit ordinal_categories"):
            module.make_preprocessor([], ["grade"], encoding="ordinal")

    def test_ratio_and_cycle_features_are_row_local_and_handle_zero_denominators(self):
        features = module.RowFeatures(["mass", "volume", "hour"], [], ratios={"density": ("mass", "volume")}, cyclical={"hour": 24})
        raw = pd.DataFrame({"mass": [6., 4.], "volume": [2., 0.], "hour": [6., 24.]})
        output = features.fit_transform(raw)
        self.assertEqual(output["density"].iloc[0], 3.)
        self.assertTrue(np.isnan(output["density"].iloc[1]))
        np.testing.assert_allclose(output["hour_sin"], [1., 0.], atol=1e-14)
        np.testing.assert_allclose(output["hour_cos"], [0., 1.], atol=1e-14)
        pd.testing.assert_frame_equal(features.transform(raw.iloc[:1]), output.iloc[:1])

    def test_time_split_preserves_timestamp_ties_and_excludes_a_gap(self):
        frame = pd.DataFrame({"time": np.repeat(pd.date_range("2025-01-01", periods=5), 2)}).sample(frac=1, random_state=3)
        train, test, excluded = module.split_indices(frame, mode="time", time_col="time", test_size=.4, gap=1)
        self.assertEqual(len(train), 4)
        self.assertEqual(len(test), 4)
        self.assertEqual(len(excluded), 2)
        self.assertLess(frame.iloc[train].time.max(), frame.iloc[test].time.min())
        self.assertTrue(frame.iloc[train].time.is_monotonic_increasing)
        self.assertFalse(set(frame.iloc[train].time) & set(frame.iloc[test].time))
        self.assertEqual(set(frame.iloc[excluded].time), {pd.Timestamp("2025-01-03")})

    def test_group_split_keeps_entities_together(self):
        frame = pd.DataFrame({"group": np.repeat(np.arange(8), 4)})
        train, test, excluded = module.split_indices(frame, mode="group", group_col="group", seed=7)
        self.assertFalse(set(frame.iloc[train].group) & set(frame.iloc[test].group))
        self.assertEqual(len(excluded), 0)
        self.assertEqual(len(set(frame.iloc[test].group)), 2)

    def test_group_time_purges_training_groups_seen_in_the_future(self):
        frame = pd.DataFrame({"time": pd.date_range("2025-01-01", periods=8), "group": ["a", "b", "a", "b", "c", "c", "a", "d"]})
        train, test, excluded = module.split_indices(frame, mode="group_time", group_col="group", time_col="time")
        self.assertFalse(set(frame.iloc[train].group) & set(frame.iloc[test].group))
        self.assertLess(frame.iloc[train].time.max(), frame.iloc[test].time.min())
        np.testing.assert_array_equal(excluded, [0, 2])
        frame["group"] = "all_same"
        with self.assertRaisesRegex(ValueError, "empty"):
            module.split_indices(frame, mode="group_time", group_col="group", time_col="time")

    def test_pipeline_fits_each_cross_validation_training_fold(self):
        frame = sample_frame().drop(columns=["time"])
        model = Pipeline([("prepare", module.make_preprocessor(["x", "z"], ["kind"])), ("model", Ridge())])
        folds = list(KFold(3, shuffle=True, random_state=42).split(frame))
        result = cross_validate(model, frame.drop(columns=["target"]), frame.target, cv=folds, return_estimator=True, error_score="raise")
        for fitted, (train, _) in zip(result["estimator"], folds):
            statistics = fitted["prepare"]["columns"].named_transformers_["numeric"]["impute"].statistics_
            np.testing.assert_allclose(statistics, frame.iloc[train][["x", "z"]].median().to_numpy())

    def test_repeated_runs_and_cloned_estimators_are_reproducible(self):
        self.assertEqual(module.run_demo(), module.run_demo())
        frame = sample_frame()
        for imputation in ("simple", "knn", "iterative"):
            with self.subTest(imputation=imputation):
                processor = module.make_preprocessor(["x", "z"], ["kind"], imputation=imputation, seed=11)
                first = processor.fit_transform(frame)
                np.testing.assert_array_equal(first, clone(processor).fit_transform(frame))
        first = module.split_indices(frame, seed=12)
        second = module.split_indices(frame, seed=12)
        for left, right in zip(first, second):
            np.testing.assert_array_equal(left, right)

    def test_invalid_or_leaking_contracts_are_rejected(self):
        frame = sample_frame()
        with self.assertRaisesRegex(ValueError, "metadata"):
            module.prepare_split(frame, "target", ["target", "x"], [])
        for split in ({"mode": "random", "time_col": "time"}, {"mode": "time", "time_col": "time", "gap": 30}, {"mode": "group", "group_col": "missing"}):
            with self.subTest(split=split), self.assertRaises(ValueError):
                module.split_indices(frame, **split)
        with self.assertRaisesRegex(ValueError, "unique"):
            module.make_preprocessor(["x"], [], ratios={"x": ("x", "x")}).fit(frame)
        frame.loc[0, "target"] = np.nan
        with self.assertRaisesRegex(ValueError, "never imputes labels"):
            module.prepare_split(frame, "target", ["x"], [])


if __name__ == "__main__":
    unittest.main()
