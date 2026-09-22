"""Train-only model selection with preprocessing refit inside each CV fold."""

from sklearn.model_selection import GridSearchCV, StratifiedKFold
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier


def select_knn(X_train, y_train, neighbors=(1, 3, 5), folds=5, seed=42):
    pipeline = Pipeline([("scale", StandardScaler()),
                         ("model", KNeighborsClassifier(weights="distance"))])
    search = GridSearchCV(pipeline, {"model__n_neighbors": list(neighbors)},
                          cv=StratifiedKFold(folds, shuffle=True, random_state=seed),
                          scoring="accuracy", error_score="raise")
    return search.fit(X_train, y_train)


def select_tree(X_train, y_train, depths=(1, 2, 3, 5), folds=5, seed=42):
    search = GridSearchCV(DecisionTreeClassifier(random_state=seed),
                          {"max_depth": list(depths)},
                          cv=StratifiedKFold(folds, shuffle=True, random_state=seed),
                          scoring="accuracy", error_score="raise")
    return search.fit(X_train, y_train)


def evaluate_holdout(estimator, X_test, y_test):
    """Use once after selection is frozen; does not fit or select parameters."""
    return {"accuracy": float(estimator.score(X_test, y_test)),
            "predictions": estimator.predict(X_test).tolist()}
