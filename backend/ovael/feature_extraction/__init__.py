"""Feature schemas and builders for both modules."""

from __future__ import annotations

from .network_schema import NETWORK_FEATURE_DESCRIPTIONS, NETWORK_FEATURES
from .website_schema import WEBSITE_FEATURE_DESCRIPTIONS, WEBSITE_FEATURES

MODULES = ("network", "website")

SCHEMAS: dict[str, list[str]] = {"network": NETWORK_FEATURES, "website": WEBSITE_FEATURES}
DESCRIPTIONS: dict[str, dict[str, str]] = {
    "network": NETWORK_FEATURE_DESCRIPTIONS,
    "website": WEBSITE_FEATURE_DESCRIPTIONS,
}


def describe(module: str, feature: str) -> str:
    return DESCRIPTIONS[module].get(feature, feature.replace("_", " "))
