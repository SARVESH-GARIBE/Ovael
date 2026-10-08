"""
Phase 0 validation: prove the ML pipeline runs end to end on a benchmark
dataset. This is NOT the final Multiclass Model — just a sanity check
that data loading, training, and evaluation work with scikit-learn
before any real feature extraction or orchestrator code exists.

Dataset: KDD Cup 1999 (10% subset), the direct predecessor to NSL-KDD,
fetched via sklearn's built-in loader so no manual download is needed.
"""

from sklearn.datasets import fetch_kddcup99
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
from sklearn.preprocessing import OrdinalEncoder


def main():
    data = fetch_kddcup99(subset="SA", percent10=True, as_frame=True)
    X, y = data.data, data.target.astype(str)

    categorical_cols = X.select_dtypes(exclude="number").columns
    X = X.copy()
    X[categorical_cols] = OrdinalEncoder().fit_transform(X[categorical_cols])

    # Not stratified: a handful of attack classes in this subset have only
    # 1-2 samples total, too few to stratify on.
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    clf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
    print(classification_report(y_test, y_pred, zero_division=0))


if __name__ == "__main__":
    main()
