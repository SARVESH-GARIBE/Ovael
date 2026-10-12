from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from ovael.config import Settings
from ovael.learning_loop.retrain import retrain
from ovael.ml import datasets, synthetic
from ovael.ml.registry import ModelRegistry


@pytest.fixture(scope="session")
def model_dir(tmp_path_factory):
    """Small but real models for both modules, trained once per test session."""
    d = tmp_path_factory.mktemp("models")
    s = Settings(_env_file=None, model_dir=d, env="test", network_dataset=d / "none.csv", network_unknown_dataset=d / "none2.csv")
    reg = ModelRegistry(d)

    real_load = datasets.load_base

    def small_load(module, settings):
        if module == "network":
            return synthetic.generate(n_per_class=250, seed=3), "synthetic_bootstrap"
        return real_load(module, settings)

    mp = pytest.MonkeyPatch()
    mp.setattr(datasets, "load_base", small_load)
    for m in ("network", "website"):
        retrain(m, s, reg, always_promote=True)
    mp.undo()
    return d


@pytest.fixture
def settings(model_dir, tmp_path) -> Settings:
    return Settings(_env_file=None, env="test", model_dir=model_dir, database_url=f"sqlite+aiosqlite:///{tmp_path / 't.db'}",
                    defense_mode="simulate", retrain_min_new_samples=10_000,
                    network_dataset=tmp_path / "none.csv", network_unknown_dataset=tmp_path / "none2.csv")


@pytest.fixture
def client(settings):
    from ovael.api.app import create_app

    with TestClient(create_app(settings)) as c:
        yield c


def flow(cls: str, seed: int = 0) -> dict:
    import numpy as np

    f, meta = synthetic.sample_flow(cls, np.random.default_rng(seed))
    return {"features": f, **meta}


@pytest.fixture
def make_flow():
    return flow


@pytest.fixture
def website_rows() -> pd.DataFrame:
    return pd.DataFrame([
        {"crawl_status": "success", "instrumentation_status": "ok", "canvas_readback_calls": 3},
        {"crawl_status": "success", "instrumentation_status": "ok", "tracker_requests_cat_advertising": 5},
        {"crawl_status": "success", "instrumentation_status": "ok"},
        {"crawl_status": "failed", "instrumentation_status": "not_run"},
        {"crawl_status": "success", "instrumentation_status": "ok", "tracker_requests_cat_advertising": 2,
         "manual_review_label": "benign"},
    ])
