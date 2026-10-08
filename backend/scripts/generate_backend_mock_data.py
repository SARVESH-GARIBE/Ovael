"""
Generates a fixture file of mock feature vectors — all four labels
(ml/multiclass/model.py's TARGET_LABELS)
— for the backend teammate to wire up and test the API/database/
dashboard against realistic-looking output before real traffic capture
is ready.

Run: python -m scripts.generate_backend_mock_data
Output: scripts/mock_feature_vectors.json — a JSON list of objects, one
per flow, with the exact fields in feature_extraction.schema.FeatureVector
(including "label", which real inference-time input will NOT have —
the backend can use it to check its own pipeline's output against the
known ground truth).
"""

import dataclasses
import json
import os

from ml.backend_models.mock_feature_generator import generate_mock_dataset
from ml.backend_models.multiclass.model import TARGET_LABELS

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "mock_feature_vectors.json")


def main(n_per_class: int = 50) -> None:
    rows = [
        dataclasses.asdict(row)
        for row in generate_mock_dataset(n_per_class=n_per_class)
        if row.label in TARGET_LABELS
    ]

    with open(OUTPUT_PATH, "w") as f:
        json.dump(rows, f, indent=2)

    print(f"Wrote {len(rows)} mock feature vectors ({TARGET_LABELS}) to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
