"""Train-only tabular preprocessing with explicit split and feature contracts.

Run this file for a deterministic synthetic example. Requires the science extra.
"""
import json

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.experimental import enable_iterative_imputer  # noqa: F401
from sklearn.impute import IterativeImputer, KNNImputer, MissingIndicator, SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder, OrdinalEncoder, RobustScaler, StandardScaler
from sklearn.utils.validation import check_is_fitted


MISSING_CATEGORY = "__MATHMODEL_MISSING__"


def split_indices(frame, *, mode="random", test_size=0.25, seed=42,
                  group_col=None, time_col=None, gap=0, stratify=None):
    """Split raw rows; time gap counts distinct timestamps, not elapsed duration.

    group_time removes training rows whose group also occurs in the future test
    set. Its estimand is future, previously unseen groups. Excluded rows are
    returned explicitly; incompatible constraints fail rather than mix groups.
    """
    if not isinstance(frame, pd.DataFrame) or len(frame) < 2:
        raise ValueError("Need a DataFrame with at least two rows")
    if not 0 < test_size < 1:
        raise ValueError("test_size must be a fraction strictly between 0 and 1")
    if mode not in {"random", "group", "time", "group_time"}:
        raise ValueError("Unknown split mode")
    if not isinstance(gap, int) or isinstance(gap, bool) or gap < 0:
        raise ValueError("gap must be a nonnegative integer")
    if mode == "random" and (group_col or time_col or gap):
        raise ValueError("Use a group/time-aware split for group_col, time_col or gap")
    if mode == "group" and (time_col or gap):
        raise ValueError("Use group_time when chronological separation is required")
    if mode == "time" and group_col:
        raise ValueError("Use group_time to enforce both constraints")
    if mode != "random" and stratify is not None:
        raise ValueError("Stratification here is supported only for random splits")
    positions = np.arange(len(frame))
    groups = None
    if mode in {"group", "group_time"}:
        if not group_col or group_col not in frame or frame[group_col].isna().any():
            raise ValueError("Provide a complete group column")
        groups = frame[group_col].to_numpy()
    if mode == "random":
        train, test = train_test_split(positions, test_size=test_size, random_state=seed, stratify=stratify)
        train, test = np.sort(train), np.sort(test)
    elif mode == "group":
        splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
        train, test = next(splitter.split(frame, groups=groups))
    else:
        if not time_col or time_col not in frame:
            raise ValueError("Provide an explicit time column")
        times = pd.to_datetime(frame[time_col], errors="raise", utc=True)
        if times.isna().any():
            raise ValueError("Missing timestamps cannot establish temporal separation")
        unique = np.sort(times.unique())
        test_periods = max(1, int(np.ceil(len(unique) * test_size)))
        cutoff = len(unique) - test_periods
        if cutoff - gap < 1:
            raise ValueError("Too few distinct timestamps for the requested test_size and gap")
        order = np.argsort(times.to_numpy(), kind="stable")
        train = order[(times.iloc[order] < unique[cutoff - gap]).to_numpy()]
        test = order[(times.iloc[order] >= unique[cutoff]).to_numpy()]
        if mode == "group_time":
            train = train[~np.isin(groups[train], groups[test])]
    if not len(train) or not len(test):
        raise ValueError("Split constraints leave an empty training or test set")
    excluded = np.setdiff1d(positions, np.concatenate([train, test]))
    return train, test, excluded


class RowFeatures(TransformerMixin, BaseEstimator):
    """Only predeclared within-row arithmetic; no cohort statistics or targets."""

    def __init__(self, numeric_columns, categorical_columns, ratios=None, cyclical=None):
        self.numeric_columns = numeric_columns
        self.categorical_columns = categorical_columns
        self.ratios = ratios
        self.cyclical = cyclical

    def fit(self, X, y=None):
        columns = list(self.numeric_columns) + list(self.categorical_columns)
        if not columns or len(set(columns)) != len(columns):
            raise ValueError("Declare at least one feature; columns must be unique and disjoint")
        if not all(isinstance(column, str) for column in columns):
            raise ValueError("Feature names must be strings")
        self.feature_names_in_ = np.asarray(columns, dtype=object)
        self.n_features_in_ = len(columns)
        generated = []
        for name, pair in (self.ratios or {}).items():
            if len(pair) != 2 or any(column not in self.numeric_columns for column in pair):
                raise ValueError("Ratio inputs must be two declared numeric columns")
            generated.append(name)
        for column, period in (self.cyclical or {}).items():
            if column not in self.numeric_columns or not np.isfinite(period) or period <= 0:
                raise ValueError("Cyclical features need a numeric column and positive period")
            generated.extend([f"{column}_sin", f"{column}_cos"])
        if any(not isinstance(name, str) for name in generated) or len(set(columns + generated)) != len(columns + generated):
            raise ValueError("Generated feature names must be unique")
        self.generated_names_ = generated
        self.transform(X)
        return self

    def transform(self, X):
        check_is_fitted(self, "generated_names_")
        if not isinstance(X, pd.DataFrame) or not X.columns.is_unique:
            raise ValueError("Expected a DataFrame with unique columns")
        if not set(self.feature_names_in_).issubset(X.columns):
            raise ValueError("Missing required feature columns")
        output = X[list(self.feature_names_in_)].copy()
        for column in self.numeric_columns:
            output[column] = pd.to_numeric(output[column], errors="raise").astype(float).replace([np.inf, -np.inf], np.nan)
        for column in self.categorical_columns:
            values = output[column].astype(object)
            if values.dropna().map(str).eq(MISSING_CATEGORY).any():
                raise ValueError("Reserved missing-category marker occurs in input")
            output[column] = values.map(lambda value: np.nan if pd.isna(value) else str(value)).astype(object)
        for name, (numerator, denominator) in (self.ratios or {}).items():
            output[name] = output[numerator] / output[denominator].replace(0, np.nan)
        for column, period in (self.cyclical or {}).items():
            angle = output[column] * (2 * np.pi / period)
            output[f"{column}_sin"] = np.sin(angle)
            output[f"{column}_cos"] = np.cos(angle)
        return output.replace([np.inf, -np.inf], np.nan)

    def get_feature_names_out(self, input_features=None):
        check_is_fitted(self, "generated_names_")
        return np.asarray(list(self.feature_names_in_) + self.generated_names_, dtype=object)


class EmptyColumnPolicy(TransformerMixin, BaseEstimator):
    """Training-empty numeric columns remain constant even if test has values."""

    def __init__(self, policy="constant", fill_value=0.0):
        self.policy = policy
        self.fill_value = fill_value

    def fit(self, X, y=None):
        values = np.asarray(X, dtype=float)
        if self.policy not in {"constant", "error"} or not np.isfinite(self.fill_value):
            raise ValueError("Use constant/error empty policy and a finite fill_value")
        self.n_features_in_ = values.shape[1]
        self.empty_features_ = np.isnan(values).all(axis=0)
        if self.policy == "error" and self.empty_features_.any():
            raise ValueError("Training data has entirely missing numeric columns")
        return self

    def transform(self, X):
        check_is_fitted(self, "empty_features_")
        values = np.asarray(X, dtype=float).copy()
        if values.ndim != 2 or values.shape[1] != self.n_features_in_:
            raise ValueError("Numeric feature count changed")
        values[:, self.empty_features_] = self.fill_value
        return values

    def get_feature_names_out(self, input_features=None):
        check_is_fitted(self, "empty_features_")
        return np.asarray(input_features if input_features is not None else [f"x{i}" for i in range(self.n_features_in_)], dtype=object)


def make_preprocessor(numeric_columns, categorical_columns, *, imputation="simple",
                      simple_strategy="median", scale="standard", encoding="onehot",
                      ordinal_categories=None, ratios=None, cyclical=None, seed=42,
                      n_neighbors=5, empty_policy="constant", empty_fill_value=0.0):
    """Return an unfitted sklearn Pipeline; fit it only inside the training fold.

    All numeric features get a separate missing indicator, including features
    first missing at inference. Dense output targets modest tabular datasets.
    """
    numeric = list(numeric_columns) + list((ratios or {}).keys())
    for column in cyclical or {}:
        numeric.extend([f"{column}_sin", f"{column}_cos"])
    scalers = {"none": "passthrough", "standard": StandardScaler(), "robust": RobustScaler(), "minmax": MinMaxScaler()}
    if scale not in scalers:
        raise ValueError("scale must be none, standard, robust or minmax")
    if simple_strategy not in {"mean", "median", "most_frequent", "constant"}:
        raise ValueError("Unsupported SimpleImputer strategy")
    if imputation == "simple":
        imputer = SimpleImputer(strategy=simple_strategy, fill_value=0, keep_empty_features=True)
    elif imputation == "knn":
        if not isinstance(n_neighbors, int) or isinstance(n_neighbors, bool) or n_neighbors < 1:
            raise ValueError("n_neighbors must be a positive integer")
        imputer = KNNImputer(n_neighbors=n_neighbors, keep_empty_features=True)
    elif imputation == "iterative":
        imputer = IterativeImputer(initial_strategy="median", random_state=seed, sample_posterior=False, max_iter=20, keep_empty_features=True)
    else:
        raise ValueError("imputation must be simple, knn or iterative")
    numeric_steps = [("empty", EmptyColumnPolicy(empty_policy, empty_fill_value))]
    if imputation == "knn":
        # Fit the distance metric's scale on observed training entries only.
        numeric_steps.append(("distance_scale", StandardScaler()))
    numeric_steps.extend([("impute", imputer), ("scale", scalers[scale])])
    if encoding == "onehot":
        encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    elif encoding == "ordinal":
        if set(ordinal_categories or {}) != set(categorical_columns):
            raise ValueError("Provide explicit ordinal_categories for every categorical column")
        categories = [[str(value) for value in ordinal_categories[column]] for column in categorical_columns]
        if any(not values or len(set(values)) != len(values) or MISSING_CATEGORY in values for values in categories):
            raise ValueError("Ordinal levels must be nonempty, unique and exclude the missing marker")
        encoder = OrdinalEncoder(categories=categories, handle_unknown="use_encoded_value", unknown_value=-1)
    else:
        raise ValueError("encoding must be onehot or ordinal")
    transformers = []
    if numeric:
        transformers.extend([("numeric", Pipeline(numeric_steps), numeric),
                             ("missing", MissingIndicator(features="all", error_on_new=False), numeric)])
    if categorical_columns:
        transformers.append(("categorical", Pipeline([
            ("impute", SimpleImputer(strategy="constant", fill_value=MISSING_CATEGORY, keep_empty_features=True)),
            ("encode", encoder),
        ]), list(categorical_columns)))
    return Pipeline([
        ("features", RowFeatures(numeric_columns, categorical_columns, ratios=ratios, cyclical=cyclical)),
        ("columns", ColumnTransformer(transformers, remainder="drop", verbose_feature_names_out=True)),
    ])


def prepare_split(frame, target, numeric_columns, categorical_columns, *, split=None, **preprocessing):
    """Raw split -> training fit_transform -> test transform, with audit metadata."""
    split = dict(split or {})
    excluded_features = {target, split.get("group_col"), split.get("time_col")}
    if excluded_features.intersection(list(numeric_columns) + list(categorical_columns)):
        raise ValueError("Target/group/time split metadata must not be predictor columns")
    if target not in frame or frame[target].isna().any():
        raise ValueError("Provide a complete target; this module never imputes labels")
    train, test, excluded = split_indices(frame, **split)
    transformer = make_preprocessor(numeric_columns, categorical_columns, **preprocessing)
    train_frame, test_frame = frame.iloc[train], frame.iloc[test]
    X_train = transformer.fit_transform(train_frame)
    X_test = transformer.transform(test_frame)
    features = transformer.named_steps["features"].transform(train_frame)
    return {"preprocessor": transformer, "X_train": X_train, "X_test": X_test,
            "y_train": train_frame[target].to_numpy(), "y_test": test_frame[target].to_numpy(),
            "train_indices": train, "test_indices": test, "excluded_indices": excluded,
            "audit": {"split_mode": split.get("mode", "random"), "fit_rows": len(train),
                      "test_rows": len(test), "excluded_rows": len(excluded),
                      "training_missing_rates": features.isna().mean().to_dict(),
                      "training_empty_columns": features.columns[features.isna().all()].tolist(),
                      "feature_names": transformer.get_feature_names_out().tolist()}}


def run_demo():
    """Synthetic measurements; the reported metric is not a contest result."""
    rng = np.random.default_rng(42)
    frame = pd.DataFrame({"mass": rng.uniform(1, 10, 60), "volume": rng.uniform(1, 4, 60),
                          "hour": np.arange(60) % 24, "site_type": np.resize(["rural", "urban"], 60),
                          "time": pd.date_range("2025-01-01", periods=60, freq="D")})
    frame["response"] = 2 * frame["mass"] - frame["volume"] + rng.normal(0, 0.1, len(frame))
    frame.loc[[3, 9, 19, 49], "mass"] = np.nan
    frame["unmeasured"] = np.nan
    frame.loc[55:, "site_type"] = "new_test_only_type"
    prepared = prepare_split(frame, "response", ["mass", "volume", "hour", "unmeasured"], ["site_type"],
                             split={"mode": "time", "time_col": "time", "gap": 1},
                             ratios={"density": ("mass", "volume")}, cyclical={"hour": 24})
    model = Ridge(alpha=1).fit(prepared["X_train"], prepared["y_train"])
    predictions = model.predict(prepared["X_test"])
    return {"dataset": "synthetic demonstration", "seed": 42, **prepared["audit"],
            "train_indices": prepared["train_indices"].tolist(), "test_indices": prepared["test_indices"].tolist(),
            "excluded_indices": prepared["excluded_indices"].tolist(),
            "test_rmse": float(np.sqrt(np.mean((predictions - prepared["y_test"]) ** 2))),
            "test_predictions": predictions.tolist()}


if __name__ == "__main__":
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2, allow_nan=False))
