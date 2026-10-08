import pytest
from fastapi.testclient import TestClient

from api import detections as api
from feature_extraction.schema import to_vector
from learning_loop.hard_example_store import HardExampleStore
from main import app
from ml.backend_models.mock_feature_generator import generate_mock_dataset
from ml.backend_models.multiclass.model import MulticlassModel, TARGET_LABELS
from ml.backend_models.novelty.model import NoveltyModel


@pytest.fixture(scope="module")
def models():
    rows = generate_mock_dataset(n_per_class=300, seed=1)
    mc_rows = [r for r in rows if r.label in TARGET_LABELS]
    mc = MulticlassModel().fit([to_vector(r) for r in mc_rows], [r.label for r in mc_rows])
    nv = NoveltyModel().fit([to_vector(r) for r in rows if r.label == "normal"])
    return mc, nv


@pytest.fixture
def client(models):
    store, hard = api.DetectionStore(), HardExampleStore()
    app.dependency_overrides[api.get_models] = lambda: models
    app.dependency_overrides[api.get_detection_store] = lambda: store
    app.dependency_overrides[api.get_hard_example_store] = lambda: hard
    c = TestClient(app)
    c.hard = hard
    yield c
    app.dependency_overrides.clear()


def _body(row, **extra):
    d = {k: getattr(row, k) for k in ("src_ip", "dst_ip", "src_port", "dst_port", "protocol",
                                     "byte_count", "duration", "packet_rate", "packet_count")}
    return {**d, **extra}


def _row(label):
    return next(r for r in generate_mock_dataset(n_per_class=20, seed=3) if r.label == label)


def test_ddos_end_to_end_matches_contract_shape(client):
    r = client.post("/detections", json=_body(_row("ddos"), simulation_id="sim-abc123"))
    assert r.status_code == 201
    d = r.json()
    for key in ("id", "simulation_id", "timestamp", "multiclass", "novelty", "risk_score", "severity", "explanation"):
        assert key in d
    assert d["simulation_id"] == "sim-abc123" and d["explanation"] is None
    assert d["multiclass"]["label"] == "ddos" and d["severity"] in ("high", "critical")
    assert 0 <= d["risk_score"] <= 100


def test_normal_is_low_and_not_hard(client):
    d = client.post("/detections", json=_body(_row("normal"))).json()
    assert d["multiclass"]["label"] == "normal"
    assert d["severity"] == "low" and not d["is_hard_example"]
    assert len(client.hard) == 0


def test_get_and_list(client):
    made = client.post("/detections", json=_body(_row("ddos"))).json()
    assert client.get(f"/detections/{made['id']}").json() == made
    assert [x["id"] for x in client.get("/detections").json()] == [made["id"]]
    assert client.get("/detections/nope").status_code == 404


def test_invalid_input_rejected(client):
    assert client.post("/detections", json={**_body(_row("ddos")), "protocol": "GRE"}).status_code == 422
    assert client.post("/detections", json={**_body(_row("ddos")), "byte_count": -1}).status_code == 422


class _StubMulticlass:
    def __init__(self, label, confidence):
        self._result = (label, confidence)

    def predict_one(self, feature_vector):
        return self._result


class _StubNovelty:
    def __init__(self, score):
        self._score = score

    def predict_one(self, feature_vector):
        return self._score


def _stub_models(client, label, confidence, novelty):
    app.dependency_overrides[api.get_models] = lambda: (
        _StubMulticlass(label, confidence), _StubNovelty(novelty))


def test_disagreement_writes_hard_example(client):
    _stub_models(client, "normal", 0.99, 0.99)
    d = client.post("/detections", json=_body(_row("port_scan"), simulation_id="sim-1")).json()
    assert d["verdict"] == "suspicious_unknown" and d["is_hard_example"] is True
    assert d["severity"] == "high" and d["risk_score"] >= 60
    pending = client.hard.list_pending()
    assert len(pending) == 1 and pending[0]["simulation_id"] == "sim-1"
    assert pending[0]["multiclass"]["label"] == "normal"


def test_agreement_does_not_write_hard_example(client):
    _stub_models(client, "normal", 0.99, 0.10)
    d = client.post("/detections", json=_body(_row("normal"))).json()
    assert d["verdict"] == "benign" and d["is_hard_example"] is False
    assert len(client.hard) == 0


def test_all_four_classes_flow_through_real_models(client):
    labels = {}
    for r in generate_mock_dataset(n_per_class=10, seed=5):
        labels[r.label] = client.post("/detections", json=_body(r)).json()["multiclass"]["label"]
    assert labels == {k: k for k in ("normal", "ddos", "port_scan", "exfiltration")}
