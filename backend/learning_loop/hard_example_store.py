"""
Minimal store for hard examples: flows where the decision table flagged
is_hard_example=True (models disagree). In-memory, with optional
JSONL file backing so entries survive a restart. Review workflow and
retraining are separate, later modules.
"""

import json
import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

from feature_extraction.schema import FeatureVector


class HardExampleStore:
    def __init__(self, path: str | None = None):
        self._path = path
        self._lock = threading.Lock()
        self._items: dict[str, dict] = {}
        if path:
            self._load(path)

    def _load(self, path: str) -> None:
        try:
            with open(path) as f:
                for line in f:
                    if line.strip():
                        item = json.loads(line)
                        self._items[item["id"]] = item
        except FileNotFoundError:
            pass

    def add(
        self,
        feature_vector: FeatureVector,
        multiclass: tuple[str, float],
        novelty_score: float,
        simulation_id: str | None = None,
    ) -> str:
        item = {
            "id": str(uuid.uuid4()),
            "simulation_id": simulation_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "features": asdict(feature_vector),
            "multiclass": {"label": multiclass[0], "confidence": multiclass[1]},
            "novelty": {"score": novelty_score},
            "status": "pending",
        }
        with self._lock:
            self._items[item["id"]] = item
            if self._path:
                with open(self._path, "a") as f:
                    f.write(json.dumps(item) + "\n")
        return item["id"]

    def get(self, item_id: str) -> dict | None:
        return self._items.get(item_id)

    def list_pending(self) -> list[dict]:
        return [i for i in self._items.values() if i["status"] == "pending"]

    def __len__(self) -> int:
        return len(self._items)
