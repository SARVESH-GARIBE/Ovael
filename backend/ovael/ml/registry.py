"""File-based model registry shared by every backend instance.

    model_store/<module>/<version>/bundle.joblib   the model pair
    model_store/<module>/<version>/meta.json       metrics, label source, timestamps
    model_store/<module>/ACTIVE                    name of the version serving traffic

Versions are never overwritten, so a bad retrain can be rolled back. Promotion rewrites ACTIVE
atomically. Every API replica checks the pointer's mtime on use and hot-swaps to the new version,
so promoting on one instance reaches all of them through the shared volume without a restart.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path

import joblib

from .bundle import ModelBundle

log = logging.getLogger(__name__)


class ModelNotAvailable(RuntimeError):
    pass


class ModelRegistry:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._lock = threading.Lock()
        self._loaded: dict[str, tuple[float, ModelBundle]] = {}

    def _dir(self, module: str) -> Path:
        return self.root / module

    def _pointer(self, module: str) -> Path:
        return self._dir(module) / "ACTIVE"

    # ------------------------------------------------------------------ versions
    def next_version(self, module: str) -> str:
        nums = [int(m.group(1)) for p in self._dir(module).glob(f"{module}-v*")
                if (m := re.fullmatch(rf"{module}-v(\d+)", p.name))]
        return f"{module}-v{max(nums, default=0) + 1}"

    def save(self, bundle: ModelBundle) -> Path:
        d = self._dir(bundle.module) / bundle.version
        d.mkdir(parents=True, exist_ok=False)
        joblib.dump(bundle, d / "bundle.joblib", compress=3)
        (d / "meta.json").write_text(json.dumps(bundle.summary(), indent=2, default=str))
        return d

    def list_versions(self, module: str) -> list[dict]:
        active = self.active_version(module)
        out = []
        for meta in sorted(self._dir(module).glob("*/meta.json")):
            m = json.loads(meta.read_text())
            m["status"] = "active" if m["version"] == active else "inactive"
            out.append(m)
        return sorted(out, key=lambda m: int(m["version"].rsplit("v", 1)[-1]), reverse=True)

    def meta(self, module: str, version: str) -> dict:
        p = self._dir(module) / version / "meta.json"
        if not p.exists():
            raise ModelNotAvailable(f"{version} does not exist")
        return json.loads(p.read_text())

    def active_version(self, module: str) -> str | None:
        p = self._pointer(module)
        return p.read_text().strip() if p.exists() else None

    def promote(self, module: str, version: str) -> None:
        if not (self._dir(module) / version / "bundle.joblib").exists():
            raise ModelNotAvailable(f"{version} does not exist")
        tmp = self._pointer(module).with_suffix(".tmp")
        tmp.write_text(version)
        os.replace(tmp, self._pointer(module))
        log.info("promoted %s", version)

    # ------------------------------------------------------------------ loading
    def load(self, module: str, version: str) -> ModelBundle:
        return joblib.load(self._dir(module) / version / "bundle.joblib")

    def active(self, module: str) -> ModelBundle:
        pointer = self._pointer(module)
        try:
            mtime = pointer.stat().st_mtime
        except FileNotFoundError:
            raise ModelNotAvailable(f"no trained {module} model; run `python -m ovael.cli train {module}`")
        cached = self._loaded.get(module)
        if cached and cached[0] == mtime:
            return cached[1]
        with self._lock:
            cached = self._loaded.get(module)
            if cached and cached[0] == mtime:
                return cached[1]
            bundle = self.load(module, self.active_version(module))
            self._loaded[module] = (mtime, bundle)
            log.info("loaded %s", bundle.version)
            return bundle

    def available(self, module: str) -> bool:
        try:
            self.active(module)
            return True
        except Exception:
            return False
