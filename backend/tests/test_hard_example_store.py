from feature_extraction.schema import FeatureVector
from learning_loop.hard_example_store import HardExampleStore

FV = FeatureVector("1.1.1.1", "2.2.2.2", 1234, 80, "TCP", 100.0, 1.0, 5.0, 5)


def test_add_get_and_pending():
    store = HardExampleStore()
    item_id = store.add(FV, ("normal", 0.97), 0.99, "sim-1")
    item = store.get(item_id)
    assert item["status"] == "pending" and item["simulation_id"] == "sim-1"
    assert item["multiclass"] == {"label": "normal", "confidence": 0.97}
    assert store.list_pending() == [item] and len(store) == 1


def test_file_backed_survives_reload(tmp_path):
    path = str(tmp_path / "hard.jsonl")
    item_id = HardExampleStore(path).add(FV, ("normal", 0.97), 0.99)
    reloaded = HardExampleStore(path)
    assert reloaded.get(item_id)["novelty"]["score"] == 0.99
