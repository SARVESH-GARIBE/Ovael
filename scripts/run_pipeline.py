#!/usr/bin/env python3
"""
Build one sample RawTraffic, run it through the Stage 1 pipeline, and
print the resulting FinalAssessment.

Run from anywhere with:
    python scripts/run_pipeline.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the `ovael` package importable when this script is run directly
# (python scripts/run_pipeline.py), without requiring the package to be
# installed. `python scripts/run_pipeline.py` puts scripts/ on sys.path,
# not the repo root, so that has to be added explicitly here.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ovael.contracts.schemas import RawTraffic  # noqa: E402
from ovael.pipeline import pipeline  # noqa: E402


def build_sample_raw_traffic() -> RawTraffic:
    """One hardcoded sample flow, just enough to exercise every stage."""
    return RawTraffic(
        source_ip="192.168.1.10",
        destination_ip="192.168.1.20",
        source_port=51234,
        destination_port=443,
        protocol="TCP",
        payload_size=1500,
        timestamp=1700000000.0,
    )


def main() -> None:
    raw_traffic = build_sample_raw_traffic()
    result = pipeline.run(raw_traffic)

    print("=== Ovael Stage 1 — pipeline run ===")
    print("(Everything below except the contract shapes themselves is a")
    print(" deliberate stub/placeholder — see docs/stage1.md.)\n")

    print("-- RawTraffic (input) --")
    print(result.raw_traffic)

    print("\n-- FeatureVector [STUB: pass-through, not real features] --")
    print(result.feature_vector)

    print("\n-- DetectionResult [STUB: deterministic dummy output] --")
    print(result.detection_result)

    print("\n-- NoveltyResult [STUB: deterministic dummy output] --")
    print(result.novelty_result)

    print("\n-- OrchestrationContext [bundling only, no decision logic] --")
    print(result.orchestration_context)

    print("\n-- RiskAssessment [PLACEHOLDER: not a real risk formula] --")
    print(result.risk_assessment)

    print("\n-- FinalAssessment --")
    print(result)


if __name__ == "__main__":
    main()
