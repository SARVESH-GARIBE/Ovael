import pytest

from feature_extraction.schema import LABELS, FeatureVector, to_vector, validate
from ml.backend_models.mock_feature_generator import generate_mock_dataset
from ml.backend_models.multiclass.model import MulticlassModel, TARGET_LABELS
from ml.backend_models.novelty.model import NoveltyModel
from ml.backend_models.novelty.score_calibration import ScoreCalibrator
from orchestrator.decision_table import decide


def _rows(label, n=50):
    return [r for r in generate_mock_dataset(n_per_class=n, seed=7) if r.label == label]


@pytest.fixture(scope="module")
def multiclass():
    rows = [r for r in generate_mock_dataset(n_per_class=300, seed=1) if r.label in TARGET_LABELS]
    return MulticlassModel().fit([to_vector(r) for r in rows], [r.label for r in rows])


@pytest.fixture(scope="module")
def novelty():
    normal = [r for r in generate_mock_dataset(n_per_class=1000, seed=1) if r.label == "normal"]
    return NoveltyModel().fit([to_vector(r) for r in normal])


def test_multiclass_targets_every_schema_label():
    assert set(TARGET_LABELS) == set(LABELS)


def test_schema_vector_order():
    fv = FeatureVector("1.1.1.1", "2.2.2.2", 1234, 80, "TCP", 10.0, 1.0, 5.0, 5)
    validate(fv)
    assert to_vector(fv) == [10.0, 1.0, 5.0, 5.0, 1234.0, 80.0]


def test_multiclass_separates_normal_and_ddos(multiclass):
    for label in TARGET_LABELS:
        rows = _rows(label)
        correct = sum(multiclass.predict_one(r)[0] == label for r in rows)
        assert correct / len(rows) > 0.95


def test_novelty_scores_in_range_and_ranks_attacks_higher(novelty):
    normal = [novelty.predict_one(r) for r in _rows("normal")]
    ddos = [novelty.predict_one(r) for r in _rows("ddos")]
    assert all(0.0 <= s <= 1.0 for s in normal + ddos)
    assert sum(ddos) / len(ddos) > sum(normal) / len(normal)


def test_both_models_feed_decision_table(multiclass, novelty):
    r = _rows("ddos", 1)[0]
    label, conf = multiclass.predict_one(r)
    assert decide(label, conf, novelty.predict_one(r)).verdict in {"known_attack", "confirmed_attack"}


def test_calibrator_requires_fit():
    with pytest.raises(RuntimeError):
        ScoreCalibrator().transform(0.5)
