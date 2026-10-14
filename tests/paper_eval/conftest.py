"""Makes the backend package (`ovael`) and the crawler package (`ovael_crawler`) importable,
without installing either. Read-only: only adds import paths, touches no source file.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (REPO_ROOT / "backend", REPO_ROOT / "dataset_collection"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
