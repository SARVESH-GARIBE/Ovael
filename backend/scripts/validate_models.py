"""
End-to-end validation: load both trained models from disk and run them
against one mock FeatureVector per class — the exact call pattern the
backend teammate will use once orchestrator/ wires these into the API.

Run `python -m ml.multiclass.model` and `python -m ml.novelty.model`
first to produce the saved model files this script loads.
"""

from ml.backend_models.mock_feature_generator import generate_mock_dataset
from ml.backend_models.multiclass.model import MulticlassModel
from ml.backend_models.novelty.model import NoveltyModel


def main():
    multiclass_model = MulticlassModel.load()
    novelty_model = NoveltyModel.load()

    one_per_class = {}
    for row in generate_mock_dataset(n_per_class=20):
        one_per_class.setdefault(row.label, row)

    for label, feature_vector in one_per_class.items():
        predicted_label, confidence = multiclass_model.predict_one(feature_vector)
        multiclass_result = f"({predicted_label}, {confidence:.2f})"

        anomaly_score = novelty_model.predict_one(feature_vector)
        print(
            f"true={label:<12} multiclass={multiclass_result:<28} "
            f"novelty_score={anomaly_score:.2f}"
        )


if __name__ == "__main__":
    main()
