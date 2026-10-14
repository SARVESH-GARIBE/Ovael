"""Shared setup for the paper-evaluation scripts.

Read-only with respect to the backend source: this only imports and calls existing functions.
Adds backend/ to sys.path so `import ovael...` works without installing the package.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
RESULTS_DIR = REPO_ROOT / "results" / "paper_eval"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()


def save_json(name: str, obj) -> Path:
    path = RESULTS_DIR / name
    path.write_text(json.dumps(obj, indent=2, default=str))
    return path


def save_csv(name: str, df) -> Path:
    path = RESULTS_DIR / name
    df.to_csv(path, index=False)
    return path
